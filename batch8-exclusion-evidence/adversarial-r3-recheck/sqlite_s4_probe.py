"""Probe only: why the exact-correlation dispatch scope is refused on SQLite (read-only on the S-run file copy)."""
import shutil, sys
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
@compiles(JSONB, "sqlite")
def _j(*a, **k): return "TEXT"
import common  # socket guard + registry
from uuid import UUID
from seeding.exclusion import DomainExecution, _enter_dispatch
src = sorted(Path(common.HERE).glob("sqlite-*.db"))[0]
copy = src.with_name("probe-" + src.name); shutil.copy(src, copy)
e = create_engine(f"sqlite:///{copy}"); f = sessionmaker(bind=e)
with e.connect() as c:
    cmd, gen, tok = c.execute(text("SELECT id, generation, claim_token FROM etl_dispatch_commands WHERE status='running'")).one()
s = DomainExecution(f, "audits", UUID(tok), UUID(cmd), UUID(gen))
try:
    _enter_dispatch(f, s, "audits", False); print("ENTERED")
except Exception as exc:
    print("REFUSED", type(exc).__name__, str(exc)[:200])
e.dispose(); copy.unlink(); common.dispose_all()
