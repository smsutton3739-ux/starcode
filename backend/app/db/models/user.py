"""Identity, access control and per-user preferences."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.db.types import JSONBType

if TYPE_CHECKING:
    from app.db.models.analysis import Analysis
    from app.db.models.content import Collection, Document, Project


class Role(str, enum.Enum):
    """Ordered least → most privileged. `Role.at_least` does the comparison."""

    VIEWER = "viewer"
    USER = "user"
    RESEARCHER = "researcher"
    MODERATOR = "moderator"
    ADMIN = "admin"

    @property
    def rank(self) -> int:
        return _ROLE_RANK[self]

    def at_least(self, other: Role) -> bool:
        return self.rank >= other.rank


_ROLE_RANK = {
    Role.VIEWER: 0,
    Role.USER: 10,
    Role.RESEARCHER: 20,
    Role.MODERATOR: 30,
    Role.ADMIN: 40,
}


class Tier(str, enum.Enum):
    """What a user has paid for. Deliberately orthogonal to `Role`.

    `Role` answers "what is this person allowed to administer"; `Tier` answers "what has
    this person paid for". Conflating them would mean an administrator could not be
    billed and a paying customer would drift upward in privilege — so they are separate
    columns, compared separately, and neither is derived from the other.

    Unordered on purpose: `byok` is not "more" than `paid`, it is a different
    arrangement, so there is no `at_least` here to misuse.
    """

    FREE = "free"
    PAID = "paid"
    BYOK = "byok"

    @property
    def unlocks_interpretation(self) -> bool:
        """Whether this tier sees interpretive claims rather than locked placeholders."""
        return self in (Tier.PAID, Tier.BYOK)


class User(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(String(1024))

    # Null for pure-OAuth accounts. Never stores anything but a bcrypt hash.
    hashed_password: Mapped[str | None] = mapped_column(String(255))

    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=20), default=Role.USER, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ---- Billing ------------------------------------------------------------
    # Kept on `users` rather than in a one-to-one Subscription table: these four fields
    # are read on nearly every authenticated request (tier gating runs on the analysis
    # read path), so a join or a lazy load here would be on the hot path for no gain.
    # Stripe is the system of record for billing *history* — invoices, proration, past
    # subscriptions — so there is nothing for a local table to append to.
    tier: Mapped[Tier] = mapped_column(
        Enum(Tier, native_enum=False, length=20),
        default=Tier.FREE,
        # Declared here as well as in the migration so `alembic check` sees the model and
        # the schema agree. The database-level default is what let the column be added
        # NOT NULL to a table that already had users; spelled as the member *name*,
        # because Enum(native_enum=False) persists names rather than values.
        server_default="FREE",
        nullable=False,
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), index=True)

    # Stripe's own status string, stored verbatim (active, past_due, canceled,
    # incomplete, trialing, unpaid, …). Not re-encoded into a local enum: Stripe adds
    # statuses, and a local enum would silently reject an unrecognised one at exactly
    # the moment a webhook is trying to tell us something new about a paying customer.
    subscription_status: Mapped[str | None] = mapped_column(String(40))

    # Display only — the last four characters of a BYOK key, so the UI can show which
    # key is in use. The key itself is never stored; see services/billing.py.
    byok_anthropic_key_last4: Mapped[str | None] = mapped_column(String(4))

    # Denormalised counters used by the admin usage dashboard.
    analyses_count: Mapped[int] = mapped_column(default=0, nullable=False)

    identities: Mapped[list[OAuthIdentity]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    settings: Mapped[UserSetting | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    projects: Mapped[list[Project]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    analyses: Mapped[list[Analysis]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    collections: Mapped[list[Collection]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN


class OAuthIdentity(UUIDPrimaryKey, Timestamped, Base):
    """A federated login bound to a user. One row per (provider, subject)."""

    __tablename__ = "oauth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_oauth_provider_subject"),
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str | None] = mapped_column(String(320))
    raw_profile: Mapped[dict] = mapped_column(JSONBType, default=dict)

    user: Mapped[User] = relationship(back_populates="identities")


class UserSetting(UUIDPrimaryKey, Timestamped, Base):
    """Per-user preferences. Deliberately a thin, additive JSON blob plus a few
    first-class columns that the API filters on."""

    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    theme: Mapped[str] = mapped_column(String(16), default="system", nullable=False)
    default_output_language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    show_advanced_by_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSONBType, default=dict)

    user: Mapped[User] = relationship(back_populates="settings")


class SystemSetting(UUIDPrimaryKey, Timestamped, Base):
    """Operator-editable runtime configuration (feature flags, model routing, prompts
    toggles). Read through `app.services.system_settings`, which caches."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSONBType, default=dict)
    description: Mapped[str | None] = mapped_column(String(500))
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Notification(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read_at"),)

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(String(2000))
    link: Mapped[str | None] = mapped_column(String(1024))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONBType, default=dict)

    user: Mapped[User] = relationship(back_populates="notifications")


__all__ = [
    "Role",
    "Tier",
    "User",
    "OAuthIdentity",
    "UserSetting",
    "SystemSetting",
    "Notification",
]
