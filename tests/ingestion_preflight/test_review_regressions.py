"""B67 review reproductions; actual code paths, inert credentials and owned PG only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import pytest
import yaml

from conftest import ROOT, tool, instrument_worker


def workflow():
    return yaml.load(
        (ROOT / ".github/workflows/ingestion-preflight.yml").read_bytes(),
        Loader=yaml.BaseLoader,
    )


def test_actual_workflow_admission_never_uses_mutable_python(tmp_path):
    job = workflow()["jobs"]["inspect"]
    command = next(s["run"] for s in job["steps"] if "--admit-only" in s.get("run", ""))
    app = tmp_path / "app/scripts/verification"
    app.mkdir(parents=True)
    for name in (
        "ingestion_preflight.py",
        "ingestion_preflight_worker.py",
        "evaluate_social_operating_budget.py",
        "social_operating_collect.py",
    ):
        shutil.copyfile(ROOT / "scripts/verification" / name, app / name)
    policy = tmp_path / "admission/docs/admin/batch66/preflight-admission.json"
    policy.parent.mkdir(parents=True)
    policy.write_bytes(
        (ROOT / "docs/admin/batch66/preflight-admission.json").read_bytes()
    )
    # Complete but small source corpus, never a repository copy or app startup.
    for name in tool.SOURCE_FILES:
        target = tmp_path / "app" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    subprocess.run(["git", "init", "-q", str(tmp_path / "app")], check=True)
    subprocess.run(["git", "-C", str(tmp_path / "app"), "add", "--", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path / "app"),
            "-c",
            "user.name=Owned Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "owned inert source",
        ],
        check=True,
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "mutable-runtime-used"
    for name in ("python", "python3"):
        binary = bin_dir / name
        binary.write_text('#!/bin/sh\nprintf used > "$B67_RUNTIME_MARKER"\nexit 0\n')
        binary.chmod(0o700)
    r = subprocess.run(
        ["sh", "-ec", command],
        cwd=tmp_path,
        env={
            "PATH": str(bin_dir) + ":/usr/bin:/bin",
            "GITHUB_WORKSPACE": str(tmp_path),
            "PREFLIGHT_PYTHON": sys.executable,
            "B67_RUNTIME_MARKER": str(marker),
        },
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert not marker.exists(), "workflow executed the runner PATH python"
    result = json.loads(r.stdout)
    assert r.returncode == 2 and result["errors"] == ["ADMISSION_DISABLED"]
    assert (
        result["policy_raw_sha256"] == hashlib.sha256(policy.read_bytes()).hexdigest()
    )
    assert result["config_sha256"] == tool.budget.content_hash(
        json.loads(policy.read_bytes())
    )


def test_policy_checkout_is_a_distinct_immutable_review_commit():
    steps = workflow()["jobs"]["inspect"]["steps"]
    checkouts = {
        s["with"]["path"]: s["with"]["ref"]
        for s in steps
        if s.get("uses", "").startswith("actions/checkout@")
    }
    assert (
        checkouts["app"] != checkouts["admission"]
    ), "policy is bundled with its implementation authority"


def test_refusal_binds_attempted_source_and_config(config):
    result = tool.run(config, execute=True, credential="NOT-A-DSN")
    assert result["status"] == "REFUSED"
    assert result["config_sha256"] == tool.budget.content_hash(config)
    assert result["source"]["head"] == config["execution_head"]


def test_idle_session_timeout_is_enforced_and_read_back(config, monkeypatch):
    import psycopg2

    connection = psycopg2.connect(
        host="127.0.0.1",
        port=56972,
        dbname="b66_preflight_owned",
        user="b66_preflight_reader",
        password="owned-reader-only",
        options=tool.OPTIONS,
    )
    connection.autocommit = True
    with connection.cursor() as c:
        c.execute("SET idle_session_timeout='0'")
    observed = []
    original = tool.Reads.one

    def capture(self, sql, params=None):
        row = original(self, sql, params)
        if sql == tool.GUARDS_SQL:
            self.cursor.execute("SHOW idle_session_timeout")
            observed.append(self.cursor.fetchone()[0])
        return row

    monkeypatch.setattr(tool.Reads, "one", capture)
    try:
        tool.inspect(connection, config)
        assert observed == ["5s"], "invoked inspector accepted idle_session_timeout=0"
    finally:
        connection.rollback()
        connection.close()


def test_timeout_during_driver_cleanup_cannot_outlive_whole_bound(
    config, credential, monkeypatch
):
    # A fresh private worker is intentionally blocked; no driver callbacks exist
    # in product inputs. Parent must kill/reap within its unchanged outer budget.
    instrument_worker(monkeypatch, "tool.inspect=lambda *_: time.sleep(2)")
    monkeypatch.setattr(tool, "RUN_SECONDS", 0.3)
    start = time.monotonic()
    result = tool.run(config, execute=True, credential=credential)
    assert result["status"] == "REFUSED" and time.monotonic() - start < 0.5
    assert result["worker_cleanup"]["forced"] is True
    assert result["worker_cleanup"]["reaped"] is True


@pytest.mark.parametrize("blocked", ["rollback", "close"])
def test_actual_valid_inspection_cannot_succeed_after_slow_cleanup(
    config, credential, pg, monkeypatch, tmp_path, blocked
):
    marker = tmp_path / "cleanup-entered"
    adapter = f"""connect=psycopg2.connect
