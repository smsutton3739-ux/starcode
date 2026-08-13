"""Widen astronomical_events.computation_engine to hold a citation

For a computed event this column names the algorithm, which is short. For a catalogue
entry it carries the scholarly citation the figure is drawn from, and the Halley
apparitions cite Yeomans & Kiang (1981) at 137 characters against a VARCHAR(120).

Same root cause as the previous revision — SQLite ignores VARCHAR lengths, so seeding
passed locally and failed on PostgreSQL — and found the same way, one column at a time.
The test added with it now seeds and then measures every stored string against its own
column, so the whole class is checked at once rather than whichever column happened to
fail first.

A separate revision rather than an edit to b2c41f7a9d38: that one may already have been
applied to a deployed database, and rewriting applied history leaves those databases
quietly disagreeing with the migration that claims to describe them.

Revision ID: c7e83b1d4a52
Revises: b2c41f7a9d38
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7e83b1d4a52"
down_revision: str | None = "b2c41f7a9d38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch mode, because SQLite has no ALTER COLUMN TYPE.
    with op.batch_alter_table("astronomical_events") as batch:
        batch.alter_column(
            "computation_engine",
            existing_type=sa.String(length=120),
            type_=sa.String(length=300),
            existing_nullable=True,
        )


def downgrade() -> None:
    op.execute(
        "UPDATE astronomical_events SET computation_engine = substr(computation_engine, 1, 120) "
        "WHERE length(computation_engine) > 120"
    )
    with op.batch_alter_table("astronomical_events") as batch:
        batch.alter_column(
            "computation_engine",
            existing_type=sa.String(length=300),
            type_=sa.String(length=120),
            existing_nullable=True,
        )
