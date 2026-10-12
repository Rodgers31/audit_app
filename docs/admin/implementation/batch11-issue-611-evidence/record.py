"""Portable owned-cohort recorder; fresh outputs never belong in any checkout."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
ENV = {
    "PATH": "/usr/bin:/bin",
    "PYTHON_DOTENV_DISABLED": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
    "DATABASE_URL": "postgresql+psycopg2://inert:inert@127.0.0.1:55534/issue611",
    "SUPABASE_URL": "http://127.0.0.1:18034",
    "SUPABASE_SERVICE_ROLE_KEY": "inert",
    "SUPABASE_JWT_SECRET": "inert",
    "ISSUE611_OWNED_POSTGRES": "1",
}
PROBE = "import json,sys,sqlalchemy,fastapi;print(json.dumps({'python':sys.version,'sqlalchemy':sqlalchemy.__version__,'fastapi':fastapi.__version__}))"
STATES = ("passed", "failure", "error", "skipped")


def git(*args):
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, timeout=10
    ).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory():
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            timeout=10,
        )
        .decode()
        .split("\0")
    )
    return {p: digest(ROOT / p) for p in sorted(set(paths)) if p}


def output_path(path, fresh=False):
    """Recheck actual Git metadata and every registered source checkout each time."""
    absolute = path.absolute()
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir"))
    worktrees = (
        subprocess.check_output(
            ["git", "worktree", "list", "--porcelain", "-z"], cwd=ROOT, timeout=10
        )
        .decode()
        .split("\0")
    )
    protected = [common.resolve(), ROOT]
    protected.extend(
        Path(row[9:]).resolve() for row in worktrees if row.startswith("worktree ")
    )
    if (
        absolute.resolve() != absolute
        or ".git" in absolute.parts
        or any(p == absolute or p in absolute.parents for p in protected)
        or (fresh and absolute.exists())
    ):
        raise ValueError(
            "Fresh external unsymlinked output required; Git metadata and all checkouts excluded"
        )
    return absolute


def junit_cases(path):
    root = ET.parse(path).getroot()
    if root.tag != "testsuites" or any(suite.tag != "testsuite" for suite in root):
        raise ValueError("Expected pytest JUnit suites")
    cases = []
    for suite in root:
        suite_cases = []
        if any(child.tag in {"error", "failure", "testsuite"} for child in suite):
            raise ValueError("Unrepresented JUnit suite outcome")
        for case in suite.findall("testcase"):
            classname, name = case.attrib.get("classname"), case.attrib.get("name")
            if not classname or not name:
                raise ValueError("JUnit case identity missing")
            outcomes = [s for s in STATES[1:] if case.find(s) is not None]
            if len(outcomes) > 1:
                raise ValueError("Contradictory JUnit testcase outcomes")
            suite_cases.append(
                {
                    "id": classname + "::" + name,
                    "state": outcomes[0] if outcomes else "passed",
                }
            )
        expected = {
            "tests": len(suite_cases),
            "failures": sum(c["state"] == "failure" for c in suite_cases),
            "errors": sum(c["state"] == "error" for c in suite_cases),
            "skipped": sum(c["state"] == "skipped" for c in suite_cases),
        }
        for key, value in expected.items():
            if suite.attrib.get(key) != str(value):
                raise ValueError("JUnit summary contradicts actual testcase inventory")
        cases.extend(suite_cases)
    return cases


def selected_modules(command):
    selected = command[6:-3]
    if not selected or any(
        not t.startswith("tests/") or not t.endswith(".py") or ".." in Path(t).parts
        for t in selected
    ):
        raise ValueError("Explicit backend test files required")
    return [t[:-3].replace("/", ".") for t in selected]


def counts(cases):
    return {s: sum(c["state"] == s for c in cases) for s in STATES}


class Destination:
    def __init__(self, path):
        self.path = output_path(path, fresh=True)
        self.path.mkdir(parents=True, exist_ok=False)
        self.identity = (self.path.stat().st_dev, self.path.stat().st_ino)

    def check(self):
        output_path(self.path)
        stat = self.path.stat()
        if (stat.st_dev, stat.st_ino) != self.identity or not self.path.is_dir():
            raise ValueError("Output directory identity changed during execution")

    def write(self, name, data):
        self.check()
        with (self.path / name).open("xb") as stream:
            stream.write(data)
        self.check()

    def read(self, name):
        self.check()
        file = output_path(self.path / name)
        data = file.read_bytes()
        self.check()
        return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("tests", nargs="+")
    args = parser.parse_args()
    if not args.python.is_file() or any(
        not name.startswith("tests/")
        or not name.endswith(".py")
        or ".." in Path(name).parts
        for name in args.tests
    ):
        raise ValueError("Explicit interpreter and backend tests required")
    destination = Destination(args.out)
    out = destination.path
    before, status = inventory(), git("status", "--porcelain=v1")
    env = {**ENV, "PYTHONPATH": str(ROOT / "backend")}
    command = [
        str(args.python),
        "-m",
        "pytest",
        "--confcutdir=tests",
        "-p",
        "no:cacheprovider",
        *args.tests,
        "-v",
        "-s",
        f"--junitxml={out / 'tests.xml'}",
    ]
    metadata = subprocess.run(
        [str(args.python), "-c", PROBE],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )
    destination.write("runtime.stdout.txt", metadata.stdout.encode())
    destination.write("runtime.stderr.txt", metadata.stderr.encode())
    if metadata.returncode != 0:
        raise ValueError("Runtime probe failed; retained setup outputs, no acceptance")
    execution = {
        "generated_by": str(Path(__file__).relative_to(ROOT)),
        "generator_sha256": digest(Path(__file__)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_commit": git("rev-parse", "HEAD"),
        "target_tree": git("rev-parse", "HEAD^{tree}"),
        "source_inventory_sha256": hashlib.sha256(
            json.dumps(before, sort_keys=True).encode()
        ).hexdigest(),
        "status_before": status,
        "runtime": json.loads(metadata.stdout),
        "runtime_probe_command": ["<owned-python>", "-c", PROBE],
        "runtime_probe_exit": metadata.returncode,
        "platform": platform.platform(),
        "command": [
            "<owned-python>",
            *command[1:-1],
            "--junitxml=<external>/tests.xml",
        ],
        "env": ENV,
    }
    destination.check()
    try:
        child = subprocess.run(
            command,
            cwd=ROOT / "backend",
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        stdout, stderr, code = (
            child.stdout.encode(),
            child.stderr.encode(),
            child.returncode,
        )
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, code = exc.stdout or b"", exc.stderr or b"", None
    # A testcase may move/replace the path. Never publish a receipt after that change.
    destination.check()
    destination.write("stdout.txt", stdout)
    destination.write("stderr.txt", stderr)
    cases = junit_cases(out / "tests.xml") if (out / "tests.xml").is_file() else []
    destination.check()
    after_status = git("status", "--porcelain=v1")
    execution.update(
        child_exit=code,
        status_after=after_status,
        source_unchanged=before == inventory() and status == after_status,
    )
    destination.write(
        "execution.json", (json.dumps(execution, indent=2) + "\n").encode()
    )
    identities = [c["id"] for c in cases]
    accepted = (
        code == 0
        and execution["source_unchanged"]
        and bool(cases)
        and len(set(identities)) == len(identities)
        and all(c["state"] == "passed" for c in cases)
    )
    outputs = (
        "stdout.txt",
        "stderr.txt",
        "tests.xml",
        "runtime.stdout.txt",
        "runtime.stderr.txt",
        "execution.json",
    )
    receipt = {
        **execution,
        "source_sha256": before,
        "cases": cases,
        "counts": counts(cases),
        "verification_exit": 0 if accepted else 1,
        "verdict": "PASS" if accepted else "NOT_ACCEPTED",
        "outputs_sha256": {
            name: hashlib.sha256(destination.read(name)).hexdigest()
            for name in outputs
            if (out / name).is_file()
        },
    }
    destination.write("run.json", (json.dumps(receipt, indent=2) + "\n").encode())
    if json.loads(destination.read("run.json")) != receipt:
        raise RuntimeError("Receipt readback mismatch")
    print(
        json.dumps(
            {
                k: receipt[k]
                for k in ("verdict", "child_exit", "counts", "source_unchanged")
            }
        )
    )
    return receipt["verification_exit"]


if __name__ == "__main__":
    sys.exit(main())