class SlowCleanup:
 def __init__(self,inner): object.__setattr__(self,'inner',inner)
 def __getattr__(self,name): return getattr(self.inner,name)
 def __setattr__(self,name,value): setattr(self.inner,name,value)
 def rollback(self):
  if {blocked!r}=='rollback':
   Path({str(marker)!r}).write_text('valid inspection reached rollback')
   time.sleep(2)
  return self.inner.rollback()
 def close(self):
  if {blocked!r}=='close':
   Path({str(marker)!r}).write_text('valid inspection reached close')
   time.sleep(2)
  return self.inner.close()
psycopg2.connect=lambda **kwargs:SlowCleanup(connect(**kwargs))
"""
    instrument_worker(monkeypatch, adapter)
    monkeypatch.setattr(tool, "RUN_SECONDS", 0.6)
    start = time.monotonic()
    result = tool.run(config, execute=True, credential=credential)
    assert (
        marker.exists()
    ), "setup failed: actual inspection never reached the slow cleanup"
    assert result["status"] == "REFUSED" and result["observation"] is None
    assert time.monotonic() - start < 0.85
    assert (
        result["worker_cleanup"]["forced"] is True
        and result["worker_cleanup"]["reaped"] is True
    )
    with pg.cursor() as c:
        c.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE application_name='b66-ingestion-preflight'"
        )
        assert c.fetchone()[0] == 0


def test_successful_worker_must_leave_no_owned_descendant(
    config, credential, monkeypatch, tmp_path
):
    marker = tmp_path / "owned-descendant"
    instrument_worker(
        monkeypatch,
        f"""import subprocess,os
p=subprocess.Popen([sys.executable,'-I','-B','-c','import time;time.sleep(10)'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
Path({str(marker)!r}).write_text(str(p.pid))
""",
    )
    result = None
    try:
        result = tool.run(config, execute=True, credential=credential)
        assert marker.exists(), "setup: descendant never started"
        assert result["status"] == "REFUSED" and result["observation"] is None
        assert result["worker_cleanup"]["forced"] is True
        assert result["worker_cleanup"]["reaped"] is True
        with pytest.raises(ProcessLookupError):
            os.kill(int(marker.read_text()), 0)
    finally:
        if marker.exists():
            pid = int(marker.read_text())
            try:
                if result and os.getpgid(pid) == result["worker_cleanup"]["pid"]:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize(
    "change",
    [
        "r['observation']=None; r['errors']=['THIS-IS-FAILED']",
        "r['errors']=['INSPECTION_FAILED']",
        "r['observation']['checks']={}",
        "r['observation']['checks']['retained_claim']=True",
        "r['observation']['sql_commands']=True",
        "r['observation']['read_requests']=0",
        "r['observation']['rows']=0",
        "r['observation']['rows']=1",
        "r['observation']['decoded_result_bytes']=1",
        "r['observation']['decoded_result_bytes']=65537",
        "r['observation']['server_version_num']=True",
        "r['runtime']['driver']='unknown'",
        "r['runtime']['libpq']=True",
        "r['budgets']['connections']=True",
        "r['binding_errors']=['CONFIG_NOT_OBSERVED']",
        "r['version']=True",
        "r['generated_at']='2000-01-01T00:00:00+00:00'",
        "r['custody_operator_gate']='ACCEPTED'",
        "r['receipt_backend_gate']='OBSERVED'",
        "r['artifact_authentication']='VERIFIED'",
        "r['status']='REFUSED';r['observation']=None;r['errors']=['TOY-SECRET']",
    ],
)
def test_malformed_worker_report_never_becomes_success(
    config, credential, monkeypatch, change
):
    instrument_worker(
        monkeypatch,
        """original_run=tool._connection_run
def altered(*args):
 r=original_run(*args)
 if r['status']!='OBSERVED_READ_CHECKS_ONLY': raise RuntimeError('fixture did not inspect')
 """
        + change
        + "\n return r\ntool._connection_run=altered",
    )
    result = tool.run(config, execute=True, credential=credential)
    assert result["status"] == "REFUSED" and result["observation"] is None
    assert result["errors"] == ["WORKER_REPORT_INVALID"]
    assert "TOY-SECRET" not in json.dumps(result)


def test_impossibly_empty_worker_census_refuses(config, credential, monkeypatch):
    monkeypatch.setattr(tool.worker, "_members", lambda *_: set())
    result = tool.run(config, execute=True, credential=credential)
    assert result["status"] == "REFUSED" and result["observation"] is None
    assert result["worker_cleanup"]["reaped"] is True
