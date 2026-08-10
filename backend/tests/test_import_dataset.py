"""Growing the corpus without weakening the labelling.

`scripts/import_dataset.py` is the documented route past the demonstration corpus. Its
job is not merely to insert rows: it is the gate that keeps unprovenanced material out of
the retrieval index, because a retrieved passage is cited in a report and a claim without
a citation is downgraded to an unsupported hypothesis.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.knowledge import AstronomicalEvent, HistoricalSource, SourcePassage
from app.knowledge.rag import retrieve

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "import_dataset.py"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("import_dataset", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def slug() -> str:
    return f"test-corpus-{os.urandom(4).hex()}"


def payload_for(slug: str) -> dict:
    return {
        "dataset": {
            "key": f"{slug}-dataset",
            "name": "Test corpus",
            "license": "Public domain",
        },
        "sources": [
            {
                "slug": slug,
                "title": "Astronomical Diaries of Babylon",
                "canonical_citation": "Sachs & Hunger, Astronomical Diaries and Related Texts.",
                "license": "Public domain (paraphrase)",
                "tradition": "mesopotamian",
                "language": "Akkadian",
                "composition_earliest_year": -652,
                "composition_latest_year": -60,
                "description": "Nightly observational records kept by Babylonian scribes.",
                "dating_note": "Individual tablets are dated by regnal year.",
            }
        ],
        "passages": [
            {
                "source_slug": slug,
                "reference_label": "Diary -567 obv. 12",
                "translation": (
                    "Night of the fourteenth, the moon was surrounded by a halo; "
                    "Jupiter stood in the halo."
                ),
                "translation_credit": "Paraphrase after Sachs & Hunger, public domain summary.",
                "themes": ["lunar halo", "Jupiter"],
                "astronomical_content": True,
                "notes": "A halo is atmospheric, not an eclipse; the diaries distinguish them.",
            }
        ],
        "events": [
            {
                "designation": f"{slug}-observation",
                "event_type": "lunar_halo",
                "label": "Lunar halo with Jupiter",
                "year": -566,
                "is_computed": False,
                "source_slug": slug,
            }
        ],
    }


def run(script, tmp_path: Path, payload: dict, *args: str) -> int:
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    argv = ["import_dataset.py", str(path), *args]
    original, sys.argv = sys.argv, argv
    try:
        return script.main()
    finally:
        sys.argv = original


class TestValidation:
    """The file is rejected as a whole, before anything is written."""

    def test_a_source_without_a_citation_is_refused(self, script, slug):
        payload = payload_for(slug)
        del payload["sources"][0]["canonical_citation"]
        problems = script.validate(payload)
        assert any("canonical_citation" in p for p in problems)

    def test_a_translation_without_credit_is_refused(self, script, slug):
        payload = payload_for(slug)
        del payload["passages"][0]["translation_credit"]
        problems = script.validate(payload)
        assert any("translation_credit" in p for p in problems)

    def test_a_recorded_event_must_name_the_text_that_records_it(self, script, slug):
        payload = payload_for(slug)
        del payload["events"][0]["source_slug"]
        problems = script.validate(payload)
        assert any("source_slug" in p and "computed" in p for p in problems)

    def test_a_computed_event_needs_no_source(self, script, slug):
        payload = payload_for(slug)
        payload["events"][0]["is_computed"] = True
        del payload["events"][0]["source_slug"]
        assert script.validate(payload) == []

    def test_a_passage_pointing_at_an_undefined_source_is_refused(self, script, slug):
        payload = payload_for(slug)
        payload["passages"][0]["source_slug"] = "not-in-this-file"
        problems = script.validate(payload)
        assert any("not defined in this file" in p for p in problems)

    def test_reversed_composition_years_are_caught_with_the_bce_explanation(self, script, slug):
        payload = payload_for(slug)
        payload["sources"][0]["composition_earliest_year"] = -60
        payload["sources"][0]["composition_latest_year"] = -652
        problems = script.validate(payload)
        assert any("astronomically numbered" in p for p in problems)

    def test_every_problem_is_reported_at_once(self, script, slug):
        payload = payload_for(slug)
        del payload["sources"][0]["canonical_citation"]
        del payload["sources"][0]["license"]
        del payload["passages"][0]["translation_credit"]
        assert len(script.validate(payload)) >= 3

    def test_one_bad_entry_stops_the_whole_file(self, script, tmp_path, db: Session, slug):
        payload = payload_for(slug)
        del payload["passages"][0]["translation_credit"]

        assert run(script, tmp_path, payload) == 1

        db.expire_all()
        assert (
            db.execute(
                select(HistoricalSource).where(HistoricalSource.slug == slug)
            ).scalar_one_or_none()
            is None
        )

    def test_dry_run_validates_without_writing(self, script, tmp_path, db: Session, slug):
        assert run(script, tmp_path, payload_for(slug), "--dry-run") == 0

        db.expire_all()
        assert (
            db.execute(
                select(HistoricalSource).where(HistoricalSource.slug == slug)
            ).scalar_one_or_none()
            is None
        )


class TestImport:
    def test_a_valid_file_lands_and_becomes_retrievable(self, script, tmp_path, db: Session, slug):
        assert run(script, tmp_path, payload_for(slug)) == 0
        db.expire_all()

        source = db.execute(
            select(HistoricalSource).where(HistoricalSource.slug == slug)
        ).scalar_one()
        assert source.title == "Astronomical Diaries of Babylon"

        passage = db.execute(
            select(SourcePassage).where(SourcePassage.source_id == source.id)
        ).scalar_one()
        assert passage.astronomical_content

        event = db.execute(
            select(AstronomicalEvent).where(AstronomicalEvent.designation == f"{slug}-observation")
        ).scalar_one()
        # A record is labelled a record, not a calculation.
        assert event.is_computed is False
        assert event.computation_engine == "historical record"
        assert event.historical_source_id == source.id

        hits = retrieve(db, "the moon was surrounded by a halo", limit=5)
        assert any(h.source_key == slug for h in hits)

    def test_the_scholarly_note_is_indexed_apart_from_the_passage(
        self, script, tmp_path, db: Session, slug
    ):
        assert run(script, tmp_path, payload_for(slug)) == 0
        db.expire_all()

        hits = retrieve(db, "is a halo an eclipse", limit=8)
        kinds = {h.kind for h in hits if h.source_key == slug}
        assert "scholarly_note" in kinds

    def test_reimporting_updates_rather_than_duplicates(self, script, tmp_path, db: Session, slug):
        assert run(script, tmp_path, payload_for(slug)) == 0

        revised = payload_for(slug)
        revised["sources"][0]["title"] = "Babylonian Astronomical Diaries"
        assert run(script, tmp_path, revised) == 0

        db.expire_all()
        rows = (
            db.execute(select(HistoricalSource).where(HistoricalSource.slug == slug))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].title == "Babylonian Astronomical Diaries"

        source_id = rows[0].id
        passages = (
            db.execute(select(SourcePassage).where(SourcePassage.source_id == source_id))
            .scalars()
            .all()
        )
        assert len(passages) == 1

    def test_unknown_fields_are_ignored_rather_than_set(self, script, tmp_path, db: Session, slug):
        payload = payload_for(slug)
        payload["sources"][0]["totally_made_up_column"] = "x"

        assert run(script, tmp_path, payload) == 0

        db.expire_all()
        source = db.execute(
            select(HistoricalSource).where(HistoricalSource.slug == slug)
        ).scalar_one()
        assert not hasattr(source, "totally_made_up_column")
