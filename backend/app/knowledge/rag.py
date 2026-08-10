"""Retrieval over the curated corpus and over a user's own analyses.

Two backends behind one interface:

* **pgvector** when the database is PostgreSQL — an ANN/exact scan in the database.
* **In-process cosine scan** otherwise (SQLite in tests, or a Postgres instance without
  the extension). Correct, just slower; fine at seed-corpus scale.

Retrieval quality is *reported*, not hidden. Every hit carries its cosine score and a
lexical-overlap cross-check, and `retrieve` refuses to return anything below a floor —
a bad match presented as a source is worse than no match, because it manufactures a
citation that looks authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.knowledge import AnalysisEmbedding, KnowledgeChunk
from app.knowledge.embeddings import (
    cosine_similarity,
    embed,
    get_embedder,
    jaccard_overlap,
)

logger = get_logger(__name__)

#: Below this cosine, a "match" is noise. Tuned against the seed corpus so that a quoted
#: passage reliably finds its own source while unrelated prose finds nothing.
MIN_SCORE = 0.18

#: A hit with a high cosine but almost no shared vocabulary is a hashing artefact.
MIN_LEXICAL_OVERLAP = 0.02


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    title: str
    content: str
    citation: str | None
    url: str | None
    source_key: str
    kind: str
    tradition: str | None
    score: float
    lexical_overlap: float
    metadata: dict

    @property
    def match_strength(self) -> str:
        """Plain-language strength, because a raw cosine means nothing to most users.

        Thresholds are calibrated against the seed corpus, not guessed: a verbatim quote
        of an indexed passage lands at ~0.55 cosine with ~0.30 token overlap, while a
        thematically related but differently worded query lands near 0.30 with ~0.07.
        Re-check these if the embedder is swapped — they are properties of the encoder,
        not universal constants.
        """
        if self.score >= 0.45 and self.lexical_overlap >= 0.20:
            return "strong"
        if self.score >= 0.25:
            return "moderate"
        return "weak"

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "title": self.title,
            "content": self.content,
            "citation": self.citation,
            "url": self.url,
            "source_key": self.source_key,
            "kind": self.kind,
            "tradition": self.tradition,
            "score": round(self.score, 4),
            "lexical_overlap": round(self.lexical_overlap, 4),
            "match_strength": self.match_strength,
            "metadata": self.metadata,
        }


def _supports_pgvector(db: Session) -> bool:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return False
    try:
        from pgvector.sqlalchemy import Vector  # noqa: F401
    except ImportError:
        return False
    return True


def retrieve(
    db: Session,
    query: str,
    *,
    limit: int = 8,
    kind: str | None = None,
    tradition: str | None = None,
    min_score: float = MIN_SCORE,
) -> list[RetrievedChunk]:
    """Semantic search over the knowledge corpus."""
    if not query or not query.strip():
        return []

    query_vector = embed(query)

    if _supports_pgvector(db):
        candidates = _retrieve_pgvector(db, query_vector, limit * 4, kind, tradition)
    else:
        candidates = _retrieve_scan(db, query_vector, kind, tradition)

    results: list[RetrievedChunk] = []
    for chunk, score in candidates:
        overlap = jaccard_overlap(query, chunk.content)
        if score < min_score or overlap < MIN_LEXICAL_OVERLAP:
            continue
        results.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                title=chunk.title,
                content=chunk.content,
                citation=chunk.citation,
                url=chunk.url,
                source_key=chunk.source_key,
                kind=chunk.kind,
                tradition=chunk.tradition,
                score=score,
                lexical_overlap=overlap,
                metadata=chunk.metadata_json or {},
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]


def _retrieve_pgvector(
    db: Session,
    query_vector: list[float],
    limit: int,
    kind: str | None,
    tradition: str | None,
) -> list[tuple[KnowledgeChunk, float]]:
    stmt = select(KnowledgeChunk).where(KnowledgeChunk.embedding.is_not(None))
    if kind:
        stmt = stmt.where(KnowledgeChunk.kind == kind)
    if tradition:
        stmt = stmt.where(KnowledgeChunk.tradition == tradition)
    # `cosine_distance` = 1 - cosine_similarity for normalised vectors.
    stmt = stmt.order_by(KnowledgeChunk.embedding.cosine_distance(query_vector)).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [(row, cosine_similarity(query_vector, row.embedding or [])) for row in rows]


def _retrieve_scan(
    db: Session, query_vector: list[float], kind: str | None, tradition: str | None
) -> list[tuple[KnowledgeChunk, float]]:
    stmt = select(KnowledgeChunk)
    if kind:
        stmt = stmt.where(KnowledgeChunk.kind == kind)
    if tradition:
        stmt = stmt.where(KnowledgeChunk.tradition == tradition)
    rows = db.execute(stmt).scalars().all()
    scored = [(row, cosine_similarity(query_vector, row.embedding or [])) for row in rows]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def index_chunk(
    db: Session,
    *,
    kind: str,
    source_key: str,
    title: str,
    content: str,
    citation: str | None = None,
    url: str | None = None,
    tradition: str | None = None,
    metadata: dict[str, Any] | None = None,
    historical_source_id: str | None = None,
) -> KnowledgeChunk:
    """Insert or refresh one corpus chunk. Idempotent on (kind, source_key, title)."""
    existing = db.execute(
        select(KnowledgeChunk).where(
            KnowledgeChunk.kind == kind,
            KnowledgeChunk.source_key == source_key,
            KnowledgeChunk.title == title,
        )
    ).scalar_one_or_none()

    embedder = get_embedder()
    vector = embedder.embed(f"{title}\n{content}")

    if existing:
        existing.content = content
        existing.citation = citation
        existing.url = url
        existing.tradition = tradition
        existing.metadata_json = metadata or {}
        existing.embedding = vector
        existing.embedding_model = embedder.model_name
        existing.tokens = len(content.split())
        existing.historical_source_id = historical_source_id
        return existing

    chunk = KnowledgeChunk(
        kind=kind,
        source_key=source_key,
        title=title,
        content=content,
        citation=citation,
        url=url,
        tradition=tradition,
        tokens=len(content.split()),
        embedding=vector,
        embedding_model=embedder.model_name,
        metadata_json=metadata or {},
        historical_source_id=historical_source_id,
    )
    db.add(chunk)
    return chunk


def index_analysis(
    db: Session, analysis_id: str, owner_id: str | None, summary_text: str
) -> AnalysisEmbedding:
    """Make a completed analysis searchable by its owner."""
    existing = db.execute(
        select(AnalysisEmbedding).where(AnalysisEmbedding.analysis_id == analysis_id)
    ).scalar_one_or_none()

    embedder = get_embedder()
    vector = embedder.embed(summary_text)

    if existing:
        existing.summary_text = summary_text
        existing.embedding = vector
        existing.embedding_model = embedder.model_name
        return existing

    record = AnalysisEmbedding(
        analysis_id=analysis_id,
        owner_id=owner_id,
        summary_text=summary_text,
        embedding=vector,
        embedding_model=embedder.model_name,
    )
    db.add(record)
    return record


def search_analyses(
    db: Session, query: str, owner_id: str | None, limit: int = 20, min_score: float = 0.12
) -> list[tuple[str, float]]:
    """Semantic search across a user's own analyses. Returns (analysis_id, score)."""
    if not query.strip():
        return []

    query_vector = embed(query)
    stmt = select(AnalysisEmbedding)
    # Scoping to the owner is an authorisation boundary, not a filter convenience:
    # without it, one user's semantic search would surface another user's work.
    if owner_id is not None:
        stmt = stmt.where(AnalysisEmbedding.owner_id == owner_id)
    else:
        stmt = stmt.where(AnalysisEmbedding.owner_id.is_(None))

    rows = db.execute(stmt).scalars().all()
    scored = [
        (row.analysis_id, cosine_similarity(query_vector, row.embedding or [])) for row in rows
    ]
    scored = [pair for pair in scored if pair[1] >= min_score]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]


def corpus_stats(db: Session) -> dict:
    from sqlalchemy import func

    total = db.execute(select(func.count()).select_from(KnowledgeChunk)).scalar_one()
    by_kind = dict(
        db.execute(select(KnowledgeChunk.kind, func.count()).group_by(KnowledgeChunk.kind)).all()
    )
    by_tradition = dict(
        db.execute(
            select(KnowledgeChunk.tradition, func.count())
            .where(KnowledgeChunk.tradition.is_not(None))
            .group_by(KnowledgeChunk.tradition)
        ).all()
    )
    return {
        "total_chunks": total,
        "by_kind": by_kind,
        "by_tradition": by_tradition,
        "embedding_model": get_embedder().model_name,
        "vector_backend": "pgvector" if _supports_pgvector(db) else "in-process cosine scan",
    }


__all__ = [
    "MIN_SCORE",
    "RetrievedChunk",
    "retrieve",
    "index_chunk",
    "index_analysis",
    "search_analyses",
    "corpus_stats",
]
