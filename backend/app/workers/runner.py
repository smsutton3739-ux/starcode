"""Standalone background job runner.

    python -m app.workers.runner

The web process runs jobs on a worker thread, which is right for development and small
deployments. Running this as a separate process (or several) moves that work off the
request path and lets analysis capacity scale independently of HTTP capacity.

Jobs live in the database, so the two approaches interoperate: whichever process claims
a row runs it, and a job interrupted by a restart is picked up again rather than lost.
"""

from __future__ import annotations

import signal
import threading
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.models.analysis import Analysis, AnalysisStatus
from app.db.models.ops import Job, JobStatus
from app.db.session import session_scope
from app.services.analysis_service import execute_job

logger = get_logger(__name__)

#: An analysis running longer than this has almost certainly lost its worker to a
#: restart or a crash. Its job is returned to the queue rather than left hanging.
STALE_AFTER = timedelta(minutes=30)

_running = True


def _stop(signum: int, _frame) -> None:
    """Finish the job in hand, then exit — never abandon work mid-analysis."""
    global _running
    logger.info("worker.shutdown_requested", signal=signum)
    _running = False


def claim_next_job() -> str | None:
    """Atomically take the next pending job.

    The UPDATE ... WHERE status = 'pending' is the lock: two workers racing for the same
    row means exactly one reports a rowcount of 1, so a job is never run twice.
    """
    with session_scope() as db:
        candidate = db.execute(
            select(Job)
            .where(
                Job.status.in_([JobStatus.PENDING, JobStatus.RETRYING]),
                Job.attempts < Job.max_attempts,
            )
            .order_by(Job.priority, Job.created_at)
            .limit(1)
        ).scalar_one_or_none()

        if candidate is None:
            return None

        claimed = db.execute(
            update(Job)
            .where(Job.id == candidate.id, Job.status == candidate.status)
            .values(status=JobStatus.RUNNING, started_at=datetime.now(UTC))
        )
        if claimed.rowcount != 1:
            return None  # another worker took it

        # execute_job re-reads the row and expects to move it out of RUNNING itself.
        db.execute(update(Job).where(Job.id == candidate.id).values(status=JobStatus.PENDING))
        return candidate.id


def requeue_stale_jobs() -> int:
    """Return jobs abandoned by a dead worker to the queue."""
    cutoff = datetime.now(UTC) - STALE_AFTER
    with session_scope() as db:
        stale = (
            db.execute(select(Job).where(Job.status == JobStatus.RUNNING, Job.started_at < cutoff))
            .scalars()
            .all()
        )

        for job in stale:
            if job.attempts < job.max_attempts:
                job.status = JobStatus.RETRYING
                job.last_error = (
                    "The worker running this job stopped without finishing it — most "
                    "likely a restart. Requeued."
                )
                logger.warning("worker.requeued_stale", job_id=job.id, attempts=job.attempts)
            else:
                job.status = JobStatus.FAILED
                job.last_error = "Abandoned by a worker and out of retries."
                analysis = db.get(Analysis, job.target_id) if job.target_id else None
                if analysis is not None and analysis.status == AnalysisStatus.RUNNING:
                    analysis.status = AnalysisStatus.FAILED
                    analysis.error_message = (
                        "This analysis was interrupted and could not be recovered. "
                        "Submitting it again usually works."
                    )
        return len(stale)


def start_sweeper_thread() -> threading.Thread:
    """Sweep for abandoned jobs from inside a process that is not the standalone worker.

    The API already runs each analysis on a thread, so a single-process deployment needs
    no worker service — but it does still need somebody to notice work that a killed
    process left behind. Free hosting tiers stop idle instances routinely, so this is the
    normal case there rather than a disaster case.

    A daemon thread, so it never delays shutdown, and every failure is swallowed: a
    sweep that cannot reach the database must not take the API down with it.
    """

    def loop() -> None:
        while True:
            time.sleep(settings.JOB_SWEEP_INTERVAL_SECONDS)
            try:
                requeued = requeue_stale_jobs()
                if requeued:
                    logger.info("worker.stale_sweep", requeued=requeued, source="api")
            except Exception as exc:  # noqa: BLE001
                # Name the database, credentials stripped. A bare "connection refused"
                # cannot distinguish a wrong host from an unreachable one, which is the
                # only question worth asking when a fallback default might be in play.
                logger.warning(
                    "worker.sweep_failed", error=str(exc), database=settings.database_target
                )

    thread = threading.Thread(target=loop, daemon=True, name="job-sweeper")
    thread.start()
    return thread


def main() -> int:
    configure_logging()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    logger.info("worker.started", poll_interval=settings.JOB_POLL_INTERVAL_SECONDS)

    idle_cycles = 0
    while _running:
        try:
            # Sweep for abandoned work occasionally, not on every pass.
            if idle_cycles % 120 == 0:
                requeued = requeue_stale_jobs()
                if requeued:
                    logger.info("worker.stale_sweep", requeued=requeued)

            job_id = claim_next_job()
            if job_id is None:
                idle_cycles += 1
                time.sleep(settings.JOB_POLL_INTERVAL_SECONDS)
                continue

            idle_cycles = 0
            logger.info("worker.job_started", job_id=job_id)
            execute_job(job_id)
            logger.info("worker.job_finished", job_id=job_id)

        except Exception as exc:  # noqa: BLE001
            # A failure handling one job must not take the worker down.
            logger.exception("worker.loop_error", error=str(exc))
            time.sleep(2)

    logger.info("worker.stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
