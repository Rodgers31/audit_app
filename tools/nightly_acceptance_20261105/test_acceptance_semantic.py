"""Supported semantic importer and both CLI consumers execute the real adapters."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from common import Refusal, canonical, sha256
import operational
from test_acceptance_refresh import actual_capture


def test_supported_semantic_importer_and_clis_keep_operational_holds(actual_capture,tmp_path):
    from tests.test_refresh_current_run_postgres import fixture_db
    from models import IngestionJob
    from seeding.source_plan import build_plan
    from seeding.current_run import PRIOR_STEPS, plan_identity, classify
    capture, secret, run, census = actual_capture
    root=tmp_path/'packet';root.mkdir()
    shutil.copytree(capture,root/'refresh')
    manager=fixture_db.__wrapped__(tmp_path)
    engine,_=next(manager)
    try:
        from models import Base, IngestionStatus
        from tests.test_oag_acquisition_origin import setup_source, ensure, BODY
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text('UPDATE ingestion_jobs SET id=id+100'))
        # A valid prior-job origin is deliberately outside the current floor.
        with Session(engine) as db:
            settings,store,client,source,prior,_=setup_source(db,tmp_path/'prior')
            with client() as http:proof=ensure(db,prior,source,http,settings)
            job=db.get(IngestionJob,prior.job_id);job.status=IngestionStatus.COMPLETED
            job.finished_at=datetime.now(timezone.utc);db.commit()
            source_id=source.id
        (root/'prior-original.pdf').write_bytes(BODY);(root/'prior-retained.pdf').write_bytes(store.read(proof['digest']))
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE alembic_version(version_num varchar(32) PRIMARY KEY)'))
            connection.execute(text("INSERT INTO alembic_version VALUES ('a756b20a0001')"))
        plan=build_plan(event='workflow_dispatch',schedule='',domain='',dry_run='false',cra='false',opendata='false',discovery='false')
        now=datetime.now(timezone.utc)
        context=dict(floor=prior.job_id,source_sha=run['commit'],admitted_sha=run['commit'],planned_sha=run['commit'],
            schema_head='a756b20a0001',planned_identity=plan_identity(plan),prior_success='true',cli_outcome='success',
            cli_executed='true',cli_exit='0',run_id=str(run['run_id']),run_attempt=str(run['attempt']),
            cli_run_id=str(run['run_id']),cli_run_attempt=str(run['attempt']),cli_floor=str(prior.job_id),
            cli_started=(now-timedelta(minutes=45)).strftime('%Y-%m-%dT%H:%M:%SZ'),cli_finished=now.strftime('%Y-%m-%dT%H:%M:%SZ'),
            prior_job_status='success',prior_steps={name:{'outcome':'success','conclusion':'success','outputs':{}} for name in PRIOR_STEPS})
        with Session(engine) as db:
            report=classify(list(db.scalars(select(IngestionJob).where(IngestionJob.id>prior.job_id)
                           .order_by(IngestionJob.id.desc()))),plan,context)
        assert report['classification']=='complete'
        def put(name,value):
            path=root/name;path.write_bytes(canonical(value))
            return {'path':name,'sha256':sha256(path),'size':path.stat().st_size}
        def reference(name):
            path=root/name;return {'path':name,'sha256':sha256(path),'size':path.stat().st_size}
        plan=asdict(plan);plan['domains']=list(plan['domains'])
        value=dict(schema='nightly-semantic-local-input-v1',kind='full15',binding=run,
            plan=put('plan.json',plan),context=put('context.json',context),current_report=put('current.json',report),
            pg_schema=engine.info_acceptance['schema'],refresh=reference('refresh/refresh.json'),
            census=put('census.json',census),oag=[],fiscal=None)
        put('input.json',value)
        config=dict(schema='nightly-backend-config-v1',plugins=['pytest_asyncio.plugin','acceptance_backend'],
            pg_url=os.environ['REFRESH_FIXTURE_PG_URL'],fixture_token=os.environ['REFRESH_FIXTURE_TOKEN'],original_family='none')
        put('backend.json',config);(root/'test-key').write_bytes(secret)
        observed=operational.observe_local(root/'input.json',backend_config=root/'backend.json',signing_key_file=root/'test-key')
        assert observed['refresh']['verdict']=='OFFLINE_HMAC_AND_ACK_SEMANTICS_VERIFIED'
        assert observed['holds'] and observed['production_accepted'] is False
        assert observed['current_run']['cli_execution_proven'] is False
        wrong_job=dict(value,oag=[dict(scope='acquisition',job_id=prior.job_id,source_id=source_id,
            record_id=proof['validation_extraction_id'],original=reference('prior-original.pdf'),retained=reference('prior-retained.pdf'))])
        put('wrong-job.json',wrong_job)
        with pytest.raises(Refusal,match='job|run'):
            operational.observe_local(root/'wrong-job.json',backend_config=root/'backend.json',signing_key_file=root/'test-key')
        tools=Path(__file__).absolute().parent
        env={'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin','HOME':str(tmp_path),'TMPDIR':str(tmp_path),
             'PYTHONDONTWRITEBYTECODE':'1','PYTHON_DOTENV_DISABLED':'1','ENVIRONMENT':'test',
             'DATABASE_URL':'postgresql+psycopg2://postgres@127.0.0.1:55432/fiscal_fixture',
             'PYTHONPATH':str(tools)+':'+str(tools.parents[1]/'backend')}
        for entry,flags in [('operational.py',['--semantic-local']),('ledger.py',['check-semantic-local'])]:
            cmd=[sys.executable,'-B',str(tools/entry),*flags,str(root/'input.json'),'--backend-config',str(root/'backend.json'),
                 '--signing-key-file',str(root/'test-key')]
            result=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=20)
            assert result.returncode==0,result.stdout+result.stderr
            assert 'LOCAL_SEMANTIC_OBSERVATIONS_ONLY_OPERATIONAL_GATES_PENDING' in result.stdout
        value['current_report']=put('forged.json',{'success':True})
        put('forged-input.json',value)
        with pytest.raises(Refusal,match='differs'):
            operational.observe_local(root/'forged-input.json',backend_config=root/'backend.json',signing_key_file=root/'test-key')
    finally:
        manager.close()
