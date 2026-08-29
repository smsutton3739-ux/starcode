"""Who may run an astronomical dating search, how often, and over how many years.

Three rules meet on one request and the order between them is the behaviour: an account
is needed before a role can be read, a role decides whether a tier matters, and a tier
decides whether a count matters. These tests pin each of them and the interactions.

The allowance is deliberately for the life of the account rather than a month, so the
tests that matter most are the ones asserting there is no reset — that is the property a
future "improvement" is most likely to break by adding period arithmetic nobody asked for.
"""

from __future__ import annotations

import pytest

from app.db.models.ops import AstronomicalDatingUsage
from app.db.models.user import Role, Tier, User
from app.services import entitlements

TEXT = "The sun was darkened and the moon became as blood, and Jupiter met Saturn in Pisces."


@pytest.fixture(autouse=True)
def _do_not_run_the_search(monkeypatch):
    """Accept the request; do not run the analysis behind it.

    Everything in this file is about the gate in front of the search — who may ask, how
    often, and over how wide a range — and all of that is decided before a job is
    enqueued. Running the pipeline for each of the sixty-odd requests below would add
    three minutes to the suite and would test what test_dating_search.py already covers.

    It also removes a real source of flakiness rather than papering over one: the
    background thread holds its own session against the same SQLite file the fixtures
    are tearing down, and a fire-and-forget request that nobody waits for races that
    teardown. The one test that does want a pipeline runs it synchronously and waits.
    """
    from app.services import analysis_service

    monkeypatch.setattr(analysis_service, "start_analysis", lambda db, analysis, **kw: None)


def _set_tier(user_id: str, tier: Tier) -> None:
    """Set a tier in its own short-lived session.

    The analysis runs on a background thread with its own session, and a long-lived
    fixture session holds a transaction that blocks that thread's writes — the same
    reason the authenticated lifecycle tests in test_api.py take only `client` and
    `auth_headers`.
    """
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        user = session.get(User, user_id)
        user.tier = tier
        session.commit()


def _usage_count(user_id: str) -> int:
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        return (
            session.query(AstronomicalDatingUsage)
            .filter(AstronomicalDatingUsage.user_id == user_id)
            .count()
        )


def _submit(client, headers, **options):
    return client.post(
        "/api/v1/analyses",
        json={"text": TEXT, "options": {"mode": "date", **options}},
        headers=headers,
    )


class TestWhoMayRunIt:
    def test_an_anonymous_visitor_is_told_to_sign_in(self, client):
        """No anonymous path, because the allowance is counted per account.

        A 401 rather than a silent fallback to ordinary analysis: someone who asked for a
        dating search should not receive something else and be left to notice.
        """
        response = client.post("/api/v1/analyses", json={"text": TEXT, "options": {"mode": "date"}})
        assert response.status_code == 401
        assert "account" in response.json()["detail"].lower()

    def test_ordinary_analysis_still_needs_no_account(self, client):
        """The whole point of making dating a separate mode."""
        response = client.post("/api/v1/analyses", json={"text": TEXT})
        assert response.status_code == 202

    def test_a_signed_in_free_user_may_run_one(self, client, auth_headers):
        headers, user = auth_headers()
        assert _submit(client, headers).status_code == 202
        assert _usage_count(user.id) == 1


