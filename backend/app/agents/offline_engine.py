"""The deterministic engine behind :class:`~app.agents.provider.OfflineProvider`.

It answers the same structured prompts the agents send to a language model, using rules
rather than inference. It is genuinely useful for the mechanical tasks — script and
language detection, entity extraction, date parsing, numerology lookup — and it is
explicitly and visibly *unable* to do the interpretive ones. Where a task requires
synthesis, it returns ``{"offline_unavailable": true}`` with a reason, and the calling
agent reports the gap rather than inventing filler.

That refusal is the point. A rule engine that produced plausible-sounding "traditional
interpretations" would be exactly the failure this platform exists to prevent.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.agents import lexicon

_TEXT_BLOCK = re.compile(r"<text>\s*(.*?)\s*</text>", re.DOTALL)


def _payload_text(prompt: str) -> str:
    match = _TEXT_BLOCK.search(prompt)
    return match.group(1) if match else prompt


def handle(task: str, prompt: str) -> dict[str, Any]:
    handler = _HANDLERS.get(task)
    if handler is None:
        return _unavailable(f"the offline engine has no handler for task {task!r}")
    return handler(_payload_text(prompt), prompt)


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "offline_unavailable": True,
        "reason": reason,
        "note": (
            "This section requires open-ended reasoning that the deterministic offline "
            "engine cannot perform. Configure ANTHROPIC_API_KEY to enable it. The section "
            "is reported as unavailable rather than filled with generated-looking text."
        ),
    }


# --------------------------------------------------------------------------------------
# Script and language detection
# --------------------------------------------------------------------------------------

_SCRIPT_RANGES: list[tuple[str, tuple[int, int]]] = [
    ("Hebrew", (0x0590, 0x05FF)),
    ("Arabic", (0x0600, 0x06FF)),
    ("Syriac", (0x0700, 0x074F)),
    ("Devanagari", (0x0900, 0x097F)),
    ("Greek", (0x0370, 0x03FF)),
    ("Coptic", (0x2C80, 0x2CFF)),
    ("Cyrillic", (0x0400, 0x04FF)),
    ("Ethiopic", (0x1200, 0x137F)),
    ("Han", (0x4E00, 0x9FFF)),
    ("Hiragana", (0x3040, 0x309F)),
    ("Katakana", (0x30A0, 0x30FF)),
    ("Hangul", (0xAC00, 0xD7AF)),
    ("Cuneiform", (0x12000, 0x123FF)),
    ("Egyptian Hieroglyphs", (0x13000, 0x1342F)),
]

_SCRIPT_LANGUAGE = {
    "Hebrew": ("he", "Hebrew"),
    "Arabic": ("ar", "Arabic"),
    "Syriac": ("syc", "Syriac"),
    "Devanagari": ("sa", "Sanskrit or Hindi"),
    "Greek": ("el", "Greek (Ancient or Modern)"),
    "Coptic": ("cop", "Coptic"),
    "Cyrillic": ("ru", "a Cyrillic-script language"),
    "Ethiopic": ("gez", "Ge'ez or Amharic"),
    "Han": ("zh", "Chinese"),
    "Hiragana": ("ja", "Japanese"),
    "Katakana": ("ja", "Japanese"),
    "Hangul": ("ko", "Korean"),
    "Cuneiform": ("akk", "Akkadian or Sumerian (cuneiform)"),
    "Egyptian Hieroglyphs": ("egy", "Ancient Egyptian"),
}

#: Function-word profiles. Crude but effective for the Latin-script languages this
#: corpus actually contains, and honest about its own confidence.
_LATIN_PROFILES: dict[str, tuple[str, set[str]]] = {
    "en": ("English", {"the", "and", "of", "to", "that", "shall", "unto", "which", "with", "was"}),
    "la": ("Latin", {"et", "in", "est", "non", "cum", "qui", "quod", "ad", "sed", "ut"}),
    "fr": ("French", {"le", "la", "les", "de", "et", "que", "qui", "dans", "pour", "sera"}),
    "es": ("Spanish", {"el", "la", "los", "de", "que", "en", "por", "para", "con", "sera"}),
    "de": ("German", {"der", "die", "das", "und", "ist", "nicht", "von", "mit", "den", "wird"}),
    "it": ("Italian", {"il", "la", "di", "che", "non", "per", "con", "sono", "nel", "una"}),
    "pt": ("Portuguese", {"o", "de", "que", "para", "com", "nao", "uma", "dos", "por", "sera"}),
}

#: Early Modern English markers. Distinguishing KJV-register English from modern English
#: matters: it is a strong signal about which translation, and therefore which source.
_ARCHAIC_MARKERS = {
    "thee", "thou", "thy", "thine", "ye", "hath", "doth", "saith", "unto", "shalt",
    "wilt", "cometh", "behold", "verily", "whosoever", "thereof", "wherefore",
}


def _detect_script(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for char in text:
        if not char.isalpha():
            continue
        code = ord(char)
        if code < 0x0250:
            counts["Latin"] = counts.get("Latin", 0) + 1
            continue
        for name, (low, high) in _SCRIPT_RANGES:
            if low <= code <= high:
                counts[name] = counts.get(name, 0) + 1
                break
    if not counts:
        return "Unknown", counts
    return max(counts, key=lambda k: counts[k]), counts


def detect_language(text: str, _prompt: str = "") -> dict[str, Any]:
    script, script_counts = _detect_script(text)
    total = sum(script_counts.values()) or 1

    if script != "Latin" and script in _SCRIPT_LANGUAGE:
        code, name = _SCRIPT_LANGUAGE[script]
        share = script_counts.get(script, 0) / total
        return {
            "language_code": code,
            "language_name": name,
            "script": script,
            "confidence": round(min(0.9, 0.5 + share * 0.45), 3),
            "needs_translation": True,
            "method": "unicode script range",
            "script_distribution": script_counts,
            "reasoning": (
                f"{share:.0%} of the letters fall in the {script} Unicode block. Script "
                "identification is reliable; the specific language and historical period "
                "within that script are not determined by this method."
            ),
        }

    tokens = re.findall(r"[a-z']+", text.lower())
    token_set = set(tokens)
    scores = {
        code: len(token_set & words) / max(1, len(words))
        for code, (_, words) in _LATIN_PROFILES.items()
    }
    best = max(scores, key=lambda k: scores[k]) if scores else "en"
    best_score = scores.get(best, 0.0)

    archaic_hits = token_set & _ARCHAIC_MARKERS
    register = None
    if best == "en" and len(archaic_hits) >= 2:
        register = "Early Modern English (King James register)"

    if best_score < 0.15:
        return {
            "language_code": "und",
            "language_name": "Undetermined (Latin script)",
            "script": "Latin",
            "confidence": 0.25,
            "needs_translation": False,
            "method": "function-word profile",
            "reasoning": (
                "The text is in Latin script but matched no function-word profile "
                "strongly. It may be a language the offline engine does not profile, a "
                "transliteration, or too short to classify."
            ),
        }

    code, name = best, _LATIN_PROFILES[best][0]
    return {
        "language_code": code,
        "language_name": name,
        "script": "Latin",
        "confidence": round(min(0.92, 0.4 + best_score * 2.0), 3),
        "needs_translation": code != "en",
        "register": register,
        "archaic_markers": sorted(archaic_hits)[:10],
        "method": "function-word profile",
        "reasoning": (
            f"Matched {int(best_score * len(_LATIN_PROFILES[best][1]))} of "
            f"{len(_LATIN_PROFILES[best][1])} {name} function words."
            + (
                f" Archaic forms ({', '.join(sorted(archaic_hits)[:4])}) indicate {register}."
                if register
                else ""
            )
        ),
    }


# --------------------------------------------------------------------------------------
# Entity extraction
# --------------------------------------------------------------------------------------


def extract_entities(text: str, _prompt: str = "") -> dict[str, Any]:
    matches = lexicon.find_entities(text)

    grouped: dict[tuple[str, str], dict] = {}
    for match in matches:
        key = (match.entry.canonical, match.entry.entity_type.value)
        entry = grouped.setdefault(
            key,
            {
                "name": match.entry.canonical,
                "entity_type": match.entry.entity_type.value,
                "description": match.entry.description,
                "mentions": [],
                "attributes": dict(match.entry.attributes or {}),
            },
        )
        entry["mentions"].append(
            {"surface": match.surface, "start": match.start, "end": match.end}
        )

    entities = []
    for entry in grouped.values():
        count = len(entry["mentions"])
        entry["mention_count"] = count
        # A term appearing once may be incidental; repeated use is stronger evidence that
        # the text is really about it.
        entry["extraction_confidence"] = round(min(0.95, 0.6 + 0.1 * (count - 1)), 3)
        attributes = entry.get("attributes") or {}
        entry["earliest_year"] = attributes.get("earliest_year")
        entry["latest_year"] = attributes.get("latest_year")
        entities.append(entry)

    numbers = lexicon.find_sacred_numbers(text)
    for number in numbers:
        entities.append(
            {
                "name": number["number"],
                "entity_type": "sacred_number",
                "description": number["significance"],
                "mention_count": 1,
                "extraction_confidence": 0.9,
                "mentions": [
                    {
                        "surface": number["surface"],
                        "start": number["start"],
                        "end": number["end"],
                    }
                ],
                "attributes": {"form": number.get("form")},
            }
        )

    markers = lexicon.find_prophecy_markers(text)
    for marker in markers:
        entities.append(
            {
                "name": marker["marker"],
                "entity_type": "prophecy",
                "description": f"Prophetic formula: “{marker['surface']}”",
                "mention_count": 1,
                "extraction_confidence": 0.85,
                "mentions": [
                    {
                        "surface": marker["surface"],
                        "start": marker["start"],
                        "end": marker["end"],
                    }
                ],
                "attributes": {},
            }
        )

    entities.sort(key=lambda e: (-e["mention_count"], e["name"]))

    return {
        "entities": entities,
        "sacred_numbers": numbers,
        "prophecy_markers": markers,
        "method": "curated lexicon and regular expressions",
        "reasoning": (
            f"Matched {len(matches)} lexicon terms, {len(numbers)} numbers with recognised "
            f"traditional significance, and {len(markers)} prophetic formulae. This method "
            "has high precision but bounded recall: entities outside the curated lexicon — "
            "unusual place names, minor figures, uncommon transliterations — will be missed."
        ),
    }


# --------------------------------------------------------------------------------------
# Date extraction
# --------------------------------------------------------------------------------------


def extract_dates(text: str, _prompt: str = "") -> dict[str, Any]:
    raw = lexicon.find_date_expressions(text)

    candidates: list[dict] = []
    for item in raw:
        entry: dict[str, Any] = {
            "surface": item["surface"],
            "kind": item["kind"],
            "start": item["start"],
            "end": item["end"],
            "groups": item["groups"],
            "resolvable": False,
        }

        if item["kind"] == "bce_year" and item["groups"]:
            entry.update(
                resolvable=True,
                calendar="julian",
                astronomical_year=1 - int(item["groups"][0]),
                precision="year",
            )
        elif item["kind"] == "ce_year" and item["groups"]:
            entry.update(
                resolvable=True,
                calendar="julian",
                astronomical_year=int(item["groups"][0]),
                precision="year",
            )
        elif item["kind"] == "hijri_year" and item["groups"]:
            entry.update(
                resolvable=True, calendar="islamic",
                calendar_year=int(item["groups"][0]), precision="year",
            )
        elif item["kind"] == "anno_mundi" and item["groups"]:
            entry.update(
                resolvable=True, calendar="hebrew",
                calendar_year=int(item["groups"][0]), precision="year",
            )
        elif item["kind"] == "maya_long_count" and len(item["groups"]) == 5:
            entry.update(
                resolvable=True,
                calendar="mayan_long_count",
                long_count=[int(g) for g in item["groups"]],
                precision="day",
            )
        elif item["kind"] in ("regnal_year", "regnal_year_spelled"):
            ordinal = item["groups"][0] if item["groups"] else None
            year_number = (
                lexicon.ORDINAL_WORDS.get(str(ordinal).lower())
                if item["kind"] == "regnal_year_spelled"
                else int(ordinal) if ordinal and str(ordinal).isdigit() else None
            )
            entry.update(
                resolvable=False,
                regnal_year=year_number,
                ruler=item["groups"][1] if len(item["groups"]) > 1 else None,
                precision="year",
                blocker=(
                    "A regnal year is only convertible once the ruler's accession date is "
                    "fixed, and accession dates for ancient rulers are frequently disputed "
                    "by years. Resolving this requires a chronology decision the engine "
                    "will not make silently."
                ),
            )
        elif item["kind"] in ("duration_years", "duration_days"):
            entry.update(
                resolvable=False,
                duration=int(item["groups"][0]) if item["groups"] else None,
                unit="years" if item["kind"] == "duration_years" else "days",
                blocker="A duration has no anchor date, so it cannot be placed on a timeline.",
            )
        elif item["kind"] == "olympiad" and item["groups"]:
            olympiad = int(item["groups"][0])
            entry.update(
                resolvable=True,
                calendar="olympiad",
                astronomical_year=-775 + (olympiad - 1) * 4,
                precision="four-year period",
                note="Olympiad years begin in midsummer, so each maps onto two Julian years.",
            )
        elif item["kind"] in ("day_month", "spelled_day_month"):
            entry.update(
                resolvable=False,
                day=(
                    lexicon.ORDINAL_WORDS.get(str(item["groups"][0]).lower())
                    if item["kind"] == "spelled_day_month"
                    else int(item["groups"][0]) if item["groups"][0].isdigit() else None
                ),
                month_name=item["groups"][1] if len(item["groups"]) > 1 else None,
                blocker="A day and month with no year cannot be placed on an absolute timeline.",
            )

        candidates.append(entry)

    return {
        "date_expressions": candidates,
        "method": "regular-expression date grammar",
        "reasoning": (
            f"Found {len(candidates)} date expressions, of which "
            f"{sum(1 for c in candidates if c['resolvable'])} can be converted to an "
            "absolute calendar date without further assumptions. The remainder are regnal "
            "years, bare durations or day-month references whose blockers are stated "
            "individually."
        ),
    }


# --------------------------------------------------------------------------------------
# Astronomical reference detection
# --------------------------------------------------------------------------------------


def detect_astronomical(text: str, _prompt: str = "") -> dict[str, Any]:
    matches = lexicon.find_entities(text)
    astro_types = {
        "astronomical_object", "planet", "star", "constellation", "comet",
        "eclipse", "meteor_shower", "moon_phase", "zodiac_sign",
    }

    references: list[dict] = []
    for match in matches:
        if match.entry.entity_type.value not in astro_types:
            continue
        attributes = match.entry.attributes or {}
        references.append(
            {
                "term": match.entry.canonical,
                "category": match.entry.entity_type.value,
                "surface": match.surface,
                "start": match.start,
                "end": match.end,
                "body": attributes.get("body"),
                "event_type": attributes.get("event_type"),
                "phase": attributes.get("phase"),
                "description": match.entry.description,
            }
        )

    return {
        "astronomical_references": references,
        "method": "curated astronomical lexicon",
        "reasoning": (
            f"Identified {len(references)} astronomical references by term matching. "
            "Detecting that a text mentions a phenomenon is not the same as establishing "
            "that it describes a specific historical occurrence of it — that judgement is "
            "left to the astronomy agent and reported separately."
        ),
    }


# --------------------------------------------------------------------------------------
# Source identification
# --------------------------------------------------------------------------------------


def identify_source(text: str, prompt: str) -> dict[str, Any]:
    """Source identification runs on retrieval, which the orchestrator has already done;
    the candidates arrive in the prompt. The offline engine's job is to grade them."""
    candidates: list[dict] = []
    for block in re.finditer(
        r"<candidate>\s*(.*?)\s*</candidate>", prompt, re.DOTALL
    ):
        body = block.group(1)
        title = re.search(r"title:\s*(.+)", body)
        score = re.search(r"score:\s*([\d.]+)", body)
        strength = re.search(r"strength:\s*(\w+)", body)
        citation = re.search(r"citation:\s*(.+)", body)
        if title:
            candidates.append(
                {
                    "title": title.group(1).strip(),
                    "score": float(score.group(1)) if score else 0.0,
                    "match_strength": strength.group(1) if strength else "weak",
                    "citation": citation.group(1).strip() if citation else None,
                }
            )

    if not candidates:
        return {
            "identified": False,
            "candidates": [],
            "reasoning": (
                "No corpus entry matched this text above the retrieval floor. That means "
                "the text is not in the seed corpus — not that it is unknown or unusual. "
                "The corpus is a demonstration set of a few dozen works."
            ),
        }

    best = max(candidates, key=lambda c: c["score"])
    identified = best["match_strength"] == "strong"
    return {
        "identified": identified,
        "best_match": best if identified else None,
        "candidates": sorted(candidates, key=lambda c: -c["score"])[:5],
        "confidence": round(min(0.85, best["score"]), 3),
        "reasoning": (
            f"Best corpus match is “{best['title']}” at similarity {best['score']:.2f} "
            f"({best['match_strength']}). "
            + (
                "Similarity is high enough, and vocabulary overlap sufficient, to treat this "
                "as an identification."
                if identified
                else "Similarity is below the threshold for a positive identification, so "
                "this is reported as a lead to check rather than an answer."
            )
        ),
    }


