"""Tests for the epistemic contract.

These are the most important tests in the suite. They verify that the product's central
promise — never present speculation as established fact — is mechanically enforced rather
than a matter of wording. Every one of them should be read as a specification.
"""

from __future__ import annotations

import pytest

from app.agents.contracts import (
    CLAIM_TYPE_PRESENTATION,
    EVIDENCE_TYPES,
    REQUIRES_CITATION,
    CitationDraft,
    ClaimDraft,
    ClaimType,
    ContractViolation,
    Section,
    coerce_claim,
    confidence_band,
    summarize_confidence,
    validate_claim,
)
from app.core.config import settings


def make_claim(**overrides) -> ClaimDraft:
    defaults = {
        "section": Section.HISTORICAL_CONTEXT,
        "claim_type": ClaimType.AI_HYPOTHESIS,
        "statement": "A statement.",
        "produced_by": "test",
        "confidence": 0.4,
    }
    return ClaimDraft(**{**defaults, **overrides})


class TestCitationRequirement:
    def test_verified_history_requires_a_citation(self):
        claim = make_claim(claim_type=ClaimType.VERIFIED_HISTORY, confidence=0.9)
        with pytest.raises(ContractViolation, match="requires at least one citation"):
            validate_claim(claim)

    def test_scholarly_interpretation_requires_a_citation(self):
        claim = make_claim(claim_type=ClaimType.SCHOLARLY_INTERPRETATION)
        with pytest.raises(ContractViolation, match="requires at least one citation"):
            validate_claim(claim)

    def test_cited_history_is_accepted(self):
        claim = make_claim(
            claim_type=ClaimType.VERIFIED_HISTORY,
            confidence=0.9,
            citations=[CitationDraft(citation_text="Herodotus, Histories 1.74")],
        )
        assert validate_claim(claim) == []

    def test_uncited_history_is_downgraded_not_dropped(self):
        """Dropping loses information; promoting would be the failure this exists to
        prevent. Downgrading, visibly, is the honest third option."""
        claim = coerce_claim(make_claim(claim_type=ClaimType.VERIFIED_HISTORY, confidence=0.95))
        assert claim.claim_type == ClaimType.AI_HYPOTHESIS
        assert claim.confidence <= settings.AI_HYPOTHESIS_CONFIDENCE_CAP
        assert "contract_adjustments" in claim.payload
        assert any("no citation" in note for note in claim.payload["contract_adjustments"])
        assert claim.statement  # the content survives


class TestConfidenceCap:
    def test_ai_hypothesis_confidence_is_capped(self):
        claim = make_claim(claim_type=ClaimType.AI_HYPOTHESIS, confidence=0.99)
        with pytest.raises(ContractViolation, match="exceeds the cap"):
            validate_claim(claim)

    def test_coercion_clamps_rather_than_rejects(self):
        claim = coerce_claim(make_claim(claim_type=ClaimType.AI_HYPOTHESIS, confidence=0.99))
        assert claim.confidence == settings.AI_HYPOTHESIS_CONFIDENCE_CAP

    def test_evidence_types_may_be_fully_confident(self):
        claim = make_claim(claim_type=ClaimType.SOURCE_TEXT, confidence=1.0, quoted_text="quoted")
        assert validate_claim(claim) == []

    def test_confidence_outside_unit_interval_rejected(self):
        with pytest.raises(ContractViolation, match="outside"):
            validate_claim(make_claim(claim_type=ClaimType.UNCERTAIN, confidence=1.5))


class TestCalculationProvenance:
    def test_calculation_must_name_its_engine(self):
        claim = make_claim(claim_type=ClaimType.ASTRONOMICAL_CALCULATION, confidence=0.9)
        with pytest.raises(ContractViolation, match="must name the engine"):
            validate_claim(claim)

    def test_calculation_with_engine_is_accepted(self):
        claim = make_claim(
            claim_type=ClaimType.ASTRONOMICAL_CALCULATION,
            confidence=0.9,
            engine="starcode-astronomy/1.0",
            algorithm_reference="Meeus ch. 54",
        )
        assert validate_claim(claim) == []


