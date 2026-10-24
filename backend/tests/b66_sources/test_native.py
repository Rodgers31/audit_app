"""Real native CLI and durable exclusion, with only source transport injected."""
from contextlib import contextmanager
import os
from pathlib import Path
import signal
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import text

from test_b17_opendata_native import opendata_pg, query, wait_for, post, receipt, AUTH
from seeding.domains.opendata import source, writer
from seeding.config import SeedingSettings
from seeding.domains import opendata
from seeding.types import DomainRunContext
from b66_sources.pg_plugin import command_environment, shared

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def opendata_url(tmp_path_factory):
    with shared(tmp_path_factory.mktemp('b66-sources-resources')) as url:
        yield url


@contextmanager
def process(tmp_path,url,module='seeding.cli', *args):
    env = command_environment(url)
    env.update({'PYTHONPATH': os.pathsep.join([str(BACKEND/'tests/b66_sources/child'),str(BACKEND/'tests'),str(BACKEND)]),
        'B66_SOURCE_CHILD':'true', 'SEED_OPENDATA_INGESTION_ENABLED':'true', 'SEED_KNBS_RELEASE_DISCOVERY_ENABLED':'true',
        'ADMIN_ETL_DISPATCH_ENABLED':'true','ADMIN_ETL_DISPATCH_SOURCES':'opendata',
        'SUPABASE_URL':'https://owned.invalid','SUPABASE_KEY':'inert','SUPABASE_JWT_SECRET':'inert-only',
        'SEED_STORAGE_PATH':str(tmp_path/'storage'), 'SEED_CACHE_PATH':str(tmp_path/'cache')})
    path = tmp_path/(uuid4().hex+'.log')
    if module == 'seeding.cli' and not args: args = ('seed','--domain','opendata','--no-dry-run')
    with path.open('xb') as log:
        child = subprocess.Popen([sys.executable,'-m',module,*args],cwd=BACKEND,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try: yield child,path
        finally:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGINT)
                try: child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid,signal.SIGKILL); child.wait(timeout=5)
            assert child.poll() is not None


@pytest.mark.parametrize('mode,status,created',[('normal','COMPLETED',1),('candidate','COMPLETED_WITH_ERRORS',0),('failure','FAILED',0),('partial','FAILED',0)])
def test_real_cli_discovery_terminal_truth_and_atomicity(opendata_pg,tmp_path,mode,status,created):
    _,_,engine,url = opendata_pg
    with engine.begin() as db: db.execute(text('UPDATE batch11_control SET mode=:m'), {'m':mode})
    with process(tmp_path,url) as (child,log):
        assert child.wait(timeout=20) == (0 if mode in ('normal','candidate') else 1), log.read_text()
    jobs = query(engine,'SELECT id,status::text,items_created,metadata,errors FROM ingestion_jobs')
    assert len(jobs) == 1 and jobs[0]['status'] == status
    assert len(query(engine,'SELECT 1 FROM source_documents')) == len(query(engine,'SELECT 1 FROM extractions')) == created
    claims = query(engine,'SELECT id,entered_at,returned_at,released_at FROM seeding_domain_claims')
    assert len(claims) == 1 and all(claims[0][f] for f in ('entered_at','returned_at','released_at'))
    assert jobs[0]['metadata']['seeding_claim_id'] == str(claims[0]['id'])
    if mode == 'normal':
        state = jobs[0]['metadata']['release_discovery']
        assert state['last_recorded_edition']['source_document_id'] == query(engine,'SELECT id FROM source_documents')[0]['id']
    if mode == 'candidate':
        state = jobs[0]['metadata']['release_discovery']
        assert state['status'] == 'quarantined_review_candidate' and state['public_qualification'] == 'not_granted'
        assert jobs[0]['errors']
        # Existing CLI returns zero for completed-with-errors; the real workflow
        # hollow-run gate must reject refused source mode.
        from models import IngestionJob
        from seeding.staleness import hollow_run_findings
        with opendata_pg[1]() as db:
            assert any(f.level == 'FAIL' for f in hollow_run_findings(db.query(IngestionJob).all()))
    if mode == 'failure': assert 'KNBS retry/backoff exhausted' in log.read_text()
    if mode == 'partial': assert 'Owned partial persistence failure' in log.read_text()
    assert not query(engine,'SELECT 1 FROM budget_lines')


def test_nochange_replay_and_new_candidate_preserve_accepted_records(opendata_pg,tmp_path):
    _,_,engine,url = opendata_pg
    for _ in range(2):
        with process(tmp_path,url) as (child,log): assert child.wait(timeout=20) == 0, log.read_text()
    original = query(engine,'SELECT id,md5,metadata,fetch_date FROM source_documents')
    extraction = query(engine,'SELECT id,extracted_json,created_at FROM extractions')
    jobs = query(engine,'SELECT metadata FROM ingestion_jobs ORDER BY id')
    assert [j['metadata']['unchanged'] for j in jobs] == [0,1]
    with engine.begin() as db: db.execute(text("UPDATE batch11_control SET mode='candidate'"))
    with process(tmp_path,url) as (child,log): assert child.wait(timeout=20) == 0, log.read_text()
    state = query(engine,'SELECT metadata FROM ingestion_jobs ORDER BY id DESC LIMIT 1')[0]['metadata']['release_discovery']
    assert state['last_recorded_edition']['source_document_id'] == original[0]['id']
    assert query(engine,'SELECT id,md5,metadata,fetch_date FROM source_documents') == original
    assert query(engine,'SELECT id,extracted_json,created_at FROM extractions') == extraction


