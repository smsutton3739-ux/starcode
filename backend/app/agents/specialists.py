"""The eight specialist agents.

Each owns one question and returns typed claims. Deterministic agents (calendar,
astronomy) never consult a language model at all — their output is calculation, and
routing it through a model would only add a way for it to be wrong.
"""

from __future__ import annotations

import json
from typing import Any

from app.agents.base import SHARED_SYSTEM_RULES, AgentResult, AnalysisContext, BaseAgent
from app.agents.contracts import CitationDraft, ClaimType, Section
from app.astronomy import service as astro
from app.calendars import service as cal
from app.core.logging import get_logger
from app.knowledge.rag import retrieve

logger = get_logger(__name__)


def _json_shape(shape: dict) -> str:
    return json.dumps(shape, indent=2)


# ======================================================================================
# 1. Language
# ======================================================================================


class LanguageAgent(BaseAgent):
    name = "language"
    description = "language detection and translation"
    max_tokens = 8000

    SYSTEM = (
        SHARED_SYSTEM_RULES
        + """
You identify the language and script of a text and translate it into English when needed.

For historical texts, name the period as well as the language where you can — "Koine
Greek" rather than "Greek", "Biblical Hebrew" rather than "Hebrew" — because the period
constrains what the text can be. If you translate, note any passage where the source is
ambiguous and the translation had to choose; those choices are frequently where
interpretive disputes begin.
"""
    )

    def run(self, ctx: AnalysisContext) -> AgentResult:
        result = AgentResult(agent_name=self.name)

        detection, response = self.ask(
            self.SYSTEM,
            f"""<task>detect_language</task>
Identify the language and script of the text below.

<text>
{ctx.excerpt(6000)}
</text>

Reply with JSON:
{_json_shape({
    "language_code": "ISO 639 code, or 'und'",
    "language_name": "including period, e.g. 'Koine Greek'",
    "script": "script name",
    "confidence": 0.0,
    "needs_translation": True,
    "register": "register or dialect notes, or null",
    "reasoning": "what features led to this identification",
})}""",
        )

        if self.unavailable(detection):
            detection = {}

        ctx.language = detection
        result.data["language"] = detection
        result.provider, result.model = response.provider, response.model
        result.input_tokens, result.output_tokens = response.input_tokens, response.output_tokens

        language_name = detection.get("language_name", "undetermined")
        confidence = float(detection.get("confidence") or 0.4)

        result.claims.append(
            self.make_claim(
                section=Section.DETECTED_LANGUAGE,
                claim_type=ClaimType.TEXTUAL_ANALYSIS,
                statement=(
                    f"The text is written in {language_name}"
                    + (f" ({detection['script']} script)" if detection.get("script") else "")
                    + "."
                ),
                reasoning=detection.get("reasoning"),
                confidence=confidence,
                confidence_basis=f"Detection method: {detection.get('method', 'model analysis')}.",
                payload=detection,
            )
        )

        if detection.get("register"):
            result.claims.append(
                self.make_claim(
                    section=Section.DETECTED_LANGUAGE,
                    claim_type=ClaimType.TEXTUAL_ANALYSIS,
                    statement=f"Register: {detection['register']}.",
                    reasoning=(
                        "Register narrows the likely translation and period, which in turn "
                        "constrains which source the text can be drawn from."
                    ),
                    confidence=max(0.3, confidence - 0.1),
                )
            )

        # Translation, only if needed.
        if detection.get("needs_translation") and detection.get("language_code") not in (
            "en",
            None,
        ):
            translation, translation_response = self.ask(
                self.SYSTEM,
                f"""<task>translate</task>
Translate the following {language_name} text into clear modern English.

<text>
{ctx.excerpt(10000)}
</text>

Reply with JSON:
{_json_shape({
    "translated_text": "the English translation",
    "translation_notes": ["places where the source is ambiguous and you had to choose"],
    "confidence": 0.0,
    "reasoning": "approach taken and any difficulties",
})}""",
            )

            if self.unavailable(translation):
                result.claims.append(
                    self.make_claim(
                        section=Section.TRANSLATION,
                        claim_type=ClaimType.UNCERTAIN,
                        statement=(
                            "Translation is unavailable: the deterministic offline engine "
                            "cannot translate. The analysis below works from the original "
                            "text, so sections depending on meaning are weaker than usual."
                        ),
                        confidence=1.0,
                        confidence_basis="System capability, not a property of the text.",
                    )
                )
            else:
                ctx.translation = translation
                result.data["translation"] = translation
                result.claims.append(
                    self.make_claim(
                        section=Section.TRANSLATION,
                        claim_type=ClaimType.TEXTUAL_ANALYSIS,
                        statement=translation.get("translated_text", ""),
                        reasoning=translation.get("reasoning"),
                        confidence=float(translation.get("confidence") or 0.6),
                        confidence_basis=(
                            "Machine translation of a historical text. Ancient languages "
                            "carry ambiguities no translation fully preserves; consult a "
                            "critical edition before relying on any single rendering."
                        ),
                        payload={"notes": translation.get("translation_notes", [])},
                    )
                )
                for note in translation.get("translation_notes", [])[:6]:
                    result.claims.append(
                        self.make_claim(
                            section=Section.TRANSLATION,
                            claim_type=ClaimType.UNCERTAIN,
                            statement=f"Translation choice: {note}",
                            confidence=0.5,
                            confidence_basis="Flagged by the translator as ambiguous in the source.",
                        )
                    )

        result.reasoning_summary = (
            f"Identified the language as {language_name} with confidence "
            f"{confidence:.0%}. "
            + (
                "Translated into English and flagged ambiguous renderings."
                if ctx.translation.get("translated_text")
                else "No translation was required or available."
            )
        )
        return result


# ======================================================================================
# 2. Source identification
# ======================================================================================


