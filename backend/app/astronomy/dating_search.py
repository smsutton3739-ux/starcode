"""Search the other way round: a described sky in, candidate dates out.

`service.correlate_date` answers "what was in the sky on this date". It is arithmetic,
and it is the workhorse behind ordinary analysis. This module answers the inverse — "on
what dates did the sky look like *this*" — which is not arithmetic at all. It is a search
whose answer is a ranked list of proposals, and the difference is the reason every
candidate here carries the criteria it failed as well as the ones it met.

Two rules shape the whole file:

**No astronomy is computed here.** Every number comes from `service`, so a candidate
date and the ordinary report agree by construction rather than by review. This module
decides *what to ask* and *how to score the answers*, nothing else.

**The search is bounded, and says where it stopped.** The engine's per-call span limits
exist because the underlying scans are linear in years; a search over five millennia is
not one call but a hundred, and for conjunctions the cost is high enough that the honest
move is to search a narrower window and report having done so. Silence about coverage
would turn "no candidate found" — a real finding — into an artefact of the budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

from app.astronomy import catalogs, service
from app.astronomy.ephemeris import NAKED_EYE_PLANETS

Precision = Literal["date", "hour"]

#: Within this many days, two phenomena count as one occasion at full strength.
#:
#: Half a synodic month, chosen for a reason rather than for roundness: a solar and a
#: lunar eclipse at the same syzygy fall about a fortnight apart, which is exactly the
#: pairing behind "the sun was darkened and the moon became as blood".
SAME_EVENT_WINDOW_DAYS = 15.0

#: Beyond that and up to here, phenomena still count, at a discount.
#:
#: Ancient reports group portents by narrative, not by clock — "in those days" covers a
#: season. Refusing a match at sixteen days would throw away real correspondences; scoring
#: one at six months as though it were simultaneous would manufacture them. So the credit
#: decays across the range and the offset is printed on the candidate either way.
NARRATIVE_WINDOW_DAYS = 180.0

#: How much of a match survives at the far edge of the narrative window.
DISTANT_MATCH_FLOOR = 0.4

#: The window used instead when a caller asks for hour precision. Rectification asks how
#: far the evidence can actually be narrowed, so it must not credit a match that half a
#: year of slack was carrying.
RECTIFICATION_WINDOW_DAYS = 2.0

#: Kept as the historical name for the full-strength window.
CO_OCCURRENCE_WINDOW_DAYS = SAME_EVENT_WINDOW_DAYS


def _search_window(precision: Precision) -> float:
    """How far out to look for a co-occurring phenomenon."""
    return RECTIFICATION_WINDOW_DAYS if precision == "hour" else NARRATIVE_WINDOW_DAYS


def _proximity_strength(offset_days: float, precision: Precision) -> float:
    """How much credit a phenomenon `offset_days` from the candidate date earns.

    Zero means it does not count as a match at all. The two-stage shape is deliberate:
    flat while the events are plausibly one occasion, then decaying, so that a candidate
    ranks above one whose portents are scattered across a year without discarding the
    latter outright.
    """
    offset = abs(offset_days)
    if precision == "hour":
        if offset > RECTIFICATION_WINDOW_DAYS:
            return 0.0
        return 1.0 - 0.5 * (offset / RECTIFICATION_WINDOW_DAYS)
    if offset <= SAME_EVENT_WINDOW_DAYS:
        return 1.0
    if offset > NARRATIVE_WINDOW_DAYS:
        return 0.0
    spread = (offset - SAME_EVENT_WINDOW_DAYS) / (NARRATIVE_WINDOW_DAYS - SAME_EVENT_WINDOW_DAYS)
    return 1.0 - (1.0 - DISTANT_MATCH_FLOOR) * spread


#: Conjunction scanning is budgeted in *pair-years*, not years.
#:
#: Cost is linear in both the span and the number of body pairs — a five-planet search
#: over a century costs the same as one named pair over a millennium. Budgeting the
#: product keeps the worst case flat whichever shape the request arrives in, instead of a
#: fixed year limit that is far too generous for one and far too mean for the other.
MAX_CONJUNCTION_PAIR_YEARS = 2000

#: Years of eclipse scanning a single search may perform.
#:
#: Eclipses are cheap to *find* — a couple of milliseconds a century — but every one
#: found becomes a candidate that then has every other criterion checked against it, and
#: that scoring is where the time goes. At four to seven eclipses a year, a millennium is
#: some six thousand candidates. Beyond that a search stops being interactive without
#: becoming more informative: a ranked list is only useful at the length a person will
#: read, and the top of it does not improve by scanning further from the era the text
#: actually belongs to.
MAX_ECLIPSE_SCAN_YEARS = 1200

#: Default separation, in degrees, for "these bodies were together".
#:
#: Naked-eye descriptions of two planets "meeting" or "standing together" are not
#: measurements. Three degrees is roughly six lunar diameters — wide enough to catch what
#: an observer would have called a meeting, narrow enough to exclude a pair merely in the
#: same quarter of the sky.
DEFAULT_MAX_SEPARATION_DEGREES = 3.0


class DatingSearchError(ValueError):
    """Raised when a search cannot be run as asked."""


# ======================================================================================
# What the text says the sky did
# ======================================================================================


@dataclass(slots=True)
class DatingCriteria:
    """A structured reading of the phenomena a text describes.

    Deliberately a description of *the text*, not of the sky: every field records
    something the passage asserts, so that a candidate's score is a statement about how
    well a date fits the text rather than about how interesting the date is.
    """

    #: ``{"kind": "solar" | "lunar" | "either", "totality_claimed": bool}``
    eclipse: dict[str, Any] | None = None
    #: ``{"bodies": [...], "zodiac_sign": str | None, "repetitions": int | None}``
    #:
    #: ``repetitions`` is how many times the text says the meeting happened. It is worth
    #: capturing because it is far more discriminating than the meeting itself: Jupiter
    #: and Saturn pass each other about every twenty years, but pass three times in one
    #: year only about every century and a half.
    conjunction: dict[str, Any] | None = None
    #: "new" | "first_quarter" | "full" | "last_quarter"
    moon_phase: str | None = None
    comet_mentioned: bool = False
    #: Days of darkness the text claims. No ephemeris can produce one, and saying so is
    #: more useful than quietly ignoring the strongest thing the passage said.
    unusual_darkness_days: float | None = None
    #: "spring" | "summer" | "autumn" | "winter"
    season_hint: str | None = None

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.eclipse,
                self.conjunction,
                self.moon_phase,
                self.comet_mentioned,
                self.unusual_darkness_days,
                self.season_hint,
            )
        )

    def describe(self) -> list[str]:
        """One readable line per criterion, for the reasoning summary and the report."""
        lines: list[str] = []
        if self.eclipse:
            kind = self.eclipse.get("kind", "either")
            totality = " described as total" if self.eclipse.get("totality_claimed") else ""
            lines.append(f"an eclipse ({'solar or lunar' if kind == 'either' else kind}){totality}")
        if self.conjunction:
            bodies = ", ".join(self.conjunction.get("bodies") or []) or "unnamed planets"
            sign = self.conjunction.get("zodiac_sign")
            repetitions = self.conjunction.get("repetitions")
            lines.append(
                f"a conjunction of {bodies}"
                + (f" in {sign}" if sign else "")
                + (f", occurring {repetitions} times" if repetitions else "")
            )
        if self.moon_phase:
            lines.append(f"the moon at {self.moon_phase.replace('_', ' ')}")
        if self.comet_mentioned:
            lines.append("a comet or comet-like apparition")
        if self.unusual_darkness_days:
            lines.append(f"darkness lasting about {self.unusual_darkness_days:g} day(s)")
        if self.season_hint:
            lines.append(f"the season given as {self.season_hint}")
        return lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "eclipse": self.eclipse,
            "conjunction": self.conjunction,
            "moon_phase": self.moon_phase,
            "comet_mentioned": self.comet_mentioned,
            "unusual_darkness_days": self.unusual_darkness_days,
            "season_hint": self.season_hint,
        }


# ======================================================================================
# What comes back
# ======================================================================================


@dataclass(slots=True)
class CriterionOutcome:
    """One criterion, checked against one date."""

    criterion: str
    matched: bool
    detail: str
    #: How well it matched, not merely whether. An eclipse on the day itself and one a
    #: fortnight away are both "an eclipse near this date"; scoring them identically
    #: would flatten the only thing that separates a good candidate from a coincidence.
    strength: float = 1.0
    #: False when the criterion is not something the engine can decide either way.
    searchable: bool = True
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion,
            "matched": self.matched,
            "strength": round(self.strength, 3) if self.matched else 0.0,
            "detail": self.detail,
            "searchable": self.searchable,
            "evidence": self.evidence,
        }


@dataclass(slots=True)
class DateCandidate:
    """A date whose sky matches, with its working shown."""

    year: int
    month: int
    day: int
    gregorian_label: str
    fit: float
    anchor: str
    """Which phenomenon put this date in the running — the search generated it, the
    others were then checked against it."""
    outcomes: list[CriterionOutcome] = field(default_factory=list)
    hour_ut: float | None = None
    uncertainty_note: str = ""
    notes: list[str] = field(default_factory=list)
    #: Passes of the same configuration within the candidate's year. Breaks ties between
    #: equally-fitting dates in favour of the one that matches the description longer.
    recurrences: int = 0

    @property
    def matched(self) -> list[CriterionOutcome]:
        return [o for o in self.outcomes if o.matched]

    @property
    def unmatched(self) -> list[CriterionOutcome]:
        return [o for o in self.outcomes if not o.matched]

    def to_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "month": self.month,
            "day": self.day,
            "hour_ut": self.hour_ut,
            "gregorian_label": self.gregorian_label,
            "fit": round(self.fit, 3),
            "anchor": self.anchor,
            "recurrences": self.recurrences,
            "engine": service.ENGINE_NAME,
            "uncertainty_note": self.uncertainty_note,
            "notes": self.notes,
            "matched_criteria": [o.to_dict() for o in self.matched],
            "unmatched_criteria": [o.to_dict() for o in self.unmatched],
        }


@dataclass(slots=True)
class SearchCoverage:
    """What the search was actually able to look at.

    Reported alongside the candidates because a bounded search that does not say it was
    bounded is indistinguishable from an exhaustive one that found nothing.
    """

    requested: tuple[int, int]
    eclipse_window: tuple[int, int] | None = None
    conjunction_window: tuple[int, int] | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.notes

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_years": list(self.requested),
            "eclipse_window": list(self.eclipse_window) if self.eclipse_window else None,
            "conjunction_window": (
                list(self.conjunction_window) if self.conjunction_window else None
            ),
            "complete": self.is_complete,
            "notes": self.notes,
        }


# ======================================================================================
# Planning
# ======================================================================================


def _chunks(start_year: int, end_year: int, size: int) -> list[tuple[int, int]]:
    """Split a span into pieces the engine will accept.

    The per-call limits in `service` are CPU guards on a single request, not statements
    about what the ephemeris can model, so walking a long span in accepted pieces is
    legitimate where widening the guard would not be.
    """
    spans = []
    year = start_year
    while year <= end_year:
        last = min(year + size - 1, end_year)
        spans.append((year, last))
        year = last + 1
    return spans


def _centred_window(start_year: int, end_year: int, width: int) -> tuple[int, int]:
    """The `width`-year window in the middle of a span.

    The middle rather than the start because a span usually comes from an era estimate,
    and an era estimate's best guess is its centre.
    """
    if end_year - start_year + 1 <= width:
        return (start_year, end_year)
    centre = (start_year + end_year) // 2
    half = width // 2
    return (centre - half, centre - half + width - 1)


def _pair_count(bodies: list[str]) -> int:
    n = max(len(bodies), 2)
    return n * (n - 1) // 2


def plan_search(criteria: DatingCriteria, start_year: int, end_year: int) -> SearchCoverage:
    """Work out, before searching, how much of the requested span each scan can cover.

    Separate from the search itself so an agent can tell a reader what it is about to do,
    and so the budget arithmetic is testable without running a scan.
    """
    if end_year < start_year:
        raise DatingSearchError("end_year must not precede start_year")
    if not (-3000 <= start_year <= 3000 and -3000 <= end_year <= 3000):
        raise DatingSearchError(
            "The ephemeris models are only defensible between 3000 BCE and 3000 CE. "
            "Narrow the search to that window."
        )

    coverage = SearchCoverage(requested=(start_year, end_year))

    if criteria.eclipse:
        window = _centred_window(start_year, end_year, MAX_ECLIPSE_SCAN_YEARS)
        coverage.eclipse_window = window
        if window != (start_year, end_year):
            coverage.notes.append(
                f"Eclipse search covered {_span_label(*window)} — the middle "
                f"{window[1] - window[0] + 1} years of the {end_year - start_year + 1} "
                "requested. Eclipses recur four to seven times a year, so a wider scan "
                "adds thousands of candidates without improving the top of the list. "
                "Narrow the range to the era the text belongs to for full coverage."
            )

    if criteria.conjunction:
        bodies = criteria.conjunction.get("bodies") or list(NAKED_EYE_PLANETS)
        pairs = _pair_count(bodies)
        affordable = max(MAX_CONJUNCTION_PAIR_YEARS // pairs, service.MAX_CONJUNCTION_YEARS)
        window = _centred_window(start_year, end_year, affordable)
        coverage.conjunction_window = window
        if window != (start_year, end_year):
            coverage.notes.append(
                f"Conjunction search covered {_span_label(*window)} — the middle "
                f"{window[1] - window[0] + 1} years of the {end_year - start_year + 1} "
                f"requested. Scanning {pairs} body pair(s) over the whole span would cost "
                "minutes of computation for a result that gets less meaningful as it "
                "widens: a Jupiter–Saturn conjunction recurs about every twenty years, so "
                "a long enough search finds one near any date at all. Narrow the range, or "
                "name the planets, for a search that covers it fully."
            )

    return coverage


@lru_cache(maxsize=4096)
def _conjunctions_in_year(bodies: tuple[str, ...], year: int) -> tuple[dict[str, Any], ...]:
    """One year of conjunctions, memoised.

    Scoring checks every criterion against every candidate, so a span with a thousand
    eclipse anchors asks for the same year's conjunctions a thousand times. The engine is
    pure and its answer for a given year never changes, which is exactly what makes a
    cache safe here — and it turns a search that took a quarter of a minute into one that
    takes a second. Callers must treat the returned dictionaries as read-only.
    """
    if not -3000 <= year <= 3000:
        return ()
    found = service.conjunctions(
        year, year, bodies=list(bodies), max_separation=DEFAULT_MAX_SEPARATION_DEGREES
    )
    return tuple(found["events"])


@lru_cache(maxsize=4096)
def _seasons_in_year(year: int) -> tuple[dict[str, Any], ...]:
    """Equinoxes and solstices for a year, memoised for the same reason."""
    return tuple(service.seasons(year)["events"])


def year_label(year: int) -> str:
    """Astronomical year number as a reader-facing era label.

    Year 0 is 1 BCE throughout this codebase, so the conversion is off by one and worth
    doing in exactly one place.
    """
    return f"{abs(year - 1)} BCE" if year <= 0 else f"{year} CE"


def span_label(start_year: int, end_year: int) -> str:
    return f"{year_label(start_year)} to {year_label(end_year)}"


#: Retained for internal call sites predating the public name.
_span_label = span_label


# ======================================================================================
# The search
# ======================================================================================


def search_candidate_dates(
    criteria: DatingCriteria,
    start_year: int,
    end_year: int,
    *,
    max_results: int = 10,
    precision: Precision = "date",
) -> list[DateCandidate]:
    """Rank dates in a span by how well their real sky fits what a text describes.

    Candidates are *generated* from the phenomena that can be scanned for — eclipses,
    conjunctions, recorded comets — and then every criterion, including the ones that
    generated them, is *checked* against each candidate date. Generating and scoring
    separately is what lets a date proposed by an eclipse lose points for having no
    conjunction near it, which is the whole value of the exercise.
    """
    if criteria.is_empty:
        return []

    coverage = plan_search(criteria, start_year, end_year)
    anchors = _generate_anchors(criteria, coverage, precision=precision)
    if not anchors:
        return []

    candidates = [
        _score_anchor(anchor, criteria, precision=precision) for anchor in anchors.values()
    ]
    # Descending fit, then by how long the configuration persisted, then by date. The
    # last term is what makes the ordering stable and reproducible, which matters because
    # these are persisted as claims and compared across runs.
    candidates.sort(key=lambda c: (-c.fit, -c.recurrences, c.year, c.month, c.day))
    return candidates[:max_results]


@dataclass(slots=True)
class _Anchor:
    year: int
    month: int
    day: int
    hour_ut: float
    kind: str
    event: dict[str, Any]
    siblings: list[dict[str, Any]] = field(default_factory=list)


def _generate_anchors(
    criteria: DatingCriteria, coverage: SearchCoverage, *, precision: Precision
) -> dict[tuple[int, int, int], _Anchor]:
    """Every date the span offers that could plausibly answer the description."""
    anchors: dict[tuple[int, int, int], _Anchor] = {}

    def add(event: dict[str, Any], kind: str) -> None:
        key = (event["year"], event["month"], event["day"])
        existing = anchors.get(key)
        if existing is None:
            anchors[key] = _Anchor(
                year=event["year"],
                month=event["month"],
                day=event["day"],
                hour_ut=event.get("hour_ut", 12.0),
                kind=kind,
                event=event,
            )
        else:
            existing.siblings.append(event)

    if criteria.eclipse and coverage.eclipse_window:
        kind = criteria.eclipse.get("kind", "either")
        query_kind = "both" if kind not in ("solar", "lunar") else kind
        for span in _chunks(*coverage.eclipse_window, service.MAX_SCAN_YEARS):
            for event in service.eclipses(span[0], span[1], kind=query_kind)["events"]:
                add(event, "eclipse")

    if criteria.conjunction and coverage.conjunction_window:
        bodies = criteria.conjunction.get("bodies") or list(NAKED_EYE_PLANETS)
        bodies = [b for b in bodies if b.title() in NAKED_EYE_PLANETS]
        if len(bodies) >= 2:
            for span in _chunks(*coverage.conjunction_window, service.MAX_CONJUNCTION_YEARS):
                found = service.conjunctions(
                    span[0],
                    span[1],
                    bodies=bodies,
                    max_separation=DEFAULT_MAX_SEPARATION_DEGREES,
                )
                for event in found["events"]:
                    add(event, "conjunction")

    # A comet on its own is a weak generator — the catalogue holds a few dozen entries
    # over five millennia — but where a text mentions one it is often the only datable
    # thing in the passage, so the recorded appearances are offered as candidates too.
    if criteria.comet_mentioned and not anchors:
        for year in range(coverage.requested[0], coverage.requested[1] + 1):
            for comet in service.catalogue_lookup(year)["comets"]:
                perihelion = comet.get("year")
                if perihelion is None or not (
                    coverage.requested[0] <= perihelion <= coverage.requested[1]
                ):
                    continue
                add(
                    {
                        "year": int(perihelion),
                        "month": 1,
                        "day": 1,
                        "hour_ut": 12.0,
                        "label": comet.get("name", "comet"),
                        "event_type": "comet",
                        "details": comet,
                    },
                    "comet",
                )

    return anchors


def _score_anchor(
    anchor: _Anchor, criteria: DatingCriteria, *, precision: Precision
) -> DateCandidate:
    """Check every criterion against one candidate date and weigh the result."""
    window = _search_window(precision)
    outcomes: list[CriterionOutcome] = []
    notes: list[str] = []

    if criteria.eclipse:
        outcomes.append(_check_eclipse(anchor, criteria.eclipse, window, precision))
    if criteria.conjunction:
        outcome, conjunction_notes = _check_conjunction(
            anchor, criteria.conjunction, window, precision
        )
        outcomes.append(outcome)
        notes.extend(conjunction_notes)
    if criteria.conjunction and criteria.conjunction.get("repetitions"):
        outcomes.append(
            _check_repetitions(anchor, int(criteria.conjunction["repetitions"]), criteria)
        )
    if criteria.moon_phase:
        outcomes.append(_check_moon_phase(anchor, criteria.moon_phase))
    if criteria.comet_mentioned:
        outcomes.append(_check_comet(anchor))
    if criteria.season_hint:
        outcomes.append(_check_season(anchor, criteria.season_hint))
    if criteria.unusual_darkness_days:
        outcomes.append(
            CriterionOutcome(
                criterion="unusual_darkness",
                matched=False,
                searchable=False,
                detail=(
                    f"The text describes darkness lasting about "
                    f"{criteria.unusual_darkness_days:g} day(s). No astronomical mechanism "
                    "produces that — a total solar eclipse lasts minutes — so no date can "
                    "match it and none is credited with doing so. Volcanic dust veils and "
                    "dust storms have produced multi-day darkness historically; that is a "
                    "question for the historical record, not for the ephemeris."
                ),
            )
        )

    fit = _fit_score(outcomes)

    # A pass repeated within a year is the signature of a triple conjunction — the
    # configuration that made 7 BCE famous — and a text describing planets that "met,
    # parted and met again" is describing exactly that. Recorded and used to break ties
    # rather than added to the fit, because fit means "how much of the description this
    # date satisfies" and inflating it past that would make the number mean two things.
    same_year_repeats = _same_year_repeat_count(anchor, criteria)
    if same_year_repeats >= 3:
        notes.append(
            f"{same_year_repeats} passes of this conjunction fall in the same year — a "
            "triple conjunction, which an observer would have experienced as one prolonged "
            "event rather than three separate ones."
        )
    if anchor.siblings:
        notes.append(f"{len(anchor.siblings) + 1} catalogued events fall on this date.")

    caveat = _discrimination_caveat(outcomes)
    if caveat:
        notes.append(caveat)

    return DateCandidate(
        recurrences=same_year_repeats,
        year=anchor.year,
        month=anchor.month,
        day=anchor.day,
        hour_ut=anchor.hour_ut if precision == "hour" else None,
        gregorian_label=anchor.event.get("gregorian_label")
        or _span_label(anchor.year, anchor.year),
        fit=fit,
        anchor=anchor.kind,
        outcomes=outcomes,
        uncertainty_note=_uncertainty_note(anchor, precision),
        notes=notes,
    )


def _same_year_repeat_count(anchor: _Anchor, criteria: DatingCriteria) -> int:
    """How many conjunction passes of the requested bodies fall in the anchor's year."""
    if anchor.kind != "conjunction" or not criteria.conjunction:
        return 0
    bodies = [
        b for b in (criteria.conjunction.get("bodies") or []) if b.title() in NAKED_EYE_PLANETS
    ]
    if len(bodies) < 2:
        return 0
    return len(_conjunctions_in_year(tuple(bodies), anchor.year))


