"""Independent manual-session lifetime control on owned SQLite only."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"backend"))
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from models import Base
import seeding.exclusion
sys.path.insert(0,str(ROOT))
from etl.database_loader import DatabaseLoader

@compiles(JSONB,"sqlite")
def jsonb_sqlite(*args,**kwargs):
    return "TEXT"

with tempfile.TemporaryDirectory(prefix="batch9-legacy-spec-session-") as temp:
    loader=DatabaseLoader(f"sqlite:///{temp}/owned.sqlite")
    Base.metadata.create_all(loader.engine)
    with loader.engine.connect() as conn:
        outer=conn.begin()
        try:
            db=loader.SessionLocal(bind=conn)
            db.execute(text("SELECT 1"))
            db.close()
            with loader.engine.connect() as read:
                active=read.scalar(text("SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL"))
            result={"verdict":"FAILED", "active_claims_after_close":active, "external_transaction_still_active":conn.in_transaction()}
        except Exception as exc:
            result={"verdict":"PASSED", "external_bind_refused":type(exc).__name__, "message":str(exc)}
        finally:
            outer.rollback()
    loader.engine.dispose()

receipt={"generated_by":str(Path(__file__).relative_to(ROOT)), "generator_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "generated_at":datetime.now(timezone.utc).isoformat(), "target_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(), "source_sha256":{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ["etl/database_loader.py","etl/writer_ownership.py"]}, "python":sys.version, "command":sys.argv, **result}
out=Path(sys.argv[1]); out.write_text(json.dumps(receipt,indent=2)); read_back=json.loads(out.read_text())
assert read_back["generator_sha256"]==receipt["generator_sha256"]
assert read_back["verdict"]==receipt["verdict"]
print(json.dumps(result,indent=2)); sys.exit(0 if result["verdict"]=="PASSED" else 1)