class TestTheFreeAllowance:
    def test_five_searches_succeed_and_the_sixth_does_not(self, client, auth_headers):
        headers, user = auth_headers()

        for attempt in range(entitlements.FREE_DATING_SEARCHES):
            response = _submit(client, headers)
            assert response.status_code == 202, f"attempt {attempt + 1}: {response.text}"

        sixth = _submit(client, headers)
        assert sixth.status_code == 402
        detail = sixth.json()["detail"]
        assert "does not reset" in detail
        assert str(entitlements.FREE_DATING_SEARCHES) in detail

    def test_the_allowance_is_for_the_life_of_the_account(self, client, auth_headers):
        """No reset date, and the message must not imply one.

        A monthly quota would need a period boundary and something to run at it. This
        deployment has no background worker by design, so a resetting quota would be one
        that silently never reset — worse than a limit that is honest about being final.
        """
        headers, user = auth_headers()
        for _ in range(entitlements.FREE_DATING_SEARCHES):
            _submit(client, headers)

        blocked = _submit(client, headers)
        assert blocked.status_code == 402
        for word in ("month", "reset date", "renew", "next period"):
            assert word not in blocked.json()["detail"].lower()

    def test_a_search_that_finds_nothing_still_spends_a_use(self, client, auth_headers):
        """Otherwise the quota rewards retrying with ever-wider ranges."""
        headers, user = auth_headers()
        response = client.post(
            "/api/v1/analyses",
            json={
                "text": "These are the generations of the sons of Noah.",
                "options": {"mode": "date"},
            },
            headers=headers,
        )
        assert response.status_code == 202
        assert _usage_count(user.id) == 1

    def test_the_remaining_allowance_is_readable_before_it_is_spent(self, client, auth_headers):
        """So the UI can warn rather than let someone hit a 402 mid-thought."""
        headers, user = auth_headers()

        before = client.get("/api/v1/analyses/dating-quota", headers=headers).json()
        assert before == {
            "used": 0,
            "limit": entitlements.FREE_DATING_SEARCHES,
            "remaining": entitlements.FREE_DATING_SEARCHES,
            "unlimited": False,
            "paid_modes_available": False,
        }

        _submit(client, headers)
        after = client.get("/api/v1/analyses/dating-quota", headers=headers).json()
        assert after["used"] == 1
        assert after["remaining"] == entitlements.FREE_DATING_SEARCHES - 1


class TestPaidAccounts:
    def test_a_paid_account_has_no_limit(self, client, auth_headers):
        headers, user = auth_headers()
        _set_tier(user.id, Tier.PAID)

        for attempt in range(entitlements.FREE_DATING_SEARCHES + 2):
            response = _submit(client, headers)
            assert response.status_code == 202, f"attempt {attempt + 1}: {response.text}"

    def test_its_quota_reads_as_unlimited(self, client, auth_headers):
        headers, user = auth_headers()
        _set_tier(user.id, Tier.PAID)

        quota = client.get("/api/v1/analyses/dating-quota", headers=headers).json()
        assert quota["limit"] is None
        assert quota["unlimited"] is True
        assert quota["paid_modes_available"] is True

    @pytest.mark.parametrize("mode", ["rectification", "eschatological", "historicizing"])
    def test_the_advanced_modes_are_paid_only(self, client, auth_headers, mode):
        """No free allowance at all for these three — not five, none."""
        headers, user = auth_headers()

        blocked = client.post(
            "/api/v1/analyses",
            json={"text": TEXT, "options": {"mode": mode}},
            headers=headers,
        )
        assert blocked.status_code == 402
        assert _usage_count(user.id) == 0, "a refused request must not spend an allowance"

        _set_tier(user.id, Tier.PAID)
        allowed = client.post(
            "/api/v1/analyses",
            json={"text": TEXT, "options": {"mode": mode}},
            headers=headers,
        )
        assert allowed.status_code == 202, allowed.text


class TestTheAdministratorBypass:
    """The site's operator, on their own account, with no subscription behind it."""

    def test_an_admin_passes_the_quota_indefinitely(self, client, auth_headers):
        headers, user = auth_headers(Role.ADMIN)
        assert user.tier is Tier.FREE

        for attempt in range(entitlements.FREE_DATING_SEARCHES + 2):
            response = _submit(client, headers)
            assert response.status_code == 202, f"attempt {attempt + 1}: {response.text}"

    @pytest.mark.parametrize("mode", ["rectification", "eschatological", "historicizing"])
    def test_an_admin_reaches_every_paid_mode(self, client, auth_headers, mode):
        headers, _ = auth_headers(Role.ADMIN)
        response = client.post(
            "/api/v1/analyses",
            json={"text": TEXT, "options": {"mode": mode}},
            headers=headers,
        )
        assert response.status_code == 202, response.text

    def test_nothing_is_metered_or_billed_for_an_admin(self, client, auth_headers):
        """No usage row, no tier change, no Stripe customer.

        The bypass is a per-request decision. If it wrote anything, the operator would
        appear in the usage figures as a customer and in the billing tables as a
        subscriber with nothing behind either.
        """
        headers, user = auth_headers(Role.ADMIN)
        _submit(client, headers)
        _submit(client, headers)

        assert _usage_count(user.id) == 0

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            fresh = session.get(User, user.id)
            assert fresh.tier is Tier.FREE
            assert fresh.stripe_customer_id is None


