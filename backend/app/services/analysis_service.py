"""Creating and running analyses, and the background job runner behind them."""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.orchestrator import run_analysis
from app.core.logging import bind_request_context, get_logger, new_request_id
from app.core.security import hash_token, new_opaque_token
from app.db.models.analysis import Analysis, AnalysisStatus
from app.db.models.content import Document, SourceKind, Upload
from app.db.models.ops import Job, JobStatus
from app.db.models.user import User
from app.db.session import session_scope
from app.services.ingest import ExtractionResult, IngestError, compute_hash

logger = get_logger(__name__)

STAGE_LABELS = {
    "starting": "Preparing your text",
    "language": "Detecting language",
    "source_identification": "Identifying the source",
    "entities": "Extracting people, places and symbols",
    "calendar": "Converting dates between calendars",
    "astronomy": "Checking the sky for those dates",
    "historical_context": "Establishing historical context",
    "interpretation": "Gathering interpretations",
    "evidence": "Weighing the evidence",
    "complete": "Done",
}


def create_document(
    db: Session,
    extraction: ExtractionResult,
    *,
    owner: User | None = None,
    project_id: str | None = None,
    upload_id: str | None = None,
    source_url: str | None = None,
) -> Document:
    normalized = extraction.normalized
    content_hash = compute_hash(normalized.encode("utf-8"))

    # Re-analysing an identical text is a legitimate action (models and corpora change),
    # so documents are deduplicated but analyses are not.
    existing = (
        db.execute(
            select(Document).where(
                Document.content_hash == content_hash,
                Document.owner_id == (owner.id if owner else None),
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing

    document = Document(
        owner_id=owner.id if owner else None,
        project_id=project_id,
        upload_id=upload_id,
        title=extraction.title,
        source_kind=SourceKind(extraction.source_kind),
        source_url=source_url,
        raw_text=extraction.text,
        normalized_text=normalized,
        char_count=len(extraction.text),
        word_count=len(extraction.text.split()),
        ocr_applied=extraction.ocr_applied,
        ocr_confidence=extraction.ocr_confidence,
        extraction_metadata={
            **extraction.metadata,
            "warnings": extraction.warnings,
            "mime_type": extraction.mime_type,
            "page_count": extraction.page_count,
        },
        content_hash=content_hash,
    )
    db.add(document)
    db.flush()
    return document


def create_analysis(
    db: Session,
    document: Document,
    *,
    owner: User | None = None,
    title: str | None = None,
    project_id: str | None = None,
    options: dict | None = None,
) -> tuple[Analysis, str | None]:
    """Create a queued analysis. Returns it with the anonymous token, if applicable."""
    anonymous_token: str | None = None
    token_hash: str | None = None
    if owner is None:
        anonymous_token = new_opaque_token()
        token_hash = hash_token(anonymous_token)

    analysis = Analysis(
        owner_id=owner.id if owner else None,
        project_id=project_id,
        document_id=document.id,
        title=title or document.title or _derive_title(document.raw_text),
        status=AnalysisStatus.QUEUED,
        options=options or {},
        anonymous_token_hash=token_hash,
    )
    db.add(analysis)

    if owner is not None:
        owner.analyses_count = (owner.analyses_count or 0) + 1

    db.flush()
    return analysis, anonymous_token


def _derive_title(text: str, limit: int = 80) -> str:
    snippet = " ".join(text.split())[:limit].strip()
    if len(text) > limit:
        snippet = snippet.rsplit(" ", 1)[0] + "…"
    return snippet or "Untitled analysis"


# --------------------------------------------------------------------------------------
# Background execution
# --------------------------------------------------------------------------------------


def enqueue_analysis(db: Session, analysis: Analysis) -> Job:
    job = Job(
        job_type="run_analysis",
        status=JobStatus.PENDING,
        payload={"analysis_id": analysis.id},
        target_type="analysis",
        target_id=analysis.id,
        max_attempts=2,
    )
    db.add(job)
    db.flush()
    return job


def execute_job(job_id: str) -> None:
    """Run one queued job in its own session.

    Deliberately opens a fresh session rather than reusing the request's: the request has
    already returned by the time this runs, and sharing a session across that boundary is
    how you get objects detached mid-write.
    """
    bind_request_context(request_id=new_request_id())

    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None or job.status not in (JobStatus.PENDING, JobStatus.RETRYING):
            return
        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.started_at = datetime.now(UTC)
        db.commit()

        analysis_id = job.payload.get("analysis_id")
        analysis = db.get(Analysis, analysis_id) if analysis_id else None
        if analysis is None:
            job.status = JobStatus.FAILED
            job.last_error = f"Analysis {analysis_id} no longer exists."
            job.finished_at = datetime.now(UTC)
            return

        try:
            run_analysis(db, analysis)
            job.status = JobStatus.SUCCEEDED
            job.result = {
                "status": analysis.status.value,
                "claims": len(analysis.claims),
                "duration_ms": analysis.duration_ms,
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("job.failed", job_id=job_id, analysis_id=analysis_id)
            job.last_error = str(exc)[:2000]
            if job.attempts < job.max_attempts:
                job.status = JobStatus.RETRYING
            else:
                job.status = JobStatus.FAILED
                analysis.status = AnalysisStatus.FAILED
                analysis.error_message = (
                    "The analysis could not be completed. The error has been logged; "
                    "resubmitting sometimes succeeds if the cause was transient."
                )
                analysis.completed_at = datetime.now(UTC)
        finally:
            job.finished_at = datetime.now(UTC)


def run_in_background(job_id: str) -> None:
    """Run a job on a worker thread.

    This is the single-process path, appropriate for development and small deployments.
    For horizontal scaling, run `python -m app.workers.runner` as a separate process (or
    several): jobs live in the database, so the two approaches interoperate and nothing
    is lost if the web process restarts mid-analysis — the job is picked up again.
    """
    thread = threading.Thread(
        target=execute_job, args=(job_id,), daemon=True, name=f"job-{job_id[:8]}"
    )
    thread.start()


def start_analysis(
    db: Session,
    analysis: Analysis,
    *,
    background: bool = True,
) -> Job | None:
    if not background:
        run_analysis(db, analysis)
        return None
    job = enqueue_analysis(db, analysis)
    db.commit()
    run_in_background(job.id)
    return job


def stage_label(stage: str | None) -> str | None:
    if stage is None:
        return None
    return STAGE_LABELS.get(stage, stage.replace("_", " ").capitalize())


def resolve_upload(db: Session, upload_id: str, owner: User | None) -> Upload:
    upload = db.get(Upload, upload_id)
    if upload is None:
        raise IngestError("That upload no longer exists.")
    if upload.owner_id != (owner.id if owner else None):
        raise IngestError("That upload no longer exists.")
    return upload


__all__ = [
    "create_document",
    "create_analysis",
    "enqueue_analysis",
    "execute_job",
    "run_in_background",
    "start_analysis",
    "stage_label",
    "resolve_upload",
    "STAGE_LABELS",
]
