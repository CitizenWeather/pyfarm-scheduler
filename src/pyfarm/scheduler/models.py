"""Pydantic models for the pyfarm-scheduler package."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Status of a scheduled job execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobResult(BaseModel):
    """Result record for a single job execution."""

    job_id: str
    name: str
    status: JobStatus
    started_at: datetime
    finished_at: datetime
    error: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)


class JobDefinition(BaseModel):
    """Static definition of a scheduled job."""

    name: str
    description: str
    schedule_cron: Optional[str] = None
    interval_seconds: Optional[int] = None
    enabled: bool = True


class SchedulerStatus(BaseModel):
    """Current runtime status of the scheduler."""

    running: bool
    job_count: int
    results: list[JobResult] = Field(default_factory=list)
