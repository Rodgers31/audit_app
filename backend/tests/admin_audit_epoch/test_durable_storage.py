"""Mandatory migrated production route controls on the canonical owned epoch PG.

No new developer override or prerequisite skip: the existing CI epoch helper
prepares the strict allowed endpoint. Local controls use the lane reservation.
"""
from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from database import get_db
from models import AdminAuditLog
from routers.admin_audit_log import router
from services import admin_audit_storage as storage
from supabase_auth import AdminUser, get_current_user
from tests.admin_audit_epoch.resource_cleanup import cleanup_owned, database_identity, role_identity

BACKEND = Path(__file__).resolve().parents[2]
MIGRATION = BACKEND / 'alembic/versions/a611b12a0001_durable_admin_audit.py'
KEY = 'ab' * 32
ACTOR = AdminUser(id='inert-admin', email=None, roles=['admin'])
PACKET=BACKEND.parent/'docs/admin/implementation/batch11-issue-611-evidence'
launch_spec=importlib.util.spec_from_file_location('retained_audit_launch',PACKET/'launch_probe.py')
launch=importlib.util.module_from_spec(launch_spec);launch_spec.loader.exec_module(launch)
# The original intended behavior and test function bytes remain unchanged.
test_retained_root_writer_control=launch.test_root_writer_late_lower_id_is_excluded
test_retained_epoch_capability_control=launch.test_durable_capability_at_real_current_epoch


def command_environment(url):
    return {'PATH': os.environ['PATH'], 'DATABASE_URL': url, 'PYTHON_DOTENV_DISABLED': '1',
            'PYTHONPATH': str(BACKEND), 'PYTHONDONTWRITEBYTECODE': '1'}


def migrate(url, *args):
    result = subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=BACKEND,
                            env=command_environment(url), capture_output=True, text=True, timeout=90)
    print('migration', args, 'exit', result.returncode, result.stdout, result.stderr)
    return result


@pytest.fixture
def durable(request, monkeypatch):
    if os.getenv('ISSUE611_OWNED_POSTGRES') != '1':
        pytest.fail('Mandatory durable audit cases require canonical prepared epoch fixture')
    port = os.getenv('ISSUE611_PG_PORT', '55534')
    if port not in ('55534', '55545'):
        pytest.fail('Explicit permitted owned epoch port required')
    admin_url = f'postgresql+psycopg2://inert:inert@127.0.0.1:{port}/issue611'
    admin = create_engine(admin_url, isolation_level='AUTOCOMMIT')
    name = 'batch12_audit_storage_' + uuid4().hex
    reader_name, writer_name = name + '_r', name + '_w'
    url = make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    owner = reader = writer = None
    created=False;expected_database=None;created_roles={}
    try:
        with admin.connect() as c:
            assert c.execute(text("SELECT current_database(),current_user,pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()")).one() == ('issue611','inert','inert')
            created=True  # Record an uncertain CREATE before crossing transport.
            c.execute(text(f'CREATE DATABASE "{name}" OWNER inert'))
            expected_database=database_identity(c,name)
        owner=create_engine(url)
        requested = getattr(request, 'param', 'e602b11a0001')
        start = 'e602b11a0001' if requested == 'legacy' else requested
        assert migrate(url, 'upgrade', start).returncode == 0
        if requested == 'legacy':
            with owner.begin() as c:
                c.execute(text("INSERT INTO admin_audit_log(actor_id,action,payload,created_at) VALUES('legacy','legacy','{}',now())"))
        assert migrate(url, 'upgrade', 'head').returncode == 0
        with owner.begin() as c:
            assert c.scalar(text('SELECT version_num FROM alembic_version')) == 'a611b12a0001'
            assert c.scalar(text('SELECT certified FROM admin_audit_storage')) is False
            incarnation = c.scalar(text('SELECT incarnation::text FROM admin_audit_storage'))
            c.execute(text('UPDATE admin_audit_storage SET certified=true'))
        with admin.connect() as c:
            for role, group in ((reader_name, 'audit_log_reader'), (writer_name, 'audit_log_writer')):
                created_roles[role]=None  # Retain uncertain creation outcomes.
                c.execute(text(f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD \'inert\''))
                created_roles[role]=role_identity(c,role)
                c.execute(text(f'GRANT {group} TO "{role}"'))
        reader = create_engine(make_url(url).set(username=reader_name).render_as_string(hide_password=False),isolation_level='REPEATABLE READ')
        writer = create_engine(make_url(url).set(username=writer_name).render_as_string(hide_password=False))
        factory = sessionmaker(bind=writer)
        monkeypatch.setenv('ADMIN_AUDIT_INCARNATION', incarnation)
        monkeypatch.setenv('ADMIN_AUDIT_BOOKMARK_KEY', KEY)
        monkeypatch.delenv('ADMIN_AUDIT_DATABASE_URL', raising=False)
        app = FastAPI(); app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: ACTOR
        def sessions():
            with sessionmaker(bind=reader)() as db: yield db
        app.dependency_overrides[get_db] = sessions
        with TestClient(app, raise_server_exceptions=False) as client:
            yield owner, factory, client, reader, writer, app, url, admin, reader_name, writer_name
    finally:
        cleanup_owned(admin,(reader,writer,owner),name,created,expected_database,created_roles)