# ---- individual criteria -------------------------------------------------------------


def _check_eclipse(
    anchor: _Anchor, spec: dict[str, Any], window: float, precision: Precision
) -> CriterionOutcome:
    wanted = spec.get("kind", "either")
    nearby = service.eclipses_around(
        anchor.year, anchor.month, anchor.day, window_days=max(window, 1.0)
    )["events"]

    def kind_of(event: dict) -> str:
        return "solar" if event.get("event_type") == "solar_eclipse" else "lunar"

    matches = [e for e in nearby if wanted in ("either", kind_of(e))]
    if not matches:
        return CriterionOutcome(
            criterion="eclipse",
            matched=False,
            detail=(
                f"No {'' if wanted == 'either' else wanted + ' '}eclipse within "
                f"{window:g} days of this date."
            ),
        )

    anchor_jd = service.julian_day_for(anchor.year, anchor.month, anchor.day)
    best = min(matches, key=lambda e: abs(e["julian_day"] - anchor_jd))
    offset = abs(best["julian_day"] - anchor_jd)

    totality_claimed = bool(spec.get("totality_claimed"))
    is_total = (best.get("details") or {}).get("eclipse_kind") == "total"

    strength = _proximity_strength(offset, precision)
    if strength <= 0.0:
        return CriterionOutcome(
            criterion="eclipse",
            matched=False,
            detail=(
                f"The nearest {'' if wanted == 'either' else wanted + ' '}eclipse is "
                f"{offset:.0f} days away, too far to belong to the same occasion."
            ),
        )
    detail = f"{best.get('label')} on {best.get('gregorian_label')}."
    if offset >= 1.0:
        detail += f" That is {offset:.0f} days from this date."
    if totality_claimed and not is_total:
        strength *= 0.7
        detail += (
            " The text describes total obscuration; this eclipse is not total, so the "
            "match is partial."
        )
    return CriterionOutcome(
        criterion="eclipse",
        matched=True,
        strength=strength,
        detail=detail,
        evidence={
            "label": best.get("label"),
            "gregorian_label": best.get("gregorian_label"),
            "offset_days": round(offset, 1),
            "totality_claimed": totality_claimed,
            "is_total": is_total,
            "accuracy_note": best.get("accuracy_note"),
            "base_rate_caveat": (
                "Four to seven eclipses occur somewhere on Earth each year, and this "
                "engine computes no ground track, so 'an eclipse near this date' is true "
                "of most dates. On its own it is not evidence; it becomes evidence in "
                "combination with something rarer."
            ),
        },
    )


