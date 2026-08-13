"""Widen astronomical_events.calendar_used to fit its own default

The column was VARCHAR(20) while its default value, "julian_gregorian_proleptic", is 26
characters. Every row that did not set the column explicitly — every comet apparition and
historical supernova in the catalogue — therefore failed to insert on PostgreSQL with
"value too long for type character varying(20)", which meant seeding a real database
could not complete at all.

It went unnoticed because SQLite does not enforce VARCHAR lengths: the entire test suite
passed against a schema that PostgreSQL rejects. The regression test added alongside this
migration asserts the constraint against the model metadata rather than against a live
database, so it holds on either engine.

A separate migration rather than an edit to the initial one: the initial revision may
already be applied to a deployed database, and rewriting applied history would leave
those databases silently inconsistent with the migration that claims to describe them.

Revision ID: b2c41f7a9d38
Revises: 0935df4c3e73
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c41f7a9d38"
down_revision: str | None = "0935df4c3e73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch_alter_table, because SQLite has no ALTER COLUMN TYPE and a plain alter_column
    # raises a syntax error there. Batch mode recreates the table on SQLite and emits an
    # ordinary ALTER on PostgreSQL, so development and production take the same path.
    with op.batch_alter_table("astronomical_events") as batch:
        batch.alter_column(
            "calendar_used",
            existing_type=sa.String(length=20),
            type_=sa.String(length=40),
            existing_nullable=False,
        )


def downgrade() -> None:
    # Truncate before narrowing: a row written since the upgrade may hold a value the old
    # width cannot store, and PostgreSQL fails the ALTER rather than truncating for you.
    # Losing the tail of a calendar name is recoverable by re-seeding; a downgrade that
    # errors halfway through a migration run is not.
    #
    # substr() rather than left() — the latter does not exist on SQLite.
    op.execute(
        "UPDATE astronomical_events SET calendar_used = substr(calendar_used, 1, 20) "
        "WHERE length(calendar_used) > 20"
    )
    with op.batch_alter_table("astronomical_events") as batch:
        batch.alter_column(
            "calendar_used",
            existing_type=sa.String(length=40),
            type_=sa.String(length=20),
            existing_nullable=False,
        )