class SourceIdentificationAgent(BaseAgent):
    name = "source_identification"
    description = "source identification"

    SYSTEM = (
        SHARED_SYSTEM_RULES
        + """
You identify which work a text comes from.

You are shown candidate matches retrieved from a curated corpus. Grade them. A retrieval
hit is evidence, not proof — high lexical similarity to a passage can also mean the text
quotes it, parodies it, or shares a common source.

If nothing matches, say so. "Not in this corpus" is a useful, honest answer, and far
better than a confident guess. The corpus is a demonstration set of a few dozen works,
so absence from it means very little about the text.
"""
    )

    def run(self, ctx: AnalysisContext) -> AgentResult:
        result = AgentResult(agent_name=self.name)

        hits = retrieve(ctx.db, ctx.working_text[:4000], limit=6)
        ctx.retrieved = [h.to_dict() for h in hits]
        result.data["retrieved"] = ctx.retrieved

        if not hits:
            result.claims.append(
                self.make_claim(
                    section=Section.SOURCE_IDENTIFICATION,
                    claim_type=ClaimType.UNCERTAIN,
                    statement=(
                        "No work in the reference corpus matches this text closely enough "
                        "to propose an identification."
                    ),
                    reasoning=(
                        "Semantic retrieval returned nothing above the similarity floor. "
                        "The corpus holds a few dozen curated works, so this indicates the "
                        "text is outside that set — not that it is unidentifiable."
                    ),
                    confidence=0.8,
                    confidence_basis="Absence of retrieval hits above threshold.",
                )
            )
            result.reasoning_summary = (
                "Searched the reference corpus and found no candidate above the similarity "
                "floor, so no identification is proposed."
            )
            return result

        candidate_blocks = "\n".join(
            f"""<candidate>
title: {h.title}
score: {h.score:.3f}
strength: {h.match_strength}
citation: {h.citation or "none"}
excerpt: {h.content[:400]}
</candidate>"""
            for h in hits
        )

        grading, response = self.ask(
            self.SYSTEM,
            f"""<task>identify_source</task>
Grade these candidate sources against the submitted text.

<text>
{ctx.excerpt(4000)}
</text>

{candidate_blocks}

Reply with JSON:
{_json_shape({
    "identified": False,
    "best_match": {"title": "", "relationship": "quotation | allusion | same work | unrelated"},
    "confidence": 0.0,
    "reasoning": "why this candidate does or does not fit",
    "alternative_candidates": ["other plausible sources, if any"],
})}""",
        )

        best = hits[0]
        result.provider, result.model = response.provider, response.model

        if self.unavailable(grading):
            grading = {
                "identified": best.match_strength == "strong",
                "confidence": best.score,
                "reasoning": (
                    f"Offline grading: the closest corpus entry is “{best.title}” at "
                    f"similarity {best.score:.2f} ({best.match_strength} match), with "
                    f"{best.lexical_overlap:.0%} vocabulary overlap."
                ),
            }

        identified = bool(grading.get("identified"))
        confidence = float(grading.get("confidence") or best.score)

        ctx.source_identification = {
            "identified": identified,
            "title": best.title,
            "citation": best.citation,
            "score": best.score,
            "match_strength": best.match_strength,
            "tradition": best.tradition,
            "metadata": best.metadata,
        }

        result.claims.append(
            self.make_claim(
                section=Section.SOURCE_IDENTIFICATION,
                claim_type=(
                    ClaimType.SCHOLARLY_INTERPRETATION if identified else ClaimType.AI_HYPOTHESIS
                ),
                statement=(
                    f"The text corresponds to {best.title}."
                    if identified
                    else f"The closest match in the reference corpus is {best.title}, but the "
                    "similarity is not strong enough to call this an identification."
                ),
                reasoning=grading.get("reasoning"),
                confidence=min(confidence, 0.9),
                confidence_basis=(
                    f"Retrieval similarity {best.score:.2f} with {best.lexical_overlap:.0%} "
                    f"vocabulary overlap ({best.match_strength} match)."
                ),
                citations=(
                    [
                        CitationDraft(
                            citation_text=best.citation,
                            reference_kind="primary",
                            verified=True,
                            reliability="curated corpus",
                        )
                    ]
                    if identified and best.citation
                    else []
                ),
                payload={"match_strength": best.match_strength, "score": best.score},
            )
        )

        # The dating dispute, if the corpus records one, is often the most important
        # thing to surface — it governs whether a "prophecy" precedes its fulfilment.
        dating_note = best.metadata.get("dating_note")
        if dating_note:
            result.claims.append(
                self.make_claim(
                    section=Section.SOURCE_IDENTIFICATION,
                    claim_type=ClaimType.SCHOLARLY_INTERPRETATION,
                    statement=f"Dating of {best.title}: {dating_note}",
                    reasoning=(
                        "When a text is dated determines whether it could have been written "
                        "before or after the events it appears to describe. Any claim of "
                        "predictive fulfilment depends on this and nothing else."
                    ),
                    confidence=0.8,
                    confidence_basis="Recorded scholarly positions from the curated corpus.",
                    citations=[
                        CitationDraft(
                            citation_text=best.citation or best.title,
                            reference_kind="secondary",
                            verified=True,
                        )
                    ],
                )
            )

        for other in hits[1:4]:
            result.claims.append(
                self.make_claim(
                    section=Section.SOURCE_IDENTIFICATION,
                    claim_type=ClaimType.AI_HYPOTHESIS,
                    statement=f"Also considered: {other.title} (similarity {other.score:.2f}).",
                    confidence=min(other.score, 0.5),
                    confidence_basis="Lower-ranked retrieval candidate, listed for transparency.",
                )
            )

        result.reasoning_summary = (
            f"Retrieved {len(hits)} candidates from the reference corpus and graded them. "
            + (
                f"Identified the text as {best.title}."
                if identified
                else "No candidate was strong enough for a positive identification."
            )
        )
        return result


# ======================================================================================
# 3. Entities
# ======================================================================================


