"""Check documented standalone scheduler import with inert optional schedule."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
from types import ModuleType

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"etl"))
sys.modules["schedule"]=ModuleType("schedule")
try:
    runpy.run_module("scheduler",run_name="independent_spec_import")
    result={"verdict":"PASSED", "documented_module_imported":True}
except Exception as exc:
    result={"verdict":"FAILED", "documented_module_imported":False, "error_type":type(exc).__name__, "error":str(exc)}
receipt={"generated_by":str(Path(__file__).relative_to(ROOT)), "generator_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "generated_at":datetime.now(timezone.utc).isoformat(), "target_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(), "source_sha256":{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ["etl/scheduler.py","etl/monitored_runner.py"]}, "python":sys.version, "command":sys.argv, "limitation":"schedule is an inert dependency; import only, no scheduling, writer or network calls", **result}
out=Path(sys.argv[1]); out.write_text(json.dumps(receipt,indent=2)); read_back=json.loads(out.read_text())
assert read_back["generator_sha256"]==receipt["generator_sha256"]
assert read_back["verdict"]==receipt["verdict"]
print(json.dumps(result,indent=2)); sys.exit(0 if result["verdict"]=="PASSED" else 1)
