"""Abstract base class for all pyfarm scheduler jobs."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Job(ABC):
    """Abstract base class for all scheduled jobs.

    Subclasses must define ``name``, ``description``, and implement ``run()``.

    Example::

        class MyJob(Job):
            name = "my_job"
            description = "Does something useful."

            async def run(self) -> dict:
                return {"result": "ok"}
    """

    #: Unique machine-friendly identifier for this job.
    name: str

    #: Human-readable description shown in status/logs.
    description: str

    @abstractmethod
    async def run(self) -> dict:
        """Execute the job and return a result data dictionary.

        Returns:
            A plain dict that will be stored in ``JobResult.data``.

        Raises:
            Exception: Any exception is caught by the scheduler and recorded
                       as a FAILED ``JobResult``.
        """
        ...
