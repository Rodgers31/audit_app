"""Execute the workflow result gate with real PostgreSQL JSONB/enum/timestamps.

Only a separately owned, loopback-only fixture database can opt in. These tests
never discover or use production connection configuration.
"""
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from models import IngestionJob, IngestionStatus
from tests.test_hollow_run_gate import HEALTHY_NIGHT, _write_db, _run_step
from tests.test_refresh_eligibility import audit_fixture
from tests.acceptance_owned_pg import owned_schema


@pytest.fixture
def fixture_db(tmp_path):
    url=os.environ.get('REFRESH_FIXTURE_PG_URL')
    if not url:
        pytest.skip('owned PostgreSQL fixture explicitly required')
    with owned_schema() as (engine, child_url):
        IngestionJob.__table__.create(engine)
        sqlite=create_engine(_write_db(tmp_path,HEALTHY_NIGHT))
        try:
            with Session(sqlite) as source, Session(engine) as target:
                for job in source.scalars(select(IngestionJob)):
                    target.add(IngestionJob(**{c.key:getattr(job,c.key) for c in IngestionJob.__mapper__.column_attrs}))
                target.commit()
            with engine.begin() as connection:
                connection.execute(text("SELECT setval(pg_get_serial_sequence('ingestion_jobs','id'),(SELECT max(id) FROM ingestion_jobs))"))
            yield engine,child_url
        finally:
            sqlite.dispose()
            (tmp_path/'seed_check.sqlite').unlink(missing_ok=True)


def parse_report(result):
    frames=[line.removeprefix('CURRENT_RUN_REPORT_V1 ') for line in result.stdout.splitlines() if line.startswith('CURRENT_RUN_REPORT_V1 ')]
    assert len(frames)==1,result.stdout+result.stderr
    return json.loads(frames[0])


def test_real_pg_retains_eligible_hold_while_actual_gate_remains_red(fixture_db):
    engine,url=fixture_db
    with Session(engine) as session:
        job=session.scalar(select(IngestionJob).where(IngestionJob.domain=='audits'))
        native,_,_=audit_fixture()
        meta=native[0].meta
        meta['execution_plan']=job.meta['execution_plan']
        job.meta=meta; job.status=IngestionStatus(native[0].status); job.errors=native[0].errors
        job.items_processed=job.items_updated=4
        session.commit()
    result=_run_step(url)
    report=parse_report(result)
    assert result.returncode==1,result.stdout+result.stderr
    assert report['classification']=='required_source_incomplete' and report['cache_eligible'] is True
    assert next(j for j in report['jobs'] if j['domain']=='audits')['held_proposals'][0]['document_id']==2392
    assert 'private.invalid' not in result.stdout


@pytest.mark.parametrize('mutation',['duplicate','running','unknown_meta','boolean_counter','arbitrary_error'])
def test_real_pg_invalid_rows_never_admit_refresh(fixture_db,mutation):
    engine,url=fixture_db
    with Session(engine) as session:
        job=session.scalar(select(IngestionJob).where(IngestionJob.domain=='audits'))
        if mutation=='duplicate':
            session.add(IngestionJob(**{c.key:getattr(job,c.key) for c in IngestionJob.__mapper__.column_attrs if c.key!='id'}))
        elif mutation=='running':job.status=IngestionStatus.RUNNING;job.finished_at=None
        elif mutation=='unknown_meta':job.meta=[]
        elif mutation=='boolean_counter':
            # PostgreSQL refuses bool->integer before the gate; keep that refusal
            # explicit, and separately test JSONB booleans in the completion proof.
            meta=dict(job.meta); meta['refresh_completion']=dict(meta['refresh_completion'],accepted_documents=True);job.meta=meta
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(job,'meta')
        else:job.errors=['inert unrelated network/database exception']
        session.commit()
    result=_run_step(url)
    report=parse_report(result)
    assert result.returncode==1,result.stdout+result.stderr
    assert report['cache_eligible'] is False and report['classification']=='unsafe'


def test_workflow_reads_job_times_in_the_postgresql_session_timezone(fixture_db):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy.engine import make_url

    engine, url = fixture_db
    chicago_url = make_url(url).update_query_dict({
        'options': make_url(url).query['options'] + ' -c TimeZone=America/Chicago',
    }).render_as_string(hide_password=False)
    finished = datetime.now(timezone.utc) - timedelta(seconds=2)
    with Session(engine) as db:
        db.execute(text("SET LOCAL TIME ZONE 'America/Chicago'"))
        job = db.scalar(select(IngestionJob).where(IngestionJob.domain == 'imf_weo'))
        job.started_at = finished - timedelta(seconds=2)
        job.finished_at = finished
        job.meta = dict(job.meta, execution_plan={
            'planned_domains': ['imf_weo'], 'execution_order': ['imf_weo'],
        })
        db.execute(IngestionJob.__table__.delete().where(IngestionJob.id != job.id))
        db.commit()

    accepted = _run_step(chicago_url, domain='imf_weo')
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert parse_report(accepted)['cache_eligible'] is True

    with engine.begin() as db:
        db.execute(text("UPDATE ingestion_jobs SET finished_at = finished_at + interval '2 hours'"))
    refused = _run_step(chicago_url, domain='imf_weo')
    assert refused.returncode == 1, refused.stdout + refused.stderr
    assert 'job_result_refused' in parse_report(refused)['refusals']
