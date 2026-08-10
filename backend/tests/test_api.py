"""API integration tests, exercising the real HTTP surface end to end."""

from __future__ import annotations

import io
import time

import pytest

from app.db.models.user import Role


def wait_for(client, analysis_id, token=None, headers=None, timeout=30.0):
    """Poll until the analysis leaves the queue.

    Needs whichever credential can read it: the anonymous capability token, or an
    Authorization header for an owned analysis.
    """
    headers = dict(headers or {})
    if token:
        headers["X-Analysis-Token"] = token
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/v1/analyses/{analysis_id}/status", headers=headers)
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in ("completed", "partial", "failed"):
            return payload
        time.sleep(0.05)
    pytest.fail(f"Analysis {analysis_id} did not finish within {timeout}s")


class TestPublicSurface:
    def test_root_points_at_the_one_button(self, client):
        payload = client.get("/").json()
        assert payload["start_here"]["path"].endswith("/analyses")
        assert "Paste any ancient text" in payload["tagline"]

    def test_health(self, client):
        payload = client.get("/api/v1/health").json()
        assert payload["status"] in ("ok", "degraded")
        assert "ai_provider" in payload

    def test_openapi_schema_is_valid(self, client):
        schema = client.get("/openapi.json").json()
        assert schema["info"]["title"]
        assert "/api/v1/analyses" in schema["paths"]

    def test_security_headers_present(self, client):
        response = client.get("/api/v1/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "X-Request-ID" in response.headers


class TestAnonymousAnalysis:
    def test_full_flow_without_an_account(self, client, sample_text):
        """The homepage promise: paste, press one button, get a report — no signup."""
        created = client.post("/api/v1/analyses", json={"text": sample_text})
        assert created.status_code == 202, created.text
        payload = created.json()
        token = payload["anonymous_token"]
        assert token, "anonymous submissions must return a retrieval token"

        status = wait_for(client, payload["id"], token)
        assert status["status"] in ("completed", "partial")

        detail = client.get(
            f"/api/v1/analyses/{payload['id']}", headers={"X-Analysis-Token": token}
        ).json()
        assert detail["report"]["executive_summary"]
        assert detail["claims"]
        assert detail["entities"]

    def test_anonymous_analysis_is_unreachable_without_the_token(self, client, sample_text):
        created = client.post("/api/v1/analyses", json={"text": sample_text}).json()
        response = client.get(f"/api/v1/analyses/{created['id']}")
        assert response.status_code == 404

    def test_wrong_token_is_rejected(self, client, sample_text):
        created = client.post("/api/v1/analyses", json={"text": sample_text}).json()
        response = client.get(
            f"/api/v1/analyses/{created['id']}", headers={"X-Analysis-Token": "wrong"}
        )
        assert response.status_code == 404

    def test_every_claim_carries_a_type_and_presentation(self, client, sample_text):
        created = client.post("/api/v1/analyses", json={"text": sample_text}).json()
        wait_for(client, created["id"], created["anonymous_token"])
        detail = client.get(
            f"/api/v1/analyses/{created['id']}",
            headers={"X-Analysis-Token": created["anonymous_token"]},
        ).json()

        valid = {
            ct["value"] for ct in client.get("/api/v1/corpus/claim-types").json()["claim_types"]
        }
        for claim in detail["claims"]:
            assert claim["claim_type"] in valid
            assert claim["presentation"]["label"]
            assert 0.0 <= claim["confidence"] <= 1.0

    def test_calculations_name_their_engine(self, client, sample_text):
        """A calculation without provenance is indistinguishable from a guess."""
        created = client.post("/api/v1/analyses", json={"text": sample_text}).json()
        wait_for(client, created["id"], created["anonymous_token"])
        detail = client.get(
            f"/api/v1/analyses/{created['id']}",
            headers={"X-Analysis-Token": created["anonymous_token"]},
        ).json()

        calculations = [
            c for c in detail["claims"] if c["claim_type"] == "astronomical_calculation"
        ]
        assert calculations, "this sample text contains a convertible date"
        for claim in calculations:
            assert claim["engine"]

    def test_no_uncited_verified_history_reaches_the_client(self, client, sample_text):
        created = client.post("/api/v1/analyses", json={"text": sample_text}).json()
        wait_for(client, created["id"], created["anonymous_token"])
        detail = client.get(
            f"/api/v1/analyses/{created['id']}",
            headers={"X-Analysis-Token": created["anonymous_token"]},
        ).json()

        for claim in detail["claims"]:
            if claim["claim_type"] in ("verified_history", "scholarly_interpretation"):
                assert claim["references"], (
                    f"uncited {claim['claim_type']}: {claim['statement'][:80]}"
                )


class TestValidation:
    def test_empty_submission_rejected(self, client):
        assert client.post("/api/v1/analyses", json={}).status_code == 422

    def test_two_sources_rejected(self, client):
        response = client.post(
            "/api/v1/analyses", json={"text": "hello", "url": "https://example.com"}
        )
        assert response.status_code == 422
        assert "exactly one source" in response.text

    def test_blank_text_rejected(self, client):
        assert client.post("/api/v1/analyses", json={"text": "   "}).status_code == 422

    def test_validation_errors_are_per_field(self, client):
        payload = client.post("/api/v1/analyses", json={}).json()
        assert payload["error"] == "validation_failed"
        assert payload["field_errors"]
        assert payload["request_id"]


class TestAuth:
    def test_register_and_sign_in(self, client):
        email = f"newuser-{time.time_ns()}@starcode-test.org"
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "a-long-enough-passphrase"},
        )
        assert registered.status_code == 201
        tokens = registered.json()

        me = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert me.status_code == 200
        assert me.json()["email"] == email

        signed_in = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "a-long-enough-passphrase"},
        )
        assert signed_in.status_code == 200

    def test_weak_password_rejected(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "weak@starcode-test.org", "password": "short"},
        )
        assert response.status_code == 422

    def test_wrong_password_rejected(self, client, user_factory):
        user = user_factory(password="the-correct-passphrase")
        response = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "wrong-passphrase"}
        )
        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    def test_duplicate_registration_does_not_confirm_the_address(self, client, user_factory):
        """The response must not reveal whether an address is already registered in a way
        that differs from any other rejection."""
        user = user_factory()
        response = client.post(
            "/api/v1/auth/register",
            json={"email": user.email, "password": "a-long-enough-passphrase"},
        )
        assert response.status_code == 409
        assert user.email not in response.text

    def test_refresh_token_is_not_accepted_as_an_access_token(self, client):
        email = f"refresh-{time.time_ns()}@starcode-test.org"
        tokens = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "a-long-enough-passphrase"},
        ).json()
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
        )
        assert response.status_code == 401

    def test_protected_route_requires_auth(self, client):
        assert client.get("/api/v1/analyses").status_code == 401


