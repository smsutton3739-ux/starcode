"""The epistemic contract, enforced in code.

The product promise — "never present speculation as established fact" — is not a matter
of prompt wording or tone. Prompts drift, models improvise, and a confident sentence reads
the same whether or not anything backs it. So the promise is implemented as a type system:

* Every assertion is a :class:`ClaimDraft` and must declare its ``claim_type``.
* :func:`validate_claim` rejects a claim that violates the rules for its type —
  a `verified_history` claim without a citation does not get to exist.
* Confidence for `ai_hypothesis` is clamped, not merely requested.

Agents may produce whatever they like. Only claims that survive validation reach a report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.config import settings
from app.db.models.analysis import ClaimType


class Section(str, Enum):
    """Report sections. The order here is the order of the rendered report."""

    EXECUTIVE_SUMMARY = "executive_summary"
    ORIGINAL_TEXT = "original_text"
    DETECTED_LANGUAGE = "detected_language"
    TRANSLATION = "translation"
    SOURCE_IDENTIFICATION = "source_identification"
    HISTORICAL_CONTEXT = "historical_context"
    ASTRONOMICAL_REFERENCES = "astronomical_references"
    CALENDAR_CONVERSION = "calendar_conversion"
    TIMELINE = "timeline"
    KEY_ENTITIES = "key_entities"
    SYMBOLISM = "symbolism"
    TRADITIONAL_INTERPRETATIONS = "traditional_interpretations"
    SCHOLARLY_VIEWS = "scholarly_views"
    ALTERNATIVE_INTERPRETATIONS = "alternative_interpretations"
    EVIDENCE = "evidence"
    CONFIDENCE_RATINGS = "confidence_ratings"
    REFERENCES = "references"
    FURTHER_READING = "further_reading"


SECTION_ORDER: list[Section] = list(Section)

SECTION_TITLES: dict[Section, str] = {
    Section.EXECUTIVE_SUMMARY: "Executive Summary",
    Section.ORIGINAL_TEXT: "Original Text",
    Section.DETECTED_LANGUAGE: "Detected Language",
    Section.TRANSLATION: "Translation",
    Section.SOURCE_IDENTIFICATION: "Source Identification",
    Section.HISTORICAL_CONTEXT: "Historical Context",
    Section.ASTRONOMICAL_REFERENCES: "Astronomical References",
    Section.CALENDAR_CONVERSION: "Calendar Conversion",
    Section.TIMELINE: "Timeline",
    Section.KEY_ENTITIES: "Key Entities",
    Section.SYMBOLISM: "Symbolism",
    Section.TRADITIONAL_INTERPRETATIONS: "Traditional Interpretations",
    Section.SCHOLARLY_VIEWS: "Modern Scholarly Views",
    Section.ALTERNATIVE_INTERPRETATIONS: "Alternative Interpretations",
    Section.EVIDENCE: "Evidence",
    Section.CONFIDENCE_RATINGS: "Confidence Ratings",
    Section.REFERENCES: "References",
    Section.FURTHER_READING: "Suggested Further Reading",
}


#: How each claim type is presented to a reader. The UI reads this, so the labelling can
#: never drift from the enforcement.
CLAIM_TYPE_PRESENTATION: dict[ClaimType, dict[str, str]] = {
    ClaimType.SOURCE_TEXT: {
        "label": "Source text",
        "short": "From your text",
        "description": "Quoted verbatim from the text you submitted. No interpretation added.",
        "tone": "neutral",
    },
    ClaimType.VERIFIED_HISTORY: {
        "label": "Verified history",
        "short": "Established",
        "description": (
            "Supported by the historical record and citable. 'Verified' means "
            "well-attested in scholarship, not beyond all dispute."
        ),
        "tone": "established",
    },
    ClaimType.ASTRONOMICAL_CALCULATION: {
        "label": "Astronomical calculation",
        "short": "Calculated",
        "description": (
            "Computed by the platform's ephemeris and calendar engines. Reproducible, "
            "and reported with the accuracy of the algorithm that produced it."
        ),
        "tone": "calculated",
    },
    ClaimType.TEXTUAL_ANALYSIS: {
        "label": "Textual analysis",
        "short": "Text analysis",
        "description": "An observation about the text itself — its language, structure or vocabulary.",
        "tone": "analytical",
    },
    ClaimType.TRADITIONAL_INTERPRETATION: {
        "label": "Traditional interpretation",
        "short": "Tradition holds",
        "description": (
            "What a religious or cultural tradition has historically understood this to "
            "mean. Reported as that tradition's position, not endorsed as fact."
        ),
        "tone": "traditional",
    },
    ClaimType.SCHOLARLY_INTERPRETATION: {
        "label": "Scholarly interpretation",
        "short": "Scholars argue",
        "description": (
            "A position argued in academic literature. Where scholars disagree, the "
            "disagreement is reported rather than resolved."
        ),
        "tone": "scholarly",
    },
    ClaimType.AI_HYPOTHESIS: {
        "label": "AI hypothesis",
        "short": "AI conjecture",
        "description": (
            "Generated by the language model. This is a suggestion for you to evaluate, "
            "not evidence, and it may be wrong. Confidence is capped by design."
        ),
        "tone": "speculative",
    },
    ClaimType.UNCERTAIN: {
        "label": "Unresolved",
        "short": "Unknown",
        "description": "Genuinely undetermined on the available evidence.",
        "tone": "unknown",
    },
}

#: Claim types that may never be stated without a citation.
REQUIRES_CITATION: frozenset[ClaimType] = frozenset(
    {ClaimType.VERIFIED_HISTORY, ClaimType.SCHOLARLY_INTERPRETATION}
)

#: Claim types that must name the engine and algorithm that produced them.
REQUIRES_ENGINE: frozenset[ClaimType] = frozenset({ClaimType.ASTRONOMICAL_CALCULATION})

#: Types that constitute *evidence*. Everything else is commentary, however plausible.
EVIDENCE_TYPES: frozenset[ClaimType] = frozenset(
    {ClaimType.SOURCE_TEXT, ClaimType.VERIFIED_HISTORY, ClaimType.ASTRONOMICAL_CALCULATION}
)

#: Language that asserts a future event as settled. A claim about the future may only be
#: `ai_hypothesis` or `traditional_interpretation`, and never phrased as a certainty.
_PREDICTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bwill (?:certainly|definitely|surely) \w+",
        r"\bis going to happen\b",
        r"\bthe world will end\b",
        r"\bwill occur on\b",
        r"\bis prophesied to happen in \d{4}\b",
    )
]


class ContractViolation(ValueError):
    """Raised when a claim cannot lawfully be made."""

    def __init__(self, message: str, claim: ClaimDraft | None = None) -> None:
        super().__init__(message)
        self.claim = claim


@dataclass(slots=True)
class CitationDraft:
    citation_text: str
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    publication: str | None = None
    year: int | None = None
    url: str | None = None
    doi: str | None = None
    locator: str | None = None
    reference_kind: str = "secondary"
    reliability: str | None = None
    verified: bool = False
    """True only when the citation came from the curated corpus. A model-supplied
    reference is stored but flagged, because language models fabricate citations and a
    fabricated one that looks real is the single most damaging failure mode here."""

    def to_dict(self) -> dict:
        return {
            "citation_text": self.citation_text,
            "title": self.title,
            "authors": self.authors,
            "publication": self.publication,
            "year": self.year,
            "url": self.url,
            "doi": self.doi,
            "locator": self.locator,
            "reference_kind": self.reference_kind,
            "reliability": self.reliability,
            "verified": self.verified,
        }


@dataclass(slots=True)
class ClaimDraft:
    """One assertion, before it is persisted."""

    section: Section
    claim_type: ClaimType
    statement: str
    produced_by: str
    confidence: float = 0.5
    reasoning: str | None = None
    confidence_basis: str | None = None
    engine: str | None = None
    algorithm_reference: str | None = None
    citations: list[CitationDraft] = field(default_factory=list)
    quoted_text: str | None = None
    text_span: tuple[int, int] | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    ordering: int = 0

    @property
    def is_evidence(self) -> bool:
        return self.claim_type in EVIDENCE_TYPES

    def to_dict(self) -> dict:
        # The key is "references", matching both the persisted `Claim.references`
        # relationship and the `ClaimOut` API schema. A claim serialised into a stored
        # report and one fetched from the API therefore have the same shape, and any
        # consumer — the web UI, the PDF exporter, the CSV writer — can read either
        # without knowing which produced it.
        return {
            "section": self.section.value,
            "claim_type": self.claim_type.value,
            "statement": self.statement,
            "reasoning": self.reasoning,
            "confidence": round(self.confidence, 3),
            "confidence_basis": self.confidence_basis,
            "produced_by": self.produced_by,
            "engine": self.engine,
            "algorithm_reference": self.algorithm_reference,
            "references": [c.to_dict() for c in self.citations],
            "quoted_text": self.quoted_text,
            "text_span": list(self.text_span) if self.text_span else None,
            "payload": self.payload,
            "ordering": self.ordering,
            "presentation": CLAIM_TYPE_PRESENTATION[self.claim_type],
            "is_evidence": self.is_evidence,
        }


def validate_claim(claim: ClaimDraft, *, strict: bool = True) -> list[str]:
    """Check a claim against the contract.

    Returns a list of problems. With ``strict=True`` a non-empty list raises, because in
    the analysis pipeline an invalid claim must be dropped rather than shown.
    """
    problems: list[str] = []

    if not claim.statement or not claim.statement.strip():
        problems.append("statement is empty")

    if not 0.0 <= claim.confidence <= 1.0:
        problems.append(f"confidence {claim.confidence} outside [0, 1]")

    if claim.claim_type in REQUIRES_CITATION and not claim.citations:
        problems.append(
            f"claim_type '{claim.claim_type.value}' requires at least one citation; "
            "downgrade it to 'ai_hypothesis' or 'uncertain' if none can be given"
        )

    if claim.claim_type in REQUIRES_ENGINE and not claim.engine:
        problems.append(
            f"claim_type '{claim.claim_type.value}' must name the engine that produced it"
        )

    if claim.claim_type == ClaimType.SOURCE_TEXT and not claim.quoted_text:
        problems.append("claim_type 'source_text' must carry the quoted text")

    if claim.claim_type == ClaimType.AI_HYPOTHESIS:
        if claim.confidence > settings.AI_HYPOTHESIS_CONFIDENCE_CAP:
            problems.append(
                f"ai_hypothesis confidence {claim.confidence:.2f} exceeds the cap "
                f"{settings.AI_HYPOTHESIS_CONFIDENCE_CAP}"
            )
        for pattern in _PREDICTION_PATTERNS:
            if pattern.search(claim.statement):
                problems.append(
                    "hypothesis asserts a future event as settled; rephrase as a possibility"
                )
                break

    if strict and problems:
        raise ContractViolation("; ".join(problems), claim)
    return problems


def coerce_claim(claim: ClaimDraft) -> ClaimDraft:
    """Repair a claim into a lawful form rather than discarding it.

    Preferred over rejection in the pipeline: a model that returns an uncited historical
    assertion has still produced something worth showing — as a hypothesis. Silently
    dropping it loses information; silently promoting it would be the exact failure the
    platform exists to prevent. Downgrading is the honest third option, and the
    downgrade itself is recorded in `payload` so it is visible in the audit trail.
    """
    downgrades: list[str] = []

    if claim.claim_type in REQUIRES_CITATION and not claim.citations:
        downgrades.append(
            f"{claim.claim_type.value} → ai_hypothesis (no citation supplied)"
        )
        claim.claim_type = ClaimType.AI_HYPOTHESIS

    if claim.claim_type in REQUIRES_ENGINE and not claim.engine:
        downgrades.append(
            f"{claim.claim_type.value} → ai_hypothesis (no computation engine named)"
        )
        claim.claim_type = ClaimType.AI_HYPOTHESIS

    if claim.claim_type == ClaimType.SOURCE_TEXT and not claim.quoted_text:
        downgrades.append("source_text → textual_analysis (no verbatim quotation)")
        claim.claim_type = ClaimType.TEXTUAL_ANALYSIS

    if claim.claim_type == ClaimType.AI_HYPOTHESIS:
        cap = settings.AI_HYPOTHESIS_CONFIDENCE_CAP
        if claim.confidence > cap:
            downgrades.append(f"confidence {claim.confidence:.2f} clamped to cap {cap}")
            claim.confidence = cap

    claim.confidence = max(0.0, min(1.0, claim.confidence))

    if downgrades:
        claim.payload = {**claim.payload, "contract_adjustments": downgrades}

    return claim


def confidence_band(value: float) -> str:
    if value >= 0.85:
        return "very high"
    if value >= 0.7:
        return "high"
    if value >= 0.5:
        return "moderate"
    if value >= 0.3:
        return "low"
    return "very low"


def summarize_confidence(claims: list[ClaimDraft]) -> dict:
    """Aggregate confidence, weighted so that evidence counts and conjecture does not
    inflate the headline number."""
    if not claims:
        return {
            "overall": None,
            "band": "not assessed",
            "by_type": {},
            "evidence_claim_count": 0,
            "total_claim_count": 0,
            "rationale": "No claims were produced.",
        }

    by_type: dict[str, dict] = {}
    for claim in claims:
        entry = by_type.setdefault(
            claim.claim_type.value,
            {"count": 0, "mean_confidence": 0.0, "label": CLAIM_TYPE_PRESENTATION[claim.claim_type]["label"]},
        )
        entry["count"] += 1
        entry["mean_confidence"] += claim.confidence

    for entry in by_type.values():
        entry["mean_confidence"] = round(entry["mean_confidence"] / entry["count"], 3)

    weights = {
        ClaimType.SOURCE_TEXT: 1.0,
        ClaimType.ASTRONOMICAL_CALCULATION: 1.0,
        ClaimType.VERIFIED_HISTORY: 1.0,
        ClaimType.TEXTUAL_ANALYSIS: 0.7,
        ClaimType.SCHOLARLY_INTERPRETATION: 0.6,
        ClaimType.TRADITIONAL_INTERPRETATION: 0.3,
        ClaimType.AI_HYPOTHESIS: 0.15,
        ClaimType.UNCERTAIN: 0.1,
    }
    numerator = sum(c.confidence * weights[c.claim_type] for c in claims)
    denominator = sum(weights[c.claim_type] for c in claims)
    overall = numerator / denominator if denominator else 0.0

    evidence_count = sum(1 for c in claims if c.is_evidence)
    hypothesis_count = sum(1 for c in claims if c.claim_type == ClaimType.AI_HYPOTHESIS)

    if evidence_count == 0:
        rationale = (
            "This analysis rests on no verifiable evidence claims — it is entirely "
            "interpretation and conjecture. Treat the overall figure as a measure of "
            "internal coherence, not of truth."
        )
    elif hypothesis_count > evidence_count:
        rationale = (
            f"{hypothesis_count} AI hypotheses against {evidence_count} evidence-grade "
            "claims. The interpretive material substantially outweighs what can be verified, "
            "which is common for symbolic and prophetic texts."
        )
    else:
        rationale = (
            f"{evidence_count} evidence-grade claims (source text, calculation or cited "
            f"history) against {hypothesis_count} AI hypotheses. Confidence is weighted "
            "toward the verifiable material."
        )

    return {
        "overall": round(overall, 3),
        "band": confidence_band(overall),
        "by_type": by_type,
        "evidence_claim_count": evidence_count,
        "hypothesis_claim_count": hypothesis_count,
        "total_claim_count": len(claims),
        "rationale": rationale,
    }


@dataclass(slots=True)
class AgentResult:
    """What every agent returns."""

    agent_name: str
    status: str = "succeeded"
    claims: list[ClaimDraft] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    reasoning_summary: str = ""
    """A plain-language account of how this agent reached its conclusions, shown to the
    user in the explainability panel. Not the model's chain of thought — a deliberate,
    reader-facing summary."""
    error: str | None = None
    duration_ms: int | None = None
    attempts: int = 1
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == "succeeded"

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "status": self.status,
            "claim_count": len(self.claims),
            "entity_count": len(self.entities),
            "reasoning_summary": self.reasoning_summary,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "attempts": self.attempts,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


__all__ = [
    "Section",
    "SECTION_ORDER",
    "SECTION_TITLES",
    "ClaimType",
    "CLAIM_TYPE_PRESENTATION",
    "REQUIRES_CITATION",
    "REQUIRES_ENGINE",
    "EVIDENCE_TYPES",
    "ContractViolation",
    "CitationDraft",
    "ClaimDraft",
    "AgentResult",
    "validate_claim",
    "coerce_claim",
    "confidence_band",
    "summarize_confidence",
]
