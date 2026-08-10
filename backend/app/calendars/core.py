"""Calendar conversion engine.

Every calendar is converted through a single intermediate representation: the **Rata Die**
(RD) fixed day number, where RD 1 = Monday, 1 January 1 CE in the proleptic Gregorian
calendar. This is the approach of Dershowitz & Reingold, *Calendrical Calculations*
(4th ed., Cambridge University Press, 2018), and it keeps every pairwise conversion
exact by construction.

Two conventions used throughout, because mixing them is the single most common source
of off-by-one-year errors in historical work:

* **Astronomical year numbering.** Year 0 exists and equals 1 BCE; -1 equals 2 BCE.
  All integers in this module are astronomical unless a field is explicitly named `bce`.
* **Proleptic extension.** Gregorian and Julian dates are extended backwards past their
  historical introduction (1582 CE and 45 BCE respectively). A proleptic date is a
  *label*, not a claim that anybody used it.

Where a calendar cannot be converted exactly — because its months began on observation
rather than arithmetic, or because intercalation was decided by an official — the
conversion still returns a value but attaches an explicit uncertainty note. The platform
never silently upgrades an approximation to a fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date

# --------------------------------------------------------------------------------------
# Julian Day <-> RD
# --------------------------------------------------------------------------------------

#: RD of Julian Day Number 0. JDN 0 began at noon on 1 January 4713 BCE (Julian).
JD_EPOCH_RD = -1721425


def rd_from_jdn(jdn: int) -> int:
    return jdn + JD_EPOCH_RD


def jdn_from_rd(rd: int) -> int:
    return rd - JD_EPOCH_RD


def jd_from_rd(rd: int, day_fraction: float = 0.5) -> float:
    """Julian Date (a real number). `day_fraction` 0.5 = noon, which is JD's own epoch
    convention; 0.0 gives midnight at the start of the RD day."""
    return (rd - JD_EPOCH_RD) - 0.5 + day_fraction


def rd_from_jd(jd: float) -> int:
    return int((jd + 0.5) // 1) + JD_EPOCH_RD


# --------------------------------------------------------------------------------------
# Gregorian
# --------------------------------------------------------------------------------------

GREGORIAN_EPOCH = 1


def gregorian_leap_year(year: int) -> bool:
    return year % 4 == 0 and year % 400 not in (100, 200, 300)


def gregorian_to_rd(year: int, month: int, day: int) -> int:
    prior = year - 1
    correction = 0 if month <= 2 else (-1 if gregorian_leap_year(year) else -2)
    return (
        GREGORIAN_EPOCH
        - 1
        + 365 * prior
        + prior // 4
        - prior // 100
        + prior // 400
        + (367 * month - 362) // 12
        + correction
        + day
    )


def gregorian_year_from_rd(rd: int) -> int:
    d0 = rd - GREGORIAN_EPOCH
    n400, d1 = divmod(d0, 146097)
    n100, d2 = divmod(d1, 36524)
    n4, d3 = divmod(d2, 1461)
    n1 = d3 // 365
    year = 400 * n400 + 100 * n100 + 4 * n4 + n1
    return year if (n100 == 4 or n1 == 4) else year + 1


def rd_to_gregorian(rd: int) -> tuple[int, int, int]:
    year = gregorian_year_from_rd(rd)
    prior_days = rd - gregorian_to_rd(year, 1, 1)
    if rd < gregorian_to_rd(year, 3, 1):
        correction = 0
    elif gregorian_leap_year(year):
        correction = 1
    else:
        correction = 2
    month = (12 * (prior_days + correction) + 373) // 367
    day = rd - gregorian_to_rd(year, month, 1) + 1
    return year, month, day


# --------------------------------------------------------------------------------------
# Julian
# --------------------------------------------------------------------------------------

JULIAN_EPOCH = gregorian_to_rd(0, 12, 30)


def julian_leap_year(year: int) -> bool:
    """Astronomical year numbering, so this is a plain divisibility test — 1 BCE (year 0)
    and 5 BCE (year -4) are leap years in the proleptic Julian calendar."""
    return year % 4 == 0


def julian_to_rd(year: int, month: int, day: int) -> int:
    correction = 0 if month <= 2 else (-1 if julian_leap_year(year) else -2)
    return (
        JULIAN_EPOCH
        - 1
        + 365 * (year - 1)
        + (year - 1) // 4  # Python floor division is correct for negative years
        + (367 * month - 362) // 12
        + correction
        + day
    )


def rd_to_julian(rd: int) -> tuple[int, int, int]:
    year = (4 * (rd - JULIAN_EPOCH) + 1464) // 1461
    # The linear estimate can land one year either side near a boundary; settle it.
    while julian_to_rd(year, 1, 1) > rd:
        year -= 1
    while julian_to_rd(year + 1, 1, 1) <= rd:
        year += 1
    prior_days = rd - julian_to_rd(year, 1, 1)
    if rd < julian_to_rd(year, 3, 1):
        correction = 0
    elif julian_leap_year(year):
        correction = 1
    else:
        correction = 2
    month = (12 * (prior_days + correction) + 373) // 367
    day = rd - julian_to_rd(year, month, 1) + 1
    return year, month, day


# --------------------------------------------------------------------------------------
# Hebrew (arithmetic, post-Hillel II)
# --------------------------------------------------------------------------------------

#: 7 October 3761 BCE (Julian) = astronomical year -3760. This is RD -1373427, the
#: traditional epoch of the Hebrew calendar (creation, per rabbinic reckoning).
HEBREW_EPOCH = julian_to_rd(-3760, 10, 7)

HEBREW_MONTH_NAMES = [
    "Nisan",
    "Iyyar",
    "Sivan",
    "Tammuz",
    "Av",
    "Elul",
    "Tishri",
    "Marheshvan",
    "Kislev",
    "Tevet",
    "Shevat",
    "Adar",
    "Adar II",
]


def hebrew_leap_year(year: int) -> bool:
    """19-year Metonic cycle: 7 leap years, in positions 3, 6, 8, 11, 14, 17, 19."""
    return ((7 * year + 1) % 19) < 7


def hebrew_last_month_of_year(year: int) -> int:
    return 13 if hebrew_leap_year(year) else 12


def _hebrew_elapsed_days(year: int) -> int:
    """Days from the epoch to 1 Tishri of `year`, before the postponement rules."""
    months_elapsed = (
        235 * ((year - 1) // 19)  # complete Metonic cycles
        + 12 * ((year - 1) % 19)  # regular years in the current cycle
        + (7 * ((year - 1) % 19) + 1) // 19  # leap months so far in the cycle
    )
    parts_elapsed = 12084 + 13753 * months_elapsed
    day = 29 * months_elapsed + parts_elapsed // 25920
    # Postponement (dehiyyah) for a molad at or after noon.
    return day + 1 if (3 * (day + 1)) % 7 < 3 else day


def _hebrew_year_length_correction(year: int) -> int:
    """The remaining postponement rules, which forbid years of certain lengths."""
    ny0 = _hebrew_elapsed_days(year - 1)
    ny1 = _hebrew_elapsed_days(year)
    ny2 = _hebrew_elapsed_days(year + 1)
    if ny2 - ny1 == 356:
        return 2
    if ny1 - ny0 == 382:
        return 1
    return 0


def hebrew_new_year(year: int) -> int:
    """RD of 1 Tishri."""
    return HEBREW_EPOCH + _hebrew_elapsed_days(year) + _hebrew_year_length_correction(year)


def hebrew_days_in_year(year: int) -> int:
    return hebrew_new_year(year + 1) - hebrew_new_year(year)


def hebrew_long_marheshvan(year: int) -> bool:
    return hebrew_days_in_year(year) in (355, 385)


def hebrew_short_kislev(year: int) -> bool:
    return hebrew_days_in_year(year) in (353, 383)


def hebrew_last_day_of_month(year: int, month: int) -> int:
    if month in (2, 4, 6, 10, 13):
        return 29
    if month == 12 and not hebrew_leap_year(year):
        return 29
    if month == 8 and not hebrew_long_marheshvan(year):
        return 29
    if month == 9 and hebrew_short_kislev(year):
        return 29
    return 30


def hebrew_to_rd(year: int, month: int, day: int) -> int:
    """Months are numbered from Nisan (1), the liturgical new year, while the *year*
    increments at Tishri (7) — an asymmetry inherent to the calendar, not a bug."""
    rd = hebrew_new_year(year) + day - 1
    if month < 7:  # Nisan..Elul, i.e. after Tishri in the same civil year
        for m in range(7, hebrew_last_month_of_year(year) + 1):
            rd += hebrew_last_day_of_month(year, m)
        for m in range(1, month):
            rd += hebrew_last_day_of_month(year, m)
    else:
        for m in range(7, month):
            rd += hebrew_last_day_of_month(year, m)
    return rd


def rd_to_hebrew(rd: int) -> tuple[int, int, int]:
    year = (rd - HEBREW_EPOCH) * 98496 // 35975351 + 1
    while hebrew_new_year(year) > rd:
        year -= 1
    while hebrew_new_year(year + 1) <= rd:
        year += 1
    # Months are numbered from Nisan but the year turns at Tishri, so a Hebrew year runs
    # 7..12/13 and then 1..6. Anything before Nisan 1 is in the first stretch.
    month = 7 if rd < hebrew_to_rd(year, 1, 1) else 1
    while rd > hebrew_to_rd(year, month, hebrew_last_day_of_month(year, month)):
        month += 1
    day = rd - hebrew_to_rd(year, month, 1) + 1
    return year, month, day


def hebrew_month_name(year: int, month: int) -> str:
    if month == 12 and hebrew_leap_year(year):
        return "Adar I"
    return HEBREW_MONTH_NAMES[month - 1]


# --------------------------------------------------------------------------------------
# Islamic (tabular / arithmetic)
# --------------------------------------------------------------------------------------

ISLAMIC_EPOCH = julian_to_rd(622, 7, 16)

ISLAMIC_MONTH_NAMES = [
    "Muharram",
    "Safar",
    "Rabi' al-awwal",
    "Rabi' al-thani",
    "Jumada al-awwal",
    "Jumada al-thani",
    "Rajab",
    "Sha'ban",
    "Ramadan",
    "Shawwal",
    "Dhu al-Qi'dah",
    "Dhu al-Hijjah",
]


def islamic_to_rd(year: int, month: int, day: int) -> int:
    return (
        ISLAMIC_EPOCH
        - 1
        + (year - 1) * 354
        + (3 + 11 * year) // 30
        + 29 * (month - 1)
        + month // 2
        + day
    )


def rd_to_islamic(rd: int) -> tuple[int, int, int]:
    year = (30 * (rd - ISLAMIC_EPOCH) + 10646) // 10631
    month = min(12, (rd - islamic_to_rd(year, 1, 1)) // 29 + 1)
    while islamic_to_rd(year, month, 1) > rd:
        month -= 1
    day = rd - islamic_to_rd(year, month, 1) + 1
    return year, month, day


# --------------------------------------------------------------------------------------
# Egyptian civil (Nabonassar era) — the "wandering year"
# --------------------------------------------------------------------------------------

EGYPTIAN_EPOCH = rd_from_jdn(1448638)  # 26 February 747 BCE (Julian)

EGYPTIAN_MONTH_NAMES = [
    "Thoth",
    "Phaophi",
    "Athyr",
    "Choiak",
    "Tybi",
    "Mechir",
    "Phamenoth",
    "Pharmuthi",
    "Pachon",
    "Payni",
    "Epiphi",
    "Mesore",
    "Epagomenae",
]


def egyptian_to_rd(year: int, month: int, day: int) -> int:
    return EGYPTIAN_EPOCH + 365 * (year - 1) + 30 * (month - 1) + day - 1


def rd_to_egyptian(rd: int) -> tuple[int, int, int]:
    days = rd - EGYPTIAN_EPOCH
    year = days // 365 + 1
    month = (days % 365) // 30 + 1
    day = days - 365 * (year - 1) - 30 * (month - 1) + 1
    return year, month, day


# --------------------------------------------------------------------------------------
# Mayan
# --------------------------------------------------------------------------------------

#: Goodman–Martinez–Thompson correlation (JDN 584283). The competing 584285 variant
#: shifts every Long Count date two days later; both are reported by the engine.
MAYAN_EPOCH = rd_from_jdn(584283)
MAYAN_EPOCH_ALT_584285 = rd_from_jdn(584285)

MAYAN_HAAB_MONTHS = [
    "Pop",
    "Uo",
    "Zip",
    "Zotz",
    "Tzec",
    "Xul",
    "Yaxkin",
    "Mol",
    "Chen",
    "Yax",
    "Zac",
    "Ceh",
    "Mac",
    "Kankin",
    "Muan",
    "Pax",
    "Kayab",
    "Cumku",
    "Uayeb",
]

MAYAN_TZOLKIN_NAMES = [
    "Imix",
    "Ik",
    "Akbal",
    "Kan",
    "Chicchan",
    "Cimi",
    "Manik",
    "Lamat",
    "Muluc",
    "Oc",
    "Chuen",
    "Eb",
    "Ben",
    "Ix",
    "Men",
    "Cib",
    "Caban",
    "Etznab",
    "Cauac",
    "Ahau",
]

# 0.0.0.0.0 fell on 8 Cumku (day 348 of the haab) and 4 Ahau (day 159 of the tzolkin).
MAYAN_HAAB_EPOCH = MAYAN_EPOCH - 348
MAYAN_TZOLKIN_EPOCH = MAYAN_EPOCH - 159


def mayan_long_count_to_rd(baktun: int, katun: int, tun: int, uinal: int, kin: int) -> int:
    return MAYAN_EPOCH + baktun * 144000 + katun * 7200 + tun * 360 + uinal * 20 + kin


def rd_to_mayan_long_count(rd: int) -> tuple[int, int, int, int, int]:
    days = rd - MAYAN_EPOCH
    baktun, days = divmod(days, 144000)
    katun, days = divmod(days, 7200)
    tun, days = divmod(days, 360)
    uinal, kin = divmod(days, 20)
    return baktun, katun, tun, uinal, kin


def rd_to_mayan_haab(rd: int) -> tuple[int, str]:
    count = (rd - MAYAN_HAAB_EPOCH) % 365
    day, month = count % 20, count // 20
    return day, MAYAN_HAAB_MONTHS[month]


def rd_to_mayan_tzolkin(rd: int) -> tuple[int, str]:
    count = rd - MAYAN_TZOLKIN_EPOCH + 1
    number = (count - 1) % 13 + 1
    name = MAYAN_TZOLKIN_NAMES[(count - 1) % 20]
    return number, name


# --------------------------------------------------------------------------------------
# Coptic / Ethiopic
# --------------------------------------------------------------------------------------

COPTIC_EPOCH = julian_to_rd(284, 8, 29)
ETHIOPIC_EPOCH = julian_to_rd(8, 8, 29)

COPTIC_MONTH_NAMES = [
    "Thoout",
    "Paope",
    "Athor",
    "Koiak",
    "Tobe",
    "Meshir",
    "Paremotep",
    "Parmoute",
    "Pashons",
    "Paone",
    "Epep",
    "Mesore",
    "Epagomenae",
]
ETHIOPIC_MONTH_NAMES = [
    "Maskaram",
    "Teqemt",
    "Hedar",
    "Takhsas",
    "Ter",
    "Yakatit",
    "Magabit",
    "Miyazya",
    "Genbot",
    "Sane",
    "Hamle",
    "Nahase",
    "Paguemen",
]


def _alexandrian_to_rd(epoch: int, year: int, month: int, day: int) -> int:
    return epoch - 1 + 365 * (year - 1) + year // 4 + 30 * (month - 1) + day


def _rd_to_alexandrian(epoch: int, rd: int) -> tuple[int, int, int]:
    year = (4 * (rd - epoch) + 1463) // 1461
    month = (rd - _alexandrian_to_rd(epoch, year, 1, 1)) // 30 + 1
    day = rd + 1 - _alexandrian_to_rd(epoch, year, month, 1)
    return year, month, day


def coptic_to_rd(year: int, month: int, day: int) -> int:
    return _alexandrian_to_rd(COPTIC_EPOCH, year, month, day)


def rd_to_coptic(rd: int) -> tuple[int, int, int]:
    return _rd_to_alexandrian(COPTIC_EPOCH, rd)


def ethiopic_to_rd(year: int, month: int, day: int) -> int:
    return _alexandrian_to_rd(ETHIOPIC_EPOCH, year, month, day)


def rd_to_ethiopic(rd: int) -> tuple[int, int, int]:
    return _rd_to_alexandrian(ETHIOPIC_EPOCH, rd)


# --------------------------------------------------------------------------------------
# Persian (arithmetic / Birashk approximation of the Jalali calendar)
# --------------------------------------------------------------------------------------

PERSIAN_EPOCH = julian_to_rd(622, 3, 19)

PERSIAN_MONTH_NAMES = [
    "Farvardin",
    "Ordibehesht",
    "Khordad",
    "Tir",
    "Mordad",
    "Shahrivar",
    "Mehr",
    "Aban",
    "Azar",
    "Dey",
    "Bahman",
    "Esfand",
]


def _persian_leap(year: int) -> bool:
    y = year - 474 if year > 0 else year - 473
    return ((((y % 2820) + 474 + 38) * 682) % 2816) < 682


def persian_to_rd(year: int, month: int, day: int) -> int:
    y = year - 474 if year > 0 else year - 473
    epy = y % 2820 + 474
    md = 31 * (month - 1) if month <= 7 else 30 * (month - 1) + 6
    return (
        PERSIAN_EPOCH
        - 1
        + 1029983 * (y // 2820)
        + 365 * (epy - 1)
        + (31 * epy - 5) // 128
        + md
        + day
    )


def rd_to_persian(rd: int) -> tuple[int, int, int]:
    year = _persian_year_from_rd(rd)
    day_of_year = rd - persian_to_rd(year, 1, 1) + 1
    month = day_of_year // 31 + 1 if day_of_year <= 186 else (day_of_year - 6) // 30 + 1
    day = rd - persian_to_rd(year, month, 1) + 1
    return year, month, day


def _persian_year_from_rd(rd: int) -> int:
    approx = (rd - PERSIAN_EPOCH) * 1029983 // 376194365 + 474
    year = approx
    while persian_to_rd(year + 1, 1, 1) <= rd:
        year += 1
    while persian_to_rd(year, 1, 1) > rd:
        year -= 1
    return year


# --------------------------------------------------------------------------------------
# Chinese sexagenary cycle
# --------------------------------------------------------------------------------------

HEAVENLY_STEMS = ["Jia", "Yi", "Bing", "Ding", "Wu", "Ji", "Geng", "Xin", "Ren", "Gui"]
EARTHLY_BRANCHES = [
    "Zi",
    "Chou",
    "Yin",
    "Mao",
    "Chen",
    "Si",
    "Wu",
    "Wei",
    "Shen",
    "You",
    "Xu",
    "Hai",
]
CHINESE_ZODIAC = [
    "Rat",
    "Ox",
    "Tiger",
    "Rabbit",
    "Dragon",
    "Snake",
    "Horse",
    "Goat",
    "Monkey",
    "Rooster",
    "Dog",
    "Pig",
]


def chinese_sexagenary_year(gregorian_year: int) -> dict[str, str | int]:
    """The 60-year stem-branch cycle.

    This is the *year* cycle only. The Chinese lunisolar calendar's month and day
    numbering requires solar-term and new-moon computation tied to a specific meridian,
    which the engine does not attempt; a text dated by a stem-branch year is therefore
    resolved to a Gregorian year, not a Gregorian day.
    """
    index = (gregorian_year - 4) % 60
    return {
        "cycle_position": index + 1,
        "stem": HEAVENLY_STEMS[index % 10],
        "branch": EARTHLY_BRANCHES[index % 12],
        "zodiac_animal": CHINESE_ZODIAC[index % 12],
        "label": f"{HEAVENLY_STEMS[index % 10]}-{EARTHLY_BRANCHES[index % 12]} "
        f"({CHINESE_ZODIAC[index % 12]})",
    }


# --------------------------------------------------------------------------------------
# Era systems (year-only)
# --------------------------------------------------------------------------------------


def era_conversions(astronomical_year: int) -> dict[str, str]:
    """Year-level era labels commonly found in ancient and medieval texts.

    These map a year to a year — no day precision is implied, and each era's own new-year
    boundary differs from 1 January, so a date near a year boundary can legitimately fall
    in either of two era years.
    """
    out: dict[str, str] = {}

    auc = astronomical_year + 753  # Varronian foundation of Rome, 753 BCE
    if auc > 0:
        out["ab_urbe_condita"] = f"AUC {auc} (Varronian reckoning; ancient authors vary)"

    seleucid = astronomical_year - 311  # autumn 312 BCE Babylonian / 311 Macedonian
    if seleucid > 0:
        out["seleucid"] = (
            f"AG {seleucid} (Seleucid era; Babylonian and Macedonian reckonings differ by ~6 months)"
        )

    diocletian = astronomical_year - 283
    if diocletian > 0:
        out["anno_martyrum"] = f"AM {diocletian} (Era of the Martyrs / Diocletian)"

    if astronomical_year >= -775:
        # Olympiads run from summer 776 BCE, in four-year cycles.
        offset = astronomical_year + 776
        olympiad, year_in = divmod(offset, 4)
        out["olympiad"] = f"Ol. {olympiad + 1}.{year_in + 1} (Olympiad years begin in midsummer)"

    byz = astronomical_year + 5508  # Byzantine Anno Mundi, epoch 1 Sept 5509 BCE
    if byz > 0:
        out["anno_mundi_byzantine"] = f"AM {byz} (Byzantine; year begins 1 September)"

    return out


# --------------------------------------------------------------------------------------
# Public result types
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class CalendarDate:
    """A date in one calendar system, plus everything a reader needs to judge it."""

    system: str
    year: int
    month: int | None
    day: int | None
    label: str
    month_name: str | None = None
    is_exact: bool = True
    uncertainty_note: str | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "system": self.system,
            "year": self.year,
            "month": self.month,
            "day": self.day,
            "month_name": self.month_name,
            "label": self.label,
            "is_exact": self.is_exact,
            "uncertainty_note": self.uncertainty_note,
            **({"extra": self.extra} if self.extra else {}),
        }


def format_gregorian(year: int, month: int, day: int) -> str:
    """Human label using BCE/CE, converting out of astronomical year numbering."""
    month_name = _MONTH_NAMES[month - 1]
    if year <= 0:
        return f"{day} {month_name} {1 - year} BCE"
    return f"{day} {month_name} {year} CE"


_MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

WEEKDAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def weekday_from_rd(rd: int) -> str:
    """RD 1 was a Monday, so RD mod 7 == 0 is Sunday."""
    return WEEKDAY_NAMES[rd % 7]


def rd_from_python_date(value: _date) -> int:
    return gregorian_to_rd(value.year, value.month, value.day)


__all__ = [name for name in dir() if not name.startswith("_")]