class TestAuthorization:
    def test_admin_routes_refuse_ordinary_users(self, client, auth_headers):
        headers, _ = auth_headers(Role.USER)
        response = client.get("/api/v1/admin/users", headers=headers)
        assert response.status_code == 403
        assert "requires the admin role" in response.json()["detail"]

    def test_admin_routes_allow_admins(self, client, auth_headers):
        headers, _ = auth_headers(Role.ADMIN)
        assert client.get("/api/v1/admin/users", headers=headers).status_code == 200

    def test_users_cannot_read_each_others_analyses(self, client, auth_headers, sample_text):
        owner_headers, _ = auth_headers(Role.USER)
        created = client.post(
            "/api/v1/analyses", json={"text": sample_text}, headers=owner_headers
        ).json()

        other_headers, _ = auth_headers(Role.USER)
        response = client.get(f"/api/v1/analyses/{created['id']}", headers=other_headers)
        # 404 rather than 403: a 403 would confirm the id exists.
        assert response.status_code == 404

    def test_admin_cannot_demote_themselves(self, client, auth_headers):
        headers, admin = auth_headers(Role.ADMIN)
        response = client.patch(
            f"/api/v1/admin/users/{admin.id}/role", json={"role": "user"}, headers=headers
        )
        assert response.status_code == 400
        assert "cannot remove your own admin role" in response.json()["detail"]


