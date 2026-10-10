"""Append an offline PDF pin check with command, output and byte provenance."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


REPO = Path(__file__).resolve().parents[4]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, default=REPO / "backend")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or Path(args.label).name != args.label:
        parser.error("an offline command and filename-only label are required")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    destination = args.output_dir / (args.label + ".json")
    if destination.exists():
        parser.error("receipts are append-only; use a fresh label")
    # No application startup, plugin autoload, dotenv or provider credentials.
    env = {"PATH": os.defpath + ":/sbin", "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHON_DOTENV_DISABLED": "1", "PYTHONNOUSERSITE": "1",
           "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    result = subprocess.run(command, cwd=args.cwd, env=env, text=True,
                            capture_output=True, timeout=180)
    files = [".github/workflows/r2-acceptance.yml", "backend/scripts/r2_producer_acceptance.py",
             "backend/tests/test_r2_acceptance_workflow_pin.py",
             "docs/admin/implementation/batch8-producer-evidence/run_check.py"]
    generator = Path(__file__).resolve()
    receipt = {
        "generated_by": str(generator.relative_to(REPO)),
        "generator_sha256": sha(generator),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "target_tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=REPO, text=True).strip(),
        "working_tree_status": subprocess.check_output(["git", "status", "--short"], cwd=REPO, text=True),
        "source_sha256": {name: sha(REPO / name) for name in files},
        "command": command, "cwd": str(args.cwd.resolve()),
        "python": sys.version, "platform": platform.platform(),
        "versions": {name: importlib.metadata.version(name) for name in ["pytest", "PyYAML"]},
        "environment": env,
        "exit_status": result.returncode,
        "verdict": "PASS" if result.returncode == 0 else "FAILED",
        "stdout": result.stdout, "stderr": result.stderr,
        "scope": "offline shell/argument/git guards only; live run boundary replaced; no workflow invocation",
    }
    with destination.open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    reread = json.loads(destination.read_text())
    assert reread == receipt
    assert reread["generator_sha256"] == sha(generator)
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    print(f"receipt={destination} verdict={receipt['verdict']} exit={result.returncode}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