@pytest.fixture
def owned(durable):
    owner,factory,client,*_=durable
    return owner,factory,client


def item(**values):
    return AdminAuditLog(actor_id='inert-admin', action='etl.trigger',
        payload={'job_id':1,'dry_run':True,'access_token':'INERT_SECRET'},
        created_at=datetime.now(timezone.utc), **values)


def insert(factory):
    with factory() as db: db.add(item()); db.commit()


def fields(value):
    return {k: value[k] for k in ('snapshot_id','as_of','visibility_snapshot')}


def private_unavailable(response):
    assert response.status_code == 503, response.text
    assert response.json() == {'detail':'Audit evidence is unavailable.'}
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['vary'] == 'Authorization'


def test_migrated_endpoint_excludes_real_late_root_writer(durable):
    owner,factory,client,*_ = durable
    with factory() as early:
        early.add(item()); early.flush()
        insert(factory)
        first = client.get('/api/v1/admin/audit-log?days=0&page_size=1')
        assert first.status_code == 200, first.text
        assert first.json()['total'] == 1
        early.commit()
    second = client.get('/api/v1/admin/audit-log', params={'days':0,'page':2,'page_size':1,**fields(first.json())})
    assert second.status_code == 200, second.text
    assert second.json()['total'] == 1 and second.json()['entries'] == []
    assert second.headers['cache-control'] == 'private, no-store'
    assert 'INERT_SECRET' not in first.text
    with owner.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM admin_audit_log')) == 2
        assert int(c.scalar(text('SELECT min(root_xid)::text FROM admin_audit_provenance'))) > 2**32


@pytest.mark.parametrize('field', ['snapshot','signature','scope','as_of','ceiling','actor'])
def test_migrated_bookmark_modification_refuses(durable,field):
    _,factory,client,_,_,app,*_ = durable
    insert(factory); first=client.get('/api/v1/admin/audit-log?days=0').json(); params=fields(first)
    token=params['visibility_snapshot']
    if field=='snapshot':
        parts=token.split(':');parts[2]='3';params['visibility_snapshot']=':'.join(parts)
    elif field=='signature': params['visibility_snapshot']=token[:-1]+('0' if token[-1]!='0' else '1')
    elif field=='scope': params['visibility_snapshot']=token.replace(token.split(':')[1],str(uuid4()))
    elif field=='as_of': params['as_of']=(datetime.fromisoformat(first['as_of'].replace('Z','+00:00'))-timedelta(seconds=1)).isoformat()
    elif field=='ceiling': params['snapshot_id']=0
    else: app.dependency_overrides[get_current_user]=lambda: AdminUser(id='other-admin',email=None,roles=['admin'])
    response=client.get('/api/v1/admin/audit-log',params=params)
    assert response.status_code==422,response.text
    assert response.headers['cache-control']=='private, no-store'