class TestAuthenticatedFlow:
    def test_analysis_lifecycle(self, client, auth_headers, sample_text):
        headers, _ = auth_headers(Role.USER)

        created = client.post(
            "/api/v1/analyses",
            json={"text": sample_text, "title": "My analysis"},
            headers=headers,
        ).json()
        assert created["anonymous_token"] is None
        wait_for(client, created["id"], headers=headers, timeout=30)

        listing = client.get("/api/v1/analyses", headers=headers).json()
        assert listing["total"] >= 1

        updated = client.patch(
            f"/api/v1/analyses/{created['id']}",
            json={"is_favorite": True, "tags": ["prophecy", "Revelation"]},
            headers=headers,
        ).json()
        assert updated["is_favorite"] is True
        assert set(updated["tags"]) == {"prophecy", "Revelation"}

        favorites = client.get("/api/v1/analyses?favorites_only=true", headers=headers).json()
        assert favorites["total"] >= 1

        assert (
            client.delete(f"/api/v1/analyses/{created['id']}", headers=headers).status_code == 200
        )

    def test_dashboard(self, client, auth_headers):
        headers, _ = auth_headers(Role.USER)
        payload = client.get("/api/v1/dashboard", headers=headers).json()
        assert "totals" in payload
        assert "by_status" in payload

    def test_share_link_grants_read_access(self, client, auth_headers, sample_text):
        headers, _ = auth_headers(Role.USER)
        created = client.post(
            "/api/v1/analyses", json={"text": sample_text}, headers=headers
        ).json()
        wait_for(client, created["id"], headers=headers)

        share = client.post(
            f"/api/v1/analyses/{created['id']}/share",
            json={"expires_in_days": 7},
            headers=headers,
        ).json()
        assert share["token"]

        # A different user reaches it only with the token.
        other_headers, _ = auth_headers(Role.USER)
        assert (
            client.get(f"/api/v1/analyses/{created['id']}", headers=other_headers).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/analyses/{created['id']}",
                headers={**other_headers, "X-Analysis-Token": share["token"]},
            ).status_code
            == 200
        )

        client.delete(f"/api/v1/shares/{share['id']}", headers=headers)
        assert (
            client.get(
                f"/api/v1/analyses/{created['id']}",
                headers={**other_headers, "X-Analysis-Token": share["token"]},
            ).status_code
            == 404
        )

    def test_share_token_is_never_returned_again(self, client, auth_headers, sample_text):
        headers, _ = auth_headers(Role.USER)
        created = client.post(
            "/api/v1/analyses", json={"text": sample_text}, headers=headers
        ).json()
        wait_for(client, created["id"], headers=headers)
        client.post(f"/api/v1/analyses/{created['id']}/share", json={}, headers=headers)

        listed = client.get(f"/api/v1/analyses/{created['id']}/shares", headers=headers).json()
        assert all(s["token"] is None for s in listed)

    def test_collections(self, client, auth_headers, sample_text):
        headers, _ = auth_headers(Role.USER)
        collection = client.post(
            "/api/v1/collections", json={"name": "Apocalyptic texts"}, headers=headers
        ).json()
        created = client.post(
            "/api/v1/analyses", json={"text": sample_text}, headers=headers
        ).json()
        wait_for(client, created["id"], headers=headers)

        assert (
            client.post(
                f"/api/v1/collections/{collection['id']}/analyses/{created['id']}",
                headers=headers,
            ).status_code
            == 200
        )

        detail = client.get(f"/api/v1/collections/{collection['id']}", headers=headers).json()
        assert len(detail["analyses"]) == 1


