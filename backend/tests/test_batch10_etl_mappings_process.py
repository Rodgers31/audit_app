"""Real dedicated supervisor/adapter/native processes with deterministic barriers."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest
from sqlalchemy import text

from test_batch10_etl_mappings import mapping_url, pg, post, AUTH, MAPPINGS

BACKEND = Path(__file__).resolve().parents[1]


def wait_for(read, predicate):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        value = read()
        if predicate(value):
            return value
        time.sleep(.03)
    raise AssertionError("Expected process barrier/receipt not observed")


def start(tmp_path, url, module, *args):
    env = {"PATH": os.environ["PATH"], "DATABASE_URL": url, "PYTHON_DOTENV_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join([str(BACKEND / 'tests/batch10_etl_mappings_fixture'), str(BACKEND / 'tests'), str(BACKEND)]),
        "ADMIN_ETL_DISPATCH_ENABLED": "true", "ADMIN_ETL_DISPATCH_SOURCES": ",".join(MAPPINGS), "BATCH10_MAPPINGS_INERT": "true",
        "SEED_STORAGE_PATH": str(tmp_path / "storage"), "SEED_CACHE_PATH": str(tmp_path / "cache"), "SEED_LOG_PATH": str(tmp_path / 'seed.jsonl')}
    with (tmp_path / (module + '-' + str(time.time_ns()) + '.log')).open('wb') as log:
        return subprocess.Popen([sys.executable, "-m", module, *args], cwd=BACKEND, env=env,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGCONT)
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


@pytest.fixture
def process_pg(pg):
    client, factory, engine = pg
    with engine.begin() as c:
        c.execute(text("CREATE TABLE IF NOT EXISTS batch10_control(domain text primary key,mode text)"))
        c.execute(text("CREATE TABLE IF NOT EXISTS batch10_markers(domain text,stage text,job_id integer)"))
        c.execute(text("TRUNCATE batch10_control,batch10_markers"))
        for domain in MAPPINGS.values():
            c.execute(text("INSERT INTO batch10_control VALUES (:d,'normal')"), {"d": domain})
    yield pg


def ready(client):
    return wait_for(lambda: client.get('/api/v1/admin/etl/dispatch', headers=AUTH).json(), lambda c: c.get('available'))


def receipt(client, identity):
    return client.get('/api/v1/admin/etl/commands/' + identity, headers=AUTH).json()


@pytest.mark.parametrize("source", MAPPINGS)
def test_real_worker_each_mapping_normal_dry_run_and_failure(process_pg, tmp_path, source):
    client, _, engine = process_pg
    worker = start(tmp_path, engine.url.render_as_string(hide_password=False), 'admin_etl_dispatch_worker')
    try:
        capability = ready(client)
        for dry_run in (False, True):
            accepted = post(client, capability['generation'], source, dry_run)
            assert accepted.status_code == 202, accepted.text
            identity = accepted.json()['command']['id']
            final = wait_for(lambda: receipt(client, identity), lambda c: c.get('status') == 'completed')
            with engine.connect() as c:
                assert c.scalar(text('SELECT count(*) FROM batch10_effects')) == 1
                assert c.scalar(text('SELECT domain FROM ingestion_jobs WHERE id=:id'), {'id': final['job_id']}) == MAPPINGS[source]
        with engine.begin() as c:
            c.execute(text("UPDATE batch10_control SET mode='failure' WHERE domain=:d"), {'d': MAPPINGS[source]})
        identity = post(client, capability['generation'], source).json()['command']['id']
        final = wait_for(lambda: receipt(client, identity), lambda c: c.get('status') == 'failed')
        assert final['job_id'] and 'private' not in str(final)
    finally:
        stop(worker)


@pytest.mark.parametrize("source", MAPPINGS)
@pytest.mark.parametrize("phase,effects", [('before',0),('after',1)])
def test_death_retains_exact_domain_and_independent_successor_progresses(process_pg, tmp_path, source, phase, effects):
    client, factory, engine = process_pg
    domain = MAPPINGS[source]
    with engine.begin() as c:
        c.execute(text('UPDATE batch10_control SET mode=:mode WHERE domain=:d'), {'mode':phase,'d':domain})
    worker = start(tmp_path, engine.url.render_as_string(hide_password=False), 'admin_etl_dispatch_worker')
    replacement = native = None
    try:
        capability = ready(client)
        identity = post(client, capability['generation'], source).json()['command']['id']
        def markers():
            with engine.connect() as c:
                return c.scalar(text('SELECT count(*) FROM batch10_markers WHERE stage=:stage'), {'stage': 'entered' if phase=='before' else 'committed'})
        wait_for(markers, lambda n:n==1)
        with engine.connect() as c:
            original = c.execute(text('SELECT id,domain,command_id FROM seeding_domain_claims WHERE released_at IS NULL')).one()
        os.killpg(worker.pid, signal.SIGKILL); worker.wait(timeout=5)
        with engine.begin() as c:
            c.execute(text("UPDATE etl_dispatch_worker SET last_seen_at=clock_timestamp()-interval '2 seconds',expires_at=clock_timestamp()-interval '1 second'"))
        replacement = start(tmp_path, engine.url.render_as_string(hide_password=False), 'admin_etl_dispatch_worker')
        new = wait_for(lambda: ready(client), lambda c:c['generation']!=capability['generation'])
        assert receipt(client, identity)['status']=='interrupted'
        blocked = post(client,new['generation'],source).json()['command']['id']
        native = start(tmp_path, engine.url.render_as_string(hide_password=False),'seeding.cli','seed','--domain',domain,'--no-dry-run')
        assert native.wait(timeout=12)==1
        other_source = 'knbs' if source!='knbs' else 'oag'
        other = post(client,new['generation'],other_source).json()['command']['id']
        wait_for(lambda:receipt(client,other),lambda c:c.get('status')=='completed')
        with engine.connect() as c:
            assert c.scalar(text('SELECT released_at IS NULL FROM seeding_domain_claims WHERE id=:id'), {'id':original.id}) is True
            assert c.scalar(text('SELECT command_id FROM etl_dispatch_domains WHERE domain=:d'), {'d':domain})==original.command_id
            assert c.scalar(text('SELECT count(*) FROM batch10_effects WHERE domain=:d'),{'d':domain})==effects
        assert receipt(client,blocked)['status']=='queued'
    finally:
        for process in (worker,replacement,native):
            if process: stop(process)