@pytest.mark.parametrize('damage', [
    'ALTER TABLE admin_audit_log DISABLE TRIGGER audit_log_capture',
    'ALTER TABLE admin_audit_provenance DISABLE TRIGGER audit_provenance_immutable',
    'ALTER TABLE admin_audit_log DISABLE ROW LEVEL SECURITY',
    'DROP POLICY audit_log_read ON admin_audit_log',
    'ALTER TABLE admin_audit_provenance DROP CONSTRAINT admin_audit_provenance_pkey',
    'UPDATE admin_audit_storage SET certified=false',
    'UPDATE admin_audit_storage SET incarnation=\'61100000-0000-4000-8000-000000000001\'',
    'UPDATE admin_audit_storage SET database_oid=0',
    'UPDATE admin_audit_storage SET system_identifier=\'copied\'',
    'UPDATE admin_audit_storage SET timeline=timeline+1',
], ids=['capture','immutable','rls','policy','primary-key','uncertified','incarnation','database','system','timeline'])
def test_storage_damage_fails_private_before_read(durable,damage):
    owner,factory,client,*_=durable;insert(factory)
    with owner.begin() as c:c.execute(text(damage))
    private_unavailable(client.get('/api/v1/admin/audit-log?days=0'))


@pytest.mark.parametrize('grant',['writer','column','provenance','certification'])
def test_effective_inherited_reader_write_is_refused(durable,grant):
    owner,factory,client,_,_,_,_,admin,reader_name,*_=durable;insert(factory)
    if grant=='writer':
        with admin.connect() as c:c.execute(text(f'GRANT audit_log_writer TO "{reader_name}"'))
    else:
        sql={'column':'GRANT INSERT(actor_id) ON admin_audit_log','provenance':'GRANT INSERT ON admin_audit_provenance','certification':'GRANT UPDATE(certified) ON admin_audit_storage'}[grant]
        with owner.begin() as c:c.execute(text(sql+f' TO "{reader_name}"'))
    private_unavailable(client.get('/api/v1/admin/audit-log?days=0'))


def test_root_raw_savepoint_and_rollback_admission(durable):
    owner,factory,client,*_=durable
    with factory() as db:
        root=db.scalar(text('SELECT pg_current_xact_id()::text'))
        with db.begin_nested():db.add(item());db.flush()
        with pytest.raises(RuntimeError):
            with db.begin_nested():db.add(item());db.flush();raise RuntimeError('inert rollback')
        db.execute(text("INSERT INTO admin_audit_log(actor_id,action,payload,created_at) VALUES('raw','etl.trigger','{}',now())"))
        db.commit()
    with owner.connect() as c:
        assert c.execute(text('SELECT root_xid::text FROM admin_audit_provenance ORDER BY audit_id')).all()==[(root,),(root,)]
    response=client.get('/api/v1/admin/audit-log?days=0');assert response.status_code==200,response.text
    assert response.json()['total']==2


def test_writer_cannot_forge_provenance_or_rewrite_history(durable):
    _,factory,client,_,writer,*_=durable;insert(factory)
    for sql in ["INSERT INTO admin_audit_provenance VALUES(1,'3','61100000-0000-4000-8000-000000000001')",'UPDATE admin_audit_log SET action=\'forged\'','DELETE FROM admin_audit_log','TRUNCATE admin_audit_log']:
        with writer.begin() as c:
            with pytest.raises(DBAPIError):
                with c.begin_nested():c.execute(text(sql))
    assert client.get('/api/v1/admin/audit-log?days=0').json()['total']==1