def test_direct_handler_without_owner_refuses_before_network(opendata_pg,monkeypatch):
    _,factory,engine,_ = opendata_pg
    from seeding.domains.opendata import discovery
    monkeypatch.setattr(discovery,'discover',lambda *a: pytest.fail('No owner reached transport'))
    with factory.begin() as db, pytest.raises(source.OpenDataSourceRefused,match='owned native'):
        opendata.run(db,SeedingSettings(_env_file=None,opendata_ingestion_enabled=True,knbs_release_discovery_enabled=True),DomainRunContext(None,False))
    assert not query(engine,'SELECT 1 FROM source_documents')


@pytest.mark.parametrize('stage,stop_signal', [('before',signal.SIGKILL),('after',signal.SIGKILL),('before',signal.SIGINT)], ids=['crash-before','crash-after','cancel-before'])
def test_crash_restart_preserves_retained_owner_and_blocks_successor(opendata_pg,tmp_path,stage,stop_signal):
    _,_,engine,url = opendata_pg
    with engine.begin() as db: db.execute(text("UPDATE batch11_control SET mode=:stage"), {"stage":stage})
    with process(tmp_path,url) as (child,log):
        wait_for(lambda:query(engine,'SELECT stage FROM batch11_markers WHERE stage=:s', {"s":"discovery" if stage == "before" else "after"}),bool)
        os.killpg(child.pid,stop_signal); assert child.wait(timeout=10) == -stop_signal
    retained = query(engine,'SELECT id,entered_at,returned_at,released_at FROM seeding_domain_claims')
    assert len(retained) == 1 and retained[0]['entered_at'] and retained[0]['returned_at'] is None and retained[0]['released_at'] is None
    with engine.begin() as db: db.execute(text("UPDATE batch11_control SET mode='normal'"))
    with process(tmp_path,url) as (child,log):
        assert child.wait(timeout=15) == 1 and 'Domain ownership unavailable' in log.read_text(), log.read_text()
    assert query(engine,'SELECT id,entered_at,returned_at,released_at FROM seeding_domain_claims') == retained
    assert len(query(engine,'SELECT 1 FROM extractions')) == (1 if stage == 'after' else 0)


def test_concurrent_cli_cannot_duplicate_discovery(opendata_pg,tmp_path):
    _,_,engine,url = opendata_pg
    with engine.begin() as db: db.execute(text("UPDATE batch11_control SET mode='before'"))
    with process(tmp_path,url) as (first,log):
        wait_for(lambda:query(engine,'SELECT stage FROM batch11_markers'),bool)
        with process(tmp_path,url) as (second,second_log):
            assert second.wait(timeout=15) == 1 and 'Domain ownership unavailable' in second_log.read_text()
        with engine.begin() as db: db.execute(text("UPDATE batch11_control SET mode='normal'"))
        assert first.wait(timeout=15) == 0, log.read_text()
    assert len(query(engine,'SELECT 1 FROM extractions')) == 1
    assert len(query(engine,'SELECT 1 FROM batch11_markers')) == 1


def test_dedicated_job_receipt_candidate_is_not_success_and_duplicate_is_replayed(opendata_pg,tmp_path):
    client,_,engine,url = opendata_pg
    with engine.begin() as db: db.execute(text("UPDATE batch11_control SET mode='candidate'"))
    with process(tmp_path,url,'admin_etl_dispatch_worker'):
        cap = wait_for(lambda:client.get('/api/v1/admin/etl/dispatch',headers=AUTH).json(),lambda v:v['available'])
        key = str(uuid4()); accepted = post(client,cap['generation'],key=key)
        assert accepted.status_code == 202
        identity = accepted.json()['command']['id']
        final = wait_for(lambda:receipt(client,identity),lambda v:v['status'] in ('failed','completed'))
        assert final['status'] == 'failed' and final['job_id']
        assert post(client,cap['generation'],key=key).json()['replayed'] is True
        job = query(engine,'SELECT status::text,metadata FROM ingestion_jobs WHERE id=:id',{'id':final['job_id']})[0]
        assert job['status'] == 'COMPLETED_WITH_ERRORS'
        assert job['metadata']['release_discovery']['status'] == 'quarantined_review_candidate'
        assert not query(engine,'SELECT 1 FROM extractions')


def test_actual_discovery_preview_has_receipt_without_extraction(opendata_pg,tmp_path):
    _,_,engine,url = opendata_pg
    with process(tmp_path,url,'seeding.cli','seed','--domain','opendata','--dry-run') as (child,log):
        assert child.wait(timeout=20) == 0, log.read_text()
    job = query(engine,'SELECT dry_run,status::text,metadata FROM ingestion_jobs')[0]
    assert job['dry_run'] is True and job['status'] == 'COMPLETED'
    assert job['metadata']['release_discovery']['status'] == 'pinned_contract_eligible'
    assert job['metadata']['extraction_status'] == 'pinned_preview'
    assert not query(engine,'SELECT 1 FROM extractions')
    assert not query(engine,'SELECT 1 FROM source_documents')
