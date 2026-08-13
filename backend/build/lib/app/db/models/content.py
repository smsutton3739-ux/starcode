"""User content: projects, uploads, documents, collections, tags and shares."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.db.types import JSONBType

if TYPE_CHECKING:
    from app.db.models.analysis import Analysis
    from app.db.models.user import User


class SourceKind(str, enum.Enum):
    PASTED_TEXT = "pasted_text"
    FILE_UPLOAD = "file_upload"
    URL = "url"
    API = "api"


class UploadStatus(str, enum.Enum):
    RECEIVED = "received"
    SCANNING = "scanning"
    EXTRACTING = "extracting"
    READY = "ready"
    REJECTED = "rejected"
    FAILED = "failed"


# ---- association tables -----------------------------------------------------

analysis_tags = Table(
    "analysis_tags",
    Base.metadata,
    Column("analysis_id", ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

collection_analyses = Table(
    "collection_analyses",
    Base.metadata,
    Column("collection_id", ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
    Column("analysis_id", ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True),
)


class Project(UUIDPrimaryKey, Timestamped, Base):
    """A workspace grouping related documents and analyses."""

    __tablename__ = "projects"

    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONBType, default=dict)

    owner: Mapped[User] = relationship(back_populates="projects")
    documents: Mapped[list[Document]] = relationship(back_populates="project")
    analyses: Mapped[list[Analysis]] = relationship(back_populates="project")


class Upload(UUIDPrimaryKey, Timestamped, Base):
    """A raw file received from a user, before/while text is extracted from it.

    `sha256` is unique per owner so re-uploading the same manuscript is deduplicated
    rather than re-OCR'd.
    """

    __tablename__ = "uploads"
    __table_args__ = (
        UniqueConstraint("owner_id", "sha256", name="uq_uploads_owner_sha256"),
        Index("ix_uploads_status_created", "status", "created_at"),
    )

    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    detected_mime_type: Mapped[str | None] = mapped_column(String(160))
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus, native_enum=False, length=20),
        default=UploadStatus.RECEIVED,
        nullable=False,
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    page_count: Mapped[int | None] = mapped_column(Integer)
    file_metadata: Mapped[dict] = mapped_column(JSONBType, default=dict)

    documents: Mapped[list[Document]] = relationship(back_populates="upload")


class Document(UUIDPrimaryKey, Timestamped, Base):
    """Extracted, normalised text ready for analysis. One per logical source text."""

    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_owner_created", "owner_id", "created_at"),)

    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    upload_id: Mapped[str | None] = mapped_column(ForeignKey("uploads.id", ondelete="SET NULL"))

    title: Mapped[str | None] = mapped_column(String(500))
    source_kind: Mapped[SourceKind] = mapped_column(
        Enum(SourceKind, native_enum=False, length=20), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(String(2048))

    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    detected_language: Mapped[str | None] = mapped_column(String(16))
    detected_language_confidence: Mapped[float | None] = mapped_column()
    detected_script: Mapped[str | None] = mapped_column(String(40))

    # OCR provenance matters for trust: a low-confidence scan should temper every
    # downstream claim, so it is stored explicitly rather than inferred.
    ocr_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ocr_confidence: Mapped[float | None] = mapped_column()

    extraction_metadata: Mapped[dict] = mapped_column(JSONBType, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    owner: Mapped[User] = relationship(back_populates="documents")
    project: Mapped[Project | None] = relationship(back_populates="documents")
    upload: Mapped[Upload | None] = relationship(back_populates="documents")
    analyses: Mapped[list[Analysis]] = relationship(back_populates="document")


class Tag(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("owner_id", "slug", name="uq_tags_owner_slug"),)

    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    color: Mapped[str | None] = mapped_column(String(16))

    analyses: Mapped[list[Analysis]] = relationship(secondary=analysis_tags, back_populates="tags")


class Collection(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "collections"

    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    owner: Mapped[User] = relationship(back_populates="collections")
    analyses: Mapped[list[Analysis]] = relationship(
        secondary=collection_analyses, back_populates="collections"
    )


class Share(UUIDPrimaryKey, Timestamped, Base):
    """A capability token granting read access to one analysis.

    The token is stored hashed; the plaintext is shown to the creator once. Expiry and
    revocation are both supported because a shared prophecy analysis often shouldn't
    live forever.
    """

    __tablename__ = "shares"

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    allow_export: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    analysis: Mapped[Analysis] = relationship(back_populates="shares")


class SearchHistory(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "search_history"
    __table_args__ = (Index("ix_search_history_user_created", "user_id", "created_at"),)

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    query: Mapped[str] = mapped_column(String(1000), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="semantic", nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    filters: Mapped[dict] = mapped_column(JSONBType, default=dict)


__all__ = [
    "SourceKind",
    "UploadStatus",
    "Project",
    "Upload",
    "Document",
    "Tag",
    "Collection",
    "Share",
    "SearchHistory",
    "analysis_tags",
    "collection_analyses",
]
