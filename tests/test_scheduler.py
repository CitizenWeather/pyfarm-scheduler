"""Tests for pyfarm-scheduler core components."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyfarm.scheduler.jobs.base import Job
from pyfarm.scheduler.jobs.snapshot import SnapshotBackupJob
from pyfarm.scheduler.models import JobResult, JobStatus, SchedulerStatus
from pyfarm.scheduler.scheduler import Scheduler, create_default_scheduler


# ---------------------------------------------------------------------------
# Mock storage backend
# ---------------------------------------------------------------------------


class MockStorage:
    """Minimal mock that satisfies the StorageBackend protocol."""

    def __init__(self, snapshot: dict | None = None) -> None:
        self._snapshot = snapshot
        self.events: list[dict] = []

    async def get_latest_snapshot(self, grow_id: str) -> dict | None:
        return self._snapshot

    async def insert_event(
        self,
        event_type: str,
        event_kind: str,
        message: str,
        timestamp: datetime,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            {
                "event_type": event_type,
                "event_kind": event_kind,
                "message": message,
                "timestamp": timestamp,
                "data": data or {},
            }
        )

    # Stub remaining protocol methods so isinstance checks pass.
    async def insert_sensor_reading(self, *args, **kwargs) -> None:
        pass

    async def insert_actuator_state(self, *args, **kwargs) -> None:
        pass

    async def save_snapshot(self, *args, **kwargs) -> None:
        pass

    async def get_readings(self, *args, **kwargs) -> list:
        return []

    async def get_events(self, *args, **kwargs) -> list:
        return []

    async def query_timeseries(self, *args, **kwargs) -> list:
        return []

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# SnapshotBackupJob tests
# ---------------------------------------------------------------------------


class TestSnapshotBackupJob:
    """Tests for SnapshotBackupJob."""

    @pytest.mark.asyncio
    async def test_run_with_snapshot_returns_has_snapshot_true(self):
        """When a snapshot exists, run() returns has_snapshot=True."""
        storage = MockStorage(snapshot={"state": "active"})
        job = SnapshotBackupJob(storage=storage, grow_id="grow-001")

        result = await job.run()

        assert result["grow_id"] == "grow-001"
        assert result["has_snapshot"] is True

    @pytest.mark.asyncio
    async def test_run_without_snapshot_returns_has_snapshot_false(self):
        """When no snapshot exists, run() returns has_snapshot=False."""
        storage = MockStorage(snapshot=None)
        job = SnapshotBackupJob(storage=storage, grow_id="grow-002")

        result = await job.run()

        assert result["grow_id"] == "grow-002"
        assert result["has_snapshot"] is False

    @pytest.mark.asyncio
    async def test_run_logs_system_event(self):
        """run() always inserts exactly one SYSTEM event into storage."""
        storage = MockStorage(snapshot={"x": 1})
        job = SnapshotBackupJob(storage=storage, grow_id="grow-003")

        await job.run()

        assert len(storage.events) == 1
        event = storage.events[0]
        assert event["event_kind"] == "system"
        assert event["data"]["has_snapshot"] is True

    @pytest.mark.asyncio
    async def test_run_result_keys(self):
        """run() result dict always contains grow_id and has_snapshot keys."""
        storage = MockStorage()
        job = SnapshotBackupJob(storage=storage, grow_id="grow-004")

        result = await job.run()

        assert set(result.keys()) >= {"grow_id", "has_snapshot"}

    def test_job_name(self):
        """SnapshotBackupJob.name is 'snapshot_backup'."""
        storage = MockStorage()
        job = SnapshotBackupJob(storage=storage, grow_id="g")
        assert job.name == "snapshot_backup"


# ---------------------------------------------------------------------------
# Scheduler.register() tests
# ---------------------------------------------------------------------------


class DummyJob(Job):
    """Trivial job for testing scheduler registration."""

    name = "dummy"
    description = "A no-op test job."

    async def run(self) -> dict:
        return {"ok": True}


class AnotherDummyJob(Job):
    """Second trivial job."""

    name = "another_dummy"
    description = "A second no-op test job."

    async def run(self) -> dict:
        return {"ok": True}


class TestSchedulerRegister:
    """Tests for Scheduler.register()."""

    def test_register_increments_job_count(self):
        """Registering a job increments the job count reported by get_status()."""
        storage = MockStorage()
        scheduler = Scheduler(storage)

        assert scheduler.get_status().job_count == 0

        scheduler.register(DummyJob(), interval_seconds=60)
        assert scheduler.get_status().job_count == 1

        scheduler.register(AnotherDummyJob(), interval_seconds=120)
        assert scheduler.get_status().job_count == 2

    def test_register_with_cron(self):
        """Jobs can be registered with a cron expression."""
        storage = MockStorage()
        scheduler = Scheduler(storage)
        scheduler.register(DummyJob(), cron="0 1 * * *")
        assert scheduler.get_status().job_count == 1

    def test_register_raises_without_trigger(self):
        """register() raises ValueError when no trigger is specified."""
        storage = MockStorage()
        scheduler = Scheduler(storage)
        with pytest.raises(ValueError, match="cron or interval_seconds"):
            scheduler.register(DummyJob())

    def test_register_raises_with_both_triggers(self):
        """register() raises ValueError when both triggers are specified."""
        storage = MockStorage()
        scheduler = Scheduler(storage)
        with pytest.raises(ValueError, match="cannot specify both"):
            scheduler.register(DummyJob(), cron="0 * * * *", interval_seconds=60)

    def test_job_names_after_registration(self):
        """job_names property lists all registered job names."""
        storage = MockStorage()
        scheduler = Scheduler(storage)
        scheduler.register(DummyJob(), interval_seconds=10)
        scheduler.register(AnotherDummyJob(), interval_seconds=20)
        assert "dummy" in scheduler.job_names
        assert "another_dummy" in scheduler.job_names


# ---------------------------------------------------------------------------
# Scheduler.get_status() tests
# ---------------------------------------------------------------------------


class TestSchedulerGetStatus:
    """Tests for Scheduler.get_status()."""

    def test_initial_status_not_running(self):
        """A fresh scheduler is not running."""
        storage = MockStorage()
        scheduler = Scheduler(storage)
        status = scheduler.get_status()
        assert status.running is False

    def test_initial_status_no_results(self):
        """A fresh scheduler has no results."""
        storage = MockStorage()
        scheduler = Scheduler(storage)
        status = scheduler.get_status()
        assert status.results == []

    @pytest.mark.asyncio
    async def test_status_running_after_start(self):
        """get_status().running is True after start() is called."""
        storage = MockStorage()
        scheduler = Scheduler(storage)
        scheduler.register(DummyJob(), interval_seconds=3600)
        await scheduler.start()
        try:
            status = scheduler.get_status()
            assert status.running is True
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_status_not_running_after_stop(self):
        """get_status().running is False after stop() is called."""
        storage = MockStorage()
        scheduler = Scheduler(storage)
        scheduler.register(DummyJob(), interval_seconds=3600)
        await scheduler.start()
        await scheduler.stop()
        status = scheduler.get_status()
        assert status.running is False

    @pytest.mark.asyncio
    async def test_results_populated_after_manual_run(self):
        """Results list grows after run_job_by_name()."""
        storage = MockStorage()
        scheduler = Scheduler(storage)
        scheduler.register(DummyJob(), interval_seconds=3600)

        result = await scheduler.run_job_by_name("dummy")

        assert isinstance(result, JobResult)
        assert result.status == JobStatus.SUCCESS
        status = scheduler.get_status()
        assert len(status.results) == 1

    @pytest.mark.asyncio
    async def test_failed_job_captured_in_results(self):
        """A job that raises an exception produces a FAILED JobResult."""

        class BrokenJob(Job):
            name = "broken"
            description = "Always fails."

            async def run(self) -> dict:
                raise RuntimeError("Something went wrong")

        storage = MockStorage()
        scheduler = Scheduler(storage)
        scheduler.register(BrokenJob(), interval_seconds=3600)

        result = await scheduler.run_job_by_name("broken")

        assert result.status == JobStatus.FAILED
        assert "RuntimeError" in result.error  # type: ignore[operator]

    @pytest.mark.asyncio
    async def test_run_unknown_job_raises_key_error(self):
        """run_job_by_name() raises KeyError for an unregistered name."""
        storage = MockStorage()
        scheduler = Scheduler(storage)
        with pytest.raises(KeyError, match="not_registered"):
            await scheduler.run_job_by_name("not_registered")


# ---------------------------------------------------------------------------
# create_default_scheduler factory tests
# ---------------------------------------------------------------------------


class TestCreateDefaultScheduler:
    """Tests for the create_default_scheduler() factory."""

    def test_factory_returns_scheduler(self):
        """create_default_scheduler returns a Scheduler instance."""
        storage = MockStorage()
        scheduler = create_default_scheduler(storage, grow_id="grow-x")
        assert isinstance(scheduler, Scheduler)

    def test_factory_registers_two_default_jobs(self):
        """Default scheduler has exactly two pre-registered jobs."""
        storage = MockStorage()
        scheduler = create_default_scheduler(storage)
        assert scheduler.get_status().job_count == 2

    def test_factory_includes_expected_job_names(self):
        """Default jobs are daily_analytics and snapshot_backup."""
        storage = MockStorage()
        scheduler = create_default_scheduler(storage)
        names = scheduler.job_names
        assert "daily_analytics" in names
        assert "snapshot_backup" in names
