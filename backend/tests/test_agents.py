"""Agent, orchestrator and knowledge-layer tests."""

from __future__ import annotations

import hashlib

import pytest

from app.agents import lexicon, offline_engine
from app.agents.orchestrator import pipeline_description, run_analysis
from app.agents.provider import OfflineProvider, extract_json, get_provider
from app.db.models.analysis import Analysis, AnalysisStatus, ClaimType
from app.db.models.content import Document, SourceKind
from app.knowledge.embeddings import cosine_similarity, embed, jaccard_overlap
from app.knowledge.rag import retrieve


@pytest.fixture
def analysis_factory(db):
    created: list[str] = []

    def make(text: str, title: str = "Test") -> Analysis:
        document = Document(
            raw_text=text,
            normalized_text=text,
            source_kind=SourceKind.PASTED_TEXT,
            char_count=len(text),
            word_count=len(text.split()),
            content_hash=hashlib.sha256(text.encode()).hexdigest(),
        )
        db.add(document)
        db.flush()
        analysis = Analysis(document_id=document.id, title=title)
        db.add(analysis)
        db.flush()
        created.append(analysis.id)
        return analysis

    yield make

    for analysis_id in created:
        obj = db.get(Analysis, analysis_id)
        if obj:
            db.delete(obj)
    db.commit()


class TestLexicon:
    def test_finds_celestial_terms(self):
        matches = lexicon.find_entities(
            "The sun became black and the moon as blood, and Jupiter stood in Aries."
        )
        found = {m.entry.canonical for m in matches}
        assert {"Sun", "Moon", "Jupiter", "Aries"} <= found

    def test_detects_eclipse_idiom_not_just_the_word(self):
        matches = lexicon.find_entities("and the moon became as blood")
        assert any(m.entry.canonical == "Lunar eclipse" for m in matches)

    def test_sacred_numbers_spelled_and_numeric(self):
        numbers = lexicon.find_sacred_numbers(
            "his number is Six hundred threescore and six, and 144000 were sealed"
        )
        values = {n["number"] for n in numbers}
        assert values == {"666", "144000"}

    def test_positional_digits_are_not_treated_as_numerology(self):
        """A Long Count or verse reference contains digits that mean position, not value."""
        numbers = lexicon.find_sacred_numbers("Long count 9.12.11.5.18 and Daniel 8:14")
        assert numbers == []

    def test_enclosed_phrases_do_not_double_count(self):
        numbers = lexicon.find_sacred_numbers("an hundred forty and four thousand")
        assert [n["number"] for n in numbers] == ["144000"]

    def test_prophecy_markers(self):
        markers = lexicon.find_prophecy_markers(
            "Thus saith the LORD: in the last days it shall come to pass"
        )
        labels = {m["marker"] for m in markers}
        assert "Prophetic messenger formula" in labels
        assert "Eschatological time marker" in labels

    def test_regnal_year_captures_a_bounded_ruler_name(self):
        dates = lexicon.find_date_expressions(
            "In the third year of the reign of Belshazzar king of Babylon a vision appeared."
        )
        regnal = next(d for d in dates if d["kind"] == "regnal_year_spelled")
        assert regnal["groups"] == ["third", "Belshazzar"]

    def test_date_expressions_do_not_overlap(self):
        dates = lexicon.find_date_expressions("In 587 BC and 9.12.11.5.18 and 40 days")
        spans = sorted((d["start"], d["end"]) for d in dates)
        for (_, end), (start, _) in zip(spans, spans[1:]):
            assert end <= start


