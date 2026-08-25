"""billing tiers and stripe subscription state

Revision ID: 48cd064670a4
Revises: d4a97f2e6b18
Create Date: 2026-08-25 20:30:43.742083

Why the billing columns live on `users` rather than in a one-to-one `subscriptions`
table, since that was a genuine choice:

The tier is read on the analysis *read* path — every claim served is filtered by it — so
a separate table would put a join or a lazy load on the hottest query in the application
in exchange for normalising four columns. And the usual reason to split billing out,
keeping history, does not apply: Stripe is the system of record for invoices, proration
and past subscriptions, so a local table would have no history to append. What is kept
here is only the cached answer to "may this account read interpretive claims", which is
inherently one-per-user and always current.

`tier` is added WITH a server default. Autogenerate proposed it as NOT NULL with no
default, which cannot apply to a table that already has rows — every existing user would
violate the constraint the moment the column appears. The default is spelled 'FREE',
upper case, because SQLAlchemy's Enum(native_enum=False) persists the member *name* and
not its value; a default of 'free' would write rows the ORM then fails to load.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "48cd064670a4"
down_revision: str | None = "d4a97f2e6b18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processed_stripe_events",
        # Stripe's own event id is the natural key, which is what makes replay protection
        # a primary-key conflict rather than a check-then-write two deliveries could race.
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processed_stripe_events")),
    )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "tier",
                sa.Enum("FREE", "PAID", "BYOK", name="tier", native_enum=False, length=20),
                nullable=False,
                server_default="FREE",
            )
        )
        batch_op.add_column(sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(sa.Column("subscription_status", sa.String(length=40), nullable=True))
        batch_op.add_column(
            sa.Column("byok_anthropic_key_last4", sa.String(length=4), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_users_stripe_customer_id"), ["stripe_customer_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_users_stripe_subscription_id"), ["stripe_subscription_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_stripe_subscription_id"))
        batch_op.drop_index(batch_op.f("ix_users_stripe_customer_id"))
        batch_op.drop_column("byok_anthropic_key_last4")
        batch_op.drop_column("subscription_status")
        batch_op.drop_column("stripe_subscription_id")
        batch_op.drop_column("stripe_customer_id")
        batch_op.drop_column("tier")

    op.drop_table("processed_stripe_events")