@pytest.mark.parametrize('audit_id',[0,-1])
def test_database_rejects_nonpositive_ids_without_provenance(durable,audit_id):
    owner,_,client,*_=durable
    with owner.begin() as c:
        with pytest.raises(DBAPIError,match='ck_admin_audit_positive_id'):
            with c.begin_nested():
                c.execute(text("INSERT INTO admin_audit_log(id,actor_id,action,payload,created_at) VALUES(:id,'raw','etl.trigger','{}',now())"),{'id':audit_id})
    with owner.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM admin_audit_log'))==0
        assert c.scalar(text('SELECT count(*) FROM admin_audit_provenance'))==0
    response=client.get('/api/v1/admin/audit-log?days=0')
    assert response.status_code==200,response.text
    assert response.json()['snapshot_id']==0


def test_actual_database_clone_refuses_copied_authority_and_bookmark(durable):
    owner,factory,client,reader,writer,app,url,admin,*_=durable
    insert(factory);first=client.get('/api/v1/admin/audit-log?days=0').json()
    source=make_url(url).database;clone=source+'_clone'
    # CREATE DATABASE TEMPLATE requires the source connections to be closed.
    for engine in (owner,reader,writer):engine.dispose()
    clone_reader=clone_owner=None;created=False
    previous=app.dependency_overrides[get_db]
    try:
        with admin.connect() as c:
            c.execute(text(f'CREATE DATABASE "{clone}" TEMPLATE "{source}" OWNER inert'))
            created=True
        clone_reader=create_engine(reader.url.set(database=clone),isolation_level='REPEATABLE READ')
        def sessions():
            with sessionmaker(bind=clone_reader)() as db:yield db
        app.dependency_overrides[get_db]=sessions
        private_unavailable(client.get('/api/v1/admin/audit-log',params={'days':0,**fields(first)}))
        clone_owner=create_engine(make_url(url).set(database=clone))
        with clone_owner.connect() as c:
            assert c.scalar(text('SELECT count(*) FROM admin_audit_provenance'))==1
            assert c.scalar(text('SELECT incarnation::text FROM admin_audit_storage'))==os.environ['ADMIN_AUDIT_INCARNATION']
            assert c.scalar(text("SELECT database_oid<>(SELECT oid FROM pg_database WHERE datname=current_database()) FROM admin_audit_storage")) is True
    finally:
        app.dependency_overrides[get_db]=previous
        if clone_reader is not None:clone_reader.dispose()
        if clone_owner is not None:clone_owner.dispose()
        if created:
            with admin.connect() as c:c.execute(text(f'DROP DATABASE "{clone}"'))


def test_postgres_without_external_custody_refuses_even_at_current_epoch(durable,monkeypatch):
    _,factory,client,*_=durable;insert(factory)
    monkeypatch.delenv('ADMIN_AUDIT_INCARNATION')
    private_unavailable(client.get('/api/v1/admin/audit-log?days=0'))


def test_read_committed_connection_cannot_admit_storage(durable):
    _,factory,client,reader,_,app,*_=durable;insert(factory)
    unsafe=create_engine(reader.url,isolation_level='READ COMMITTED')
    previous=app.dependency_overrides[get_db]
    def sessions():
        with sessionmaker(bind=unsafe)() as db:yield db
    try:
        app.dependency_overrides[get_db]=sessions
        private_unavailable(client.get('/api/v1/admin/audit-log?days=0'))
    finally:app.dependency_overrides[get_db]=previous;unsafe.dispose()


