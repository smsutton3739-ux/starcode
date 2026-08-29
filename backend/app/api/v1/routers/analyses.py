"""The core endpoint: submit something, get an analysis."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.agents.contracts import CLAIM_TYPE_PRESENTATION
from app.api.deps import (
    CurrentUser,
    DbSession,
    OptionalUser,
    get_anonymous_token,
    get_owned_or_shared_analysis,
    paginate,
    rate_limiter,
    record_audit,
    require_paid_tier,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.analysis import Analysis, AnalysisStatus, ClaimType
from app.db.models.content import Document, Tag
from app.db.models.ops import AuditAction
from app.db.models.user import User
from app.schemas.analysis import (
    AnalysisCreated,
    AnalysisDetail,
    AnalysisStatusOut,
    AnalysisSummary,
    AnalysisUpdate,
    AnalyzeRequest,
)
from app.schemas.common import Message, Page
from app.services import analysis_service, entitlements
from app.services.entitlements import gate_claim_dicts, gate_report
from app.services.ingest import IngestError, extract_from_text
from app.services.url_fetch import FetchError, fetch_as_extraction

logger = get_logger(__name__)
router = APIRouter(prefix="/analyses", tags=["analyses"])


def _authorise_dating_mode(db: DbSession, mode: str, user: User | None) -> int:
    """Check a dating request and return the span cap it may search.

    Kept in one function because three separate rules apply to the same request and the
    order between them is the whole behaviour: an account is needed before a role can be
    read, a role decides whether a tier matters, and a tier decides whether a count
    matters. Split across the endpoint body they would drift.

    Administrators pass every check here without a subscription and without spending an
    allowance — the same bypass, and the same single implementation of it, that decides
    whether a reader sees interpretive claims. See services/entitlements.py.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Astronomical dating needs an account: the free allowance is counted per "
                "account, so there is no anonymous path for it. Ordinary analysis still "
                "works without signing in."
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    if mode in entitlements.PAID_DATING_MODES:
        # The same dependency that gates every other paid surface, called directly rather
        # than reimplemented, so its 402 and its admin bypass apply here unchanged.
        require_paid_tier(user)

    if not entitlements.may_run_dating_search(db, user):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"You have used all {entitlements.FREE_DATING_SEARCHES} free astronomical "
                "dating searches on this account. The allowance is for the life of the "
                "account and does not reset; a paid plan removes the limit and widens the "
                f"searchable range to {entitlements.PAID_DATING_SPAN_YEARS:,} years."
            ),
        )

    return entitlements.dating_span_cap(user)


@router.get(
    "/dating-quota",
    summary="How much of the free astronomical dating allowance is left",
)
def dating_quota(db: DbSession, user: CurrentUser) -> dict:
    """Read the allowance before spending it.

    Declared above `/{analysis_id}` because FastAPI matches routes in definition order
    and this path would otherwise be read as an analysis id.
    """
    return entitlements.dating_quota(db, user)


