"""Column widths, checked against the values we actually write.

The tests run on SQLite, which ignores VARCHAR lengths entirely. PostgreSQL does not: it
rejects the row. So a column too narrow for its own contents passes every test here and
then fails on the first real deployment, during seeding, before the app serves anything.

That is not hypothetical — `astronomical_events.calendar_used` was VARCHAR(20) with a
26-character default, and seeding a real PostgreSQL could not complete. These assertions
are made against the model metadata rather than a live database, so they hold on either
engine and fail in the suite rather than in production.
"""

from __future__ import annotations

import pytest
from sqlalchemy import String

from app.astronomy.catalogs import COMET_APPARITIONS, HISTORICAL_SUPERNOVAE
from app.db.base import Base
from app.knowledge import corpus


def string_columns():
    """Every String column in the schema, with its declared length."""
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if isinstance(column.type, String) and column.type.length:
                yield table.name, column.name, column, column.type.length


def test_no_column_is_too_narrow_for_its_own_default():
    """A column that cannot hold its own default is broken for every row that omits it."""
    too_narrow = []
    for table_name, column_name, column, length in string_columns():
        default = getattr(column.default, "arg", None)
        if isinstance(default, str) and len(default) > length:
            too_narrow.append(
                f"{table_name}.{column_name} is VARCHAR({length}) but its default "
                f"{default!r} is {len(default)} characters"
            )
    assert not too_narrow, "\n".join(too_narrow)


def declared_length(table: str, column: str) -> int:
    return Base.metadata.tables[table].columns[column].type.length


@pytest.mark.parametrize(
    "value",
    sorted(
        {
            row.get("calendar_used", "julian_proleptic")
            for row in corpus.RECORDED_ASTRONOMICAL_EVENTS
        }
        | {"julian_gregorian_proleptic"}
    ),
)
def test_every_calendar_name_the_seeder_writes_fits(value: str):
    assert len(value) <= declared_length("astronomical_events", "calendar_used")


@pytest.mark.parametrize("designation", [c.designation for c in COMET_APPARITIONS])
def test_comet_designations_fit(designation: str):
    assert len(designation) <= declared_length("astronomical_events", "designation")


@pytest.mark.parametrize("supernova", HISTORICAL_SUPERNOVAE)
def test_supernova_fields_fit(supernova: dict):
    # These take the column default for calendar_used, which is how the overflow was
    # reached in the first place.
    assert len(str(supernova["designation"])) <= declared_length(
        "astronomical_events", "designation"
    )
    assert len(str(supernova["constellation"])) <= declared_length(
        "astronomical_events", "constellation"
    )


def test_seed_corpus_slugs_and_labels_fit():
    problems = []
    for row in corpus.HISTORICAL_SOURCES:
        for field, column in (("slug", "slug"), ("title", "title")):
            limit = declared_length("historical_sources", column)
            if len(str(row[field])) > limit:
                problems.append(f"historical_sources.{column}: {row[field]!r} exceeds {limit}")
    for row in corpus.SOURCE_PASSAGES:
        limit = declared_length("source_passages", "reference_label")
        if len(str(row["reference_label"])) > limit:
            problems.append(
                f"source_passages.reference_label: {row['reference_label']!r} exceeds {limit}"
            )
    assert not problems, "\n".join(problems)
