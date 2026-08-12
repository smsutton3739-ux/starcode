"""What happens to an analysis when the process running it is killed.

This is the ordinary case on any host that stops idle instances, which every free tier
does. The API threads each analysis rather than requiring a separate worker, so if
nothing sweeps for abandoned work, an interrupted analysis sits at "running" forever and
the reader is told to keep waiting for something nobody is doing.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.models.analysis import Analysis, AnalysisStatus
from app.db.models.content import Document, SourceKind
from app.db.models.ops import Job, JobStatus
from app.workers.runner import STALE_AFTER, requeue_stale_jobs

TEXT = "In the third year of the reign of Belshazzar king of Babylon."


def abandoned_job(db: Session, *, age: timedelta, attempts: int = 0) -> tuple[Job, Analysis]:
    """A job left in RUNNING by a process that died, and the analysis it belongs to."""
    document = Document(
        raw_text=TEXT,
        normalized_text=TEXT,
        source_kind=SourceKind.PASTED_TEXT,
        char_count=len(TEXT),
        word_count=len(TEXT.split()),
        content_hash=hashlib.sha256(TEXT.encode()).hexdigest(),
    )
    db.add(document)
    db.flush()

    analysis = Analysis(document_id=document.id, status=AnalysisStatus.RUNNING)
    db.add(analysis)
    db.flush()

    job = Job(
        job_type="analysis",
        status=JobStatus.RUNNING,
        target_id=analysis.id,
        attempts=attempts,
        max_attempts=3,
        started_at=datetime.now(UTC) - age,
    )
    db.add(job)
    db.commit()
    return job, analysis


def test_an_interrupted_analysis_is_returned_to_the_queue(db: Session):
    job, _ = abandoned_job(db, age=STALE_AFTER + timedelta(minutes=5))

    assert requeue_stale_jobs() == 1

    db.expire_all()
    refreshed = db.get(Job, job.id)
    assert refreshed.status is JobStatus.RETRYING
    # The reason is recorded, so the admin console shows a restart rather than a mystery.
    assert "restart" in (refreshed.last_error or "").lower()


def test_a_job_that_just_started_is_left_alone(db: Session):
    job, _ = abandoned_job(db, age=timedelta(seconds=30))

    requeue_stale_jobs()

    db.expire_all()
    # Requeueing live work would run the same analysis twice and bill for it twice.
    assert db.get(Job, job.id).status is JobStatus.RUNNING


def test_a_job_out_of_retries_fails_the_analysis_instead_of_looping(db: Session):
    job, analysis = abandoned_job(db, age=STALE_AFTER + timedelta(minutes=5), attempts=3)

    requeue_stale_jobs()

    db.expire_all()
    assert db.get(Job, job.id).status is JobStatus.FAILED

    # The reader is told plainly, and told what to do about it, rather than watching a
    # spinner that will never resolve.
    recovered = db.get(Analysis, analysis.id)
    assert recovered.status is AnalysisStatus.FAILED
    assert "again" in (recovered.error_message or "").lower()


def test_the_sweep_is_safe_to_run_when_there_is_nothing_to_do(db: Session):
    # It runs on every API cold start, so the empty case is the common one.
    assert requeue_stale_jobs() >= 0
