"""Publish a fresh external execution packet using the preserved recorder."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

prior_bytecode = sys.dont_write_bytecode
try:
    sys.dont_write_bytecode = True
    from verify import external, inventory, sha, validate
finally:
    sys.dont_write_bytecode = prior_bytecode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("tests", nargs="+")
    args = parser.parse_args()
    root, out = args.root.resolve(), args.out.absolute()
    if out.exists() or out.is_symlink() or out.parent.resolve() != out.parent or ".." in out.parts or root == out or root in out.parents:
        raise ValueError("Fresh external nonsymlink output directory required")
    # Only relative backend test selections are admitted, never a replacement
    # runner or arbitrary publisher command. The actual pytest process executes.
    if any(not t.startswith("tests/") or ".." in Path(t).parts or not (root / "backend" / t).is_file() for t in args.tests):
        raise ValueError("Actual backend test files required")
    out.mkdir()
    command = [sys.executable, str(root / "docs/admin/implementation/batch10-readiness-evidence/record.py"),
        "--root", str(root), "--output", str(out / "receipt.json"), "--timeout", str(args.timeout),
        "--", sys.executable, "-m", "pytest", *args.tests, "-vv", "-s", "--junitxml=" + str(out / "results.xml"),
        "--basetemp=" + str(out / "tmp"), "-o", "cache_dir=" + str(out / "pytest-cache")]
    env = {k: os.environ[k] for k in ("PATH", "DATABASE_URL", "JWT_SECRET_KEY", "PYTHONPATH") if k in os.environ}
    env.update(PYTHON_DOTENV_DISABLED="1", PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(command, env=env, timeout=args.timeout + 30, check=False)
    if result.returncode:
        raise RuntimeError("Recorded execution failed; original outputs preserved")
    packet = dict(schema="batch11-603-v1", generated_by="docs/admin/implementation/batch11-issue-603-evidence/publish.py",
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        portable_command=["<python>", "-m", "pytest", *args.tests, "-vv", "-s", "--junitxml=<output>/results.xml"],
        files={name: sha(external(out / name, root)) for name in ("receipt.json", "receipt.txt", "results.xml")},
        testcases=inventory(out / "results.xml"))
    index = out / "INDEX.json"
    with index.open("x") as stream:
        json.dump(packet, stream, indent=2)
    if json.loads(index.read_text()) != packet:
        raise RuntimeError("Packet readback mismatch")
    print(json.dumps(validate(root, index)))


if __name__ == "__main__":
    main()
