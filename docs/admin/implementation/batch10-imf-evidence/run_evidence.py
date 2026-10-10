"""Record source-bound offline pytest executions in a fresh external directory.

Usage: python run_evidence.py CHECKOUT OUTPUT_DIR TEST_SELECTION...
Outputs are append-only. The portable verifier checks their original hashes;
historical red records intentionally bind pre-fix source, not current code.
"""

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def source_state(root, names):
    return {
        "head": git(root, "rev-parse", "HEAD"),
        "tree": git(root, "rev-parse", "HEAD^{tree}"),
        "status": git(root, "status", "--porcelain", "--untracked-files=all"),
        "sha256": {name: digest(root / name) for name in names},
    }


def source_names(root):
    """Entire tracked corpus plus the explicitly owned, unpublished lane files."""
    names = set(git(root, "ls-files").splitlines())
    names.update(
        str(p.relative_to(root))
        for p in (root / "backend/tests").glob("test_batch10_imf_actuals*.py")
    )
    names.update(
        str(p.relative_to(root))
        for p in (root / "docs/admin/implementation/batch10-imf-evidence").rglob("*")
        if p.is_file()
    )
    handoff = root / "docs/admin/implementation/BATCH_10_IMF_ACTUALS_HANDOFF.md"
    if handoff.is_file():
        names.add(str(handoff.relative_to(root)))
    return sorted(names)


def main():
    root = Path(sys.argv[1]).resolve(strict=True)
    output_arg = Path(sys.argv[2])
    output = output_arg.absolute()
    if output != output.resolve() or output.is_relative_to(root):
        raise ValueError("Outputs must be external and have no symlink components")
    output.mkdir(exist_ok=False)
    # Include all published source/fixtures and new lane files, never runtimes.
    names = source_names(root)
    start = source_state(root, names)
    generator = Path(__file__).resolve()
    generator_hash = digest(generator)
    entry = root / "docs/admin/implementation/batch10-imf-evidence/pytest_entry.py"
    command = [
        sys.executable,
        "-B",
        str(entry),
        "-p",
        "no:cacheprovider",
        "-v",
        "-ra",
        "--junitxml=" + str(output / "cases.xml"),
        "--basetemp=" + str(output / "tmp"),
        *sys.argv[3:],
    ]
    env = {
        "PATH": os.defpath,
        "PYTHONPATH": str(root / "backend"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHON_DOTENV_DISABLED": "1",
        "DATABASE_URL": "sqlite:///" + str(output / "batch10-imf-import.sqlite"),
        "REDIS_URL": "redis://127.0.0.1:55521/15",
        "ENVIRONMENT": "test",
        "SECRET_BACKEND": "env",
        "SECRET_KEY": "batch10-imf-inert-fixture-key",
        "AUTO_SEEDER_ENABLED": "false",
        "AUTO_WARMUP_ENABLED": "false",
        "PARLIAMENT_PIPELINE_ENABLED": "0",
        "PARLIAMENT_RECONCILE_ENABLED": "0",
        "CACHE_VERSION": "batch10-imf-" + start["head"],
        "AWS_EC2_METADATA_DISABLED": "true",
        "TMPDIR": str(output),
    }
    began = datetime.now(timezone.utc).isoformat()
    with (output / "raw.log").open("x") as log:
        try:
            child = subprocess.run(
                command,
                cwd=root / "backend",
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=180,
            )
            child_exit = child.returncode
        except subprocess.TimeoutExpired:
            child_exit = "timeout"
    end = source_state(root, names)
    receipt = {
        "generated_by": "docs/admin/implementation/batch10-imf-evidence/run_evidence.py",
        "generator_sha256": generator_hash,
        "entry_sha256": digest(entry),
        "started_at": began,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "runtime": sys.version,
        "platform": platform.platform(),
        "checkout": str(root),
        "command": command,
        "environment": env,
        "start": start,
        "end": end,
        "child_exit": child_exit,
        "source_stable": start == end and generator_hash == digest(generator),
        "outputs": {p.name: digest(p) for p in output.iterdir() if p.is_file()},
    }
    receipt["verification_exit"] = (
        0 if receipt["source_stable"] and child_exit == 0 else 1
    )
    path = output / "receipt.json"
    with path.open("x") as stream:
        json.dump(receipt, stream, indent=2)
    readback = json.loads(path.read_text())
    if readback != receipt:
        raise RuntimeError("Receipt readback differs")
    print(
        json.dumps(
            {
                "receipt": str(path),
                "child_exit": child_exit,
                "source_stable": receipt["source_stable"],
            }
        )
    )
    print((output / "raw.log").read_text()[-3500:])
    return receipt["verification_exit"]


if __name__ == "__main__":
    raise SystemExit(main())
