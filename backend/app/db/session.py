"""Engine and session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_connect_args: dict = {}
_engine_kwargs: dict = {
    "echo": settings.DATABASE_ECHO,
    "pool_pre_ping": True,
    "future": True,
}

if settings.DATABASE_URL.startswith("sqlite"):
    # Test/dev convenience path. `check_same_thread` is required because FastAPI's
    # threadpool hands sessions between threads.
    _connect_args["check_same_thread"] = False
else:
    _engine_kwargs.update(
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_recycle=1800,
    )

engine: Engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args, **_engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """Foreign keys are off by default in SQLite; the tests rely on them behaving like
    Postgres."""
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency. Rolls back on exception, always closes."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """For background jobs and scripts, which have no request lifecycle."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_all() -> None:
    """Schema creation for tests and first-run development only.

    Production schema changes go through Alembic; see docs/DEPLOYMENT.md.
    """
    from app.db import models  # noqa: F401  (registers mappers)

    models.Base.metadata.create_all(bind=engine)


__all__ = ["engine", "SessionLocal", "get_db", "session_scope", "create_all"]