@router.post(
    "",
    response_model=AnalysisCreated,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limiter("analyze"))],
    summary="Analyse a text, URL, or previously uploaded document",
)
def create(
    payload: AnalyzeRequest,
    request: Request,
    db: DbSession,
    user: OptionalUser,
) -> AnalysisCreated:
    """The one button. Everything the homepage does goes through here."""
    if user is None and not settings.ALLOW_ANONYMOUS_ANALYSIS:
        raise HTTPException(status_code=401, detail="Sign in to submit an analysis.")

    mode = payload.options.mode
    options = payload.options.model_dump()
    if entitlements.is_dating_mode(mode):
        # Authorised before anything is created or fetched: a request that cannot run
        # should not leave a document, a URL fetch or an audit entry behind it.
        options["dating_span_cap_years"] = _authorise_dating_mode(db, mode, user)

    document: Document | None = None
    source_url: str | None = None

    try:
        if payload.text:
            extraction = extract_from_text(payload.text, title=payload.title)
        elif payload.url:
            extraction = fetch_as_extraction(payload.url)
            source_url = payload.url
            record_audit(
                db,
                AuditAction.URL_FETCHED,
                actor=user,
                target_type="url",
                target_id=payload.url[:64],
                request=request,
                detail={"url": payload.url},
            )
        elif payload.upload_id:
            upload = analysis_service.resolve_upload(db, payload.upload_id, user)
            document = (
                db.execute(select(Document).where(Document.upload_id == upload.id))
                .scalars()
                .first()
            )
            if document is None:
                raise IngestError(
                    "No text has been extracted from that upload yet. Upload it again."
                )
            extraction = None  # type: ignore[assignment]
        else:
            document = db.get(Document, payload.document_id)
            if document is None or document.owner_id != (user.id if user else None):
                raise HTTPException(status_code=404, detail="No such document.")
            extraction = None  # type: ignore[assignment]
    except FetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if document is None:
        document = analysis_service.create_document(
            db, extraction, owner=user, project_id=payload.project_id, source_url=source_url
        )

    analysis, anonymous_token = analysis_service.create_analysis(
        db,
        document,
        owner=user,
        title=payload.title,
        project_id=payload.project_id,
        options=options,
    )

    if entitlements.is_dating_mode(mode) and user is not None:
        # Spent here, once the search is definitely going to run. A search that finds
        # nothing still spends a use — the computation happened, and refunding empty
        # results would reward retrying with ever-wider ranges.
        entitlements.record_dating_search(db, user, analysis.id, mode)

    record_audit(
        db,
        AuditAction.ANALYSIS_CREATED,
        actor=user,
        target_type="analysis",
        target_id=analysis.id,
        request=request,
        detail={
            "source_kind": document.source_kind.value,
            "chars": document.char_count,
            "mode": mode,
        },
    )
    db.commit()

    analysis_service.start_analysis(db, analysis)

    return AnalysisCreated(
        id=analysis.id,
        status=analysis.status.value,
        progress=analysis.progress,
        poll_url=f"{settings.API_V1_PREFIX}/analyses/{analysis.id}/status",
        anonymous_token=anonymous_token,
        message=(
            "Analysis started. Poll the status endpoint for progress."
            + (
                " Keep the anonymous_token: without an account it is the only way to reach "
                "this analysis again."
                if anonymous_token
                else ""
            )
        ),
    )


@router.get("/{analysis_id}/status", response_model=AnalysisStatusOut)
def get_status(
    analysis_id: str,
    db: DbSession,
    user: OptionalUser,
    anonymous_token: Annotated[str | None, Depends(get_anonymous_token)] = None,
) -> AnalysisStatusOut:
    analysis = get_owned_or_shared_analysis(db, analysis_id, user, anonymous_token)
    return AnalysisStatusOut(
        id=analysis.id,
        status=analysis.status.value,
        progress=analysis.progress,
        current_stage=analysis.current_stage,
        stage_label=analysis_service.stage_label(analysis.current_stage),
        error_message=analysis.error_message,
        failed_stages=list(analysis.failed_stages or []),
    )


@router.get("/{analysis_id}", response_model=AnalysisDetail)
def get_detail(
    analysis_id: str,
    request: Request,
    db: DbSession,
    user: OptionalUser,
    anonymous_token: Annotated[str | None, Depends(get_anonymous_token)] = None,
) -> AnalysisDetail:
    analysis = get_owned_or_shared_analysis(db, analysis_id, user, anonymous_token)

    analysis = db.execute(
        select(Analysis)
        .where(Analysis.id == analysis_id)
        .options(
            selectinload(Analysis.claims),
            selectinload(Analysis.entities),
            selectinload(Analysis.reports),
            selectinload(Analysis.agent_runs),
            selectinload(Analysis.references),
            selectinload(Analysis.document),
            selectinload(Analysis.tags),
        )
    ).scalar_one()

    record_audit(
        db,
        AuditAction.ANALYSIS_VIEWED,
        actor=user,
        target_type="analysis",
        target_id=analysis.id,
        request=request,
    )
    db.commit()

    return _serialize_detail(analysis, user)


