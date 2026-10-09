"""Drop every reviewer-owned round-3 re-check (r3b) schema listed in schemas-r3.txt; verify none remain."""
import json, re, sys
from pathlib import Path
from sqlalchemy import create_engine, text
HERE = Path(__file__).resolve().parent
URL = "postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55485/batch7_etl_worker"
listed = [l.split()[0] for l in (HERE / "schemas-r3b.txt").read_text().splitlines() if l.strip()]
assert all(re.fullmatch(r"batch8_adversarial_r3b_[0-9a-f]{32}", s) for s in listed)
engine = create_engine(URL)
with engine.connect() as conn:
    present = set(conn.scalars(text("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'batch8\\_adversarial\\_r3b\\_%'")))
dropped = []
for schema in listed:
    if schema in present:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        dropped.append(schema)
with engine.connect() as conn:
    remaining = list(conn.scalars(text("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'batch8\\_adversarial\\_r3b\\_%'")))
    unlisted_before = sorted(present - set(listed))
    own_other_backends = conn.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE usename=current_user AND pid<>pg_backend_pid()"))
    adv_locks = conn.scalar(text("SELECT count(*) FROM pg_locks WHERE locktype='advisory'"))
engine.dispose()
receipt = {"listed": len(listed), "present_before": len(present), "dropped": len(dropped),
           "remaining_r3_schemas": remaining, "unlisted_r3_schemas_seen": unlisted_before,
           "other_backends_same_role_after": own_other_backends, "advisory_locks_after": adv_locks,
           "engine_disposed": True}
print(json.dumps(receipt, indent=2))
(HERE / "cleanup-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
sys.exit(0 if not remaining else 1)
