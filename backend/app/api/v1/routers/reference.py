"""Reference-data endpoints: astronomy, calendars and the corpus.

These are directly useful on their own — a researcher can ask "what eclipses happened in
33 CE?" without submitting a text — and they power the sky map and calendar views.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DbSession, rate_limiter
from app.astronomy import catalogs
from app.astronomy import service as astro
from app.calendars import service as cal
from app.db.models.knowledge import AstronomicalEvent, HistoricalSource, SourcePassage

router = APIRouter(tags=["reference"])


# --------------------------------------------------------------------------------------
# Astronomy
# --------------------------------------------------------------------------------------

astronomy_router = APIRouter(
    prefix="/astronomy", tags=["astronomy"], dependencies=[Depends(rate_limiter("reference"))]
)


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except astro.AstronomyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@astronomy_router.get("/sky", summary="The sky on a given date")
def sky(
    year: int = Query(..., ge=-3000, le=3000, description="Astronomical year; 0 = 1 BCE"),
    month: int = Query(1, ge=1, le=12),
    day: int = Query(1, ge=1, le=31),
    hour_ut: float = Query(12.0, ge=0, le=24),
) -> dict:
    return _guard(astro.sky_on_date, year, month, day, hour_ut)


@astronomy_router.get("/eclipses", summary="Eclipses in a year range")
def eclipses(
    start_year: int = Query(..., ge=-3000, le=3000),
    end_year: int = Query(..., ge=-3000, le=3000),
    kind: str = Query("both", pattern="^(both|solar|lunar)$"),
) -> dict:
    return _guard(astro.eclipses, start_year, end_year, kind)


@astronomy_router.get("/eclipses/near", summary="Eclipses near a date")
def eclipses_near(
    year: int = Query(..., ge=-3000, le=3000),
    month: int = Query(1, ge=1, le=12),
    day: int = Query(1, ge=1, le=31),
    window_days: float = Query(400.0, gt=0, le=3650),
) -> dict:
    return _guard(astro.eclipses_around, year, month, day, window_days)


@astronomy_router.get("/moon-phases", summary="Lunar phases in a year range")
def moon_phases(
    start_year: int = Query(..., ge=-3000, le=3000),
    end_year: int = Query(..., ge=-3000, le=3000),
    phase: str | None = Query(None, pattern="^(new|first_quarter|full|last_quarter)$"),
) -> dict:
    return _guard(astro.moon_phases, start_year, end_year, phase)


@astronomy_router.get("/moon", summary="The Moon on a given date")
def moon(
    year: int = Query(..., ge=-3000, le=3000),
    month: int = Query(..., ge=1, le=12),
    day: int = Query(..., ge=1, le=31),
    hour_ut: float = Query(12.0, ge=0, le=24),
) -> dict:
    return _guard(astro.moon_on_date, year, month, day, hour_ut)


@astronomy_router.get("/seasons", summary="Equinoxes and solstices for a year")
def seasons(year: int = Query(..., ge=-3000, le=3000)) -> dict:
    return _guard(astro.seasons, year)


@astronomy_router.get("/conjunctions", summary="Planetary conjunctions in a year range")
def conjunctions(
    start_year: int = Query(..., ge=-3000, le=3000),
    end_year: int = Query(..., ge=-3000, le=3000),
    bodies: list[str] | None = Query(None),
    max_separation: float = Query(3.0, gt=0, le=30),
) -> dict:
    return _guard(astro.conjunctions, start_year, end_year, bodies, max_separation)


@astronomy_router.get("/positions", summary="Body positions on a date")
def positions(
    year: int = Query(..., ge=-3000, le=3000),
    month: int = Query(..., ge=1, le=12),
    day: int = Query(..., ge=1, le=31),
    hour_ut: float = Query(12.0, ge=0, le=24),
) -> dict:
    return _guard(astro.positions_on, year, month, day, hour_ut)


@astronomy_router.get("/catalogue", summary="Recorded comets, supernovae and meteor showers")
def catalogue(
    year: int | None = Query(None, ge=-3000, le=3000),
    month: int | None = Query(None, ge=1, le=12),
    day: int | None = Query(None, ge=1, le=31),
) -> dict:
    if year is None:
        return {
            "meteor_showers": [s.to_dict() for s in catalogs.METEOR_SHOWERS],
            "comets": [c.to_dict() for c in catalogs.COMET_APPARITIONS],
            "supernovae": catalogs.HISTORICAL_SUPERNOVAE,
        }
    return astro.catalogue_lookup(year, month, day)


@astronomy_router.get("/correlate", summary="Everything astronomical about a candidate date")
def correlate(
    year: int = Query(..., ge=-3000, le=3000),
    month: int | None = Query(None, ge=1, le=12),
    day: int | None = Query(None, ge=1, le=31),
) -> dict:
    return _guard(astro.correlate_date, year, month, day)


@astronomy_router.get("/engine", summary="Engine capabilities and accuracy")
def engine_info() -> dict:
    """What the engine can and cannot do, in the engine's own words."""
    return {
        "engine": astro.ENGINE_NAME,
        "range": {"start_year": -3000, "end_year": 3000},
        "limits": {
            "max_scan_years": astro.MAX_SCAN_YEARS,
            "max_conjunction_years": astro.MAX_CONJUNCTION_YEARS,
        },
        "models": [
            {
                "target": "Sun",
                "model": "Meeus ch. 25 (low accuracy)",
                "accuracy": "~0.01° in longitude",
            },
            {
                "target": "Moon",
                "model": "Meeus ch. 47 (abridged ELP-2000/82)",
                "accuracy": "~10 arcsec in longitude near the present epoch",
            },
            {
                "target": "Planets",
                "model": "JPL/Standish Keplerian approximation",
                "accuracy": "0.3–0.6° geocentric over 3000 BCE – 3000 CE",
            },
            {
                "target": "Eclipses",
                "model": "Meeus ch. 54",
                "accuracy": (
                    "Date reliable throughout the range; γ agrees with the NASA Five "
                    "Millennium Canon to ~0.0005 for modern eclipses and degrades for "
                    "ancient ones."
                ),
            },
        ],
        "known_limitations": [
            "No eclipse ground track is computed. Whether an eclipse was visible from a "
            "specific place is a separate question this engine does not answer.",
            "ΔT before the telescopic era is estimated from ancient eclipse records and is "
            "itself uncertain by minutes to hours; every result carries the resulting "
            "longitude uncertainty.",
            "Planetary positions are approximations. For a slow pair such as Jupiter and "
            "Saturn, the position error translates into roughly two weeks of uncertainty in "
            "the date of closest approach, which is reported with each conjunction.",
            "Zodiac signs and IAU constellations are both reported and will usually differ, "
            "because precession has moved them roughly a full sign apart since antiquity.",
        ],
        "verification": (
            "The engine reproduces Meeus' worked examples, the eclipse of Thales "
            "(28 May 585 BCE), the Assyrian Bur-Sagale eclipse (15 June 763 BCE) and the "
            "7 BCE Jupiter–Saturn triple conjunction in Pisces."
        ),
    }


