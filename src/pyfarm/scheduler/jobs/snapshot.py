"""Snapshot backup watchdog job for pyfarm-scheduler."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pyfarm.core.models import ControlEvent, EventKind
from pyfarm.core.storage import StorageBackend
from pyfarm.scheduler.jobs.base import Job

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SnapshotBackupJob(Job):
    """Watchdog job that verifies the control engine is persisting snapshots.

    Fetches the latest control context snapshot from storage and logs a SYSTEM
    event to confirm it exists. Useful for alerting if the control engine has
    stopped writing state.

    Args:
        storage: A ``StorageBackend``-compatible instance.
        grow_id: Identifier for the active grow session.
    """

    name = "snapshot_backup"
    description = (
        "Confirms that a control context snapshot exists in storage (watchdog)."
    )

    def __init__(self, storage: "StorageBackend", grow_id: str) -> None:
        self._storage = storage
        self._grow_id = grow_id

    async def run(self) -> dict:
        """Check for a recent snapshot and log a SYSTEM event.

        Returns:
            Dict with ``grow_id`` and ``has_snapshot`` boolean.
        """
        snapshot = await self._storage.get_latest_snapshot(self._grow_id)
        has_snapshot = snapshot is not None

        message = (
            f"Snapshot exists for grow={self._grow_id}"
            if has_snapshot
            else f"WARNING: no snapshot found for grow={self._grow_id}"
        )
        logger.warning(message) if not has_snapshot else logger.info(message)

        event = ControlEvent(
            kind=EventKind.SYSTEM,
            message=message,
            data={"grow_id": self._grow_id, "has_snapshot": has_snapshot},
        )
        await self._storage.insert_event(
            event_type="watchdog",
            event_kind=event.kind.value,
            message=event.message,
            timestamp=event.timestamp,
            data=event.data,
        )

        return {"grow_id": self._grow_id, "has_snapshot": has_snapshot}
