"""The inverse search: a described sky in, candidate dates out.

Every assertion here is checked against something outside the implementation — a
configuration the historical literature agrees on, a base rate anyone can look up, or a
property the product promises. A test that only asserted the search agrees with itself
would pass just as happily on a search that ranked dates at random.

Deterministic and offline throughout: the ephemeris is pure arithmetic and the lexicon is
a fixed table, so these run without a network, a model or a database.
"""

from __future__ import annotations

import pytest

from app.agents.specialists import build_dating_criteria
from app.astronomy import dating_search
from app.astronomy.dating_search import (
    DatingCriteria,
    DatingSearchError,
    plan_search,
    search_candidate_dates,
)


def _criteria_from_text(text: str) -> DatingCriteria:
    from app.agents import offline_engine

    references = offline_engine.detect_astronomical(text)["astronomical_references"]
    return build_dating_criteria(references, text)


class TestTheWorkedExample:
    """The 7 BCE Jupiter–Saturn triple conjunction in Pisces.

    README.md lists this as one of the configurations the engine reproduces, and it is
    the best available external check on the search: three passes of the two planets
    inside a single year, in Pisces, is a specific and independently documented event.
    A search told what the sky looked like has to find its way back to it.
    """

    TEXT = (
        "And Jupiter and Saturn came together in the fishes, and stood together again, "
        "and a third time in that same year."
    )

    def test_the_lexicon_reading_of_the_text_names_the_configuration(self):
        criteria = _criteria_from_text(self.TEXT)
        assert criteria.conjunction is not None
        assert set(criteria.conjunction["bodies"]) == {"Jupiter", "Saturn"}
        assert criteria.conjunction["zodiac_sign"] == "Pisces"

    def test_the_search_rediscovers_7_bce(self):
        criteria = _criteria_from_text(self.TEXT)
        candidates = search_candidate_dates(criteria, -100, 100, max_results=10)

        # Astronomical year numbering: year -6 is 7 BCE.
        years = [c.year for c in candidates]
        assert -6 in years, f"7 BCE missing from the candidates: {years}"

        best_7bce = max((c for c in candidates if c.year == -6), key=lambda c: c.fit)
        assert best_7bce.fit >= 0.8, "the worked example should be a strong candidate"
        assert best_7bce.recurrences == 3, "three passes in the year is what makes it triple"
        assert any("triple conjunction" in note for note in best_7bce.notes)

    def test_it_ranks_at_the_top_over_a_span_containing_rival_recurrences(self):
        """Jupiter and Saturn meet about every twenty years, so rivals are guaranteed.

        The span deliberately contains the 66 BCE conjunction in Pisces as well. Both fit
        the description; the tie is broken by which one persisted, which is the thing the
        text actually describes.
        """
        criteria = _criteria_from_text(self.TEXT)
        candidates = search_candidate_dates(criteria, -100, 100, max_results=5)

        assert candidates[0].year == -6
        assert len({c.year for c in candidates}) > 1, "the rivals should still be offered"

    def test_a_sign_named_in_the_text_is_matched_by_constellation_not_only_by_sign(self):
        """Precession moved the signs about a whole sign away from the constellations.

        The 7 BCE conjunction is in the *constellation* Pisces and the *tropical sign*
        Aries. A text written in antiquity that says "in the fishes" means the former, so
        matching only on tropical sign would reject the one configuration this test
        exists to find — and would do it silently.
        """
        criteria = _criteria_from_text(self.TEXT)
        candidates = search_candidate_dates(criteria, -20, 20, max_results=5)
        best = max(candidates, key=lambda c: c.fit)

        conjunction = next(o for o in best.outcomes if o.criterion == "conjunction")
        assert conjunction.matched
        assert conjunction.evidence["constellation"] == "Pisces"
        assert conjunction.evidence["tropical_sign"] != "Pisces"
        assert any("precession" in note.lower() for note in best.notes)


