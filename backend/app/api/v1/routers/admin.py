"""Admin: user management, monitoring, usage analytics, prompts, datasets, audit."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select

from app.api.deps import AdminUser, DbSession, ModeratorUser, record_audit
from app.core.config import settings
from app.db.models.analysis import Analysis, AnalysisStatus, Claim, ClaimType
from app.db.models.content import Document, Upload
from app.db.models.knowledge import Dataset, PromptTemplate
from app.db.models.ops import AuditAction, AuditLog, Job, JobStatus
from app.db.models.user import Role, User
from app.schemas.common import Message, Page
from app.schemas.user import AuditLogOut, RoleUpdate, UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


# ---- users ------------------------------------------------------------------------


@router.get("/users", response_model=Page[UserOut])
def list_users(
    db: DbSession,
    admin: AdminUser,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=200),
    role: str | None = None,
    active_only: bool = False,
) -> Page[UserOut]:
    stmt = select(User)
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%"))
    if role:
        try:
            stmt = stmt.where(User.role == Role(role))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Unknown role {role!r}.") from exc
    if active_only:
        stmt = stmt.where(User.is_active.is_(True))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )

    return Page[UserOut](
        items=[UserOut.model_validate({**u.__dict__, "role": u.role.value}) for u in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/users/{user_id}/role", response_model=UserOut)
def change_role(
    user_id: str, payload: RoleUpdate, request: Request, db: DbSession, admin: AdminUser
) -> UserOut:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="No such user.")

    if target.id == admin.id and payload.role != Role.ADMIN.value:
        # Prevents an administrator locking themselves — and possibly everyone — out.
        raise HTTPException(
            status_code=400,
            detail="You cannot remove your own admin role. Ask another administrator.",
        )

    previous = target.role.value
    target.role = Role(payload.role)
    record_audit(
        db,
        AuditAction.ROLE_CHANGED,
        actor=admin,
        target_type="user",
        target_id=user_id,
        request=request,
        detail={"from": previous, "to": payload.role},
    )
    db.commit()
    db.refresh(target)
    return UserOut.model_validate({**target.__dict__, "role": target.role.value})


@router.patch("/users/{user_id}/active", response_model=UserOut)
def set_active(
    user_id: str, active: bool, request: Request, db: DbSession, admin: AdminUser
) -> UserOut:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="No such user.")
    if target.id == admin.id and not active:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")

    target.is_active = active
    record_audit(
        db,
        AuditAction.USER_DEACTIVATED if not active else AuditAction.ADMIN_ACTION,
        actor=admin,
        target_type="user",
        target_id=user_id,
        request=request,
        detail={"active": active},
    )
    db.commit()
    db.refresh(target)
    return UserOut.model_validate({**target.__dict__, "role": target.role.value})


# ---- monitoring -------------------------------------------------------------------


@router.get("/system", summary="System status")
def system_status(db: DbSession, admin: AdminUser) -> dict:
    from app.agents.provider import provider_status
    from app.core.rate_limit import get_backend
    from app.knowledge.rag import corpus_stats

    now = datetime.now(UTC)
    jobs = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    stuck = db.execute(
        select(func.count())
        .select_from(Analysis)
        .where(
            Analysis.status == AnalysisStatus.RUNNING,
            Analysis.started_at < now - timedelta(minutes=30),
        )
    ).scalar_one()

    return {
        "environment": settings.ENVIRONMENT,
        "database": db.bind.dialect.name if db.bind else "unknown",
        "ai_provider": provider_status(),
        "rate_limit_backend": type(get_backend()).__name__,
        "corpus": corpus_stats(db),
        "jobs": {
            (s.value if isinstance(s, JobStatus) else str(s)): count for s, count in jobs.items()
        },
        "stuck_analyses": stuck,
        "warnings": (
            [
                f"{stuck} analyses have been running for over 30 minutes. They may have "
                "been interrupted by a restart; the job runner will retry them."
            ]
            if stuck
            else []
        ),
    }


@router.get("/usage", summary="Usage analytics")
def usage(
    db: DbSession,
    admin: AdminUser,
    days: int = Query(30, ge=1, le=365),
) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)

    total_analyses = db.execute(
        select(func.count()).select_from(Analysis).where(Analysis.created_at >= since)
    ).scalar_one()

    by_status = dict(
        db.execute(
            select(Analysis.status, func.count())
            .where(Analysis.created_at >= since)
            .group_by(Analysis.status)
        ).all()
    )

    by_claim_type = dict(
        db.execute(
            select(Claim.claim_type, func.count())
            .join(Analysis, Analysis.id == Claim.analysis_id)
            .where(Analysis.created_at >= since)
            .group_by(Claim.claim_type)
        ).all()
    )

    by_source = dict(
        db.execute(
            select(Document.source_kind, func.count())
            .where(Document.created_at >= since)
            .group_by(Document.source_kind)
        ).all()
    )

    average_duration = db.execute(
        select(func.avg(Analysis.duration_ms)).where(
            Analysis.created_at >= since, Analysis.duration_ms.is_not(None)
        )
    ).scalar_one()

    new_users = db.execute(
        select(func.count()).select_from(User).where(User.created_at >= since)
    ).scalar_one()

    ocr_count = db.execute(
        select(func.count())
        .select_from(Document)
        .where(Document.created_at >= since, Document.ocr_applied.is_(True))
    ).scalar_one()

    evidence_types = {
        ClaimType.SOURCE_TEXT,
        ClaimType.VERIFIED_HISTORY,
        ClaimType.ASTRONOMICAL_CALCULATION,
    }
    evidence_claims = sum(
        count for claim_type, count in by_claim_type.items() if claim_type in evidence_types
    )
    total_claims = sum(by_claim_type.values())

    return {
        "window_days": days,
        "analyses": total_analyses,
        "new_users": new_users,
        "average_duration_ms": round(average_duration) if average_duration else None,
        "ocr_documents": ocr_count,
        "by_status": {
            (s.value if isinstance(s, AnalysisStatus) else str(s)): c for s, c in by_status.items()
        },
        "by_source_kind": {
            (s.value if hasattr(s, "value") else str(s)): c for s, c in by_source.items()
        },
        "by_claim_type": {
            (t.value if isinstance(t, ClaimType) else str(t)): c for t, c in by_claim_type.items()
        },
        "evidence_ratio": (round(evidence_claims / total_claims, 3) if total_claims else None),
        "evidence_ratio_note": (
            "The share of claims that are evidence-grade rather than interpretation. A "
            "falling ratio suggests the platform is producing more conjecture relative to "
            "verifiable findings, which is worth investigating."
        ),
        "uploads": db.execute(
            select(func.count()).select_from(Upload).where(Upload.created_at >= since)
        ).scalar_one(),
    }


# ---- prompts ----------------------------------------------------------------------


@router.get("/prompts")
def list_prompts(db: DbSession, admin: AdminUser) -> dict:
    from app.agents.orchestrator import pipeline_description

    stored = (
        db.execute(
            select(PromptTemplate).order_by(PromptTemplate.agent_name, PromptTemplate.version)
        )
        .scalars()
        .all()
    )

    return {
        "agents": pipeline_description(),
        "stored_overrides": [
            {
                "id": p.id,
                "agent_name": p.agent_name,
                "version": p.version,
                "is_active": p.is_active,
                "notes": p.notes,
                "created_at": p.created_at,
            }
            for p in stored
        ],
        "note": (
            "Agents ship with built-in prompts. Stored overrides are versioned and only "
            "one per agent is active, so a report can always be explained in terms of the "
            "prompt that produced it."
        ),
    }


@router.post("/prompts", status_code=201)
def create_prompt(
    agent_name: str,
    version: str,
    system_prompt: str,
    request: Request,
    db: DbSession,
    admin: AdminUser,
    instruction_template: str = "",
    notes: str | None = None,
    activate: bool = False,
) -> dict:
    existing = db.execute(
        select(PromptTemplate).where(
            PromptTemplate.agent_name == agent_name, PromptTemplate.version == version
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Version {version} of {agent_name} already exists. Use a new version.",
        )

    if activate:
        db.query(PromptTemplate).filter(PromptTemplate.agent_name == agent_name).update(
            {"is_active": False}
        )

    template = PromptTemplate(
        agent_name=agent_name,
        version=version,
        system_prompt=system_prompt,
        instruction_template=instruction_template,
        is_active=activate,
        notes=notes,
        created_by_id=admin.id,
    )
    db.add(template)
    record_audit(
        db,
        AuditAction.PROMPT_UPDATED,
        actor=admin,
        target_type="prompt",
        target_id=agent_name,
        request=request,
        detail={"version": version, "activated": activate},
    )
    db.commit()
    db.refresh(template)
    return {"id": template.id, "agent_name": agent_name, "version": version, "active": activate}


# ---- datasets ---------------------------------------------------------------------


@router.get("/datasets")
def list_datasets(db: DbSession, admin: AdminUser) -> dict:
    rows = db.execute(select(Dataset).order_by(Dataset.name)).scalars().all()
    return {
        "datasets": [
            {
                "id": d.id,
                "key": d.key,
                "name": d.name,
                "description": d.description,
                "provider": d.provider,
                "license": d.license,
                "source_url": d.source_url,
                "record_count": d.record_count,
                "version": d.version,
                "is_enabled": d.is_enabled,
            }
            for d in rows
        ]
    }


@router.post("/datasets/reseed", response_model=Message)
def reseed(request: Request, db: DbSession, admin: AdminUser) -> Message:
    """Reload the curated corpus and rebuild the retrieval index. Idempotent."""
    from app.knowledge.seed import seed_all

    summary = seed_all(db)
    record_audit(
        db,
        AuditAction.DATASET_UPDATED,
        actor=admin,
        target_type="dataset",
        target_id="starcode-seed",
        request=request,
        detail=summary,
    )
    db.commit()
    return Message(message="Corpus reseeded.", detail=str(summary))


@router.patch("/datasets/{dataset_id}", response_model=Message)
def toggle_dataset(
    dataset_id: str, enabled: bool, request: Request, db: DbSession, admin: AdminUser
) -> Message:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="No such dataset.")
    dataset.is_enabled = enabled
    record_audit(
        db,
        AuditAction.DATASET_UPDATED,
        actor=admin,
        target_type="dataset",
        target_id=dataset_id,
        request=request,
        detail={"enabled": enabled},
    )
    db.commit()
    return Message(message=f"{dataset.name} {'enabled' if enabled else 'disabled'}.")


# ---- audit ------------------------------------------------------------------------


@router.get("/audit", response_model=Page[AuditLogOut])
def audit_log(
    db: DbSession,
    moderator: ModeratorUser,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: str | None = None,
    actor_id: str | None = None,
    outcome: str | None = None,
) -> Page[AuditLogOut]:
    stmt = select(AuditLog)
    if action:
        try:
            stmt = stmt.where(AuditLog.action == AuditAction(action))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Unknown action {action!r}.") from exc
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if outcome:
        stmt = stmt.where(AuditLog.outcome == outcome)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )

    return Page[AuditLogOut](
        items=[AuditLogOut.model_validate({**r.__dict__, "action": r.action.value}) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/jobs")
def list_jobs(
    db: DbSession,
    admin: AdminUser,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    stmt = select(Job).order_by(Job.created_at.desc())
    if status_filter:
        try:
            stmt = stmt.where(Job.status == JobStatus(status_filter))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Unknown status.") from exc

    rows = db.execute(stmt.limit(limit)).scalars().all()
    return {
        "jobs": [
            {
                "id": j.id,
                "job_type": j.job_type,
                "status": j.status.value,
                "attempts": j.attempts,
                "max_attempts": j.max_attempts,
                "target_id": j.target_id,
                "last_error": j.last_error,
                "created_at": j.created_at,
                "started_at": j.started_at,
                "finished_at": j.finished_at,
            }
            for j in rows
        ]
    }


@router.post("/jobs/{job_id}/retry", response_model=Message)
def retry_job(job_id: str, db: DbSession, admin: AdminUser) -> Message:
    from app.services.analysis_service import run_in_background

    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job.")

    job.status = JobStatus.PENDING
    job.max_attempts = max(job.max_attempts, job.attempts + 1)
    db.commit()
    run_in_background(job.id)
    return Message(message="Job requeued.")


__all__ = ["router"]