class EntityAgent(BaseAgent):
    name = "entities"
    description = "entity extraction"
    max_tokens = 6000

    SYSTEM = (
        SHARED_SYSTEM_RULES
        + """
You extract entities: people, places, empires, nations, religions, cultures, deities,
astronomical objects and phenomena, calendars, sacred numbers, symbols, prophecies and
historical events.

Separate two different confidences, because they are genuinely different questions:
  - extraction_confidence: how sure you are the text refers to this at all.
  - identification_confidence: how sure you are about WHICH specific referent it is.
"Babylon" in a text is near-certain as a mention and often genuinely ambiguous as a
referent — the city, the empire, or Rome under a cipher.
"""
    )

    def run(self, ctx: AnalysisContext) -> AgentResult:
        result = AgentResult(agent_name=self.name)

        # The deterministic lexicon always runs, so extraction has a floor that does not
        # depend on the model behaving well.
        from app.agents import offline_engine

        baseline = offline_engine.extract_entities(ctx.working_text)
        entities: dict[tuple[str, str], dict] = {
            (e["name"].lower(), e["entity_type"]): e for e in baseline["entities"]
        }

        model_data, response = self.ask(
            self.SYSTEM,
            f"""<task>extract_entities</task>
Extract every entity from the text.

<text>
{ctx.excerpt(10000)}
</text>

Reply with JSON:
{_json_shape({
    "entities": [{
        "name": "canonical name",
        "entity_type": "person | place | empire | nation | religion | culture | deity | "
                       "date | calendar | astronomical_object | constellation | planet | "
                       "star | comet | eclipse | meteor_shower | moon_phase | zodiac_sign | "
                       "sacred_number | symbol | prophecy | prediction | historical_event | "
                       "artifact | text_work | other",
        "description": "one or two sentences",
        "aliases": [],
        "extraction_confidence": 0.0,
        "identification_confidence": 0.0,
        "earliest_year": None,
        "latest_year": None,
        "ambiguity": "what else this could refer to, or null",
    }],
    "reasoning": "how you identified these",
})}""",
        )
        result.provider, result.model = response.provider, response.model

        model_entities = [] if self.unavailable(model_data) else model_data.get("entities", [])
        for entity in model_entities:
            name = str(entity.get("name", "")).strip()
            if not name:
                continue
            key = (name.lower(), entity.get("entity_type", "other"))
            if key in entities:
                # Lexicon hit confirmed by the model: keep the span information from the
                # lexicon and enrich it with the model's description.
                merged = entities[key]
                merged["description"] = entity.get("description") or merged.get("description")
                merged["aliases"] = entity.get("aliases", [])
                merged["identification_confidence"] = entity.get("identification_confidence")
                merged["ambiguity"] = entity.get("ambiguity")
                merged["earliest_year"] = entity.get("earliest_year") or merged.get("earliest_year")
                merged["latest_year"] = entity.get("latest_year") or merged.get("latest_year")
                merged["extraction_confidence"] = min(
                    0.98, float(merged.get("extraction_confidence", 0.7)) + 0.1
                )
                merged["corroborated"] = True
            else:
                entities[key] = {
                    "name": name,
                    "entity_type": entity.get("entity_type", "other"),
                    "description": entity.get("description"),
                    "aliases": entity.get("aliases", []),
                    "mention_count": 1,
                    "mentions": [],
                    "extraction_confidence": float(entity.get("extraction_confidence") or 0.5),
                    "identification_confidence": entity.get("identification_confidence"),
                    "ambiguity": entity.get("ambiguity"),
                    "earliest_year": entity.get("earliest_year"),
                    "latest_year": entity.get("latest_year"),
                    "corroborated": False,
                }

        result.entities = list(entities.values())
        ctx.entities = result.entities
        result.data["sacred_numbers"] = baseline["sacred_numbers"]
        result.data["prophecy_markers"] = baseline["prophecy_markers"]

        # Quoted spans are the only claim type that is beyond dispute, so record them.
        for number in baseline["sacred_numbers"][:12]:
            result.claims.append(
                self.make_claim(
                    section=Section.KEY_ENTITIES,
                    claim_type=ClaimType.SOURCE_TEXT,
                    statement=(
                        f"The text contains the number {number['number']} "
                        f"(as “{number['surface']}”)."
                    ),
                    quoted_text=number["surface"],
                    text_span=(number["start"], number["end"]),
                    confidence=1.0,
                    confidence_basis="Directly present in the submitted text.",
                )
            )
            result.claims.append(
                self.make_claim(
                    section=Section.SYMBOLISM,
                    claim_type=ClaimType.TRADITIONAL_INTERPRETATION,
                    statement=f"{number['number']}: {number['significance']}",
                    reasoning=(
                        "Traditional numerological significance. That a number carries "
                        "significance in a tradition does not establish that this text uses "
                        "it in that sense — many are ordinary counts."
                    ),
                    confidence=0.55,
                    confidence_basis="Widely attested traditional association.",
                )
            )

        for marker in baseline["prophecy_markers"][:10]:
            result.claims.append(
                self.make_claim(
                    section=Section.KEY_ENTITIES,
                    claim_type=ClaimType.TEXTUAL_ANALYSIS,
                    statement=f"{marker['marker']} present: “{marker['surface']}”.",
                    quoted_text=marker["surface"],
                    text_span=(marker["start"], marker["end"]),
                    confidence=0.85,
                    confidence_basis="Recognised prophetic formula matched in the text.",
                )
            )

        confirmed = sum(1 for e in result.entities if e.get("corroborated"))
        result.reasoning_summary = (
            f"Extracted {len(result.entities)} entities. The curated lexicon found "
            f"{len(baseline['entities'])} with exact text spans; "
            + (
                f"the language model corroborated {confirmed} of these and added "
                f"{len(result.entities) - len(baseline['entities'])} more."
                if model_entities
                else "no model was available, so this is lexicon coverage only and recall "
                "is limited to curated terms."
            )
        )
        return result


