"""One slow host must produce a timeout line, not cancel the health check.

WHAT HAPPENED
-------------
Run 36211613362, 2026-09-26. The "Data Source Health Check" job printed five
``[OK]`` lines, the last ``COB National Reports (200)`` at 02:25:22Z, then
nothing until ``##[error]The operation was canceled.`` at 02:30:15Z — the
job's ``timeout-minutes: 5``. The next source is ``OAG WP REST API``.

Its request timeout did fire; it just fired too many times. The probe was
``curl --max-time 60 --retry 2 --retry-delay 3``, and curl retries a
``--max-time`` timeout, so one call could last 3x60+2x3 = 186s. A timeout is
code ``000``, which is transient, so the source was then re-probed with a
browser UA for up to another 186s: 372s for ONE source, against a 300s job.
(The same flags also scored a host that sent ``200`` headers and then stalled
the body as ``[OK]``: curl exits 28 but ``-w %{http_code}`` still says 200.)

A cancelled job writes no outputs, so ``has_failures`` was ``''``: both
health-check issue steps were skipped, and the pipeline-failure issue that
night (#229) said "**Health Check:** ✅ All sources reachable".

WHAT THESE TESTS DO
-------------------
They pull the real ``Check data source URLs`` step out of
``.github/workflows/seed.yml`` and RUN it with ``bash -e`` (what Actions
uses), with its SOURCES list pointed at a local server that can hang, stall
mid-body, 404, or WAF-block a non-browser UA. The budgets are shrunk through
the step's own ``HC_*`` env overrides; the subprocess timeout plays the part
of ``timeout-minutes``. The failure-issue step is run under node with a stub
``github`` client.

*Seen to fail against the pre-fix step: the hung-host run is killed by the
subprocess timeout with no summary line and an empty GITHUB_OUTPUT.*
"""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "seed.yml"
DOC = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _step(job: str, name: str) -> dict:
    for step in DOC["jobs"][job]["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(
        f"step {name!r} not found in job {job!r} — this test would otherwise "
        "pass vacuously against a workflow that no longer has it"
    )


HEALTHCHECK = _step("healthcheck", "Check data source URLs")["run"]
assert "${{" not in HEALTHCHECK, (
    "the health-check step now carries a GitHub expression; it is substituted "
    "before the shell sees it, so running the raw text would test the wrong string"
)
SOURCES_BLOCK = re.compile(r"^\s*SOURCES=\(\n.*?^\s*\)\n", re.S | re.M)
assert SOURCES_BLOCK.search(HEALTHCHECK), "could not find SOURCES=( ... ) to redirect"

#: Stand-ins for timeout-minutes. Generous against the shrunk budgets below
#: (the fixed step finishes in ~budget seconds); the pre-fix step needs 372s
#: per hung source and is killed here.
KILL_AFTER = 30

FAST = {
    "HC_ATTEMPT_MAX_TIME": "2",
    "HC_SOURCE_BUDGET": "3",
    "HC_JOB_BUDGET": "20",
    "HC_RETRY_DELAY": "1",
}


# ── A local host that misbehaves on request ───────────────────────────────


class _Handler(BaseHTTPRequestHandler):
    stop: threading.Event

    def log_message(self, *args):  # keep pytest output clean
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/hang":
            # Accept, read the request, never answer.
            self.stop.wait(600)
            return
        if path == "/trickle":
            # Answer 200 at once, then stall the body.
            self.send_response(200)
            self.send_header("Content-Length", "100000")
            self.end_headers()
            try:
                while not self.stop.wait(0.5):
                    self.wfile.write(b"x")
                    self.wfile.flush()
            except OSError:
                pass
            return
        if path == "/waf":
            ua = self.headers.get("User-Agent", "")
            code = 200 if ua.startswith("Mozilla/") else 403
        elif path == "/gone":
            code = 404
        else:
            code = 200
        self.send_response(code)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")


@pytest.fixture
def host():
    stop = threading.Event()
    handler = type("H", (_Handler,), {"stop": stop})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    stop.set()
    server.shutdown()
    server.server_close()


