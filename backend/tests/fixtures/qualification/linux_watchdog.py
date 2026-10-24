"""Explicit Linux cohort: real watchdog + child + native CLI + owned PostgreSQL.

Run explicitly inside the cached 512 MiB Linux fixture, sharing only the owned
PostgreSQL network namespace. Not a host or government-source qualification.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
from uuid import UUID
import pytest

from test_b17_opendata_native import opendata_url, opendata_pg, AUTH, wait_for
from test_dispatch_qualification import policy_environment
from test_dispatch_qualification_pg import trigger
from test_dispatch_qualification_watchdog import child_module
from sqlalchemy import select, text
from models import EtlDispatchDomain, EtlDispatchWorker, IngestionJob
import admin_etl_qualification_watchdog as watchdog


def test_forced_descendant_cleanup_is_not_success(child_module, monkeypatch):
    import ctypes, os, signal, time
    assert sys.platform == 'linux'
    libc = ctypes.CDLL(None, use_errno=True)
    prior = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(prior), 0, 0, 0) == 0
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    path, receipt = child_module
    pidfile = path.parent / 'owned-descendant.pid'
    path.write_text('import subprocess,sys\nfrom pathlib import Path\n'
        'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n'
        'Path(' + repr(str(pidfile)) + ').write_text(str(p.pid))\nprint(' + repr(json.dumps(receipt)) + ')\n')
    original = watchdog.group_absent
    def reap_then_observe(pid):
        if pidfile.exists():
            try: os.waitpid(int(pidfile.read_text()), os.WNOHANG)
            except ChildProcessError: pass
        return original(pid)
    actual_killpg = os.killpg
    def signal_owned_and_wait(pid, sig):
        actual_killpg(pid, sig)
        time.sleep(.05)
    monkeypatch.setattr(watchdog, 'group_absent', reap_then_observe)
    monkeypatch.setattr(os, 'killpg', signal_owned_and_wait)
    try:
        result, code = watchdog.supervise()
        assert code == 1 and result['reason'] == 'WORKER_GROUP_RETAINED'
        assert result['reaped'] and result['group_absent']
    finally:
        if pidfile.exists():
            identity = int(pidfile.read_text())
            try: os.kill(identity, signal.SIGKILL)
            except ProcessLookupError: pass
            try: os.waitpid(identity, 0)
            except ChildProcessError: pass
        assert libc.prctl(36, prior.value, 0, 0, 0) == 0


@pytest.mark.parametrize('baseline', [None, 282 * watchdog.MIB])
def test_linux_whole_watchdog_native_dry_run(opendata_pg, policy_environment, monkeypatch, tmp_path, baseline):
    assert sys.platform == 'linux'
    client, factory, engine, url = opendata_pg
    monkeypatch.setenv('DATABASE_URL', url)
    backend = Path(__file__).resolve().parents[3]
    # Instrument only input transport in the owned child. Everything in the
    # accepted worker, native CLI, parser, database writer and watchdog executes.
    shim = tmp_path / 'admin_etl_qualification_worker.py'
    shim.write_text('''import sys, importlib.util
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0, %r)
from seeding.domains.opendata import source
payload=Path(%r).read_bytes()
source.fetch_publication=lambda: (payload,datetime.now(timezone.utc))
spec=importlib.util.spec_from_file_location('owned_worker_under_test',%r)
worker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
raise SystemExit(worker.main())
''' % (str(backend), str(backend / 'tests/fixtures/opendata/Chapter-5-Public-Finance.xlsx'),
       str(backend / 'admin_etl_qualification_worker.py')))
    monkeypatch.setattr(watchdog, '__file__', str(tmp_path / 'watchdog.py'))
    # Approximate the observed live API's shared memory footprint without
    # claiming a production load test. The native worker's kernel limits remain
    # real, and concurrent reads use the actual router and owned database.
    ballast = bytearray(max(0, baseline - watchdog.memory_usage())) if baseline else None
    assert watchdog.memory_usage() < watchdog.ADMISSION_MAX
    def submit():
        cap = wait_for(lambda: client.get('/api/v1/admin/etl/dispatch', headers=AUTH).json(), lambda v: v['available'])
        accepted = trigger(client, UUID(cap['generation']))
        assert accepted.status_code == 202, accepted.text
        assert trigger(client, UUID(cap['generation'])).status_code == 409
        for _ in range(8):
            assert client.get('/api/v1/admin/etl/dispatch', headers=AUTH).status_code == 200
            assert client.get('/api/v1/admin/etl/commands?page=1&page_size=10', headers=AUTH).status_code == 200
        return accepted.json()['command']['id']
    with ThreadPoolExecutor(max_workers=1) as pool:
        accepted = pool.submit(submit)
        result, code = watchdog.supervise()
        command_id = accepted.result(timeout=2)
    print(json.dumps(result, sort_keys=True))
    assert code == 0 and result['status'] == 'completed', result
    assert result['reaped'] and result['group_absent']
    assert result['worker']['command_id'] == command_id
    assert result['sampled_cgroup_peak_bytes'] < watchdog.HOST_MAX - watchdog.RESERVE
    with factory() as db:
        jobs = db.scalars(select(IngestionJob)).all()
        assert len(jobs) == 1 and jobs[0].dry_run is True
        assert (jobs[0].items_processed, jobs[0].items_created, jobs[0].items_updated) == (2125,0,0)
        assert db.get(EtlDispatchWorker,1).ready is False
        assert all(not d.ready and d.claim_token is None and d.command_id is None
                   for d in db.scalars(select(EtlDispatchDomain)))
        for table in ('source_documents','extractions','budget_lines'):
            assert db.scalar(text('SELECT count(*) FROM '+table)) == 0
    assert ballast is None or len(ballast) <= baseline
