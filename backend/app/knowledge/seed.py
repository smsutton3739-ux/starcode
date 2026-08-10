"""Load the curated corpus into the database and build the retrieval index.

Idempotent: safe to run on every deploy. Existing rows are updated in place rather than
duplicated, so re-seeding never multiplies the corpus.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.astronomy.catalogs import (
    COMET_APPARITIONS,
    HISTORICAL_SUPERNOVAE,
    METEOR_SHOWERS,
)
from app.core.logging import get_logger
from app.db.models.knowledge import (
    AstronomicalEvent,
    CalendarSystem,
    Dataset,
    HistoricalSource,
    SourcePassage,
)
from app.knowledge import corpus
from app.knowledge.rag import index_chunk

logger = get_logger(__name__)


def _upsert_sources(db: Session) -> dict[str, str]:
    """Returns slug -> id so passages can be linked."""
    ids: dict[str, str] = {}
    for row in corpus.HISTORICAL_SOURCES:
        existing = db.execute(
            select(HistoricalSource).where(HistoricalSource.slug == row["slug"])
        ).scalar_one_or_none()
        target = existing or HistoricalSource(slug=row["slug"])
        for field, value in row.items():
            if field != "slug":
                setattr(target, field, value)
        if existing is None:
            db.add(target)
        db.flush()
        ids[row["slug"]] = target.id
    return ids


def _upsert_passages(db: Session, source_ids: dict[str, str]) -> int:
    count = 0
    for row in corpus.SOURCE_PASSAGES:
        source_id = source_ids.get(row["source_slug"])
        if source_id is None:
            logger.warning("seed.passage_orphaned", reference=row["reference_label"])
            continue
        existing = db.execute(
            select(SourcePassage).where(
                SourcePassage.source_id == source_id,
                SourcePassage.reference_label == row["reference_label"],
            )
        ).scalar_one_or_none()
        target = existing or SourcePassage(
            source_id=source_id, reference_label=row["reference_label"]
        )
        target.translation = row["translation"]
        target.translation_credit = row.get("translation_credit")
        target.themes = row.get("themes", [])
        target.astronomical_content = row.get("astronomical_content", False)
        target.prophetic_content = row.get("prophetic_content", False)
        target.notes = row.get("notes")
        if existing is None:
            db.add(target)
        count += 1
    return count


def _upsert_calendars(db: Session) -> int:
    count = 0
    for row in corpus.calendar_system_rows():
        existing = db.execute(
            select(CalendarSystem).where(CalendarSystem.key == row["key"])
        ).scalar_one_or_none()
        target = existing or CalendarSystem(key=row["key"])
        for field, value in row.items():
            if field != "key":
                setattr(target, field, value)
        if existing is None:
            db.add(target)
        count += 1
    return count


def _upsert_recorded_events(db: Session, source_ids: dict[str, str]) -> int:
    count = 0
    for row in corpus.RECORDED_ASTRONOMICAL_EVENTS:
        existing = db.execute(
            select(AstronomicalEvent).where(AstronomicalEvent.designation == row["designation"])
        ).scalar_one_or_none()
        target = existing or AstronomicalEvent(designation=row["designation"])
        target.event_type = row["event_type"]
        target.label = row["label"]
        target.year = row.get("year")
        target.month = row.get("month")
        target.day = row.get("day")
        target.calendar_used = row.get("calendar_used", "julian_proleptic")
        target.is_computed = row.get("is_computed", False)
        target.description = row.get("description")
        target.visibility_regions = row.get("visibility_regions", [])
        target.computation_engine = "historical record" if not row.get("is_computed") else None
        slug = row.get("source_slug")
        target.historical_source_id = source_ids.get(slug) if slug else None
        if existing is None:
            db.add(target)
        count += 1

    # Comet apparitions and supernovae from the static catalogues.
    for comet in COMET_APPARITIONS:
        existing = db.execute(
            select(AstronomicalEvent).where(AstronomicalEvent.designation == comet.designation)
        ).scalar_one_or_none()
        target = existing or AstronomicalEvent(designation=comet.designation)
        target.event_type = "comet"
        target.label = f"{comet.name} — {comet.perihelion_note}"
        target.year = comet.year
        target.is_computed = comet.evidence in ("computed_return", "both")
        target.computation_engine = comet.source
        target.description = comet.perihelion_note
        target.attributes = {"evidence": comet.evidence, "records": comet.records}
        if existing is None:
            db.add(target)
        count += 1

    for sn in HISTORICAL_SUPERNOVAE:
        existing = db.execute(
            select(AstronomicalEvent).where(AstronomicalEvent.designation == sn["designation"])
        ).scalar_one_or_none()
        target = existing or AstronomicalEvent(designation=str(sn["designation"]))
        target.event_type = "supernova"
        target.label = f"{sn['designation']} in {sn['constellation']}"
        target.year = int(sn["year"])
        target.is_computed = False
        target.constellation = str(sn["constellation"])
        target.description = str(sn["record"])
        target.attributes = {
            "modern_remnant": sn["modern_remnant"],
            "evidence": sn["evidence"],
        }
        if existing is None:
            db.add(target)
        count += 1

    return count


def _upsert_datasets(db: Session, counts: dict[str, int]) -> None:
    for row in corpus.DATASETS:
        existing = db.execute(select(Dataset).where(Dataset.key == row["key"])).scalar_one_or_none()
        target = existing or Dataset(key=row["key"])
        for field, value in row.items():
            if field != "key":
                setattr(target, field, value)
        target.record_count = counts.get(row["key"], target.record_count or 0)
        if existing is None:
            db.add(target)


def _build_index(db: Session, source_ids: dict[str, str]) -> int:
    """Index passages, source descriptions and catalogue entries for retrieval."""
    count = 0

    by_slug = {row["slug"]: row for row in corpus.HISTORICAL_SOURCES}

    for row in corpus.SOURCE_PASSAGES:
        source = by_slug.get(row["source_slug"])
        if source is None:
            continue
        citation = (
            f"{source['title']}, {row['reference_label']}. "
            f"{row.get('translation_credit', '')}".strip()
        )
        shared_metadata = {
            "reference_label": row["reference_label"],
            "themes": row.get("themes", []),
            "astronomical_content": row.get("astronomical_content", False),
            "prophetic_content": row.get("prophetic_content", False),
            "translation_credit": row.get("translation_credit"),
            "dating_note": source.get("dating_note"),
        }

        # The passage and the scholarly caveat about it are indexed as separate chunks.
        # Mixing them dilutes both vectors: a user pasting a verse should match the verse
        # at full strength, and a user asking "is the blood moon an eclipse?" should reach
        # the caveat directly. The note is linked back so a passage hit can always show it.
        index_chunk(
            db,
            kind="source_passage",
            source_key=row["source_slug"],
            title=f"{source['title']} — {row['reference_label']}",
            content=row["translation"],
            citation=citation,
            tradition=source.get("tradition"),
            historical_source_id=source_ids.get(row["source_slug"]),
            metadata={**shared_metadata, "scholarly_note": row.get("notes")},
        )
        count += 1

        if row.get("notes"):
            index_chunk(
                db,
                kind="scholarly_note",
                source_key=row["source_slug"],
                title=f"On {source['title']} {row['reference_label']}",
                content=row["notes"],
                citation=citation,
                tradition=source.get("tradition"),
                historical_source_id=source_ids.get(row["source_slug"]),
                metadata={**shared_metadata, "annotates": row["reference_label"]},
            )
            count += 1

    for row in corpus.HISTORICAL_SOURCES:
        content = " ".join(filter(None, [row.get("description"), row.get("dating_note")]))
        index_chunk(
            db,
            kind="source_profile",
            source_key=row["slug"],
            title=row["title"],
            content=content,
            citation=row.get("canonical_citation"),
            tradition=row.get("tradition"),
            historical_source_id=source_ids.get(row["slug"]),
            metadata={
                "composition_earliest_year": row.get("composition_earliest_year"),
                "composition_latest_year": row.get("composition_latest_year"),
                "reliability": row.get("reliability"),
                "language": row.get("language"),
            },
        )
        count += 1

    for shower in METEOR_SHOWERS:
        index_chunk(
            db,
            kind="astronomical_reference",
            source_key=f"meteor:{shower.key}",
            title=f"{shower.name} meteor shower",
            content=(
                f"{shower.name}: peaks around {shower.peak_day} "
                f"{['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'][shower.peak_month - 1]}, "
                f"radiant in {shower.radiant_constellation}, parent body "
                f"{shower.parent_body or 'unknown'}, zenithal hourly rate about {shower.zhr}. "
                f"{shower.note}"
            ),
            citation="International Meteor Organization, Working List of Visual Meteor Showers",
            metadata={"peak_month": shower.peak_month, "peak_day": shower.peak_day},
        )
        count += 1

    for comet in COMET_APPARITIONS:
        index_chunk(
            db,
            kind="astronomical_reference",
            source_key=f"comet:{comet.designation}",
            title=f"{comet.name} ({comet.to_dict()['year_label']})",
            content=(
                f"{comet.name}, {comet.perihelion_note}. Evidence type: {comet.evidence}. "
                + (" Records: " + "; ".join(comet.records) if comet.records else "")
            ),
            citation=comet.source,
            metadata={"year": comet.year, "evidence": comet.evidence},
        )
        count += 1

    return count


def seed_all(db: Session, *, build_index: bool = True) -> dict:
    """Seed everything. Returns a summary suitable for logging or an admin response."""
    source_ids = _upsert_sources(db)
    passages = _upsert_passages(db, source_ids)
    calendars = _upsert_calendars(db)
    db.flush()
    events = _upsert_recorded_events(db, source_ids)

    chunks = _build_index(db, source_ids) if build_index else 0

    _upsert_datasets(
        db,
        {
            "starcode-seed-sources": len(source_ids) + passages,
            "starcode-recorded-events": events,
            "starcode-calendars": calendars,
            "imo-meteor-showers": len(METEOR_SHOWERS),
            "halley-apparitions": len([c for c in COMET_APPARITIONS if "Halley" in c.name]),
        },
    )

    db.commit()

    summary = {
        "sources": len(source_ids),
        "passages": passages,
        "calendar_systems": calendars,
        "astronomical_events": events,
        "indexed_chunks": chunks,
    }
    logger.info("knowledge.seeded", **summary)
    return summary


__all__ = ["seed_all"]
