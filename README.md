# pyfarm-scheduler

Async job orchestration engine for the [pyfarm](https://github.com/pyfarm) platform.
Runs periodic and event-triggered background jobs — daily analytics, snapshot watchdogs, and more — backed by [APScheduler 3.x](https://apscheduler.readthedocs.io/en/3.x/).

## Features

- `AsyncIOScheduler`-based execution (cron and interval triggers)
- Pluggable `Job` base class — add new jobs without touching the scheduler core
- In-memory result ring buffer (last 100 results, no extra DB writes)
- Thin internal FastAPI service with shared-secret auth for status and manual triggers
- First-class integration with `pyfarm-storage` and `pyfarm-analytics`

## Included jobs

| Job | Trigger | Purpose |
|-----|---------|---------|
| `DailyAnalyticsJob` | `0 1 * * *` (1 am UTC) | Runs the full KPI dashboard for the previous day and writes a summary event to storage |
| `SnapshotBackupJob` | Every 300 seconds | Watchdog — confirms the control engine has written a recent snapshot; logs a SYSTEM event |

## Installation

```bash
pip install -e ".[dev]"
# or from the monorepo root
pip install -e pyfarm-core -e pyfarm-storage -e pyfarm-analytics -e pyfarm-scheduler
```

## Quick start

```python
import asyncio
from pyfarm.storage import get_backend
from pyfarm.scheduler import create_default_scheduler

async def main():
    storage = get_backend()  # SQLite or Postgres
    scheduler = create_default_scheduler(storage, grow_id="grow-001")
    await scheduler.start()

    # Trigger a job manually
    result = await scheduler.run_job_by_name("snapshot_backup")
    print(result.status, result.data)

    await scheduler.stop()

asyncio.run(main())
```

## Writing a custom job

```python
from pyfarm.scheduler.jobs.base import Job

class HeartbeatJob(Job):
    name = "heartbeat"
    description = "Sends a heartbeat ping."

    async def run(self) -> dict:
        # ... do async work ...
        return {"pinged": True}

# Register it
scheduler.register(HeartbeatJob(), interval_seconds=30)
```

## Internal API

The FastAPI app (`pyfarm.scheduler.app`) exposes an **internal-only** HTTP interface.
All endpoints require the `X-Internal-Token` header matching the `SCHEDULER_INTERNAL_TOKEN` env var.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe (no auth) |
| `GET` | `/api/v1/scheduler/status` | Full status + recent results |
| `GET` | `/api/v1/scheduler/jobs` | List registered job names |
| `POST` | `/api/v1/scheduler/jobs/{name}/run` | Trigger a job immediately |

### Running the server

```bash
export SCHEDULER_INTERNAL_TOKEN=supersecret
uvicorn pyfarm.scheduler.app:app --host 0.0.0.0 --port 8003
```

## Running tests

```bash
pytest tests/
```

## Project structure

```
src/pyfarm/scheduler/
├── __init__.py          # Public exports
├── app.py               # FastAPI internal API
├── models.py            # Pydantic models (JobStatus, JobResult, …)
├── scheduler.py         # Scheduler class + create_default_scheduler()
└── jobs/
    ├── base.py          # Abstract Job base class
    ├── analytics.py     # DailyAnalyticsJob
    └── snapshot.py      # SnapshotBackupJob
```

## License

MIT
