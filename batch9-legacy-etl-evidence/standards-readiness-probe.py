"""Independent incomplete-schema control; all writes use temporary SQLite."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

with tempfile.TemporaryDirectory(prefix="batch9-legacy-readiness-") as temp:
    url = "sqlite:///" + str(Path(temp) / "owned.sqlite")
    os.environ["DATABASE_URL"] = url
    import sqlalchemy
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import sessionmaker
    from models import Base
    from etl.database_loader import DatabaseLoader
    from seeding.exclusion import enter_domain

    @compiles(JSONB, "sqlite")
    def jsonb_sqlite(*args, **kwargs):
        return "TEXT"

    loader = DatabaseLoader(url)
    Base.metadata.create_all(loader.engine)
    with loader.engine.begin() as db:
        db.execute(text("CREATE TABLE inert_effects (n integer)"))
    retained = enter_domain(sessionmaker(bind=loader.engine), "audits", False)
    retained.close()  # No acknowledgement: authoritative retained execution.
    with loader.engine.begin() as db:
        db.execute(text("DROP INDEX uq_seeding_active_domain"))
    events = []
    try:
        loader.check_ownership_ready()
        events.append({"check_ready": "returned"})
        with loader.get_db_session() as db:
            db.execute(text("INSERT INTO inert_effects VALUES (1)"))
            db.commit()
        events.append({"next_legacy_writer": "committed"})
    except Exception as exc:
        events.append({"refusal": type(exc).__name__, "detail": str(exc)})
    with loader.engine.connect() as db:
        claims = db.scalar(text("SELECT count(*) FROM seeding_domain_claims WHERE domain='audits'"))
        effects = db.scalar(text("SELECT count(*) FROM inert_effects"))
    receipt = {
        "generated_by": str(Path(__file__).relative_to(ROOT)),
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "command": [sys.executable, str(Path(__file__).resolve())],
        "python": platform.python_version(), "sqlalchemy": sqlalchemy.__version__,
        "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in ("etl/database_loader.py", "etl/writer_ownership.py", "backend/seeding/exclusion.py")},
        "database": "owned temporary SQLite; deleted after probe",
        "events": events, "audit_claim_history": claims, "committed_inert_effects": effects,
        "acceptance": "readiness refuses storage missing the protocol's unique active-domain index",
        "verdict": "PASSED" if effects == 0 else "FAILED",
    }
    output = ROOT / "batch9-legacy-etl-evidence" / "standards-readiness-probe.json"
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    loader.engine.dispose()
    sys.exit(0 if effects == 0 else 1)
