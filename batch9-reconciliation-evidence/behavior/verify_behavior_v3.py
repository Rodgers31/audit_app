"""Independent executed reconciliation controls; every database is this verifier's own."""
import contextlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import select
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import DBAPIError
import sqlalchemy
from seeding.reconciliation import ReconciliationRefused, apply_plan, make_plan, verify_evidence, canonical, digest, target_identity
from seeding.reconcile_operator import request, load_policy

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('author_helpers', ROOT/'backend/tests/test_batch9_reconciliation.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
BASE = 'postgresql+psycopg2://postgres:batch9-inert-local@127.0.0.1:55493/'
checks = []
failures = []


def record(name, **detail):
    checks.append({'name':name, **detail})
    print(json.dumps(checks[-1], default=str), flush=True)


@contextlib.contextmanager
def owned(label):
    name = 'batch9-reconciliation-behavior-' + label + '-' + uuid4().hex[:12]
    admin = create_engine(BASE+'postgres', poolclass=NullPool, isolation_level='AUTOCOMMIT')
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "batch9-reconciliation-a46a"'))
    engine = create_engine(BASE+name, poolclass=NullPool)
    connection=engine.connect()
    connection.execute(text('SET search_path = public')); connection.execute(text("SET TimeZone = 'UTC'")); connection.commit()
    def admission(value):
        with admin.connect() as c:
            c.execute(text(f'ALTER DATABASE "{name}" ALLOW_CONNECTIONS '+('true' if value else 'false')))
    db=SimpleNamespace(name=name,admin=admin,engine=engine,connection=connection,factory=sessionmaker(bind=engine),url=BASE+name,admission=admission)
    try:
        yield db
    finally:
        connection.close(); engine.dispose(); admission(True)
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def refused(name, action):
    try:
        result=action()
    except Exception as exc:
        record(name, verdict='refused', exception=type(exc).__name__, message=str(exc)[:300])
        return
    record(name, verdict='FAIL_SUCCESS_ON_BAD_INPUT', returned=result)
    failures.append(name)


def rows(db, query):
    try:
        return [dict(x) for x in db.connection.execute(text(query)).mappings().all()]
    finally:
        db.connection.rollback()


def read_line(process, timeout=15):
    ready,_,_=select.select([process.stdout],[],[],timeout)
    if not ready:
        raise RuntimeError('Timed out waiting for actual operator process output')
    line=process.stdout.readline()
    if not line:
        raise RuntimeError('Operator ended: '+process.stderr.read())
    return json.loads(line)


def operator(db, policy, directory, lose_report=False):
    path=directory/'policy.json'; path.write_bytes(canonical(policy)); path.chmod(0o600)
    env={'PATH':'/usr/bin:/bin:/usr/local/bin','PYTHONPATH':str(ROOT/'backend'),'PYTHONDONTWRITEBYTECODE':'1','PYTHON_DOTENV_DISABLED':'1',
      'DATABASE_URL':db.url,'AUDIT_RECONCILIATION_DIRECT_DATABASE_URL':db.url,
      'AUDIT_RECONCILIATION_POLICY_PATH':str(path),'AUDIT_RECONCILIATION_POLICY_SHA256':hashlib.sha256(path.read_bytes()).hexdigest()}
    command=[sys.executable,'-m','seeding.reconcile_operator']
    if lose_report:
        command=[sys.executable,'-c',"import os,sys;from seeding import reconcile_operator as op\nreal=op.apply_plan\ndef lose(*args):\n    real(*args)\n    os._exit(91)\nop.apply_plan=lose\nsys.exit(op.main())"]
    process=subprocess.Popen(command,cwd=ROOT/'backend',env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    assert read_line(process)['status']=='connected'
    return process


def send(process, value):
    process.stdin.write(json.dumps(value)+'\n');process.stdin.flush()
    return read_line(process)


def run():
    # Complete valid DB context protects against mistaking setup errors for refusal.
    with owned('bounds') as db:
        selected=helpers.native(db)
        policy,evidence,keys=helpers.signed(db,selected)
        db.admission(False)
        valid=make_plan(db.connection,policy,evidence)
        record('baseline-plan', verdict='planned', database=db.name, backend=valid['backend'])
        for value in [None,[],{},True,1,float('nan'),float('inf'),'',{'action':'reclaim'},{'action':'plan','evidence':evidence,'policy':policy}]:
            refused('request-shape:'+repr(value)[:80],lambda value=value: request(db.connection,policy,value))
        for value in [None,[],{},True,1,float('nan'),float('inf'),'']:
            refused('evidence-shape:'+repr(value),lambda value=value:make_plan(db.connection,policy,value))
            refused('policy-shape:'+repr(value),lambda value=value:make_plan(db.connection,value,evidence))
            refused('plan-shape:'+repr(value),lambda value=value:apply_plan(db.connection,policy,evidence,value))
        for field,value in [('version',True),('who',None),('who','\u2003\u00a0\t\n'),('why',None),('why','\u0085\u1680'),('effects',{}),('effects','\u2028\u3000'),('effects',float('nan')),('effects_artifact',None),('effects_artifact',[]),('signature',''),('signature','00'*64),('artifacts',{}),('statements',[]),('selector',{}),('selector',{'domain':'audits','claim_id':selected['claim_id'],'legacy_job_ids':[True]})]:
            changed=deepcopy(evidence);changed[field]=value
            if field!='signature':
                try:helpers.resign(changed,keys)
                except Exception:pass
            refused('evidence-field:'+field+':'+repr(value)[:50],lambda changed=changed:make_plan(db.connection,policy,changed))
        for field,value in [('version',True),('operators',{}),('scopes',{}),('target',{})]:
            changed=deepcopy(policy);changed[field]=value
            refused('policy-field:'+field,lambda changed=changed:make_plan(db.connection,changed,evidence))
        # Self-authorizing policy in submitted request is never accepted.
        refused('submitted-self-authorized-policy', lambda:request(db.connection,policy,{'action':'plan','evidence':evidence,'policy':policy}))
        # Authenticated but invalid signed artifact is independently refused.
        for case in ['stale','future','target','empty','source_blank']:
            changed=deepcopy(evidence); artifact=next(iter(changed['artifacts'].values()));old=next(iter(changed['artifacts']))
            if case=='stale':artifact['observed_at']=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
            if case=='future':artifact['observed_at']=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
            if case=='target':artifact['target']['database_oid']=-1
            if case=='empty':artifact['content']='\u2007\t\n'
            if case=='source_blank':artifact['source']='\u202f\n'
            new=digest(artifact);changed['artifacts']={new:artifact};changed['effects_artifact']=new
            for st in changed['statements']:st['payload']['artifact']=new
            helpers.resign(changed,keys)
            refused('signed-artifact:'+case,lambda changed=changed:make_plan(db.connection,policy,changed))
        for field,value in [('version',True),('generator_sha256','0'*64),('snapshot_sha256','0'*64),('policy_sha256','0'*64),('evidence_sha256','0'*64),('backend',{}),('planned_at','2000-01-01T00:00:00+00:00')]:
            changed=deepcopy(valid);changed[field]=value
            refused('plan-field:'+field,lambda changed=changed:apply_plan(db.connection,policy,evidence,changed))
        assert rows(db,'SELECT count(*) AS n FROM admin_audit_log')[0]['n']==0
        assert rows(db,'SELECT released_at FROM seeding_domain_claims')[0]['released_at'] is None
        record('boundary-invariants',verdict='retained-no-audit')
    # Explicit JSON null tag must not masquerade as truly untagged legacy observation.
    with owned('nulltag') as db:
        selected=helpers.legacy(db)
        with db.connection.begin():db.connection.execute(text("UPDATE ingestion_jobs SET metadata=jsonb_build_object('seeding_claim_id',NULL)"))
        policy,evidence,_=helpers.signed(db,selected);db.admission(False)
        refused('explicit-null-legacy-tag-plan', lambda:make_plan(db.connection,policy,evidence))
        assert rows(db,'SELECT status FROM ingestion_jobs')[0]['status']=='RUNNING'
    # Closed admission rejects actual freshly opened TCP session (even maintenance superuser).
    with owned('admission') as db:
        selected=helpers.native(db);policy,evidence,_=helpers.signed(db,selected);db.admission(False)
        refused('new-session-closed-admission',lambda:db.engine.connect())
        plan=make_plan(db.connection,policy,evidence)
        # Same database catalogue row is locked through mutation/commit. An independent
        # actual OS process attempts to reopen from postgres and must time out.
        with db.connection.begin():
            db.connection.execute(text("SELECT datallowconn FROM pg_database WHERE datname=current_database() FOR SHARE"))
            code="from sqlalchemy import create_engine,text;from sqlalchemy.pool import NullPool; e=create_engine("+repr(BASE+'postgres')+",poolclass=NullPool,isolation_level='AUTOCOMMIT');c=e.connect();c.execute(text(\"SET lock_timeout='500ms'\"));c.execute(text("+repr(f'ALTER DATABASE "{db.name}" ALLOW_CONNECTIONS true')+"))"
            completed=subprocess.run([sys.executable,'-c',code],text=True,capture_output=True,timeout=15)
            assert completed.returncode!=0 and 'lock timeout' in completed.stderr
            record('admission-fence-row-lock',verdict='blocked-independent-process',exit=completed.returncode,stderr=completed.stderr[-500:])
        assert apply_plan(db.connection,policy,evidence,plan)['status']=='applied'
        record('valid-apply-after-boundaries',verdict='applied')
    # Keep real operator connection and kill its backend, preserving retained state.
    with owned('backendkill') as db:
        selected=helpers.native(db);policy,evidence,_=helpers.signed(db,selected)
        directory=Path(__file__).parent/(db.name+'-io');directory.mkdir()
        p=operator(db,policy,directory)
        db.connection.close()
        db.admission(False)
        result=send(p,{'action':'plan','evidence':evidence});assert result['status']=='planned';pid=result['plan']['backend']['pid']
        with db.admin.connect() as c:assert c.scalar(text('SELECT pg_terminate_backend(:pid)'),{'pid':pid}) is True
        outcome=send(p,{'action':'apply','evidence':evidence,'plan':result['plan']});assert outcome['status']=='uncertain'
        assert p.wait(10)==2
        db.admission(True);db.connection=db.engine.connect();db.connection.execute(text('SET search_path=public'));db.connection.commit()
        assert rows(db,'SELECT released_at FROM seeding_domain_claims')[0]['released_at'] is None
        assert rows(db,'SELECT count(*) AS n FROM admin_audit_log')[0]['n']==0
        record('actual-operator-backend-termination',verdict='uncertain-no-release',backend=pid,cli=outcome)
    # SIGKILL operator after plan; restart on a new backend cannot use old plan.
    with owned('restart') as db:
        selected=helpers.native(db);policy,evidence,_=helpers.signed(db,selected)
        directory=Path(__file__).parent/(db.name+'-io');directory.mkdir()
        p=operator(db,policy,directory);db.connection.close();db.admission(False)
        result=send(p,{'action':'plan','evidence':evidence});assert result['status']=='planned'
        p.kill();assert p.wait(10)==-signal.SIGKILL
        db.admission(True);p2=operator(db,policy,directory);db.admission(False)
        outcome=send(p2,{'action':'apply','evidence':evidence,'plan':result['plan']});assert outcome['status']=='refused'
        p2.stdin.close();assert p2.wait(10)==0
        db.admission(True);db.connection=db.engine.connect();db.connection.execute(text('SET search_path=public'));db.connection.commit()
        assert rows(db,'SELECT released_at FROM seeding_domain_claims')[0]['released_at'] is None
        record('actual-operator-sigkill-restart-old-plan',verdict='refused-retained',old_backend=result['plan']['backend'],cli=outcome)

    # Database trigger pauses genuine operator midway through writes. Terminate
    # its real backend; audit/claim/job mutations must all roll back together.
    with owned('midwritekill') as db:
        selected=helpers.native(db)
        with db.connection.begin():
            db.connection.execute(text("CREATE FUNCTION behavior_pause() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(8); RETURN NEW; END $$"))
            db.connection.execute(text("CREATE TRIGGER behavior_pause BEFORE UPDATE ON ingestion_jobs FOR EACH ROW EXECUTE FUNCTION behavior_pause()"))
        policy,evidence,_=helpers.signed(db,selected)
        directory=Path(__file__).parent/(db.name+'-io');directory.mkdir()
        p=operator(db,policy,directory);db.connection.close();db.admission(False)
        result=send(p,{'action':'plan','evidence':evidence});assert result['status']=='planned';pid=result['plan']['backend']['pid']
        p.stdin.write(json.dumps({'action':'apply','evidence':evidence,'plan':result['plan']})+'\n');p.stdin.flush()
        deadline=time.monotonic()+10
        observed=None
        while time.monotonic()<deadline:
            with db.admin.connect() as c:
                observed=c.execute(text('SELECT state,wait_event,query FROM pg_stat_activity WHERE pid=:pid'),{'pid':pid}).mappings().one_or_none()
            if observed and observed['wait_event']=='PgSleep':break
            time.sleep(.02)
        assert observed and observed['wait_event']=='PgSleep', observed
        with db.admin.connect() as c:assert c.scalar(text('SELECT pg_terminate_backend(:pid)'),{'pid':pid}) is True
        outcome=read_line(p);assert outcome['status']=='uncertain';assert p.wait(10)==2
        db.admission(True);db.connection=db.engine.connect();db.connection.execute(text('SET search_path=public'));db.connection.commit()
        assert rows(db,'SELECT released_at FROM seeding_domain_claims')[0]['released_at'] is None
        assert rows(db,'SELECT status FROM ingestion_jobs')[0]['status']=='RUNNING'
        assert rows(db,'SELECT count(*) AS n FROM admin_audit_log')[0]['n']==0
        record('actual-operator-midwrite-backend-death',verdict='uncertain-all-rolled-back',backend=pid,query=str(observed['query'])[:300],cli=outcome)
    # Deliberately inject loss AFTER actual apply transaction committed but BEFORE
    # operator can report/return. This is report-boundary fault injection, not an
    # exclusion/acquisition proof or a substituted reconciliation implementation.
    with owned('lostreport') as db:
        selected=helpers.native(db);policy,evidence,_=helpers.signed(db,selected)
        directory=Path(__file__).parent/(db.name+'-io');directory.mkdir()
        p=operator(db,policy,directory,lose_report=True);db.connection.close();db.admission(False)
        result=send(p,{'action':'plan','evidence':evidence});assert result['status']=='planned'
        p.stdin.write(json.dumps({'action':'apply','evidence':evidence,'plan':result['plan']})+'\n');p.stdin.flush()
        assert p.wait(15)==91 and p.stdout.read()==''
        db.admission(True);db.connection=db.engine.connect();db.connection.execute(text('SET search_path=public'));db.connection.commit()
        assert rows(db,'SELECT released_at FROM seeding_domain_claims')[0]['released_at'] is not None
        assert rows(db,'SELECT status FROM ingestion_jobs')[0]['status']=='FAILED'
        assert rows(db,'SELECT count(*) AS n FROM admin_audit_log')[0]['n']==1
        db.connection.close()
        p2=operator(db,policy,directory);db.admission(False)
        outcome=send(p2,{'action':'apply','evidence':evidence,'plan':result['plan']});assert outcome['status']=='refused'
        p2.stdin.close();assert p2.wait(10)==0
        db.admission(True);db.connection=db.engine.connect();db.connection.execute(text('SET search_path=public'));db.connection.commit()
        assert rows(db,'SELECT count(*) AS n FROM admin_audit_log')[0]['n']==1
        record('injected-postcommit-report-loss-restart',verdict='durably-committed-old-plan-refused',exit=91,old_backend=result['plan']['backend'],cli=outcome)


def main():
    label=sys.argv[1]
    sources=['backend/seeding/reconciliation.py','backend/seeding/reconcile_operator.py','backend/models.py','backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py','backend/tests/test_batch9_reconciliation.py']
    before={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources}
    setup=None
    try:run()
    except Exception as exc:
        import traceback
        setup={'exception':type(exc).__name__,'traceback':traceback.format_exc()}
        print(setup['traceback'],flush=True)
    after={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources}
    receipt={'generated_by':str(Path(__file__).relative_to(ROOT)),'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'generated_at':datetime.now(timezone.utc).isoformat(),'target_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'source_sha256_before':before,'source_sha256_after':after,'source_changed_during_run':before!=after,'runtime':sys.version,'sqlalchemy':sqlalchemy.__version__,'platform':platform.platform(),'exact_command':[sys.executable,*sys.argv],'environment':{k:os.environ.get(k) for k in ['PYTHONPATH','DATABASE_URL','PYTHON_DOTENV_DISABLED','PYTHONDONTWRITEBYTECODE']},'checks':checks,'failures':failures,'setup_or_unexpected_exception':setup,'verdict':'FAILED' if failures or setup or before!=after else 'PASSED'}
    path=Path(__file__).parent/(label+'.json');assert not path.exists();path.write_text(json.dumps(receipt,indent=2,default=str)+'\n')
    readback=json.loads(path.read_text());assert readback['generator_sha256']==receipt['generator_sha256'];assert readback['verdict']==receipt['verdict']
    print('RECEIPT',path,'CHECKS',len(checks),'VERDICT',receipt['verdict'],flush=True)
    return 1 if receipt['verdict']!='PASSED' else 0

if __name__=='__main__':sys.exit(main())
