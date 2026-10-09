"""Drop only this reviewer's owned schemas recovered from its retained logs."""
import json
from pathlib import Path
import re
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
from sqlalchemy import create_engine, text
from sqlalchemy.schema import DropSchema

directory = Path(__file__).resolve().parent
schemas = set()
for path in directory.glob("run-*.log"):
    for line in path.read_text().splitlines():
        try:
            entry = json.loads(line)
        except (ValueError, TypeError):
            continue
        if type(entry) is not dict:
            continue
        if type(entry.get("schema")) is str:
            schemas.add(entry["schema"])
        if type(entry.get("schemas")) is list:
            schemas.update(entry["schemas"])
assert schemas and all(type(name) is str and re.fullmatch(r"batch8_adversarial_[a-z0-9_]+", name) for name in schemas)
engine = create_engine("postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55485/batch7_etl_worker")
with engine.begin() as conn:
    for schema in sorted(schemas):
        existed = conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:schema)"), {"schema":schema})
        conn.execute(DropSchema(schema, cascade=True, if_exists=True))
        print(json.dumps({"owned_schema":schema,"existed":existed,"dropped":True}), flush=True)
    remaining = conn.execute(text("SELECT nspname FROM pg_namespace WHERE nspname = ANY(:schemas)"), {"schemas":sorted(schemas)}).all()
    assert not remaining, remaining
print(json.dumps({"owned_schema_count":len(schemas),"remaining":0}), flush=True)
engine.dispose()
