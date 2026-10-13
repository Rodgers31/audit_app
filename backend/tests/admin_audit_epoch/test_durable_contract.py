"""Transport refusal regressions; these do not certify PostgreSQL storage."""
from collections import namedtuple
from datetime import datetime, timezone, tzinfo
import importlib.util
from pathlib import Path

from fastapi import HTTPException
import pytest
from sqlalchemy.exc import MultipleResultsFound, NoResultFound

from services import admin_audit_storage as storage

SCOPE = '61100000-0000-4000-8000-000000000001'
KEY = bytes.fromhex('ab' * 32)
Constraint = namedtuple('Constraint', 'conname contype convalidated conkey confrelid confkey ready')
Role = namedtuple('Role', 'rolsuper rolbypassrls')
Table = namedtuple('Table', 'ordinary relrowsecurity owns mutates writes_column rls resolves')
Trigger = namedtuple('Trigger', 'relname tgname tgenabled tgtype prosrc prosecdef proconfig owned unconditional noargs')
Function = namedtuple('Function', 'prosrc prosecdef proconfig owned')
State = namedtuple('State', 'singleton schema_version incarnation system_identifier database_oid timeline certified')


class Result:
    def __init__(self, rows): self.rows = rows
    def all(self): return self.rows
    def one(self):
        if not self.rows: raise NoResultFound()
        if len(self.rows) != 1: raise MultipleResultsFound()
        return self.rows[0]


class CatalogTransport:
    """Literal valid catalog result plus one hostile transport mutation."""
    def __init__(self):
        self.role = Role(False, False)
        self.constraints = [
            Constraint('admin_audit_provenance_audit_id_fkey','f',True,'{1}','admin_audit_log','{1}',True),
            Constraint('admin_audit_provenance_pkey','p',True,'{1}','-',None,True)]
        self.policy_permissive = True
        self.state = State(True,1,SCOPE,'111',1,1,True)
        self.prepared = self.unknown = self.public_authority = self.sequence_authority = False
        self.isolation='repeatable read'
        self.triggers = [
            Trigger('admin_audit_log','audit_log_capture','A',5,storage.CAPTURE_BODY,True,['search_path=pg_catalog'],True,True,True),
            Trigger('admin_audit_log','audit_log_immutable','A',58,storage.IMMUTABLE_BODY,False,['search_path=pg_catalog'],True,True,True),
            Trigger('admin_audit_provenance','audit_provenance_immutable','A',58,storage.IMMUTABLE_BODY,False,['search_path=pg_catalog'],True,True,True)]

    def scalar(self, statement, params=None):
        sql = str(statement)
        if 'transaction_isolation' in sql:return self.isolation
        if 'pg_prepared_xacts' in sql: return self.prepared
        if 'LEFT JOIN public.admin_audit_provenance' in sql: return self.unknown
        if 'has_schema_privilege' in sql: return False
        if 'has_sequence_privilege' in sql:return self.sequence_authority
        if "r.rolname IN ('anon','authenticated')" in sql: return self.public_authority
        raise AssertionError('Unexpected transport query: ' + sql)

    def execute(self, statement, params=None):
        sql = str(statement)
        if sql.startswith(('SET LOCAL','LOCK TABLE')): return Result([])
        if 'rolsuper,rolbypassrls' in sql: return Result([self.role])
        if 'AS ordinary' in sql: return Result([Table(True,True,False,False,False,True,True)])
        if 'FROM pg_attribute' in sql:
            cols = [('audit_id','integer',True),('root_xid','xid8',True),('incarnation','uuid',True)]
            if "'public.admin_audit_storage'::regclass" in sql:
                cols = [(n,t,True) for n,t in [('singleton','boolean'),('schema_version','integer'),('incarnation','uuid'),('system_identifier','text'),('database_oid','oid'),('timeline','integer'),('certified','boolean')]]
            return Result(cols)
        if 'FROM pg_constraint' in sql:
            if "'public.admin_audit_storage'::regclass" in sql:
                return Result([('admin_audit_storage_pkey',True,'PRIMARY KEY (singleton)'),('ck_audit_storage_singleton',True,'CHECK (singleton)'),('ck_audit_storage_version',True,'CHECK ((schema_version = 1))')])
            if "'public.admin_audit_log'::regclass" in sql:
                return Result([('admin_audit_log_pkey',True,'PRIMARY KEY (id)'),('ck_admin_audit_positive_id',True,'CHECK ((id > 0))')])
            return Result(self.constraints)
        if 'FROM pg_policy' in sql:
            return Result({
                'public.admin_audit_log': [('audit_log_read','r',self.policy_permissive,['audit_log_reader','audit_log_writer'],'true',None),('audit_log_write','a',True,['audit_log_writer'],None,'true')],
                'public.admin_audit_provenance': [('audit_provenance_read','r',self.policy_permissive,['audit_log_reader'],'true',None)],
                'public.admin_audit_storage': [('audit_storage_read','r',self.policy_permissive,['audit_log_reader'],'true',None)],
            }[params['t']])
        if 'FROM pg_trigger' in sql: return Result(self.triggers)
        if 'FROM pg_proc' in sql: return Result([Function(storage.IDENTITY_BODY,True,['search_path=pg_catalog'],True)])
        if sql.startswith('SELECT singleton,'): return Result([self.state])
        if 'SELECT * FROM public.audit_log_identity()' in sql: return Result([('111',1,1,False)])
        raise AssertionError('Unexpected transport query: ' + sql)


