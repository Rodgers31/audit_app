"""Compatibility entry point for the backend-packaged calendar planner."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import runpy

_PLANNER_PATH = Path(__file__).resolve().parents[1] / "backend/etl/smart_scheduler.py"

if __name__ == "__main__":
    # Preserve the existing standalone demonstration without changing sys.path.
    runpy.run_path(str(_PLANNER_PATH), run_name="__main__")
else:
    _spec = spec_from_file_location("audit_calendar_planner", _PLANNER_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError("Calendar planner unavailable")
    _planner = module_from_spec(_spec)
    _spec.loader.exec_module(_planner)
    SmartScheduler = _planner.SmartScheduler
    should_run_etl = _planner.should_run_etl