class TestSourceText:
    def test_source_text_must_carry_the_quotation(self):
        claim = make_claim(claim_type=ClaimType.SOURCE_TEXT, confidence=1.0)
        with pytest.raises(ContractViolation, match="must carry the quoted text"):
            validate_claim(claim)

    def test_unquoted_source_text_becomes_textual_analysis(self):
        claim = coerce_claim(make_claim(claim_type=ClaimType.SOURCE_TEXT, confidence=1.0))
        assert claim.claim_type == ClaimType.TEXTUAL_ANALYSIS


class TestPredictionLanguage:
    @pytest.mark.parametrize(
        "statement",
        [
            "The world will end in 2027.",
            "This will certainly happen within a decade.",
            "The event is going to happen soon.",
        ],
    )
    def test_hypotheses_may_not_assert_the_future(self, statement):
        claim = make_claim(claim_type=ClaimType.AI_HYPOTHESIS, statement=statement)
        with pytest.raises(ContractViolation, match="future event as settled"):
            validate_claim(claim)

    def test_hedged_phrasing_is_permitted(self):
        claim = make_claim(
            claim_type=ClaimType.AI_HYPOTHESIS,
            statement="Some readers take this as pointing to a future event; the text does "
            "not specify one.",
        )
        assert validate_claim(claim) == []


class TestVocabulary:
    def test_every_claim_type_has_presentation_metadata(self):
        for claim_type in ClaimType:
            presentation = CLAIM_TYPE_PRESENTATION[claim_type]
            assert presentation["label"]
            assert presentation["description"]
            assert presentation["tone"]

    def test_evidence_types_are_the_verifiable_ones(self):
        assert EVIDENCE_TYPES == {
            ClaimType.SOURCE_TEXT,
            ClaimType.VERIFIED_HISTORY,
            ClaimType.ASTRONOMICAL_CALCULATION,
        }
        assert ClaimType.AI_HYPOTHESIS not in EVIDENCE_TYPES
        assert ClaimType.TRADITIONAL_INTERPRETATION not in EVIDENCE_TYPES

    def test_interpretation_types_require_citations(self):
        assert ClaimType.SCHOLARLY_INTERPRETATION in REQUIRES_CITATION
        # A tradition's own reading is reportable without an academic citation; requiring
        # one would systematically exclude living oral traditions.
        assert ClaimType.TRADITIONAL_INTERPRETATION not in REQUIRES_CITATION


class TestConfidenceSummary:
    def test_hypotheses_are_discounted_against_evidence(self):
        """A pile of low-confidence conjecture must not drag down a solid finding the way
        a plain average would. Weighting is what stops "we also thought of five other
        things" from making a calculation look uncertain."""
        claims = [make_claim(claim_type=ClaimType.SOURCE_TEXT, confidence=1.0, quoted_text="x")] + [
            make_claim(claim_type=ClaimType.AI_HYPOTHESIS, confidence=0.1) for _ in range(5)
        ]

        weighted = summarize_confidence(claims)["overall"]
        naive_mean = sum(c.confidence for c in claims) / len(claims)

        assert weighted > naive_mean * 2, (
            f"weighted {weighted} should heavily discount hypotheses relative to the "
            f"naive mean {naive_mean}"
        )

    def test_hypotheses_cannot_inflate_a_weak_analysis(self):
        """The discount cuts both ways: many *confident* hypotheses must not push the
        headline figure up either."""
        hypotheses_only = [
            make_claim(claim_type=ClaimType.AI_HYPOTHESIS, confidence=0.55) for _ in range(20)
        ]
        with_one_calculation = hypotheses_only + [
            make_claim(
                claim_type=ClaimType.ASTRONOMICAL_CALCULATION,
                confidence=0.95,
                engine="starcode-astronomy/1.0",
            )
        ]
        assert (
            summarize_confidence(with_one_calculation)["overall"]
            > summarize_confidence(hypotheses_only)["overall"]
        )

    def test_analysis_with_no_evidence_says_so(self):
        claims = [make_claim(claim_type=ClaimType.AI_HYPOTHESIS) for _ in range(4)]
        summary = summarize_confidence(claims)
        assert summary["evidence_claim_count"] == 0
        assert "no verifiable evidence" in summary["rationale"]

    def test_hypothesis_heavy_analysis_is_flagged(self):
        claims = [make_claim(claim_type=ClaimType.SOURCE_TEXT, confidence=1.0, quoted_text="x")] + [
            make_claim(claim_type=ClaimType.AI_HYPOTHESIS) for _ in range(5)
        ]
        assert "outweighs" in summarize_confidence(claims)["rationale"]

    def test_empty_claim_set(self):
        summary = summarize_confidence([])
        assert summary["overall"] is None
        assert summary["band"] == "not assessed"

    @pytest.mark.parametrize(
        "value,band",
        [(0.95, "very high"), (0.75, "high"), (0.55, "moderate"), (0.35, "low"), (0.1, "very low")],
    )
    def test_confidence_bands(self, value, band):
        assert confidence_band(value) == band