def _serialize_detail(analysis: Analysis, viewer: User | None = None) -> AnalysisDetail:
    """Serialise an analysis for one reader.

    `viewer` decides which interpretive claims are readable. It defaults to None — the
    free tier — so a new call site that forgets to pass it withholds too much rather than
    too little.
    """
    references_by_claim: dict[str, list] = {}
    for reference in analysis.references:
        if reference.claim_id:
            references_by_claim.setdefault(reference.claim_id, []).append(reference)

    claims = []
    for claim in sorted(analysis.claims, key=lambda c: c.ordering):
        item = {
            **{
                key: getattr(claim, key)
                for key in (
                    "id",
                    "section",
                    "statement",
                    "reasoning",
                    "confidence",
                    "confidence_basis",
                    "produced_by",
                    "engine",
                    "algorithm_reference",
                    "quoted_text",
                    "text_span_start",
                    "text_span_end",
                    "ordering",
                    "payload",
                )
            },
            "claim_type": claim.claim_type.value,
            "references": references_by_claim.get(claim.id, []),
            # Shipped with every claim so the client never has to hard-code how a claim
            # type should be labelled — the enforcement and the presentation stay in sync.
            "presentation": CLAIM_TYPE_PRESENTATION[claim.claim_type],
        }
        claims.append(item)

    claims = gate_claim_dicts(claims, viewer)

    report = max(analysis.reports, key=lambda r: r.version) if analysis.reports else None

    return AnalysisDetail.model_validate(
        {
            "id": analysis.id,
            "title": analysis.title,
            "status": analysis.status.value,
            "progress": analysis.progress,
            "current_stage": analysis.current_stage,
            "detected_language": analysis.detected_language,
            "overall_confidence": analysis.overall_confidence,
            "confidence_rationale": analysis.confidence_rationale,
            "source_identification": analysis.source_identification or {},
            "translation_applied": analysis.translation_applied,
            "options": analysis.options or {},
            "error_message": analysis.error_message,
            "failed_stages": list(analysis.failed_stages or []),
            "token_usage": analysis.token_usage or {},
            "is_favorite": analysis.is_favorite,
            "created_at": analysis.created_at,
            "completed_at": analysis.completed_at,
            "duration_ms": analysis.duration_ms,
            "tags": [t.name for t in analysis.tags],
            "document": analysis.document,
            "claims": claims,
            "entities": [
                {
                    **{
                        key: getattr(entity, key)
                        for key in (
                            "id",
                            "name",
                            "canonical_name",
                            "aliases",
                            "description",
                            "extraction_confidence",
                            "identification_confidence",
                            "mention_count",
                            "mentions",
                            "earliest_year",
                            "latest_year",
                            "latitude",
                            "longitude",
                            "attributes",
                        )
                    },
                    "entity_type": entity.entity_type.value,
                }
                for entity in analysis.entities
            ],
            "report": gate_report(report, viewer),
            "agent_runs": sorted(analysis.agent_runs, key=lambda r: r.sequence),
        }
    )


