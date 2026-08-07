"""The astronomy facade the rest of the platform talks to.

Every function here returns plain dictionaries carrying the engine name, the algorithm
reference and an accuracy statement, so that a claim built from one of them can be
labelled `astronomical_calculation` and audited later.
"""

from __future__ import annotations

from app.astronomy import catalogs, events
from app.astronomy.ephemeris import (
    NAKED_EYE_PLANETS,
    ZODIAC_SIGNS,
    body_position,
    is_retrograde,
    moon_illuminated_fraction,
    moon_phase_name,
)
from app.astronomy.timescales import (
    decimal_year_from_jd,
    jd_from_gregorian,
    time_uncertainty,
)
from app.calendars.core import gregorian_to_rd, rd_to_gregorian

ENGINE_NAME = "starcode-astronomy/1.0 (Meeus + JPL Keplerian)"

#: Guard rails. A user asking for "every eclipse from 4000 BCE to now" would otherwise
#: spin the CPU for minutes; the API surfaces this as a validation error, not a timeout.
MAX_SCAN_YEARS = 200
MAX_CONJUNCTION_YEARS = 50


class AstronomyError(ValueError):
    pass


def _guard_span(start_year: int, end_year: int, limit: int) -> None:
    if end_year < start_year:
        raise AstronomyError("end_year must not precede start_year")
    if end_year - start_year + 1 > limit:
        raise AstronomyError(
            f"Requested span of {end_year - start_year + 1} years exceeds the {limit}-year "
            "limit for this operation. Narrow the range, or run it as a background job."
        )
    if not (-3000 <= start_year <= 3000 and -3000 <= end_year <= 3000):
        raise AstronomyError(
            "The ephemeris models are only defensible between 3000 BCE and 3000 CE. "
            "Outside that window the engine declines rather than returning numbers it "
            "cannot stand behind."
        )


def sky_on_date(year: int, month: int = 1, day: int = 1, hour_ut: float = 12.0) -> dict:
    """Full description of the sky on a date: positions, phase, active showers."""
    jd = jd_from_gregorian(year, month, day, hour_ut)
    snapshot = events.sky_snapshot(jd)

    for entry in snapshot["bodies"]:
        entry["ecliptic_constellation"] = catalogs.ecliptic_constellation(
            entry["ecliptic_longitude"]
        )

    snapshot.update(
        {
            "engine": ENGINE_NAME,
            "date": {"year": year, "month": month, "day": day, "hour_ut": hour_ut},
            "active_meteor_showers": catalogs.showers_active_on(month, day),
            "sign_vs_constellation_note": (
                "Zodiac *signs* are twelve equal 30° divisions measured from the vernal "
                "equinox. Zodiac *constellations* are unequal regions of sky. Because of "
                "precession the two have drifted roughly a full sign apart since they were "
                "defined in antiquity, so both are reported and they will usually differ."
            ),
        }
    )
    return snapshot


def eclipses(start_year: int, end_year: int, kind: str = "both") -> dict:
    _guard_span(start_year, end_year, MAX_SCAN_YEARS)
    if kind not in ("both", "solar", "lunar"):
        raise AstronomyError("kind must be 'both', 'solar' or 'lunar'")
    found = events.eclipses_in_range(start_year, end_year, kind=kind)
    return {
        "engine": ENGINE_NAME,
        "query": {"start_year": start_year, "end_year": end_year, "kind": kind},
        "count": len(found),
        "events": [e.to_dict() for e in found],
    }


def eclipses_around(year: int, month: int = 1, day: int = 1, window_days: float = 400.0) -> dict:
    if window_days <= 0 or window_days > 3650:
        raise AstronomyError("window_days must be between 1 and 3650")
    jd = jd_from_gregorian(year, month, day)
    return {
        "engine": ENGINE_NAME,
        "target": {"year": year, "month": month, "day": day},
        "window_days": window_days,
        "events": events.eclipses_near(jd, window_days=window_days),
    }


def moon_phases(start_year: int, end_year: int, phase: str | None = None) -> dict:
    _guard_span(start_year, end_year, MAX_SCAN_YEARS)
    mapping = {"new": (0.0,), "first_quarter": (0.25,), "full": (0.5,), "last_quarter": (0.75,)}
    phases = mapping.get(phase or "", (0.0, 0.25, 0.5, 0.75))
    found = events.moon_phases_in_range(start_year, end_year, phases=phases)
    return {
        "engine": ENGINE_NAME,
        "query": {"start_year": start_year, "end_year": end_year, "phase": phase},
        "count": len(found),
        "events": [e.to_dict() for e in found],
    }


def moon_on_date(year: int, month: int, day: int, hour_ut: float = 12.0) -> dict:
    jd = jd_from_gregorian(year, month, day, hour_ut)
    position = body_position("Moon", jd)
    return {
        "engine": ENGINE_NAME,
        "phase_name": moon_phase_name(jd),
        "illuminated_fraction": round(moon_illuminated_fraction(jd), 4),
        "position": position.to_dict(),
        "ecliptic_constellation": catalogs.ecliptic_constellation(position.longitude),
        "note": (
            "Illumination and phase are geometric. Many ancient calendars began a month at "
            "the first visible crescent, typically one to two days after astronomical new "
            "moon and dependent on local horizon and weather."
        ),
    }


