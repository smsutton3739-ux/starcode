"""Shared test fixtures.

Tests run against SQLite with the deterministic offline AI provider, so the whole suite
needs no services, no network and no credentials.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Must be set before app modules import settings.
_TMP = tempfile.mkdtemp(prefix="starcode-tests-")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP}/test.db")
os.environ.setdefault("AI_PROVIDER", "offline")
os.environ.setdefault("UPLOAD_DIR", f"{_TMP}/uploads")
os.environ.setdefault("SECRET_KEY", "test-only-secret-not-used-anywhere-real")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("RATE_LIMIT_ANONYMOUS_PER_HOUR", "10000")
os.environ.setdefault("RATE_LIMIT_USER_PER_HOUR", "10000")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core import rate_limit  # noqa: E402
from app.db.models import Base, Role, User  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.knowledge.seed import seed_all  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_all(db)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit.reset_backend()
    yield


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user_factory(db: Session):
    created: list[str] = []
    counter = {"n": 0}

    def make(email: str | None = None, role: Role = Role.USER, password: str | None = None) -> User:
        from app.core.security import hash_password

        counter["n"] += 1
        address = email or f"user{counter['n']}-{os.urandom(4).hex()}@starcode-test.org"
        user = User(
            email=address,
            display_name=f"Test user {counter['n']}",
            role=role,
            hashed_password=hash_password(password or "correct-horse-battery"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        created.append(user.id)
        return user

    yield make

    for user_id in created:
        obj = db.get(User, user_id)
        if obj:
            db.delete(obj)
    db.commit()


@pytest.fixture
def auth_headers(user_factory):
    def make(role: Role = Role.USER) -> tuple[dict, User]:
        from app.core.security import create_token

        user = user_factory(role=role)
        token = create_token(user.id, "access", role=user.role)
        return {"Authorization": f"Bearer {token}"}, user

    return make


SAMPLE_TEXT = (
    "And I beheld when he had opened the sixth seal, and, lo, there was a great "
    "earthquake; and the sun became black as sackcloth of hair, and the moon became as "
    "blood; And the stars of heaven fell unto the earth. In the third year of the reign "
    "of Belshazzar king of Babylon a vision appeared unto me. Here is wisdom: his number "
    "is Six hundred threescore and six. In 587 BC Jerusalem fell."
)


@pytest.fixture
def sample_text() -> str:
    return SAMPLE_TEXT


@pytest.fixture
def tmp_upload_dir() -> Path:
    path = Path(_TMP) / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path