@pytest.fixture
def authority(monkeypatch):
    monkeypatch.setenv('ADMIN_AUDIT_INCARNATION', SCOPE)
    monkeypatch.setenv('ADMIN_AUDIT_BOOKMARK_KEY', KEY.hex())


def test_literal_catalog_transport_control(authority):
    assert storage.capability(CatalogTransport()) == (SCOPE, KEY)


def test_later_sequence_authority_drift_refuses(authority):
    catalog=CatalogTransport();catalog.sequence_authority=True
    with pytest.raises(HTTPException) as failure:
        storage.capability(catalog)
    assert failure.value.status_code==503


@pytest.mark.parametrize('surface', ['validated','ready','policy','role','version','prepared','unknown','public'])
@pytest.mark.parametrize('value', [None, 0, 1, 'false'])
def test_ambiguous_catalog_transport_refuses(authority, surface, value):
    db = CatalogTransport()
    if surface in ('validated','ready'):
        db.constraints[0] = db.constraints[0]._replace(**{'convalidated' if surface=='validated' else 'ready':value})
    elif surface=='policy': db.policy_permissive=value
    elif surface=='role': db.role=db.role._replace(rolsuper=value)
    elif surface=='version': db.state=db.state._replace(schema_version=True if value==1 else value)
    else: setattr(db, {'public':'public_authority'}.get(surface,surface),value)
    with pytest.raises(HTTPException) as exc: storage.capability(db)
    assert exc.value.status_code==503


def test_duplicate_trigger_cannot_replace_missing_protection(authority):
    db=CatalogTransport();db.triggers[2]=db.triggers[1]
    with pytest.raises(HTTPException) as exc: storage.capability(db)
    assert exc.value.status_code==503


@pytest.mark.parametrize('isolation',['read committed','serializable',None,False])
def test_unknown_or_different_read_population_refuses(authority,isolation):
    db=CatalogTransport();db.isolation=isolation
    with pytest.raises(HTTPException) as exc:storage.capability(db)
    assert exc.value.status_code==503


class NoOffset(tzinfo):
    def utcoffset(self, dt): return None