def seasons(year: int) -> dict:
    if not -3000 <= year <= 3000:
        raise AstronomyError("Year must be between 3000 BCE and 3000 CE")
    return {
        "engine": ENGINE_NAME,
        "year": year,
        "events": [e.to_dict() for e in events.seasons_for_year(year)],
    }


def conjunctions(
    start_year: int,
    end_year: int,
    bodies: list[str] | None = None,
    max_separation: float = 3.0,
) -> dict:
    _guard_span(start_year, end_year, MAX_CONJUNCTION_YEARS)
    if max_separation <= 0 or max_separation > 30:
        raise AstronomyError("max_separation must be between 0 and 30 degrees")
    selected = bodies or NAKED_EYE_PLANETS
    unknown = [b for b in selected if b.title() not in NAKED_EYE_PLANETS + ["Sun", "Moon"]]
    if unknown:
        raise AstronomyError(f"Unsupported bodies: {', '.join(unknown)}")

    found = events.find_conjunctions(
        start_year, end_year, bodies=[b.title() for b in selected], max_separation=max_separation
    )
    return {
        "engine": ENGINE_NAME,
        "query": {
            "start_year": start_year,
            "end_year": end_year,
            "bodies": selected,
            "max_separation": max_separation,
        },
        "count": len(found),
        "events": [e.to_dict() for e in found],
    }


def positions_on(year: int, month: int, day: int, hour_ut: float = 12.0) -> dict:
    jd = jd_from_gregorian(year, month, day, hour_ut)
    result = []
    for name in ["Sun", "Moon", *NAKED_EYE_PLANETS]:
        position = body_position(name, jd)
        entry = position.to_dict()
        entry["ecliptic_constellation"] = catalogs.ecliptic_constellation(position.longitude)
        if name not in ("Sun", "Moon"):
            entry["retrograde"] = is_retrograde(name, jd)
        result.append(entry)
    return {"engine": ENGINE_NAME, "julian_day": jd, "positions": result}


def catalogue_lookup(year: int, month: int | None = None, day: int | None = None) -> dict:
    """Historically attested events near a date — comets, supernovae, meteor showers."""
    return {
        "engine": ENGINE_NAME,
        "comets": catalogs.comets_near_year(year),
        "supernovae": catalogs.supernovae_near_year(year),
        "meteor_showers": (
            catalogs.showers_active_on(month, day) if month and day else
            [s.to_dict() for s in catalogs.METEOR_SHOWERS]
        ),
        "note": (
            "Comet and supernova entries distinguish computed returns from historical "
            "records. An entry marked 'historical_record' means a document describes "
            "something; identifying that description with a specific object is a separate, "
            "often contested, scholarly judgement."
        ),
    }


def correlate_date(year: int, month: int | None = None, day: int | None = None) -> dict:
    """Given a candidate date, gather every astronomical fact that might bear on a text.

    This is the workhorse the astronomy agent calls. It never decides what a text *means*;
    it establishes what was demonstrably in the sky.
    """
    has_day = month is not None and day is not None
    m, d = (month or 1), (day or 1)
    jd = jd_from_gregorian(year, m, d)

    payload: dict = {
        "engine": ENGINE_NAME,
        "input": {"year": year, "month": month, "day": day, "day_known": has_day},
        "time_uncertainty": time_uncertainty(year).to_dict(),
        "seasons": [e.to_dict() for e in events.seasons_for_year(year)],
        "catalogue": catalogue_lookup(year, month, day),
    }

    if has_day:
        payload["sky"] = sky_on_date(year, m, d)
        payload["eclipses_within_a_year"] = events.eclipses_near(jd, window_days=370)
        payload["nearest_new_moon"] = events.nearest_new_moon(jd).to_dict()
    else:
        payload["eclipses_in_year"] = [
            e.to_dict() for e in events.eclipses_in_range(year, year)
        ]
        payload["note"] = (
            "Only a year was supplied, so day-specific results (positions, phase) are "
            "omitted rather than computed for an arbitrary 1 January."
        )

    return payload


def zodiac_sign_for_longitude(longitude: float) -> dict:
    sign = ZODIAC_SIGNS[int(longitude % 360 // 30)]
    return {
        "tropical_sign": sign,
        "degrees_in_sign": round(longitude % 30, 2),
        "iau_constellation": catalogs.ecliptic_constellation(longitude),
    }


def gregorian_from_rd_tuple(rd: int) -> tuple[int, int, int]:
    return rd_to_gregorian(rd)


def rd_from_gregorian_tuple(year: int, month: int, day: int) -> int:
    return gregorian_to_rd(year, month, day)


def julian_day_for(year: int, month: int, day: int, hour_ut: float = 12.0) -> float:
    return jd_from_gregorian(year, month, day, hour_ut)


def year_from_julian_day(jd: float) -> float:
    return decimal_year_from_jd(jd)


__all__ = [
    "ENGINE_NAME",
    "AstronomyError",
    "sky_on_date",
    "eclipses",
    "eclipses_around",
    "moon_phases",
    "moon_on_date",
    "seasons",
    "conjunctions",
    "positions_on",
    "catalogue_lookup",
    "correlate_date",
    "zodiac_sign_for_longitude",
    "julian_day_for",
    "year_from_julian_day",
]