@router.get("", response_model=Page[AnalysisSummary])
def list_analyses(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"),
    favorites_only: bool = False,
    project_id: str | None = None,
    tag: str | None = None,
    q: str | None = Query(None, max_length=200, description="Substring match on the title"),
) -> Page[AnalysisSummary]:
    limit, offset = paginate(limit, offset)

    stmt = select(Analysis).where(Analysis.owner_id == user.id)
    if status_filter:
        try:
            stmt = stmt.where(Analysis.status == AnalysisStatus(status_filter))
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Unknown status {status_filter!r}."
            ) from exc
    if favorites_only:
        stmt = stmt.where(Analysis.is_favorite.is_(True))
    if project_id:
        stmt = stmt.where(Analysis.project_id == project_id)
    if tag:
        stmt = stmt.join(Analysis.tags).where(Tag.slug == tag.lower())
    if q:
        stmt = stmt.where(Analysis.title.ilike(f"%{q}%"))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    rows = (
        db.execute(
            stmt.options(selectinload(Analysis.tags))
            .order_by(Analysis.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return Page[AnalysisSummary](
        items=[
            AnalysisSummary.model_validate(
                {
                    "id": a.id,
                    "title": a.title,
                    "status": a.status.value,
                    "progress": a.progress,
                    "current_stage": a.current_stage,
                    "detected_language": a.detected_language,
                    "overall_confidence": a.overall_confidence,
                    "is_favorite": a.is_favorite,
                    "created_at": a.created_at,
                    "completed_at": a.completed_at,
                    "duration_ms": a.duration_ms,
                    "failed_stages": list(a.failed_stages or []),
                    "tags": [t.name for t in a.tags],
                }
            )
            for a in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/{analysis_id}", response_model=AnalysisSummary)
def update(
    analysis_id: str,
    payload: AnalysisUpdate,
    db: DbSession,
    user: CurrentUser,
) -> AnalysisSummary:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None or analysis.owner_id != user.id:
        raise HTTPException(status_code=404, detail="No such analysis.")

    if payload.title is not None:
        analysis.title = payload.title
    if payload.is_favorite is not None:
        analysis.is_favorite = payload.is_favorite
    if payload.project_id is not None:
        analysis.project_id = payload.project_id or None

    if payload.tags is not None:
        from app.services.tagging import set_tags

        set_tags(db, analysis, user, payload.tags)

    db.commit()
    db.refresh(analysis)
    return AnalysisSummary.model_validate(
        {
            "id": analysis.id,
            "title": analysis.title,
            "status": analysis.status.value,
            "progress": analysis.progress,
            "current_stage": analysis.current_stage,
            "detected_language": analysis.detected_language,
            "overall_confidence": analysis.overall_confidence,
            "is_favorite": analysis.is_favorite,
            "created_at": analysis.created_at,
            "completed_at": analysis.completed_at,
            "duration_ms": analysis.duration_ms,
            "failed_stages": list(analysis.failed_stages or []),
            "tags": [t.name for t in analysis.tags],
        }
    )


@router.delete("/{analysis_id}", response_model=Message)
def delete(
    analysis_id: str,
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> Message:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None or analysis.owner_id != user.id:
        raise HTTPException(status_code=404, detail="No such analysis.")

    record_audit(
        db,
        AuditAction.ANALYSIS_DELETED,
        actor=user,
        target_type="analysis",
        target_id=analysis_id,
        request=request,
        detail={"title": analysis.title},
    )
    db.delete(analysis)
    db.commit()
    return Message(message="Analysis deleted.")


@router.post(
    "/{analysis_id}/rerun",
    response_model=AnalysisCreated,
    dependencies=[Depends(rate_limiter("analyze"))],
)
def rerun(
    analysis_id: str,
    db: DbSession,
    user: CurrentUser,
) -> AnalysisCreated:
    """Re-analyse the same text as a new version.

    A new analysis rather than a mutation of the old one: reports are dated artefacts,
    and overwriting one would silently invalidate anything already shared or cited.
    """
    original = db.get(Analysis, analysis_id)
    if original is None or original.owner_id != user.id:
        raise HTTPException(status_code=404, detail="No such analysis.")

    analysis, _ = analysis_service.create_analysis(
        db,
        original.document,
        owner=user,
        title=original.title,
        project_id=original.project_id,
        options=original.options,
    )
    analysis.parent_analysis_id = original.id
    analysis.version = (original.version or 1) + 1
    db.commit()

    analysis_service.start_analysis(db, analysis)
    return AnalysisCreated(
        id=analysis.id,
        status=analysis.status.value,
        progress=0.0,
        poll_url=f"{settings.API_V1_PREFIX}/analyses/{analysis.id}/status",
        anonymous_token=None,
        message=f"Re-running as version {analysis.version}. The original is unchanged.",
    )


@router.get("/{analysis_id}/trace", summary="Explainability trace for an analysis")
def get_trace(
    analysis_id: str,
    db: DbSession,
    user: OptionalUser,
    anonymous_token: Annotated[str | None, Depends(get_anonymous_token)] = None,
) -> dict:
    """Which agent produced what, with timings, models and reasoning summaries."""
    analysis = get_owned_or_shared_analysis(db, analysis_id, user, anonymous_token)

    claims_by_agent: dict[str, int] = {}
    for claim in analysis.claims:
        claims_by_agent[claim.produced_by] = claims_by_agent.get(claim.produced_by, 0) + 1

    return {
        "analysis_id": analysis.id,
        "status": analysis.status.value,
        "duration_ms": analysis.duration_ms,
        "token_usage": analysis.token_usage or {},
        "failed_stages": list(analysis.failed_stages or []),
        "steps": [
            {
                "sequence": run.sequence,
                "agent": run.agent_name,
                "status": run.status,
                "attempts": run.attempt,
                "provider": run.provider,
                "model": run.model,
                "prompt_version": run.prompt_version,
                "duration_ms": run.duration_ms,
                "reasoning": run.reasoning_summary,
                "error": run.error_message,
                "claims_produced": claims_by_agent.get(run.agent_name, 0),
            }
            for run in sorted(analysis.agent_runs, key=lambda r: r.sequence)
        ],
        "claim_type_totals": _claim_type_totals(analysis),
    }


def _claim_type_totals(analysis: Analysis) -> list[dict]:
    counts: dict[ClaimType, int] = {}
    for claim in analysis.claims:
        counts[claim.claim_type] = counts.get(claim.claim_type, 0) + 1
    return [
        {
            "claim_type": claim_type.value,
            "count": count,
            **CLAIM_TYPE_PRESENTATION[claim_type],
        }
        for claim_type, count in sorted(counts.items(), key=lambda kv: -kv[1])
    ]


__all__ = ["router"]
