"""pyfarm-scheduler: Async job orchestration engine for the pyfarm platform.

Runs periodic and event-triggered jobs including daily analytics and snapshot
watchdog checks.

Quick start::

    from pyfarm.scheduler import Scheduler, create_default_scheduler

    storage = get_backend()
    scheduler = create_default_scheduler(storage, grow_id="grow-001")
    await scheduler.start()
    status = scheduler.get_status()
    await scheduler.stop()
"""

from pyfarm.scheduler.models import (
    JobDefinition,
    JobResult,
    JobStatus,
    SchedulerStatus,
)
from pyfarm.scheduler.jobs.base import Job
from pyfarm.scheduler.scheduler import Scheduler, create_default_scheduler

__version__ = "0.1.0"

__all__ = [
    # Core classes
    "Scheduler",
    "Job",
    "create_default_scheduler",
    # Models
    "JobStatus",
    "JobResult",
    "JobDefinition",
    "SchedulerStatus",
]
