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
    defaults = dict(
        section=Section.HISTORICAL_CONTEXT,
        claim_type=ClaimType.AI_HYPOTHESIS,
        statement="A statement.",
        produced_by="test",
        confidence=0.4,
    )
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
        claim = make_claim(
            claim_type=ClaimType.SOURCE_TEXT, confidence=1.0, quoted_text="quoted"
        )
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
        claims = [
            make_claim(claim_type=ClaimType.SOURCE_TEXT, confidence=1.0, quoted_text="x")
        ] + [make_claim(claim_type=ClaimType.AI_HYPOTHESIS, confidence=0.1) for _ in range(5)]

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
        claims = [
            make_claim(claim_type=ClaimType.SOURCE_TEXT, confidence=1.0, quoted_text="x")
        ] + [make_claim(claim_type=ClaimType.AI_HYPOTHESIS) for _ in range(5)]
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
        assert claim.to_dict()["citations"][0]["verified"] is False
