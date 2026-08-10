"""Calendar engine tests.

Anchors are dates with a published, checkable value — festival dates, epoch definitions,
and the widely-cited Long Count correspondences — rather than values produced by this
code. A test that only asserts self-consistency would pass on a systematically wrong
implementation.
"""

from __future__ import annotations

import random

import pytest

from app.calendars import core
from app.calendars.service import (
    CALENDARS,
    CalendarError,
    convert,
    convert_all,
    convert_mayan_long_count,
    gregorian_range_for_year,
    to_rd,
)


class TestGregorianJulian:
    def test_epoch(self):
        assert core.gregorian_to_rd(1, 1, 1) == 1

    def test_j2000_julian_day(self):
        assert core.jdn_from_rd(core.gregorian_to_rd(2000, 1, 1)) == 2451545

    def test_gregorian_reform(self):
        """4 October 1582 (Julian) was followed by 15 October (Gregorian)."""
        assert core.rd_to_gregorian(core.julian_to_rd(1582, 10, 4)) == (1582, 10, 14)

    def test_leap_year_rules(self):
        assert core.gregorian_leap_year(2000)
        assert not core.gregorian_leap_year(1900)
        assert core.gregorian_leap_year(2024)
        # Astronomical numbering: year 0 is 1 BCE and is a Julian leap year.
        assert core.julian_leap_year(0)
        assert core.julian_leap_year(-4)

    def test_bce_dates_use_astronomical_numbering(self):
        """44 BCE is astronomical year -43; the Ides of March fall there."""
        rd = core.julian_to_rd(-43, 3, 15)
        assert core.rd_to_julian(rd) == (-43, 3, 15)
        assert core.format_gregorian(*core.rd_to_gregorian(rd)).endswith("44 BCE")

    def test_weekday(self):
        assert core.weekday_from_rd(core.gregorian_to_rd(2024, 10, 3)) == "Thursday"
        assert core.weekday_from_rd(1) == "Monday"  # RD 1 is defined as a Monday


class TestHebrew:
    def test_epoch_is_traditional_value(self):
        assert core.HEBREW_EPOCH == -1373427

    @pytest.mark.parametrize(
        "hebrew,gregorian",
        [
            ((5785, 7, 1), (2024, 10, 3)),  # Rosh Hashanah 5785
            ((5784, 7, 1), (2023, 9, 16)),  # Rosh Hashanah 5784
            ((5784, 1, 15), (2024, 4, 23)),  # Passover 5784
            ((5784, 5, 9), (2024, 8, 13)),  # Tisha B'Av 5784
        ],
    )
    def test_known_festival_dates(self, hebrew, gregorian):
        assert core.rd_to_gregorian(core.hebrew_to_rd(*hebrew)) == gregorian

    def test_reverse_conversion(self):
        assert core.rd_to_hebrew(core.gregorian_to_rd(2024, 10, 3)) == (5785, 7, 1)

    def test_leap_years_follow_metonic_cycle(self):
        leaps = [y for y in range(5780, 5799) if core.hebrew_leap_year(y)]
        assert len(leaps) == 7  # 7 leap years per 19-year cycle

    def test_year_lengths_are_valid(self):
        for year in range(5700, 5800):
            assert core.hebrew_days_in_year(year) in (353, 354, 355, 383, 384, 385)

    def test_adar_naming_in_leap_years(self):
        assert core.hebrew_leap_year(5784)
        assert core.hebrew_month_name(5784, 12) == "Adar I"
        assert core.hebrew_month_name(5784, 13) == "Adar II"
        assert core.hebrew_month_name(5785, 12) == "Adar"


class TestIslamic:
    def test_epoch(self):
        assert core.ISLAMIC_EPOCH == core.julian_to_rd(622, 7, 16)

    def test_year_length(self):
        span = gregorian_range_for_year("islamic", 1446)
        assert span is not None
        assert span["day_count"] in (354, 355)

    def test_spans_two_gregorian_years(self):
        """A lunar year is shorter than a solar one, so it straddles the boundary."""
        span = gregorian_range_for_year("islamic", 1446)
        assert len(span["spans_gregorian_years"]) == 2

    def test_caveat_is_present(self):
        """The tabular/observational divergence must be stated, never silently ignored."""
        span = gregorian_range_for_year("islamic", 1446)
        assert "sighting" in span["uncertainty_note"].lower()