def test_concurrent_custody_change_keeps_one_read_population(durable,monkeypatch):
    owner,factory,client,*_=durable;insert(factory)
    original=storage.capability
    def change_after_admission(db):
        admitted=original(db)
        with owner.begin() as c:
            c.execute(text('UPDATE admin_audit_storage SET incarnation=:scope'),{'scope':uuid4()})
        insert(factory)
        return admitted
    monkeypatch.setattr(storage,'capability',change_after_admission)
    first=client.get('/api/v1/admin/audit-log?days=0')
    assert first.status_code==200,first.text
    assert first.json()['total']==1
    monkeypatch.setattr(storage,'capability',original)
    private_unavailable(client.get('/api/v1/admin/audit-log?days=0'))


def test_freeze_rewrite_and_retention_preserve_issued_population(durable):
    owner,factory,client,*_=durable;insert(factory)
    first=client.get('/api/v1/admin/audit-log?days=0').json()
    with owner.connect().execution_options(isolation_level='AUTOCOMMIT') as c:
        before=c.execute(text('SELECT * FROM admin_audit_provenance')).all()
        for table in ('admin_audit_log','admin_audit_provenance'):
            c.execute(text(f'VACUUM (FREEZE, ANALYZE) {table}'));c.execute(text(f'VACUUM FULL {table}'))
        assert c.execute(text('SELECT * FROM admin_audit_provenance')).all()==before
    for sql in ['DELETE FROM admin_audit_log','TRUNCATE admin_audit_provenance','UPDATE admin_audit_log SET action=action']:
        with owner.begin() as c:
            with pytest.raises(DBAPIError,match='append only'):
                with c.begin_nested():c.execute(text(sql))
    response=client.get('/api/v1/admin/audit-log',params={'days':0,**fields(first)})
    assert response.status_code==200,response.text
    assert response.json()['entries']==first['entries']


def test_filter_transfer_expiry_and_external_authority(durable,monkeypatch):
    _,factory,client,*_=durable;insert(factory)
    first=client.get('/api/v1/admin/audit-log?days=0').json()
    for _ in range(3):
        response=client.get('/api/v1/admin/audit-log',params={'days':0,'actor_id':'absent',**fields(first)})
        assert response.status_code==200,response.text
        assert response.json()['total']==0 and response.json()['visibility_snapshot']==first['visibility_snapshot']
    empty=client.get('/api/v1/admin/audit-log?days=0&actor_id=absent').json()
    assert empty['snapshot_id']==first['snapshot_id']
    transferred=client.get('/api/v1/admin/audit-log',params={'days':0,**fields(empty)})
    assert transferred.status_code==200,transferred.text
    assert transferred.json()['total']==1
    expired=client.get('/api/v1/admin/audit-log',params={**fields(first),'as_of':(datetime.now(timezone.utc)-timedelta(minutes=16)).isoformat()})
    assert expired.status_code==422 and 'expired' in expired.text
    monkeypatch.delenv('ADMIN_AUDIT_BOOKMARK_KEY')
    private_unavailable(client.get('/api/v1/admin/audit-log?days=0'))


def test_actual_independent_writer_failure_and_uncertain_commit(durable,monkeypatch,caplog):
    import database
    from utils.audit import record_admin_action
    owner,factory,client,*_=durable
    monkeypatch.setattr(database,'SessionLocal',factory)
    with factory() as caller:
        caller.add(item());caller.flush()
        record_admin_action(caller,actor=ACTOR,action='etl.trigger',payload={'job_id':1,'dry_run':True})
        caller.rollback()
    assert client.get('/api/v1/admin/audit-log?days=0').json()['total']==1
    # Actual committed transaction, then lost acknowledgement. Do not invent a
    # rollback/retry of an unknown commit or change the caller's ownership.
    class UncertainSession:
        def __init__(self):self.db=factory()
        def add(self,row):self.db.add(row)
        def commit(self):self.db.commit();raise RuntimeError('INERT_SECRET uncertain acknowledgement')
        def rollback(self):self.db.rollback()
        def close(self):self.db.close()
    monkeypatch.setattr(database,'SessionLocal',UncertainSession)
    record_admin_action(None,actor=ACTOR,action='etl.trigger',payload={'job_id':1})
    assert 'Failed to write admin_audit_log row' in caplog.text and 'INERT_SECRET' not in caplog.text
    assert client.get('/api/v1/admin/audit-log?days=0').json()['total']==2
    with owner.begin() as c:
        c.execute(text("CREATE FUNCTION batch12_reject() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'inert rejected write'; END $$"))
        c.execute(text('CREATE TRIGGER batch12_reject BEFORE INSERT ON admin_audit_log FOR EACH ROW EXECUTE FUNCTION batch12_reject()'))
    monkeypatch.setattr(database,'SessionLocal',factory)
    record_admin_action(None,actor=ACTOR,action='etl.trigger')
    with owner.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM admin_audit_log'))==c.scalar(text('SELECT count(*) FROM admin_audit_provenance'))==2