class TestEveryCandidateShowsItsWorking:
    """The product promise for this feature: a proposal you can argue with."""

    def test_criteria_that_failed_are_recorded_not_dropped(self):
        criteria = DatingCriteria(
            eclipse={"kind": "solar", "totality_claimed": False},
            conjunction={"bodies": ["Jupiter", "Saturn"], "zodiac_sign": "Capricornus"},
        )
        candidates = search_candidate_dates(criteria, -50, -30, max_results=5)
        assert candidates

        # Somewhere in the list a candidate met one criterion and failed the other; that
        # is the normal case and the failure has to be visible on the candidate itself.
        with_misses = [c for c in candidates if c.unmatched]
        assert with_misses
        for candidate in with_misses:
            for miss in candidate.unmatched:
                assert miss.detail, "an unmatched criterion must say why it did not match"
            assert len(candidate.matched) + len(candidate.unmatched) == len(candidate.outcomes)

    def test_a_claim_a_no_engine_can_check_is_listed_and_excluded_from_the_score(self):
        """Three days of darkness is the case that matters.

        No astronomical mechanism produces it — a total solar eclipse lasts minutes — so
        no date can match, and counting it as a failure would drag every candidate down
        by the same amount while telling a reader nothing about which date is better.
        Silently ignoring it would be worse: it is often the most striking thing the
        passage says.
        """
        criteria = DatingCriteria(
            eclipse={"kind": "solar", "totality_claimed": True},
            unusual_darkness_days=3.0,
        )
        candidates = search_candidate_dates(criteria, -600, -590, max_results=3)
        assert candidates

        candidate = candidates[0]
        darkness = next(o for o in candidate.outcomes if o.criterion == "unusual_darkness")
        assert darkness.searchable is False
        assert darkness.matched is False
        assert "no astronomical mechanism" in darkness.detail.lower()

        # It is excluded from the denominator: an eclipse-only match still scores full.
        assert candidate.fit == pytest.approx(1.0, abs=0.3)

    def test_a_candidate_resting_only_on_common_phenomena_says_so(self):
        """Eclipses occur four to seven times a year somewhere on Earth.

        This engine computes no ground track, so "an eclipse near this date" is true of a
        large fraction of all dates. A search that presented such a match as a finding
        would be manufacturing the exact coincidence the platform exists to refuse.
        """
        criteria = DatingCriteria(eclipse={"kind": "lunar", "totality_claimed": False})
        candidates = search_candidate_dates(criteria, -590, -580, max_results=3)
        assert candidates
        assert all(any("fit most dates" in note for note in c.notes) for c in candidates), (
            "an eclipse-only candidate must carry the base-rate caveat"
        )

    def test_the_serialised_candidate_carries_the_keys_the_contract_requires(self):
        criteria = DatingCriteria(conjunction={"bodies": ["Jupiter", "Saturn"]})
        candidate = search_candidate_dates(criteria, -20, 20, max_results=1)[0]
        payload = candidate.to_dict()

        assert isinstance(payload["matched_criteria"], list)
        assert isinstance(payload["unmatched_criteria"], list)
        assert payload["engine"]
        assert payload["uncertainty_note"]


class TestScoring:
    def test_a_tighter_match_outscores_a_looser_one(self):
        """Fit has to mean something, or the ranking is decoration."""
        criteria = DatingCriteria(conjunction={"bodies": ["Jupiter", "Saturn"]})
        candidates = search_candidate_dates(criteria, -60, 60, max_results=10)
        assert len(candidates) > 2

        separations = [
            next(o for o in c.outcomes if o.criterion == "conjunction").evidence[
                "separation_degrees"
            ]
            for c in candidates
        ]
        # Ranked descending by fit, and fit falls as the planets sit further apart.
        assert separations[0] <= separations[-1]

    def test_fit_is_bounded(self):
        criteria = DatingCriteria(
            eclipse={"kind": "either"},
            conjunction={"bodies": ["Jupiter", "Saturn"]},
            moon_phase="full",
            comet_mentioned=True,
            season_hint="spring",
        )
        for candidate in search_candidate_dates(criteria, -20, 20, max_results=10):
            assert 0.0 <= candidate.fit <= 1.0

    def test_the_ordering_is_reproducible(self):
        """Candidates are persisted as claims and compared between runs."""
        criteria = DatingCriteria(conjunction={"bodies": ["Jupiter", "Saturn"]})
        first = search_candidate_dates(criteria, -40, 40, max_results=6)
        second = search_candidate_dates(criteria, -40, 40, max_results=6)
        assert [(c.year, c.month, c.day) for c in first] == [
            (c.year, c.month, c.day) for c in second
        ]


