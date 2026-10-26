"""Background job infrastructure.

Jobs run in daemon threads and report progress into the Job model.
Heavy engine imports happen lazily inside service functions so Django
boots fast even when OCR/AI dependencies are not installed.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback

from django.db import OperationalError
from django.utils import timezone

from .models import Job, Project

logger = logging.getLogger(__name__)

# Only one heavy job per project at a time
_project_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()

# Cancel signals keyed by job id; checked at choke points inside services.
_cancel_events: dict[str, threading.Event] = {}
_cancel_guard = threading.Lock()


def _db_write_retry(fn, *args, attempts: int = 5, base_delay: float = 0.05):
    """Retry a DB write on transient SQLite lock errors.

    Job threads write progress/logs from a worker while request threads write
    job rows from the cancel endpoint; SQLite (shared-cache in tests, file DB
    in dev) can return "table is locked" under that contention. Losing one of
    these writes used to fail the whole job, so retry with backoff.
    """
    for attempt in range(attempts):
        try:
            return fn(*args)
        except OperationalError as e:
            if "locked" not in str(e).lower() or attempt == attempts - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))


def _lock_for(project_id: str) -> threading.Lock:
    with _locks_guard:
        if project_id not in _project_locks:
            _project_locks[project_id] = threading.Lock()
        return _project_locks[project_id]


def _event_for(job_id: str) -> threading.Event:
    with _cancel_guard:
        if job_id not in _cancel_events:
            _cancel_events[job_id] = threading.Event()
        return _cancel_events[job_id]


def request_cancel(job_id: str) -> bool:
    """Signal a running job to stop. Returns False if already forgotten."""
    with _cancel_guard:
        event = _cancel_events.get(str(job_id))
    if event is None:
        return False
    event.set()
    return True


class JobCancelled(Exception):
    """Raised inside a job when the user requested cancellation."""


class JobContext:
    """Progress/logging wrapper around a Job row."""

    MAX_LOGS = 400

    def __init__(self, job: Job):
        self.job = job
        self.cancel_event = _event_for(str(job.id))

    def check_cancelled(self) -> None:
        """Raise JobCancelled if the user cancelled this job."""
        if self.cancel_event.is_set():
            raise JobCancelled("Cancelled by user")

    def log(self, message: str) -> None:
        logs = list(self.job.logs or [])
        stamp = timezone.now().strftime("%H:%M:%S")
        logs.append(f"[{stamp}] {message}")
        if len(logs) > self.MAX_LOGS:
            logs = logs[-self.MAX_LOGS:]
        self.job.logs = logs
        _db_write_retry(lambda: self.job.save(update_fields=["logs", "updated_at"]))

    def progress(self, value: float, stage: str | None = None) -> None:
        # Choke point: every progress report checks the cancel flag so a
        # cancelled job cannot be resurrected to RUNNING by late callbacks.
        self.check_cancelled()
        self.job.progress = max(0.0, min(1.0, value))
        if stage is not None:
            self.job.stage = stage
        # Conditional update: only flip the status forward while the row is
        # still PENDING/RUNNING. The cancel view may have already set the row
        # to CANCELLED between our check_cancelled() above and this save — an
        # unconditional save would resurrect the cancelled row to RUNNING and
        # brick the project behind the one-active-job guard.
        updated = _db_write_retry(lambda: Job.objects.filter(
            pk=self.job.pk,
            status__in=[Job.Status.PENDING, Job.Status.RUNNING],
        ).update(
            progress=self.job.progress,
            stage=self.job.stage,
            status=Job.Status.RUNNING,
            updated_at=timezone.now(),
        ))
        if not updated:
            self.check_cancelled()

    def succeed(self, result: dict | None = None) -> None:
        # Cancel window: if the user cancelled between the runner's last
        # check and here, the row is already terminal — leave it alone.
        refreshed = Job.objects.filter(pk=self.job.pk).first()
        if refreshed and refreshed.status in (Job.Status.CANCELLED,
                                              Job.Status.FAILED):
            self.job = refreshed
            self.check_cancelled()
        self.job.progress = 1.0
        self.job.status = Job.Status.SUCCESS
        self.job.stage = "Done"
        self.job.finished_at = timezone.now()
        if result is not None:
            self.job.result = result
        _db_write_retry(lambda: self.job.save())

    def fail(self, message: str) -> None:
        self.job.status = Job.Status.FAILED
        self.job.error_message = message
        self.job.stage = "Failed"
        self.job.finished_at = timezone.now()
        _db_write_retry(lambda: self.job.save())


def _sync_project_counters(project: Project) -> None:
    """Recompute total/translated block counters from real block rows.

    Needed whenever a job ends without its success path running (cancel,
    crash, server restart): `_do_chunk` saves translations block-by-block,
    but `_refresh_counts` only ran at the end — so a cancelled translate
    keeps translations in the DB while the stale counter shows 0 and locks
    rendering. Best-effort: never let counter sync mask a job outcome.
    """
    try:
        from .services import _refresh_counts  # lazy: services imports jobs
        _refresh_counts(project)
    except Exception:
        logger.exception("Counter sync failed for project %s", project.pk)


def _project_after_interrupt(project: Project, message: str) -> None:
    """Settle a project whose job was cancelled/interrupted.

    READY when extraction results exist (partial work stays usable),
    CREATED when nothing was ever extracted.
    """
    _sync_project_counters(project)
    Project.objects.filter(pk=project.pk).update(
        status=Project.Status.READY if project.pages.exists()
        else Project.Status.CREATED,
        error_message=message,
    )


def worker_alive(project_id: str) -> bool:
    """True while a worker thread of this process holds the project lock."""
    return _lock_for(str(project_id)).locked()


def settle_zombie(project: Project) -> bool:
    """Self-heal a zombie job: an active PENDING/RUNNING row whose owning
    process died before finalize (a dev-server autoreload/restart kills the
    worker thread mid-call). The project lock is in-process memory, so an
    active row plus a free lock proves no worker will ever finalize the row.

    Marks the row FAILED, settles the project counters/status, and returns
    True when a zombie was healed. Returns False while a live worker holds
    the lock (or the row already turned terminal) — callers keep 409s.
    """
    if worker_alive(str(project.id)):
        return False
    updated = Job.objects.filter(
        project=project,
        status__in=[Job.Status.PENDING, Job.Status.RUNNING],
    ).update(
        status=Job.Status.FAILED,
        stage="Failed",
        error_message="Job interrupted — the worker is no longer alive"
                      " (the server restarted while it was running)",
        finished_at=timezone.now(),
    )
    if not updated:
        return False
    _project_after_interrupt(
        project, "Previous job was interrupted by a server restart")
    return True


def submit_job(project: Project, kind: str, params: dict, run) -> Job:
    """Create a Job row and run `run(job)` in a background thread.

    run signature: run(ctx: JobContext) -> dict | None (result payload)
    """
    lock = _lock_for(str(project.id))
    if not lock.acquire(blocking=False):
        raise RuntimeError("Another job is already running for this project")

    job = Job.objects.create(project=project, kind=kind, params=params)
    cancel_event = _event_for(str(job.id))

    def _worker():
        ctx = JobContext(job)
        try:
            ctx.progress(0.0, "Starting")
            result = run(ctx)
            # Shrink the cancel/completion race: if cancel landed between the
            # runner's last check and here, treat the job as cancelled.
            ctx.check_cancelled()
            ctx.succeed(result or {})
        except JobCancelled:
            logger.info("Job %s cancelled", job.id)
            # The cancel view usually flips the row itself, but a cancel that
            # lands mid-progress() can be lost — finalize idempotently so the
            # row can never stay stuck in RUNNING (it would 409 the project).
            Job.objects.filter(
                pk=job.pk, status__in=[Job.Status.PENDING, Job.Status.RUNNING],
            ).update(
                status=Job.Status.CANCELLED,
                stage="Cancelled",
                error_message="Cancelled by user",
                finished_at=timezone.now(),
            )
            _project_after_interrupt(project, "Cancelled by user")
        except Exception as e:
            logger.exception("Job %s failed", job.id)
            # Counters must reflect whatever partial work reached the DB.
            _sync_project_counters(project)
            ctx.fail(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            Project.objects.filter(pk=project.pk).update(
                status=Project.Status.FAILED,
                error_message=f"{type(e).__name__}: {e}",
            )
        finally:
            with _cancel_guard:
                _cancel_events.pop(str(job.id), None)
            lock.release()
            # NOTE: _project_locks is intentionally never pruned. Pruning a
            # free lock races with a submitter that already fetched the object
            # via _lock_for() but hasn't acquired() yet — that would let two
            # jobs run concurrently on one project. The dict is bounded by the
            # number of projects ever touched this process, which is small.

    try:
        threading.Thread(target=_worker, name=f"job-{job.id}", daemon=True).start()
    except Exception:
        # The lock would otherwise stay held forever, bricking the project.
        lock.release()
        with _cancel_guard:
            _cancel_events.pop(str(job.id), None)
        job.status = Job.Status.FAILED
        job.error_message = "Failed to start worker thread"
        job.stage = "Failed"
        job.finished_at = timezone.now()
        job.save()
        raise
    return job