# --------------------------------------------------------------------------------------
# Calendars
# --------------------------------------------------------------------------------------

calendar_router = APIRouter(
    prefix="/calendars", tags=["calendars"], dependencies=[Depends(rate_limiter("reference"))]
)


@calendar_router.get("", summary="Supported calendar systems")
def list_calendars() -> dict:
    return {"calendars": cal.list_calendars()}


@calendar_router.get("/convert", summary="Convert a date between calendar systems")
def convert(
    system: str = Query(..., description="Source calendar key"),
    year: int = Query(...),
    month: int = Query(1, ge=1, le=19),
    day: int = Query(1, ge=1, le=31),
) -> dict:
    try:
        return cal.convert(system, year, month, day)
    except cal.CalendarError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@calendar_router.get("/convert/maya", summary="Convert a Maya Long Count date")
def convert_maya(
    baktun: int = Query(..., ge=0, le=20),
    katun: int = Query(0, ge=0, le=19),
    tun: int = Query(0, ge=0, le=19),
    uinal: int = Query(0, ge=0, le=17),
    kin: int = Query(0, ge=0, le=19),
    correlation: int = Query(584283, ge=580000, le=590000),
) -> dict:
    return cal.convert_mayan_long_count(baktun, katun, tun, uinal, kin, correlation)


@calendar_router.get("/year-span", summary="The Gregorian span of one year of another calendar")
def year_span(
    system: str = Query(...),
    year: int = Query(...),
) -> dict:
    result = cal.gregorian_range_for_year(system, year)
    if result is None:
        raise HTTPException(
            status_code=400,
            detail=f"{system!r} does not support year-span conversion.",
        )
    return result


# --------------------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------------------

corpus_router = APIRouter(prefix="/corpus", tags=["corpus"])