# --------------------------------------------------------------------------------------
# Interpretive tasks the offline engine will not fake
# --------------------------------------------------------------------------------------


def _refuse(reason: str):
    def handler(_text: str, _prompt: str) -> dict[str, Any]:
        return _unavailable(reason)

    return handler


_HANDLERS = {
    "detect_language": detect_language,
    "extract_entities": extract_entities,
    "extract_dates": extract_dates,
    "detect_astronomical": detect_astronomical,
    "identify_source": identify_source,
    "translate": _refuse("translation requires a language model"),
    "historical_context": _refuse(
        "placing a text in historical context requires synthesis across sources"
    ),
    "traditional_interpretation": _refuse(
        "reporting what traditions have held requires knowledge beyond the seed corpus"
    ),
    "scholarly_views": _refuse(
        "summarising scholarly positions requires knowledge beyond the seed corpus"
    ),
    "alternative_interpretations": _refuse(
        "generating alternative readings requires open-ended reasoning"
    ),
    "symbolism": _refuse("symbolic analysis requires interpretation, not term matching"),
    "executive_summary": _refuse("summary prose requires a language model"),
    "evidence_evaluation": _refuse("weighing evidence requires judgement"),
}


def normalize_for_comparison(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower().strip()


__all__ = ["handle", "detect_language", "extract_entities", "extract_dates",
           "detect_astronomical", "identify_source"]
