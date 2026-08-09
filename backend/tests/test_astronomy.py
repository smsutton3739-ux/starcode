"""Astronomy engine tests.

Validated against three independent external sources: Meeus' own worked examples, the
NASA Five Millennium Canon, and the historically attested anchor eclipses that ancient
chronology is built on. None of the expected values come from this implementation.
"""

from __future__ import annotations

import pytest

from app.astronomy import catalogs, events
from app.astronomy import service as astro
from app.astronomy.ephemeris import (
    ALL_PLANETS,
    is_retrograde,
    moon_illuminated_fraction,
    moon_position,
    planet_position,
    sun_position,
)
from app.astronomy.timescales import (
    delta_t_seconds,
    jd_from_gregorian,
    time_uncertainty,
)
from app.calendars.core import rd_from_jd, rd_to_julian

AU_KM = 149_597_870.7


class TestTimescales:
    def test_j2000_epoch(self):
        assert jd_from_gregorian(2000, 1, 1, 12.0) == pytest.approx(2451545.0, abs=1e-6)

    @pytest.mark.parametrize(
        "year,expected,tolerance",
        [
            (2000, 63.87, 0.5),   # Espenak & Meeus
            (1900, -2.8, 0.5),
            (1800, 13.7, 1.0),
            (-500, 17190, 100),
        ],
    )
    def test_delta_t_matches_published_values(self, year, expected, tolerance):
        assert delta_t_seconds(year) == pytest.approx(expected, abs=tolerance)

    def test_uncertainty_grows_into_antiquity(self):
        """This is the whole reason ancient eclipse visibility cannot be asserted."""
        modern = time_uncertainty(2000)
        ancient = time_uncertainty(-700)
        assert ancient.uncertainty_seconds > modern.uncertainty_seconds * 100
        assert ancient.longitude_uncertainty_degrees > 1
        assert "not settled by this calculation alone" in ancient.note

    def test_modern_uncertainty_is_stated_as_negligible(self):
        assert "known exactly" in time_uncertainty(2000).note


class TestEphemeris:
    def test_moon_matches_meeus_example_47a(self):
        """Meeus, Astronomical Algorithms 2nd ed., example 47.a (1992 April 12, 0h TD)."""
        position = moon_position(2448724.5)
        assert position.longitude == pytest.approx(133.167, abs=0.005)
        assert position.latitude == pytest.approx(-3.229, abs=0.005)
        assert position.distance_au * AU_KM == pytest.approx(368409.7, abs=1.0)

    def test_sun_matches_meeus_example_25b(self):
        """Meeus example 25.b (1992 October 13, 0h TD): apparent longitude 199.90988."""
        assert sun_position(2448908.5).longitude == pytest.approx(199.90988, abs=0.005)

    def test_planet_positions_at_j2000(self):
        """Cross-checked against published ephemerides for 2000 January 1."""
        expected = {
            "Mercury": 271.9, "Venus": 241.6, "Mars": 328.0,
            "Jupiter": 25.4, "Saturn": 40.0, "Uranus": 314.9, "Neptune": 303.2,
        }
        for body, longitude in expected.items():
            assert planet_position(body, 2451545.0).longitude == pytest.approx(
                longitude, abs=0.7
            ), f"{body} out of tolerance"

    def test_every_position_reports_its_accuracy(self):
        """A number without its accuracy cannot be labelled an astronomical_calculation."""
        for body in ["Sun", "Moon", *ALL_PLANETS]:
            from app.astronomy.ephemeris import body_position

            position = body_position(body, 2451545.0)
            assert position.accuracy_degrees > 0
            assert position.model

    def test_moon_phase_illumination(self):
        full = jd_from_gregorian(2024, 10, 17, 11.26)
        assert moon_illuminated_fraction(full) == pytest.approx(1.0, abs=0.01)

    def test_retrograde_detection(self):
        """Mars was retrograde in December 2022 and direct in June 2023."""
        assert is_retrograde("Mars", jd_from_gregorian(2022, 12, 1))
        assert not is_retrograde("Mars", jd_from_gregorian(2023, 6, 1))

    def test_unknown_body_rejected(self):
        with pytest.raises(ValueError, match="Unknown planet"):
            planet_position("Vulcan", 2451545.0)


