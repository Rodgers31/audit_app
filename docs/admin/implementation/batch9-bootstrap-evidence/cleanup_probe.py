"""Remove only this lane's verified, unused PostgreSQL container and volume."""
import hashlib
import os
import json
import sys
from pathlib import Path
import socket
import subprocess
import time

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend/tests/batch9_bootstrap_fixture"))
from owned_database import TARGETS, owned_engine, owned_url

url = os.environ["DATABASE_URL"]
target = owned_url(url)
name = TARGETS[target.port][3]
prefix = TARGETS[target.port][2]
docker = ["docker", "--host", "unix:///Users/roger/.docker/run/docker.sock"]
inspection = json.loads(subprocess.check_output([*docker, "inspect", name], text=True))
assert len(inspection) == 1
container = inspection[0]
assert container["Name"] == "/" + name
assert container["Config"]["Labels"].get("audit.batch9.owner") == "pr590-review"
assert container["NetworkSettings"]["Ports"] == {
    "5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(target.port)}]
}
print("generator_sha256", hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
print("verified_owned_container_id", container["Id"])
engine = owned_engine(url)
with engine.connect() as db:
    assert db.scalar(text("SELECT current_database()")) == target.database
    assert db.scalar(text("SELECT current_user")) == target.username
    databases = db.scalars(text("SELECT datname FROM pg_database WHERE starts_with(datname, :prefix) ORDER BY datname"), {"prefix": prefix}).all()
    schemas = db.scalars(text("SELECT schema_name FROM information_schema.schemata WHERE schema_name ~ '^(bootstrap|spec|adversarial)_'" )).all()
    sessions = db.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE pid<>pg_backend_pid() AND starts_with(datname, :prefix)"), {"prefix": prefix})
    assert databases == [target.database], databases
    assert schemas == [] and sessions == 0, (schemas, sessions)
    print("remaining_owned_databases", databases, "fixture_schemas", schemas, "other_owned_sessions", sessions)
engine.dispose()
subprocess.run([*docker, "rm", "-f", "-v", container["Id"]], check=True)
remaining = subprocess.check_output([*docker, "ps", "-a", "--filter", "name=^/" + name + "$", "--format", "{{.Names}}"], text=True)
assert not remaining.strip(), remaining
for _ in range(20):
    with socket.socket() as sock:
        free = sock.connect_ex(("127.0.0.1", target.port)) != 0
    if free:
        break
    time.sleep(0.05)
assert free
print("owned_container_and_volume_removed", name, "port_free", free)
