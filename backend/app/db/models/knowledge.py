"""Reference data: historical sources, astronomical catalogues, calendar systems,
prompt templates and the RAG chunk index.

These tables are *curated*, not user-generated. Everything in them is expected to be
citable — that is what lets the analysis engine distinguish evidence from conjecture.
"""

from __future__ import annotations

import enum

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.db.types import JSONBType, VectorType

EMBEDDING_DIM = 384


class SourceTradition(str, enum.Enum):
    HEBREW_BIBLE = "hebrew_bible"
    NEW_TESTAMENT = "new_testament"
    APOCRYPHA = "apocrypha"
    QURANIC = "quranic"
    MESOPOTAMIAN = "mesopotamian"
    EGYPTIAN = "egyptian"
    GREEK = "greek"
    ROMAN = "roman"
    HINDU = "hindu"
    BUDDHIST = "buddhist"
    CHINESE = "chinese"
    MAYAN = "mayan"
    AZTEC = "aztec"
    NORSE = "norse"
    CELTIC = "celtic"
    PERSIAN = "persian"
    ISLAMIC_SCHOLARLY = "islamic_scholarly"
    MEDIEVAL_EUROPEAN = "medieval_european"
    EARLY_MODERN = "early_modern"
    INDIGENOUS_AMERICAN = "indigenous_american"
    AFRICAN = "african"
    OTHER = "other"


class AstroEventType(str, enum.Enum):
    SOLAR_ECLIPSE = "solar_eclipse"
    LUNAR_ECLIPSE = "lunar_eclipse"
    COMET = "comet"
    METEOR_SHOWER = "meteor_shower"
    PLANETARY_CONJUNCTION = "planetary_conjunction"
    OCCULTATION = "occultation"
    SUPERNOVA = "supernova"
    EQUINOX = "equinox"
    SOLSTICE = "solstice"
    MOON_PHASE = "moon_phase"
    HELIACAL_RISING = "heliacal_rising"
    TRANSIT = "transit"
    SOLAR_CYCLE = "solar_cycle"
    OTHER = "other"


class HistoricalSource(UUIDPrimaryKey, Timestamped, Base):
    """A text, inscription, chronicle or scholarly work that can be cited."""

    __tablename__ = "historical_sources"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_historical_sources_slug"),
        Index("ix_historical_sources_tradition", "tradition"),
    )

    slug: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    alternate_titles: Mapped[list] = mapped_column(JSONBType, default=list)
    tradition: Mapped[str] = mapped_column(String(40), default=SourceTradition.OTHER.value)
    language: Mapped[str | None] = mapped_column(String(60))
    script: Mapped[str | None] = mapped_column(String(60))

    author: Mapped[str | None] = mapped_column(String(300))
    composition_earliest_year: Mapped[int | None] = mapped_column(Integer)
    composition_latest_year: Mapped[int | None] = mapped_column(Integer)
    dating_note: Mapped[str | None] = mapped_column(Text)
    """Ancient dating is contested far more often than popular sources admit. This field
    records *why* the range is what it is, and is surfaced verbatim in reports."""

    region: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    canonical_citation: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2048))
    license: Mapped[str | None] = mapped_column(String(200))
    reliability: Mapped[str] = mapped_column(String(40), default="scholarly_consensus")
    is_primary_source: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    attributes: Mapped[dict] = mapped_column(JSONBType, default=dict)


