"""Analyses and everything they produce: claims, entities, references, reports.

The `ClaimType` enum here is the database-level enforcement of the epistemic contract
described in PROJECT_PLAN.md. Nothing reaches a user without one.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.db.types import JSONBType
from app.db.models.content import analysis_tags, collection_analyses

if TYPE_CHECKING:
    from app.db.models.content import Collection, Document, Project, Share, Tag
    from app.db.models.user import User


class AnalysisStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    """At least one agent failed but the report is still useful. Surfaced to the user
    with the failed sections named — a silent gap is worse than a stated one."""
    FAILED = "failed"
    CANCELLED = "cancelled"


class ClaimType(str, enum.Enum):
    """The epistemic vocabulary. See PROJECT_PLAN.md."""

    SOURCE_TEXT = "source_text"
    VERIFIED_HISTORY = "verified_history"
    ASTRONOMICAL_CALCULATION = "astronomical_calculation"
    TEXTUAL_ANALYSIS = "textual_analysis"
    TRADITIONAL_INTERPRETATION = "traditional_interpretation"
    SCHOLARLY_INTERPRETATION = "scholarly_interpretation"
    AI_HYPOTHESIS = "ai_hypothesis"
    UNCERTAIN = "uncertain"


class EntityType(str, enum.Enum):
    PERSON = "person"
    PLACE = "place"
    EMPIRE = "empire"
    NATION = "nation"
    RELIGION = "religion"
    CULTURE = "culture"
    DEITY = "deity"
    DATE = "date"
    CALENDAR = "calendar"
    ASTRONOMICAL_OBJECT = "astronomical_object"
    CONSTELLATION = "constellation"
    PLANET = "planet"
    STAR = "star"
    COMET = "comet"
    ECLIPSE = "eclipse"
    METEOR_SHOWER = "meteor_shower"
    MOON_PHASE = "moon_phase"
    ZODIAC_SIGN = "zodiac_sign"
    SACRED_NUMBER = "sacred_number"
    SYMBOL = "symbol"
    PROPHECY = "prophecy"
    PREDICTION = "prediction"
    HISTORICAL_EVENT = "historical_event"
    ARTIFACT = "artifact"
    TEXT_WORK = "text_work"
    OTHER = "other"


class Analysis(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "analyses"
    __table_args__ = (
        Index("ix_analyses_owner_created", "owner_id", "created_at"),
        Index("ix_analyses_status_created", "status", "created_at"),
        CheckConstraint(
            "overall_confidence IS NULL OR (overall_confidence >= 0 AND overall_confidence <= 1)",
            name="confidence_range",
        ),
    )

    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )

    title: Mapped[str] = mapped_column(String(500), default="Untitled analysis", nullable=False)
    status: Mapped[AnalysisStatus] = mapped_column(
        Enum(AnalysisStatus, native_enum=False, length=20),
        default=AnalysisStatus.QUEUED,
        index=True,
        nullable=False,
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(80))

    # Anonymous submissions are keyed by a client token so the homepage can poll and
    # display a result without forcing a signup.
    anonymous_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    detected_language: Mapped[str | None] = mapped_column(String(16))
    translation_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_identification: Mapped[dict] = mapped_column(JSONBType, default=dict)

    overall_confidence: Mapped[float | None] = mapped_column(Float)
    confidence_rationale: Mapped[str | None] = mapped_column(Text)

    options: Mapped[dict] = mapped_column(JSONBType, default=dict)
    """Advanced settings, if the user opened that drawer. Empty means 'defaults', which
    is the intended path for almost everyone."""

    error_message: Mapped[str | None] = mapped_column(Text)
    failed_stages: Mapped[list] = mapped_column(JSONBType, default=list)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    token_usage: Mapped[dict] = mapped_column(JSONBType, default=dict)

    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    parent_analysis_id: Mapped[str | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL")
    )

    owner: Mapped[User] = relationship(back_populates="analyses")
    project: Mapped[Project | None] = relationship(back_populates="analyses")
    document: Mapped[Document] = relationship(back_populates="analyses")
    claims: Mapped[list[Claim]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    entities: Mapped[list[Entity]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    references: Mapped[list[Reference]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    reports: Mapped[list[Report]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    agent_runs: Mapped[list[AgentRun]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    shares: Mapped[list[Share]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    tags: Mapped[list[Tag]] = relationship(secondary=analysis_tags, back_populates="analyses")
    collections: Mapped[list[Collection]] = relationship(
        secondary=collection_analyses, back_populates="analyses"
    )


class Claim(UUIDPrimaryKey, Timestamped, Base):
    """An individual assertion. Everything the report says is one of these.

    Separating claims from prose is what makes the "never present speculation as fact"
    rule mechanically checkable rather than a matter of tone.
    """

    __tablename__ = "claims"
    __table_args__ = (
        Index("ix_claims_analysis_type", "analysis_id", "claim_type"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    section: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    claim_type: Mapped[ClaimType] = mapped_column(
        Enum(ClaimType, native_enum=False, length=40), nullable=False
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    confidence_basis: Mapped[str | None] = mapped_column(String(500))

    # Which agent said it, and which algorithm/engine backs it (for calculations).
    produced_by: Mapped[str] = mapped_column(String(60), nullable=False)
    engine: Mapped[str | None] = mapped_column(String(120))
    algorithm_reference: Mapped[str | None] = mapped_column(String(300))

    supports_claim_id: Mapped[str | None] = mapped_column(
        ForeignKey("claims.id", ondelete="SET NULL")
    )
    contradicts_claim_id: Mapped[str | None] = mapped_column(
        ForeignKey("claims.id", ondelete="SET NULL")
    )

    text_span_start: Mapped[int | None] = mapped_column(Integer)
    text_span_end: Mapped[int | None] = mapped_column(Integer)
    quoted_text: Mapped[str | None] = mapped_column(Text)

    ordering: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONBType, default=dict)

    analysis: Mapped[Analysis] = relationship(back_populates="claims")
    references: Mapped[list[Reference]] = relationship(back_populates="claim")


class Entity(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "entities"
    __table_args__ = (Index("ix_entities_analysis_type", "analysis_id", "entity_type"),)

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(EntityType, native_enum=False, length=40), nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    canonical_name: Mapped[str | None] = mapped_column(String(300), index=True)
    aliases: Mapped[list] = mapped_column(JSONBType, default=list)
    description: Mapped[str | None] = mapped_column(Text)

    # How certain we are the entity is *in the text*, distinct from how certain we are
    # about what it means.
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    identification_confidence: Mapped[float | None] = mapped_column(Float)

    mention_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    mentions: Mapped[list] = mapped_column(JSONBType, default=list)

    earliest_year: Mapped[int | None] = mapped_column(Integer)
    latest_year: Mapped[int | None] = mapped_column(Integer)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    linked_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("historical_sources.id", ondelete="SET NULL")
    )
    linked_astronomical_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("astronomical_events.id", ondelete="SET NULL")
    )
    attributes: Mapped[dict] = mapped_column(JSONBType, default=dict)

    analysis: Mapped[Analysis] = relationship(back_populates="entities")


class Reference(UUIDPrimaryKey, Timestamped, Base):
    """A citation. Bound to the analysis and, where possible, to the specific claim."""

    __tablename__ = "references"
    __table_args__ = (Index("ix_references_analysis", "analysis_id", "ordering"),)

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    claim_id: Mapped[str | None] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"))
    historical_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("historical_sources.id", ondelete="SET NULL")
    )

    citation_text: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    authors: Mapped[list] = mapped_column(JSONBType, default=list)
    publication: Mapped[str | None] = mapped_column(String(300))
    year: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(String(2048))
    doi: Mapped[str | None] = mapped_column(String(200))
    locator: Mapped[str | None] = mapped_column(String(200))

    reference_kind: Mapped[str] = mapped_column(String(40), default="secondary", nullable=False)
    reliability: Mapped[str | None] = mapped_column(String(40))
    # False when the citation came from the model rather than the curated corpus. Such
    # references are rendered as "unverified" in the UI and never counted as evidence.
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ordering: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    analysis: Mapped[Analysis] = relationship(back_populates="references")
    claim: Mapped[Claim | None] = relationship(back_populates="references")


class Report(UUIDPrimaryKey, Timestamped, Base):
    """A rendered report. Versioned so re-running an analysis never destroys history."""

    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("analysis_id", "version", name="uq_reports_analysis_version"),
    )

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    executive_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sections: Mapped[list] = mapped_column(JSONBType, default=list)
    timeline: Mapped[list] = mapped_column(JSONBType, default=list)
    confidence_summary: Mapped[dict] = mapped_column(JSONBType, default=dict)
    further_reading: Mapped[list] = mapped_column(JSONBType, default=list)
    reasoning_trace: Mapped[list] = mapped_column(JSONBType, default=list)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generator_version: Mapped[str] = mapped_column(String(40), default="1.0.0", nullable=False)

    analysis: Mapped[Analysis] = relationship(back_populates="reports")


class AgentRun(UUIDPrimaryKey, Timestamped, Base):
    """One execution of one specialist agent. This is the explainability substrate:
    every conclusion can be traced back to the agent, prompt version, inputs and
    latency that produced it."""

    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_analysis_seq", "analysis_id", "sequence"),)

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(60), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(80))
    prompt_version: Mapped[str | None] = mapped_column(String(40))

    input_summary: Mapped[dict] = mapped_column(JSONBType, default=dict)
    output_summary: Mapped[dict] = mapped_column(JSONBType, default=dict)
    reasoning_summary: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    analysis: Mapped[Analysis] = relationship(back_populates="agent_runs")


__all__ = [
    "AnalysisStatus",
    "ClaimType",
    "EntityType",
    "Analysis",
    "Claim",
    "Entity",
    "Reference",
    "Report",
    "AgentRun",
]
