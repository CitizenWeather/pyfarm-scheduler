"""FastAPI application for the pyfarm-scheduler internal API.

This is an **internal-only** service, not publicly exposed. All endpoints
require the ``X-Internal-Token`` header matching the ``SCHEDULER_INTERNAL_TOKEN``
environment variable.

Endpoints:
    GET  /health                              Liveness probe.
    GET  /api/v1/scheduler/status             Full scheduler status.
    GET  /api/v1/scheduler/jobs               List of registered job names.
    POST /api/v1/scheduler/jobs/{name}/run    Trigger a job immediately.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status

from pyfarm.config import get_settings
from pyfarm.scheduler.models import JobResult, SchedulerStatus
from pyfarm.scheduler.scheduler import Scheduler

app = FastAPI(
    title="pyfarm-scheduler",
    description="Internal async job orchestration engine for the pyfarm platform.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)

# ---------------------------------------------------------------------------
# Global scheduler instance — injected at startup by the process entrypoint.
# ---------------------------------------------------------------------------
_scheduler: Scheduler | None = None


def set_scheduler(scheduler: Scheduler) -> None:
    """Inject the global ``Scheduler`` instance (called from entrypoint)."""
    global _scheduler  # noqa: PLW0603
    _scheduler = scheduler


def get_scheduler() -> Scheduler:
    """FastAPI dependency: retrieve the global scheduler or raise 503."""
    if _scheduler is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler not initialised.",
        )
    return _scheduler


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def verify_token(x_internal_token: str = Header(...)) -> None:
    """Verify the shared-secret internal token from the request header.

    Raises:
        HTTPException 401: Token missing or does not match configured token.
    """
    settings = get_settings()
    expected = settings.scheduler_internal_token.get_secret_value()
    if x_internal_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal token.",
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["internal"])
async def health() -> dict[str, str]:
    """Liveness probe — no auth required."""
    return {"status": "ok"}


@app.get(
    "/api/v1/scheduler/status",
    response_model=SchedulerStatus,
    tags=["scheduler"],
    dependencies=[Depends(verify_token)],
)
async def get_status(
    scheduler: Scheduler = Depends(get_scheduler),
) -> SchedulerStatus:
    """Return the current scheduler status including recent job results."""
    return scheduler.get_status()


@app.get(
    "/api/v1/scheduler/jobs",
    response_model=list[str],
    tags=["scheduler"],
    dependencies=[Depends(verify_token)],
)
async def list_jobs(
    scheduler: Scheduler = Depends(get_scheduler),
) -> list[str]:
    """Return a list of registered job names."""
    return scheduler.job_names


@app.post(
    "/api/v1/scheduler/jobs/{name}/run",
    response_model=JobResult,
    tags=["scheduler"],
    dependencies=[Depends(verify_token)],
)
async def run_job(
    name: str,
    scheduler: Scheduler = Depends(get_scheduler),
) -> JobResult:
    """Trigger a registered job immediately and return its result.

    Args:
        name: The job name as registered with the scheduler.

    Raises:
        404: If no job with the given name is registered.
    """
    try:
        return await scheduler.run_job_by_name(name)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No job registered with name '{name}'.",
        )