class TestSerialization:
    def test_claim_dict_carries_its_presentation_and_evidence_flag(self):
        claim = make_claim(
            claim_type=ClaimType.ASTRONOMICAL_CALCULATION,
            engine="starcode-astronomy/1.0",
            confidence=0.9,
        )
        payload = claim.to_dict()
        assert payload["claim_type"] == "astronomical_calculation"
        assert payload["presentation"]["label"] == "Astronomical calculation"
        assert payload["is_evidence"] is True

    def test_unverified_citations_are_marked(self):
        """A model-supplied citation must never look like a corpus-verified one."""
        claim = make_claim(
            citations=[CitationDraft(citation_text="Some Book (2019)", verified=False)]
        )
        assert claim.to_dict()["references"][0]["verified"] is False

    def test_serialised_claim_matches_the_api_schema_shape(self):
        """A claim inside a stored report and one fetched from the API must have the
        same shape.

        They diverged once — the report used "citations" where the API used
        "references" — which crashed the web report view and silently dropped every
        citation from the PDF, DOCX and Markdown exports. Nothing caught it because each
        side was individually correct.
        """
        from app.schemas.analysis import ClaimOut

        serialised = make_claim(
            citations=[CitationDraft(citation_text="Herodotus, Histories 1.74")]
        ).to_dict()

        api_fields = set(ClaimOut.model_fields)
        # Fields the API adds from the database row and a draft cannot have yet.
        draft_cannot_have = {"id", "text_span_start", "text_span_end", "section"}

        missing = api_fields - draft_cannot_have - set(serialised)
        assert not missing, f"serialised claim is missing API fields: {sorted(missing)}"
        assert isinstance(serialised["references"], list)
        assert serialised["references"][0]["citation_text"]


class TestDatingCandidates:
    """The claim type for a date proposed because the sky on it matches a text.

    Its rules exist because it is the one type in the vocabulary whose evidence is exact
    and whose conclusion is not. The ephemeris behind a candidate is arithmetic; that
    *this* text describes it is a proposal, and every rule here keeps those two apart.
    """

    EVIDENCE = {
        "matched_criteria": [{"criterion": "eclipse", "matched": True}],
        "unmatched_criteria": [{"criterion": "conjunction", "matched": False}],
    }

    def _candidate(self, **overrides):
        defaults = {
            "claim_type": ClaimType.ASTRONOMICAL_DATING_CANDIDATE,
            "section": Section.DATING_CANDIDATES,
            "statement": "28 May 585 BCE is a candidate.",
            "engine": "starcode-astronomy/1.0",
            "confidence": 0.4,
            "payload": dict(self.EVIDENCE),
        }
        return make_claim(**{**defaults, **overrides})

    def test_a_candidate_must_name_the_engine(self):
        claim = self._candidate(engine=None)
        with pytest.raises(ContractViolation, match="must name the engine"):
            validate_claim(claim)

    def test_a_candidate_must_show_which_criteria_it_failed(self):
        """A match with no misses listed is unfalsifiable, and so is worth nothing.

        "The sky matches" cannot be argued with. "Matches the eclipse, does not match the
        conjunction" can be checked and rejected by a reader, which is the entire value
        of offering a candidate at all.
        """
        claim = self._candidate(payload={"matched_criteria": [{"criterion": "eclipse"}]})
        with_no_misses = validate_claim(claim, strict=False)
        assert any("matched_criteria" in problem for problem in with_no_misses)

        empty = self._candidate(payload={"matched_criteria": [], "unmatched_criteria": []})
        assert validate_claim(empty, strict=False), "a candidate matching nothing is not one"

    def test_a_candidate_without_its_working_is_downgraded_not_dropped(self):
        claim = coerce_claim(self._candidate(payload={}))
        assert claim.claim_type is ClaimType.AI_HYPOTHESIS
        assert "cannot be audited" in claim.payload["contract_adjustments"][0]

    def test_confidence_is_capped_exactly_as_a_hypothesis_is(self):
        """The precision of the ephemeris is the reason for the cap, not an exception to it.

        Computing that an eclipse crossed Anatolia on 28 May 585 BCE is arithmetic.
        Concluding that Herodotus describes *that* eclipse is not, and the exactness of
        the first is what makes an unbounded confidence in the second dishonest.
        """
        claim = coerce_claim(self._candidate(confidence=0.99))
        assert claim.confidence == settings.AI_HYPOTHESIS_CONFIDENCE_CAP
        assert claim.claim_type is ClaimType.ASTRONOMICAL_DATING_CANDIDATE

    def test_a_complete_candidate_is_lawful(self):
        assert validate_claim(self._candidate()) == []

    def test_it_is_not_evidence(self):
        assert ClaimType.ASTRONOMICAL_DATING_CANDIDATE not in EVIDENCE_TYPES
        assert self._candidate().is_evidence is False

    def test_it_is_presented_to_readers(self):
        """Every type needs its presentation, or the UI renders an unlabelled claim."""
        presentation = CLAIM_TYPE_PRESENTATION[ClaimType.ASTRONOMICAL_DATING_CANDIDATE]
        assert presentation["label"]
        assert presentation["description"]