def _check_conjunction(
    anchor: _Anchor, spec: dict[str, Any], window: float, precision: Precision
) -> tuple[CriterionOutcome, list[str]]:
    notes: list[str] = []
    bodies = [b for b in (spec.get("bodies") or []) if b.title() in NAKED_EYE_PLANETS]
    wanted_sign = (spec.get("zodiac_sign") or "").title() or None

    if len(bodies) < 2:
        return (
            CriterionOutcome(
                criterion="conjunction",
                matched=False,
                searchable=False,
                detail=(
                    "The text mentions planets meeting but names fewer than two of them, "
                    "so there is no specific configuration to search for."
                ),
            ),
            notes,
        )

    if anchor.kind == "conjunction":
        event = anchor.event
        details = event.get("details") or {}
        offset = 0.0
    else:
        anchor_jd = service.julian_day_for(anchor.year, anchor.month, anchor.day)
        # A conjunction can straddle a year boundary, so the neighbouring years are
        # scanned too rather than only the candidate's own.
        near: list[dict[str, Any]] = []
        for year in (anchor.year - 1, anchor.year, anchor.year + 1):
            near.extend(
                e
                for e in _conjunctions_in_year(tuple(bodies), year)
                if abs(e["julian_day"] - anchor_jd) <= window
            )
        if not near:
            return (
                CriterionOutcome(
                    criterion="conjunction",
                    matched=False,
                    detail=(
                        f"{' and '.join(bodies)} were not within "
                        f"{DEFAULT_MAX_SEPARATION_DEGREES:g}° of each other within "
                        f"{window:g} days of this date."
                    ),
                ),
                notes,
            )
        best = min(near, key=lambda e: abs(e["julian_day"] - anchor_jd))
        event, details = best, (best.get("details") or {})
        offset = abs(best["julian_day"] - anchor_jd)

    separation = details.get("separation_degrees")
    longitude = details.get("longitude")
    constellation = catalogs.ecliptic_constellation(longitude) if longitude is not None else None
    tropical_sign = details.get("zodiac_sign")

    proximity = _proximity_strength(offset, precision)
    if proximity <= 0.0:
        return (
            CriterionOutcome(
                criterion="conjunction",
                matched=False,
                detail=(
                    f"The nearest conjunction of {' and '.join(bodies)} is {offset:.0f} "
                    "days away, too far to belong to the same occasion."
                ),
            ),
            notes,
        )

    detail = f"{event.get('label')} on {event.get('gregorian_label')}."
    if offset >= 1.0:
        detail += f" That is {offset:.0f} days from this date."
    matched = True

    if wanted_sign:
        # Signs and constellations drifted roughly a full sign apart between antiquity and
        # now, so a text saying "in Pisces" may mean either. Both are checked and which
        # one answered is recorded — quietly accepting the wrong one would make the match
        # look tighter than it is.
        by_constellation = constellation == wanted_sign
        by_sign = tropical_sign == wanted_sign
        if by_constellation or by_sign:
            which = "constellation" if by_constellation else "tropical sign"
            detail += f" In {wanted_sign} by {which}."
            if by_constellation and not by_sign:
                notes.append(
                    f"The conjunction falls in the constellation {wanted_sign} but the "
                    f"tropical sign {tropical_sign}. Precession separates the two by about "
                    "a sign for this era; the constellation is what an observer would have "
                    "seen the planets among."
                )
        else:
            matched = False
            detail += (
                f" But it falls in {constellation or 'an undetermined constellation'} "
                f"(tropical sign {tropical_sign}), not {wanted_sign}."
            )

    # Tighter pairs are better matches for a text describing planets that met: at three
    # degrees an observer sees two nearby stars, at a tenth of one they nearly touch.
    strength = proximity
    if isinstance(separation, int | float):
        strength *= 1.0 - 0.5 * min(float(separation) / DEFAULT_MAX_SEPARATION_DEGREES, 1.0)

    return (
        CriterionOutcome(
            criterion="conjunction",
            matched=matched,
            strength=strength,
            detail=detail,
            evidence={
                "bodies": details.get("bodies", bodies),
                "separation_degrees": separation,
                "offset_days": round(offset, 1),
                "constellation": constellation,
                "tropical_sign": tropical_sign,
                "gregorian_label": event.get("gregorian_label"),
                "accuracy_note": event.get("accuracy_note"),
            },
        ),
        notes,
    )