class TestOfflineEngine:
    def test_detects_english(self):
        result = offline_engine.detect_language("The sun shall be turned into darkness")
        assert result["language_code"] == "en"
        assert result["script"] == "Latin"

    def test_detects_archaic_register(self):
        result = offline_engine.detect_language(
            "Thou shalt behold, and verily the LORD saith unto thee, hath spoken"
        )
        assert result["register"] and "Early Modern" in result["register"]

    @pytest.mark.parametrize(
        "text,code",
        [
            ("ἐν ἀρχῇ ἦν ὁ λόγος καὶ ὁ λόγος ἦν πρὸς τὸν θεόν", "el"),
            ("בְּרֵאשִׁית בָּרָא אֱלֹהִים אֵת הַשָּׁמַיִם", "he"),
            ("天命之謂性率性之謂道修道之謂教", "zh"),
        ],
    )
    def test_detects_non_latin_scripts(self, text, code):
        result = offline_engine.detect_language(text)
        assert result["language_code"] == code
        assert result["needs_translation"] is True

    def test_resolvable_and_unresolvable_dates_are_distinguished(self):
        result = offline_engine.extract_dates(
            "In 587 BC, in the third year of the reign of Belshazzar, after 40 days."
        )
        by_kind = {d["kind"]: d for d in result["date_expressions"]}
        assert by_kind["bce_year"]["resolvable"] is True
        assert by_kind["bce_year"]["astronomical_year"] == -586
        assert by_kind["regnal_year_spelled"]["resolvable"] is False
        assert "accession" in by_kind["regnal_year_spelled"]["blocker"]
        assert by_kind["duration_days"]["resolvable"] is False

    def test_interpretive_tasks_are_refused_rather_than_faked(self):
        """A rule engine inventing 'traditional interpretations' is the exact failure the
        platform exists to prevent."""
        for task in (
            "traditional_interpretation", "scholarly_views", "alternative_interpretations",
            "historical_context", "symbolism", "translate",
        ):
            result = offline_engine.handle(task, "<text>anything</text>")
            assert result["offline_unavailable"] is True
            assert result["reason"]

    def test_mechanical_tasks_are_actually_performed(self):
        for task in ("detect_language", "extract_entities", "extract_dates", "detect_astronomical"):
            result = offline_engine.handle(task, "<text>the sun and the moon in 587 BC</text>")
            assert "offline_unavailable" not in result


class TestProvider:
    def test_offline_provider_is_selected_without_a_key(self):
        assert get_provider().name == "offline"

    def test_offline_provider_returns_parseable_json(self):
        provider = OfflineProvider()
        response = provider.complete("sys", "<task>detect_language</task><text>hello world</text>")
        assert response.json()["language_code"]

    @pytest.mark.parametrize(
        "raw",
        [
            '{"a": 1}',
            '```json\n{"a": 1}\n```',
            'Here is the result:\n{"a": 1}\nHope that helps.',
            '```\n{"a": 1}```',
        ],
    )
    def test_json_extraction_tolerates_model_formatting(self, raw):
        assert extract_json(raw) == {"a": 1}

    def test_json_extraction_handles_braces_inside_strings(self):
        assert extract_json('{"a": "a } brace"}') == {"a": "a } brace"}

    def test_json_extraction_reports_failure(self):
        with pytest.raises(ValueError, match="no parseable JSON"):
            extract_json("no json at all here")


class TestEmbeddings:
    def test_identical_text_is_maximally_similar(self):
        vector = embed("the sun turned to darkness")
        assert cosine_similarity(vector, vector) == pytest.approx(1.0, abs=1e-6)

    def test_related_text_beats_unrelated(self):
        query = embed("the moon turned to blood at the eclipse")
        related = embed("the moon became as blood, a lunar eclipse")
        unrelated = embed("quarterly revenue guidance for the semiconductor sector")
        assert cosine_similarity(query, related) > cosine_similarity(query, unrelated)

    def test_empty_text_yields_a_zero_vector(self):
        assert not any(embed(""))

    def test_deterministic_across_calls(self):
        assert embed("Nebuchadnezzar") == embed("Nebuchadnezzar")

    def test_lexical_overlap_cross_check(self):
        assert jaccard_overlap("the sun and moon", "the sun and moon") == 1.0
        assert jaccard_overlap("sun moon", "quarterly earnings") == 0.0


class TestRetrieval:
    def test_quoted_passage_finds_its_source(self, db):
        hits = retrieve(
            db,
            "The sun shall be turned into darkness, and the moon into blood, before the "
            "great and terrible day of the LORD come.",
            limit=3,
        )
        assert hits
        assert "Joel" in hits[0].title
        assert hits[0].match_strength == "strong"

    def test_conceptual_question_reaches_the_scholarly_note(self, db):
        hits = retrieve(db, "is the blood moon prophecy really about a lunar eclipse", limit=5)
        assert any(h.kind == "scholarly_note" for h in hits)

    def test_irrelevant_query_returns_nothing(self, db):
        assert retrieve(db, "kubernetes ingress controller latency", limit=5) == []

    def test_hits_report_their_strength(self, db):
        for hit in retrieve(db, "seventy weeks are determined upon thy people", limit=3):
            assert hit.match_strength in ("strong", "moderate", "weak")
            assert 0.0 <= hit.score <= 1.0


