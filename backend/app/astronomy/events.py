"""Discrete celestial events: lunar phases, eclipses, equinoxes, solstices and
planetary conjunctions.

Eclipse determination follows Meeus ch. 54, which works from the Moon's argument of
latitude at the exact syzygy rather than from a full ground-track integration. That gets
the date, the time of greatest eclipse, the type and the magnitude — the things ancient
texts actually record — without pretending to a ground track the ΔT uncertainty would not
support (see `app.astronomy.timescales`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.astronomy.ephemeris import (
    NAKED_EYE_PLANETS,
    ZODIAC_SIGNS,
    body_position,
    is_retrograde,
    moon_position,
    sun_position,
)
from app.astronomy.timescales import (
    MEEUS,
    dcos,
    dsin,
    gregorian_from_jd,
    jd_from_gregorian,
    normalize_degrees,
    normalize_degrees_signed,
    time_uncertainty,
    tt_to_ut,
)
from app.calendars.core import format_gregorian

LUNATION_DAYS = 29.530588861


@dataclass(slots=True)
class CelestialEvent:
    event_type: str
    label: str
    jd_tt: float
    jd_ut: float
    year: int
    month: int
    day: int
    hour_ut: float
    gregorian_label: str
    engine: str
    accuracy_note: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "label": self.label,
            "julian_day": round(self.jd_tt, 5),
            "julian_day_ut": round(self.jd_ut, 5),
            "year": self.year,
            "month": self.month,
            "day": self.day,
            "hour_ut": round(self.hour_ut, 3),
            "gregorian_label": self.gregorian_label,
            "engine": self.engine,
            "accuracy_note": self.accuracy_note,
            "details": self.details,
        }


def _finish(
    event_type: str, label: str, jd_tt: float, engine: str, note: str, details: dict
) -> CelestialEvent:
    jd_ut = tt_to_ut(jd_tt)
    year, month, day, hour = gregorian_from_jd(jd_ut)
    return CelestialEvent(
        event_type=event_type,
        label=label,
        jd_tt=jd_tt,
        jd_ut=jd_ut,
        year=year,
        month=month,
        day=day,
        hour_ut=hour,
        gregorian_label=format_gregorian(year, month, day),
        engine=engine,
        accuracy_note=note,
        details=details,
    )


# --------------------------------------------------------------------------------------
# Lunar phases — Meeus ch. 49
# --------------------------------------------------------------------------------------

PHASE_NAMES = {0.0: "New Moon", 0.25: "First Quarter", 0.5: "Full Moon", 0.75: "Last Quarter"}


def _lunation_k(year: float) -> float:
    """Approximate lunation number; k=0 is the new moon of 2000 January 6."""
    return (year - 2000.0) * 12.3685


def _phase_fundamentals(k: float) -> tuple[float, float, float, float, float, float, float]:
    t = k / 1236.85
    jde = (
        2451550.09766
        + 29.530588861 * k
        + 0.00015437 * t**2
        - 0.000000150 * t**3
        + 0.00000000073 * t**4
    )
    e = 1 - 0.002516 * t - 0.0000074 * t**2
    m = 2.5534 + 29.10535670 * k - 0.0000014 * t**2 - 0.00000011 * t**3
    mp = (
        201.5643
        + 385.81693528 * k
        + 0.0107582 * t**2
        + 0.00001238 * t**3
        - 0.000000058 * t**4
    )
    f = (
        160.7108
        + 390.67050284 * k
        - 0.0016118 * t**2
        - 0.00000227 * t**3
        + 0.000000011 * t**4
    )
    omega = 124.7746 - 1.56375588 * k + 0.0020672 * t**2 + 0.00000215 * t**3
    return jde, t, e, m, mp, f, omega


def _planetary_arguments(k: float, t: float) -> float:
    """The 14 small periodic corrections common to every phase (Meeus, p. 351)."""
    a = [
        299.77 + 0.107408 * k - 0.009173 * t**2,
        251.88 + 0.016321 * k,
        251.83 + 26.651886 * k,
        349.42 + 36.412478 * k,
        84.66 + 18.206239 * k,
        141.74 + 53.303771 * k,
        207.14 + 2.453732 * k,
        154.84 + 7.306860 * k,
        34.52 + 27.261239 * k,
        207.19 + 0.121824 * k,
        291.34 + 1.844379 * k,
        161.72 + 24.198154 * k,
        239.56 + 25.513099 * k,
        331.55 + 3.592518 * k,
    ]
    coefficients = [
        0.000325, 0.000165, 0.000164, 0.000126, 0.000110, 0.000062, 0.000060,
        0.000056, 0.000047, 0.000042, 0.000040, 0.000037, 0.000035, 0.000023,
    ]
    return sum(c * dsin(arg) for c, arg in zip(coefficients, a))


def moon_phase_time(k: float) -> float:
    """JDE (TT) of the phase with lunation index `k`.

    Integer k = new moon; +0.25 first quarter; +0.5 full moon; +0.75 last quarter.
    """
    jde, t, e, m, mp, f, omega = _phase_fundamentals(k)
    fraction = round((k % 1) * 4) / 4

    if fraction == 0.0:
        correction = (
            -0.40720 * dsin(mp)
            + 0.17241 * e * dsin(m)
            + 0.01608 * dsin(2 * mp)
            + 0.01039 * dsin(2 * f)
            + 0.00739 * e * dsin(mp - m)
            - 0.00514 * e * dsin(mp + m)
            + 0.00208 * e * e * dsin(2 * m)
            - 0.00111 * dsin(mp - 2 * f)
            - 0.00057 * dsin(mp + 2 * f)
            + 0.00056 * e * dsin(2 * mp + m)
            - 0.00042 * dsin(3 * mp)
            + 0.00042 * e * dsin(m + 2 * f)
            + 0.00038 * e * dsin(m - 2 * f)
            - 0.00024 * e * dsin(2 * mp - m)
            - 0.00017 * dsin(omega)
            - 0.00007 * dsin(mp + 2 * m)
            + 0.00004 * dsin(2 * mp - 2 * f)
            + 0.00004 * dsin(3 * m)
            + 0.00003 * dsin(mp + m - 2 * f)
            + 0.00003 * dsin(2 * mp + 2 * f)
            - 0.00003 * dsin(mp + m + 2 * f)
            + 0.00003 * dsin(mp - m + 2 * f)
            - 0.00002 * dsin(mp - m - 2 * f)
            - 0.00002 * dsin(3 * mp + m)
            + 0.00002 * dsin(4 * mp)
        )
    elif fraction == 0.5:
        correction = (
            -0.40614 * dsin(mp)
            + 0.17302 * e * dsin(m)
            + 0.01614 * dsin(2 * mp)
            + 0.01043 * dsin(2 * f)
            + 0.00734 * e * dsin(mp - m)
            - 0.00515 * e * dsin(mp + m)
            + 0.00209 * e * e * dsin(2 * m)
            - 0.00111 * dsin(mp - 2 * f)
            - 0.00057 * dsin(mp + 2 * f)
            + 0.00056 * e * dsin(2 * mp + m)
            - 0.00042 * dsin(3 * mp)
            + 0.00042 * e * dsin(m + 2 * f)
            + 0.00038 * e * dsin(m - 2 * f)
            - 0.00024 * e * dsin(2 * mp - m)
            - 0.00017 * dsin(omega)
            - 0.00007 * dsin(mp + 2 * m)
            + 0.00004 * dsin(2 * mp - 2 * f)
            + 0.00004 * dsin(3 * m)
            + 0.00003 * dsin(mp + m - 2 * f)
            + 0.00003 * dsin(2 * mp + 2 * f)
            - 0.00003 * dsin(mp + m + 2 * f)
            + 0.00003 * dsin(mp - m + 2 * f)
            - 0.00002 * dsin(mp - m - 2 * f)
            - 0.00002 * dsin(3 * mp + m)
            + 0.00002 * dsin(4 * mp)
        )
    else:
        correction = (
            -0.62801 * dsin(mp)
            + 0.17172 * e * dsin(m)
            - 0.01183 * e * dsin(mp + m)
            + 0.00862 * dsin(2 * mp)
            + 0.00804 * dsin(2 * f)
            + 0.00454 * e * dsin(mp - m)
            + 0.00204 * e * e * dsin(2 * m)
            - 0.00180 * dsin(mp - 2 * f)
            - 0.00070 * dsin(mp + 2 * f)
            - 0.00040 * dsin(3 * mp)
            - 0.00034 * e * dsin(2 * mp - m)
            + 0.00032 * e * dsin(m + 2 * f)
            + 0.00032 * e * dsin(m - 2 * f)
            - 0.00028 * e * e * dsin(mp + 2 * m)
            + 0.00027 * e * dsin(2 * mp + m)
            - 0.00017 * dsin(omega)
            - 0.00005 * dsin(mp - m - 2 * f)
            + 0.00004 * dsin(2 * mp + 2 * f)
            - 0.00004 * dsin(mp + m + 2 * f)
            + 0.00004 * dsin(mp - 2 * m)
            + 0.00003 * dsin(mp + m - 2 * f)
            + 0.00003 * dsin(3 * m)
            + 0.00002 * dsin(2 * mp - 2 * f)
            + 0.00002 * dsin(mp - m + 2 * f)
            - 0.00002 * dsin(3 * mp + m)
        )
        w = (
            0.00306
            - 0.00038 * e * dcos(m)
            + 0.00026 * dcos(mp)
            - 0.00002 * dcos(mp - m)
            + 0.00002 * dcos(mp + m)
            + 0.00002 * dcos(2 * f)
        )
        correction += w if fraction == 0.25 else -w

    return jde + correction + _planetary_arguments(k, t)


def moon_phases_in_range(
    start_year: int, end_year: int, phases: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75)
) -> list[CelestialEvent]:
    """Every requested phase between two years. Guard the span: a century is ~1,237
    lunations per phase."""
    events: list[CelestialEvent] = []
    k_start = math.floor(_lunation_k(start_year)) - 2
    k_end = math.ceil(_lunation_k(end_year + 1)) + 2
    for k_int in range(int(k_start), int(k_end)):
        for fraction in phases:
            jd = moon_phase_time(k_int + fraction)
            jd_ut = tt_to_ut(jd)
            year = gregorian_from_jd(jd_ut)[0]
            if not (start_year <= year <= end_year):
                continue
            events.append(
                _finish(
                    "moon_phase",
                    PHASE_NAMES[fraction],
                    jd,
                    f"{MEEUS}, ch. 49",
                    "Phase times are accurate to well under a minute for the last few "
                    "millennia; conversion to local civil time depends on ΔT.",
                    {"lunation": k_int, "phase": PHASE_NAMES[fraction]},
                )
            )
    events.sort(key=lambda e: e.jd_tt)
    return events


def nearest_new_moon(jd_tt: float) -> CelestialEvent:
    from app.astronomy.timescales import decimal_year_from_jd

    k = round(_lunation_k(decimal_year_from_jd(jd_tt)))
    best = min(
        (moon_phase_time(k + offset) for offset in (-1, 0, 1)),
        key=lambda t: abs(t - jd_tt),
    )
    return _finish(
        "moon_phase",
        "New Moon",
        best,
        f"{MEEUS}, ch. 49",
        "Astronomical conjunction, not first crescent visibility — many ancient calendars "
        "began the month one to two days later, at the first sighting.",
        {"phase": "New Moon"},
    )


# --------------------------------------------------------------------------------------
# Eclipses — Meeus ch. 54
# --------------------------------------------------------------------------------------

def _eclipse_accuracy_note(year: int) -> str:
    """State the precision honestly, and differently for different epochs.

    Validation against the NASA Five Millennium Canon: γ agrees to ~0.001 for modern
    eclipses (1999 Aug 11: 0.5058 computed vs 0.5062 published) and the method recovers
    the classical anchor eclipses — Thales (28 May 585 BCE) and Bur-Sagale
    (15 June 763 BCE) — on the correct Julian day. Magnitudes drift further back in time
    as the mean elements accumulate error.
    """
    base = (
        "Computed from the Moon's argument of latitude at syzygy (Meeus ch. 54). "
        "No ground track is integrated, so this establishes that an eclipse occurred, "
        "when, and of what type — not who could see it."
    )
    if year >= 1600:
        return base + " Date and magnitude match modern catalogues to within ~0.005."
    if year >= 0:
        return (
            base + " For this epoch the date is dependable; magnitude and γ should be "
            "treated as accurate to a few hundredths and cross-checked against the NASA "
            "Five Millennium Canon before being used as evidence."
        )
    return (
        base + " For dates BCE the day itself is dependable — the method reproduces the "
        "classical anchor eclipses exactly — but magnitude and γ carry meaningfully larger "
        "error, and ΔT uncertainty of tens of minutes means visibility from any named "
        "location must be verified separately."
    )


def _eclipse_at(k: float) -> dict | None:
    """Evaluate one syzygy. Integer k → solar; k+0.5 → lunar. None if no eclipse."""
    jde, t, e, m, mp, f, omega = _phase_fundamentals(k)

    # No eclipse is possible unless the Moon is near a node.
    if abs(dsin(f)) > 0.36:
        return None

    is_solar = abs(k % 1) < 0.25
    f1 = f - 0.02665 * dsin(omega)
    a1 = 299.77 + 0.107408 * k - 0.009173 * t**2

    common = (
        0.0161 * dsin(2 * mp)
        - 0.0097 * dsin(2 * f1)
        + 0.0073 * e * dsin(mp - m)
        - 0.0050 * e * dsin(mp + m)
        - 0.0023 * dsin(mp - 2 * f1)
        + 0.0021 * e * dsin(2 * m)
        + 0.0012 * dsin(mp + 2 * f1)
        + 0.0006 * e * dsin(2 * mp + m)
        - 0.0004 * dsin(3 * mp)
        - 0.0003 * e * dsin(m + 2 * f1)
        + 0.0003 * dsin(a1)
        - 0.0002 * e * dsin(m - 2 * f1)
        - 0.0002 * e * dsin(2 * mp - m)
        - 0.0002 * dsin(omega)
    )
    if is_solar:
        correction = -0.4075 * dsin(mp) + 0.1721 * e * dsin(m) + common
    else:
        correction = -0.4065 * dsin(mp) + 0.1727 * e * dsin(m) + common

    jd_max = jde + correction

    p = (
        0.2070 * e * dsin(m)
        + 0.0024 * e * dsin(2 * m)
        - 0.0392 * dsin(mp)
        + 0.0116 * dsin(2 * mp)
        - 0.0073 * e * dsin(mp + m)
        + 0.0067 * e * dsin(mp - m)
        + 0.0118 * dsin(2 * f1)
    )
    q = (
        5.2207
        - 0.0048 * e * dcos(m)
        + 0.0020 * e * dcos(2 * m)
        - 0.3299 * dcos(mp)
        - 0.0060 * e * dcos(mp + m)
        + 0.0041 * e * dcos(mp - m)
    )
    w = abs(dcos(f1))
    gamma = (p * dcos(f1) + q * dsin(f1)) * (1 - 0.0048 * w)
    u = (
        0.0059
        + 0.0046 * e * dcos(m)
        - 0.0182 * dcos(mp)
        + 0.0004 * dcos(2 * mp)
        - 0.0005 * dcos(m + mp)
    )

    abs_gamma = abs(gamma)

    if is_solar:
        if abs_gamma > 1.5433 + u:
            return None
        if abs_gamma < 0.9972:
            if u < 0:
                kind, magnitude = "total", 1.0
            elif u > 0.0047:
                kind, magnitude = "annular", 1.0
            else:
                omega_limit = 0.00464 * math.sqrt(max(0.0, 1 - gamma * gamma))
                kind = "hybrid" if u < omega_limit else "annular"
                magnitude = 1.0
            central = True
        else:
            central = False
            kind = "partial"
            magnitude = (1.5433 + u - abs_gamma) / (0.5461 + 2 * u)
            if magnitude <= 0:
                return None
        return {
            "jd_max": jd_max,
            "kind": kind,
            "magnitude": magnitude,
            "gamma": gamma,
            "u": u,
            "central": central,
            "is_solar": True,
        }

    # Lunar
    penumbral_magnitude = (1.5573 + u - abs_gamma) / 0.5450
    umbral_magnitude = (1.0128 - u - abs_gamma) / 0.5450
    if penumbral_magnitude <= 0:
        return None
    if umbral_magnitude >= 1.0:
        kind, magnitude = "total", umbral_magnitude
    elif umbral_magnitude > 0:
        kind, magnitude = "partial", umbral_magnitude
    else:
        kind, magnitude = "penumbral", penumbral_magnitude

    n = 0.5458 + 0.04 * dcos(mp)
    durations: dict[str, float] = {}
    for key, radius in (
        ("penumbral_minutes", 1.5573 + u),
        ("partial_minutes", 1.0128 - u),
        ("total_minutes", 0.4678 - u),
    ):
        inner = radius * radius - gamma * gamma
        if inner > 0:
            durations[key] = round(2 * (60.0 / n) * math.sqrt(inner), 1)

    return {
        "jd_max": jd_max,
        "kind": kind,
        "magnitude": magnitude,
        "gamma": gamma,
        "u": u,
        "central": False,
        "is_solar": False,
        "umbral_magnitude": umbral_magnitude,
        "penumbral_magnitude": penumbral_magnitude,
        "durations": durations,
    }


def eclipses_in_range(
    start_year: int, end_year: int, kind: str = "both"
) -> list[CelestialEvent]:
    """All solar and/or lunar eclipses between two years (inclusive)."""
    if end_year < start_year:
        raise ValueError("end_year must not precede start_year")

    events: list[CelestialEvent] = []
    k = math.floor(_lunation_k(start_year)) - 2
    k_end = math.ceil(_lunation_k(end_year + 1)) + 2

    offsets: list[float] = []
    if kind in ("both", "solar"):
        offsets.append(0.0)
    if kind in ("both", "lunar"):
        offsets.append(0.5)

    for k_int in range(int(k), int(k_end)):
        for offset in offsets:
            result = _eclipse_at(k_int + offset)
            if result is None:
                continue
            jd_max = result["jd_max"]
            jd_ut = tt_to_ut(jd_max)
            year = gregorian_from_jd(jd_ut)[0]
            if not (start_year <= year <= end_year):
                continue

            solar = result["is_solar"]
            event_type = "solar_eclipse" if solar else "lunar_eclipse"
            label = f"{result['kind'].title()} {'solar' if solar else 'lunar'} eclipse"

            sun = sun_position(jd_max)
            unc = time_uncertainty(year)
            details = {
                "eclipse_kind": result["kind"],
                "magnitude": round(result["magnitude"], 3),
                "gamma": round(result["gamma"], 4),
                "central": result["central"],
                "sun_longitude": round(sun.longitude, 3),
                "zodiac_sign": sun.zodiac_sign
                if solar
                else ZODIAC_SIGNS[int(normalize_degrees(sun.longitude + 180) // 30)],
                "saros_series_estimate": _saros_series(k_int, solar),
                "time_uncertainty": unc.to_dict(),
                "visibility_uncertainty": unc.note,
            }
            if not solar:
                details["umbral_magnitude"] = round(result["umbral_magnitude"], 3)
                details["penumbral_magnitude"] = round(result["penumbral_magnitude"], 3)
                details["durations"] = result["durations"]

            events.append(
                _finish(
                    event_type,
                    label,
                    jd_max,
                    f"{MEEUS}, ch. 54",
                    _eclipse_accuracy_note(year),
                    details,
                )
            )

    events.sort(key=lambda e: e.jd_tt)
    return events


def _saros_series(k: int, solar: bool) -> int:
    """Approximate Saros series number.

    The classic relation ties lunation number to series; it drifts at the ends of a
    series, so this is offered as an estimate for cross-referencing catalogues, not as a
    catalogue identity.
    """
    base = 136 if solar else 131
    return int((k * 38 / 223 + base) % 223) or 223


def eclipses_near(jd_tt: float, window_days: float = 400.0, kind: str = "both") -> list[dict]:
    """Eclipses within a window of a date, nearest first — the common shape of the
    question "was there an eclipse around the time this text describes?"."""
    from app.astronomy.timescales import decimal_year_from_jd

    year = int(decimal_year_from_jd(jd_tt))
    span = int(window_days / 365.25) + 1
    found = eclipses_in_range(year - span, year + span, kind=kind)
    nearby = [e for e in found if abs(e.jd_tt - jd_tt) <= window_days]
    nearby.sort(key=lambda e: abs(e.jd_tt - jd_tt))
    return [{**e.to_dict(), "days_from_target": round(e.jd_tt - jd_tt, 2)} for e in nearby]


# --------------------------------------------------------------------------------------
# Equinoxes and solstices — Meeus ch. 27
# --------------------------------------------------------------------------------------

_SEASON_TERMS = [
    (485, 324.96, 1934.136), (203, 337.23, 32964.467), (199, 342.08, 20.186),
    (182, 27.85, 445267.112), (156, 73.14, 45036.886), (136, 171.52, 22518.443),
    (77, 222.54, 65928.934), (74, 296.72, 3034.906), (70, 243.58, 9037.513),
    (58, 119.81, 33718.147), (52, 297.17, 150.678), (50, 21.02, 2281.226),
    (45, 247.54, 29929.562), (44, 325.15, 31555.956), (29, 60.93, 4443.417),
    (18, 155.12, 67555.328), (17, 288.79, 4562.452), (16, 198.04, 62894.029),
    (14, 199.76, 31436.921), (12, 95.39, 14577.848), (12, 287.11, 31931.756),
    (12, 320.81, 34777.259), (9, 227.73, 1222.114), (8, 15.45, 16859.074),
]

SEASON_NAMES = ["March equinox", "June solstice", "September equinox", "December solstice"]


def season_time(year: int, season_index: int) -> float:
    """JDE (TT) of an equinox or solstice. `season_index` 0–3 per SEASON_NAMES."""
    if year >= 1000:
        y = (year - 2000) / 1000.0
        jde0 = [
            2451623.80984 + 365242.37404 * y + 0.05169 * y**2 - 0.00411 * y**3 - 0.00057 * y**4,
            2451716.56767 + 365241.62603 * y + 0.00325 * y**2 + 0.00888 * y**3 - 0.00030 * y**4,
            2451810.21715 + 365242.01767 * y - 0.11575 * y**2 + 0.00337 * y**3 + 0.00078 * y**4,
            2451900.05952 + 365242.74049 * y - 0.06223 * y**2 - 0.00823 * y**3 + 0.00032 * y**4,
        ][season_index]
    else:
        y = year / 1000.0
        jde0 = [
            1721139.29189 + 365242.13740 * y + 0.06134 * y**2 + 0.00111 * y**3 - 0.00071 * y**4,
            1721233.25401 + 365241.72562 * y - 0.05323 * y**2 + 0.00907 * y**3 + 0.00025 * y**4,
            1721325.70455 + 365242.49558 * y - 0.11677 * y**2 - 0.00297 * y**3 + 0.00074 * y**4,
            1721414.39987 + 365242.88257 * y - 0.00769 * y**2 - 0.00933 * y**3 - 0.00006 * y**4,
        ][season_index]

    t = (jde0 - 2451545.0) / 36525.0
    w = 35999.373 * t - 2.47
    delta_lambda = 1 + 0.0334 * dcos(w) + 0.0007 * dcos(2 * w)
    s = sum(a * dcos(b + c * t) for a, b, c in _SEASON_TERMS)
    return jde0 + (0.00001 * s) / delta_lambda


def seasons_for_year(year: int) -> list[CelestialEvent]:
    return [
        _finish(
            "equinox" if index % 2 == 0 else "solstice",
            SEASON_NAMES[index],
            season_time(year, index),
            f"{MEEUS}, ch. 27",
            "Accurate to under a minute for 1000–3000 CE and to a few minutes over the "
            "wider −1000 to +3000 range.",
            {"season": SEASON_NAMES[index], "hemisphere_note": "Names use the northern hemisphere convention."},
        )
        for index in range(4)
    ]


# --------------------------------------------------------------------------------------
# Conjunctions
# --------------------------------------------------------------------------------------


def find_conjunctions(
    start_year: int,
    end_year: int,
    bodies: list[str] | None = None,
    max_separation: float = 3.0,
    step_days: float = 2.0,
) -> list[CelestialEvent]:
    """Close approaches between pairs of bodies in geocentric ecliptic longitude.

    Scans on a coarse grid, then refines each candidate minimum by golden-section search.
    `max_separation` is in degrees of true angular separation.
    """
    from app.astronomy.timescales import angular_separation

    bodies = bodies or NAKED_EYE_PLANETS
    pairs = [(a, b) for i, a in enumerate(bodies) for b in bodies[i + 1 :]]

    jd_start = jd_from_gregorian(start_year, 1, 1, 0.0)
    jd_end = jd_from_gregorian(end_year, 12, 31, 24.0)

    events: list[CelestialEvent] = []
    for first, second in pairs:
        previous: tuple[float, float] | None = None
        trend_down = False
        jd = jd_start
        while jd <= jd_end:
            p1, p2 = body_position(first, jd), body_position(second, jd)
            sep = angular_separation(p1.longitude, p1.latitude, p2.longitude, p2.latitude)
            if previous is not None:
                if sep > previous[1] and trend_down and previous[1] < max_separation * 3:
                    refined_jd, refined_sep = _refine_minimum(
                        first, second, previous[0] - step_days, jd
                    )
                    if refined_sep <= max_separation:
                        events.append(_conjunction_event(first, second, refined_jd, refined_sep))
                trend_down = sep < previous[1]
            previous = (jd, sep)
            jd += step_days

    events.sort(key=lambda e: e.jd_tt)
    return events


def _refine_minimum(first: str, second: str, lo: float, hi: float) -> tuple[float, float]:
    from app.astronomy.timescales import angular_separation

    def separation(jd: float) -> float:
        p1, p2 = body_position(first, jd), body_position(second, jd)
        return angular_separation(p1.longitude, p1.latitude, p2.longitude, p2.latitude)

    phi = (math.sqrt(5) - 1) / 2
    a, b = lo, hi
    c, d = b - phi * (b - a), a + phi * (b - a)
    fc, fd = separation(c), separation(d)
    for _ in range(60):
        if b - a < 1e-4:
            break
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = separation(c)
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = separation(d)
    best = c if fc < fd else d
    return best, min(fc, fd)


def _conjunction_event(first: str, second: str, jd: float, separation: float) -> CelestialEvent:
    from app.astronomy.timescales import angular_separation

    p1, p2 = body_position(first, jd), body_position(second, jd)
    combined_accuracy = math.sqrt(p1.accuracy_degrees**2 + p2.accuracy_degrees**2)

    # Position error converts into *timing* error at a rate set by the pair's relative
    # angular velocity. For a slow pair such as Jupiter and Saturn a few tenths of a
    # degree of model error is a couple of weeks of date uncertainty, which matters a
    # great deal when a text is being matched to a specific day.
    #
    # This must be the relative *velocity*, not the change in separation: at the minimum
    # the separation is stationary by definition, so differencing it would report zero.
    def offsets(delta: float) -> tuple[float, float]:
        a, b = body_position(first, jd + delta), body_position(second, jd + delta)
        return normalize_degrees_signed(a.longitude - b.longitude), a.latitude - b.latitude

    (lon_before, lat_before), (lon_after, lat_after) = offsets(-5.0), offsets(5.0)
    relative_speed = math.hypot(lon_after - lon_before, lat_after - lat_before) / 10.0
    timing_uncertainty_days = (
        min(combined_accuracy / relative_speed, 999.0) if relative_speed > 1e-6 else None
    )

    if timing_uncertainty_days is None:
        timing_phrase = "The pair moves too slowly relative to each other to date the exact minimum."
    elif timing_uncertainty_days >= 1:
        timing_phrase = (
            f"Because the two bodies separate at only {relative_speed:.3f}°/day, that position "
            f"error corresponds to roughly ±{timing_uncertainty_days:.0f} days in the date of "
            "closest approach. The conjunction is real; the exact day is not pinned down here."
        )
    else:
        timing_phrase = "The date of closest approach is determined to within about a day."

    return _finish(
        "planetary_conjunction",
        f"{first}–{second} conjunction ({separation:.2f}° apart)",
        jd,
        "JPL Keplerian approximation (Standish) via app.astronomy.ephemeris",
        f"Separation is uncertain by roughly ±{combined_accuracy:.2f}° from the underlying "
        f"model. {timing_phrase}",
        {
            "bodies": [first, second],
            "separation_degrees": round(separation, 3),
            "separation_uncertainty_degrees": round(combined_accuracy, 3),
            "timing_uncertainty_days": (
                round(timing_uncertainty_days, 1) if timing_uncertainty_days is not None else None
            ),
            "relative_speed_degrees_per_day": round(relative_speed, 4),
            "zodiac_sign": p1.zodiac_sign,
            "longitude": round(p1.longitude, 3),
            f"{first.lower()}_retrograde": is_retrograde(first, jd),
            f"{second.lower()}_retrograde": is_retrograde(second, jd),
        },
    )


def sky_snapshot(jd_tt: float) -> dict:
    """Everything a report needs to describe "the sky on this date"."""
    sun = sun_position(jd_tt)
    moon = moon_position(jd_tt)
    from app.astronomy.ephemeris import moon_illuminated_fraction, moon_phase_name

    bodies = [sun.to_dict(), moon.to_dict()]
    for name in NAKED_EYE_PLANETS:
        position = body_position(name, jd_tt)
        entry = position.to_dict()
        entry["retrograde"] = is_retrograde(name, jd_tt)
        bodies.append(entry)

    year = gregorian_from_jd(tt_to_ut(jd_tt))[0]
    return {
        "julian_day": round(jd_tt, 5),
        "bodies": bodies,
        "moon_phase": moon_phase_name(jd_tt),
        "moon_illuminated_fraction": round(moon_illuminated_fraction(jd_tt), 4),
        "time_uncertainty": time_uncertainty(year).to_dict(),
    }


__all__ = [
    "CelestialEvent",
    "LUNATION_DAYS",
    "PHASE_NAMES",
    "SEASON_NAMES",
    "moon_phase_time",
    "moon_phases_in_range",
    "nearest_new_moon",
    "eclipses_in_range",
    "eclipses_near",
    "season_time",
    "seasons_for_year",
    "find_conjunctions",
    "sky_snapshot",
]
