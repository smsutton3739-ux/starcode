"""Report assembly.

Turns the claim set into the ordered report the product specifies. The assembler never
invents content: every sentence in a section traces to a claim, and a section with no
claims is rendered as explicitly empty with the reason, rather than being padded or
silently dropped.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentResult, AnalysisContext
from app.agents.contracts import (
    SECTION_ORDER,
    SECTION_TITLES,
    ClaimDraft,
    ClaimType,
    Section,
)
from app.db.models.analysis import Analysis
from app.db.models.content import Document

GENERATOR_VERSION = "1.0.0"

#: Why a section might legitimately be empty. Shown to the reader instead of a blank.
EMPTY_SECTION_REASONS: dict[Section, str] = {
    Section.TRANSLATION: "The text is already in English, or no translation was produced.",
    Section.ASTRONOMICAL_REFERENCES: "No astronomical references were detected in this text.",
    Section.CALENDAR_CONVERSION: "No date expressions were found that could be converted.",
    Section.TIMELINE: "No datable events were established, so no timeline could be built.",
    Section.SYMBOLISM: "No symbolic content was identified.",
    Section.TRADITIONAL_INTERPRETATIONS: (
        "No traditional interpretations were produced. If the analysis ran offline, this "
        "section requires a language model."
    ),
    Section.SCHOLARLY_VIEWS: (
        "No scholarly positions were produced. If the analysis ran offline, this section "
        "requires a language model."
    ),
    Section.ALTERNATIVE_INTERPRETATIONS: "No alternative readings were generated.",
    Section.REFERENCES: "No citations were produced for this analysis.",
    Section.FURTHER_READING: "No further reading was suggested.",
}


def build_report(
    *,
    analysis: Analysis,
    document: Document,
    claims: list[ClaimDraft],
    results: list[AgentResult],
    context: AnalysisContext,
    confidence: dict,
) -> dict[str, Any]:
    by_section: dict[Section, list[ClaimDraft]] = {section: [] for section in SECTION_ORDER}
    for claim in claims:
        by_section[claim.section].append(claim)

    timeline = _build_timeline(claims, context)
    references = _collect_references(claims)
    further_reading = _further_reading(context, claims)
    trace = _reasoning_trace(results)
    summary = _executive_summary(analysis, document, claims, context, confidence, results)

    # Four sections are backed by structured data rather than by claims. Attaching that
    # data here is what stops them rendering as empty when they are in fact populated —
    # the timeline, the citation list, the entity table and the confidence breakdown all
    # live in their own shapes because the UI renders them as tables and charts.
    section_data: dict[Section, dict] = {
        Section.TIMELINE: {"events": timeline},
        Section.REFERENCES: {"references": references},
        Section.FURTHER_READING: {"items": further_reading},
        Section.CONFIDENCE_RATINGS: {"summary": confidence},
        Section.KEY_ENTITIES: {"entities": context.entities},
        Section.CALENDAR_CONVERSION: {"conversions": context.calendar.get("conversions", [])},
        Section.ASTRONOMICAL_REFERENCES: {
            "references": context.astronomy.get("references", []),
            "computed": context.astronomy.get("computed", []),
        },
    }

    sections: list[dict] = []
    for section in SECTION_ORDER:
        if section == Section.EXECUTIVE_SUMMARY:
            continue  # assembled last, from everything else
        section_claims = by_section[section]
        data = section_data.get(section, {})
        has_data = any(bool(value) for value in data.values())
        sections.append(
            {
                "key": section.value,
                "title": SECTION_TITLES[section],
                "claims": [c.to_dict() for c in section_claims],
                "claim_count": len(section_claims),
                "data": data,
                "is_empty": not section_claims and not has_data,
                "empty_reason": (
                    None
                    if section_claims or has_data
                    else EMPTY_SECTION_REASONS.get(
                        section, "No findings were produced for this section."
                    )
                ),
                "claim_type_breakdown": _breakdown(section_claims),
            }
        )

    sections.insert(
        0,
        {
            "key": Section.EXECUTIVE_SUMMARY.value,
            "title": SECTION_TITLES[Section.EXECUTIVE_SUMMARY],
            "claims": [],
            "claim_count": 0,
            "data": {},
            "is_empty": False,
            "empty_reason": None,
            "narrative": summary,
            "claim_type_breakdown": {},
        },
    )

    word_count = sum(len(c.statement.split()) for c in claims) + len(summary.split())

    return {
        "executive_summary": summary,
        "sections": sections,
        "timeline": timeline,
        "confidence_summary": confidence,
        "references": references,
        "further_reading": further_reading,
        "reasoning_trace": trace,
        "word_count": word_count,
        "generator_version": GENERATOR_VERSION,
    }


def _breakdown(claims: list[ClaimDraft]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for claim in claims:
        counts[claim.claim_type.value] = counts.get(claim.claim_type.value, 0) + 1
    return counts


def _build_timeline(claims: list[ClaimDraft], context: AnalysisContext) -> list[dict]:
    """Datable events, sorted. Each entry says how firm its date is."""
    events: list[dict] = []

    for conversion in context.calendar.get("conversions", []):
        year = conversion.get("astronomical_year")
        if year is None:
            for entry in conversion.get("all_systems", []):
                if entry["system"] == "gregorian":
                    year = entry["year"]
                    break
        if year is None:
            continue
        events.append(
            {
                "year": int(year),
                "label": conversion["gregorian_label"],
                "description": f"Date reference in the text: “{conversion['input']}”",
                "kind": "calendar_conversion",
                "certainty": "calculated",
                "confidence": conversion.get("confidence", 0.7),
                "note": conversion.get("uncertainty_note"),
            }
        )

    for computed in context.astronomy.get("computed", []):
        correlation = computed["correlation"]
        for eclipse in correlation.get("eclipses_in_year", [])[:8]:
            events.append(
                {
                    "year": eclipse["year"],
                    "label": eclipse["gregorian_label"],
                    "description": eclipse["label"],
                    "kind": "astronomical_event",
                    "certainty": "calculated",
                    "confidence": 0.9,
                    "note": eclipse["accuracy_note"],
                }
            )

    for item in (context.history or {}).get("timeline", []):
        try:
            year = int(item.get("year"))
        except (TypeError, ValueError):
            continue
        if str(item.get("era", "")).upper() == "BCE" and year > 0:
            year = 1 - year
        events.append(
            {
                "year": year,
                "label": f"{abs(year)} {'BCE' if year <= 0 else 'CE'}",
                "description": item.get("event", ""),
                "kind": "historical_event",
                "certainty": item.get("certainty", "approximate"),
                "confidence": {"attested": 0.85, "approximate": 0.6, "disputed": 0.4}.get(
                    item.get("certainty", "approximate"), 0.5
                ),
                "note": None,
            }
        )

    for entity in context.entities:
        earliest, latest = entity.get("earliest_year"), entity.get("latest_year")
        if earliest is None:
            continue
        events.append(
            {
                "year": int(earliest),
                "year_end": int(latest) if latest is not None else None,
                "label": f"{abs(int(earliest))} {'BCE' if int(earliest) <= 0 else 'CE'}",
                "description": f"{entity['name']} ({entity['entity_type'].replace('_', ' ')})",
                "kind": "entity_span",
                "certainty": "approximate",
                "confidence": 0.5,
                "note": "Conventional date range for this entity, not a claim about the text.",
            }
        )

    seen: set[tuple] = set()
    unique: list[dict] = []
    for event in sorted(events, key=lambda e: e["year"]):
        key = (event["year"], event["description"][:80])
        if key not in seen:
            seen.add(key)
            unique.append(event)
    return unique


def _collect_references(claims: list[ClaimDraft]) -> list[dict]:
    references: list[dict] = []
    seen: set[str] = set()
    for claim in claims:
        for citation in claim.citations:
            if citation.citation_text in seen:
                continue
            seen.add(citation.citation_text)
            references.append(
                {
                    **citation.to_dict(),
                    "supports_claim": claim.statement[:160],
                    "claim_type": claim.claim_type.value,
                }
            )
    # Verified (corpus) citations first — the ones a reader can actually rely on.
    references.sort(key=lambda r: (not r["verified"], r["citation_text"]))
    return references


def _further_reading(context: AnalysisContext, claims: list[ClaimDraft]) -> list[dict]:
    reading: list[dict] = []
    seen: set[str] = set()

    for hit in context.retrieved[:6]:
        if hit.get("citation") and hit["citation"] not in seen:
            seen.add(hit["citation"])
            reading.append(
                {
                    "title": hit["title"],
                    "citation": hit["citation"],
                    "why": (
                        f"Matched this text in the reference corpus "
                        f"({hit['match_strength']} similarity)."
                    ),
                    "source": "curated corpus",
                }
            )

    if any(c.claim_type == ClaimType.ASTRONOMICAL_CALCULATION for c in claims):
        for title, citation, why in (
            (
                "Astronomical Algorithms",
                "Meeus, J., Astronomical Algorithms, 2nd ed. (Willmann-Bell, 1998)",
                "The source of the eclipse, lunar-phase and season algorithms used above.",
            ),
            (
                "NASA Five Millennium Canon of Solar Eclipses",
                "Espenak, F. & Meeus, J., Five Millennium Canon of Solar Eclipses: "
                "-1999 to +3000 (NASA/TP-2006-214141)",
                "Independently check any eclipse this report computes.",
            ),
        ):
            if citation not in seen:
                seen.add(citation)
                reading.append(
                    {"title": title, "citation": citation, "why": why, "source": "engine reference"}
                )

    if any(
        c.claim_type == ClaimType.ASTRONOMICAL_CALCULATION and c.engine and "calendar" in c.engine
        for c in claims
    ):
        citation = (
            "Dershowitz, N. & Reingold, E. M., Calendrical Calculations: The Ultimate "
            "Edition, 4th ed. (Cambridge University Press, 2018)"
        )
        if citation not in seen:
            reading.append(
                {
                    "title": "Calendrical Calculations",
                    "citation": citation,
                    "why": "The source of every calendar conversion in this report.",
                    "source": "engine reference",
                }
            )

    return reading


def _reasoning_trace(results: list[AgentResult]) -> list[dict]:
    """The explainability panel: what each agent did, in order, and how it went."""
    return [
        {
            "step": index + 1,
            "agent": result.agent_name,
            "status": result.status,
            "reasoning": result.reasoning_summary,
            "claims_produced": len(result.claims),
            "entities_produced": len(result.entities),
            "duration_ms": result.duration_ms,
            "attempts": result.attempts,
            "provider": result.provider,
            "model": result.model,
            "error": result.error,
        }
        for index, result in enumerate(results)
    ]


def _executive_summary(
    analysis: Analysis,
    document: Document,
    claims: list[ClaimDraft],
    context: AnalysisContext,
    confidence: dict,
    results: list[AgentResult],
) -> str:
    """A factual summary assembled from the claim set.

    Deliberately mechanical rather than model-written: the summary is the part most
    likely to be read alone, so it must not be the part where hedging gets lost.
    """
    parts: list[str] = []

    language = (context.language or {}).get("language_name")
    words = document.word_count or len(document.raw_text.split())
    opening = f"This analysis covers a {words:,}-word text"
    if language:
        opening += f" in {language}"
    if context.translation.get("translated_text"):
        opening += ", translated into English for analysis"
    parts.append(opening + ".")

    identification = context.source_identification or {}
    if identification.get("identified"):
        parts.append(
            f"It has been identified as {identification['title']} "
            f"(similarity {identification.get('score', 0):.2f})."
        )
    elif identification.get("title"):
        parts.append(
            f"The closest match in the reference corpus is {identification['title']}, but "
            "the similarity is below the threshold for identification."
        )
    else:
        parts.append("No source in the reference corpus matched it closely.")

    counts = _breakdown(claims)
    evidence = confidence["evidence_claim_count"]
    hypotheses = counts.get(ClaimType.AI_HYPOTHESIS.value, 0)
    parts.append(
        f"{len(claims)} findings were produced: {evidence} evidence-grade "
        f"(direct quotation, calculation, or cited history) and {hypotheses} AI hypotheses."
    )

    astro_count = counts.get(ClaimType.ASTRONOMICAL_CALCULATION.value, 0)
    if astro_count:
        parts.append(
            f"{astro_count} astronomical or calendrical calculations were performed; each is "
            "reproducible and carries the accuracy of the algorithm that produced it."
        )

    references = context.astronomy.get("references", [])
    if references:
        terms = sorted({r["term"] for r in references})
        parts.append(
            f"Astronomical references detected: {', '.join(terms[:8])}"
            + (f" and {len(terms) - 8} more" if len(terms) > 8 else "")
            + "."
        )

    parts.append(confidence["rationale"])

    failed = [r.agent_name for r in results if r.status == "failed"]
    skipped = [r.agent_name for r in results if r.status == "skipped"]
    if failed:
        parts.append(
            f"The following stages failed and their sections are empty: {', '.join(failed)}."
        )
    if skipped:
        parts.append(
            f"The following stages were unavailable in this run and their sections are "
            f"marked accordingly: {', '.join(skipped)}."
        )

    parts.append(
        "Every statement in this report is labelled by kind. Nothing marked as an AI "
        "hypothesis, a traditional interpretation, or a scholarly interpretation should be "
        "read as established fact."
    )

    return " ".join(parts)


__all__ = ["build_report", "GENERATOR_VERSION"]
