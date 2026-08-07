"""Time scales, ΔT, and the honest accounting of when we do and do not know the hour.

The distinction that matters for ancient astronomy:

* **TT** (Terrestrial Time) is the smooth time scale ephemerides are computed in.
* **UT** is tied to the Earth's rotation, which is irregular and slowly decelerating.
* **ΔT = TT − UT** must be modelled, and for dates before telescopic records it is
  *estimated from eclipse observations themselves*.

For 1000 BCE the ΔT uncertainty is roughly ±hours. That does not blur *whether* an
eclipse happened — that is orbital mechanics and is solid — but it can move the sub-solar
point by tens of degrees of longitude, which is why this engine reports eclipse dates
confidently and eclipse *visibility from a named city* only with an explicit error band.
Any tool that shows you a precise ancient eclipse track without saying this is
overselling its precision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.calendars.core import (
    gregorian_to_rd,
    jd_from_rd,
    rd_from_jd,
    rd_to_gregorian,
)

J2000 = 2451545.0
"""Julian Date of 2000 January 1.5 TT — the standard epoch."""

MEEUS = "Meeus, J., Astronomical Algorithms, 2nd ed. (Willmann-Bell, 1998)"
ESPENAK_MEEUS_DELTA_T = (
    "Espenak, F. & Meeus, J., 'Polynomial Expressions for Delta T', "
    "NASA Eclipse Web Site / NASA TP-2006-214141"
)


def jd_from_gregorian(year: int, month: int, day: int, hour: float = 12.0) -> float:
    """Julian Date from a proleptic Gregorian calendar date and UT hour."""
    return jd_from_rd(gregorian_to_rd(year, month, day), day_fraction=hour / 24.0)


def gregorian_from_jd(jd: float) -> tuple[int, int, int, float]:
    """Inverse of :func:`jd_from_gregorian`. Returns (year, month, day, hour)."""
    shifted = jd + 0.5
    rd = rd_from_jd(jd)
    year, month, day = rd_to_gregorian(rd)
    hour = (shifted - math.floor(shifted)) * 24.0
    return year, month, day, hour


def decimal_year_from_jd(jd: float) -> float:
    year, month, day, hour = gregorian_from_jd(jd)
    start = jd_from_gregorian(year, 1, 1, 0.0)
    end = jd_from_gregorian(year + 1, 1, 1, 0.0)
    return year + (jd - start) / (end - start)


def julian_centuries(jd: float) -> float:
    """Julian centuries from J2000."""
    return (jd - J2000) / 36525.0


def delta_t_seconds(year: float) -> float:
    """ΔT = TT − UT, in seconds, via the Espenak & Meeus polynomial expressions.

    Valid from −1999 to +3000. Outside the range of direct observation the value is an
    extrapolation from the parabola fitted to ancient eclipse records; use
    :func:`delta_t_uncertainty_seconds` alongside it, always.
    """
    y = year

    if y < -500:
        u = (y - 1820) / 100.0
        return -20 + 32 * u * u

    if y < 500:
        u = y / 100.0
        return (
            10583.6
            - 1014.41 * u
            + 33.78311 * u**2
            - 5.952053 * u**3
            - 0.1798452 * u**4
            + 0.022174192 * u**5
            + 0.0090316521 * u**6
        )

    if y < 1600:
        u = (y - 1000) / 100.0
        return (
            1574.2
            - 556.01 * u
            + 71.23472 * u**2
            + 0.319781 * u**3
            - 0.8503463 * u**4
            - 0.005050998 * u**5
            + 0.0083572073 * u**6
        )

    if y < 1700:
        t = y - 1600
        return 120 - 0.9808 * t - 0.01532 * t**2 + t**3 / 7129.0

    if y < 1800:
        t = y - 1700
        return 8.83 + 0.1603 * t - 0.0059285 * t**2 + 0.00013336 * t**3 - t**4 / 1174000.0

    if y < 1860:
        t = y - 1800
        return (
            13.72
            - 0.332447 * t
            + 0.0068612 * t**2
            + 0.0041116 * t**3
            - 0.00037436 * t**4
            + 0.0000121272 * t**5
            - 0.0000001699 * t**6
            + 0.000000000875 * t**7
        )

    if y < 1900:
        t = y - 1860
        return (
            7.62
            + 0.5737 * t
            - 0.251754 * t**2
            + 0.01680668 * t**3
            - 0.0004473624 * t**4
            + t**5 / 233174.0
        )

    if y < 1920:
        t = y - 1900
        return -2.79 + 1.494119 * t - 0.0598939 * t**2 + 0.0061966 * t**3 - 0.000197 * t**4

    if y < 1941:
        t = y - 1920
        return 21.20 + 0.84493 * t - 0.076100 * t**2 + 0.0020936 * t**3

    if y < 1961:
        t = y - 1950
        return 29.07 + 0.407 * t - t**2 / 233.0 + t**3 / 2547.0

    if y < 1986:
        t = y - 1975
        return 45.45 + 1.067 * t - t**2 / 260.0 - t**3 / 718.0

    if y < 2005:
        t = y - 2000
        return (
            63.86
            + 0.3345 * t
            - 0.060374 * t**2
            + 0.0017275 * t**3
            + 0.000651814 * t**4
            + 0.00002373599 * t**5
        )

    if y < 2050:
        t = y - 2000
        return 62.92 + 0.32217 * t + 0.005589 * t**2

    if y < 2150:
        return -20 + 32 * ((y - 1820) / 100.0) ** 2 - 0.5628 * (2150 - y)

    u = (y - 1820) / 100.0
    return -20 + 32 * u * u


def delta_t_uncertainty_seconds(year: float) -> float:
    """A defensible 1σ-ish uncertainty on ΔT.

    Modern values (post-1955, atomic timekeeping) are exact. Telescopic-era values are
    good to seconds. Pre-telescopic values rest on a sparse set of datable ancient eclipse
    reports, and Stephenson & Morrison's error envelope grows roughly quadratically
    backwards. These figures follow that envelope.
    """
    if year >= 1955:
        return 0.1
    if year >= 1600:
        return 2.0
    if year >= 1000:
        return 20.0 + (1600 - year) * 0.5
    if year >= 0:
        return 320.0 + (1000 - year) * 1.2
    u = (year - 1820) / 100.0
    return max(600.0, 0.8 * abs(u) ** 2 * 32.0 * 0.25)


@dataclass(frozen=True, slots=True)
class TimeUncertainty:
    delta_t_seconds: float
    uncertainty_seconds: float
    note: str

    @property
    def uncertainty_minutes(self) -> float:
        return self.uncertainty_seconds / 60.0

    @property
    def longitude_uncertainty_degrees(self) -> float:
        """How far east/west the sub-solar point could be, at 15° per hour."""
        return self.uncertainty_seconds / 3600.0 * 15.0

    def to_dict(self) -> dict:
        return {
            "delta_t_seconds": round(self.delta_t_seconds, 1),
            "uncertainty_seconds": round(self.uncertainty_seconds, 1),
            "uncertainty_minutes": round(self.uncertainty_minutes, 1),
            "longitude_uncertainty_degrees": round(self.longitude_uncertainty_degrees, 2),
            "note": self.note,
        }


def time_uncertainty(year: float) -> TimeUncertainty:
    dt = delta_t_seconds(year)
    unc = delta_t_uncertainty_seconds(year)
    lon = unc / 3600.0 * 15.0
    if unc < 1:
        note = "ΔT is known exactly for this epoch; the computed time is the limiting factor."
    elif lon < 1:
        note = (
            f"ΔT is uncertain by about ±{unc:.0f}s, shifting the ground track by under a "
            "degree of longitude. Local circumstances are reliable."
        )
    else:
        note = (
            f"ΔT for this epoch is uncertain by roughly ±{unc / 60:.0f} minutes, which moves "
            f"the sub-solar point by about ±{lon:.0f}° of longitude. The date and the fact of "
            "the eclipse are secure; whether it was visible from a particular city is not "
            "settled by this calculation alone."
        )
    return TimeUncertainty(delta_t_seconds=dt, uncertainty_seconds=unc, note=note)


def tt_to_ut(jd_tt: float) -> float:
    return jd_tt - delta_t_seconds(decimal_year_from_jd(jd_tt)) / 86400.0


def ut_to_tt(jd_ut: float) -> float:
    return jd_ut + delta_t_seconds(decimal_year_from_jd(jd_ut)) / 86400.0


# ---- angle helpers ---------------------------------------------------------------------


def normalize_degrees(value: float) -> float:
    return value % 360.0


def normalize_degrees_signed(value: float) -> float:
    """Wrap to (−180, 180]."""
    v = (value + 180.0) % 360.0 - 180.0
    return v + 360.0 if v <= -180.0 else v


def dsin(degrees: float) -> float:
    return math.sin(math.radians(degrees))


def dcos(degrees: float) -> float:
    return math.cos(math.radians(degrees))


def angular_separation(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle separation in degrees between two ecliptic positions."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    cos_d = math.sin(phi1) * math.sin(phi2) + math.cos(phi1) * math.cos(phi2) * math.cos(dlon)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_d))))


__all__ = [
    "J2000",
    "MEEUS",
    "ESPENAK_MEEUS_DELTA_T",
    "jd_from_gregorian",
    "gregorian_from_jd",
    "decimal_year_from_jd",
    "julian_centuries",
    "delta_t_seconds",
    "delta_t_uncertainty_seconds",
    "TimeUncertainty",
    "time_uncertainty",
    "tt_to_ut",
    "ut_to_tt",
    "normalize_degrees",
    "normalize_degrees_signed",
    "dsin",
    "dcos",
    "angular_separation",
]
