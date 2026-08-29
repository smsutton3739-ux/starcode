"""What a tier may see, and the single place that decision is applied.

Three separate code paths deliver claim text to a reader, and all three must agree:

1. `GET /analyses/{id}` — the claim list, via `_serialize_detail`.
2. The stored report structure, which embeds `claim.to_dict()` per section and is served
   inside that same response.
3. Every export format — PDF, DOCX, CSV, Markdown, JSON — which read `analysis.claims`
   straight off the ORM and never pass through the router's serialiser at all.

Gating only the first would have left the paid content readable by asking for the same
analysis as a CSV. That is the same shape as the bug recorded in the developer guide,
where the serialiser and the exporters disagreed about a field name and every unit test
still passed, so the rule here is: nothing renders a claim without coming through this
module.

Locking is deliberately *not* deletion. The claim keeps its id, type, section, ordering
and confidence; only the human-readable content is replaced. That keeps the audit trail
intact, keeps the claim-type counts in the confidence summary honest, and lets the UI
show a reader precisely what they are missing rather than a shorter report that looks
like the analysis simply found less.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.contracts import ClaimType
from app.db.models.ops import AstronomicalDatingUsage
from app.db.models.user import Role, Tier, User

#: Claim types withheld from the free tier.
#:
#: These are the interpretive types — the ones a language model produced and that carry
#: no independently checkable evidence. The deterministic types (`source_text`,
#: `verified_history`, `astronomical_calculation`, `textual_analysis`) stay visible to
#: everyone, because they are the part of the product that is checkable and the part that
#: costs nothing per run to produce.
LOCKED_CLAIM_TYPES: frozenset[ClaimType] = frozenset(
    {
        ClaimType.TRADITIONAL_INTERPRETATION,
        ClaimType.SCHOLARLY_INTERPRETATION,
        ClaimType.AI_HYPOTHESIS,
    }
)

LOCKED_STATEMENT = "[Unlock with a paid plan to see this interpretation]"

#: Marker the client keys off. Present and true only on a withheld claim.
LOCKED_FLAG = "locked"


def tier_of(user: User | None) -> Tier:
    """The effective tier for a request, including the anonymous case.

    Anonymous readers are free-tier: the homepage works without an account by design, and
    that includes seeing the deterministic half of a report.
    """
    return user.tier if user is not None else Tier.FREE


def unlocks_interpretation(user: User | None) -> bool:
    """Whether this reader sees interpretive claims rather than locked placeholders.

    The single place that question is answered. `require_paid_tier` in api/deps.py
    delegates here rather than repeating the rule, so an endpoint gated by the dependency
    and a claim gated by the serialiser can never disagree about who has access.

    Administrators pass unconditionally, whatever their tier. This is a deliberate,
    narrow exception to the rule that tier and role are orthogonal — stated as such
    rather than hidden, because the rest of this codebase depends on that separation
    holding. It exists so the operator of the site can use the whole product on their own
    account without buying a subscription from themselves.

    The exception is exactly this wide: ADMIN bypasses *paid-tier* checks. It grants no
    tier, writes nothing to the database, and changes no billing state — an admin who
    subscribes is still an ordinary paying customer in Stripe and in `users.tier`. It is
    not a licence to answer other tier questions with a role, or vice versa.
    """
    if user is not None and user.role is Role.ADMIN:
        return True
    return tier_of(user).unlocks_interpretation


# ======================================================================================
# Astronomical dating: quota and search span
# ======================================================================================

#: Astronomical dating searches a free account may run, for the life of the account.
#:
#: Lifetime rather than monthly, and that is the whole design. A resetting quota needs a
#: period boundary, arithmetic to decide which side of it a request falls on, and — for a
#: rolling window — something to run when it expires. This deployment has no background
#: worker by design, so the honest options were a lifetime count or a quota that quietly
#: never reset. `COUNT(*)` for a user answers this one exactly.
FREE_DATING_SEARCHES = 5

#: Years a free account may search in one dating run.
FREE_DATING_SPAN_YEARS = 500

#: Years a paid account may search in one dating run.
#:
#: The ephemeris is defensible from 3000 BCE to 3000 CE — six millennia — so this is a
#: limit on cost, not on the engine's reach. The scans inside a search are separately
#: budgeted and report the window they actually covered, because a five-millennium
#: request is not one call to the engine but hundreds; see astronomy/dating_search.py.
PAID_DATING_SPAN_YEARS = 5000

#: The modes that are paid-only, with no free allowance at all.
PAID_DATING_MODES: frozenset[str] = frozenset({"rectification", "eschatological", "historicizing"})

#: Every mode that runs a dating search, free or paid.
DATING_MODES: frozenset[str] = frozenset({"date"}) | PAID_DATING_MODES


def is_dating_mode(mode: str | None) -> bool:
    return mode in DATING_MODES


def dating_span_cap(user: User | None) -> int:
    """How many years of history one search may cover, for this account.

    Routed through `unlocks_interpretation` rather than reading the tier, so the admin
    bypass reaches this too: the site's operator gets the paid span for the same reason
    they get the paid claims.
    """
    return PAID_DATING_SPAN_YEARS if unlocks_interpretation(user) else FREE_DATING_SPAN_YEARS


def dating_searches_used(db: Session, user: User) -> int:
    """Dating searches this account has ever run."""
    return int(
        db.execute(
            select(func.count())
            .select_from(AstronomicalDatingUsage)
            .where(AstronomicalDatingUsage.user_id == user.id)
        ).scalar_one()
    )


def dating_quota(db: Session, user: User) -> dict[str, Any]:
    """What to tell a client about this account's dating allowance.

    `limit` is null for an account with no limit, which is the shape the UI keys on:
    a number means show "n of m used", null means show nothing.
    """
    if unlocks_interpretation(user):
        return {
            "used": dating_searches_used(db, user),
            "limit": None,
            "remaining": None,
            "unlimited": True,
            "paid_modes_available": True,
        }
    used = dating_searches_used(db, user)
    return {
        "used": used,
        "limit": FREE_DATING_SEARCHES,
        "remaining": max(0, FREE_DATING_SEARCHES - used),
        "unlimited": False,
        "paid_modes_available": False,
    }


def may_run_dating_search(db: Session, user: User) -> bool:
    """Whether this account has an allowance left. Paid and admin accounts always do."""
    if unlocks_interpretation(user):
        return True
    return dating_searches_used(db, user) < FREE_DATING_SEARCHES


def record_dating_search(db: Session, user: User, analysis_id: str | None, mode: str) -> None:
    """Spend one use.

    An attempt that returns no candidates still spends one — the search ran, and refunding
    empty results would turn the quota into an incentive to retry with ever-wider spans.

    Written for paying accounts as well as free ones, because the row is also the record
    of what the feature is used for and only its *count* is ever compared to a limit.
    Administrators are the exception: nothing meters them, so a row for the operator's own
    account could never change an outcome, and leaving it out keeps the ledger an honest
    picture of what customers do rather than one inflated by the owner testing the feature.
    """
    if user.role is Role.ADMIN:
        return
    db.add(AstronomicalDatingUsage(user_id=user.id, analysis_id=analysis_id, mode=mode))


def _lock_claim_dict(claim: dict[str, Any]) -> dict[str, Any]:
    """Replace the readable content of one already-serialised claim.

    Every field that can carry the interpretation is cleared, not just `statement`:
    `reasoning` restates the argument, `confidence_basis` often paraphrases the finding,
    and `quoted_text` on an interpretive claim can carry the passage being interpreted.
    Leaving any of them populated would hand back through a side door exactly what the
    statement withheld.

    `references` are deliberately kept. A citation here is bibliography — title, authors,
    year, DOI — with no excerpt field, so it discloses nothing about the interpretation
    itself. Stripping them would also break the epistemic contract in the one place it
    matters most: `scholarly_interpretation` requires at least one citation to exist, and
    a gated response emitting that type with an empty reference list would be the exact
    uncited claim the contract exists to prevent. Keeping them also makes the upsell
    honest — a reader can see the withheld claim is backed by real sources.
    """
    locked = dict(claim)
    locked["statement"] = LOCKED_STATEMENT
    locked["reasoning"] = None
    locked["confidence_basis"] = None
    locked["quoted_text"] = None
    locked[LOCKED_FLAG] = True
    return locked


def gate_claim_dicts(claims: list[dict[str, Any]], user: User | None) -> list[dict[str, Any]]:
    """Apply the tier rule to a list of serialised claim dicts.

    Claims are marked `locked: false` rather than left unmarked when visible, so a client
    can render the two states from one field instead of inferring the negative.
    """
    if unlocks_interpretation(user):
        return [{**claim, LOCKED_FLAG: False} for claim in claims]

    gated = []
    for claim in claims:
        raw_type = claim.get("claim_type")
        claim_type = raw_type.value if isinstance(raw_type, ClaimType) else raw_type
        if claim_type in {t.value for t in LOCKED_CLAIM_TYPES}:
            gated.append(_lock_claim_dict(claim))
        else:
            gated.append({**claim, LOCKED_FLAG: False})
    return gated


def gate_orm_claims(claims: list[Any], user: User | None) -> list[Any]:
    """The exporters' entry point.

    Exporters read ORM `Claim` rows and reach for attributes, so returning dicts here
    would break every one of them. Instead each withheld row is wrapped in a lightweight
    stand-in exposing the same attribute names, leaving the ORM objects — and therefore
    the database — untouched.
    """
    if unlocks_interpretation(user):
        return list(claims)
    return [_LockedClaimView(c) if c.claim_type in LOCKED_CLAIM_TYPES else c for c in claims]


class _LockedClaimView:
    """A read-only stand-in for a withheld claim, shaped like the ORM row it replaces.

    Attribute access falls through to the real row for everything structural (id, type,
    section, ordering, confidence) and is overridden for everything readable. It is never
    added to a session, so nothing here can write a locked placeholder to the database.
    """

    __slots__ = ("_claim",)

    def __init__(self, claim: Any) -> None:
        self._claim = claim

    def __getattr__(self, name: str) -> Any:
        return getattr(self._claim, name)

    @property
    def statement(self) -> str:
        return LOCKED_STATEMENT

    @property
    def reasoning(self) -> None:
        return None

    @property
    def confidence_basis(self) -> None:
        return None

    @property
    def quoted_text(self) -> None:
        return None

    @property
    def locked(self) -> bool:
        return True


def gate_report_sections(sections: Any, user: User | None) -> Any:
    """Apply the same rule inside a stored report's section payloads.

    `build_report` embeds `claim.to_dict()` under each section, so a report carries a
    second, independent copy of every statement. A reader served a gated claim list but
    an ungated report would simply read the interpretation out of the section body.

    Returns a new list; the ORM row is never mutated, so a locked placeholder can never
    be flushed back to the database and become the stored report.
    """
    if unlocks_interpretation(user) or not isinstance(sections, list):
        return sections

    gated = []
    for section in sections:
        if isinstance(section, dict) and isinstance(section.get("claims"), list):
            gated.append({**section, "claims": gate_claim_dicts(section["claims"], user)})
        else:
            gated.append(section)
    return gated


def gate_report(report: Any, user: User | None) -> Any:
    """Gate a whole report row for one reader.

    The executive summary is deliberately NOT withheld. It is assembled mechanically
    rather than written by a model — word count, corpus identification, per-type claim
    *counts*, the astronomical terms detected, which stages failed, and the standing note
    that every statement is labelled by kind. None of that is an interpretation.

    Withholding it was the first thing tried here and it was wrong twice over: it removed
    the free tier's only orientation to its own report, and it hid the best honest upsell
    in the product — a sentence that tells a reader exactly how many interpretive findings
    exist without revealing any of them.
    """
    if report is None or unlocks_interpretation(user):
        return report

    return {
        "id": report.id,
        "version": report.version,
        "executive_summary": report.executive_summary,
        "sections": gate_report_sections(report.sections, user),
        "timeline": report.timeline,
        "confidence_summary": report.confidence_summary,
        "further_reading": report.further_reading,
        "reasoning_trace": report.reasoning_trace,
        "word_count": report.word_count,
        "generator_version": report.generator_version,
    }


__all__ = [
    "FREE_DATING_SEARCHES",
    "FREE_DATING_SPAN_YEARS",
    "PAID_DATING_SPAN_YEARS",
    "PAID_DATING_MODES",
    "DATING_MODES",
    "is_dating_mode",
    "dating_span_cap",
    "dating_searches_used",
    "dating_quota",
    "may_run_dating_search",
    "record_dating_search",
    "LOCKED_CLAIM_TYPES",
    "LOCKED_STATEMENT",
    "LOCKED_FLAG",
    "tier_of",
    "unlocks_interpretation",
    "gate_claim_dicts",
    "gate_orm_claims",
    "gate_report_sections",
    "gate_report",
]