# ======================================================================================
# 4. Dates and calendars (deterministic)
# ======================================================================================


class CalendarAgent(BaseAgent):
    name = "calendar"
    description = "date extraction and calendar conversion"

    SYSTEM = SHARED_SYSTEM_RULES

    def run(self, ctx: AnalysisContext) -> AgentResult:
        """Entirely deterministic: date grammar plus the calendar engine.

        No language model is consulted. Calendar conversion is arithmetic, and a model
        would only introduce a way for the arithmetic to be wrong.
        """
        from app.agents import offline_engine

        result = AgentResult(agent_name=self.name, provider="deterministic", model="starcode-calendars/1.0")
        found = offline_engine.extract_dates(ctx.working_text)
        expressions = found["date_expressions"]
        ctx.dates = found

        converted: list[dict] = []
        for item in expressions:
            if not item.get("resolvable"):
                result.claims.append(
                    self.make_claim(
                        section=Section.CALENDAR_CONVERSION,
                        claim_type=ClaimType.UNCERTAIN,
                        statement=(
                            f"“{item['surface']}” cannot be converted to a Gregorian date."
                        ),
                        reasoning=item.get("blocker"),
                        confidence=0.9,
                        confidence_basis=(
                            "The obstacle is a property of the reference itself, not a "
                            "limitation of the engine."
                        ),
                        quoted_text=item["surface"],
                        text_span=(item["start"], item["end"]),
                        payload=item,
                    )
                )
                continue

            try:
                payload = self._convert(item)
            except Exception as exc:  # noqa: BLE001
                logger.warning("calendar.conversion_failed", surface=item["surface"], error=str(exc))
                continue
            if payload is None:
                continue

            converted.append(payload)
            gregorian = payload["gregorian_label"]
            caveat = payload.get("uncertainty_note")

            result.claims.append(
                self.make_claim(
                    section=Section.CALENDAR_CONVERSION,
                    claim_type=ClaimType.ASTRONOMICAL_CALCULATION,
                    statement=f"“{item['surface']}” converts to {gregorian}.",
                    reasoning=payload.get("reasoning"),
                    confidence=payload["confidence"],
                    confidence_basis=caveat or "Exact arithmetic conversion via Rata Die day count.",
                    engine="starcode-calendars/1.0",
                    algorithm_reference=(
                        "Dershowitz & Reingold, Calendrical Calculations (4th ed., CUP, 2018)"
                    ),
                    quoted_text=item["surface"],
                    text_span=(item["start"], item["end"]),
                    payload=payload,
                )
            )

        ctx.calendar = {"conversions": converted}
        result.data["conversions"] = converted
        result.data["expressions"] = expressions

        resolvable = sum(1 for e in expressions if e.get("resolvable"))
        result.reasoning_summary = (
            f"Found {len(expressions)} date expressions. {resolvable} were convertible to "
            f"absolute dates by calendar arithmetic; {len(expressions) - resolvable} were not, "
            "and each unconvertible one is reported with the specific reason (an unfixed "
            "regnal accession, a duration with no anchor, or a day and month with no year)."
        )
        return result

    def _convert(self, item: dict) -> dict | None:
        calendar_key = item.get("calendar")

        if calendar_key == "mayan_long_count":
            lc = item["long_count"]
            payload = cal.convert_mayan_long_count(*lc)
            gregorian = next(c for c in payload["conversions"] if c["system"] == "gregorian")
            alt = next(c for c in payload["conversions"] if c["system"] == "mayan_long_count")
            return {
                "input": item["surface"],
                "source_calendar": "mayan_long_count",
                "gregorian_label": gregorian["label"],
                "all_systems": payload["conversions"],
                "eras": payload.get("eras", {}),
                "confidence": 0.75,
                "uncertainty_note": alt.get("uncertainty_note"),
                "reasoning": (
                    "Long Count is a plain count of days from a fixed epoch, so the "
                    "arithmetic is exact. The uncertainty is entirely in the correlation "
                    "constant tying that epoch to our calendar; the GMT value 584283 is "
                    "used, and the 584285 alternative shifts the result by two days."
                ),
            }

        if calendar_key in ("julian", "olympiad"):
            year = item["astronomical_year"]
            rd = cal.to_rd("julian", year, 1, 1)
            payload = cal.convert_all(rd)
            span = cal.gregorian_range_for_year("julian", year)
            return {
                "input": item["surface"],
                "source_calendar": "julian",
                "gregorian_label": (
                    f"{span['gregorian_start']} – {span['gregorian_end']}"
                    if span
                    else str(year)
                ),
                "astronomical_year": year,
                "all_systems": payload["conversions"],
                "eras": payload.get("eras", {}),
                "confidence": 0.85 if calendar_key == "julian" else 0.6,
                "uncertainty_note": (
                    item.get("note")
                    or "Only a year was given, so the result is the Gregorian span that "
                    "Julian year covers, not a single day."
                ),
                "reasoning": (
                    "A bare year converts to a range rather than a date. The Julian and "
                    "Gregorian years do not align, so a Julian year always straddles two "
                    "Gregorian ones."
                ),
            }

        if calendar_key in ("islamic", "hebrew"):
            year = item["calendar_year"]
            span = cal.gregorian_range_for_year(calendar_key, year)
            if span is None:
                return None
            return {
                "input": item["surface"],
                "source_calendar": calendar_key,
                "gregorian_label": f"{span['gregorian_start']} – {span['gregorian_end']}",
                "calendar_year": year,
                "spans_gregorian_years": span["spans_gregorian_years"],
                "confidence": 0.7,
                "uncertainty_note": span["uncertainty_note"],
                "reasoning": (
                    f"Year {year} of the {calendar_key} calendar spans "
                    f"{span['day_count']} days across "
                    f"{len(span['spans_gregorian_years'])} Gregorian year(s)."
                ),
            }

        return None


