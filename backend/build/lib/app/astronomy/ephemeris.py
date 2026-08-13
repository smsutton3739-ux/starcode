"""Positions of the Sun, Moon and planets.

Three independent models, each chosen for the accuracy it can *honestly* claim over the
several-millennia span that ancient texts require:

* **Sun** — Meeus ch. 25 (low accuracy), ~0.01° over historical timescales.
* **Moon** — Meeus ch. 47, the abridged ELP-2000/82 series. ~10″ in longitude, ~4″ in
  latitude near the present epoch, degrading gradually into antiquity.
* **Planets** — the JPL/Standish Keplerian approximation valid 3000 BCE – 3000 CE.

Every public function returns the model's own accuracy alongside the number. The engine
would rather say "Jupiter was in Pisces, ±0.3°" than imply arcsecond precision it does
not have. For work that depends on precision better than these bounds, re-verify against
a full numerical ephemeris (JPL DE441).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.astronomy.timescales import (
    MEEUS,
    dcos,
    dsin,
    julian_centuries,
    normalize_degrees,
)

JPL_REFERENCE = (
    "Standish, E. M., 'Keplerian Elements for Approximate Positions of the Major Planets', "
    "JPL Solar System Dynamics"
)


@dataclass(frozen=True, slots=True)
class Position:
    """A geocentric apparent position in ecliptic coordinates of date."""

    body: str
    jd_tt: float
    longitude: float
    latitude: float
    distance_au: float
    accuracy_degrees: float
    model: str

    @property
    def zodiac_sign(self) -> str:
        return ZODIAC_SIGNS[int(normalize_degrees(self.longitude) // 30)]

    @property
    def degrees_in_sign(self) -> float:
        return normalize_degrees(self.longitude) % 30

    def to_dict(self) -> dict:
        return {
            "body": self.body,
            "julian_day": round(self.jd_tt, 5),
            "ecliptic_longitude": round(self.longitude, 4),
            "ecliptic_latitude": round(self.latitude, 4),
            "distance_au": round(self.distance_au, 6),
            "zodiac_sign": self.zodiac_sign,
            "degrees_in_sign": round(self.degrees_in_sign, 2),
            "accuracy_degrees": self.accuracy_degrees,
            "model": self.model,
        }


ZODIAC_SIGNS = [
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
]


# --------------------------------------------------------------------------------------
# Sun
# --------------------------------------------------------------------------------------


def sun_position(jd_tt: float) -> Position:
    """Apparent geocentric position of the Sun. Meeus ch. 25."""
    t = julian_centuries(jd_tt)

    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t * t  # geometric mean longitude
    m = 357.52911 + 35999.05029 * t - 0.0001537 * t * t  # mean anomaly
    e = 0.016708634 - 0.000042037 * t - 0.0000001267 * t * t  # eccentricity

    c = (
        (1.914602 - 0.004817 * t - 0.000014 * t * t) * dsin(m)
        + (0.019993 - 0.000101 * t) * dsin(2 * m)
        + 0.000289 * dsin(3 * m)
    )
    true_longitude = l0 + c
    true_anomaly = m + c
    radius = (1.000001018 * (1 - e * e)) / (1 + e * dcos(true_anomaly))

    # Apparent longitude: nutation in longitude plus aberration.
    omega = 125.04 - 1934.136 * t
    apparent = true_longitude - 0.00569 - 0.00478 * dsin(omega)

    return Position(
        body="Sun",
        jd_tt=jd_tt,
        longitude=normalize_degrees(apparent),
        latitude=0.0,
        distance_au=radius,
        accuracy_degrees=0.01,
        model=f"{MEEUS}, ch. 25 (low accuracy)",
    )


# --------------------------------------------------------------------------------------
# Moon — abridged ELP-2000/82 (Meeus ch. 47)
# --------------------------------------------------------------------------------------

# (D, M, M', F, coefficient in ΣL [1e-6 deg], coefficient in Σr [1e-3 km])
_MOON_LR = [
    (0, 0, 1, 0, 6288774, -20905355),
    (2, 0, -1, 0, 1274027, -3699111),
    (2, 0, 0, 0, 658314, -2955968),
    (0, 0, 2, 0, 213618, -569925),
    (0, 1, 0, 0, -185116, 48888),
    (0, 0, 0, 2, -114332, -3149),
    (2, 0, -2, 0, 58793, 246158),
    (2, -1, -1, 0, 57066, -152138),
    (2, 0, 1, 0, 53322, -170733),
    (2, -1, 0, 0, 45758, -204586),
    (0, 1, -1, 0, -40923, -129620),
    (1, 0, 0, 0, -34720, 108743),
    (0, 1, 1, 0, -30383, 104755),
    (2, 0, 0, -2, 15327, 10321),
    (0, 0, 1, 2, -12528, 0),
    (0, 0, 1, -2, 10980, 79661),
    (4, 0, -1, 0, 10675, -34782),
    (0, 0, 3, 0, 10034, -23210),
    (4, 0, -2, 0, 8548, -21636),
    (2, 1, -1, 0, -7888, 24208),
    (2, 1, 0, 0, -6766, 30824),
    (1, 0, -1, 0, -5163, -8379),
    (1, 1, 0, 0, 4987, -16675),
    (2, -1, 1, 0, 4036, -12831),
    (2, 0, 2, 0, 3994, -10445),
    (4, 0, 0, 0, 3861, -11650),
    (2, 0, -3, 0, 3665, 14403),
    (0, 1, -2, 0, -2689, -7003),
    (2, 0, -1, 2, -2602, 0),
    (2, -1, -2, 0, 2390, 10056),
    (1, 0, 1, 0, -2348, 6322),
    (2, -2, 0, 0, 2236, -9884),
    (0, 1, 2, 0, -2120, 5751),
    (0, 2, 0, 0, -2069, 0),
    (2, -2, -1, 0, 2048, -4950),
    (2, 0, 1, -2, -1773, 4130),
    (2, 0, 0, 2, -1595, 0),
    (4, -1, -1, 0, 1215, -3958),
    (0, 0, 2, 2, -1110, 0),
    (3, 0, -1, 0, -892, 3258),
    (2, 1, 1, 0, -810, 2616),
    (4, -1, -2, 0, 759, -1897),
    (0, 2, -1, 0, -713, -2117),
    (2, 2, -1, 0, -700, 2354),
    (2, 1, -2, 0, 691, 0),
    (2, -1, 0, -2, 596, 0),
    (4, 0, 1, 0, 549, -1423),
    (0, 0, 4, 0, 537, -1117),
    (4, -1, 0, 0, 520, -1571),
    (1, 0, -2, 0, -487, -1739),
    (2, 1, 0, -2, -399, 0),
    (0, 0, 2, -2, -381, -4421),
    (1, 1, 1, 0, 351, 0),
    (3, 0, -2, 0, -340, 0),
    (4, 0, -3, 0, 330, 0),
    (2, -1, 2, 0, 327, 0),
    (0, 2, 1, 0, -323, 1165),
    (1, 1, -1, 0, 299, 0),
    (2, 0, 3, 0, 294, 0),
    (2, 0, -1, -2, 0, 8752),
]

# (D, M, M', F, coefficient in ΣB [1e-6 deg])
_MOON_B = [
    (0, 0, 0, 1, 5128122),
    (0, 0, 1, 1, 280602),
    (0, 0, 1, -1, 277693),
    (2, 0, 0, -1, 173237),
    (2, 0, -1, 1, 55413),
    (2, 0, -1, -1, 46271),
    (2, 0, 0, 1, 32573),
    (0, 0, 2, 1, 17198),
    (2, 0, 1, -1, 9266),
    (0, 0, 2, -1, 8822),
    (2, -1, 0, -1, 8216),
    (2, 0, -2, -1, 4324),
    (2, 0, 1, 1, 4200),
    (2, 1, 0, -1, -3359),
    (2, -1, -1, 1, 2463),
    (2, -1, 0, 1, 2211),
    (2, -1, -1, -1, 2065),
    (0, 1, -1, -1, -1870),
    (4, 0, -1, -1, 1828),
    (0, 1, 0, 1, -1794),
    (0, 0, 0, 3, -1749),
    (0, 1, -1, 1, -1565),
    (1, 0, 0, 1, -1491),
    (0, 1, 1, 1, -1475),
    (0, 1, 1, -1, -1410),
    (0, 1, 0, -1, -1344),
    (1, 0, 0, -1, -1335),
    (0, 0, 3, 1, 1107),
    (4, 0, 0, -1, 1021),
    (4, 0, -1, 1, 833),
    (0, 0, 1, -3, 777),
    (4, 0, -2, 1, 671),
    (2, 0, 0, -3, 607),
    (2, 0, 2, -1, 596),
    (2, -1, 1, -1, 491),
    (2, 0, -2, 1, -451),
    (0, 0, 3, -1, 439),
    (2, 0, 2, 1, 422),
    (2, 0, -3, -1, 421),
    (2, 1, -1, 1, -366),
    (2, 1, 0, 1, -351),
    (4, 0, 0, 1, 331),
    (2, -1, 1, 1, 315),
    (2, -2, 0, -1, 302),
    (0, 0, 1, 3, -283),
    (2, 1, 1, -1, -229),
    (1, 1, 0, -1, 223),
    (1, 1, 0, 1, 223),
    (0, 1, -2, -1, -220),
    (2, 1, -1, -1, -220),
    (1, 0, 1, 1, -185),
    (2, -1, -2, -1, 181),
    (0, 1, 2, 1, -177),
    (4, 0, -2, -1, 176),
    (4, -1, -1, -1, 166),
    (1, 0, 1, -1, -164),
    (4, 0, 1, -1, 132),
    (1, 0, -1, -1, -119),
    (4, -1, 0, -1, 115),
    (2, -2, 0, 1, 107),
]


def moon_position(jd_tt: float) -> Position:
    """Apparent geocentric position of the Moon. Meeus ch. 47."""
    t = julian_centuries(jd_tt)

    lp = 218.3164477 + 481267.88123421 * t - 0.0015786 * t**2 + t**3 / 538841 - t**4 / 65194000
    d = 297.8501921 + 445267.1114034 * t - 0.0018819 * t**2 + t**3 / 545868 - t**4 / 113065000
    m = 357.5291092 + 35999.0502909 * t - 0.0001536 * t**2 + t**3 / 24490000
    mp = 134.9633964 + 477198.8675055 * t + 0.0087414 * t**2 + t**3 / 69699 - t**4 / 14712000
    f = 93.2720950 + 483202.0175233 * t - 0.0036539 * t**2 - t**3 / 3526000 + t**4 / 863310000

    a1 = 119.75 + 131.849 * t
    a2 = 53.09 + 479264.290 * t
    a3 = 313.45 + 481266.484 * t
    e = 1 - 0.002516 * t - 0.0000074 * t * t

    sum_l = 0.0
    sum_r = 0.0
    for cd, cm, cmp_, cf, coef_l, coef_r in _MOON_LR:
        arg = cd * d + cm * m + cmp_ * mp + cf * f
        # Terms in M depend on the Earth's eccentricity, which changes secularly.
        ecc = e ** abs(cm)
        sum_l += coef_l * ecc * dsin(arg)
        sum_r += coef_r * ecc * dcos(arg)

    sum_b = 0.0
    for cd, cm, cmp_, cf, coef_b in _MOON_B:
        arg = cd * d + cm * m + cmp_ * mp + cf * f
        sum_b += coef_b * (e ** abs(cm)) * dsin(arg)

    # Additive terms for Venus, Jupiter and the flattening of the Earth.
    sum_l += 3958 * dsin(a1) + 1962 * dsin(lp - f) + 318 * dsin(a2)
    sum_b += (
        -2235 * dsin(lp)
        + 382 * dsin(a3)
        + 175 * dsin(a1 - f)
        + 175 * dsin(a1 + f)
        + 127 * dsin(lp - mp)
        - 115 * dsin(lp + mp)
    )

    longitude = normalize_degrees(lp + sum_l / 1_000_000.0)
    latitude = sum_b / 1_000_000.0
    distance_km = 385000.56 + sum_r / 1000.0

    # Nutation in longitude (principal term) to reach apparent coordinates.
    omega = 125.04452 - 1934.136261 * t
    nutation = (-17.20 * dsin(omega) - 1.32 * dsin(2 * (280.4665 + 36000.7698 * t))) / 3600.0

    return Position(
        body="Moon",
        jd_tt=jd_tt,
        longitude=normalize_degrees(longitude + nutation),
        latitude=latitude,
        distance_au=distance_km / 149_597_870.7,
        accuracy_degrees=0.005,
        model=f"{MEEUS}, ch. 47 (abridged ELP-2000/82)",
    )


def moon_phase_angle(jd_tt: float) -> float:
    """Elongation of the Moon from the Sun in degrees: 0 = new, 180 = full."""
    return normalize_degrees(moon_position(jd_tt).longitude - sun_position(jd_tt).longitude)


def moon_illuminated_fraction(jd_tt: float) -> float:
    return (1 - dcos(moon_phase_angle(jd_tt))) / 2.0


MOON_PHASE_NAMES = [
    "New Moon",
    "Waxing Crescent",
    "First Quarter",
    "Waxing Gibbous",
    "Full Moon",
    "Waning Gibbous",
    "Last Quarter",
    "Waning Crescent",
]


def moon_phase_name(jd_tt: float) -> str:
    angle = moon_phase_angle(jd_tt)
    # Name the four exact phases only within ±1.5° of the true aspect; otherwise the
    # intermediate name is the accurate description.
    for index, centre in enumerate((0.0, 90.0, 180.0, 270.0)):
        if min(abs(angle - centre), 360 - abs(angle - centre)) < 1.5:
            return MOON_PHASE_NAMES[index * 2]
    return MOON_PHASE_NAMES[int((angle + 22.5) % 360 // 45)]


# --------------------------------------------------------------------------------------
# Planets — JPL Keplerian approximation, 3000 BCE to 3000 CE
# --------------------------------------------------------------------------------------

# name: (a, a., e, e., I, I., L, L., varpi, varpi., Omega, Omega.)  [au, deg, per century]
_PLANET_ELEMENTS: dict[str, tuple[float, ...]] = {
    "Mercury": (
        0.38709843,
        0.00000000,
        0.20563661,
        0.00002123,
        7.00559432,
        -0.00590158,
        252.25166724,
        149472.67486623,
        77.45771895,
        0.15940013,
        48.33961819,
        -0.12214182,
    ),
    "Venus": (
        0.72332102,
        -0.00000026,
        0.00676399,
        -0.00005107,
        3.39777545,
        0.00043494,
        181.97970850,
        58517.81560260,
        131.76755713,
        0.05679648,
        76.67261496,
        -0.27274174,
    ),
    "Earth": (
        1.00000018,
        -0.00000003,
        0.01673163,
        -0.00003661,
        -0.00054346,
        -0.01337178,
        100.46691572,
        35999.37306329,
        102.93005885,
        0.31795260,
        -5.11260389,
        -0.24123856,
    ),
    "Mars": (
        1.52371243,
        0.00000097,
        0.09336511,
        0.00009149,
        1.85181869,
        -0.00724757,
        -4.56813164,
        19140.29934243,
        -23.91744784,
        0.45223625,
        49.71320984,
        -0.26852431,
    ),
    "Jupiter": (
        5.20248019,
        -0.00002864,
        0.04853590,
        0.00018026,
        1.29861416,
        -0.00322699,
        34.33479152,
        3034.90371757,
        14.27495244,
        0.18199196,
        100.29282654,
        0.13024619,
    ),
    "Saturn": (
        9.54149883,
        -0.00003065,
        0.05550825,
        -0.00032044,
        2.49424102,
        0.00451969,
        50.07571329,
        1222.11494724,
        92.86136063,
        0.54179478,
        113.63998702,
        -0.25015002,
    ),
    "Uranus": (
        19.18797948,
        -0.00020455,
        0.04685740,
        -0.00001550,
        0.77298127,
        -0.00180155,
        314.20276625,
        428.49512595,
        172.43404441,
        0.09266985,
        73.96250215,
        0.05739699,
    ),
    "Neptune": (
        30.06952752,
        0.00006447,
        0.00895439,
        0.00000818,
        1.77005520,
        0.00022400,
        304.22289287,
        218.46515314,
        46.68158724,
        0.01009938,
        131.78635853,
        -0.00606302,
    ),
}

# Additional long-period corrections to the mean anomaly, required for the giant planets
# over the extended 3000 BCE – 3000 CE interval: (b, c, s, f)
_PLANET_EXTRA: dict[str, tuple[float, float, float, float]] = {
    "Jupiter": (-0.00012452, 0.06064060, -0.35635438, 38.35125000),
    "Saturn": (0.00025899, -0.13434469, 0.87320147, 38.35125000),
    "Uranus": (0.00058331, -0.97731848, 0.17689245, 7.67025000),
    "Neptune": (-0.00041348, 0.68346318, -0.10162547, 7.67025000),
}

#: Documented worst-case error of the Standish approximation over 3000 BCE – 3000 CE,
#: converted from arcseconds of geocentric angle to degrees.
_PLANET_ACCURACY_DEGREES: dict[str, float] = {
    "Mercury": 0.4,
    "Venus": 0.3,
    "Mars": 0.6,
    "Jupiter": 0.3,
    "Saturn": 0.5,
    "Uranus": 0.4,
    "Neptune": 0.3,
}

NAKED_EYE_PLANETS = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn"]
ALL_PLANETS = NAKED_EYE_PLANETS + ["Uranus", "Neptune"]


def _heliocentric_ecliptic(body: str, jd_tt: float) -> tuple[float, float, float]:
    """Rectangular heliocentric ecliptic coordinates (au), J2000 frame."""
    t = julian_centuries(jd_tt)
    (a0, ad, e0, ed, i0, idot, l0, ldot, w0, wdot, o0, odot) = _PLANET_ELEMENTS[body]

    a = a0 + ad * t
    e = e0 + ed * t
    inc = i0 + idot * t
    mean_longitude = l0 + ldot * t
    varpi = w0 + wdot * t
    node = o0 + odot * t

    mean_anomaly = mean_longitude - varpi
    if body in _PLANET_EXTRA:
        b, c, s, f = _PLANET_EXTRA[body]
        mean_anomaly += b * t * t + c * dcos(f * t) + s * dsin(f * t)

    mean_anomaly = ((mean_anomaly + 180.0) % 360.0) - 180.0

    # Kepler's equation, solved in degrees (Newton-Raphson; converges in a few passes at
    # these eccentricities).
    e_star = math.degrees(e)
    ecc_anomaly = mean_anomaly + e_star * dsin(mean_anomaly)
    for _ in range(12):
        delta_m = mean_anomaly - (ecc_anomaly - e_star * dsin(ecc_anomaly))
        delta_e = delta_m / (1 - e * dcos(ecc_anomaly))
        ecc_anomaly += delta_e
        if abs(delta_e) < 1e-10:
            break

    # In the orbital plane...
    x_orb = a * (dcos(ecc_anomaly) - e)
    y_orb = a * math.sqrt(max(0.0, 1 - e * e)) * dsin(ecc_anomaly)

    # ...then rotate by argument of perihelion, inclination and ascending node.
    arg_peri = varpi - node
    cos_w, sin_w = dcos(arg_peri), dsin(arg_peri)
    cos_o, sin_o = dcos(node), dsin(node)
    cos_i, sin_i = dcos(inc), dsin(inc)

    x = (cos_w * cos_o - sin_w * sin_o * cos_i) * x_orb + (
        -sin_w * cos_o - cos_w * sin_o * cos_i
    ) * y_orb
    y = (cos_w * sin_o + sin_w * cos_o * cos_i) * x_orb + (
        -sin_w * sin_o + cos_w * cos_o * cos_i
    ) * y_orb
    z = (sin_w * sin_i) * x_orb + (cos_w * sin_i) * y_orb
    return x, y, z


def planet_position(body: str, jd_tt: float) -> Position:
    """Geocentric ecliptic position of a planet, corrected for light-time."""
    if body not in _PLANET_ELEMENTS or body == "Earth":
        raise ValueError(f"Unknown planet: {body!r}")

    ex, ey, ez = _heliocentric_ecliptic("Earth", jd_tt)

    # One light-time iteration: the planet is seen where it was when the light left.
    px, py, pz = _heliocentric_ecliptic(body, jd_tt)
    for _ in range(2):
        dx, dy, dz = px - ex, py - ey, pz - ez
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        light_days = distance * 0.0057755183
        px, py, pz = _heliocentric_ecliptic(body, jd_tt - light_days)

    dx, dy, dz = px - ex, py - ey, pz - ez
    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
    longitude = normalize_degrees(math.degrees(math.atan2(dy, dx)))
    latitude = math.degrees(math.asin(dz / distance)) if distance else 0.0

    return Position(
        body=body,
        jd_tt=jd_tt,
        longitude=longitude,
        latitude=latitude,
        distance_au=distance,
        accuracy_degrees=_PLANET_ACCURACY_DEGREES[body],
        model=f"{JPL_REFERENCE} (valid 3000 BCE – 3000 CE)",
    )


def body_position(body: str, jd_tt: float) -> Position:
    """Uniform accessor across Sun, Moon and planets."""
    name = body.strip().title()
    if name == "Sun":
        return sun_position(jd_tt)
    if name == "Moon":
        return moon_position(jd_tt)
    return planet_position(name, jd_tt)


def all_positions(jd_tt: float, bodies: list[str] | None = None) -> list[Position]:
    return [body_position(b, jd_tt) for b in (bodies or (["Sun", "Moon"] + NAKED_EYE_PLANETS))]


def is_retrograde(body: str, jd_tt: float, step_days: float = 1.0) -> bool:
    """Apparent retrograde motion: geocentric ecliptic longitude decreasing."""
    before = body_position(body, jd_tt - step_days).longitude
    after = body_position(body, jd_tt + step_days).longitude
    delta = ((after - before + 180.0) % 360.0) - 180.0
    return delta < 0


__all__ = [
    "Position",
    "ZODIAC_SIGNS",
    "MOON_PHASE_NAMES",
    "NAKED_EYE_PLANETS",
    "ALL_PLANETS",
    "JPL_REFERENCE",
    "sun_position",
    "moon_position",
    "moon_phase_angle",
    "moon_illuminated_fraction",
    "moon_phase_name",
    "planet_position",
    "body_position",
    "all_positions",
    "is_retrograde",
]