def test_legacy_and_partial_schema_never_fabricate_history(durable):
    owner,_,client,*_=durable
    with owner.begin() as c:
        c.execute(text('ALTER TABLE admin_audit_log DISABLE TRIGGER audit_log_capture'))
        c.execute(text("INSERT INTO admin_audit_log(actor_id,action,payload,created_at) VALUES('legacy','legacy','{}',now())"))
        c.execute(text('ALTER TABLE admin_audit_log ENABLE ALWAYS TRIGGER audit_log_capture'))
    private_unavailable(client.get('/api/v1/admin/audit-log?actor_id=absent&days=0'))
    with owner.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM admin_audit_log'))==1
        assert c.scalar(text('SELECT count(*) FROM admin_audit_provenance'))==0


@pytest.mark.parametrize('durable',['e554b10a0001','e583b9c9a001','e602b11a0001'],indirect=True)
def test_ordered_upgrade_repeat_and_history_refuses_downgrade(durable):
    owner,factory,_,_,_,_,url,*_=durable
    assert migrate(url,'upgrade','head').returncode==0
    insert(factory)
    result=migrate(url,'downgrade','e602b11a0001')
    assert result.returncode!=0 and 'Audit history or certification exists' in result.stderr
    with owner.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM admin_audit_log'))==1
        assert c.scalar(text('SELECT version_num FROM alembic_version'))=='a611b12a0001'


def test_empty_uncertified_round_trip_preserves_private_admission(durable,monkeypatch):
    owner,_,client,_,_,_,url,*_=durable
    with owner.begin() as c:c.execute(text('UPDATE admin_audit_storage SET certified=false'))
    assert migrate(url,'downgrade','e602b11a0001').returncode==0
    with owner.connect() as c:
        assert c.scalar(text("SELECT to_regclass('public.admin_audit_provenance')")) is None
        assert c.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='admin_audit_log'::regclass")) is True
    private_unavailable(client.get('/api/v1/admin/audit-log?days=0'))
    assert migrate(url,'upgrade','head').returncode==0
    with owner.connect() as c:
        assert c.scalar(text('SELECT certified FROM admin_audit_storage')) is False
    private_unavailable(client.get('/api/v1/admin/audit-log?days=0'))


