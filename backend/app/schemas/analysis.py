"""Request and response schemas for analyses, documents and reports."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings
from app.schemas.common import ORMModel


class AnalysisOptions(BaseModel):
    """Advanced settings. Every field has a sensible default — the homepage never shows
    this, and a user who never opens the drawer gets the full analysis."""

    output_language: str = Field(default="en", max_length=16)
    include_traditional_interpretations: bool = True
    include_alternative_interpretations: bool = True
    include_astronomical_correlation: bool = True
    astronomical_search_window_years: int = Field(default=5, ge=0, le=200)
    calendar_preference: str | None = Field(default=None, max_length=40)
    maya_correlation: int = Field(default=584283, ge=580000, le=590000)
    detail_level: Literal["standard", "brief", "exhaustive"] = "standard"
    model_override: str | None = Field(default=None, max_length=80)

    @field_validator("output_language")
    @classmethod
    def _valid_language(cls, v: str) -> str:
        if not v.replace("-", "").isalpha():
            raise ValueError("output_language must be a language code such as 'en' or 'pt-BR'")
        return v


class AnalyzeRequest(BaseModel):
    """The one-button request. Exactly one input source must be supplied."""

    text: str | None = Field(default=None, max_length=settings.MAX_TEXT_CHARS)
    url: str | None = Field(default=None, max_length=2048)
    upload_id: str | None = Field(default=None, max_length=64)
    document_id: str | None = Field(default=None, max_length=64)

    title: str | None = Field(default=None, max_length=500)
    project_id: str | None = Field(default=None, max_length=64)
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)

    @model_validator(mode="after")
    def _exactly_one_source(self) -> AnalyzeRequest:
        supplied = [
            name
            for name, value in (
                ("text", self.text),
                ("url", self.url),
                ("upload_id", self.upload_id),
                ("document_id", self.document_id),
            )
            if value
        ]
        if not supplied:
            raise ValueError(
                "Provide something to analyse: text, a url, an upload_id, or a document_id."
            )
        if len(supplied) > 1:
            raise ValueError(f"Provide exactly one source; received {', '.join(supplied)}.")
        if self.text is not None and not self.text.strip():
            raise ValueError("The text is empty.")
        return self


class CitationOut(ORMModel):
    id: str
    citation_text: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    publication: str | None = None
    year: int | None = None
    url: str | None = None
    doi: str | None = None
    locator: str | None = None
    reference_kind: str
    reliability: str | None = None
    verified: bool


class ClaimOut(ORMModel):
    id: str
    section: str
    claim_type: str
    statement: str
    reasoning: str | None = None
    confidence: float
    confidence_basis: str | None = None
    produced_by: str
    engine: str | None = None
    algorithm_reference: str | None = None
    quoted_text: str | None = None
    text_span_start: int | None = None
    text_span_end: int | None = None
    ordering: int
    payload: dict[str, Any] = Field(default_factory=dict)
    references: list[CitationOut] = Field(default_factory=list)
    presentation: dict[str, str] | None = None

    # True when the reader's tier withholds this claim's content. The claim is still
    # present with its type, section, ordering and confidence intact — only the readable
    # fields are replaced — so a client can show what is being withheld rather than
    # rendering a shorter report that looks like the analysis simply found less.
    locked: bool = False


class EntityOut(ORMModel):
    id: str
    entity_type: str
    name: str
    canonical_name: str | None = None
    aliases: list[Any] = Field(default_factory=list)
    description: str | None = None
    extraction_confidence: float
    identification_confidence: float | None = None
    mention_count: int
    mentions: list[Any] = Field(default_factory=list)
    earliest_year: int | None = None
    latest_year: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ReportOut(ORMModel):
    id: str
    version: int
    executive_summary: str
    sections: list[dict[str, Any]]
    timeline: list[dict[str, Any]]
    confidence_summary: dict[str, Any]
    further_reading: list[dict[str, Any]]
    reasoning_trace: list[dict[str, Any]]
    word_count: int
    generator_version: str


class AgentRunOut(ORMModel):
    id: str
    agent_name: str
    sequence: int
    status: str
    attempt: int
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    reasoning_summary: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None


class DocumentOut(ORMModel):
    id: str
    title: str | None = None
    source_kind: str
    source_url: str | None = None
    char_count: int
    word_count: int
    detected_language: str | None = None
    detected_script: str | None = None
    ocr_applied: bool
    ocr_confidence: float | None = None
    extraction_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AnalysisSummary(ORMModel):
    id: str
    title: str
    status: str
    progress: float
    current_stage: str | None = None
    detected_language: str | None = None
    overall_confidence: float | None = None
    is_favorite: bool
    created_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
    failed_stages: list[Any] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class AnalysisDetail(AnalysisSummary):
    document: DocumentOut | None = None
    confidence_rationale: str | None = None
    source_identification: dict[str, Any] = Field(default_factory=dict)
    translation_applied: bool = False
    options: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    token_usage: dict[str, Any] = Field(default_factory=dict)
    claims: list[ClaimOut] = Field(default_factory=list)
    entities: list[EntityOut] = Field(default_factory=list)
    report: ReportOut | None = None
    agent_runs: list[AgentRunOut] = Field(default_factory=list)


class AnalysisCreated(BaseModel):
    """The response the homepage gets immediately. `anonymous_token` is returned only
    for unauthenticated submissions and is the only way to reach that analysis again."""

    id: str
    status: str
    progress: float
    poll_url: str
    anonymous_token: str | None = None
    message: str


class AnalysisStatusOut(BaseModel):
    id: str
    status: str
    progress: float
    current_stage: str | None = None
    stage_label: str | None = None
    error_message: str | None = None
    failed_stages: list[str] = Field(default_factory=list)


class UploadOut(ORMModel):
    id: str
    original_filename: str
    mime_type: str
    detected_mime_type: str | None = None
    byte_size: int
    status: str
    page_count: int | None = None
    rejection_reason: str | None = None
    file_metadata: dict[str, Any] = Field(default_factory=dict)


class UploadResult(BaseModel):
    upload: UploadOut
    document_id: str
    extracted_characters: int
    ocr_applied: bool
    ocr_confidence: float | None = None
    warnings: list[str] = Field(default_factory=list)
    preview: str


class UrlPreview(BaseModel):
    url: str
    final_url: str
    title: str | None = None
    document_id: str
    extracted_characters: int
    preview: str
    warnings: list[str] = Field(default_factory=list)


class AnalysisUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    is_favorite: bool | None = None
    project_id: str | None = None
    tags: list[str] | None = None


__all__ = [
    "AnalysisOptions",
    "AnalyzeRequest",
    "AnalysisCreated",
    "AnalysisStatusOut",
    "AnalysisSummary",
    "AnalysisDetail",
    "AnalysisUpdate",
    "ClaimOut",
    "CitationOut",
    "EntityOut",
    "ReportOut",
    "AgentRunOut",
    "DocumentOut",
    "UploadOut",
    "UploadResult",
    "UrlPreview",
]