class TestExports:
    @pytest.fixture
    def finished(self, client, auth_headers, sample_text):
        headers, _ = auth_headers(Role.USER)
        created = client.post(
            "/api/v1/analyses", json={"text": sample_text}, headers=headers
        ).json()
        wait_for(client, created["id"], headers=headers)
        return created["id"], headers

    @pytest.mark.parametrize(
        "fmt,signature",
        [
            ("pdf", b"%PDF-"),
            ("docx", b"PK\x03\x04"),
            ("csv", b"\xef\xbb\xbf"),
            ("markdown", b"#"),
            ("json", b"{"),
        ],
    )
    def test_every_format_produces_a_valid_file(self, client, finished, fmt, signature):
        analysis_id, headers = finished
        response = client.get(f"/api/v1/analyses/{analysis_id}/export/{fmt}", headers=headers)
        assert response.status_code == 200, response.text
        assert response.content.startswith(signature)
        assert "attachment" in response.headers["content-disposition"]
        assert len(response.content) > 100

    def test_exports_preserve_claim_type_labelling(self, client, finished):
        """The distinction between calculation and conjecture must survive the export."""
        analysis_id, headers = finished
        markdown = client.get(
            f"/api/v1/analyses/{analysis_id}/export/markdown", headers=headers
        ).text
        assert "[Source text]" in markdown or "[Astronomical calculation]" in markdown
        assert "labelled by kind" in markdown

    def test_csv_has_a_claim_type_column(self, client, finished):
        import csv

        analysis_id, headers = finished
        body = client.get(
            f"/api/v1/analyses/{analysis_id}/export/csv", headers=headers
        ).content.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(body)))
        assert rows
        assert "claim_type" in rows[0]
        assert "is_evidence" in rows[0]

    def test_unknown_format_rejected(self, client, finished):
        analysis_id, headers = finished
        response = client.get(f"/api/v1/analyses/{analysis_id}/export/xlsx", headers=headers)
        assert response.status_code == 400


class TestReferenceEndpoints:
    def test_eclipses(self, client):
        payload = client.get(
            "/api/v1/astronomy/eclipses?start_year=2017&end_year=2017&kind=solar"
        ).json()
        assert payload["count"] == 2

    def test_span_guard(self, client):
        response = client.get("/api/v1/astronomy/eclipses?start_year=-1000&end_year=1000")
        assert response.status_code == 400
        assert "exceeds" in response.json()["detail"]

    def test_calendar_conversion(self, client):
        payload = client.get(
            "/api/v1/calendars/convert?system=gregorian&year=2024&month=10&day=3"
        ).json()
        hebrew = next(c for c in payload["conversions"] if c["system"] == "hebrew")
        assert hebrew["year"] == 5785

    def test_maya_conversion_reports_the_correlation(self, client):
        payload = client.get(
            "/api/v1/calendars/convert/maya?baktun=13&katun=0&tun=0&uinal=0&kin=0"
        ).json()
        gregorian = next(c for c in payload["conversions"] if c["system"] == "gregorian")
        assert "21 December 2012" in gregorian["label"]

    def test_engine_info_states_its_limitations(self, client):
        payload = client.get("/api/v1/astronomy/engine").json()
        assert payload["known_limitations"]
        assert any("ground track" in limit for limit in payload["known_limitations"])

    def test_corpus_discloses_that_it_is_a_demonstration_set(self, client):
        payload = client.get("/api/v1/corpus/sources").json()
        assert "demonstration corpus" in payload["disclosure"]

    def test_claim_type_vocabulary_is_published(self, client):
        payload = client.get("/api/v1/corpus/claim-types").json()
        assert len(payload["claim_types"]) == 8
        hypothesis = next(c for c in payload["claim_types"] if c["value"] == "ai_hypothesis")
        assert hypothesis["is_evidence"] is False

    def test_pipeline_is_described(self, client):
        payload = client.get("/api/v1/corpus/pipeline").json()
        assert len(payload["agents"]) == 8
        deterministic = [a["name"] for a in payload["agents"] if a["deterministic"]]
        assert set(deterministic) == {"calendar", "astronomy"}