def _run(tmp_path: Path, sources: list[str], env: dict | None = None):
    """Run the real step against ``sources``; return (stdout, outputs, secs)."""
    block = "          SOURCES=(\n" + "".join(f'            "{s}"\n' for s in sources) + "          )\n"
    script = SOURCES_BLOCK.sub(lambda _: block, HEALTHCHECK, count=1)
    out_file = tmp_path / "github_output"
    out_file.write_text("")
    run_env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "GITHUB_OUTPUT": str(out_file),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "step_summary"),
        **FAST,
        **(env or {}),
    }
    start = time.monotonic()
    killed = None
    try:
        proc = subprocess.run(
            ["bash", "-e", "-c", script],
            env=run_env,
            capture_output=True,
            text=True,
            timeout=KILL_AFTER,
        )
    except subprocess.TimeoutExpired as exc:
        killed = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
    if killed is not None:
        pytest.fail(
            f"the health check was still running after {KILL_AFTER}s — the "
            f"job would be cancelled with no outputs. GITHUB_OUTPUT="
            f"{out_file.read_text()!r}. Log so far:\n{killed}"
        )
    secs = time.monotonic() - start
    assert proc.returncode == 0, f"the step must always exit 0:\n{proc.stdout}\n{proc.stderr}"
    return proc.stdout, _outputs(out_file.read_text()), secs


def _outputs(text: str) -> dict:
    """Parse GITHUB_OUTPUT: ``k=v`` lines and ``k<<MARK ... MARK`` blocks."""
    out, lines, i = {}, text.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        if "<<" in line and "=" not in line.split("<<")[0]:
            key, mark = line.split("<<", 1)
            j = lines.index(mark, i + 1)
            out[key] = "\n".join(lines[i + 1 : j])
            i = j + 1
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            out[key] = val
        i += 1
    return out


# ── The night of 2026-09-26 ───────────────────────────────────────────────


def test_a_hung_host_is_reported_as_a_timeout_and_the_next_source_still_runs(tmp_path, host):
    stdout, outputs, secs = _run(
        tmp_path,
        [
            f"Before|{host}/ok|false",
            f"Hung Host|{host}/hang|true",
            f"After|{host}/ok|true",
        ],
    )
    assert "[OK]   Before (200)" in stdout
    assert re.search(r"\[WARNING\] Hung Host → timed out after \d+s", stdout), stdout
    assert "[OK]   After (200)" in stdout, "the source after the hung host was never probed"
    assert "Total: 3 | OK: 2 | Critical Failures: 0 | Warnings: 1 | Not probed: 0" in stdout
    # A timeout is transient: named, but not a CRITICAL page.
    assert outputs.get("has_failures") == "false"
    assert outputs.get("unprobed") == "0"
    assert f"WARNING|Hung Host|{host}/hang|timeout" in outputs.get("report", "")
    # Both UAs and every retry are charged to one source budget (3s here).
    assert secs < int(FAST["HC_SOURCE_BUDGET"]) + 5, f"one hung source took {secs:.1f}s"


def test_a_stalled_body_after_200_headers_is_a_timeout_not_ok(tmp_path, host):
    """curl exits 28 with -w %{http_code} = 200; the old probe scored that [OK]."""
    stdout, outputs, _ = _run(tmp_path, [f"Stalled Body|{host}/trickle|true"])
    assert "[OK]" not in stdout, stdout
    assert re.search(r"\[WARNING\] Stalled Body → timed out after \d+s", stdout), stdout
    assert f"WARNING|Stalled Body|{host}/trickle|timeout" in outputs["report"]


def test_when_the_job_budget_runs_out_the_rest_are_named_and_outputs_still_written(tmp_path, host):
    stdout, outputs, secs = _run(
        tmp_path,
        [f"Hung {n}|{host}/hang|true" for n in range(1, 6)] + [f"Last|{host}/ok|true"],
        env={"HC_JOB_BUDGET": "5"},
    )
    not_probed = re.findall(r"\[WARNING\] (.+?) → not probed: the 5s health-check budget ran out", stdout)
    assert not_probed and not_probed[-1] == "Last", stdout
    assert outputs.get("unprobed") == str(len(not_probed)), outputs
    assert int(outputs["unprobed"]) >= 3
    assert outputs.get("has_failures") == "false"
    assert "Health Check Summary" in stdout
    assert secs < 5 + 5, f"a 5s job budget took {secs:.1f}s"


# ── What the fix must not break ───────────────────────────────────────────


def test_healthy_sources_are_ok_and_fast(tmp_path, host):
    stdout, outputs, secs = _run(tmp_path, [f"S{n}|{host}/ok|true" for n in range(4)])
    assert stdout.count("[OK]") == 4, stdout
    assert outputs["has_failures"] == "false" and outputs["unprobed"] == "0"
    assert secs < 5


def test_a_gone_critical_url_still_pages(tmp_path, host):
    stdout, outputs, _ = _run(tmp_path, [f"Moved|{host}/gone|true"])
    assert f"[CRITICAL] Moved → HTTP 404 ({host}/gone)" in stdout, stdout
    assert outputs["has_failures"] == "true"


