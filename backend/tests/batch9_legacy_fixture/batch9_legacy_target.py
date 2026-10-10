"""Exact, inert target required before destructive review process controls."""
import os
from contextlib import contextmanager

from sqlalchemy.engine import make_url

OWNED_HOST = "127.0.0.1"
_port = os.getenv("BATCH9_LEGACY_FIXTURE_PORT", "55506")
if _port not in ("55506", "55507"):
    raise ValueError("Exact owned legacy fixture target required; overrides refused")
OWNED_PORT = int(_port)
OWNED_DATABASE = "batch9-review-596"
OWNED_USER = "batch9_review_596"
OWNED_PASSWORD = "batch9-review-inert-local"


def validate_target(raw):
    try:
        url = make_url(raw)
    except Exception:
        raise ValueError("Owned legacy fixture URL required") from None
    if (url.drivername not in ("postgresql+psycopg2", "postgresql") or url.host != OWNED_HOST
            or url.port != OWNED_PORT or url.database != OWNED_DATABASE
            or url.username != OWNED_USER or url.password != OWNED_PASSWORD
            or url.query or any(key.startswith("PG") for key in os.environ)):
        raise ValueError("Exact owned legacy fixture target required; overrides refused")
    return raw


def connect_args():
    return {"host": OWNED_HOST, "hostaddr": OWNED_HOST, "port": OWNED_PORT,
            "dbname": OWNED_DATABASE, "user": OWNED_USER, "password": OWNED_PASSWORD}

DEFAULT_URL = f"postgresql+psycopg2://{OWNED_USER}:{OWNED_PASSWORD}@{OWNED_HOST}:{OWNED_PORT}/{OWNED_DATABASE}"
APPROVED_IMAGE = "public.ecr.aws/docker/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3"


@contextmanager
def owned_postgres_fixture(override, root, receipt_dir):
    """Prepare one migrated process fixture unless its owner provided the exact target."""
    import hashlib
    import json
    import socket
    import subprocess
    import sys
    import time
    from pathlib import Path
    from uuid import uuid4
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    url = validate_target(override or DEFAULT_URL)
    if override:
        yield url
        return
    token = uuid4().hex[:12]
    stem = "batch9-review-596-" + token
    container, network = stem + "-db", stem + "-network"
    receipt = {"generated_by": str(Path(__file__).relative_to(root)),
               "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "container": container, "network": network, "port": OWNED_PORT,
               "database": OWNED_DATABASE, "image": APPROVED_IMAGE,
               "container_removed": False, "network_removed": False}
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / "owned-postgres.json"
    network_created = False
    container_created = False
    def command(args):
        return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    try:
        with socket.socket() as reservation:
            reservation.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            reservation.bind((OWNED_HOST, OWNED_PORT))
        command(["docker", "image", "inspect", APPROVED_IMAGE])
        command(["docker", "network", "create", "--label", "audit_app.fixture=" + token, network])
        network_created = True
        result = command(["docker", "run", "--pull", "never", "--detach", "--name", container,
                          "--label", "audit_app.fixture=" + token, "--network", network,
                          "--publish", f"{OWNED_HOST}:{OWNED_PORT}:5432",
                          "--env", "POSTGRES_USER=" + OWNED_USER,
                          "--env", "POSTGRES_PASSWORD=" + OWNED_PASSWORD,
                          "--env", "POSTGRES_DB=" + OWNED_DATABASE, APPROVED_IMAGE])
        container_created = True
        receipt["container_id"] = result.stdout.strip()
        inspection = json.loads(command(["docker", "inspect", container]).stdout)[0]
        if (inspection["Config"]["Image"] != APPROVED_IMAGE
                or inspection["Config"]["Labels"].get("audit_app.fixture") != token
                or inspection["NetworkSettings"]["Ports"]["5432/tcp"] != [{"HostIp": OWNED_HOST, "HostPort": str(OWNED_PORT)}]):
            raise RuntimeError("Owned PostgreSQL identity/binding mismatch")
        receipt["image_id"] = inspection["Image"]
        deadline = time.monotonic() + 40
        while True:
            ready = subprocess.run(["docker", "exec", container, "pg_isready", "-U", OWNED_USER, "-d", OWNED_DATABASE], capture_output=True)
            if ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Owned PostgreSQL readiness timed out")
            time.sleep(.2)
        environment = {"PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
                       "PYTHONDONTWRITEBYTECODE": "1", "PYTHON_DOTENV_DISABLED": "1",
                       "DATABASE_URL": url, "PYTHONPATH": str(root / "backend")}
        config = Config(str(root / "backend/alembic.ini"))
        config.set_main_option("script_location", str(root / "backend/alembic"))
        heads = ScriptDirectory.from_config(config).get_heads()
        if len(heads) != 1:
            raise RuntimeError("Owned PostgreSQL fixture requires one actual migration head")
        receipt["expected_migration_revision"] = heads[0]
        migrated = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                                  cwd=root / "backend", env=environment, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        receipt["migration_exit"] = migrated.returncode
        receipt["migration_output"] = migrated.stdout
        if migrated.returncode:
            raise RuntimeError("Owned PostgreSQL migration failed")
        import psycopg2
        with psycopg2.connect(**connect_args()) as db:
            with db.cursor() as cursor:
                cursor.execute("SELECT current_database(),current_user,version(),(SELECT version_num FROM alembic_version)")
                database, user, version, revision = cursor.fetchone()
                if database != OWNED_DATABASE or user != OWNED_USER or revision != heads[0]:
                    raise RuntimeError("Owned PostgreSQL migrated target mismatch")
                receipt.update(server_version=version, migration_revision=revision)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        yield url
    finally:
        errors = []
        # A failed docker run may create an inactive container before returning.
        inspection = subprocess.run(["docker", "inspect", container], capture_output=True, text=True)
        if inspection.returncode == 0:
            metadata = json.loads(inspection.stdout)[0]
            if metadata["Config"]["Labels"].get("audit_app.fixture") != token:
                errors.append("container ownership changed; removal refused")
            else:
                removed = subprocess.run(["docker", "rm", "--force", "--volumes", container], capture_output=True, text=True)
                receipt["container_removed"] = removed.returncode == 0
                if removed.returncode:
                    errors.append("owned container removal failed")
        else:
            receipt["container_removed"] = not container_created
        if network_created:
            removed = subprocess.run(["docker", "network", "rm", network], capture_output=True, text=True)
            receipt["network_removed"] = removed.returncode == 0
            if removed.returncode:
                errors.append("owned network removal failed")
        else:
            receipt["network_removed"] = True
        deadline = time.monotonic() + 10
        while True:
            try:
                with socket.socket() as reservation:
                    # TCP TIME_WAIT from a stopped fixture is not a live listener.
                    reservation.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    reservation.bind((OWNED_HOST, OWNED_PORT))
                receipt["port_free_after_cleanup"] = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    receipt["port_free_after_cleanup"] = False
                    if container_created:
                        errors.append("owned port remained occupied")
                    break
                time.sleep(.05)
        receipt["cleanup_errors"] = errors
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        print("BATCH9_OWNED_POSTGRES_RECEIPT " + str(receipt_path), flush=True)
        if errors:
            raise RuntimeError("Owned PostgreSQL cleanup failed: " + "; ".join(errors))
