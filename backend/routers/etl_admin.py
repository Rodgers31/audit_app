"""Admin calendar planning. Worker execution and freshness require separate evidence."""
import logging
import re
from importlib.util import module_from_spec, spec_from_file_location
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, StrictBool, StrictStr, ValidationError

from routers.admin_operations import OperationsRoute, PRIVATE_HEADERS
from supabase_auth import AdminUser, require_admin
from database import get_db
from sqlalchemy.orm import Session
from admin_etl_dispatch import (TriggerBody, DispatchCapability, Accepted, Command, CommandPage,
    Source, Status, capability, accept, command_detail, command_history)

# Both Docker backend-only contexts and repository imports load the same packaged
# planner without changing global package precedence (especially seeding).
try:
    _planner_spec = spec_from_file_location("admin_operations_calendar", Path(__file__).resolve().parents[1] / "etl/smart_scheduler.py")
    if _planner_spec is None or _planner_spec.loader is None:
        raise ImportError("Calendar module unavailable")
    _planner_module = module_from_spec(_planner_spec)
    _planner_spec.loader.exec_module(_planner_module)
    SmartScheduler = _planner_module.SmartScheduler
except Exception:
    SmartScheduler = None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin/etl", tags=["ETL Administration"],
    route_class=OperationsRoute,
    dependencies=[Depends(require_admin)])
VALID_SOURCES = ["treasury", "cob", "oag", "knbs", "opendata", "cra"]
MANUAL_TRIGGER = {"available": False, "reason": (
    "Calendar endpoints do not dispatch work or verify worker readiness. "
    "Use dedicated dispatch capability and command receipts for execution evidence."
)}


class PlanDecision(BaseModel):
    should_run_now: StrictBool
    reason: StrictStr
    next_run: StrictStr | None
    next_reason: StrictStr
    current_period: StrictStr
    schedule_config: dict


def _calendar_plan():
    try:
        if SmartScheduler is None:
            raise ValueError("Planner unavailable")
        raw = SmartScheduler().generate_schedule_report()
        if not isinstance(raw, dict) or set(raw) != set(VALID_SOURCES):
            raise ValueError("Unsupported planner sources")
        sources = {}
        for name, value in raw.items():
            decision = PlanDecision.model_validate(value).model_dump(exclude={"schedule_config"})
            if decision["next_run"] is not None:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?", decision["next_run"]):
                    raise ValueError("Unsupported planner timestamp")
                datetime.fromisoformat(decision["next_run"])
            # Preserve the source endpoint/planner field and match the UI contract.
            sources[name] = {**decision, "should_run": decision["should_run_now"]}
        scheduled = [{"source": name, "reason": item["reason"]} for name, item in sources.items() if item["should_run"]]
        skipped = [name for name, item in sources.items() if not item["should_run"]]
        reduction = (1 - len(scheduled) / (len(sources) * 2)) * 100
        return {"timestamp": datetime.now(timezone.utc).isoformat(), "evidence": "calendar_plan",
            "manual_trigger": dict(MANUAL_TRIGGER), "sources": sources,
            "summary": {"sources_running_today": len(scheduled), "sources_skipping_today": len(skipped),
                "total_sources": len(sources), "skip_percentage": round(len(skipped)/len(sources)*100, 1),
                "efficiency_vs_fixed_schedule": f"{reduction:.0f}% fewer planned checks than fixed schedule",
                "sources_to_run": scheduled, "sources_not_running": skipped}}
    except Exception:
        # Raw planner errors/configuration are never returned to an operator/browser.
        logger.warning("admin_calendar_plan_unavailable")
        raise HTTPException(status_code=503, detail="Calendar plan unavailable", headers=PRIVATE_HEADERS) from None


@router.get("/schedule", response_model=dict, summary="Get ETL calendar plan")
async def get_etl_schedule():
    return _calendar_plan()


@router.get("/schedule/summary", response_model=dict, summary="Get calendar plan summary")
async def get_schedule_summary():
    plan = _calendar_plan()
    summary = plan["summary"]
    return {"timestamp": plan["timestamp"], "evidence": plan["evidence"],
        "running_today": summary["sources_running_today"], "skipping_today": summary["sources_skipping_today"],
        "total_sources": summary["total_sources"],
        "efficiency": {"skip_percentage": summary["skip_percentage"], "vs_fixed_schedule": summary["efficiency_vs_fixed_schedule"]},
        "sources_to_run": summary["sources_to_run"], "manual_trigger": dict(MANUAL_TRIGGER)}


def _known_source(source):
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=404, detail="Unknown ETL source", headers=PRIVATE_HEADERS)


@router.get("/schedule/source/{source}", response_model=dict, summary="Get source calendar plan")
async def get_source_schedule(source: str):
    _known_source(source)
    plan = _calendar_plan()
    return {"source": source, "timestamp": plan["timestamp"], "evidence": plan["evidence"], **plan["sources"][source]}


@router.get("/health", response_model=dict, summary="ETL evidence availability")
async def get_etl_health():
    try:
        plan = _calendar_plan()
    except HTTPException:
        plan = None
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "scheduler_status": "unverified",
        "plan_status": "available" if plan else "unavailable", "worker_status": "unverified",
        "data_freshness": "unverified", "schedule_summary": plan["summary"] if plan else None,
        "manual_trigger": dict(MANUAL_TRIGGER),
        "note": "A calendar calculation does not establish scheduler activity, job execution or data freshness."}


@router.post("/trigger/{source}", response_model=Accepted, status_code=202, summary="Accept dedicated worker intent")
def trigger_etl_run(source: str, body: TriggerBody | None = None,
    actor: AdminUser = Depends(require_admin), db: Session = Depends(get_db),
    idempotency_key: str | None = Header(None)):
    _known_source(source)
    # Preserve valid legacy direct calls as well as FastAPI's parsed body while
    # applying the same strict shape to either entry point.
    if isinstance(body, dict):
        try:
            body = TriggerBody.model_validate(body)
        except ValidationError:
            raise HTTPException(422, "Invalid operations parameters") from None
    return accept(db, actor, source, TriggerBody() if body is None else body, idempotency_key)


@router.get("/dispatch", response_model=DispatchCapability)
def get_dispatch(db: Session = Depends(get_db)):
    return capability(db)


@router.get("/commands", response_model=CommandPage)
def get_commands(page: int = Query(1, ge=1, le=10000), page_size: int = Query(20, ge=1, le=50),
    source: Source | None = None, status: Status | None = None, db: Session = Depends(get_db)):
    return command_history(db, page, page_size, source, status)


@router.get("/commands/{command_id}", response_model=Command)
def get_command(command_id: str, db: Session = Depends(get_db)):
    return command_detail(db, command_id)