def test_a_refused_connection_is_transient_not_a_timeout(tmp_path):
    import socket

    with socket.socket() as s:  # a port nothing listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    stdout, outputs, secs = _run(tmp_path, [f"Down|http://127.0.0.1:{port}/|true"])
    assert "[WARNING] Down → HTTP 000 (transient/blocked)" in stdout, stdout
    assert outputs["has_failures"] == "false"
    assert secs < int(FAST["HC_SOURCE_BUDGET"]) + 5


def test_a_ua_block_is_still_retried_with_the_browser_ua(tmp_path, host):
    stdout, _, _ = _run(tmp_path, [f"WAF|{host}/waf|true"])
    assert "[OK]   WAF (200)" in stdout, stdout


def test_the_default_budgets_fit_inside_the_job_timeout():
    """Text check on the numbers, since the runs above use shrunk ones."""
    default = lambda name: int(re.search(rf"{name}=\$\{{{name}:-(\d+)\}}", HEALTHCHECK).group(1))
    job_cap = DOC["jobs"]["healthcheck"]["timeout-minutes"] * 60
    assert default("HC_JOB_BUDGET") + 30 <= job_cap
    assert default("HC_SOURCE_BUDGET") >= default("HC_ATTEMPT_MAX_TIME")
    # COB's HTML listings legitimately take 30-50s; one attempt must allow it.
    assert default("HC_ATTEMPT_MAX_TIME") >= 50


# ── The pipeline-failure issue must not vouch for a check that never ran ──

ISSUE_STEP = _step("notify", "Create issue on seeding/validation failure")


def _issue_body(**env) -> str:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node is required to run the github-script step (it is on ubuntu-latest)")
    script = ISSUE_STEP["with"]["script"]
    assert "${{" not in script, "the issue script splices GitHub expressions again"
    harness = (
        "const github = {rest: {issues: {create: async (a) => { console.log(JSON.stringify(a)); }}}};\n"
        "const context = {repo: {owner: 'o', repo: 'r'}, serverUrl: 'https://github.com', runId: 1, eventName: 'schedule'};\n"
        "(async () => {\n" + script + "\n})().catch((e) => { console.error(e); process.exit(1); });\n"
    )
    base = {"PIPELINE_SEED_RESULT": "skipped", "PIPELINE_VALIDATE_RESULT": "failure", "PIPELINE_DOMAIN": "all"}
    proc = subprocess.run([node, "-e", harness], env={**base, **env}, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    import json

    return json.loads(proc.stdout.strip().splitlines()[-1])["body"]


def _health_line(body: str) -> str:
    return next(line for line in body.split("\n") if line.startswith("**Health Check:**"))


def test_the_issue_step_takes_its_inputs_from_the_job_results():
    env = ISSUE_STEP["env"]
    assert env["HEALTHCHECK_RESULT"] == "${{ needs.healthcheck.result }}"
    assert env["HEALTHCHECK_HAS_FAILURES"] == "${{ needs.healthcheck.outputs.has_failures }}"
    assert env["HEALTHCHECK_UNPROBED"] == "${{ needs.healthcheck.outputs.unprobed }}"


def test_a_cancelled_health_check_is_not_reported_as_all_reachable():
    """Run 36211613362: result=cancelled, outputs empty. Issue #229 said ✅."""
    line = _health_line(
        _issue_body(HEALTHCHECK_RESULT="cancelled", HEALTHCHECK_HAS_FAILURES="", HEALTHCHECK_UNPROBED="")
    )
    assert "did not finish (cancelled)" in line, line
    assert "✅" not in line


def test_a_partial_health_check_says_so():
    line = _health_line(
        _issue_body(HEALTHCHECK_RESULT="success", HEALTHCHECK_HAS_FAILURES="false", HEALTHCHECK_UNPROBED="3")
    )
    assert "3 source(s) not probed" in line and "✅" not in line, line


def test_a_complete_clean_health_check_is_still_green():
    line = _health_line(
        _issue_body(HEALTHCHECK_RESULT="success", HEALTHCHECK_HAS_FAILURES="false", HEALTHCHECK_UNPROBED="0")
    )
    assert line.startswith("**Health Check:** ✅"), line


def test_auto_close_needs_every_source_probed():
    cond = _step("notify", "Auto-close resolved health-check issues")["if"]
    assert "needs.healthcheck.outputs.unprobed == '0'" in cond, cond