@pytest.mark.parametrize('field,value', [
    ('scope','invalid'),('visible','2:3:'),('visible','3:5:4,3'),
    ('captured',datetime(2026,1,1)),('captured',datetime(2026,1,1,tzinfo=NoOffset())),
    ('ceiling',True),('ceiling',-1),('ceiling',float('nan')),('ceiling',2**31),
    ('actor_id',''),('actor_id','a'*65),('key',b''),('key','ab'*32),
])
def test_issuer_rejects_invalid_bound_fields(field,value):
    values=dict(scope=SCOPE,visible='4294967300:4294967301:',captured=datetime(2026,1,1,tzinfo=timezone.utc),ceiling=1,actor_id='inert-admin',key=KEY)
    values[field]=value
    with pytest.raises(HTTPException): storage.issue_bookmark(**values)


def test_full_epoch_bookmark_round_trip():
    token=storage.issue_bookmark(SCOPE,'4294967300:4294967305:4294967301',datetime(2026,1,1,tzinfo=timezone.utc),1,'inert-admin',KEY)
    assert storage.bookmark(token)[:2]==(SCOPE,'4294967300:4294967305:4294967301')


@pytest.mark.parametrize('url',['sqlite:///:memory:','mysql://inert:inert@127.0.0.1/inert'])
def test_reader_engine_refuses_other_database_dialects(url):
    with pytest.raises(HTTPException) as exc: storage.reader_engine(url)
    assert exc.value.status_code==503


def migration_module():
    path=Path(__file__).resolve().parents[2]/'alembic/versions/a611b12a0001_durable_admin_audit.py'
    spec=importlib.util.spec_from_file_location('audit_migration_contract',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('identity',[(None,1,1,False),('111',True,1,False),('111',1,-1,False),('111',1,1,0)])
def test_migration_refuses_malformed_identity_before_ddl(monkeypatch,identity):
    module=migration_module()
    class DB:
        def scalar(self,*args): return False
        def execute(self,*args): return Result([identity])
    emitted=[]
    monkeypatch.setattr(module,'prepare',lambda:DB())
    monkeypatch.setattr(module.op,'execute',emitted.append)
    with pytest.raises(RuntimeError,match='identity cannot be verified'): module.upgrade()
    assert emitted==[]


@pytest.mark.parametrize('role',[(),(False,),tuple(False for _ in range(7)),(0,False,False,False,False,False)])
def test_migration_refuses_partial_or_ambiguous_role_transport(monkeypatch,role):
    module=migration_module()
    class DB:
        def scalar(self,*args): return False
        def execute(self,query,*args):
            return Result([role] if 'FROM pg_roles' in str(query) else [('111',1,1,False)])
    emitted=[]
    monkeypatch.setattr(module,'prepare',lambda:DB())
    monkeypatch.setattr(module.op,'execute',emitted.append)
    with pytest.raises(RuntimeError,match='Unsafe existing audit role'): module.upgrade()
    assert not any('CREATE TABLE' in sql for sql in emitted)


def test_empty_filter_keeps_population_ceiling_for_transfer():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from database import get_db
    from models import AdminAuditLog
    from routers.admin_audit_log import router
    from supabase_auth import AdminUser, get_current_user
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    factory=sessionmaker(bind=engine)
    try:
        AdminAuditLog.__table__.create(engine)
        with factory() as db:
            db.add(AdminAuditLog(actor_id='present',action='etl.trigger',payload={},created_at=datetime.now(timezone.utc)))
            db.commit()
        app=FastAPI();app.include_router(router)
        app.dependency_overrides[get_current_user]=lambda:AdminUser(id='inert-admin',email=None,roles=['admin'])
        def sessions():
            with factory() as db:yield db
        app.dependency_overrides[get_db]=sessions
        with TestClient(app,raise_server_exceptions=False) as client:
            empty=client.get('/api/v1/admin/audit-log?days=0&actor_id=absent')
            assert empty.status_code==200,empty.text
            assert empty.json()['total']==0 and empty.json()['snapshot_id']==1
            transferred=client.get('/api/v1/admin/audit-log',params={'days':0,'snapshot_id':empty.json()['snapshot_id'],'as_of':empty.json()['as_of']})
            assert transferred.status_code==200,transferred.text
            assert transferred.json()['total']==1
    finally:engine.dispose()
