"""Semantic and keyword search over analyses and the reference corpus."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DbSession, OptionalUser, rate_limiter
from app.db.models.analysis import Analysis
from app.db.models.content import SearchHistory
from app.knowledge.rag import corpus_stats, retrieve, search_analyses
from app.schemas.user import SearchHit, SearchRequest, SearchResponse

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse, dependencies=[Depends(rate_limiter("search"))])
def search(payload: SearchRequest, db: DbSession, user: OptionalUser) -> SearchResponse:
    hits: list[SearchHit] = []
    notes: list[str] = []

    if payload.scope in ("corpus", "all"):
        for chunk in retrieve(db, payload.query, limit=payload.limit):
            hits.append(
                SearchHit(
                    kind="corpus",
                    id=chunk.chunk_id,
                    title=chunk.title,
                    snippet=chunk.content[:400],
                    score=chunk.score,
                    match_strength=chunk.match_strength,
                    citation=chunk.citation,
                    url=chunk.url,
                )
            )

    if payload.scope in ("analyses", "all"):
        if user is None:
            notes.append("Sign in to search your own analyses.")
        else:
            if payload.mode in ("semantic", "hybrid"):
                scored = search_analyses(db, payload.query, user.id, limit=payload.limit)
                by_id = {
                    a.id: a
                    for a in db.execute(
                        select(Analysis).where(Analysis.id.in_([sid for sid, _ in scored]))
                    ).scalars()
                }
                for analysis_id, score in scored:
                    analysis = by_id.get(analysis_id)
                    if analysis is None:
                        continue
                    hits.append(
                        SearchHit(
                            kind="analysis",
                            id=analysis.id,
                            title=analysis.title,
                            snippet=(analysis.confidence_rationale or "")[:400],
                            score=score,
                            created_at=analysis.created_at,
                        )
                    )

            if payload.mode in ("keyword", "hybrid"):
                pattern = f"%{payload.query}%"
                rows = (
                    db.execute(
                        select(Analysis)
                        .where(
                            Analysis.owner_id == user.id,
                            or_(
                                Analysis.title.ilike(pattern),
                                Analysis.confidence_rationale.ilike(pattern),
                            ),
                        )
                        .order_by(Analysis.created_at.desc())
                        .limit(payload.limit)
                    )
                    .scalars()
                    .all()
                )
                seen = {h.id for h in hits}
                for analysis in rows:
                    if analysis.id in seen:
                        continue
                    hits.append(
                        SearchHit(
                            kind="analysis",
                            id=analysis.id,
                            title=analysis.title,
                            snippet=(analysis.confidence_rationale or "")[:400],
                            # A keyword hit is exact-substring, so it is scored at 1.0
                            # rather than being blended into the semantic scale, where
                            # the two numbers would not mean the same thing.
                            score=1.0,
                            match_strength="keyword",
                            created_at=analysis.created_at,
                        )
                    )

    hits.sort(key=lambda h: h.score, reverse=True)
    hits = hits[: payload.limit]

    if user is not None:
        db.add(
            SearchHistory(
                user_id=user.id,
                query=payload.query[:1000],
                mode=payload.mode,
                result_count=len(hits),
                filters={"scope": payload.scope},
            )
        )
        db.commit()

    if not hits:
        notes.append(
            "No matches above the relevance floor. Weak matches are withheld rather than "
            "shown, because a poor match presented as a source is worse than no result."
        )

    return SearchResponse(
        query=payload.query,
        mode=payload.mode,
        scope=payload.scope,
        total=len(hits),
        hits=hits,
        note=" ".join(notes) or None,
    )


@router.get("/history")
def history(db: DbSession, user: CurrentUser, limit: int = Query(20, ge=1, le=100)) -> dict:
    rows = (
        db.execute(
            select(SearchHistory)
            .where(SearchHistory.user_id == user.id)
            .order_by(SearchHistory.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "query": row.query,
                "mode": row.mode,
                "result_count": row.result_count,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


@router.delete("/history")
def clear_history(db: DbSession, user: CurrentUser) -> dict:
    deleted = db.query(SearchHistory).filter(SearchHistory.user_id == user.id).delete()
    db.commit()
    return {"message": f"Cleared {deleted} search history entries."}


@router.get("/corpus/stats")
def stats(db: DbSession) -> dict:
    """What is actually in the reference corpus — stated so nobody over-reads a miss."""
    payload = corpus_stats(db)
    payload["disclosure"] = (
        "This is a curated demonstration corpus, not a comprehensive scholarly database. "
        "A text absent from it is not thereby unknown or unusual."
    )
    return payload


__all__ = ["router"]
