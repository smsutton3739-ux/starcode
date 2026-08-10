"""Calendar service: convert between systems and say honestly how good the answer is.

The engine's job is not merely to convert. It is to convert *and* to tell the reader which
part of the answer is arithmetic and which part is inference. A Gregorian date printed
without its caveats is the most common way ancient chronology gets misrepresented.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.calendars import core
from app.calendars.core import CalendarDate, format_gregorian, weekday_from_rd

# --------------------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CalendarSpec:
    key: str
    name: str
    culture: str
    kind: str
    epoch_description: str
    to_rd: Callable[[int, int, int], int] | None
    from_rd: Callable[[int], tuple[int, int, int]] | None
    month_names: list[str] = field(default_factory=list)
    exact: bool = True
    caveat: str | None = None
    active_from_year: int | None = None
    active_to_year: int | None = None
    references: list[str] = field(default_factory=list)


_RD_REFERENCE = (
    "Dershowitz, N. & Reingold, E. M., Calendrical Calculations: The Ultimate Edition "
    "(4th ed., Cambridge University Press, 2018)."
)

CALENDARS: dict[str, CalendarSpec] = {
    "gregorian": CalendarSpec(
        key="gregorian",
        name="Gregorian (proleptic)",
        culture="Modern international standard",
        kind="solar",
        epoch_description="1 January 1 CE (proleptic).",
        to_rd=core.gregorian_to_rd,
        from_rd=core.rd_to_gregorian,
        month_names=core._MONTH_NAMES,
        caveat=(
            "Introduced 15 October 1582 and adopted piecemeal thereafter (Britain and its "
            "colonies in 1752, Russia in 1918). Dates before adoption are proleptic labels "
            "for the purpose of comparison, not dates anyone recorded."
        ),
        references=[_RD_REFERENCE],
    ),
    "julian": CalendarSpec(
        key="julian",
        name="Julian (proleptic)",
        culture="Roman / Christian Europe",
        kind="solar",
        epoch_description="1 January 1 CE (Julian reckoning).",
        to_rd=core.julian_to_rd,
        from_rd=core.rd_to_julian,
        month_names=core._MONTH_NAMES,
        caveat=(
            "Instituted by Julius Caesar in 45 BCE. Between 45 BCE and roughly 8 CE the "
            "Roman priesthood inserted leap days on the wrong cycle; dates in that window "
            "carry an additional uncertainty of a few days that no arithmetic can remove."
        ),
        active_from_year=-44,
        references=[_RD_REFERENCE],
    ),
    "hebrew": CalendarSpec(
        key="hebrew",
        name="Hebrew (arithmetic)",
        culture="Jewish",
        kind="lunisolar",
        epoch_description="7 October 3761 BCE (Julian), the traditional date of creation.",
        to_rd=core.hebrew_to_rd,
        from_rd=core.rd_to_hebrew,
        month_names=core.HEBREW_MONTH_NAMES,
        caveat=(
            "The fixed arithmetic calendar used here was standardised in stages and was "
            "not fully settled until roughly the 10th century CE. Before that, months began "
            "on witnessed sighting of the new crescent, so projecting this calendar back "
            "into the Biblical or Second Temple period can be off by a day or more, and "
            "occasionally by a whole month in an intercalation year."
        ),
        references=[_RD_REFERENCE],
    ),
    "islamic": CalendarSpec(
        key="islamic",
        name="Islamic (tabular)",
        culture="Islamic",
        kind="lunar",
        epoch_description="16 July 622 CE (Julian), the Hijra.",
        to_rd=core.islamic_to_rd,
        from_rd=core.rd_to_islamic,
        month_names=core.ISLAMIC_MONTH_NAMES,
        exact=False,
        caveat=(
            "This is the tabular (arithmetic) Islamic calendar. Religious practice uses "
            "observed lunar crescent sighting, which routinely differs from the tabular "
            "date by one or two days and varies between countries in the same month."
        ),
        active_from_year=622,
        references=[_RD_REFERENCE],
    ),
    "egyptian": CalendarSpec(
        key="egyptian",
        name="Egyptian civil (Era of Nabonassar)",
        culture="Ancient Egyptian",
        kind="wandering solar",
        epoch_description="26 February 747 BCE (Julian), Era of Nabonassar.",
        to_rd=core.egyptian_to_rd,
        from_rd=core.rd_to_egyptian,
        month_names=core.EGYPTIAN_MONTH_NAMES,
        caveat=(
            "365 days exactly, with no leap day, so it drifts one day every four years "
            "against the seasons and completes a full cycle in 1,460 years. Egyptian texts "
            "are usually dated by regnal year rather than this era, and regnal chronology "
            "is itself debated; a conversion is only as firm as the reign it is anchored to."
        ),
        references=[_RD_REFERENCE],
    ),
    "coptic": CalendarSpec(
        key="coptic",
        name="Coptic (Era of the Martyrs)",
        culture="Coptic Christian",
        kind="solar",
        epoch_description="29 August 284 CE (Julian), accession of Diocletian.",
        to_rd=core.coptic_to_rd,
        from_rd=core.rd_to_coptic,
        month_names=core.COPTIC_MONTH_NAMES,
        active_from_year=284,
        references=[_RD_REFERENCE],
    ),
    "ethiopic": CalendarSpec(
        key="ethiopic",
        name="Ethiopic",
        culture="Ethiopian",
        kind="solar",
        epoch_description="29 August 8 CE (Julian).",
        to_rd=core.ethiopic_to_rd,
        from_rd=core.rd_to_ethiopic,
        month_names=core.ETHIOPIC_MONTH_NAMES,
        active_from_year=8,
        references=[_RD_REFERENCE],
    ),
    "persian": CalendarSpec(
        key="persian",
        name="Persian (arithmetic Jalali)",
        culture="Persian / Iranian",
        kind="solar",
        epoch_description="19 March 622 CE (Julian).",
        to_rd=core.persian_to_rd,
        from_rd=core.rd_to_persian,
        month_names=core.PERSIAN_MONTH_NAMES,
        exact=False,
        caveat=(
            "The arithmetic (Birashk) approximation is used. The observational Iranian "
            "calendar starts its year at the true vernal equinox measured at Tehran, so the "
            "two disagree by one day in a small number of years."
        ),
        active_from_year=622,
        references=[_RD_REFERENCE],
    ),
    "mayan_long_count": CalendarSpec(
        key="mayan_long_count",
        name="Maya Long Count",
        culture="Maya",
        kind="count of days",
        epoch_description="11 August 3114 BCE (proleptic Gregorian) under the GMT-584283 correlation.",
        to_rd=None,
        from_rd=None,
        exact=False,
        caveat=(
            "Depends entirely on the chosen correlation constant. This engine reports the "
            "Goodman–Martinez–Thompson value 584283 as primary and 584285 as the main "
            "alternative; the two differ by two days. Correlations outside this family have "
            "been proposed and would move dates by centuries."
        ),
        references=[
            _RD_REFERENCE,
            "Martin, S. & Skidmore, J., 'Exploring the 584286 Correlation between the Maya "
            "and European Calendars', The PARI Journal 13(2), 2012.",
        ],
    ),
    "chinese_sexagenary": CalendarSpec(
        key="chinese_sexagenary",
        name="Chinese sexagenary cycle",
        culture="Chinese",
        kind="cyclical",
        epoch_description="60-year stem-and-branch cycle.",
        to_rd=None,
        from_rd=None,
        exact=False,
        caveat=(
            "Year-level only. The full Chinese lunisolar calendar requires new-moon and "
            "solar-term computation referred to a specific meridian, and the meridian itself "
            "changed historically; this engine therefore resolves a stem-branch year to a "
            "Gregorian year and does not claim a day."
        ),
        references=[_RD_REFERENCE],
    ),
    "julian_day": CalendarSpec(
        key="julian_day",
        name="Julian Day Number",
        culture="Astronomical convention",
        kind="count of days",
        epoch_description="1 January 4713 BCE (Julian), noon.",
        to_rd=None,
        from_rd=None,
        references=["Meeus, J., Astronomical Algorithms (2nd ed., Willmann-Bell, 1998), ch. 7."],
    ),
}


def list_calendars() -> list[dict]:
    return [
        {
            "key": spec.key,
            "name": spec.name,
            "culture": spec.culture,
            "kind": spec.kind,
            "epoch_description": spec.epoch_description,
            "exact": spec.exact,
            "caveat": spec.caveat,
            "month_names": spec.month_names,
            "active_from_year": spec.active_from_year,
            "active_to_year": spec.active_to_year,
            "references": spec.references,
        }
        for spec in CALENDARS.values()
    ]


# --------------------------------------------------------------------------------------
# Conversion
# --------------------------------------------------------------------------------------


class CalendarError(ValueError):
    pass


def to_rd(system: str, year: int, month: int = 1, day: int = 1) -> int:
    """Convert a date in `system` to a Rata Die day number."""
    spec = CALENDARS.get(system)
    if spec is None:
        raise CalendarError(f"Unknown calendar system: {system!r}")
    if spec.to_rd is None:
        raise CalendarError(
            f"{spec.name} cannot be converted from a (year, month, day) triple; "
            "use the system-specific helper."
        )
    if month < 1 or day < 1:
        raise CalendarError("Month and day are 1-based.")
    return spec.to_rd(year, month, day)


def convert_all(rd: int, *, include_eras: bool = True) -> dict:
    """Render one instant in every supported calendar, with caveats attached."""
    results: list[CalendarDate] = []

    for spec in CALENDARS.values():
        if spec.from_rd is None:
            continue
        year, month, day = spec.from_rd(rd)
        month_name = (
            core.hebrew_month_name(year, month)
            if spec.key == "hebrew"
            else (spec.month_names[month - 1] if 0 < month <= len(spec.month_names) else None)
        )
        if spec.key == "gregorian":
            label = format_gregorian(year, month, day)
        elif spec.key == "julian":
            era = "CE" if year > 0 else "BCE"
            shown = year if year > 0 else 1 - year
            label = f"{day} {month_name} {shown} {era} (Julian)"
        else:
            label = f"{day} {month_name} {year}" if month_name else f"{year}-{month:02d}-{day:02d}"
        results.append(
            CalendarDate(
                system=spec.key,
                year=year,
                month=month,
                day=day,
                month_name=month_name,
                label=label,
                is_exact=spec.exact,
                uncertainty_note=spec.caveat,
            )
        )

    # Maya: three interlocking cycles, plus the correlation alternative.
    baktun, katun, tun, uinal, kin = core.rd_to_mayan_long_count(rd)
    haab_day, haab_month = core.rd_to_mayan_haab(rd)
    tz_num, tz_name = core.rd_to_mayan_tzolkin(rd)
    alt = core.rd_to_mayan_long_count(rd - (core.MAYAN_EPOCH_ALT_584285 - core.MAYAN_EPOCH))
    results.append(
        CalendarDate(
            system="mayan_long_count",
            year=baktun,
            month=katun,
            day=tun,
            label=f"{baktun}.{katun}.{tun}.{uinal}.{kin} — {tz_num} {tz_name}, {haab_day} {haab_month}",
            is_exact=False,
            uncertainty_note=CALENDARS["mayan_long_count"].caveat,
            extra={
                "long_count": [baktun, katun, tun, uinal, kin],
                "tzolkin": f"{tz_num} {tz_name}",
                "haab": f"{haab_day} {haab_month}",
                "correlation": "GMT 584283",
                "alternative_584285": ".".join(str(x) for x in alt),
            },
        )
    )

    greg_year = core.rd_to_gregorian(rd)[0]
    sexagenary = core.chinese_sexagenary_year(greg_year)
    results.append(
        CalendarDate(
            system="chinese_sexagenary",
            year=greg_year,
            month=None,
            day=None,
            label=str(sexagenary["label"]),
            is_exact=False,
            uncertainty_note=CALENDARS["chinese_sexagenary"].caveat,
            extra=dict(sexagenary),
        )
    )

    jdn = core.jdn_from_rd(rd)
    results.append(
        CalendarDate(
            system="julian_day",
            year=jdn,
            month=None,
            day=None,
            label=f"JDN {jdn}",
            is_exact=True,
            extra={"julian_date_noon": core.jd_from_rd(rd)},
        )
    )

    payload: dict = {
        "rd": rd,
        "weekday": weekday_from_rd(rd),
        "conversions": [r.to_dict() for r in results],
    }
    if include_eras:
        payload["eras"] = core.era_conversions(greg_year)
    return payload


def convert(system: str, year: int, month: int = 1, day: int = 1) -> dict:
    """Full conversion table starting from a date in any supported calendar."""
    rd = to_rd(system, year, month, day)
    result = convert_all(rd)
    result["input"] = {"system": system, "year": year, "month": month, "day": day}
    return result


def convert_mayan_long_count(
    baktun: int, katun: int, tun: int, uinal: int, kin: int, correlation: int = 584283
) -> dict:
    rd = core.rd_from_jdn(correlation) + (
        baktun * 144000 + katun * 7200 + tun * 360 + uinal * 20 + kin
    )
    result = convert_all(rd)
    result["input"] = {
        "system": "mayan_long_count",
        "long_count": [baktun, katun, tun, uinal, kin],
        "correlation": correlation,
    }
    return result


def gregorian_range_for_year(system: str, year: int) -> dict | None:
    """The Gregorian span covered by one year of another calendar.

    Most ancient dates are known only to the year, and a lunisolar or wandering year does
    not line up with a Gregorian one. Returning the span rather than a single date is the
    difference between "1446 AH" meaning "2024" and it meaning "part of 2024 and part of 2025".
    """
    spec = CALENDARS.get(system)
    if spec is None or spec.to_rd is None:
        return None
    start_rd = spec.to_rd(year, 1, 1)
    end_rd = spec.to_rd(year + 1, 1, 1) - 1
    sy, sm, sd = core.rd_to_gregorian(start_rd)
    ey, em, ed = core.rd_to_gregorian(end_rd)
    return {
        "system": system,
        "year": year,
        "gregorian_start": format_gregorian(sy, sm, sd),
        "gregorian_end": format_gregorian(ey, em, ed),
        "spans_gregorian_years": sorted({sy, ey}),
        "day_count": end_rd - start_rd + 1,
        "uncertainty_note": spec.caveat,
    }


__all__ = [
    "CalendarSpec",
    "CALENDARS",
    "CalendarError",
    "list_calendars",
    "to_rd",
    "convert",
    "convert_all",
    "convert_mayan_long_count",
    "gregorian_range_for_year",
]
