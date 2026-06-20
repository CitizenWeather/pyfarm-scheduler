"""Daily analytics job for pyfarm-scheduler."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from pyfarm.analytics import Analyzer
from pyfarm.core.models import ControlEvent, EventKind
from pyfarm.core.storage import StorageBackend
from pyfarm.scheduler.jobs.base import Job

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class DailyAnalyticsJob(Job):
    """Runs the full KPI dashboard for yesterday and stores a summary event.

    Computes environment summaries, nutrient drift, and anomaly detection for
    the previous calendar day. Writes a SYSTEM event to storage summarising
    the key numbers so the audit trail is self-contained.

    Args:
        storage: A ``StorageBackend``-compatible instance.
        grow_id: Identifier for the active grow session.
    """

    name = "daily_analytics"
    description = "Computes the daily KPI dashboard and persists a summary event."

    def __init__(self, storage: "StorageBackend", grow_id: str) -> None:
        self._storage = storage
        self._grow_id = grow_id

    async def run(self) -> dict:
        """Execute the daily analytics computation.

        Returns:
            Summary dict with grow_id, date, anomaly count, drift count, and
            mean environment metrics.
        """
        now = datetime.now(timezone.utc)
        # Yesterday's date range (midnight-to-midnight UTC)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
        date_label = start.date().isoformat()

        logger.info(
            "DailyAnalyticsJob: computing dashboard for grow=%s date=%s",
            self._grow_id,
            date_label,
        )

        analyzer = Analyzer(self._storage)
        dashboard = await analyzer.dashboard(self._grow_id, start, end)

        env = dashboard.environment_summary
        summary: dict = {
            "grow_id": self._grow_id,
            "date": date_label,
            "anomaly_count": len(dashboard.anomalies),
            "nutrient_drift_count": len(dashboard.nutrient_drifts),
            "flagged_drifts": sum(
                1 for d in dashboard.nutrient_drifts if d.flagged
            ),
        }
        if env is not None:
            summary.update(
                {
                    "mean_temp": env.mean_temp,
                    "mean_rh": env.mean_rh,
                    "mean_vpd": env.mean_vpd,
                    "mean_co2": env.mean_co2,
                    "dli": env.dli,
                }
            )

        event = ControlEvent(
            kind=EventKind.SYSTEM,
            message=f"Daily analytics complete for {date_label}",
            data=summary,
        )
        await self._storage.insert_event(
            event_type="analytics",
            event_kind=event.kind.value,
            message=event.message,
            timestamp=event.timestamp,
            data=event.data,
        )

        logger.info("DailyAnalyticsJob: summary=%s", summary)
        return summary