class TestPhasesAndSeasons:
    def test_new_moon_matches_meeus_example_49a(self):
        assert events.moon_phase_time(-283) == pytest.approx(2443192.65118, abs=1e-4)

    def test_last_quarter_matches_meeus_example_49b(self):
        assert events.moon_phase_time(544.75) == pytest.approx(2467636.49186, abs=1e-4)

    def test_june_solstice_matches_meeus_example_27a(self):
        assert events.season_time(1962, 1) == pytest.approx(2437837.39245, abs=1e-4)

    def test_four_seasons_per_year(self):
        seasons = events.seasons_for_year(2024)
        assert len(seasons) == 4
        assert [s.month for s in seasons] == [3, 6, 9, 12]

    def test_phases_are_evenly_spaced(self):
        phases = events.moon_phases_in_range(2024, 2024, phases=(0.0,))
        assert 12 <= len(phases) <= 13
        gaps = [b.jd_tt - a.jd_tt for a, b in zip(phases, phases[1:])]
        assert all(29.2 < gap < 29.9 for gap in gaps)


class TestEclipses:
    def test_2017_solar_eclipses_match_nasa(self):
        found = events.eclipses_in_range(2017, 2017, "solar")
        assert len(found) == 2
        annular, total = found
        assert (annular.month, annular.day) == (2, 26)
        assert annular.details["eclipse_kind"] == "annular"
        assert annular.details["gamma"] == pytest.approx(-0.4581, abs=0.005)
        assert (total.month, total.day) == (8, 21)
        assert total.details["eclipse_kind"] == "total"
        assert total.details["gamma"] == pytest.approx(0.4367, abs=0.005)

    def test_1999_total_eclipse_gamma(self):
        found = events.eclipses_in_range(1999, 1999, "solar")
        august = next(e for e in found if e.month == 8)
        assert august.details["gamma"] == pytest.approx(0.5062, abs=0.005)

    def test_2019_lunar_eclipses_match_nasa(self):
        found = events.eclipses_in_range(2019, 2019, "lunar")
        january = next(e for e in found if e.month == 1)
        assert january.details["eclipse_kind"] == "total"
        assert january.details["umbral_magnitude"] == pytest.approx(1.1953, abs=0.01)

    def test_eclipse_of_thales(self):
        """28 May 585 BCE (Julian) — Herodotus 1.74, the classical anchor eclipse."""
        found = events.eclipses_in_range(-584, -584, "solar")
        julian_dates = [rd_to_julian(rd_from_jd(e.jd_ut)) for e in found]
        assert (-584, 5, 28) in julian_dates

    def test_bur_sagale_eclipse(self):
        """15 June 763 BCE (Julian) — the Assyrian Eponym Canon eclipse that fixes
        Assyrian chronology absolutely."""
        found = events.eclipses_in_range(-762, -762, "solar")
        julian_dates = [rd_to_julian(rd_from_jd(e.jd_ut)) for e in found]
        assert (-762, 6, 15) in julian_dates

    def test_every_eclipse_carries_visibility_uncertainty(self):
        for year in (-700, 33, 2024):
            for eclipse in events.eclipses_in_range(year, year):
                assert eclipse.details["visibility_uncertainty"]
                assert eclipse.accuracy_note

    def test_ancient_accuracy_note_is_more_cautious(self):
        ancient = events.eclipses_in_range(-700, -700)[0]
        modern = events.eclipses_in_range(2024, 2024)[0]
        assert ancient.accuracy_note != modern.accuracy_note
        assert "larger error" in ancient.accuracy_note

    def test_eclipse_rate_is_physically_plausible(self):
        """Between about 2 and 5 solar eclipses occur per year."""
        found = events.eclipses_in_range(2000, 2019, "solar")
        assert 40 <= len(found) <= 100