# ======================================================================================
# 5. Astronomy (deterministic)
# ======================================================================================


class AstronomyAgent(BaseAgent):
    name = "astronomy"
    description = "astronomical correlation"

    SYSTEM = SHARED_SYSTEM_RULES

    def run(self, ctx: AnalysisContext) -> AgentResult:
        """Detects astronomical references, then computes what was actually in the sky.

        Deterministic throughout. The agent establishes what the text mentions and what
        the ephemeris says; it never concludes that a text *refers to* a computed event.
        That inference is offered separately, as a hypothesis, and only where a date in
        the text supports it.
        """
        from app.agents import offline_engine

        result = AgentResult(
            agent_name=self.name, provider="deterministic", model=astro.ENGINE_NAME
        )
        detected = offline_engine.detect_astronomical(ctx.working_text)
        references = detected["astronomical_references"]
        ctx.astronomy = {"references": references}

        if not references:
            result.reasoning_summary = (
                "No astronomical terms from the curated lexicon appear in this text."
            )
            result.claims.append(
                self.make_claim(
                    section=Section.ASTRONOMICAL_REFERENCES,
                    claim_type=ClaimType.TEXTUAL_ANALYSIS,
                    statement="No astronomical references were detected in this text.",
                    confidence=0.7,
                    confidence_basis=(
                        "Lexicon coverage is good for common terms but not exhaustive; an "
                        "unusual phrasing could be missed."
                    ),
                )
            )
            return result

        for reference in references:
            result.claims.append(
                self.make_claim(
                    section=Section.ASTRONOMICAL_REFERENCES,
                    claim_type=ClaimType.SOURCE_TEXT,
                    statement=(
                        f"The text refers to {reference['term']} "
                        f"(as “{reference['surface']}”)."
                    ),
                    reasoning=reference.get("description") or None,
                    quoted_text=reference["surface"],
                    text_span=(reference["start"], reference["end"]),
                    confidence=0.9,
                    confidence_basis="Term matched directly in the submitted text.",
                    payload=reference,
                )
            )

        # If a date was resolved, compute the real sky and offer correlations.
        candidate_years = self._candidate_years(ctx)
        computed: list[dict] = []

        for year, label in candidate_years[:3]:
            try:
                correlation = astro.correlate_date(year)
            except astro.AstronomyError as exc:
                logger.info("astronomy.out_of_range", year=year, error=str(exc))
                continue

            computed.append({"year": year, "label": label, "correlation": correlation})

            for eclipse in correlation.get("eclipses_in_year", [])[:6]:
                result.claims.append(
                    self.make_claim(
                        section=Section.ASTRONOMICAL_REFERENCES,
                        claim_type=ClaimType.ASTRONOMICAL_CALCULATION,
                        statement=(
                            f"{eclipse['label']} on {eclipse['gregorian_label']} "
                            f"(magnitude {eclipse['details'].get('magnitude')})."
                        ),
                        reasoning=(
                            f"Computed for {label}, a date derived from the text. This "
                            "establishes what occurred; it does not establish that the text "
                            "describes it."
                        ),
                        confidence=0.9,
                        confidence_basis=eclipse["accuracy_note"],
                        engine=astro.ENGINE_NAME,
                        algorithm_reference=eclipse["engine"],
                        payload=eclipse,
                    )
                )

            for comet in correlation["catalogue"]["comets"][:4]:
                result.claims.append(
                    self.make_claim(
                        section=Section.ASTRONOMICAL_REFERENCES,
                        claim_type=(
                            ClaimType.ASTRONOMICAL_CALCULATION
                            if comet["evidence"] in ("computed_return", "both")
                            else ClaimType.VERIFIED_HISTORY
                        ),
                        statement=f"{comet['name']}: {comet['perihelion_note']}.",
                        reasoning=(
                            "Within a few years of a date derived from the text."
                            + (
                                f" Historical records: {'; '.join(comet['records'])}."
                                if comet["records"]
                                else ""
                            )
                        ),
                        confidence=0.75,
                        confidence_basis=f"Evidence type: {comet['evidence']}.",
                        engine=astro.ENGINE_NAME if comet["evidence"] != "historical_record" else None,
                        algorithm_reference=comet["source"],
                        citations=[
                            CitationDraft(
                                citation_text=comet["source"],
                                reference_kind="secondary",
                                verified=True,
                            )
                        ],
                        payload=comet,
                    )
                )

        # Correlation is a hypothesis, and is stated as one.
        eclipse_terms = [r for r in references if r["category"] == "eclipse"]
        if eclipse_terms and computed:
            result.claims.append(
                self.make_claim(
                    section=Section.ALTERNATIVE_INTERPRETATIONS,
                    claim_type=ClaimType.AI_HYPOTHESIS,
                    statement=(
                        "The eclipse language in this text could correspond to one of the "
                        "computed eclipses listed above."
                    ),
                    reasoning=(
                        "Both an eclipse reference and a datable year are present, so a "
                        "correlation is possible. It is not established: eclipse imagery is "
                        "standard prophetic idiom across the ancient Near East and appears "
                        "in texts with no astronomical event behind them. Establishing a "
                        "real correlation needs the text to specify a date independently, "
                        "not merely to use the imagery."
                    ),
                    confidence=0.3,
                    confidence_basis=(
                        "Co-occurrence of a phenomenon term and a datable year. This is weak "
                        "evidence on its own."
                    ),
                )
            )
        elif eclipse_terms:
            result.claims.append(
                self.make_claim(
                    section=Section.ASTRONOMICAL_REFERENCES,
                    claim_type=ClaimType.UNCERTAIN,
                    statement=(
                        "The text uses eclipse imagery but supplies no date, so no specific "
                        "eclipse can be proposed."
                    ),
                    reasoning=(
                        "Without a date, any eclipse could be matched to the passage — and "
                        "over a few centuries there are thousands. A match found that way "
                        "carries no evidential weight."
                    ),
                    confidence=0.85,
                    confidence_basis="Absence of a datable anchor in the text.",
                )
            )

        result.data["computed"] = computed
        result.data["references"] = references
        ctx.astronomy["computed"] = computed

        result.reasoning_summary = (
            f"Detected {len(references)} astronomical references. "
            + (
                f"Computed the sky for {len(computed)} candidate year(s) derived from dates "
                "in the text, and listed eclipses and comets in those windows as "
                "calculations, keeping any correlation with the text explicitly separate."
                if computed
                else "No datable year was recoverable from the text, so no ephemeris "
                "correlation was attempted — matching imagery to an arbitrary date would "
                "produce a coincidence, not a finding."
            )
        )
        return result

    @staticmethod
    def _candidate_years(ctx: AnalysisContext) -> list[tuple[int, str]]:
        years: list[tuple[int, str]] = []
        for conversion in ctx.calendar.get("conversions", []):
            year = conversion.get("astronomical_year")
            if year is None:
                for entry in conversion.get("all_systems", []):
                    if entry["system"] == "gregorian":
                        year = entry["year"]
                        break
            if year is not None and -3000 <= year <= 3000:
                years.append((int(year), conversion["input"]))
        return years


