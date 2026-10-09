"""Strict default fixture: use a prepared immutable image, never a live database."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from uuid import uuid4

from sqlalchemy import text
from .owned_database import owned_engine

IMAGE = "public.ecr.aws/docker/library/postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675"
OWNER = "pr590-review"
PORT = 55492


def docker_command():
    sockets = (Path("/var/run/docker.sock"), Path.home() / ".docker/run/docker.sock")
    endpoint = next((p for p in sockets if p.exists()), None)
    if endpoint is None:
        raise RuntimeError("Owned bootstrap fixture requires a local Docker socket")
    return ["docker", "--host", "unix://" + str(endpoint)]


def run(docker, *args):
    result = subprocess.run([*docker, *args], env={"PATH": os.environ["PATH"]},
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("Owned bootstrap Docker operation failed: " + " ".join(args[:2]))
    return result.stdout.strip()


@contextmanager
def postgres():
    docker = docker_command()
    image = json.loads(run(docker, "image", "inspect", IMAGE))
    server = json.loads(run(docker, "version", "--format", "{{json .Server}}"))
    assert len(image) == 1 and IMAGE in image[0]["RepoDigests"]
    assert image[0]["Os"] == server["Os"] == "linux"
    assert image[0]["Architecture"] == server["Arch"]
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", PORT))
    token = uuid4().hex[:16]
    name, network = "batch9-review-590-auto-" + token, "batch9-review-590-auto-network-" + token
    database = "batch9-bootstrap-auto-" + token
    url = f"postgresql+psycopg2://batch9_bootstrap:batch9-inert-local@127.0.0.1:{PORT}/{database}"
    network_id = container_id = None
    engine = None
    try:
        network_id = run(docker, "network", "create", "--label", "audit.batch9.owner=" + OWNER, network)
        container_id = run(docker, "run", "--pull=never", "-d", "--name", name, "--network", network,
                           "--label", "audit.batch9.owner=" + OWNER, "-p", f"127.0.0.1:{PORT}:5432",
                           "-e", "POSTGRES_USER=batch9_bootstrap", "-e", "POSTGRES_PASSWORD=batch9-inert-local",
                           "-e", "POSTGRES_DB=" + database, IMAGE)
        container = json.loads(run(docker, "inspect", container_id))[0]
        assert container["Name"] == "/" + name and container["Id"] == container_id
        assert container["Config"]["Labels"]["audit.batch9.owner"] == OWNER
        assert container["NetworkSettings"]["Ports"] == {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(PORT)}]}
        isolated = json.loads(run(docker, "network", "inspect", network_id))[0]
        assert isolated["Id"] == network_id and isolated["Driver"] == "bridge"
        assert isolated["Labels"]["audit.batch9.owner"] == OWNER
        assert set(isolated["Containers"]) == {container_id}
        assert set(container["NetworkSettings"]["Networks"]) == {network}
        engine = owned_engine(url)
        deadline = time.monotonic() + 30
        while True:
            try:
                with engine.connect() as db:
                    assert db.scalar(text("SELECT current_database()")) == database
                    assert db.scalar(text("SELECT current_user")) == "batch9_bootstrap"
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        print("OWNED_BOOTSTRAP_DEFAULT_FIXTURE", json.dumps({"image": IMAGE, "image_id": image[0]["Id"],
              "container": name, "container_id": container_id, "network": network, "database": database, "port": PORT}))
        yield url
    finally:
        if engine is not None:
            engine.dispose()
        if container_id:
            container = json.loads(run(docker, "inspect", container_id))[0]
            assert container["Id"] == container_id and container["Name"] == "/" + name
            assert container["Config"]["Labels"]["audit.batch9.owner"] == OWNER
            run(docker, "rm", "-f", "-v", container_id)
        if network_id:
            isolated = json.loads(run(docker, "network", "inspect", network_id))[0]
            assert isolated["Id"] == network_id and isolated["Name"] == network
            assert isolated["Labels"]["audit.batch9.owner"] == OWNER and not isolated["Containers"]
            run(docker, "network", "rm", network_id)
        deadline = time.monotonic() + 5
        while True:
            try:
                with socket.socket() as probe:
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    probe.bind(("127.0.0.1", PORT))
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        print("OWNED_BOOTSTRAP_DEFAULT_FIXTURE_REMOVED", name, network, "port_free", PORT)
