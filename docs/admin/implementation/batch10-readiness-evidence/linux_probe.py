"""Linux replay using an owned preinstalled runtime and read-only source mount."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

IMAGE = "sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f"


def run(root, artifacts, minimum):
    name = "batch10-readiness-linux-" + uuid4().hex[:12]
    network = name + "-network"
    network_id = subprocess.check_output(
        [
            "docker",
            "network",
            "create",
            "--label",
            "audit.owner=batch10-readiness",
            network,
        ],
        text=True,
    ).strip()
    python = (
        "/owned/linux-min-venv/bin/python"
        if minimum
        else "/owned/linux-venv/bin/python"
    )
    setup = ""
    if minimum:
        setup = (
            "python -m venv /owned/linux-min-venv && "
            'printf "%s\\n" /owned/linux-venv/lib/python3.12/site-packages > '
            "/owned/linux-min-venv/lib/python3.12/site-packages/readiness-deps.pth && "
            "/owned/linux-min-venv/bin/pip install --no-deps --cache-dir /owned/linux-pip-cache sqlalchemy==2.0.23 && "
        )
    script = (
        setup
        + python
        + ' -c "import platform,sqlalchemy; print(platform.platform(),sqlalchemy.__version__)" && '
        + python
        + (
            " -m pytest /source/backend/tests/test_batch10_startup_readiness.py "
            '/source/backend/tests/test_batch9_bootstrap_sessions.py -k "lifespans or not nonbudget" '
            f"--basetemp /owned/linux-tmp-{name} -o cache_dir=/owned/linux-cache-{name} -vs"
        )
    )
    command = [
        "docker",
        "run",
        "--pull=never",
        "--name",
        name,
        "--network",
        network,
        "--label",
        "audit.owner=batch10-readiness",
        "-v",
        str(root) + ":/source:ro",
        "-v",
        str(artifacts) + ":/owned",
        "-w",
        "/source/backend",
        "-e",
        "PYTHON_DOTENV_DISABLED=1",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-e",
        "DATABASE_URL=sqlite:////owned/batch10-readiness-linux-runner.sqlite",
        "-e",
        "JWT_SECRET_KEY=batch10-readiness-inert-key",
        "-e",
        "AUTO_SEEDER_ENABLED=false",
        "-e",
        "AUTO_WARMUP_ENABLED=false",
        "-e",
        "ENABLE_ETL_SCHEDULER=false",
        IMAGE,
        "sh",
        "-c",
        script,
    ]
    try:
        result = subprocess.run(command, timeout=120)
        if result.returncode:
            raise RuntimeError("Linux cohort failed")
    finally:
        check = subprocess.run(
            ["docker", "inspect", name], capture_output=True, text=True, timeout=30
        )
        if check.returncode == 0:
            state = json.loads(check.stdout)[0]
            if (
                state["Config"]["Labels"]["audit.owner"] != "batch10-readiness"
                or state["Name"] != "/" + name
            ):
                raise RuntimeError("Linux container ownership mismatch")
            subprocess.run(
                ["docker", "rm", "-f", "-v", state["Id"]], check=True, timeout=30
            )
        subprocess.run(["docker", "network", "rm", network_id], check=True, timeout=30)
        if (
            subprocess.run(
                ["docker", "inspect", name], capture_output=True, timeout=30
            ).returncode
            == 0
        ):
            raise RuntimeError("Linux container survived cleanup")
        print("OWNED_LINUX_REMOVED", name, network_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--minimum", action="store_true")
    args = parser.parse_args()
    run(args.root.resolve(), args.artifacts.resolve(), args.minimum)