def _check_repetitions(anchor: _Anchor, wanted: int, criteria: DatingCriteria) -> CriterionOutcome:
    """Whether the configuration recurred as many times as the text says it did.

    The most discriminating thing a conjunction criterion can carry. Two planets meeting
    is common; meeting three times inside one year requires the pair to be near
    opposition so that retrograde motion carries one back across the other twice more,
    which for Jupiter and Saturn happens roughly every century and a half. A text that
    says "and again, and a third time" has named that, and a search that ignored it would
    rank an ordinary single pass alongside the configuration actually described.
    """
    actual = _same_year_repeat_count(anchor, criteria)
    matched = actual >= wanted
    return CriterionOutcome(
        criterion="recurrence",
        matched=matched,
        strength=1.0 if matched else 0.0,
        detail=(
            f"The configuration recurs {actual} time(s) within this year; the text "
            f"describes {wanted}."
            + (
                ""
                if matched
                else " A single pass is not what the passage describes, however close it is."
            )
        ),
        evidence={"passes_in_year": actual, "passes_described": wanted},
    )


_PHASE_LABELS = {
    "new": "New Moon",
    "first_quarter": "First Quarter",
    "full": "Full Moon",
    "last_quarter": "Last Quarter",
}


def _check_moon_phase(anchor: _Anchor, phase: str) -> CriterionOutcome:
    wanted = _PHASE_LABELS.get(phase)
    if wanted is None:
        return CriterionOutcome(
            criterion="moon_phase",
            matched=False,
            searchable=False,
            detail=f"'{phase}' is not a phase this engine computes.",
        )

    actual = service.moon_on_date(anchor.year, anchor.month, anchor.day)
    # Phase names are assigned over a range, so an exact-name comparison on the anchor
    # date is the right test for "the moon looked like this then" — tighter than the
    # co-occurrence window used for discrete events, which is correct: the moon's
    # appearance is a property of the day itself.
    matched = actual["phase_name"].lower().startswith(wanted.split()[0].lower())
    return CriterionOutcome(
        criterion="moon_phase",
        matched=matched,
        detail=(
            f"The moon was {actual['phase_name'].lower()} "
            f"({actual['illuminated_fraction'] * 100:.0f}% illuminated) on this date"
            + ("." if matched else f", not {wanted.lower()}.")
        ),
        evidence={
            "phase_name": actual["phase_name"],
            "illuminated_fraction": actual["illuminated_fraction"],
            "note": actual["note"],
        },
    )


