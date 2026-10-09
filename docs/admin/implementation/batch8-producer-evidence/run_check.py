"""Run a local check with an allowlisted environment and read-back provenance."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--lint-packages", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[4]
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    args.output_dir.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(args.lint_packages.resolve()) + os.pathsep + str(repo / "backend"),
        "PYTHON_DOTENV_DISABLED": "1", "SECRET_BACKEND": "env",
        "SECRET_KEY": "batch8-inert-test-key",
        "DATABASE_URL": "sqlite:///" + str(args.output_dir.resolve() / "runner.sqlite"),
        "ENVIRONMENT": "testing", "TESTING": "true", "REDIS_URL": "",
        "AUTO_SEEDER_ENABLED": "false", "AUTO_WARMUP_ENABLED": "false",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    result = subprocess.run(command, cwd=repo / "backend", env=env,
                            capture_output=True, text=True)
    report = {
        "generated_by": str(Path(__file__).relative_to(repo)),
        "generator_sha256": sha(Path(__file__)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "target_tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=repo, text=True).strip(),
        "producer_sha256": sha(repo / "backend/scripts/r2_producer_acceptance.py"),
        "test_sha256": sha(repo / "backend/tests/test_r2_producer_capture.py") if (repo / "backend/tests/test_r2_producer_capture.py").exists() else None,
        "command": command, "cwd": str(repo / "backend"),
        "python": sys.version, "platform": platform.platform(),
        "exit_status": result.returncode,
        "verdict": "PASS" if result.returncode == 0 else "FAILED",
        "stdout": result.stdout, "stderr": result.stderr,
    }
    path = args.output_dir / (args.label + ".json")
    # Receipts are append-only; a rerun requires a new label.
    with path.open("x") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    check = json.loads(path.read_text())
    assert check["generator_sha256"] == sha(Path(__file__))
    assert check["exit_status"] == result.returncode
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    print(f"receipt={path}; exit={result.returncode}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
