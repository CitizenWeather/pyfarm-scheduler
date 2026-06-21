"""Core Scheduler class for pyfarm-scheduler."""

from __future__ import annotations

import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from pyfarm.scheduler.models import JobResult, JobStatus, SchedulerStatus

if TYPE_CHECKING:
    from pyfarm.scheduler.jobs.base import Job
    from pyfarm.core.storage import StorageBackend

logger = logging.getLogger(__name__)

_MAX_RESULTS = 100


class Scheduler:
    """Async job orchestration engine backed by APScheduler 3.x.

    Wraps ``AsyncIOScheduler`` to provide job registration, result tracking,
    and a simple status API consumed by the internal FastAPI app.

    Args:
        storage: A ``StorageBackend``-compatible instance (passed to jobs).

    Example::

        scheduler = Scheduler(storage)
        scheduler.register(MyJob(), interval_seconds=60)
        await scheduler.start()
        status = scheduler.get_status()
        await scheduler.stop()
    """

    def __init__(self, storage: "StorageBackend") -> None:
        self._storage = storage
        self._aps = AsyncIOScheduler()
        self._jobs: list["Job"] = []
        self._results: deque[JobResult] = deque(maxlen=_MAX_RESULTS)
        self._running = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        job: "Job",
        cron: str | None = None,
        interval_seconds: int | None = None,
    ) -> None:
        """Register a job with the scheduler.

        Exactly one of ``cron`` or ``interval_seconds`` must be provided.

        Args:
            job:              An instance of a ``Job`` subclass.
            cron:             Cron expression string (e.g. ``"0 1 * * *"``).
            interval_seconds: Interval in seconds between executions.

        Raises:
            ValueError: If neither or both of ``cron``/``interval_seconds``
                        are supplied.
        """
        if cron is None and interval_seconds is None:
            raise ValueError(
                f"Job '{job.name}' must specify cron or interval_seconds."
            )
        if cron is not None and interval_seconds is not None:
            raise ValueError(
                f"Job '{job.name}' cannot specify both cron and interval_seconds."
            )

        if cron is not None:
            trigger = CronTrigger.from_crontab(cron)
        else:
            trigger = IntervalTrigger(seconds=interval_seconds)  # type: ignore[arg-type]

        self._aps.add_job(
            self._run_job,
            trigger=trigger,
            args=[job],
            id=job.name,
            name=job.name,
            replace_existing=True,
        )
        self._jobs.append(job)
        logger.info(
            "Registered job '%s' (cron=%s, interval=%s)",
            job.name,
            cron,
            interval_seconds,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the underlying APScheduler AsyncIOScheduler."""
        if not self._running:
            self._aps.start()
            self._running = True
            logger.info("Scheduler started with %d job(s).", len(self._jobs))

    async def stop(self) -> None:
        """Gracefully stop the scheduler."""
        if self._running:
            self._aps.shutdown(wait=False)
            self._running = False
            logger.info("Scheduler stopped.")

    # ------------------------------------------------------------------
    # Job execution wrapper
    # ------------------------------------------------------------------

    async def _run_job(self, job: "Job") -> JobResult:
        """Execute a job, capture its result, and append to result history."""
        job_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        logger.info("Running job '%s' (id=%s)", job.name, job_id)

        try:
            data = await job.run()
            finished_at = datetime.now(timezone.utc)
            result = JobResult(
                job_id=job_id,
                name=job.name,
                status=JobStatus.SUCCESS,
                started_at=started_at,
                finished_at=finished_at,
                data=data,
            )
            logger.info(
                "Job '%s' succeeded in %.2fs",
                job.name,
                (finished_at - started_at).total_seconds(),
            )
        except Exception as exc:  # noqa: BLE001
            finished_at = datetime.now(timezone.utc)
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.exception("Job '%s' failed: %s", job.name, error_msg)
            result = JobResult(
                job_id=job_id,
                name=job.name,
                status=JobStatus.FAILED,
                started_at=started_at,
                finished_at=finished_at,
                error=error_msg,
            )

        self._results.appendleft(result)
        return result

    # ------------------------------------------------------------------
    # Status / results
    # ------------------------------------------------------------------

    def get_status(self) -> SchedulerStatus:
        """Return the current scheduler status.

        Returns:
            ``SchedulerStatus`` with running flag, job count, and recent
            results (newest first, up to 100).
        """
        return SchedulerStatus(
            running=self._running,
            job_count=len(self._jobs),
            results=list(self._results),
        )

    def get_results(self, limit: int = 20) -> list[JobResult]:
        """Return the most recent job results.

        Args:
            limit: Maximum number of results to return (default 20).

        Returns:
            List of ``JobResult`` ordered newest-first.
        """
        return list(self._results)[:limit]

    async def run_job_by_name(self, name: str) -> JobResult:
        """Trigger a registered job immediately by name.

        Args:
            name: The ``job.name`` to run.

        Returns:
            ``JobResult`` from the execution.

        Raises:
            KeyError: If no job with that name is registered.
        """
        for job in self._jobs:
            if job.name == name:
                return await self._run_job(job)
        raise KeyError(f"No job registered with name '{name}'.")

    @property
    def job_names(self) -> list[str]:
        """Return a list of registered job names."""
        return [j.name for j in self._jobs]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_default_scheduler(
    storage: "StorageBackend",
    grow_id: str = "default",
) -> Scheduler:
    """Create a ``Scheduler`` pre-loaded with the default pyfarm jobs.

    Default jobs:
    - ``DailyAnalyticsJob``  — cron ``"0 1 * * *"`` (1 am UTC daily)
    - ``SnapshotBackupJob``  — every 300 seconds

    Args:
        storage: A ``StorageBackend``-compatible instance.
        grow_id: Grow session identifier passed to jobs (default ``"default"``).

    Returns:
        A configured ``Scheduler`` instance (not yet started).
    """
    # Local imports to avoid pulling in heavy analytics/storage chains at
    # module import time — these deps may not be available in all environments.
    from pyfarm.scheduler.jobs.analytics import DailyAnalyticsJob
    from pyfarm.scheduler.jobs.snapshot import SnapshotBackupJob

    scheduler = Scheduler(storage)
    scheduler.register(
        DailyAnalyticsJob(storage, grow_id),
        cron="0 1 * * *",
    )
    scheduler.register(
        SnapshotBackupJob(storage, grow_id),
        interval_seconds=300,
    )
    return scheduler
