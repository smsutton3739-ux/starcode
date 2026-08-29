"""Operational tables: audit log and the background job queue."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.db.types import JSONBType


class AuditAction(str, enum.Enum):
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    REGISTER = "register"
    ANALYSIS_CREATED = "analysis_created"
    ANALYSIS_VIEWED = "analysis_viewed"
    ANALYSIS_DELETED = "analysis_deleted"
    ANALYSIS_EXPORTED = "analysis_exported"
    ANALYSIS_SHARED = "analysis_shared"
    UPLOAD_RECEIVED = "upload_received"
    UPLOAD_REJECTED = "upload_rejected"
    URL_FETCHED = "url_fetched"
    SETTINGS_UPDATED = "settings_updated"
    ROLE_CHANGED = "role_changed"
    USER_DEACTIVATED = "user_deactivated"
    PROMPT_UPDATED = "prompt_updated"
    DATASET_UPDATED = "dataset_updated"
    BILLING_CHECKOUT_STARTED = "billing_checkout_started"
    BILLING_PORTAL_OPENED = "billing_portal_opened"
    BILLING_SUBSCRIPTION_CHANGED = "billing_subscription_changed"
    RATE_LIMITED = "rate_limited"
    ADMIN_ACTION = "admin_action"
    SECURITY_EVENT = "security_event"


class AuditLog(UUIDPrimaryKey, Base):
    """Append-only. No `updated_at`, and the API exposes no mutation route.

    Records the actor, the target, and enough request context to reconstruct an incident
    without storing anything that would itself be sensitive.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, native_enum=False, length=40), nullable=False
    )
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_email: Mapped[str | None] = mapped_column(String(320))
    """Denormalised: an audit trail must survive deletion of the account it describes."""

    target_type: Mapped[str | None] = mapped_column(String(60))
    target_id: Mapped[str | None] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    """Hashed, not stored raw — enough to correlate abuse, not enough to track a person."""

    user_agent: Mapped[str | None] = mapped_column(String(500))
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    detail: Mapped[dict] = mapped_column(JSONBType, default=dict)


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class Job(UUIDPrimaryKey, Timestamped, Base):
    """Durable record of background work.

    The in-process worker and any external queue both write here, so job state survives a
    restart and the admin console can show what is actually happening.
    """

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_priority", "status", "priority", "created_at"),)

    job_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=20), default=JobStatus.PENDING, nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONBType, default=dict)
    result: Mapped[dict] = mapped_column(JSONBType, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    target_type: Mapped[str | None] = mapped_column(String(60))
    target_id: Mapped[str | None] = mapped_column(String(64), index=True)


class ProcessedStripeEvent(Timestamped, Base):
    """Stripe event ids already applied, so a replay is a no-op.

    Stripe retries a webhook until it gets a 2xx, and it does not promise exactly-once
    delivery — a network blip between our commit and our response produces a second
    delivery of an event we have already applied. Without this, a replayed
    `customer.subscription.deleted` could downgrade an account that had since
    re-subscribed.

    The event id is the primary key, so the uniqueness is enforced by the database
    rather than by a check-then-write that two concurrent deliveries could both pass.
    """

    __tablename__ = "processed_stripe_events"

    # Stripe event ids look like evt_1P... — their own identifier is the natural key.
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)


class AstronomicalDatingUsage(UUIDPrimaryKey, Timestamped, Base):
    """One row per astronomical dating search a user runs.

    A log, not a counter, and deliberately so. The free allowance is five searches for
    the life of the account, which a `COUNT(*)` answers exactly — no period arithmetic,
    no month boundary to get wrong, and nothing that needs a scheduled job to reset it.
    That last point is not incidental: this deployment runs with no background worker and
    no Redis on purpose (see docs/GO_LIVE.md), so a quota that required a reset job would
    be a quota that silently never reset.

    Keeping the rows rather than a number also means the usage is auditable — which
    analysis each search produced, and when — so a support question about someone's
    allowance has an answer.
    """

    __tablename__ = "astronomical_dating_usage"
    __table_args__ = (Index("ix_dating_usage_user_created", "user_id", "created_at"),)

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    analysis_id: Mapped[str | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL"), index=True
    )
    mode: Mapped[str] = mapped_column(String(40), nullable=False, default="date")
    """Which dating mode was run. Paid modes are logged too — they are unmetered, but
    knowing what the feature is actually used for is worth the column."""


__all__ = [
    "AuditAction",
    "AuditLog",
    "JobStatus",
    "Job",
    "ProcessedStripeEvent",
    "AstronomicalDatingUsage",
]