@pytest.mark.parametrize('precondition',['ready-worker','partial-storage','inherited-owner'])
def test_migration_preconditions_abort_without_partial_admission(durable,precondition):
    owner,_,_,_,_,_,url,admin,*_=durable
    with owner.begin() as c:c.execute(text('UPDATE admin_audit_storage SET certified=false'))
    assert migrate(url,'downgrade','e602b11a0001').returncode==0
    try:
        with owner.begin() as c:
            if precondition=='ready-worker':
                c.execute(text("INSERT INTO etl_dispatch_worker VALUES(1,:g,now(),now()+interval '30 seconds',true)"),{'g':uuid4()})
            elif precondition=='partial-storage':c.execute(text('CREATE TABLE admin_audit_storage(inert integer)'))
        if precondition=='inherited-owner':
            with admin.connect() as c:c.execute(text('GRANT inert TO audit_log_reader'))
        result=migrate(url,'upgrade','head')
        assert result.returncode!=0
        message={'ready-worker':'Stop dedicated worker','partial-storage':'Partial or preexisting audit storage','inherited-owner':'cannot inherit other authority'}[precondition]
        assert message in result.stderr,result.stderr
        with owner.connect() as c:
            assert c.scalar(text('SELECT version_num FROM alembic_version'))=='e602b11a0001'
            assert c.scalar(text("SELECT to_regclass('public.admin_audit_provenance')")) is None
            assert c.scalar(text("SELECT EXISTS(SELECT FROM pg_constraint WHERE conname='ck_admin_audit_positive_id' AND conrelid='admin_audit_log'::regclass)")) is False
    finally:
        if precondition=='inherited-owner':
            with admin.connect() as c:c.execute(text('REVOKE inert FROM audit_log_reader'))


def test_migration_removes_existing_public_column_grants(durable):
    owner,_,_,_,_,_,url,*_=durable
    with owner.begin() as c:c.execute(text('UPDATE admin_audit_storage SET certified=false'))
    assert migrate(url,'downgrade','e602b11a0001').returncode==0
    with owner.begin() as c:c.execute(text('GRANT SELECT(actor_id) ON admin_audit_log TO PUBLIC'))
    assert migrate(url,'upgrade','head').returncode==0
    with owner.connect() as c:
        assert c.scalar(text("SELECT EXISTS(SELECT FROM pg_attribute a,LATERAL aclexplode(a.attacl) e WHERE a.attrelid='admin_audit_log'::regclass AND e.grantee=0)")) is False


def test_migration_removes_existing_public_sequence_grants(durable,monkeypatch):
    owner,factory,client,_,_,_,url,*_=durable
    with owner.begin() as c:c.execute(text('UPDATE admin_audit_storage SET certified=false'))
    assert migrate(url,'downgrade','e602b11a0001').returncode==0
    with owner.begin() as c:c.execute(text('GRANT ALL ON SEQUENCE admin_audit_log_id_seq TO PUBLIC'))
    assert migrate(url,'upgrade','head').returncode==0
    with owner.begin() as c:
        assert c.scalar(text("SELECT has_sequence_privilege('audit_log_reader','admin_audit_log_id_seq','USAGE,SELECT,UPDATE')")) is False
        assert c.scalar(text("SELECT has_sequence_privilege('audit_log_writer','admin_audit_log_id_seq','UPDATE,SELECT')")) is False
        assert c.scalar(text("SELECT has_sequence_privilege('audit_log_writer','admin_audit_log_id_seq','USAGE')")) is True
        c.execute(text('UPDATE admin_audit_storage SET certified=true'))
        monkeypatch.setenv('ADMIN_AUDIT_INCARNATION',c.scalar(text('SELECT incarnation::text FROM admin_audit_storage')))
    insert(factory)
    assert client.get('/api/v1/admin/audit-log?days=0').status_code==200


def test_migration_bodies_match_runtime_contract():
    spec=importlib.util.spec_from_file_location('durable_audit_migration',MIGRATION)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.down_revision=='e602b11a0001'
    for name in ('CAPTURE_BODY','IMMUTABLE_BODY','IDENTITY_BODY'):assert getattr(module,name)==getattr(storage,name)


@pytest.mark.parametrize('durable',['legacy'],indirect=True)
def test_upgrade_keeps_preexisting_legacy_truthfully_unavailable(durable):
    owner,_,client,*_=durable
    private_unavailable(client.get('/api/v1/admin/audit-log?days=0&actor_id=absent'))
    with owner.connect() as c:
        assert c.execute(text('SELECT actor_id,action FROM admin_audit_log')).all()==[('legacy','legacy')]
        assert c.scalar(text('SELECT count(*) FROM admin_audit_provenance'))==0