class TestCoverage:
    """A bounded search that hides its bounds turns a budget into a finding."""

    def test_a_span_inside_the_budget_is_covered_completely(self):
        criteria = DatingCriteria(conjunction={"bodies": ["Jupiter", "Saturn"]})
        coverage = plan_search(criteria, -100, 100)
        assert coverage.is_complete
        assert coverage.conjunction_window == (-100, 100)

    def test_a_span_beyond_the_budget_is_narrowed_and_says_so(self):
        criteria = DatingCriteria(
            eclipse={"kind": "solar"}, conjunction={"bodies": ["Jupiter", "Saturn"]}
        )
        coverage = plan_search(criteria, -2500, 2499)

        assert not coverage.is_complete
        assert coverage.notes
        eclipse_span = coverage.eclipse_window[1] - coverage.eclipse_window[0] + 1
        assert eclipse_span <= dating_search.MAX_ECLIPSE_SCAN_YEARS
        assert all("covered" in note for note in coverage.notes)

    def test_the_conjunction_budget_is_in_pair_years_not_years(self):
        """Cost is linear in both span and body pairs, so the budget is their product.

        Naming two planets should buy a far longer search than asking about all five, and
        a fixed year limit would be far too generous for one and far too mean for the
        other.
        """
        wide = plan_search(
            DatingCriteria(conjunction={"bodies": ["Jupiter", "Saturn"]}), -2500, 2499
        )
        narrow = plan_search(
            DatingCriteria(
                conjunction={"bodies": ["Jupiter", "Saturn", "Mars", "Venus", "Mercury"]}
            ),
            -2500,
            2499,
        )
        wide_span = wide.conjunction_window[1] - wide.conjunction_window[0]
        narrow_span = narrow.conjunction_window[1] - narrow.conjunction_window[0]
        assert wide_span > narrow_span

    def test_a_span_outside_the_ephemeris_window_is_refused_rather_than_guessed(self):
        criteria = DatingCriteria(eclipse={"kind": "solar"})
        with pytest.raises(DatingSearchError, match="3000 BCE"):
            plan_search(criteria, -5000, -4000)

    def test_a_reversed_span_is_refused(self):
        with pytest.raises(DatingSearchError):
            plan_search(DatingCriteria(eclipse={"kind": "solar"}), 100, -100)


class TestPrecision:
    def test_hour_precision_reports_a_time_and_the_limit_of_that_time(self):
        """ΔT for ancient dates is uncertain by tens of minutes.

        Rectification exists to narrow a window, so the one thing it must never do is
        imply a precision the underlying timescale cannot support.
        """
        criteria = DatingCriteria(eclipse={"kind": "solar"})
        candidate = search_candidate_dates(criteria, -20, 20, max_results=1, precision="hour")[0]

        assert candidate.hour_ut is not None
        assert "ΔT" in candidate.uncertainty_note

    def test_hour_precision_refuses_the_slack_that_date_precision_allows(self):
        """A match carried by six months of narrative latitude is not a rectification."""
        criteria = DatingCriteria(
            eclipse={"kind": "solar"}, conjunction={"bodies": ["Jupiter", "Saturn"]}
        )
        loose = search_candidate_dates(criteria, -20, 20, max_results=20, precision="date")
        tight = search_candidate_dates(criteria, -20, 20, max_results=20, precision="hour")

        def both_matched(candidates):
            return [c for c in candidates if len(c.matched) == 2]

        assert len(both_matched(tight)) < len(both_matched(loose))