class TestRestrictedDatingModes:
    """Eschatological calculation and historicizing may propose, never establish.

    Both modes take material that names no date and propose one for it. That is a
    legitimate thing to offer and an illegitimate thing to assert, and the difference has
    to survive an agent — or a model behind one — judging its own reasoning solid enough
    to call history.
    """

    @pytest.mark.parametrize("mode", ["eschatological", "historicizing"])
    @pytest.mark.parametrize(
        "forbidden", [ClaimType.VERIFIED_HISTORY, ClaimType.ASTRONOMICAL_CALCULATION]
    )
    def test_a_dating_agent_cannot_type_its_link_as_evidence(self, mode, forbidden):
        claim = coerce_claim(
            make_claim(
                claim_type=forbidden,
                produced_by="advanced_dating",
                engine="starcode-astronomy/1.0",
                citations=[CitationDraft(citation_text="Some source")],
                statement="The seventy weeks end in this year.",
                confidence=0.9,
            ),
            mode=mode,
        )

        assert claim.claim_type is ClaimType.AI_HYPOTHESIS
        assert claim.confidence <= settings.AI_HYPOTHESIS_CONFIDENCE_CAP
        assert any(
            "may not be typed as evidence" in a for a in claim.payload["contract_adjustments"]
        )

    @pytest.mark.parametrize("mode", ["eschatological", "historicizing"])
    def test_the_restriction_survives_a_citation_that_would_normally_satisfy_it(self, mode):
        """A real citation makes `verified_history` lawful everywhere else.

        Here it must not, because what is being asserted is not the cited fact but the
        link between a symbolic passage and a date, and no citation establishes that.
        """
        claim = coerce_claim(
            make_claim(
                claim_type=ClaimType.VERIFIED_HISTORY,
                produced_by="astronomical_dating",
                citations=[CitationDraft(citation_text="Josephus, Antiquities 10.11")],
                confidence=0.95,
            ),
            mode=mode,
        )
        assert claim.claim_type is not ClaimType.VERIFIED_HISTORY

    @pytest.mark.parametrize("mode", ["eschatological", "historicizing"])
    def test_real_arithmetic_from_other_agents_is_untouched(self, mode):
        """Scoped to the dating agents, and that scoping is the point.

        The astronomy agent still runs in these modes and still computes eclipses. "A
        total solar eclipse occurred on this date" is true whatever mode asked the
        question; downgrading it would make the report less honest, not more.
        """
        claim = coerce_claim(
            make_claim(
                claim_type=ClaimType.ASTRONOMICAL_CALCULATION,
                produced_by="astronomy",
                engine="starcode-astronomy/1.0",
                statement="Total solar eclipse on 28 May 585 BCE.",
                confidence=0.9,
            ),
            mode=mode,
        )
        assert claim.claim_type is ClaimType.ASTRONOMICAL_CALCULATION
        assert claim.confidence == 0.9

    def test_the_ordinary_dating_mode_is_not_restricted(self):
        """Free-tier dating searches a text that names its own phenomena.

        The restriction is on modes that supply a date for material carrying none, not on
        the search itself.
        """
        claim = coerce_claim(
            make_claim(
                claim_type=ClaimType.ASTRONOMICAL_CALCULATION,
                produced_by="astronomical_dating",
                engine="starcode-astronomy/1.0",
                confidence=0.8,
            ),
            mode="date",
        )
        assert claim.claim_type is ClaimType.ASTRONOMICAL_CALCULATION

    def test_a_mode_an_agent_invented_cannot_lift_the_restriction(self):
        """The mode comes from the analysis's options, never from the agent.

        `coerce_claim` is called by the base agent with the analysis's own mode, so an
        agent cannot exempt itself by claiming to be running a different one.
        """
        from app.agents.base import BaseAgent
        from app.agents.contracts import AgentResult

        class RogueAgent(BaseAgent):
            name = "advanced_dating"

            def run(self, ctx):
                return AgentResult(
                    agent_name=self.name,
                    claims=[
                        make_claim(
                            claim_type=ClaimType.VERIFIED_HISTORY,
                            produced_by="advanced_dating",
                            citations=[CitationDraft(citation_text="A source")],
                            confidence=0.95,
                        )
                    ],
                )

        from app.agents.base import AnalysisContext

        ctx = AnalysisContext(
            analysis_id="a",
            text="t",
            normalized_text="t",
            db=None,  # type: ignore[arg-type]
            options={"mode": "eschatological"},
        )
        result = RogueAgent().execute(ctx)
        assert result.claims[0].claim_type is ClaimType.AI_HYPOTHESIS