def _check_comet(anchor: _Anchor) -> CriterionOutcome:
    catalogue = service.catalogue_lookup(anchor.year)
    comets = catalogue["comets"]
    if not comets:
        return CriterionOutcome(
            criterion="comet",
            matched=False,
            detail=(
                "No catalogued comet appearance within a few years of this date. The "
                "catalogue is a curated set of well-attested apparitions, not a complete "
                "record — absence here is weak evidence, not none."
            ),
        )
    best = min(comets, key=lambda c: abs((c.get("year") or anchor.year) - anchor.year))
    gap = abs((best.get("year") or anchor.year) - anchor.year)
    return CriterionOutcome(
        criterion="comet",
        matched=True,
        strength=1.0 - 0.15 * min(gap, 3),
        detail=f"{best.get('name')}: {best.get('perihelion_note')}."
        + (f" That is {gap} year(s) from this date." if gap else ""),
        evidence={
            "years_from_candidate": gap,
            "name": best.get("name"),
            "evidence": best.get("evidence"),
            "records": best.get("records", []),
            "source": best.get("source"),
        },
    )


_SEASON_EVENT = {
    "spring": "March equinox",
    "summer": "June solstice",
    "autumn": "September equinox",
    "winter": "December solstice",
}


def _check_season(anchor: _Anchor, season: str) -> CriterionOutcome:
    season = season.lower()
    if season not in _SEASON_EVENT:
        return CriterionOutcome(
            criterion="season",
            matched=False,
            searchable=False,
            detail=f"'{season}' is not a season this engine can place.",
        )

    markers = _seasons_in_year(anchor.year)
    jd = service.julian_day_for(anchor.year, anchor.month, anchor.day)
    ordered = sorted(markers, key=lambda e: e["julian_day"])
    boundaries = [e["julian_day"] for e in ordered]

    # Before the March equinox the date belongs to the winter that began the previous
    # December, so the index wraps rather than clamping.
    index = sum(1 for b in boundaries if b <= jd) - 1
    names = ["spring", "summer", "autumn", "winter"]
    actual = names[index % 4] if index >= 0 else "winter"

    return CriterionOutcome(
        criterion="season",
        matched=actual == season,
        detail=(
            f"This date falls in astronomical {actual} in the northern hemisphere"
            + ("." if actual == season else f", not {season}.")
        ),
        evidence={
            "actual_season": actual,
            "note": (
                "Seasons are northern-hemisphere and astronomical, bounded by the "
                "equinoxes and solstices. A text's own calendar may divide the year "
                "differently."
            ),
        },
    )