# ======================================================================================
# 6. Historical context
# ======================================================================================


class HistoricalContextAgent(BaseAgent):
    name = "historical_context"
    description = "historical context"
    max_tokens = 6000

    SYSTEM = (
        SHARED_SYSTEM_RULES
        + """
You place a text in its historical setting: who wrote it, when, for whom, under what
political and religious conditions, and what a contemporary audience would have
understood by it.

Cite what you can. Where the setting is disputed — and for ancient texts it usually is —
give the competing reconstructions and what each rests on. Prefer "the majority view is
X, though Y is argued on the grounds of Z" to a flat assertion.
"""
    )

    def run(self, ctx: AnalysisContext) -> AgentResult:
        result = AgentResult(agent_name=self.name)

        corpus_context = "\n".join(
            f"- {hit['title']}: {hit['content'][:300]} [{hit['citation'] or 'no citation'}]"
            for hit in ctx.retrieved[:5]
        )
        entity_summary = ", ".join(
            f"{e['name']} ({e['entity_type']})" for e in ctx.entities[:25]
        )

        data, response = self.ask(
            self.SYSTEM,
            f"""<task>historical_context</task>
Place this text in historical context.

<text>
{ctx.excerpt(8000)}
</text>

Entities already extracted: {entity_summary or "none"}

Reference corpus material that may be relevant:
{corpus_context or "none retrieved"}

Reply with JSON:
{_json_shape({
    "period": "the historical period, with a date range",
    "setting": "political and religious situation",
    "audience": "who this was written for",
    "context_claims": [{
        "statement": "",
        "claim_type": "verified_history | scholarly_interpretation | ai_hypothesis | uncertain",
        "confidence": 0.0,
        "reasoning": "",
        "citation": "a real, checkable citation, or null if you have none",
    }],
    "disputes": [{"question": "", "positions": [{"view": "", "held_by": "", "basis": ""}]}],
    "timeline": [{"year": 0, "era": "BCE | CE", "event": "", "certainty": "attested | approximate | disputed"}],
    "reasoning": "how you reached this",
})}""",
        )
        result.provider, result.model = response.provider, response.model

        if self.unavailable(data):
            return self.offline_result(
                data, "Historical context could not be produced."
            )

        for item in data.get("context_claims", [])[:15]:
            citation = item.get("citation")
            claim_type = self._claim_type(item.get("claim_type"), bool(citation))
            result.claims.append(
                self.make_claim(
                    section=Section.HISTORICAL_CONTEXT,
                    claim_type=claim_type,
                    statement=item.get("statement", ""),
                    reasoning=item.get("reasoning"),
                    confidence=float(item.get("confidence") or 0.5),
                    confidence_basis="Assessed by the historical-context agent.",
                    citations=(
                        [
                            CitationDraft(
                                citation_text=citation,
                                reference_kind="secondary",
                                # Not from the curated corpus, so not verified. Models
                                # fabricate references, and an unverified one must look
                                # unverified.
                                verified=False,
                            )
                        ]
                        if citation
                        else []
                    ),
                )
            )

        for dispute in data.get("disputes", [])[:8]:
            positions = "; ".join(
                f"{p.get('view')} ({p.get('held_by', 'unattributed')}) — {p.get('basis', '')}"
                for p in dispute.get("positions", [])
            )
            result.claims.append(
                self.make_claim(
                    section=Section.SCHOLARLY_VIEWS,
                    claim_type=ClaimType.UNCERTAIN,
                    statement=f"Disputed: {dispute.get('question')}. Positions: {positions}",
                    reasoning=(
                        "Reported as an open question. The platform does not adjudicate "
                        "between scholarly positions."
                    ),
                    confidence=0.7,
                    confidence_basis="Presence of a documented scholarly disagreement.",
                )
            )

        ctx.history = data
        result.data = data
        result.reasoning_summary = data.get("reasoning") or (
            f"Placed the text in {data.get('period', 'an undetermined period')} and recorded "
            f"{len(data.get('disputes', []))} open scholarly questions."
        )
        return result

    @staticmethod
    def _claim_type(raw: str | None, has_citation: bool) -> ClaimType:
        try:
            claim_type = ClaimType(raw or "ai_hypothesis")
        except ValueError:
            claim_type = ClaimType.AI_HYPOTHESIS
        # The contract layer would downgrade this anyway; doing it here makes the
        # intent explicit at the point the decision is made.
        if claim_type in (ClaimType.VERIFIED_HISTORY, ClaimType.SCHOLARLY_INTERPRETATION):
            if not has_citation:
                return ClaimType.AI_HYPOTHESIS
        return claim_type


# ======================================================================================
# 7. Interpretation
# ======================================================================================