class TestTheFutureIsNeverAsserted:
    """ "It makes no claims about the future" — README.md, and now enforced on write.

    This rule was declared in `validate_claim` from the start and never reached
    production: the pipeline coerces claims, it does not validate them, so a hypothesis
    phrased as a forecast was rejected in tests and shipped to readers. The
    eschatological dating mode is what made closing it urgent — that mode exists to say
    what applying a framework yields, and the distance between that and a prediction is
    the entire product.
    """

    @pytest.mark.parametrize(
        "statement",
        [
            "The world will end on this date.",
            "The tribulation is going to happen in that year.",
            "The final judgement will occur on 21 December 2029.",
        ],
    )
    def test_a_forecast_is_downgraded_to_unresolved(self, statement):
        claim = coerce_claim(make_claim(claim_type=ClaimType.AI_HYPOTHESIS, statement=statement))
        assert claim.claim_type is ClaimType.UNCERTAIN
        assert any("does not predict" in a for a in claim.payload["contract_adjustments"])

    def test_a_dating_candidate_phrased_as_a_forecast_is_caught_too(self):
        claim = coerce_claim(
            make_claim(
                claim_type=ClaimType.ASTRONOMICAL_DATING_CANDIDATE,
                statement="Applying this framework, the world will end on this date.",
                engine="starcode-astronomy/1.0",
                payload={
                    "matched_criteria": [{"criterion": "eclipse"}],
                    "unmatched_criteria": [],
                },
            )
        )
        assert claim.claim_type is ClaimType.UNCERTAIN

    def test_describing_a_text_about_the_future_is_untouched(self):
        """The rule catches assertion, not subject matter.

        A text *about* the end of the world is ordinary material here. Saying when it
        will happen is not, and a rule that could not tell the two apart would make the
        platform unable to discuss its own core subject.
        """
        for statement in (
            "The passage describes the end of the world as imminent.",
            "One reading places the end of the seventy weeks in 34 CE.",
            "Tradition holds that these events precede the final judgement.",
        ):
            claim = coerce_claim(
                make_claim(claim_type=ClaimType.AI_HYPOTHESIS, statement=statement)
            )
            assert claim.claim_type is ClaimType.AI_HYPOTHESIS, statement
