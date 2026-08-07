"""Declarative base and shared column mixins."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Explicit naming convention so Alembic autogenerate produces stable, reviewable names.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class UUIDPrimaryKey:
    """String UUID primary keys: portable across Postgres and SQLite (used in tests)."""

    id: Mapped[str] = mapped_column(primary_key=True, default=new_uuid)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


__all__ = ["Base", "UUIDPrimaryKey", "Timestamped", "utcnow", "new_uuid", "NAMING_CONVENTION"]
