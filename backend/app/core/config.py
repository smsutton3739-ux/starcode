"""Application settings.

Everything is environment-driven. Nothing secret has a usable default: the app
refuses to boot in production if a secret is left at its development value.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_SENTINEL = "dev-only-insecure-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Identity -----------------------------------------------------------
    APP_NAME: str = "Starcode"
    APP_TAGLINE: str = "Paste any ancient text, manuscript, prophecy, or historical document."
    ENVIRONMENT: Literal["development", "test", "staging", "production"] = "development"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # ---- Security -----------------------------------------------------------
    SECRET_KEY: str = DEV_SECRET_SENTINEL
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_MINUTES: int = 60
    REFRESH_TOKEN_TTL_DAYS: int = 30
    # Comma-separated in env, parsed to a list.
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    TRUSTED_HOSTS: str = "*"
    ALLOW_ANONYMOUS_ANALYSIS: bool = True
    """The homepage must work with zero friction. Anonymous submissions are allowed and
    rate-limited far more aggressively than authenticated ones."""

    # ---- OAuth --------------------------------------------------------------
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    OAUTH_REDIRECT_BASE: str = "http://localhost:8000"
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # ---- Database -----------------------------------------------------------
    DATABASE_URL: str = "postgresql+psycopg://starcode:starcode@localhost:5432/starcode"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_ECHO: bool = False

    # ---- Cache / queue ------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 3600
    JOB_POLL_INTERVAL_SECONDS: float = 0.5

    # ---- Rate limiting (requests per window) --------------------------------
    RATE_LIMIT_ANONYMOUS_PER_HOUR: int = 10
    RATE_LIMIT_USER_PER_HOUR: int = 120
    RATE_LIMIT_ADMIN_PER_HOUR: int = 1000
    RATE_LIMIT_WINDOW_SECONDS: int = 3600

    # ---- AI -----------------------------------------------------------------
    ANTHROPIC_API_KEY: str = ""
    AI_MODEL: str = "claude-opus-5"
    AI_FAST_MODEL: str = "claude-haiku-4-5-20251001"
    AI_MAX_TOKENS: int = 8000
    AI_TEMPERATURE: float = 0.2
    AI_MAX_RETRIES: int = 3
    AI_TIMEOUT_SECONDS: float = 120.0
    AI_HYPOTHESIS_CONFIDENCE_CAP: float = 0.55
    """Hard ceiling on the confidence any AI-generated hypothesis may report. A model
    cannot talk its way into certainty about an interpretive question."""
    AI_PROVIDER: Literal["anthropic", "offline", "auto"] = "auto"
    """'auto' uses Anthropic when a key is present and the deterministic offline engine
    otherwise, so the platform is fully functional (and testable) without credentials."""

    # ---- Ingestion ----------------------------------------------------------
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024
    MAX_TEXT_CHARS: int = 400_000
    UPLOAD_DIR: str = "/tmp/starcode-uploads"  # noqa: S108 - overridden in deployment
    ALLOWED_UPLOAD_MIME: str = (
        "text/plain,text/markdown,application/pdf,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "image/png,image/jpeg,image/tiff,image/webp"
    )
    URL_FETCH_TIMEOUT_SECONDS: float = 20.0
    URL_FETCH_MAX_BYTES: int = 5 * 1024 * 1024
    OCR_LANGUAGES: str = "eng"

    # ---- Observability ------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"

    @field_validator("SECRET_KEY")
    @classmethod
    def _no_empty_secret(cls, v: str) -> str:
        return v or DEV_SECRET_SENTINEL

    @model_validator(mode="after")
    def _production_hardening(self) -> Settings:
        if self.ENVIRONMENT == "production":
            if self.SECRET_KEY == DEV_SECRET_SENTINEL:
                raise ValueError(
                    "SECRET_KEY is still the development sentinel. Set a real secret "
                    "before running in production."
                )
            if self.DEBUG:
                raise ValueError("DEBUG must be false in production.")
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS may not be '*' in production.")
        return self

    # ---- Derived helpers ----------------------------------------------------
    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def trusted_hosts(self) -> list[str]:
        return [h.strip() for h in self.TRUSTED_HOSTS.split(",") if h.strip()]

    @property
    def allowed_upload_mime(self) -> set[str]:
        return {m.strip() for m in self.ALLOWED_UPLOAD_MIME.split(",") if m.strip()}

    @property
    def ocr_languages(self) -> str:
        return "+".join(p.strip() for p in self.OCR_LANGUAGES.split(",") if p.strip())

    @property
    def use_anthropic(self) -> bool:
        if self.AI_PROVIDER == "anthropic":
            return True
        if self.AI_PROVIDER == "offline":
            return False
        return bool(self.ANTHROPIC_API_KEY)

    @property
    def is_test(self) -> bool:
        return self.ENVIRONMENT == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def new_secret() -> str:
    """Convenience for `python -c 'from app.core.config import new_secret; print(new_secret())'`."""
    return secrets.token_urlsafe(48)


settings = get_settings()

__all__ = ["Settings", "get_settings", "settings", "new_secret", "Field"]