class TestMaya:
    def test_epoch_gmt_correlation(self):
        assert core.rd_to_gregorian(core.MAYAN_EPOCH) == (-3113, 8, 11)
        assert core.rd_to_julian(core.MAYAN_EPOCH) == (-3113, 9, 6)

    def test_baktun_13(self):
        rd = core.mayan_long_count_to_rd(13, 0, 0, 0, 0)
        assert core.rd_to_gregorian(rd) == (2012, 12, 21)

    def test_epoch_calendar_round(self):
        """0.0.0.0.0 fell on 4 Ahau 8 Cumku."""
        assert core.rd_to_mayan_tzolkin(core.MAYAN_EPOCH) == (4, "Ahau")
        assert core.rd_to_mayan_haab(core.MAYAN_EPOCH) == (8, "Cumku")

    def test_alternative_correlation_reported(self):
        result = convert_mayan_long_count(13, 0, 0, 0, 0)
        maya = next(c for c in result["conversions"] if c["system"] == "mayan_long_count")
        assert maya["extra"]["correlation"] == "GMT 584283"
        assert "alternative_584285" in maya["extra"]
        assert maya["is_exact"] is False


class TestOtherCalendars:
    def test_coptic(self):
        assert core.rd_to_coptic(core.gregorian_to_rd(2024, 1, 1)) == (1740, 4, 22)

    def test_ethiopic_new_year(self):
        year, month, day = core.rd_to_ethiopic(core.gregorian_to_rd(2024, 9, 11))
        assert (year, month, day) == (2017, 1, 1)

    def test_persian_nowruz(self):
        assert core.rd_to_gregorian(core.persian_to_rd(1403, 1, 1)) == (2024, 3, 20)

    def test_chinese_sexagenary(self):
        result = core.chinese_sexagenary_year(2024)
        assert result["stem"] == "Jia"
        assert result["branch"] == "Chen"
        assert result["zodiac_animal"] == "Dragon"

    def test_egyptian_wandering_year_has_no_leap_day(self):
        first = core.egyptian_to_rd(100, 1, 1)
        second = core.egyptian_to_rd(101, 1, 1)
        assert second - first == 365


class TestRoundTrips:
    @pytest.mark.parametrize(
        "to_fn,from_fn",
        [
            (core.rd_to_gregorian, core.gregorian_to_rd),
            (core.rd_to_julian, core.julian_to_rd),
            (core.rd_to_hebrew, core.hebrew_to_rd),
            (core.rd_to_islamic, core.islamic_to_rd),
            (core.rd_to_coptic, core.coptic_to_rd),
            (core.rd_to_ethiopic, core.ethiopic_to_rd),
            (core.rd_to_egyptian, core.egyptian_to_rd),
            (core.rd_to_persian, core.persian_to_rd),
        ],
    )
    def test_round_trip_over_four_millennia(self, to_fn, from_fn):
        rng = random.Random(20260807)  # fixed seed: a failure is reproducible
        for _ in range(500):
            rd = rng.randint(-700_000, 800_000)
            assert from_fn(*to_fn(rd)) == rd, f"{to_fn.__name__} failed at RD {rd}"

    def test_julian_day_round_trip(self):
        for rd in range(-100_000, 100_000, 997):
            assert core.rd_from_jdn(core.jdn_from_rd(rd)) == rd


class TestService:
    def test_convert_all_covers_every_system(self):
        result = convert_all(core.gregorian_to_rd(2024, 10, 3))
        systems = {c["system"] for c in result["conversions"]}
        assert systems == set(CALENDARS)

    def test_inexact_systems_carry_a_caveat(self):
        """Anything not exactly convertible must say why, every time."""
        result = convert_all(core.gregorian_to_rd(2024, 10, 3))
        for conversion in result["conversions"]:
            if not conversion["is_exact"]:
                assert conversion["uncertainty_note"], (
                    f"{conversion['system']} is inexact but gives no explanation"
                )

    def test_era_conversions(self):
        result = convert("gregorian", 2024, 10, 3)
        assert "ab_urbe_condita" in result["eras"]
        assert "AUC 2777" in result["eras"]["ab_urbe_condita"]
        assert "olympiad" in result["eras"]

    def test_unknown_system_rejected(self):
        with pytest.raises(CalendarError, match="Unknown calendar"):
            to_rd("klingon", 2024)

    def test_month_and_day_are_one_based(self):
        with pytest.raises(CalendarError):
            to_rd("gregorian", 2024, 0, 1)
