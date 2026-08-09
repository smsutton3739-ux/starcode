"""User library: projects, collections, tags, shares and notifications."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, record_audit
from app.core.config import settings
from app.core.security import hash_token, new_opaque_token
from app.db.models.analysis import Analysis, AnalysisStatus
from app.db.models.content import Collection, Project, Share
from app.db.models.ops import AuditAction
from app.db.models.user import Notification
from app.schemas.common import Message
from app.schemas.user import (
    CollectionCreate,
    CollectionOut,
    NotificationOut,
    ProjectCreate,
    ProjectOut,
    ShareCreate,
    ShareOut,
    TagOut,
)
from app.services import tagging

router = APIRouter(tags=["library"])


# ---- dashboard --------------------------------------------------------------------


@router.get("/dashboard", summary="Dashboard summary for the signed-in user")
def dashboard(db: DbSession, user: CurrentUser) -> dict:
    total = db.execute(
        select(func.count()).select_from(Analysis).where(Analysis.owner_id == user.id)
    ).scalar_one()

    by_status = dict(
        db.execute(
            select(Analysis.status, func.count())
            .where(Analysis.owner_id == user.id)
            .group_by(Analysis.status)
        ).all()
    )

    recent = db.execute(
        select(Analysis)
        .where(Analysis.owner_id == user.id)
        .order_by(Analysis.created_at.desc())
        .limit(5)
    ).scalars().all()

    favorites = db.execute(
        select(func.count())
        .select_from(Analysis)
        .where(Analysis.owner_id == user.id, Analysis.is_favorite.is_(True))
    ).scalar_one()

    unread = db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    ).scalar_one()

    average_confidence = db.execute(
        select(func.avg(Analysis.overall_confidence)).where(
            Analysis.owner_id == user.id,
            Analysis.overall_confidence.is_not(None),
        )
    ).scalar_one()

    return {
        "totals": {
            "analyses": total,
            "favorites": favorites,
            "collections": db.execute(
                select(func.count()).select_from(Collection).where(Collection.owner_id == user.id)
            ).scalar_one(),
            "projects": db.execute(
                select(func.count()).select_from(Project).where(Project.owner_id == user.id)
            ).scalar_one(),
            "unread_notifications": unread,
        },
        "by_status": {
            (status.value if isinstance(status, AnalysisStatus) else str(status)): count
            for status, count in by_status.items()
        },
        "average_confidence": round(average_confidence, 3) if average_confidence else None,
        "recent": [
            {
                "id": a.id,
                "title": a.title,
                "status": a.status.value,
                "created_at": a.created_at,
                "overall_confidence": a.overall_confidence,
            }
            for a in recent
        ],
    }


# ---- projects ---------------------------------------------------------------------


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: DbSession, user: CurrentUser) -> list[ProjectOut]:
    rows = db.execute(
        select(Project).where(Project.owner_id == user.id).order_by(Project.created_at.desc())
    ).scalars().all()
    return [ProjectOut.model_validate(p) for p in rows]


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, db: DbSession, user: CurrentUser) -> ProjectOut:
    project = Project(owner_id=user.id, name=payload.name, description=payload.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.delete("/projects/{project_id}", response_model=Message)
def delete_project(project_id: str, db: DbSession, user: CurrentUser) -> Message:
    project = db.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="No such project.")
    db.delete(project)
    db.commit()
    return Message(message="Project deleted. Analyses in it were kept.")


# ---- collections ------------------------------------------------------------------


@router.get("/collections", response_model=list[CollectionOut])
def list_collections(db: DbSession, user: CurrentUser) -> list[CollectionOut]:
    rows = db.execute(
        select(Collection)
        .where(Collection.owner_id == user.id)
        .order_by(Collection.created_at.desc())
    ).scalars().all()
    return [
        CollectionOut.model_validate({**c.__dict__, "analysis_count": len(c.analyses)})
        for c in rows
    ]


@router.post("/collections", response_model=CollectionOut, status_code=201)
def create_collection(
    payload: CollectionCreate, db: DbSession, user: CurrentUser
) -> CollectionOut:
    collection = Collection(
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        is_public=payload.is_public,
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return CollectionOut.model_validate({**collection.__dict__, "analysis_count": 0})


@router.post("/collections/{collection_id}/analyses/{analysis_id}", response_model=Message)
def add_to_collection(
    collection_id: str, analysis_id: str, db: DbSession, user: CurrentUser
) -> Message:
    collection = db.get(Collection, collection_id)
    analysis = db.get(Analysis, analysis_id)
    if collection is None or collection.owner_id != user.id:
        raise HTTPException(status_code=404, detail="No such collection.")
    if analysis is None or analysis.owner_id != user.id:
        raise HTTPException(status_code=404, detail="No such analysis.")

    if analysis not in collection.analyses:
        collection.analyses.append(analysis)
        db.commit()
    return Message(message=f"Added to {collection.name}.")


@router.delete("/collections/{collection_id}/analyses/{analysis_id}", response_model=Message)
def remove_from_collection(
    collection_id: str, analysis_id: str, db: DbSession, user: CurrentUser
) -> Message:
    collection = db.get(Collection, collection_id)
    if collection is None or collection.owner_id != user.id:
        raise HTTPException(status_code=404, detail="No such collection.")
    analysis = db.get(Analysis, analysis_id)
    if analysis is not None and analysis in collection.analyses:
        collection.analyses.remove(analysis)
        db.commit()
    return Message(message="Removed from collection.")


@router.get("/collections/{collection_id}")
def collection_detail(collection_id: str, db: DbSession, user: CurrentUser) -> dict:
    collection = db.get(Collection, collection_id)
    if collection is None or collection.owner_id != user.id:
        raise HTTPException(status_code=404, detail="No such collection.")
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "is_public": collection.is_public,
        "created_at": collection.created_at,
        "analyses": [
            {
                "id": a.id,
                "title": a.title,
                "status": a.status.value,
                "overall_confidence": a.overall_confidence,
                "created_at": a.created_at,
            }
            for a in collection.analyses
        ],
    }


@router.delete("/collections/{collection_id}", response_model=Message)
def delete_collection(collection_id: str, db: DbSession, user: CurrentUser) -> Message:
    collection = db.get(Collection, collection_id)
    if collection is None or collection.owner_id != user.id:
        raise HTTPException(status_code=404, detail="No such collection.")
    db.delete(collection)
    db.commit()
    return Message(message="Collection deleted. The analyses in it were kept.")


# ---- tags -------------------------------------------------------------------------


@router.get("/tags", response_model=list[TagOut])
def list_tags(db: DbSession, user: CurrentUser) -> list[TagOut]:
    return [TagOut.model_validate(t) for t in tagging.list_tags(db, user)]


# ---- shares -----------------------------------------------------------------------


@router.post("/analyses/{analysis_id}/share", response_model=ShareOut, status_code=201)
def create_share(
    analysis_id: str,
    payload: ShareCreate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> ShareOut:
    """Create a read-only share link.

    The token is returned once and stored only as a keyed hash. If it is lost, revoke the
    share and make a new one — the plaintext genuinely cannot be recovered.
    """
    analysis = db.get(Analysis, analysis_id)
    if analysis is None or analysis.owner_id != user.id:
        raise HTTPException(status_code=404, detail="No such analysis.")

    token = new_opaque_token()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
        if payload.expires_in_days
        else None
    )

    share = Share(
        analysis_id=analysis.id,
        created_by_id=user.id,
        token_hash=hash_token(token),
        expires_at=expires_at,
        allow_export=payload.allow_export,
    )
    db.add(share)
    record_audit(
        db, AuditAction.ANALYSIS_SHARED, actor=user, target_type="analysis",
        target_id=analysis.id, request=request,
        detail={"expires_in_days": payload.expires_in_days, "allow_export": payload.allow_export},
    )
    db.commit()
    db.refresh(share)

    return ShareOut(
        id=share.id,
        url=f"{settings.FRONTEND_BASE_URL}/shared/{analysis.id}?token={token}",
        token=token,
        expires_at=share.expires_at,
        allow_export=share.allow_export,
        view_count=0,
    )


@router.get("/analyses/{analysis_id}/shares", response_model=list[ShareOut])
def list_shares(analysis_id: str, db: DbSession, user: CurrentUser) -> list[ShareOut]:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None or analysis.owner_id != user.id:
        raise HTTPException(status_code=404, detail="No such analysis.")
    return [
        ShareOut(
            id=s.id,
            url=f"{settings.FRONTEND_BASE_URL}/shared/{analysis_id}",
            token=None,  # never recoverable after creation
            expires_at=s.expires_at,
            allow_export=s.allow_export,
            view_count=s.view_count,
            revoked=s.revoked_at is not None,
        )
        for s in analysis.shares
    ]


@router.delete("/shares/{share_id}", response_model=Message)
def revoke_share(share_id: str, db: DbSession, user: CurrentUser) -> Message:
    share = db.get(Share, share_id)
    if share is None or share.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="No such share link.")
    share.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return Message(message="Share link revoked. It stops working immediately.")


# ---- notifications ----------------------------------------------------------------


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    db: DbSession,
    user: CurrentUser,
    unread_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
) -> list[NotificationOut]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.execute(
        stmt.order_by(Notification.created_at.desc()).limit(limit)
    ).scalars().all()
    return [NotificationOut.model_validate(n) for n in rows]


@router.post("/notifications/{notification_id}/read", response_model=Message)
def mark_read(notification_id: str, db: DbSession, user: CurrentUser) -> Message:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such notification.")
    notification.read_at = datetime.now(timezone.utc)
    db.commit()
    return Message(message="Marked as read.")


@router.post("/notifications/read-all", response_model=Message)
def mark_all_read(db: DbSession, user: CurrentUser) -> Message:
    count = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.read_at.is_(None))
        .update({"read_at": datetime.now(timezone.utc)})
    )
    db.commit()
    return Message(message=f"Marked {count} notifications as read.")


__all__ = ["router"]