class SourcePassage(UUIDPrimaryKey, Timestamped, Base):
    """A quotable excerpt from a historical source, used for source identification."""

    __tablename__ = "source_passages"
    __table_args__ = (Index("ix_source_passages_source_ref", "source_id", "reference_label"),)

    source_id: Mapped[str] = mapped_column(
        ForeignKey("historical_sources.id", ondelete="CASCADE"), index=True, nullable=False
    )
    reference_label: Mapped[str] = mapped_column(String(160), nullable=False)
    original_text: Mapped[str | None] = mapped_column(Text)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    translation_credit: Mapped[str | None] = mapped_column(String(300))
    themes: Mapped[list] = mapped_column(JSONBType, default=list)
    astronomical_content: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    prophetic_content: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class AstronomicalEvent(UUIDPrimaryKey, Timestamped, Base):
    """A catalogued celestial event.

    Rows are either *observational records* (attested in a historical document) or
    *computed* (produced by the ephemeris engine and cached). `is_computed` keeps the two
    from being confused, because an ancient record of an eclipse and a modern calculation
    of one are different kinds of evidence.
    """

    __tablename__ = "astronomical_events"
    __table_args__ = (
        Index("ix_astro_events_type_year", "event_type", "year"),
        Index("ix_astro_events_jd", "julian_day"),
    )

    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(200), index=True)
    label: Mapped[str] = mapped_column(String(300), nullable=False)

    # Astronomical year numbering (1 BCE = year 0, 2 BCE = -1) to keep arithmetic sane.
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    month: Mapped[int | None] = mapped_column(Integer)
    day: Mapped[int | None] = mapped_column(Integer)
    julian_day: Mapped[float | None] = mapped_column(Float, index=True)
    calendar_used: Mapped[str] = mapped_column(String(20), default="julian_gregorian_proleptic")

    magnitude: Mapped[float | None] = mapped_column(Float)
    duration_minutes: Mapped[float | None] = mapped_column(Float)
    visibility_regions: Mapped[list] = mapped_column(JSONBType, default=list)
    visibility_uncertainty: Mapped[str | None] = mapped_column(Text)
    delta_t_seconds: Mapped[float | None] = mapped_column(Float)

    bodies: Mapped[list] = mapped_column(JSONBType, default=list)
    constellation: Mapped[str | None] = mapped_column(String(80))
    separation_degrees: Mapped[float | None] = mapped_column(Float)

    is_computed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    computation_engine: Mapped[str | None] = mapped_column(String(120))
    accuracy_note: Mapped[str | None] = mapped_column(Text)

    historical_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("historical_sources.id", ondelete="SET NULL")
    )
    description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(JSONBType, default=dict)


class CalendarSystem(UUIDPrimaryKey, Timestamped, Base):
    """Metadata about a calendar the engine can convert to and from."""

    __tablename__ = "calendar_systems"

    key: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    culture: Mapped[str | None] = mapped_column(String(160))
    calendar_kind: Mapped[str] = mapped_column(String(40), default="solar")
    epoch_description: Mapped[str | None] = mapped_column(Text)
    epoch_rd: Mapped[int | None] = mapped_column(Integer)
    """Rata Die of the calendar's epoch (RD 1 = 1 Jan 1 CE proleptic Gregorian)."""

    months_per_year: Mapped[int | None] = mapped_column(Integer)
    supports_conversion: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    conversion_caveats: Mapped[str | None] = mapped_column(Text)
    """Why a conversion may be approximate — observational month starts, intercalation
    uncertainty, regional variation. Always shown next to a converted date."""

    active_from_year: Mapped[int | None] = mapped_column(Integer)
    active_to_year: Mapped[int | None] = mapped_column(Integer)
    references: Mapped[list] = mapped_column(JSONBType, default=list)
    attributes: Mapped[dict] = mapped_column(JSONBType, default=dict)


class KnowledgeChunk(UUIDPrimaryKey, Timestamped, Base):
    """An embedded chunk for retrieval-augmented generation."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (Index("ix_knowledge_chunks_kind", "kind", "source_key"),)

    kind: Mapped[str] = mapped_column(String(40), default="source_passage", nullable=False)
    source_key: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citation: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2048))
    tradition: Mapped[str | None] = mapped_column(String(40))
    tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding: Mapped[list | None] = mapped_column(VectorType(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(80))
    metadata_json: Mapped[dict] = mapped_column(JSONBType, default=dict)

    historical_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("historical_sources.id", ondelete="CASCADE")
    )


class AnalysisEmbedding(UUIDPrimaryKey, Timestamped, Base):
    """Embedding of a completed analysis so users can semantically search their own work."""

    __tablename__ = "analysis_embeddings"

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(VectorType(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(80))


class PromptTemplate(UUIDPrimaryKey, Timestamped, Base):
    """Versioned agent prompts, editable by admins without a redeploy.

    Only one version per agent is active at a time; older versions are retained so an
    existing report can always be explained in terms of the prompt that produced it.
    """

    __tablename__ = "prompt_templates"
    __table_args__ = (
        UniqueConstraint("agent_name", "version", name="uq_prompt_templates_agent_version"),
    )

    agent_name: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    instruction_template: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Dataset(UUIDPrimaryKey, Timestamped, Base):
    """A registered reference dataset. Admins can see what is loaded, from where, and
    under what licence — the honest answer to "where did this claim come from?"."""

    __tablename__ = "datasets"

    key: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(200))
    license: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[str | None] = mapped_column(String(40))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    attributes: Mapped[dict] = mapped_column(JSONBType, default=dict)


__all__ = [
    "EMBEDDING_DIM",
    "SourceTradition",
    "AstroEventType",
    "HistoricalSource",
    "SourcePassage",
    "AstronomicalEvent",
    "CalendarSystem",
    "KnowledgeChunk",
    "AnalysisEmbedding",
    "PromptTemplate",
    "Dataset",
]
