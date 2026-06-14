"""
ETL Administration Router - Schedule monitoring and control.

Provides endpoints for:
- Viewing current ETL schedule
- Checking which sources should run
- Getting schedule efficiency metrics
- Manually triggering ETL runs (future)
"""

# Import smart scheduler
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

# Add parent and etl directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "etl"))

try:
    from etl.smart_scheduler import SmartScheduler
except Exception as e:
    # Fallback if smart scheduler unavailable
    class SmartScheduler:  # type: ignore
        def should_run(self, source):
            return (True, "Fallback: always run")

        def generate_schedule_report(self):
            return {}

        def get_schedule_summary(self):
            return {
                "timestamp": datetime.now().isoformat(),
                "sources_to_run_today": [],
                "sources_not_running_today": [],
                "efficiency": {
                    "running": 0,
                    "skipping": 0,
                    "total_sources": 0,
                    "skip_percentage": 0,
                },
            }


from supabase_auth import AdminUser, require_admin

router = APIRouter(
    prefix="/api/v1/admin/etl",
    tags=["ETL Administration"],
    dependencies=[Depends(require_admin)],
)


# Response models
class ScheduleDecision(BaseModel):
    """Decision about whether a source should run."""

    source: str
    should_run: bool
    reason: str
    next_run: str | None = None
    next_reason: str | None = None
    current_period: str


class ScheduleSummary(BaseModel):
    """High-level summary of scheduling efficiency."""

    timestamp: str
    sources_running_today: int
    sources_skipping_today: int
    total_sources: int
    skip_percentage: float
    efficiency_vs_fixed_schedule: str


class ScheduleReport(BaseModel):
    """Complete schedule report for all sources."""

    timestamp: str
    sources: Dict[str, ScheduleDecision]
    summary: ScheduleSummary


@router.get("/schedule", response_model=Dict, summary="Get ETL Schedule")
async def get_etl_schedule():
    """
    Get complete ETL schedule for all sources.

    Returns detailed information about:
    - Which sources should run today
    - Reasons for running/skipping
    - Next scheduled run times
    - Current scheduling period (budget season, audit season, etc.)
    - Efficiency metrics vs fixed 720-minute schedule

    This endpoint is useful for:
    - Monitoring ETL health
    - Understanding why sources are/aren't running
    - Debugging scheduling logic
    - Dashboard displays
    """
    scheduler = SmartScheduler()

    # Get complete schedule report
    report = scheduler.generate_schedule_report()

    # Get summary
    summary = scheduler.get_schedule_summary()

    # Calculate efficiency vs old fixed schedule
    # Old schedule: all 3 sources every 12 hours = 6 runs/day
    # New schedule: varies by calendar, target ~2 runs/day average = 67% reduction
    sources_running = summary["efficiency"]["running"]
    total_sources = summary["efficiency"]["total_sources"]

    if total_sources > 0:
        old_daily_runs = total_sources * 2  # 2x per day for all sources
        new_daily_runs = sources_running
        reduction = ((old_daily_runs - new_daily_runs) / old_daily_runs) * 100
        efficiency_msg = f"{reduction:.0f}% fewer runs than fixed schedule"
    else:
        efficiency_msg = "No sources configured"

    return {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "sources_running_today": sources_running,
            "sources_skipping_today": summary["efficiency"]["skipping"],
            "total_sources": total_sources,
            "skip_percentage": summary["efficiency"]["skip_percentage"],
            "efficiency_vs_fixed_schedule": efficiency_msg,
            "sources_to_run": [
                {"source": item["source"], "reason": item["reason"]}
                for item in summary["sources_to_run_today"]
            ],
            "sources_not_running": summary["sources_not_running_today"],
        },
        "sources": report,
    }


@router.get(
    "/schedule/summary", response_model=Dict, summary="Get Schedule Summary (Quick)"
)
async def get_schedule_summary():
    """
    Get quick summary of today's ETL schedule.

    Returns high-level metrics:
    - Number of sources running today
    - Number of sources being skipped
    - Efficiency percentage
    - List of sources to run with reasons

    This is a lightweight endpoint for dashboard widgets.
    Use /schedule for full details.
    """
    scheduler = SmartScheduler()
    summary = scheduler.get_schedule_summary()

    sources_running = summary["efficiency"]["running"]
    total_sources = summary["efficiency"]["total_sources"]

    if total_sources > 0:
        old_daily_runs = total_sources * 2
        new_daily_runs = sources_running
        reduction = ((old_daily_runs - new_daily_runs) / old_daily_runs) * 100
        efficiency_msg = f"{reduction:.0f}% reduction"
    else:
        efficiency_msg = "No sources"

    return {
        "timestamp": summary["timestamp"],
        "running_today": sources_running,
        "skipping_today": summary["efficiency"]["skipping"],
        "total_sources": total_sources,
        "efficiency": {
            "skip_percentage": summary["efficiency"]["skip_percentage"],
            "vs_fixed_schedule": efficiency_msg,
        },
        "sources_to_run": summary["sources_to_run_today"],
    }