class TestSearch:
    def test_corpus_search_finds_a_quoted_passage(self, client):
        payload = client.post(
            "/api/v1/search",
            json={
                "query": "the sun shall be turned into darkness and the moon into blood",
                "scope": "corpus",
            },
        ).json()
        assert payload["total"] >= 1
        assert "Joel" in payload["hits"][0]["title"]

    def test_irrelevant_query_returns_nothing_rather_than_noise(self, client):
        payload = client.post(
            "/api/v1/search",
            json={"query": "quarterly earnings guidance for semiconductors", "scope": "corpus"},
        ).json()
        assert payload["total"] == 0
        assert "relevance floor" in payload["note"]

    def test_analysis_search_is_scoped_to_the_owner(self, client, auth_headers, sample_text):
        owner_headers, _ = auth_headers(Role.USER)
        client.post(
            "/api/v1/analyses",
            json={"text": sample_text, "title": "Belshazzar vision study"},
            headers=owner_headers,
        )
        other_headers, _ = auth_headers(Role.USER)
        payload = client.post(
            "/api/v1/search",
            json={"query": "Belshazzar vision study", "scope": "analyses", "mode": "keyword"},
            headers=other_headers,
        ).json()
        assert payload["total"] == 0


class TestUploads:
    def test_text_file_upload(self, client, sample_text):
        response = client.post(
            "/api/v1/uploads",
            files={"file": ("prophecy.txt", sample_text.encode(), "text/plain")},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["extracted_characters"] > 0
        assert payload["document_id"]

    def test_html_disguised_as_text_is_refused(self, client):
        """Content is sniffed, not trusted. An HTML payload is a stored-XSS vector."""
        response = client.post(
            "/api/v1/uploads",
            files={
                "file": (
                    "notes.txt",
                    b"<script>alert(document.cookie)</script>",
                    "text/plain",
                )
            },
        )
        assert response.status_code == 400
        assert "HTML or script markup" in response.json()["detail"]

    def test_executable_extension_refused(self, client):
        response = client.post(
            "/api/v1/uploads",
            files={"file": ("payload.exe", b"MZ\x90\x00binary", "application/octet-stream")},
        )
        assert response.status_code == 400

    def test_empty_file_refused(self, client):
        response = client.post("/api/v1/uploads", files={"file": ("empty.txt", b"", "text/plain")})
        assert response.status_code == 400

    def test_limits_endpoint(self, client):
        payload = client.get("/api/v1/uploads/limits").json()
        assert payload["max_upload_bytes"] > 0
        assert "application/pdf" in payload["accepted_mime_types"]

    def test_uploaded_document_can_be_analysed(self, client, sample_text):
        upload = client.post(
            "/api/v1/uploads",
            files={"file": ("text.txt", sample_text.encode(), "text/plain")},
        ).json()
        created = client.post("/api/v1/analyses", json={"document_id": upload["document_id"]})
        assert created.status_code == 202


class TestTrace:
    def test_trace_explains_every_step(self, client, sample_text):
        created = client.post("/api/v1/analyses", json={"text": sample_text}).json()
        wait_for(client, created["id"], created["anonymous_token"])

        trace = client.get(
            f"/api/v1/analyses/{created['id']}/trace",
            headers={"X-Analysis-Token": created["anonymous_token"]},
        ).json()

        assert len(trace["steps"]) == 8
        for step in trace["steps"]:
            assert step["agent"]
            assert step["status"] in ("succeeded", "failed", "skipped")
            assert step["reasoning"], f"{step['agent']} gave no reasoning summary"
        assert trace["claim_type_totals"]