class InterpretationAgent(BaseAgent):
    name = "interpretation"
    description = "traditional, scholarly and alternative interpretations"
    max_tokens = 8000

    SYSTEM = (
        SHARED_SYSTEM_RULES
        + """
You report how a text has been understood. Three distinct categories, never merged:

  1. Traditional interpretations - what religious or cultural communities have held.
     Name the tradition and, where you can, the period. Report faithfully and
     respectfully, whether or not the reading is defensible historically.
  2. Scholarly interpretations - what academic study argues. Requires citation.
  3. Alternative interpretations - other readings, including your own, clearly marked
     as hypotheses.

You must also supply symbolic analysis: what the images, numbers and figures have been
taken to mean, and by whom.

Where a text is commonly read as predicting a specific modern event, say so — and also
say plainly what would have to be true for that reading to hold, and whether it is.
Do not mock the reading and do not endorse it.
"""
    )

    def run(self, ctx: AnalysisContext) -> AgentResult:
        result = AgentResult(agent_name=self.name)

        data, response = self.ask(
            self.SYSTEM,
            f"""<task>traditional_interpretation</task>
Analyse how this text has been and can be interpreted.

<text>
{ctx.excerpt(8000)}
</text>

Identified source: {ctx.source_identification.get('title', 'not identified')}
Historical period: {ctx.history.get('period', 'not established')}

Reply with JSON:
{_json_shape({
    "traditional": [{"tradition": "", "interpretation": "", "period": "", "confidence": 0.0}],
    "scholarly": [{"position": "", "argued_by": "", "basis": "", "citation": "", "confidence": 0.0}],
    "alternative": [{"reading": "", "supporting": "", "against": "", "confidence": 0.0}],
    "symbolism": [{"symbol": "", "meanings": [{"meaning": "", "tradition": ""}]}],
    "predictive_claims": [{
        "claim": "how this text is said to predict something",
        "held_by": "who reads it this way",
        "requires": "what must be true for this reading to work",
        "assessment": "whether those conditions hold, stated neutrally",
    }],
    "reasoning": "",
})}""",
        )
        result.provider, result.model = response.provider, response.model

        if self.unavailable(data):
            return self.offline_result(data, "Interpretive analysis could not be produced.")

        for item in data.get("traditional", [])[:12]:
            result.claims.append(
                self.make_claim(
                    section=Section.TRADITIONAL_INTERPRETATIONS,
                    claim_type=ClaimType.TRADITIONAL_INTERPRETATION,
                    statement=(
                        f"{item.get('tradition', 'A tradition')}: {item.get('interpretation', '')}"
                    ),
                    reasoning=(
                        f"Held within {item.get('tradition', 'this tradition')}"
                        + (f", {item['period']}" if item.get("period") else "")
                        + ". Reported as that tradition's position, not as an established fact."
                    ),
                    confidence=float(item.get("confidence") or 0.5),
                    confidence_basis="Confidence that the tradition holds this reading, not that it is correct.",
                )
            )

        for item in data.get("scholarly", [])[:12]:
            citation = item.get("citation")
            result.claims.append(
                self.make_claim(
                    section=Section.SCHOLARLY_VIEWS,
                    claim_type=(
                        ClaimType.SCHOLARLY_INTERPRETATION if citation else ClaimType.AI_HYPOTHESIS
                    ),
                    statement=item.get("position", ""),
                    reasoning=(
                        f"Argued by {item.get('argued_by', 'unattributed')}. "
                        f"Basis: {item.get('basis', 'not stated')}."
                    ),
                    confidence=float(item.get("confidence") or 0.5),
                    confidence_basis="Scholarly position as reported by the interpretation agent.",
                    citations=(
                        [CitationDraft(citation_text=citation, verified=False)]
                        if citation
                        else []
                    ),
                )
            )

        for item in data.get("alternative", [])[:10]:
            result.claims.append(
                self.make_claim(
                    section=Section.ALTERNATIVE_INTERPRETATIONS,
                    claim_type=ClaimType.AI_HYPOTHESIS,
                    statement=item.get("reading", ""),
                    reasoning=(
                        f"For: {item.get('supporting', 'not stated')}. "
                        f"Against: {item.get('against', 'not stated')}."
                    ),
                    confidence=float(item.get("confidence") or 0.35),
                    confidence_basis="Generated hypothesis; confidence capped by policy.",
                )
            )

        for item in data.get("symbolism", [])[:15]:
            meanings = item.get("meanings", [])
            rendered = "; ".join(
                f"{m.get('meaning')} ({m.get('tradition', 'unattributed')})" for m in meanings
            )
            result.claims.append(
                self.make_claim(
                    section=Section.SYMBOLISM,
                    claim_type=ClaimType.TRADITIONAL_INTERPRETATION,
                    statement=f"{item.get('symbol')}: {rendered}",
                    reasoning=(
                        "Symbolic associations attributed to named traditions. A symbol "
                        "carrying a meaning somewhere does not establish that this text "
                        "intends it."
                    ),
                    confidence=0.5,
                    confidence_basis="Attested symbolic associations.",
                )
            )

        for item in data.get("predictive_claims", [])[:8]:
            result.claims.append(
                self.make_claim(
                    section=Section.ALTERNATIVE_INTERPRETATIONS,
                    claim_type=ClaimType.TRADITIONAL_INTERPRETATION,
                    statement=(
                        f"{item.get('held_by', 'Some readers')} hold that {item.get('claim')}"
                    ),
                    reasoning=(
                        f"This reading requires: {item.get('requires', 'unstated conditions')}. "
                        f"Assessment: {item.get('assessment', 'not assessed')}."
                    ),
                    confidence=0.4,
                    confidence_basis=(
                        "Confidence that this interpretation is held, not that its "
                        "prediction is correct. The platform makes no claim about future events."
                    ),
                )
            )

        result.data = data
        result.reasoning_summary = data.get("reasoning") or (
            f"Reported {len(data.get('traditional', []))} traditional readings, "
            f"{len(data.get('scholarly', []))} scholarly positions and "
            f"{len(data.get('alternative', []))} alternative interpretations, each labelled "
            "by kind."
        )
        return result