class TestOrchestrator:
    def test_pipeline_has_eight_agents_in_dependency_order(self):
        agents = pipeline_description()
        assert [a["name"] for a in agents] == [
            "language", "source_identification", "entities", "calendar",
            "astronomy", "historical_context", "interpretation", "evidence",
        ]
        assert [a["progress_after"] for a in agents] == sorted(
            a["progress_after"] for a in agents
        )

    def test_calendar_and_astronomy_are_deterministic(self):
        """These must not consult a model: their output is arithmetic."""
        deterministic = {a["name"] for a in pipeline_description() if a["deterministic"]}
        assert deterministic == {"calendar", "astronomy"}

    def test_full_run_offline(self, db, analysis_factory, sample_text):
        analysis = analysis_factory(sample_text)
        run_analysis(db, analysis)

        assert analysis.status in (AnalysisStatus.COMPLETED, AnalysisStatus.PARTIAL)
        assert analysis.progress == 1.0
        assert analysis.claims
        assert analysis.reports
        assert len(analysis.agent_runs) == 8

    def test_source_text_is_always_recorded_verbatim(self, db, analysis_factory, sample_text):
        analysis = analysis_factory(sample_text)
        run_analysis(db, analysis)
        quotes = [c for c in analysis.claims if c.claim_type == ClaimType.SOURCE_TEXT]
        assert quotes
        assert any(sample_text[:60] in (c.quoted_text or "") for c in quotes)

    def test_every_claim_survives_the_contract(self, db, analysis_factory, sample_text):
        analysis = analysis_factory(sample_text)
        run_analysis(db, analysis)

        cited = {c.claim_id for c in analysis.references if c.claim_id}
        for claim in analysis.claims:
            if claim.claim_type in (
                ClaimType.VERIFIED_HISTORY, ClaimType.SCHOLARLY_INTERPRETATION
            ):
                assert claim.id in cited, f"uncited: {claim.statement[:60]}"
            if claim.claim_type == ClaimType.ASTRONOMICAL_CALCULATION:
                assert claim.engine
            if claim.claim_type == ClaimType.AI_HYPOTHESIS:
                assert claim.confidence <= 0.55

    def test_offline_run_marks_interpretive_sections_unavailable(
        self, db, analysis_factory, sample_text
    ):
        analysis = analysis_factory(sample_text)
        run_analysis(db, analysis)
        skipped = {r.agent_name for r in analysis.agent_runs if r.status == "skipped"}
        assert {"historical_context", "interpretation"} <= skipped

        report = analysis.reports[0]
        interpretive = next(
            s for s in report.sections if s["key"] == "traditional_interpretations"
        )
        assert interpretive["is_empty"]
        assert "language model" in interpretive["empty_reason"]

    def test_report_covers_every_specified_section(self, db, analysis_factory, sample_text):
        analysis = analysis_factory(sample_text)
        run_analysis(db, analysis)
        keys = {s["key"] for s in analysis.reports[0].sections}
        assert {
            "executive_summary", "original_text", "detected_language", "translation",
            "source_identification", "historical_context", "astronomical_references",
            "calendar_conversion", "timeline", "key_entities", "symbolism",
            "traditional_interpretations", "scholarly_views", "alternative_interpretations",
            "evidence", "confidence_ratings", "references", "further_reading",
        } <= keys

    def test_astronomy_declines_to_correlate_without_a_date(self, db, analysis_factory):
        """Matching eclipse imagery to an arbitrary year manufactures a coincidence."""
        analysis = analysis_factory(
            "And the sun became black as sackcloth and the moon as blood."
        )
        run_analysis(db, analysis)
        statements = " ".join(c.statement for c in analysis.claims)
        assert "supplies no date" in statements

    def test_calculations_appear_when_a_date_is_present(self, db, analysis_factory):
        analysis = analysis_factory("In 587 BC Jerusalem fell to Babylon.")
        run_analysis(db, analysis)
        calculations = [
            c for c in analysis.claims if c.claim_type == ClaimType.ASTRONOMICAL_CALCULATION
        ]
        assert calculations
        assert all(c.engine and c.algorithm_reference for c in calculations)

    def test_trace_is_complete(self, db, analysis_factory, sample_text):
        analysis = analysis_factory(sample_text)
        run_analysis(db, analysis)
        for run in analysis.agent_runs:
            assert run.reasoning_summary
            assert run.status in ("succeeded", "failed", "skipped")
            assert run.duration_ms is not None

    def test_empty_analysis_still_produces_a_report(self, db, analysis_factory):
        """A text with nothing recognisable must not fail — it must say so."""
        analysis = analysis_factory("aaa bbb ccc ddd")
        run_analysis(db, analysis)
        assert analysis.reports
        assert analysis.reports[0].executive_summary