# ---- scoring -------------------------------------------------------------------------

#: Criteria common enough that matching one says almost nothing on its own.
#:
#: Both are true of a large fraction of all dates — eclipses occur several times a year
#: somewhere on Earth, and a season covers a quarter of one. A candidate resting only on
#: these is a coincidence with a fit score, and it says so.
_WEAKLY_DISCRIMINATING = frozenset({"eclipse", "season"})


def _discrimination_caveat(outcomes: list[CriterionOutcome]) -> str:
    matched = [o.criterion for o in outcomes if o.matched]
    if not matched or set(matched) - _WEAKLY_DISCRIMINATING:
        return ""
    return (
        "This candidate rests only on criteria that fit most dates: eclipses occur four "
        "to seven times a year somewhere on Earth, and a season spans a quarter of it. "
        "Treat the fit score as a measure of consistency, not of evidence — a search over "
        "any comparable span would find dates that fit as well."
    )


#: Relative weight of each criterion in the fit score.
#:
#: An eclipse is the most discriminating thing a text can describe — a specific one, on a
#: specific day, computable to the day for millennia. A season narrows a year to a
#: quarter and no further, so it must not carry the same weight as a datable event, or a
#: candidate that matched nothing but the time of year would score half.
_CRITERION_WEIGHTS = {
    "eclipse": 1.0,
    "conjunction": 0.9,
    # Weighted with the eclipse, not with the conjunction it qualifies: a triple pass is
    # about as rare as a specific eclipse and narrows a span just as sharply.
    "recurrence": 1.0,
    "comet": 0.6,
    "moon_phase": 0.5,
    "season": 0.25,
    "unusual_darkness": 0.0,
}


