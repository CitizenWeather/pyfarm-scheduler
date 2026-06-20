"""Job implementations for pyfarm-scheduler.

Imports are lazy to avoid pulling in heavy optional dependencies (analytics,
storage) when only the base class is needed (e.g. in tests with mocked deps).
"""

from pyfarm.scheduler.jobs.base import Job


def __getattr__(name: str):
    if name == "DailyAnalyticsJob":
        from pyfarm.scheduler.jobs.analytics import DailyAnalyticsJob
        return DailyAnalyticsJob
    if name == "SnapshotBackupJob":
        from pyfarm.scheduler.jobs.snapshot import SnapshotBackupJob
        return SnapshotBackupJob
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Job",
    "DailyAnalyticsJob",
    "SnapshotBackupJob",
]