# ======================================================================================
# 8. Evidence evaluation
# ======================================================================================


class EvidenceAgent(BaseAgent):
    name = "evidence"
    description = "evidence evaluation"
    max_tokens = 5000

    SYSTEM = (
        SHARED_SYSTEM_RULES
        + """
You audit an analysis. You are the last check before a user reads it.

Given the claims other agents produced, assess:
  - Which are genuinely supported, and by what.
  - Which are weaker than they are being made to sound.
  - What would change the picture if it were known.
  - Whether any claim crosses from evidence into speculation without saying so.

Be sceptical, including of the other agents. If an analysis rests mostly on conjecture,
say that clearly — that is the single most useful thing you can tell a reader.
"""
    )

    def run(self, ctx: AnalysisContext) -> AgentResult:
        result = AgentResult(agent_name=self.name)
        existing: list[dict] = ctx.options.get("_claims_for_review", [])

        summary_lines = [
            f"- [{c['claim_type']}] {c['statement'][:200]} (confidence {c['confidence']})"
            for c in existing[:60]
        ]

        data, response = self.ask(
            self.SYSTEM,
            f"""<task>evidence_evaluation</task>
Audit the following claims about a text.

Claims:
{chr(10).join(summary_lines) or "none"}

Reply with JSON:
{_json_shape({
    "assessment": "overall, in two or three sentences",
    "strongest_evidence": [{"claim": "", "why": ""}],
    "weakest_points": [{"claim": "", "why": "", "suggested_type": "the claim_type it should have"}],
    "what_would_change_this": ["evidence that would materially alter the conclusions"],
    "overconfidence_flags": ["claims stated more firmly than their support warrants"],
    "reasoning": "",
})}""",
        )
        result.provider, result.model = response.provider, response.model

        if self.unavailable(data):
            # The deterministic summary still says something true and useful.
            evidence_count = sum(
                1
                for c in existing
                if c["claim_type"]
                in ("source_text", "verified_history", "astronomical_calculation")
            )
            result.claims.append(
                self.make_claim(
                    section=Section.EVIDENCE,
                    claim_type=ClaimType.TEXTUAL_ANALYSIS,
                    statement=(
                        f"Of {len(existing)} claims, {evidence_count} are evidence-grade "
                        "(direct quotation, calculation, or cited history) and the remainder "
                        "are interpretation or hypothesis."
                    ),
                    reasoning=(
                        "Counted directly from claim types. Narrative evidence review was "
                        "unavailable in offline mode."
                    ),
                    confidence=1.0,
                    confidence_basis="Arithmetic over the claim set.",
                )
            )
            result.status = "succeeded"
            result.reasoning_summary = (
                "Produced a quantitative evidence breakdown. The narrative critique requires "
                "a language model and was skipped."
            )
            return result

        result.claims.append(
            self.make_claim(
                section=Section.EVIDENCE,
                claim_type=ClaimType.TEXTUAL_ANALYSIS,
                statement=data.get("assessment", ""),
                reasoning=data.get("reasoning"),
                confidence=0.7,
                confidence_basis="Meta-assessment of the analysis, not of the text.",
            )
        )

        for item in data.get("strongest_evidence", [])[:6]:
            result.claims.append(
                self.make_claim(
                    section=Section.EVIDENCE,
                    claim_type=ClaimType.TEXTUAL_ANALYSIS,
                    statement=f"Best supported: {item.get('claim')}",
                    reasoning=item.get("why"),
                    confidence=0.7,
                    confidence_basis="Evidence audit.",
                )
            )

        for item in data.get("weakest_points", [])[:8]:
            result.claims.append(
                self.make_claim(
                    section=Section.EVIDENCE,
                    claim_type=ClaimType.UNCERTAIN,
                    statement=f"Weak point: {item.get('claim')}",
                    reasoning=(
                        f"{item.get('why')} "
                        + (
                            f"Should arguably be typed as {item['suggested_type']}."
                            if item.get("suggested_type")
                            else ""
                        )
                    ),
                    confidence=0.6,
                    confidence_basis="Evidence audit.",
                )
            )

        for flag in data.get("overconfidence_flags", [])[:6]:
            result.claims.append(
                self.make_claim(
                    section=Section.CONFIDENCE_RATINGS,
                    claim_type=ClaimType.UNCERTAIN,
                    statement=f"Stated more firmly than the support warrants: {flag}",
                    confidence=0.6,
                    confidence_basis="Flagged during the evidence audit.",
                )
            )

        for item in data.get("what_would_change_this", [])[:6]:
            result.claims.append(
                self.make_claim(
                    section=Section.EVIDENCE,
                    claim_type=ClaimType.TEXTUAL_ANALYSIS,
                    statement=f"Would change these conclusions: {item}",
                    reasoning=(
                        "Naming what would falsify or revise a reading is the difference "
                        "between an argument and an assertion."
                    ),
                    confidence=0.65,
                    confidence_basis="Evidence audit.",
                )
            )

        result.data = data
        result.reasoning_summary = data.get("reasoning") or data.get("assessment", "")
        return result


ALL_AGENTS: list[type[BaseAgent]] = [
    LanguageAgent,
    SourceIdentificationAgent,
    EntityAgent,
    CalendarAgent,
    AstronomyAgent,
    HistoricalContextAgent,
    InterpretationAgent,
    EvidenceAgent,
]

__all__ = [
    "LanguageAgent",
    "SourceIdentificationAgent",
    "EntityAgent",
    "CalendarAgent",
    "AstronomyAgent",
    "HistoricalContextAgent",
    "InterpretationAgent",
    "EvidenceAgent",
    "ALL_AGENTS",
]
