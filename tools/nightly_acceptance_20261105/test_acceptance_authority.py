"""Domain readers execute actual ORM/origin consumers; inert PDF cannot publish."""
from datetime import datetime, timezone
import json

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from common import Refusal
from acceptance_authority import observe_oag_acquisition, observe_oag_report
from acceptance_database import observe_catalog, observe_current_run


@pytest.fixture
def owned_database():
    from models import Base
    from tests.acceptance_owned_pg import owned_schema
    with owned_schema() as (engine, url):
        Base.metadata.create_all(engine)
        yield engine


def read_only(db):
    db.execute(text('SET TRANSACTION READ ONLY'))
    db.execute(text('SET LOCAL row_security=off'))


def test_origin_is_observed_but_inert_body_never_earns_publication(owned_database, tmp_path):
    from tests.test_oag_acquisition_origin import setup_source, ensure, BODY
    from models import IngestionJob, IngestionStatus
    with Session(owned_database) as db:
        settings, store, client, source, context, _ = setup_source(db, tmp_path)
        with client() as http: proof = ensure(db, context, source, http, settings)
        job = db.get(IngestionJob, context.job_id)
        job.status = IngestionStatus.COMPLETED; job.finished_at = datetime.now(timezone.utc)
        db.commit(); source_id, job_id = source.id, job.id
        original = tmp_path / 'original.pdf'; original.write_bytes(BODY)
        retained = tmp_path / 'readback.pdf'; retained.write_bytes(store.read(proof['digest']))
        db.rollback(); read_only(db)
        observation = observe_oag_acquisition(db, job_id=job_id, source_id=source_id,
            validation_id=proof['validation_extraction_id'], original_pdf=original, retained_pdf=retained)
        assert observation['publication_authority'] is False
        db.rollback()
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        db.execute(text('SET LOCAL row_security=off'))
        with pytest.raises(ValueError):
            observe_oag_report(db, job_id=job_id, record_id=proof['validation_extraction_id'],
                               original_pdf=original, retained_pdf=retained)
        retained.write_bytes(b'%PDF-1.7\nforged\n%%EOF')
        with pytest.raises(Refusal, match='readback'):
            observe_oag_acquisition(db, job_id=job_id, source_id=source_id,
                validation_id=proof['validation_extraction_id'], original_pdf=original, retained_pdf=retained)
        with pytest.raises(Refusal):
            observe_oag_acquisition(db, job_id=True, source_id=source_id,
                validation_id=proof['validation_extraction_id'], original_pdf=original, retained_pdf=original)


def test_actual_revision_role_rls_and_acl_are_observed(owned_database):
    with owned_database.begin() as connection:
        connection.execute(text('CREATE TABLE alembic_version(version_num varchar(32) PRIMARY KEY)'))
        connection.execute(text("INSERT INTO alembic_version VALUES ('a756b20a0001')"))
        connection.execute(text('ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY'))
        connection.execute(text('ALTER TABLE ingestion_jobs FORCE ROW LEVEL SECURITY'))
        connection.execute(text('REVOKE ALL ON ingestion_jobs FROM PUBLIC'))
    with Session(owned_database) as db:
        read_only(db)
        observed = observe_catalog(db, ['ingestion_jobs'], expected_revision='a756b20a0001', expected_role='postgres')
        row = observed['tables'][0]
        assert row['rls'] is True and row['force_rls'] is True
        assert observed['role_flags'][0] is True and observed['policy_accepted'] is False
        assert row['columns'] and row['constraints'] and observed['revision'] == 'a756b20a0001'
        with pytest.raises(Refusal, match='revision'):
            observe_catalog(db, ['ingestion_jobs'], expected_revision='wrong', expected_role='postgres')
        with pytest.raises(Refusal, match='role'):
            observe_catalog(db, ['ingestion_jobs'], expected_revision='a756b20a0001', expected_role='inert')


def test_current_run_recomputed_from_actual_pg_refuses_forged_cli_report(tmp_path):
    from tests.test_refresh_current_run_postgres import fixture_db, parse_report
    from tests.test_hollow_run_gate import _run_step
    from seeding.source_plan import build_plan
    from seeding.current_run import PRIOR_STEPS, plan_identity
    from dataclasses import asdict
    from datetime import timedelta
    manager = fixture_db.__wrapped__(tmp_path)
    engine, url = next(manager)
    try:
        result = _run_step(url); report = parse_report(result)
        assert result.returncode == 0, result.stdout + result.stderr
        plan = build_plan(event='workflow_dispatch', schedule='', domain='', dry_run='false',
                          cra='false', opendata='false', discovery='false')
        now = datetime.now(timezone.utc)
        context = dict(floor=0, source_sha='a'*40, admitted_sha='a'*40, planned_sha='a'*40,
            schema_head='a756b20a0001', planned_identity=plan_identity(plan), prior_success='true',
            cli_outcome='success', cli_executed='true', cli_exit='0', run_id='1234', run_attempt='1',
            cli_run_id='1234', cli_run_attempt='1', cli_floor='0',
            cli_started=(now-timedelta(minutes=45)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            cli_finished=now.strftime('%Y-%m-%dT%H:%M:%SZ'), prior_job_status='success',
            prior_steps={n:{'outcome':'success','conclusion':'success','outputs':{}} for n in PRIOR_STEPS})
        original = asdict(plan); original['domains'] = list(plan.domains)
        with Session(engine) as db:
            read_only(db)
            observed = observe_current_run(db, original, context, json.dumps(report).encode())
            assert observed['source_complete'] is True and observed['cli_execution_proven'] is False
            # Hold clean ORM instances across another writer's commit. A fresh
            # SELECT must refresh their columns under READ COMMITTED.
            from sqlalchemy import select
            from models import IngestionJob, IngestionStatus
            cached = list(db.scalars(select(IngestionJob)))
            assert len(cached) == 15
            with Session(engine) as writer:
                changed = writer.scalar(select(IngestionJob).where(IngestionJob.domain=='audits'))
                changed.status = IngestionStatus.FAILED; changed.errors = ['inert committed failure']
                writer.commit()
            with pytest.raises(Refusal, match='differs|unsafe'):
                observe_current_run(db, original, context, json.dumps(report).encode())
            report['run_id'] = 'wrong-run'
            with pytest.raises(Refusal, match='differs'):
                observe_current_run(db, original, context, json.dumps(report).encode())
            for bad in (b'{}', b'[]', b'null', b'{"cache_eligible":true}', b''):
                with pytest.raises(Refusal): observe_current_run(db, original, context, bad)
    finally:
        manager.close()


def test_revision_cannot_be_borrowed_from_another_visible_schema(owned_database):
    from tests.acceptance_owned_pg import owned_schema
    target_schema = owned_database.info_acceptance['schema']
    with owned_schema() as (decoy, _):
        decoy_schema = decoy.info_acceptance['schema']
        with decoy.begin() as connection:
            connection.execute(text('CREATE TABLE alembic_version(version_num varchar(32))'))
            connection.execute(text("INSERT INTO alembic_version VALUES ('a756b20a0001')"))
        with Session(owned_database) as db:
            read_only(db)
            db.execute(text('SET LOCAL search_path='+target_schema+','+decoy_schema+',pg_catalog'))
            with pytest.raises(Refusal, match='revision|schema'):
                observe_catalog(db,['ingestion_jobs'],expected_revision='a756b20a0001',expected_role='postgres')