@router.get(
    "/schedule/source/{source}", response_model=Dict, summary="Get Source Schedule"
)
async def get_source_schedule(source: str):
    """
    Get schedule information for a specific source.

    Args:
        source: Source key (treasury, cob, oag, knbs, opendata, cra)

    Returns:
        Detailed schedule information for the source including:
        - Should it run now?
        - Why/why not?
        - When is next run?
        - What period is it in? (budget season, audit season, etc.)
    """
    valid_sources = ["treasury", "cob", "oag", "knbs", "opendata", "cra"]
    if source not in valid_sources:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown source '{source}'. Valid sources: {', '.join(valid_sources)}",
        )

    scheduler = SmartScheduler()

    # Get decision for this source
    should_run, reason = scheduler.should_run(source)
    next_run, next_reason = scheduler.get_next_run(source)

    # Get full report to extract current period
    report = scheduler.generate_schedule_report()
    source_info = report.get(source, {})

    return {
        "source": source,
        "timestamp": datetime.now().isoformat(),
        "should_run_now": should_run,
        "reason": reason,
        "next_run": next_run.isoformat() if next_run else None,
        "next_reason": next_reason,
        "current_period": source_info.get("current_period", "unknown"),
        "schedule_config": source_info.get("schedule_config", {}),
    }


@router.get("/health", response_model=Dict, summary="ETL System Health")
async def get_etl_health():
    """
    Get overall ETL system health status.

    Returns:
        Health metrics including:
        - Scheduler status
        - Last run times (future)
        - Error counts (future)
        - Data freshness (future)
    """
    scheduler = SmartScheduler()

    # Check scheduler is working
    try:
        summary = scheduler.get_schedule_summary()
        scheduler_status = "healthy"
    except Exception as e:
        scheduler_status = f"error: {str(e)}"
        summary = None

    return {
        "timestamp": datetime.now().isoformat(),
        "scheduler_status": scheduler_status,
        "schedule_summary": summary if summary else None,
        "note": "Extended health metrics (last runs, errors, freshness) coming in Week 5",
    }


VALID_SOURCES = ["treasury", "cob", "oag", "knbs", "opendata", "cra"]


class TriggerBody(BaseModel):
    """Body for the manual-trigger endpoint."""

    dry_run: bool = False


# Module-level lazy import wrapper for ``get_db`` so we can use it as a
# FastAPI dependency without paying its heavy import cost at router
# import time. The first request resolves it, subsequent requests reuse
# the cached reference. Returning the generator directly is fine —
# FastAPI knows how to iterate it and call ``close()`` on the dependency.
_get_db_dep = None


def _db_dep():
    global _get_db_dep
    if _get_db_dep is None:
        from database import get_db as _gd

        _get_db_dep = _gd
    yield from _get_db_dep()


@router.post("/trigger/{source}", response_model=Dict, summary="Manually trigger ETL run")
async def trigger_etl_run(
    source: str,
    body: TriggerBody | None = None,
    actor: AdminUser = Depends(require_admin),
    db: Session = Depends(_db_dep),
):
    """
    Queue a manual ETL run for ``source``.

    This writes an ``ingestion_jobs`` row with ``status=PENDING`` and
    ``metadata.manual_trigger=true``. The existing scheduler/seeder
    process is what actually picks up pending jobs and runs them —
    we don't shell out to the pipeline here, both because it would
    block the request for minutes and because the ETL machinery
    already lives in a long-running worker that owns the per-source
    locks. The returned ``job_id`` lets the operator follow the run
    on /admin/ingestion.

    Records an entry in ``admin_audit_log`` so the trigger is
    attributable.
    """
    # Local imports for the model/util side — kept local to keep router
    # import time light. The DB session itself comes via the FastAPI
    # ``Depends(_db_dep)`` above so its lifecycle (commit / rollback /
    # close) is owned by the framework, not this handler.
    from models import IngestionJob, IngestionStatus
    from utils.audit import record_admin_action

    if source not in VALID_SOURCES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown source '{source}'. Valid sources: {', '.join(VALID_SOURCES)}",
        )

    payload = body or TriggerBody()
    job = IngestionJob(
        domain=source,
        status=IngestionStatus.PENDING,
        dry_run=payload.dry_run,
        meta={
            "manual_trigger": True,
            "requested_by": actor.id,
            "requested_by_email": actor.email,
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    record_admin_action(
        db,
        actor=actor,
        action="etl.trigger",
        target_type="etl_source",
        target_id=source,
        payload={"job_id": job.id, "dry_run": payload.dry_run},
    )

    return {
        "ok": True,
        "job_id": job.id,
        "source": source,
        "status": job.status.value,
        "dry_run": job.dry_run,
        "note": "Job queued. The seeder picks up pending jobs on its next cycle.",
    }
