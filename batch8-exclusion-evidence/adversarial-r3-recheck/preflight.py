"""r3b preflight: server identity, connection headroom, pre-existing r3b schemas (must be none)."""
import json
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
URL = "postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55485/batch7_etl_worker"
e = create_engine(URL, poolclass=NullPool)
with e.connect() as c:
    out = {k: c.scalar(text(q)) for k, q in {
        "version": "SELECT version()", "max_connections": "SHOW max_connections",
        "backends_total": "SELECT count(*) FROM pg_stat_activity WHERE backend_type='client backend'",
        "backends_same_role": "SELECT count(*) FROM pg_stat_activity WHERE usename=current_user",
        "r3b_schemas": "SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'batch8\\_adversarial\\_r3b\\_%'",
        "r3_schemas_left_by_prior": "SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'batch8\\_adversarial\\_r3\\_%'",
        "idle_in_tx_timeout": "SHOW idle_in_transaction_session_timeout", "timezone": "SHOW TimeZone",
        "superuser": "SELECT rolsuper FROM pg_roles WHERE rolname=current_user"}.items()}
e.dispose()
print(json.dumps(out, indent=1, default=str))
