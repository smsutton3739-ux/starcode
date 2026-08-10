"""Ingestion, file-safety and security-primitive tests."""

from __future__ import annotations

import io

import pytest

from app.core.security import (
    AuthError,
    create_token,
    decode_token,
    hash_ip,
    hash_password,
    hash_token,
    new_opaque_token,
    validate_password_strength,
    verify_password,
    verify_token_hash,
)
from app.db.models.user import Role
from app.services.ingest import (
    IngestError,
    check_upload_safety,
    extract_from_docx,
    extract_from_pdf,
    extract_from_text,
    normalize_text,
    sniff_mime,
    validate_text,
)
from app.services.url_fetch import FetchError, extract_readable_text, validate_url


class TestPasswords:
    def test_hash_and_verify(self):
        hashed = hash_password("a-perfectly-fine-passphrase")
        assert hashed != "a-perfectly-fine-passphrase"
        assert verify_password("a-perfectly-fine-passphrase", hashed)
        assert not verify_password("something-else-entirely", hashed)

    def test_hashes_are_salted(self):
        assert hash_password("same-passphrase") != hash_password("same-passphrase")

    def test_missing_password_fails_closed(self):
        assert verify_password("anything", None) is False

    def test_malformed_hash_fails_closed_rather_than_raising(self):
        assert verify_password("anything", "not-a-bcrypt-hash") is False

    def test_over_length_password_rejected_not_truncated(self):
        """bcrypt truncates at 72 bytes; truncating silently would make two different
        long passwords equivalent."""
        with pytest.raises(ValueError, match="72 bytes"):
            hash_password("x" * 100)

    def test_strength_policy_prefers_length(self):
        assert validate_password_strength("short") != []
        assert validate_password_strength("aaaaaaaaaaaaaaaa") != []  # too few distinct chars
        assert validate_password_strength("password") != []
        assert validate_password_strength("a-perfectly-fine-passphrase") == []

    def test_unicode_passwords_work(self):
        hashed = hash_password("паролькоторыйдлинный")
        assert verify_password("паролькоторыйдлинный", hashed)


class TestTokens:
    def test_round_trip(self):
        token = create_token("user-123", "access", role=Role.USER)
        payload = decode_token(token, "access")
        assert payload["sub"] == "user-123"
        assert payload["role"] == "user"

    def test_kind_confusion_is_rejected(self):
        """A refresh token accepted as an access token silently grants a 30-day session."""
        refresh = create_token("user-123", "refresh")
        with pytest.raises(AuthError, match="Expected a access token"):
            decode_token(refresh, "access")

    def test_tampered_token_rejected(self):
        token = create_token("user-123", "access")
        with pytest.raises(AuthError):
            decode_token(token[:-4] + "AAAA", "access")

    def test_each_token_is_unique(self):
        assert create_token("u", "access") != create_token("u", "access")

    def test_opaque_tokens_are_stored_hashed(self):
        token = new_opaque_token()
        stored = hash_token(token)
        assert token not in stored
        assert verify_token_hash(token, stored)
        assert not verify_token_hash(new_opaque_token(), stored)

    def test_ip_hashing_is_stable_and_not_reversible(self):
        assert hash_ip("203.0.113.5") == hash_ip("203.0.113.5")
        assert "203.0.113.5" not in (hash_ip("203.0.113.5") or "")
        assert hash_ip(None) is None