def _fit_score(outcomes: list[CriterionOutcome]) -> float:
    """Weighted fraction of the searchable criteria this date satisfies.

    Criteria the engine cannot decide are excluded from the denominator rather than
    counted as failures: a text claiming three days of darkness should not drag down
    every candidate equally, since it does so uniformly and therefore says nothing about
    which date is better. It stays in the unmatched list, where a reader can see it.
    """
    searchable = [o for o in outcomes if o.searchable]
    if not searchable:
        return 0.0
    total = sum(_CRITERION_WEIGHTS.get(o.criterion, 0.5) for o in searchable)
    if total <= 0:
        return 0.0
    hit = sum(
        _CRITERION_WEIGHTS.get(o.criterion, 0.5) * max(0.0, min(1.0, o.strength))
        for o in searchable
        if o.matched
    )
    return hit / total


def _uncertainty_note(anchor: _Anchor, precision: Precision) -> str:
    accuracy = anchor.event.get("accuracy_note")
    base = accuracy or (
        "Computed by the platform's ephemeris; see the engine's accuracy statement for "
        "this class of event."
    )
    if precision == "hour":
        return (
            base + " Requested at hour precision: the time given is Universal Time, and ΔT "
            "uncertainty for ancient dates is tens of minutes, so local civil time cannot "
            "be pinned more tightly than that however exact the computation looks."
        )
    return base


__all__ = [
    "SAME_EVENT_WINDOW_DAYS",
    "NARRATIVE_WINDOW_DAYS",
    "CO_OCCURRENCE_WINDOW_DAYS",
    "RECTIFICATION_WINDOW_DAYS",
    "MAX_CONJUNCTION_PAIR_YEARS",
    "MAX_ECLIPSE_SCAN_YEARS",
    "DEFAULT_MAX_SEPARATION_DEGREES",
    "DatingSearchError",
    "DatingCriteria",
    "CriterionOutcome",
    "DateCandidate",
    "SearchCoverage",
    "plan_search",
    "search_candidate_dates",
    "year_label",
    "span_label",
]
