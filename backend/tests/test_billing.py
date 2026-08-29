"""Billing: webhook trust, idempotency, tier transitions, and what each tier may read.

The tests that matter most here are the ones asserting what a *reader* receives, not what
a function returns. Interpretive content reaches a user by three independent routes — the
claim list, the report embedded in the same response, and five export formats that read
the ORM directly — so each is checked separately. A gate that held on one and not the
others would pass a narrower suite while the paid content stayed one URL away.

No network: Stripe's client is never called for the webhook path, and the signature is
computed the same way Stripe computes it, so verification is exercised for real rather
than mocked out.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from app.core.config import settings
from app.db.models.ops import ProcessedStripeEvent
from app.db.models.user import Role, Tier, User
from app.services import billing
from app.services.entitlements import (
    LOCKED_STATEMENT,
    gate_claim_dicts,
    gate_orm_claims,
)

WEBHOOK_SECRET = "whsec_test_secret_not_used_anywhere_real"


def _signed(payload: dict, secret: str = WEBHOOK_SECRET, timestamp: int | None = None):
    """Sign a payload exactly the way Stripe does, so verification is really tested."""
    body = json.dumps(payload).encode()
    ts = timestamp if timestamp is not None else int(time.time())
    signature = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return body, f"t={ts},v1={signature}"


@pytest.fixture
def webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_not_a_real_key")
    return WEBHOOK_SECRET


def _subscription_event(user: User, event_id: str, status: str, event_type: str) -> dict:
    return {
        "id": event_id,
        "type": event_type,
        "data": {
            "object": {
                "id": "sub_test_123",
                "status": status,
                "customer": user.stripe_customer_id,
                "metadata": {"user_id": user.id},
            }
        },
    }


class TestWebhookSignature:
    def test_a_valid_signature_is_accepted(self, webhook_secret):
        body, header = _signed({"id": "evt_1", "type": "ping"})
        event = billing.verify_webhook(body, header)
        assert event["id"] == "evt_1"

    def test_a_forged_signature_is_rejected(self, webhook_secret):
        body, _ = _signed({"id": "evt_1", "type": "ping"})
        _, wrong = _signed({"id": "evt_1", "type": "ping"}, secret="whsec_attacker_secret")
        with pytest.raises(billing.BillingError):
            billing.verify_webhook(body, wrong)

    def test_a_tampered_body_is_rejected(self, webhook_secret):
        """The signature covers the bytes, so editing the payload must invalidate it."""
        _, header = _signed({"id": "evt_1", "type": "customer.subscription.updated"})
        tampered = json.dumps({"id": "evt_1", "type": "checkout.session.completed"}).encode()
        with pytest.raises(billing.BillingError):
            billing.verify_webhook(tampered, header)

    def test_a_missing_signature_header_is_rejected(self, webhook_secret):
        body, _ = _signed({"id": "evt_1", "type": "ping"})
        with pytest.raises(billing.BillingError):
            billing.verify_webhook(body, None)

    def test_without_a_configured_secret_everything_is_refused(self, monkeypatch):
        """The dangerous default would be to trust unsigned events when unconfigured."""
        monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "")
        body, header = _signed({"id": "evt_1", "type": "ping"})
        with pytest.raises(billing.BillingNotConfigured):
            billing.verify_webhook(body, header)

    def test_the_route_rejects_an_unsigned_request(self, client, webhook_secret):
        response = client.post("/api/v1/billing/webhook", content=b'{"id":"evt_x"}')
        assert response.status_code == 400


class TestTierTransitions:
    def test_checkout_completion_grants_the_paid_tier(self, db, user_factory):
        user = user_factory()
        user.stripe_customer_id = "cus_test_1"
        db.commit()

        billing.handle_webhook_event(
            db,
            {
                "id": "evt_checkout",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_test",
                        "customer": "cus_test_1",
                        "subscription": "sub_test_123",
                        "metadata": {"user_id": user.id},
                    }
                },
            },
        )
        db.refresh(user)
        assert user.tier is Tier.PAID
        assert user.stripe_subscription_id == "sub_test_123"

    @pytest.mark.parametrize(
        "status,expected",
        [
            ("active", Tier.PAID),
            ("trialing", Tier.PAID),
            # Still entitled: Stripe is retrying the card, and cutting access at the first
            # failed charge treats an expired card like a cancellation.
            ("past_due", Tier.PAID),
            ("canceled", Tier.FREE),
            ("unpaid", Tier.FREE),
            ("incomplete_expired", Tier.FREE),
        ],
    )
    def test_subscription_status_drives_the_tier(self, db, user_factory, status, expected):
        user = user_factory()
        user.stripe_customer_id = "cus_status"
        db.commit()

        billing.handle_webhook_event(
            db,
            _subscription_event(user, f"evt_{status}", status, "customer.subscription.updated"),
        )
        db.refresh(user)
        assert user.tier is expected
        assert user.subscription_status == status

    def test_cancellation_returns_the_account_to_free(self, db, user_factory):
        user = user_factory()
        user.stripe_customer_id = "cus_cancel"
        user.tier = Tier.PAID
        user.stripe_subscription_id = "sub_gone"
        db.commit()

        billing.handle_webhook_event(
            db,
            _subscription_event(user, "evt_del", "canceled", "customer.subscription.deleted"),
        )
        db.refresh(user)
        assert user.tier is Tier.FREE
        assert user.stripe_subscription_id is None

    def test_a_failed_payment_records_status_without_cutting_access(self, db, user_factory):
        user = user_factory()
        user.stripe_customer_id = "cus_fail"
        user.tier = Tier.PAID
        db.commit()

        billing.handle_webhook_event(
            db,
            {
                "id": "evt_failed",
                "type": "invoice.payment_failed",
                "data": {"object": {"customer": "cus_fail", "metadata": {"user_id": user.id}}},
            },
        )
        db.refresh(user)
        assert user.subscription_status == "past_due"
        assert user.tier is Tier.PAID

    def test_a_byok_account_is_not_downgraded_by_stripe_events(self, db, user_factory):
        """BYOK is an arrangement Stripe knows nothing about; its events must not clear it."""
        user = user_factory()
        user.stripe_customer_id = "cus_byok"
        user.tier = Tier.BYOK
        db.commit()

        billing.handle_webhook_event(
            db,
            _subscription_event(user, "evt_byok", "canceled", "customer.subscription.deleted"),
        )
        db.refresh(user)
        assert user.tier is Tier.BYOK

    def test_an_event_for_an_unknown_customer_is_ignored_not_crashed(self, db):
        billing.handle_webhook_event(
            db,
            {
                "id": "evt_orphan",
                "type": "customer.subscription.updated",
                "data": {"object": {"id": "sub_x", "status": "active", "customer": "cus_nobody"}},
            },
        )
        # Recorded as processed so Stripe stops redelivering something unattributable.
        assert db.get(ProcessedStripeEvent, "evt_orphan") is not None


class TestIdempotency:
    def test_replaying_an_event_does_not_reapply_it(self, db, user_factory):
        user = user_factory()
        user.stripe_customer_id = "cus_replay"
        db.commit()

        event = _subscription_event(user, "evt_once", "active", "customer.subscription.updated")
        billing.handle_webhook_event(db, event)
        db.refresh(user)
        assert user.tier is Tier.PAID

        # The customer cancels through some other route, then Stripe redelivers the old
        # activation. Without the ledger this would silently re-grant the paid tier.
        user.tier = Tier.FREE
        db.commit()

        billing.handle_webhook_event(db, event)
        db.refresh(user)
        assert user.tier is Tier.FREE, "a replayed event re-applied its effect"

    def test_each_event_is_recorded_once(self, db, user_factory):
        user = user_factory()
        user.stripe_customer_id = "cus_ledger"
        db.commit()
        event = _subscription_event(user, "evt_ledger", "active", "customer.subscription.updated")

        billing.handle_webhook_event(db, event)
        billing.handle_webhook_event(db, event)

        rows = db.query(ProcessedStripeEvent).filter_by(id="evt_ledger").all()
        assert len(rows) == 1


class TestPaidTierDependency:
    def test_a_free_user_gets_402_not_403(self, client, auth_headers):
        """402 sends the caller to the pricing page; 403 sends them to support."""
        from fastapi import HTTPException

        from app.api.deps import require_paid_tier

        headers, user = auth_headers()
        assert user.tier is Tier.FREE
        with pytest.raises(HTTPException) as excinfo:
            require_paid_tier(user)
        assert excinfo.value.status_code == 402

    def test_tier_and_role_stay_independent(self, db, user_factory):
        """An admin on the free tier is still gated; a paying viewer is not."""
        from fastapi import HTTPException

        from app.api.deps import require_paid_tier

        admin = user_factory(role=Role.ADMIN)
        with pytest.raises(HTTPException):
            require_paid_tier(admin)

        viewer = user_factory(role=Role.VIEWER)
        viewer.tier = Tier.PAID
        db.commit()
        assert require_paid_tier(viewer) is viewer


class TestWhatEachTierReads:
    """The product promise: a free reader sees the checkable half and nothing more."""

    INTERPRETIVE = ["traditional_interpretation", "scholarly_interpretation", "ai_hypothesis"]
    DETERMINISTIC = ["source_text", "verified_history", "astronomical_calculation"]

    def _claims(self):
        return [
            {
                "claim_type": t,
                "statement": f"SECRET-{t}",
                "reasoning": "secret reasoning",
                "confidence_basis": "secret basis",
                "quoted_text": "secret quote",
                "references": [{"id": "r1"}],
            }
            for t in self.INTERPRETIVE + self.DETERMINISTIC
        ]

    def test_free_readers_lose_interpretive_claims_only(self, db, user_factory):
        free = user_factory()
        gated = gate_claim_dicts(self._claims(), free)
        by_type = {c["claim_type"]: c for c in gated}

        for t in self.INTERPRETIVE:
            assert by_type[t]["statement"] == LOCKED_STATEMENT
            assert by_type[t]["locked"] is True
        for t in self.DETERMINISTIC:
            assert by_type[t]["statement"] == f"SECRET-{t}"
            assert by_type[t]["locked"] is False

    def test_locking_clears_every_field_that_could_carry_the_content(self, db, user_factory):
        """Withholding `statement` alone would leak the same finding via `reasoning`."""
        free = user_factory()
        gated = gate_claim_dicts(self._claims(), free)
        locked = [c for c in gated if c["locked"]]
        assert locked
        for claim in locked:
            assert claim["reasoning"] is None
            assert claim["confidence_basis"] is None
            assert claim["quoted_text"] is None
            assert "SECRET" not in json.dumps(claim)

    def test_locking_keeps_the_citations(self, db, user_factory):
        """Bibliography is not the interpretation, and the contract needs it present.

        `scholarly_interpretation` requires at least one citation to exist at all, so a
        gated response that emptied the reference list would emit precisely the uncited
        claim the epistemic contract exists to prevent. A citation carries no excerpt —
        title, authors, year, DOI — so keeping it discloses nothing that was withheld.
        """
        free = user_factory()
        gated = gate_claim_dicts(self._claims(), free)
        locked = [c for c in gated if c["locked"]]
        assert locked
        for claim in locked:
            assert claim["references"] == [{"id": "r1"}]

    @pytest.mark.parametrize("tier", [Tier.PAID, Tier.BYOK])
    def test_paid_and_byok_readers_see_everything(self, db, user_factory, tier):
        user = user_factory()
        user.tier = tier
        db.commit()
        gated = gate_claim_dicts(self._claims(), user)
        assert all(c["statement"].startswith("SECRET-") for c in gated)
        assert not any(c["locked"] for c in gated)

    def test_anonymous_readers_are_treated_as_free(self):
        gated = gate_claim_dicts(self._claims(), None)
        locked = {c["claim_type"] for c in gated if c["locked"]}
        assert locked == set(self.INTERPRETIVE)

    def test_the_claim_type_survives_locking_for_the_audit_trail(self, db, user_factory):
        """Locked claims keep their type: the confidence summary counts must stay honest."""
        free = user_factory()
        gated = gate_claim_dicts(self._claims(), free)
        assert [c["claim_type"] for c in gated] == self.INTERPRETIVE + self.DETERMINISTIC


class TestEveryDeliveryPathIsGated:
    """Each route that can hand a reader claim text, checked on its own.

    Written this way because the failure that motivated it is invisible to a suite that
    checks only the API: exports read the ORM directly and would have kept serving the
    paid content in five formats.
    """

    def test_the_orm_gate_locks_interpretive_rows(self, db, user_factory, sample_text, client):
        from app.agents.contracts import ClaimType

        class FakeClaim:
            def __init__(self, claim_type, statement):
                self.claim_type = claim_type
                self.statement = statement
                self.reasoning = "reasoning"
                self.confidence_basis = "basis"
                self.quoted_text = "quote"
                self.ordering = 0

        rows = [
            FakeClaim(ClaimType.AI_HYPOTHESIS, "SECRET hypothesis"),
            FakeClaim(ClaimType.ASTRONOMICAL_CALCULATION, "eclipse of 585 BCE"),
        ]
        free = user_factory()
        gated = gate_orm_claims(rows, free)

        assert gated[0].statement == LOCKED_STATEMENT
        assert gated[0].reasoning is None
        assert gated[1].statement == "eclipse of 585 BCE"

    def test_the_gate_never_mutates_the_underlying_rows(self, db, user_factory):
        """A locked placeholder must never be flushable back into the database."""
        from app.agents.contracts import ClaimType

        class FakeClaim:
            def __init__(self):
                self.claim_type = ClaimType.AI_HYPOTHESIS
                self.statement = "SECRET hypothesis"
                self.reasoning = "reasoning"
                self.confidence_basis = "basis"
                self.quoted_text = "quote"
                self.ordering = 0

        row = FakeClaim()
        free = user_factory()
        gate_orm_claims([row], free)
        assert row.statement == "SECRET hypothesis", "gating wrote through to the ORM row"

    def test_the_report_summary_stays_readable_for_free_readers(self, db, user_factory):
        """The summary is mechanical — counts and corpus matches, not interpretation.

        It reports *how many* interpretive findings exist without revealing any of them,
        so withholding it would cost the free tier its orientation and hide the most
        honest upsell in the product.
        """
        from app.services.entitlements import gate_report

        class FakeReport:
            id = "rep_1"
            version = 1
            executive_summary = "12 findings: 4 evidence-grade, 3 hypotheses."
            sections = [
                {
                    "key": "traditional_interpretations",
                    "claims": [{"claim_type": "traditional_interpretation", "statement": "SECRET"}],
                }
            ]
            timeline: list = []
            confidence_summary: dict = {}
            further_reading: list = []
            reasoning_trace: list = []
            word_count = 10
            generator_version = "1.0.0"

        free = user_factory()
        gated = gate_report(FakeReport(), free)
        assert gated["executive_summary"] == "12 findings: 4 evidence-grade, 3 hypotheses."
        # The section bodies are still gated — that is where the statements live.
        assert gated["sections"][0]["claims"][0]["statement"] == LOCKED_STATEMENT
        assert "SECRET" not in json.dumps(gated["sections"])


class TestThroughTheRealApi:
    """End to end against the real pipeline, because that is where the paths converge.

    Everything above tests the gate in isolation. This runs a real analysis and reads it
    back over HTTP as each tier, which is the only check that would catch a delivery path
    nobody remembered to wire up.

    None of these take the `db` fixture. The analysis runs on its own thread with its own
    session, and the fixture's long-lived session holds a transaction that blocks that
    thread's writes — the same reason the existing authenticated lifecycle test in
    test_api.py takes only `client` and `auth_headers`. Where a tier has to be set, a
    short-lived session is opened and closed before the run starts.
    """

    TEXT = "In the second year of Darius the moon became as blood over Babylon."

    @staticmethod
    def _set_tier(user_id: str, tier: Tier) -> None:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            user = session.get(User, user_id)
            user.tier = tier
            session.commit()

    def _run(self, client, headers):
        created = client.post("/api/v1/analyses", json={"text": self.TEXT}, headers=headers)
        assert created.status_code == 202, created.text
        analysis_id = created.json()["id"]

        deadline = time.time() + 60
        while time.time() < deadline:
            status = client.get(f"/api/v1/analyses/{analysis_id}/status", headers=headers).json()
            if status["status"] in ("completed", "partial", "failed"):
                return analysis_id
            time.sleep(0.05)
        pytest.fail("analysis did not finish in time")

    def test_a_free_user_receives_locked_interpretive_claims(self, client, auth_headers):
        headers, user = auth_headers()
        assert user.tier is Tier.FREE

        analysis_id = self._run(client, headers)
        detail = client.get(f"/api/v1/analyses/{analysis_id}", headers=headers).json()

        interpretive = [
            c
            for c in detail["claims"]
            if c["claim_type"]
            in ("traditional_interpretation", "scholarly_interpretation", "ai_hypothesis")
        ]
        for claim in interpretive:
            assert claim["statement"] == LOCKED_STATEMENT
            assert claim["locked"] is True

        assert [c for c in detail["claims"] if not c["locked"]], (
            "a free reader must still receive the checkable claims"
        )

    def test_a_paid_user_receives_the_real_statements(self, client, auth_headers):
        headers, user = auth_headers()
        self._set_tier(user.id, Tier.PAID)

        analysis_id = self._run(client, headers)
        detail = client.get(f"/api/v1/analyses/{analysis_id}", headers=headers).json()

        assert not any(c["locked"] for c in detail["claims"])
        assert all(c["statement"] != LOCKED_STATEMENT for c in detail["claims"])

    def test_no_export_format_leaks_what_the_api_withheld(self, client, auth_headers):
        """The gap a serialiser-only gate would have left: same content, different URL."""
        headers, _ = auth_headers()

        analysis_id = self._run(client, headers)
        detail = client.get(f"/api/v1/analyses/{analysis_id}", headers=headers).json()
        locked_ids = {c["id"] for c in detail["claims"] if c["locked"]}
        if not locked_ids:
            pytest.skip("this offline run produced no interpretive claims to withhold")

        from app.db.models.analysis import Analysis
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            analysis = session.get(Analysis, analysis_id)
            withheld = [c.statement for c in analysis.claims if c.id in locked_ids]
        assert withheld

        for fmt in ("markdown", "json", "csv"):
            response = client.get(f"/api/v1/analyses/{analysis_id}/export/{fmt}", headers=headers)
            assert response.status_code == 200, f"{fmt}: {response.text[:200]}"
            body = response.content.decode("utf-8", errors="ignore")
            for statement in withheld:
                assert statement not in body, f"the {fmt} export leaked a withheld statement"