class TestNormalization:
    def test_strips_control_characters(self):
        assert "\x00" not in normalize_text("bad\x00text")

    def test_strips_zero_width_characters(self):
        assert normalize_text("a​b") == "ab"

    def test_normalizes_line_endings(self):
        assert normalize_text("a\r\nb") == "a\nb"

    def test_preserves_hebrew_and_greek_composition(self):
        """NFC, not NFKC: compatibility folding would destroy distinctions these texts
        depend on."""
        hebrew = "בְּרֵאשִׁית"
        assert normalize_text(hebrew) == hebrew
        greek = "ἐν ἀρχῇ"
        assert normalize_text(greek) == greek

    def test_empty_text_rejected(self):
        with pytest.raises(IngestError, match="empty"):
            validate_text("   \n\n  ")

    def test_oversize_text_rejected(self):
        from app.core.config import settings

        with pytest.raises(IngestError, match="over the"):
            validate_text("word " * (settings.MAX_TEXT_CHARS // 2))


class TestContentSniffing:
    @pytest.mark.parametrize(
        "payload,expected",
        [
            (b"%PDF-1.7\n...", "application/pdf"),
            (b"\x89PNG\r\n\x1a\n", "image/png"),
            (b"\xff\xd8\xff\xe0", "image/jpeg"),
            (b"II*\x00", "image/tiff"),
            (b"Plain prose about eclipses.", "text/plain"),
        ],
    )
    def test_sniffs_by_magic_bytes(self, payload, expected):
        assert sniff_mime(payload) == expected

    def test_detects_html_regardless_of_name(self):
        assert sniff_mime(b"<html><script>alert(1)</script></html>") == "text/html"

    def test_detects_docx_inside_a_zip(self):
        payload = b"PK\x03\x04" + b"\x00" * 40 + b"word/document.xml" + b"\x00" * 100
        assert sniff_mime(payload).endswith("wordprocessingml.document")


class TestUploadSafety:
    def test_declared_type_is_not_trusted(self):
        """A file claiming to be text but containing script markup must be refused."""
        with pytest.raises(IngestError, match="HTML or script markup"):
            check_upload_safety("notes.txt", "text/plain", b"<script>alert(1)</script>")

    @pytest.mark.parametrize(
        "filename", ["run.exe", "script.sh", "page.html", "vector.svg", "code.py"]
    )
    def test_dangerous_extensions_refused(self, filename):
        with pytest.raises(IngestError, match="not accepted"):
            check_upload_safety(filename, "text/plain", b"harmless looking content")

    @pytest.mark.parametrize(
        "filename", ["../../etc/passwd", "dir/file.txt", "back\\slash.txt", "null\x00.txt"]
    )
    def test_path_traversal_in_filename_refused(self, filename):
        with pytest.raises(IngestError, match="not permitted"):
            check_upload_safety(filename, "text/plain", b"content")

    def test_empty_file_refused(self):
        with pytest.raises(IngestError, match="empty"):
            check_upload_safety("a.txt", "text/plain", b"")

    def test_oversize_file_refused(self):
        from app.core.config import settings

        with pytest.raises(IngestError, match="over the"):
            check_upload_safety("big.txt", "text/plain", b"x" * (settings.MAX_UPLOAD_BYTES + 1))

    def test_unsupported_type_refused(self):
        with pytest.raises(IngestError, match="not supported"):
            check_upload_safety("archive.zip", "application/zip", b"PK\x03\x04" + b"\x00" * 100)

    def test_valid_text_accepted(self):
        assert (
            check_upload_safety("t.txt", "text/plain", b"The moon became as blood.") == "text/plain"
        )


class TestDocumentExtraction:
    def test_plain_text(self):
        result = extract_from_text("The sun became black.", title="Fragment")
        assert result.text == "The sun became black."
        assert result.title == "Fragment"
        assert result.ocr_applied is False

    def test_docx_round_trip(self):
        docx = pytest.importorskip("docx")
        document = docx.Document()
        document.add_paragraph("And the moon became as blood.")
        table = document.add_table(rows=1, cols=2)
        table.rows[0].cells[0].text = "587 BC"
        table.rows[0].cells[1].text = "Fall of Jerusalem"
        buffer = io.BytesIO()
        document.save(buffer)

        result = extract_from_docx(buffer.getvalue(), "test.docx")
        assert "moon became as blood" in result.text
        # Tables often hold the chronology in documents like these.
        assert "587 BC" in result.text
        assert "Fall of Jerusalem" in result.text

    def test_pdf_round_trip(self):
        pytest.importorskip("reportlab")
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer)
        pdf.drawString(100, 700, "In 587 BC Jerusalem fell to Babylon.")
        pdf.save()

        result = extract_from_pdf(buffer.getvalue(), "test.pdf")
        assert "587 BC" in result.text
        assert result.page_count == 1

    def test_unreadable_pdf_gives_a_useful_message(self):
        with pytest.raises(IngestError, match="could not be read"):
            extract_from_pdf(b"%PDF-1.4 corrupted garbage", "broken.pdf")


class TestUrlSafety:
    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost/admin",
            "http://127.0.0.1:8000/",
            "http://169.254.169.254/latest/meta-data/",
            "http://metadata.google.internal/",
        ],
    )
    def test_ssrf_targets_refused(self, url):
        """A user-supplied URL is a request this server makes from inside the perimeter."""
        with pytest.raises(FetchError):
            validate_url(url)

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "gopher://x/"])
    def test_non_http_schemes_refused(self, url):
        with pytest.raises(FetchError, match="Only http and https"):
            validate_url(url)

    def test_unresolvable_host_refused(self):
        with pytest.raises(FetchError):
            validate_url("https://this-host-does-not-exist-9f8e7d6c5b4a.invalid/")

    def test_html_extraction_drops_chrome_and_scripts(self):
        html = """
        <html><head><title>Joel 2</title></head>
        <body>
          <nav>Home | About</nav>
          <script>trackUser()</script>
          <article><p>The sun shall be turned into darkness.</p></article>
          <footer>Copyright</footer>
        </body></html>
        """
        title, text = extract_readable_text(html)
        assert title == "Joel 2"
        assert "sun shall be turned into darkness" in text
        assert "trackUser" not in text
        assert "Copyright" not in text


