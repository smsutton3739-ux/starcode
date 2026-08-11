"""Settings that have to survive contact with a hosting platform.

These are not unit tests of pydantic. They pin the specific shapes that a real deploy
hands the app, each of which has a failure mode that reads as something else entirely.
"""

from __future__ import annotations

import pytest

from app.core.config import DEV_SECRET_SENTINEL, Settings


def build(**overrides) -> Settings:
    """A Settings that ignores the ambient environment.

    `_env_file=None` matters: conftest sets DATABASE_URL for the suite, and without this
    every case here would silently test that value instead of the one passed in.
    """
    base = {"SECRET_KEY": "test-only-secret-not-used-anywhere-real", "_env_file": None}
    return Settings(**{**base, **overrides})


class TestDatabaseUrl:
    """Managed platforms hand out a URL SQLAlchemy 2 cannot use as-is."""

    @pytest.mark.parametrize(
        "given",
        [
            "postgresql://user:pw@host:5432/starcode",
            "postgres://user:pw@host:5432/starcode",
        ],
    )
    def test_a_platform_supplied_url_is_given_its_driver(self, given: str):
        # Pasting the connection string Render or Railway shows you is the obvious thing
        # to do, and it used to fail at import with a message about a missing DBAPI.
        assert build(DATABASE_URL=given).DATABASE_URL == (
            "postgresql+psycopg://user:pw@host:5432/starcode"
        )

    def test_credentials_and_query_parameters_survive_intact(self):
        given = "postgresql://u%40odd:p%3Aw@host:5432/db?sslmode=require&application_name=x"
        result = build(DATABASE_URL=given).DATABASE_URL
        assert result == (
            "postgresql+psycopg://u%40odd:p%3Aw@host:5432/db?sslmode=require&application_name=x"
        )

    def test_an_explicit_driver_is_left_alone(self):
        # Someone who chose asyncpg meant it.
        for url in (
            "postgresql+psycopg://user:pw@host/db",
            "postgresql+asyncpg://user:pw@host/db",
            "postgresql+pg8000://user:pw@host/db",
        ):
            assert build(DATABASE_URL=url).DATABASE_URL == url

    def test_sqlite_is_untouched(self):
        assert build(DATABASE_URL="sqlite:///./local.db").DATABASE_URL == "sqlite:///./local.db"


class TestProductionHardening:
    """The checks that make a misconfigured production refuse to boot rather than run."""

    def test_the_development_secret_is_refused(self):
        with pytest.raises(ValueError, match="SECRET_KEY"):
            build(ENVIRONMENT="production", SECRET_KEY=DEV_SECRET_SENTINEL)

    def test_wildcard_cors_is_refused(self):
        with pytest.raises(ValueError, match="CORS_ORIGINS"):
            build(ENVIRONMENT="production", CORS_ORIGINS="*")

    def test_debug_is_refused(self):
        with pytest.raises(ValueError, match="DEBUG"):
            build(ENVIRONMENT="production", DEBUG=True)

    def test_a_correctly_configured_production_starts(self):
        settings = build(
            ENVIRONMENT="production",
            CORS_ORIGINS="https://www.astro-decoded.com",
            DATABASE_URL="postgresql://user:pw@host:5432/starcode",
        )
        assert settings.cors_origins == ["https://www.astro-decoded.com"]
        assert settings.DATABASE_URL.startswith("postgresql+psycopg://")


class TestAccountDefaults:
    def test_passwords_are_off_and_anonymous_use_is_on(self):
        # The product decision, asserted where it is declared: the homepage works with no
        # account, and no credential is offered that nobody could recover.
        assert Settings.model_fields["ALLOW_PASSWORD_REGISTRATION"].default is False
        assert Settings.model_fields["ALLOW_ANONYMOUS_ANALYSIS"].default is True