class TestSpanClamping:
    """A range is a narrowing option. The plan's limit always wins."""

    def test_a_free_account_is_clamped_to_its_span(self, client, auth_headers):
        headers, _ = auth_headers()
        response = _submit(client, headers, date_range_start=-2000, date_range_end=2000)
        assert response.status_code == 202

        options = client.get(f"/api/v1/analyses/{response.json()['id']}", headers=headers).json()[
            "options"
        ]
        assert options["dating_span_cap_years"] == entitlements.FREE_DATING_SPAN_YEARS

    def test_a_paid_account_gets_the_wider_span(self, client, auth_headers):
        headers, user = auth_headers()
        _set_tier(user.id, Tier.PAID)

        response = _submit(client, headers)
        options = client.get(f"/api/v1/analyses/{response.json()['id']}", headers=headers).json()[
            "options"
        ]
        assert options["dating_span_cap_years"] == entitlements.PAID_DATING_SPAN_YEARS

    def test_an_admin_gets_the_paid_span(self, client, auth_headers):
        headers, _ = auth_headers(Role.ADMIN)
        response = _submit(client, headers)
        options = client.get(f"/api/v1/analyses/{response.json()['id']}", headers=headers).json()[
            "options"
        ]
        assert options["dating_span_cap_years"] == entitlements.PAID_DATING_SPAN_YEARS

    def test_the_agent_clamps_a_wide_request_rather_than_failing_it(self):
        """The clamp is applied in the agent too, on the span it actually searches.

        The cap on the request and the span handed to the engine are different numbers in
        different places, and a request wider than the plan allows must narrow rather than
        error: someone who asked for too much should get a smaller search and be told, not
        a rejection.
        """
        from app.agents.base import AnalysisContext
        from app.agents.specialists import AstronomicalDatingAgent

        ctx = AnalysisContext(
            analysis_id="a",
            text=TEXT,
            normalized_text=TEXT,
            db=None,  # type: ignore[arg-type]
            options={
                "mode": "date",
                "dating_span_cap_years": entitlements.FREE_DATING_SPAN_YEARS,
                "date_range_start": -2500,
                "date_range_end": 2500,
            },
        )
        start, end, basis = AstronomicalDatingAgent().span_for(ctx)

        assert end - start + 1 <= entitlements.FREE_DATING_SPAN_YEARS
        assert "clamped" in basis

    def test_a_narrower_request_is_honoured_exactly(self):
        from app.agents.base import AnalysisContext
        from app.agents.specialists import AstronomicalDatingAgent

        ctx = AnalysisContext(
            analysis_id="a",
            text=TEXT,
            normalized_text=TEXT,
            db=None,  # type: ignore[arg-type]
            options={
                "mode": "date",
                "dating_span_cap_years": entitlements.FREE_DATING_SPAN_YEARS,
                "date_range_start": -600,
                "date_range_end": -500,
            },
        )
        start, end, basis = AstronomicalDatingAgent().span_for(ctx)
        assert (start, end) == (-600, -500)
        assert "clamped" not in basis


class TestTheOrdinaryPathIsUntouched:
    def test_a_default_submission_runs_the_default_pipeline(self):
        from app.agents.orchestrator import PIPELINE, pipeline_for
        from app.schemas.analysis import AnalysisOptions

        assert pipeline_for(AnalysisOptions().model_dump()) is PIPELINE

    def test_no_dating_agent_runs_on_a_default_analysis(self):
        from app.agents.orchestrator import PIPELINE

        names = {agent.name for agent, _ in PIPELINE}
        assert "astronomical_dating" not in names
        assert "advanced_dating" not in names

    def test_an_unrecognised_mode_falls_back_rather_than_erroring(self):
        """Options come from a client; a typo should not be an error page."""
        from app.agents.orchestrator import PIPELINE, pipeline_for

        assert pipeline_for({"mode": "dating"}) is PIPELINE
        assert pipeline_for({"mode": None}) is PIPELINE
        assert pipeline_for(None) is PIPELINE
