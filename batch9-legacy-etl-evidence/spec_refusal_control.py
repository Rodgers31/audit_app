"""Independent refusal propagation control; no database/network/provider calls."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from etl.kenya_pipeline import KenyaDataPipeline
from etl.monitored_runner import ETLMonitor
from seeding.exclusion import DomainOwnershipError

socket.socket.connect = lambda *args: (_ for _ in ()).throw(RuntimeError("Network forbidden"))

class RefusingLoader:
    async def load_audit_findings_document(self, *args):
        raise DomainOwnershipError("independent owned refusal control")

async def immediate_sleep(*args):
    pass

async def control():
    pipeline = KenyaDataPipeline.__new__(KenyaDataPipeline)
    with tempfile.TemporaryDirectory(prefix="batch9-legacy-spec-") as temp:
        pipeline.storage_path = Path(temp)
        pipeline.kenya_sources = {}
        pipeline.processed_manifest = {}
        pipeline._ssl_verify_for = lambda *args: True
        pipeline.http = SimpleNamespace(get=lambda *args, **kwargs: SimpleNamespace(content=b"%PDF-inert-spec-refusal", headers={"content-type":"application/pdf"}, raise_for_status=lambda: None))
        pipeline._maybe_upload_to_s3 = lambda *args: None
        pipeline.extractor = SimpleNamespace(extract_with_fallback=lambda *args: {"confidence":1.0})
        pipeline.audit_parser = SimpleNamespace(parse=lambda *args: [{"finding_text":"inert"}])
        pipeline.data_validator = SimpleNamespace(validate_audit_data=lambda *args: SimpleNamespace(is_valid=True, confidence=1.0, warnings=[]))
        pipeline.db_loader = RefusingLoader()
        pipeline.scheduler = SimpleNamespace(get_schedule_summary=lambda: {"efficiency":{"skip_percentage":0}}, should_run=lambda source: (source=="oag", "owned control"), get_next_run=lambda source: ("none", "inert"))
        pipeline.discover_budget_documents = lambda *args: [{"url":"https://fixture.invalid/refusal.pdf", "source_key":"oag", "title":"Inert refusal", "source":"Owned fixture", "doc_type":"audit"}]
        monitor = ETLMonitor()
        asyncio.sleep = immediate_sleep
        try:
            result = await monitor.run_with_monitoring(pipeline.run_full_pipeline)
        except DomainOwnershipError:
            return {"verdict":"PASSED", "monitor_success":monitor.success, "refusal_propagated":True}
        return {"verdict":"FAILED", "monitor_success":monitor.success, "refusal_propagated":False, "result":result}

result = asyncio.run(control())
receipt = {"generated_by":str(Path(__file__).relative_to(ROOT)), "generator_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "generated_at":datetime.now(timezone.utc).isoformat(), "target_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(), "source_sha256":{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ["etl/kenya_pipeline.py","etl/monitored_runner.py","etl/scheduler.py"]}, "python":sys.version, "command":sys.argv, **result}
out = Path(sys.argv[1])
out.write_text(json.dumps(receipt,indent=2))
read_back = json.loads(out.read_text())
assert read_back["generator_sha256"] == receipt["generator_sha256"]
assert read_back["verdict"] == receipt["verdict"]
print(json.dumps(result,indent=2))
sys.exit(0 if result["verdict"]=="PASSED" else 1)
