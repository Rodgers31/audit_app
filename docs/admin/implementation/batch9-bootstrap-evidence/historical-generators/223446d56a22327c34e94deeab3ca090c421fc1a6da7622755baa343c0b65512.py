"""Remove only this lane's verified, unused PostgreSQL container and volume."""
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import time

from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
assert "@127.0.0.1:55492/batch9-bootstrap-1183" in url
print("generator_sha256", hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
engine = create_engine(url)
with engine.connect() as db:
    databases = db.scalars(text("SELECT datname FROM pg_database WHERE datname LIKE 'batch9-bootstrap-%' ORDER BY datname")).all()
    schemas = db.scalars(text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'bootstrap_%'")).all()
    sessions = db.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE pid<>pg_backend_pid() AND datname LIKE 'batch9-bootstrap-%'"))
    assert databases == ["batch9-bootstrap-1183"], databases
    assert schemas == [] and sessions == 0, (schemas, sessions)
    print("remaining_owned_databases", databases, "fixture_schemas", schemas, "other_owned_sessions", sessions)
engine.dispose()
docker = ["docker", "--host", "unix:///Users/roger/.docker/run/docker.sock"]
name = "batch9-bootstrap-1183-db"
ports = subprocess.check_output([*docker, "inspect", "--format", "{{json .NetworkSettings.Ports}}", name], text=True)
assert '"HostIp":"127.0.0.1"' in ports and '"HostPort":"55492"' in ports, ports
print("verified_owned_container_ports", ports.strip())
subprocess.run([*docker, "rm", "-f", "-v", name], check=True)
remaining = subprocess.check_output([*docker, "ps", "-a", "--filter", "name=^/" + name + "$", "--format", "{{.Names}}"], text=True)
assert not remaining.strip(), remaining
for _ in range(20):
    with socket.socket() as sock:
        free = sock.connect_ex(("127.0.0.1", 55492)) != 0
    if free:
        break
    time.sleep(0.05)
assert free
print("owned_container_and_volume_removed", name, "port_55492_free", free)