@corpus_router.get("/sources", summary="Historical sources in the reference corpus")
def sources(
    db: DbSession,
    tradition: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    stmt = select(HistoricalSource).order_by(HistoricalSource.title)
    if tradition:
        stmt = stmt.where(HistoricalSource.tradition == tradition)
    rows = db.execute(stmt.limit(limit)).scalars().all()
    return {
        "total": len(rows),
        "disclosure": (
            "A curated demonstration corpus. Absence from it says nothing about a text."
        ),
        "sources": [
            {
                "id": row.id,
                "slug": row.slug,
                "title": row.title,
                "tradition": row.tradition,
                "language": row.language,
                "composition_earliest_year": row.composition_earliest_year,
                "composition_latest_year": row.composition_latest_year,
                "dating_note": row.dating_note,
                "description": row.description,
                "canonical_citation": row.canonical_citation,
                "reliability": row.reliability,
                "is_primary_source": row.is_primary_source,
            }
            for row in rows
        ],
    }


@corpus_router.get("/sources/{slug}", summary="One source and its passages")
def source_detail(slug: str, db: DbSession) -> dict:
    source = db.execute(
        select(HistoricalSource).where(HistoricalSource.slug == slug)
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="No such source in the corpus.")

    passages = db.execute(
        select(SourcePassage).where(SourcePassage.source_id == source.id)
    ).scalars().all()

    return {
        "source": {
            "id": source.id,
            "slug": source.slug,
            "title": source.title,
            "alternate_titles": source.alternate_titles,
            "tradition": source.tradition,
            "language": source.language,
            "script": source.script,
            "author": source.author,
            "composition_earliest_year": source.composition_earliest_year,
            "composition_latest_year": source.composition_latest_year,
            "dating_note": source.dating_note,
            "region": source.region,
            "description": source.description,
            "canonical_citation": source.canonical_citation,
            "license": source.license,
            "reliability": source.reliability,
        },
        "passages": [
            {
                "id": p.id,
                "reference_label": p.reference_label,
                "translation": p.translation,
                "translation_credit": p.translation_credit,
                "themes": p.themes,
                "astronomical_content": p.astronomical_content,
                "prophetic_content": p.prophetic_content,
                "scholarly_note": p.notes,
            }
            for p in passages
        ],
    }


@corpus_router.get("/events", summary="Astronomical events recorded in historical documents")
def recorded_events(
    db: DbSession,
    event_type: str | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    stmt = select(AstronomicalEvent).order_by(AstronomicalEvent.year)
    if event_type:
        stmt = stmt.where(AstronomicalEvent.event_type == event_type)
    if start_year is not None:
        stmt = stmt.where(AstronomicalEvent.year >= start_year)
    if end_year is not None:
        stmt = stmt.where(AstronomicalEvent.year <= end_year)

    rows = db.execute(stmt.limit(limit)).scalars().all()
    return {
        "total": len(rows),
        "note": (
            "`is_computed` distinguishes a calculated event from one attested in a "
            "document. Both are useful; they are not the same kind of evidence."
        ),
        "events": [
            {
                "id": row.id,
                "event_type": row.event_type,
                "designation": row.designation,
                "label": row.label,
                "year": row.year,
                "month": row.month,
                "day": row.day,
                "calendar_used": row.calendar_used,
                "is_computed": row.is_computed,
                "computation_engine": row.computation_engine,
                "description": row.description,
                "visibility_regions": row.visibility_regions,
                "attributes": row.attributes,
            }
            for row in rows
        ],
    }


@corpus_router.get("/claim-types", summary="The claim-type vocabulary")
def claim_types() -> dict:
    """The epistemic vocabulary, so any client renders the labels identically."""
    from app.agents.contracts import (
        CLAIM_TYPE_PRESENTATION,
        EVIDENCE_TYPES,
        REQUIRES_CITATION,
    )

    return {
        "claim_types": [
            {
                "value": claim_type.value,
                **presentation,
                "is_evidence": claim_type in EVIDENCE_TYPES,
                "requires_citation": claim_type in REQUIRES_CITATION,
            }
            for claim_type, presentation in CLAIM_TYPE_PRESENTATION.items()
        ],
        "rule": (
            "A claim requiring a citation cannot be stored without one — it is downgraded "
            "to an AI hypothesis instead. AI-hypothesis confidence is capped by policy."
        ),
    }


@corpus_router.get("/pipeline", summary="The analysis pipeline")
def pipeline() -> dict:
    from app.agents.orchestrator import pipeline_description
    from app.agents.provider import provider_status

    return {"agents": pipeline_description(), "provider": provider_status()}


router.include_router(astronomy_router)
router.include_router(calendar_router)
router.include_router(corpus_router)

__all__ = ["router"]
