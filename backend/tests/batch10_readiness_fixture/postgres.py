"""Automatic local disposable fixture, with exact container/network/volume cleanup."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from uuid import uuid4

IMAGE = "public.ecr.aws/docker/library/postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675"
OWNER = "batch10-readiness"



# Only this reviewed finite selector can change CI fixture transport.
import hashlib as _transport_hashlib
from pathlib import Path as _TransportPath
_transport_path = _TransportPath(__file__).resolve().parents[3] / 'tools/ci_postgres_image_transport.py'
_transport_raw = _transport_path.read_bytes()
if _transport_hashlib.sha256(_transport_raw).hexdigest() != 'e0b369929fce5a73b907dbfe462f89f6b9d65403fb6218457bb056df65d5337a':
    raise RuntimeError('CI test image transport source changed')
_CI_IMAGE_TRANSPORT = {'__file__': str(_transport_path)}
exec(compile(_transport_raw, str(_transport_path), 'exec'), _CI_IMAGE_TRANSPORT)
IMAGE = _CI_IMAGE_TRANSPORT['select_image'](IMAGE)

def docker(*args, check=True):
    endpoint = next(
        (
            p
            for p in (
                Path("/var/run/docker.sock"),
                Path.home() / ".docker/run/docker.sock",
            )
            if p.exists()
        ),
        None,
    )
    if endpoint is None:
        raise RuntimeError("Local Docker prerequisite is missing")
    result = subprocess.run(
        ["docker", "--host", "unix://" + str(endpoint), *args],
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        timeout=30,
    )
    if check and result.returncode:
        raise RuntimeError(f"Docker {args[:2]} failed: {result.stderr}")
    return result


@contextmanager
def postgres():
    image = json.loads(docker("image", "inspect", IMAGE).stdout)[0]
    server = json.loads(docker("version", "--format", "{{json .Server}}").stdout)
    if (
        IMAGE not in image["RepoDigests"]
        or image["Os"] != server["Os"]
        or image["Architecture"] != server["Arch"]
    ):
        raise RuntimeError("Fixture image/platform mismatch")
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", 55520))
        except OSError:
            probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    token = uuid4().hex[:16]
    name = "batch10-readiness-" + token
    network = name + "-network"
    url = f"postgresql+psycopg2://batch10_readiness:inert-local@127.0.0.1:{port}/{name}"
    network_id = container_id = None
    volumes = []
    try:
        network_id = docker(
            "network", "create", "--label", "audit.owner=" + OWNER, network
        ).stdout.strip()
        container_id = docker(
            "run",
            "--pull=never",
            "-d",
            "--name",
            name,
            "--network",
            network,
            "--label",
            "audit.owner=" + OWNER,
            "-p",
            f"127.0.0.1:{port}:5432",
            "-e",
            "POSTGRES_USER=batch10_readiness",
            "-e",
            "POSTGRES_PASSWORD=inert-local",
            "-e",
            "POSTGRES_DB=" + name,
            IMAGE,
        ).stdout.strip()
        state = json.loads(docker("inspect", container_id).stdout)[0]
        if (
            state["Id"] != container_id
            or state["Config"]["Labels"]["audit.owner"] != OWNER
        ):
            raise RuntimeError("Container ownership mismatch")
        volumes = [m["Name"] for m in state["Mounts"] if m["Type"] == "volume"]
        deadline = time.monotonic() + 30
        while docker(
            "exec",
            container_id,
            "pg_isready",
            "-h",
            "127.0.0.1",
            "-U",
            "batch10_readiness",
            check=False,
        ).returncode:
            if time.monotonic() >= deadline:
                raise RuntimeError("Postgres startup timeout")
            time.sleep(0.1)
        print(
            "OWNED_READINESS_POSTGRES",
            json.dumps(
                dict(
                    container=container_id,
                    name=name,
                    network=network_id,
                    volumes=volumes,
                    image=IMAGE,
                    image_id=image["Id"],
                    server=server,
                    port=port,
                    database=name,
                )
            ),
        )
        yield url
    finally:
        if container_id:
            state = json.loads(docker("inspect", container_id).stdout)[0]
            if (
                state["Name"] != "/" + name
                or state["Config"]["Labels"]["audit.owner"] != OWNER
            ):
                raise RuntimeError("Cleanup ownership mismatch")
            docker("rm", "-f", "-v", container_id)
            if docker("inspect", container_id, check=False).returncode == 0:
                raise RuntimeError("Container survived cleanup")
            for volume in volumes:
                if docker("volume", "inspect", volume, check=False).returncode == 0:
                    raise RuntimeError("Owned volume survived cleanup")
        if network_id:
            state = json.loads(docker("network", "inspect", network_id).stdout)[0]
            if (
                state["Name"] != network
                or state["Labels"]["audit.owner"] != OWNER
                or state["Containers"]
            ):
                raise RuntimeError("Network cleanup ownership mismatch")
            docker("network", "rm", network_id)
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", port))
        print("OWNED_READINESS_REMOVED", name, network, volumes, "port_free", port)
