#!/usr/bin/env python3
"""Load an additional source corpus from a JSON file.

The curated corpus in `app/knowledge/corpus.py` is a demonstration set. This is how a
deployment grows past it without editing Python: write a JSON file in the same shape,
run this, and the sources, passages and recorded events become retrievable alongside the
built-in ones.

    python3 scripts/import_dataset.py corpus.json
    python3 scripts/import_dataset.py corpus.json --dry-run     # validate, change nothing

**Every entry must carry its provenance, and the importer refuses the file otherwise.**
That is the whole point rather than an inconvenience: retrieved passages are cited in
reports, and a claim type that requires a citation is downgraded to an unsupported
hypothesis when it has none. A source without a `canonical_citation`, a translation
without a `translation_credit`, or a recorded event with neither a source nor a stated
computation would quietly erode the labelling the platform exists to provide.

Validation is complete before anything is written: a file with ten good entries and one
bad one imports nothing, and lists every problem at once.

File shape (`sources` is required; the rest are optional):

    {
      "dataset": {
        "key": "my-corpus",                     required
        "name": "My corpus",                    required
        "license": "CC BY-SA 4.0",              required
        "description": "...",
        "url": "https://example.org/corpus",
        "provider": "Example Institute"
      },
      "sources": [
        {
          "slug": "epic-of-gilgamesh",          required, stable, unique
          "title": "Epic of Gilgamesh",         required
          "canonical_citation": "...",          required
          "license": "Public domain",           required
          "tradition": "mesopotamian",
          "language": "Akkadian",
          "composition_earliest_year": -2100,   negative = BCE, astronomical numbering
          "composition_latest_year": -1200,
          "dating_note": "...",                 strongly encouraged where contested
          "description": "...",
          "reliability": "contested_dating",
          "is_primary_source": true
        }
      ],
      "passages": [
        {
          "source_slug": "epic-of-gilgamesh",   required, must name a source
          "reference_label": "Tablet XI",       required, unique within the source
          "translation": "...",                 required
          "translation_credit": "...",          required
          "themes": ["flood"],
          "astronomical_content": false,
          "prophetic_content": false,
          "notes": "scholarly caveat, indexed separately from the passage itself"
        }
      ],
      "events": [
        {
          "designation": "eclipse-763-bce",     required, unique
          "event_type": "solar_eclipse",        required
          "label": "Bur-Sagale eclipse",        required
          "year": -762,                         astronomical numbering
          "month": 6, "day": 15,
          "calendar_used": "julian_proleptic",
          "is_computed": false,                 false requires source_slug
          "source_slug": "assyrian-eponym-list",
          "description": "...",
          "visibility_regions": ["Assyria"]
        }
      ]
    }

Re-running the same file updates in place rather than duplicating, so it is safe in a
deploy script. Run it from `backend/` with the same environment the API uses.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Python puts the *script's* directory on the path, not the working directory, so `app`
# is not importable without this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402 - after the path bootstrap above

from app.db.models.knowledge import (  # noqa: E402
    AstronomicalEvent,
    Dataset,
    HistoricalSource,
    SourcePassage,
)
from app.db.session import session_scope  # noqa: E402
from app.knowledge.rag import index_chunk  # noqa: E402

SOURCE_REQUIRED = ("slug", "title", "canonical_citation", "license")
PASSAGE_REQUIRED = ("source_slug", "reference_label", "translation", "translation_credit")
EVENT_REQUIRED = ("designation", "event_type", "label")
DATASET_REQUIRED = ("key", "name", "license")

# Mirrors the columns the seed loader sets. Anything else in the file is ignored rather
# than passed to the model, so a typo cannot silently create an attribute.
SOURCE_FIELDS = {
    "title",
    "alternate_titles",
    "tradition",
    "language",
    "script",
    "composition_earliest_year",
    "composition_latest_year",
    "dating_note",
    "region",
    "description",
    "canonical_citation",
    "reliability",
    "is_primary_source",
    "license",
}


def validate(payload: dict[str, Any]) -> list[str]:
    """Every problem in the file, not just the first."""
    problems: list[str] = []

    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        return ["'sources' must be a non-empty list."]

    slugs: set[str] = set()
    for i, row in enumerate(sources):
        where = f"sources[{i}]"
        if not isinstance(row, dict):
            problems.append(f"{where}: not an object.")
            continue
        for field in SOURCE_REQUIRED:
            if not str(row.get(field) or "").strip():
                problems.append(f"{where}: '{field}' is required.")
        slug = str(row.get("slug") or "")
        if slug in slugs:
            problems.append(f"{where}: duplicate slug '{slug}'.")
        slugs.add(slug)

        earliest, latest = row.get("composition_earliest_year"), row.get("composition_latest_year")
        if isinstance(earliest, int) and isinstance(latest, int) and earliest > latest:
            problems.append(
                f"{where}: composition_earliest_year ({earliest}) is after "
                f"composition_latest_year ({latest}). Years are astronomically numbered, "
                "so BCE dates are negative and -600 is earlier than -164."
            )

    seen_passages: set[tuple[str, str]] = set()
    for i, row in enumerate(payload.get("passages") or []):
        where = f"passages[{i}]"
        if not isinstance(row, dict):
            problems.append(f"{where}: not an object.")
            continue
        for field in PASSAGE_REQUIRED:
            if not str(row.get(field) or "").strip():
                problems.append(f"{where}: '{field}' is required.")
        slug = str(row.get("source_slug") or "")
        if slug and slug not in slugs:
            problems.append(f"{where}: source_slug '{slug}' is not defined in this file.")
        key = (slug, str(row.get("reference_label") or ""))
        if key in seen_passages:
            problems.append(f"{where}: duplicate reference_label '{key[1]}' for '{slug}'.")
        seen_passages.add(key)

    designations: set[str] = set()
    for i, row in enumerate(payload.get("events") or []):
        where = f"events[{i}]"
        if not isinstance(row, dict):
            problems.append(f"{where}: not an object.")
            continue
        for field in EVENT_REQUIRED:
            if not str(row.get(field) or "").strip():
                problems.append(f"{where}: '{field}' is required.")
        designation = str(row.get("designation") or "")
        if designation in designations:
            problems.append(f"{where}: duplicate designation '{designation}'.")
        designations.add(designation)

        slug = row.get("source_slug")
        if slug and slug not in slugs:
            problems.append(f"{where}: source_slug '{slug}' is not defined in this file.")
        if not row.get("is_computed") and not slug:
            problems.append(
                f"{where}: a recorded (not computed) event needs 'source_slug' naming the "
                "text that records it. Set 'is_computed': true if it comes from calculation "
                "instead — the distinction is reported to users."
            )

    dataset = payload.get("dataset")
    if dataset is not None:
        if not isinstance(dataset, dict):
            problems.append("'dataset': not an object.")
        else:
            for field in DATASET_REQUIRED:
                if not str(dataset.get(field) or "").strip():
                    problems.append(f"dataset: '{field}' is required when 'dataset' is present.")

    return problems


def import_payload(db, payload: dict[str, Any]) -> dict[str, int]:
    source_ids: dict[str, str] = {}

    for row in payload["sources"]:
        slug = row["slug"]
        existing = db.execute(
            select(HistoricalSource).where(HistoricalSource.slug == slug)
        ).scalar_one_or_none()
        target = existing or HistoricalSource(slug=slug)
        for field, value in row.items():
            if field in SOURCE_FIELDS:
                setattr(target, field, value)
        if existing is None:
            db.add(target)
        db.flush()
        source_ids[slug] = target.id

    passages = 0
    for row in payload.get("passages") or []:
        source_id = source_ids[row["source_slug"]]
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
        target.translation_credit = row["translation_credit"]
        target.themes = row.get("themes", [])
        target.astronomical_content = bool(row.get("astronomical_content", False))
        target.prophetic_content = bool(row.get("prophetic_content", False))
        target.notes = row.get("notes")
        if existing is None:
            db.add(target)
        passages += 1

    events = 0
    for row in payload.get("events") or []:
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
        target.is_computed = bool(row.get("is_computed", False))
        target.description = row.get("description")
        target.visibility_regions = row.get("visibility_regions", [])
        target.constellation = row.get("constellation")
        # Kept parallel with the seed loader: a computed event names its engine, a
        # recorded one says it is a record. Reports show which.
        target.computation_engine = (
            row.get("computation_engine") if row.get("is_computed") else "historical record"
        )
        slug = row.get("source_slug")
        target.historical_source_id = source_ids.get(slug) if slug else None
        if existing is None:
            db.add(target)
        events += 1

    chunks = index_payload(db, payload, source_ids)

    dataset = payload.get("dataset")
    if dataset:
        existing = db.execute(
            select(Dataset).where(Dataset.key == dataset["key"])
        ).scalar_one_or_none()
        target = existing or Dataset(key=dataset["key"])
        for field, value in dataset.items():
            if field != "key":
                setattr(target, field, value)
        target.record_count = len(source_ids) + passages + events
        if existing is None:
            db.add(target)

    return {
        "sources": len(source_ids),
        "passages": passages,
        "events": events,
        "indexed_chunks": chunks,
    }


def index_payload(db, payload: dict[str, Any], source_ids: dict[str, str]) -> int:
    """Make the new material retrievable, on the same terms as the seed corpus."""
    by_slug = {row["slug"]: row for row in payload["sources"]}
    count = 0

    for row in payload.get("passages") or []:
        source = by_slug[row["source_slug"]]
        citation = (
            f"{source['title']}, {row['reference_label']}. {row['translation_credit']}".strip()
        )
        shared = {
            "reference_label": row["reference_label"],
            "themes": row.get("themes", []),
            "astronomical_content": row.get("astronomical_content", False),
            "prophetic_content": row.get("prophetic_content", False),
            "translation_credit": row["translation_credit"],
            "dating_note": source.get("dating_note"),
        }

        # A passage and the scholarly caveat about it are indexed separately, exactly as
        # in the seed loader: mixing them dilutes both vectors.
        index_chunk(
            db,
            kind="source_passage",
            source_key=row["source_slug"],
            title=f"{source['title']} — {row['reference_label']}",
            content=row["translation"],
            citation=citation,
            tradition=source.get("tradition"),
            historical_source_id=source_ids[row["source_slug"]],
            metadata={**shared, "scholarly_note": row.get("notes")},
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
                historical_source_id=source_ids[row["source_slug"]],
                metadata={**shared, "annotates": row["reference_label"]},
            )
            count += 1

    for row in payload["sources"]:
        content = " ".join(filter(None, [row.get("description"), row.get("dating_note")]))
        if not content:
            continue
        index_chunk(
            db,
            kind="source_profile",
            source_key=row["slug"],
            title=row["title"],
            content=content,
            citation=row["canonical_citation"],
            tradition=row.get("tradition"),
            historical_source_id=source_ids[row["slug"]],
            metadata={
                "composition_earliest_year": row.get("composition_earliest_year"),
                "composition_latest_year": row.get("composition_latest_year"),
                "reliability": row.get("reliability"),
                "language": row.get("language"),
            },
        )
        count += 1

    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a source corpus from JSON.")
    parser.add_argument("file", type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report what would be imported, without writing.",
    )
    args = parser.parse_args()

    try:
        payload = json.loads(args.file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"No such file: {args.file}") from None
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{args.file} is not valid JSON: {exc}") from None

    if not isinstance(payload, dict):
        raise SystemExit("The top level of the file must be an object.")

    problems = validate(payload)
    if problems:
        print(f"{args.file}: {len(problems)} problem(s), nothing imported:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    counts = {
        "sources": len(payload["sources"]),
        "passages": len(payload.get("passages") or []),
        "events": len(payload.get("events") or []),
    }

    if args.dry_run:
        print(
            f"{args.file}: valid. Would import " + ", ".join(f"{v} {k}" for k, v in counts.items())
        )
        return 0

    with session_scope() as db:
        result = import_payload(db, payload)

    print(", ".join(f"{v} {k}" for k, v in result.items()) + " imported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
