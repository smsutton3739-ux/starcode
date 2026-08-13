"""Column widths, measured against the values actually written.

These tests run on SQLite, which ignores VARCHAR lengths entirely. PostgreSQL rejects the
row instead. So a column too narrow for its contents passes every other test here and then
fails on the first real deployment — during seeding, at container start, before the app
serves anything.

It happened twice: `calendar_used` was VARCHAR(20) with a 26-character default, and
`computation_engine` was VARCHAR(120) holding a 137-character citation. The first fix
enumerated columns by hand and so found only the first one. This measures every string
the seeder writes against its own column, so the whole class is covered rather than
whichever column happens to fail first.
"""

from __future__ import annotations

from sqlalchemy import String, select
from sqlalchemy.orm import Session

from app.db.base import Base


def sized_string_columns(table):
    return [c for c in table.columns if isinstance(c.type, String) and c.type.length]


def test_no_seeded_value_exceeds_its_column(db: Session):
    """Seed data is written on every deploy, so it must fit on the strictest engine.

    The corpus is already seeded by the session fixture, so this reads what is there
    rather than seeding again.
    """
    overflows: list[str] = []

    for table in Base.metadata.sorted_tables:
        columns = sized_string_columns(table)
        if not columns:
            continue
        for row in db.execute(select(table)).mappings():
            for column in columns:
                value = row.get(column.name)
                if isinstance(value, str) and len(value) > column.type.length:
                    overflows.append(
                        f"{table.name}.{column.name} is VARCHAR({column.type.length}) "
                        f"but holds {len(value)} characters: {value[:70]!r}…"
                    )

    # Deduplicated by column: one citation repeated across thirty rows is one bug.
    unique = sorted(set(overflows))
    assert not unique, "\n".join(unique)


def test_no_column_is_too_narrow_for_its_own_default():
    """A column that cannot hold its own default is broken for every row that omits it.

    Checked against metadata rather than data, because a default only reaches the database
    for rows that leave the column unset — which may be none of the rows in a given seed
    and all of the rows in a later one.
    """
    too_narrow = []
    for table in Base.metadata.sorted_tables:
        for column in sized_string_columns(table):
            default = getattr(column.default, "arg", None)
            if isinstance(default, str) and len(default) > column.type.length:
                too_narrow.append(
                    f"{table.name}.{column.name} is VARCHAR({column.type.length}) but its "
                    f"default {default!r} is {len(default)} characters"
                )
    assert not too_narrow, "\n".join(too_narrow)


def test_the_scan_actually_covers_the_tables_that_matter():
    """A scan that silently covered nothing would pass forever.

    The two live failures were both on astronomical_events, populated from the catalogues
    rather than from the corpus module, which is exactly the path that had no test.
    """
    covered = {table.name for table in Base.metadata.sorted_tables if sized_string_columns(table)}
    for expected in (
        "astronomical_events",
        "historical_sources",
        "source_passages",
        "calendar_systems",
        "knowledge_chunks",
    ):
        assert expected in covered, f"{expected} has no sized string columns to check"