class TestRateLimiting:
    def test_limit_is_enforced_and_reports_remaining(self):
        from app.core import rate_limit

        rate_limit.reset_backend()
        results = [rate_limit.check("test-identity", "test-bucket", limit=3) for _ in range(5)]
        assert [r.allowed for r in results] == [True, True, True, False, False]
        assert results[0].remaining == 2
        assert results[-1].retry_after >= 1

    def test_identities_are_isolated(self):
        from app.core import rate_limit

        rate_limit.reset_backend()
        for _ in range(3):
            rate_limit.check("identity-a", "bucket", limit=3)
        assert rate_limit.check("identity-b", "bucket", limit=3).allowed

    def test_shipped_defaults_favour_authenticated_users(self):
        """Read the declared defaults, not a Settings instance: conftest raises the
        limits via the environment so tests are not throttled, and a constructed
        Settings would pick those up and mask the ordering."""
        from app.core.config import Settings

        default = lambda name: Settings.model_fields[name].default  # noqa: E731

        assert (
            default("RATE_LIMIT_ANONYMOUS_PER_HOUR")
            < default("RATE_LIMIT_USER_PER_HOUR")
            < default("RATE_LIMIT_ADMIN_PER_HOUR")
        )

    def test_each_role_maps_to_its_configured_limit(self):
        from app.core.config import settings
        from app.core.rate_limit import limit_for_role

        assert limit_for_role(None) == settings.RATE_LIMIT_ANONYMOUS_PER_HOUR
        assert limit_for_role("user") == settings.RATE_LIMIT_USER_PER_HOUR
        assert limit_for_role("researcher") == settings.RATE_LIMIT_USER_PER_HOUR
        assert limit_for_role("admin") == settings.RATE_LIMIT_ADMIN_PER_HOUR
        assert limit_for_role("moderator") == settings.RATE_LIMIT_ADMIN_PER_HOUR

    def test_headers_are_well_formed(self):
        from app.core import rate_limit

        rate_limit.reset_backend()
        headers = rate_limit.check("id", "bucket", limit=1).headers()
        assert headers["X-RateLimit-Limit"] == "1"
        assert "X-RateLimit-Reset" in headers