class TestConjunctions:
    def test_7bce_jupiter_saturn_triple_conjunction(self):
        """Kepler's proposed Star of Bethlehem: three close approaches in 7 BCE, in Pisces."""
        found = events.find_conjunctions(-7, -5, ["Jupiter", "Saturn"], max_separation=2.0)
        in_7bce = [e for e in found if e.year == -6]
        assert len(in_7bce) == 3
        for conjunction in in_7bce:
            assert conjunction.details["separation_degrees"] < 1.5
            assert catalogs.ecliptic_constellation(
                conjunction.details["longitude"]
            ) == "Pisces"

    def test_2020_great_conjunction(self):
        found = events.find_conjunctions(2020, 2020, ["Jupiter", "Saturn"], max_separation=1.0)
        assert len(found) == 1
        assert (found[0].month, found[0].day) == (12, 22)
        assert found[0].details["separation_degrees"] < 0.2

    def test_timing_uncertainty_is_reported_and_realistic(self):
        """Slow pairs must not be given a false-precision date."""
        slow = events.find_conjunctions(-7, -6, ["Jupiter", "Saturn"], max_separation=2.0)[0]
        fast = events.find_conjunctions(2024, 2024, ["Venus", "Mars"], max_separation=5.0)[0]
        assert slow.details["timing_uncertainty_days"] > fast.details["timing_uncertainty_days"]
        assert 1 < slow.details["timing_uncertainty_days"] < 60


class TestCatalogs:
    def test_zodiac_sign_and_constellation_differ(self):
        """Precession has moved them roughly a full sign apart; conflating them is the
        commonest astronomical error in popular writing about these texts."""
        result = astro.zodiac_sign_for_longitude(15.0)
        assert result["tropical_sign"] == "Aries"
        assert result["iau_constellation"] == "Pisces"

    def test_meteor_showers_active_window(self):
        showers = catalogs.showers_active_on(8, 12)
        assert any(s["name"] == "Perseids" for s in showers)

    def test_shower_window_wrapping_new_year(self):
        showers = catalogs.showers_active_on(1, 3)
        assert any(s["name"] == "Quadrantids" for s in showers)

    def test_halley_apparitions_spaced_by_period(self):
        halley = sorted(
            (c for c in catalogs.COMET_APPARITIONS if "Halley" in c.name), key=lambda c: c.year
        )
        gaps = [b.year - a.year for a, b in zip(halley, halley[1:])]
        assert all(70 <= gap <= 90 for gap in gaps if gap < 200)

    def test_comet_evidence_type_distinguishes_record_from_calculation(self):
        for comet in catalogs.COMET_APPARITIONS:
            assert comet.evidence in ("computed_return", "historical_record", "both")


class TestService:
    def test_span_guard_rejects_huge_scans(self):
        with pytest.raises(astro.AstronomyError, match="exceeds"):
            astro.eclipses(-1000, 1000)

    def test_out_of_range_rejected(self):
        with pytest.raises(astro.AstronomyError, match="3000 BCE"):
            astro.eclipses(-4000, -3900)

    def test_correlate_date_without_a_day(self):
        result = astro.correlate_date(33)
        assert "eclipses_in_year" in result
        assert "sky" not in result
        assert "Only a year was supplied" in result["note"]

    def test_correlate_date_with_a_day(self):
        result = astro.correlate_date(33, 4, 3)
        assert "sky" in result
        assert "nearest_new_moon" in result

    def test_sky_snapshot_reports_both_sign_systems(self):
        result = astro.sky_on_date(2024, 1, 1)
        assert "sign_vs_constellation_note" in result
        for body in result["bodies"]:
            assert "zodiac_sign" in body
            assert "ecliptic_constellation" in body
