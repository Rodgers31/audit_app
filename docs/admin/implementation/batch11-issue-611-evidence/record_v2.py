"""Portable owned-cohort recorder; fresh outputs never belong in any checkout."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "PYTHON_DOTENV_DISABLED": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
    "DATABASE_URL": "postgresql+psycopg2://inert:inert@127.0.0.1:55534/issue611",
    "SUPABASE_URL": "http://127.0.0.1:18034",
    "SUPABASE_SERVICE_ROLE_KEY": "inert",
    "SUPABASE_JWT_SECRET": "inert",
    "ISSUE611_OWNED_POSTGRES": "1",
    "AUTO_SEEDER_ENABLED": "false",
    "AUTO_WARMUP_ENABLED": "false",
    "ENABLE_ETL_SCHEDULER": "false",
}
def environment(port):
    if type(port) is not int or port not in (55534, 55545):
        raise ValueError("Explicit issue611 owned PostgreSQL port required")
    return {**ENV, "SUPABASE_URL": f"http://127.0.0.1:{18045 if port == 55545 else 18034}",
            "DATABASE_URL": f"postgresql+psycopg2://inert:inert@127.0.0.1:{port}/issue611",
            "ISSUE611_PG_PORT": str(port)}


PROBE = "import json,sys,sqlalchemy,fastapi;print(json.dumps({'python':sys.version,'sqlalchemy':sqlalchemy.__version__,'fastapi':fastapi.__version__}))"
STATES = ("passed", "failure", "error", "skipped")


def git(*args):
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, timeout=10, env={"PATH": "/usr/bin:/bin", "HOME": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    ).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory():
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            timeout=10,
            env={"PATH": "/usr/bin:/bin", "HOME": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"},
        )
        .decode()
        .split("\0")
    )
    files = {}
    for name in sorted(set(paths)):
        if not name:
            continue
        path = ROOT / name
        if path.resolve() != path or path.is_symlink() or not path.is_file():
            raise ValueError("Ordinary source files inside the checkout required")
        files[name] = digest(path)
    return files


def output_path(path, fresh=False):
    """Recheck actual Git metadata and every registered source checkout each time."""
    absolute = path.absolute()
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir"))
    worktrees = (
        subprocess.check_output(
            ["git", "worktree", "list", "--porcelain", "-z"], cwd=ROOT, timeout=10,
            env={"PATH": "/usr/bin:/bin", "HOME": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"},
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
    selected = command[6:-4]
    if not selected or any(
        not t.startswith("tests/") or not t.endswith(".py") or ".." in Path(t).parts
        for t in selected
    ):
        raise ValueError("Explicit backend test files required")
    return [t[:-3].replace("/", ".") for t in selected]


def counts(cases):
    return {s: sum(c["state"] == s for c in cases) for s in STATES}


def unexpected_passes(stdout):
    """JUnit loses nonstrict XPASS outcomes; retain actual verbose pytest evidence."""
    if type(stdout) is not bytes:
        raise ValueError("Actual captured pytest stdout bytes required")
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", stdout.decode("utf-8", errors="replace"))
    status = re.compile(r"^(?:tests/[^\r\n]*\.py::[^\r\n]*[ \t]+)?XPASS(?:[ \t]+\([^\r\n]*\))?[ \t]*$")
    summary = re.compile(r"^=+[^\r\n]*\b[1-9][0-9]* xpassed\b[^\r\n]*=+$")
    return [line for line in text.splitlines() if status.fullmatch(line) or summary.fullmatch(line)]


def group_alive(group):
    try:
        os.killpg(group, 0)
        return True
    except ProcessLookupError:
        return False


def cleanup_group(group, prior_signals=()):
    """Boundedly close only the isolated group this recorder launched."""
    survived = group_alive(group)
    signals = list(prior_signals)
    for action, deadline in ((signal.SIGTERM, 1), (signal.SIGKILL, 3)):
        if not group_alive(group):
            break
        try:
            os.killpg(group, action)
            signals.append(int(action))
        except ProcessLookupError:
            break
        until = time.monotonic() + deadline
        while group_alive(group) and time.monotonic() < until:
            time.sleep(0.025)
    return {"id": group, "survived_parent": survived, "signals": signals,
            "absent": not group_alive(group)}


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
    parser.add_argument("--port", type=int, choices=(55534, 55545), default=55534)
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
    selected_env = environment(args.port)
    env = {**selected_env, "PYTHONPATH": str(ROOT / "backend")}
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
        f"--basetemp={out / 'tmp'}",
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
            *command[1:-2],
            "--basetemp=<external>/tmp",
            "--junitxml=<external>/tests.xml",
        ],
        "env": selected_env,
    }
    destination.check()
    sent_signals = []
    try:
        child = subprocess.Popen(
            command, cwd=ROOT / "backend", env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
        )
        stdout, stderr = child.communicate(timeout=180)
        code = child.returncode
    except subprocess.TimeoutExpired:
        # Terminate only the process group this recorder launched. A partial
        # JUnit inventory never becomes acceptance after an interrupted run.
        os.killpg(child.pid, signal.SIGTERM)
        sent_signals.append(int(signal.SIGTERM))
        try:
            stdout, stderr = child.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            sent_signals.append(int(signal.SIGKILL))
            stdout, stderr = child.communicate(timeout=10)
        code = None
    lifecycle = cleanup_group(child.pid, sent_signals)
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
        process_group=lifecycle,
        unexpected_passes=unexpected_passes(stdout),
    )
    destination.write(
        "execution.json", (json.dumps(execution, indent=2) + "\n").encode()
    )
    identities = [c["id"] for c in cases]
    accepted = (
        code == 0
        and execution["source_unchanged"]
        and lifecycle["absent"]
        and not lifecycle["survived_parent"]
        and not execution["unexpected_passes"]
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
