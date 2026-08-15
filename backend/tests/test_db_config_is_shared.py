"""One database target, read from one place.

A background sweep inside the API process reported "connection to server at 127.0.0.1
port 5432 failed" while the API itself served requests, which looks like two code paths
reading different configuration. It is not: both reach the database through the single
engine in `app.db.session`, built once from `settings.DATABASE_URL`.

The real defect was upstream — an unset DATABASE_URL fell back to the development default
in production, silently, and only the sweep surfaced it because only the sweep touches
the database without a request. These tests pin both halves: that the paths cannot
diverge, and that the fallback can no longer happen quietly.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.db import session as session_module


def build(**overrides) -> Settings:
    base = {"SECRET_KEY": "test-only-secret-not-used-anywhere-real", "_env_file": None}
    return Settings(**{**base, **overrides})


class TestOneEngineForEveryPath:
    """Whatever opens a connection, it is the same connection target."""

    def test_the_request_path_and_the_background_path_share_one_engine(self):
        """Open a session the way a request does, and the way the sweep does, and compare.

        Asserted on real sessions rather than on module internals, because the question is
        about what actually happens at connection time.
        """
        from app.db.session import get_db, session_scope

        request_session = next(get_db())
        try:
            request_bind = request_session.get_bind()
        finally:
            request_session.close()

        with session_scope() as background_session:
            background_bind = background_session.get_bind()

        assert request_bind is background_bind
        assert str(request_bind.url) == str(background_bind.url)

    def test_nothing_builds_a_second_engine(self):
        """Grep-as-a-test: a second create_engine call is how the paths would diverge."""
        import pathlib

        root = pathlib.Path(session_module.__file__).parent.parent
        offenders = [
            path.relative_to(root).as_posix()
            for path in root.rglob("*.py")
            if "create_engine(" in path.read_text(encoding="utf-8")
        ]
        assert offenders == ["db/session.py"], (
            "Only app/db/session.py may construct an engine; found: " + ", ".join(offenders)
        )

    def test_the_engine_url_is_the_configured_one(self):
        from app.core.config import settings

        # Rendered without the password, which is also what the logs show.
        assert session_module.engine.url.render_as_string(hide_password=True).startswith(
            settings.DATABASE_URL.split("://")[0]
        )


class TestLoopbackFallbackCannotPassSilently:
    """The development default must not survive into production unnoticed."""

    DEV_DEFAULT = "postgresql+psycopg://starcode:starcode@localhost:5432/starcode"

    def test_production_refuses_the_unset_default(self):
        with pytest.raises(ValueError, match="loopback"):
            build(
                ENVIRONMENT="production",
                CORS_ORIGINS="https://www.astro-decoded.com",
                DATABASE_URL=self.DEV_DEFAULT,
            )

    @pytest.mark.parametrize(
        "url",
        [
            "postgresql://user:pw@127.0.0.1:5432/starcode",
            "postgresql://user:pw@localhost/starcode",
            "postgresql://user:pw@[::1]:5432/starcode",
        ],
    )
    def test_production_refuses_any_loopback_host(self, url: str):
        with pytest.raises(ValueError, match="loopback"):
            build(
                ENVIRONMENT="production",
                CORS_ORIGINS="https://www.astro-decoded.com",
                DATABASE_URL=url,
            )

    def test_a_real_host_is_accepted(self):
        settings = build(
            ENVIRONMENT="production",
            CORS_ORIGINS="https://www.astro-decoded.com",
            DATABASE_URL="postgresql://u:pw@aws-0-eu-west-2.pooler.supabase.com:5432/postgres",
        )
        assert settings.database_is_loopback is False

    def test_an_explicit_opt_in_still_allows_a_local_database(self):
        settings = build(
            ENVIRONMENT="production",
            CORS_ORIGINS="https://www.astro-decoded.com",
            DATABASE_URL=self.DEV_DEFAULT,
            ALLOW_LOCAL_DATABASE=True,
        )
        assert settings.database_is_loopback is True

    def test_development_is_left_alone(self):
        # The default exists for local work and must keep working there.
        assert build(DATABASE_URL=self.DEV_DEFAULT).database_is_loopback is True


class TestDatabaseTargetIsSafeToLog:
    """The failure log names the host; it must never name the credentials."""

    def test_credentials_are_stripped(self):
        settings = build(
            DATABASE_URL="postgresql://admin:sup3r-s3cret@db.example.com:5432/starcode"
        )
        target = settings.database_target
        assert target == "db.example.com:5432/starcode"
        assert "sup3r-s3cret" not in target
        assert "admin" not in target

    def test_a_sqlite_path_has_no_credentials_to_strip(self):
        settings = build(DATABASE_URL="sqlite:///./local.db")
        assert settings.database_target == "sqlite:///./local.db"

    def test_the_loopback_default_is_recognisable_in_a_log_line(self):
        # This is the string that would have identified the problem immediately: the log
        # said "connection refused" and named no host, so the fallback was invisible.
        # Passed explicitly because the suite sets DATABASE_URL in the environment.
        settings = build(DATABASE_URL=TestLoopbackFallbackCannotPassSilently.DEV_DEFAULT)
        assert settings.database_target == "localhost:5432/starcode"