class TestReadingTheText:
    """Criteria come from the same detections the rest of the report shows."""

    def test_an_eclipse_pair_is_read_as_either_kind(self):
        criteria = _criteria_from_text(
            "The sun was darkened and the moon became as blood over the city."
        )
        assert criteria.eclipse["kind"] == "either"

    def test_totality_is_only_claimed_when_the_text_claims_it(self):
        dim = _criteria_from_text("There was an eclipse of the sun.")
        total = _criteria_from_text("The sun became black as sackcloth of hair.")
        assert dim.eclipse["totality_claimed"] is False
        assert total.eclipse["totality_claimed"] is True

    def test_one_named_planet_is_not_a_conjunction(self):
        """Two bodies are the minimum for a meeting, and the search says so."""
        criteria = _criteria_from_text("The star of Jupiter rose over the temple.")
        assert criteria.conjunction is None

    def test_days_of_darkness_are_read_as_a_number(self):
        criteria = _criteria_from_text(
            "And there was thick darkness in all the land for three days."
        )
        assert criteria.unusual_darkness_days == 3.0

    def test_a_text_with_no_phenomena_yields_nothing_to_search(self):
        criteria = _criteria_from_text("These are the generations of the sons of Noah.")
        assert criteria.is_empty
        assert search_candidate_dates(criteria, -1000, 0) == []


class TestThroughTheWholePipeline:
    """One real dating analysis, end to end, because that is where the parts meet.

    Everything above tests the search in isolation. This runs it as a mode of the actual
    pipeline and reads the result back over HTTP, which is the only check that would
    catch a claim the contract rejected on the way to the database, or a section the
    report never rendered.

    The range is deliberately narrow: eleven years is enough for a real search and keeps
    the suite fast. No `db` fixture — the analysis runs on its own thread with its own
    session, and a long-lived fixture session would block its writes.
    """

    TEXT = "In those days the sun was darkened over the city, and the moon became as blood."

    def test_a_dating_run_produces_candidates_a_reader_can_check(self, client, auth_headers):
        import time

        headers, _ = auth_headers()
        created = client.post(
            "/api/v1/analyses",
            json={
                "text": self.TEXT,
                "options": {"mode": "date", "date_range_start": -600, "date_range_end": -590},
            },
            headers=headers,
        )
        assert created.status_code == 202, created.text
        analysis_id = created.json()["id"]

        deadline = time.time() + 120
        while time.time() < deadline:
            status = client.get(f"/api/v1/analyses/{analysis_id}/status", headers=headers).json()
            if status["status"] in ("completed", "partial", "failed"):
                break
            time.sleep(0.05)
        else:
            pytest.fail("the dating analysis did not finish in time")

        assert status["status"] in ("completed", "partial"), status

        detail = client.get(f"/api/v1/analyses/{analysis_id}", headers=headers).json()
        candidates = [
            c for c in detail["claims"] if c["claim_type"] == "astronomical_dating_candidate"
        ]
        assert candidates, "a datable phenomenon over a real span should yield candidates"

        for claim in candidates:
            # The contract's requirements, verified after a full round trip through
            # coercion, persistence and serialisation rather than on the draft.
            assert claim["engine"]
            assert claim["payload"]["matched_criteria"]
            assert "unmatched_criteria" in claim["payload"]
            assert claim["confidence"] <= 0.55
            assert claim["presentation"]["label"] == "Dating candidate"

    def test_the_report_carries_a_candidate_dates_section(self, client, auth_headers):
        import time

        headers, _ = auth_headers()
        created = client.post(
            "/api/v1/analyses",
            json={
                "text": self.TEXT,
                "options": {"mode": "date", "date_range_start": -600, "date_range_end": -590},
            },
            headers=headers,
        )
        analysis_id = created.json()["id"]

        deadline = time.time() + 120
        while time.time() < deadline:
            status = client.get(f"/api/v1/analyses/{analysis_id}/status", headers=headers).json()
            if status["status"] in ("completed", "partial", "failed"):
                break
            time.sleep(0.05)

        report = client.get(f"/api/v1/analyses/{analysis_id}", headers=headers).json()["report"]
        section = next(s for s in report["sections"] if s["key"] == "dating_candidates")
        assert section["title"] == "Candidate Dates"
        assert section["claim_count"] > 0
