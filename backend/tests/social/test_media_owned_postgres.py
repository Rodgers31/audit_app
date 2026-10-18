"""Actual additive migrations, durable proof/audit and forced writer races."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Event
from urllib.parse import urlsplit
from uuid import uuid4
import os

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, InvalidRequestError
from sqlalchemy.orm import Session

from social.media.config import MediaConfig
from social.media.inspection import LocalInspector
from social.media.models import SocialMediaWriteOwner, SocialMediaWriteAttempt, SocialMediaUpload
from social.media.owned_writes import reconcile_owned
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from social.models import SocialAuditEvent, SocialMediaAsset
from social.service import SocialError
from test_media_owned_writes import concrete_runtime, failed_intent, scope, totals
from test_media_support import ACTOR, ENDPOINT, intent, png


@pytest.fixture(scope='module')
def template():
    value=os.getenv('B17_MEDIA_TEST_DATABASE_URL')
    if not value:
        pytest.skip('Owned B17 media PostgreSQL prerequisite is not assigned')
    target=urlsplit(value)
    if (target.scheme!='postgresql+psycopg2' or target.hostname!='127.0.0.1'
            or target.port!=55417 or target.username!='b17_media' or target.password
            or target.path!='/b17_media_test' or target.query or target.fragment):
        raise ValueError('Refused an unowned B17 media fixture')
    admin=create_engine(value,isolation_level='AUTOCOMMIT',pool_size=2,max_overflow=0)
    name='b17_media_template_'+uuid4().hex
    with admin.connect() as conn: conn.execute(text('CREATE DATABASE '+name))
    engine=create_engine(make_url(value).set(database=name),pool_size=2,max_overflow=0)
    scripts=ScriptDirectory(str(Path(__file__).resolve().parents[2]/'alembic'))
    try:
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            for rev in reversed(list(scripts.walk_revisions(base='base',head='a706b17a0001'))):
                rev.module.upgrade()
        engine.dispose()
        yield value,admin,name
    finally:
        engine.dispose()
        with admin.connect() as conn: conn.execute(text('DROP DATABASE '+name))
        admin.dispose()


@pytest.fixture
def pg_owned(template,monkeypatch):
    value,admin,source=template
    name='b17_media_case_'+uuid4().hex
    with admin.connect() as conn: conn.execute(text('CREATE DATABASE '+name+' TEMPLATE '+source))
    engine=create_engine(make_url(value).set(database=name),pool_size=2,max_overflow=0,
        connect_args={'options':'-c statement_timeout=10000 -c lock_timeout=2000'})
    cfg=MediaConfig(enabled=True,endpoint=ENDPOINT,bucket='media-test',access_key='fixture',secret_key='fixture')
    db=Session(engine,expire_on_commit=False)
    svc=MediaService(db,MediaRuntime(cfg,None,LocalInspector(cfg)))
    io=concrete_runtime(svc,monkeypatch)
    try: yield svc,io,engine
    finally:
        db.close(); io.sdk.close(); engine.dispose()
        with admin.connect() as conn: conn.execute(text('DROP DATABASE '+name))


def test_pg_owned_positive_durable_audit_replay_and_immutable_history(pg_owned,monkeypatch):
    svc,io,engine=pg_owned
    identity=failed_intent(svc,io,monkeypatch)
    body=scope(svc,identity); key=uuid4()
    result=reconcile_owned(svc,ACTOR,identity,key,body,uuid4())
    assert result.state=='archived'
    with Session(engine,expire_on_commit=False) as fresh:
        restarted=MediaService(fresh,svc.runtime)
        assert reconcile_owned(restarted,ACTOR,identity,key,body,uuid4())==result
        with fresh.begin():
            event=fresh.scalar(select(SocialAuditEvent).where(SocialAuditEvent.action=='media.writes_reconciled'))
            assert event.details['receipt_id']==str(key)
            assert fresh.get(SocialMediaWriteOwner,identity).state=='settled'
    for statement in (
        'DELETE FROM social_media_write_owners',
        'DELETE FROM social_media_write_attempts',
        "UPDATE social_media_write_owners SET state='open'",
        "UPDATE social_media_write_attempts SET state='issued'",
        "UPDATE social_media_write_owners SET binding_hash=repeat('a',64)",
        'DELETE FROM social_media_uploads',
    ):
        with engine.begin() as conn,pytest.raises(DBAPIError): conn.execute(text(statement))
    with engine.begin() as conn:
        for table in ('social_media_write_owners','social_media_write_attempts'):
            assert conn.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:table AS regclass)"),{'table':table}).scalar() is True
            assert conn.execute(text("SELECT EXISTS(SELECT 1 FROM pg_class c,LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid=CAST(:table AS regclass) AND a.grantee=0)"),{'table':table}).scalar() is False
    assert totals(svc,identity)==(1,0,2*len(png()),1)


@pytest.mark.parametrize('timing,mutation',[
    ('BEFORE','RETURN NULL;'),
    ('BEFORE',"NEW.details=jsonb_set(NEW.details,'{grant_epoch}','true'::jsonb); RETURN NEW;"),
    ('DEFERRED',"UPDATE social_media_uploads SET grant_settled_epoch=0; RETURN NEW;"),
    ('DEFERRED',"UPDATE social_media_budgets SET bytes_used=0,pending_count=0; RETURN NEW;"),
])
def test_pg_suppressed_altered_deferred_persistence_refuses_success(pg_owned,monkeypatch,timing,mutation):
    svc,io,engine=pg_owned
    identity=failed_intent(svc,io,monkeypatch)
    with engine.begin() as conn:
        conn.execute(text('CREATE FUNCTION b17_alter() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN '+mutation+' END $$'))
        if timing=='DEFERRED':
            conn.execute(text("CREATE CONSTRAINT TRIGGER b17_alter AFTER INSERT ON social_audit_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.action='media.writes_reconciled') EXECUTE FUNCTION b17_alter()"))
        else:
            conn.execute(text("CREATE TRIGGER b17_alter BEFORE INSERT ON social_audit_events FOR EACH ROW WHEN (NEW.action='media.writes_reconciled') EXECUTE FUNCTION b17_alter()"))
    with pytest.raises(SocialError):
        reconcile_owned(svc,ACTOR,identity,uuid4(),scope(svc,identity),uuid4())
    with Session(engine) as fresh,fresh.begin():
        assert fresh.get(SocialMediaWriteOwner,identity).state=='closed'
        assert fresh.get(SocialMediaUpload,identity).grant_settled_epoch==0
        assert fresh.scalar(select(SocialAuditEvent).where(SocialAuditEvent.action=='media.writes_reconciled')) is None


def test_pg_delayed_signer_cancel_and_racing_reconcile_cannot_escape(pg_owned,monkeypatch):
    svc,io,engine=pg_owned
    entered,release=Event(),Event()
    original=io.sdk.generate_presigned_url
    def delayed(*args,**kw):
        entered.set()
        if not release.wait(8): raise RuntimeError('test barrier timed out')
        return original(*args,**kw)
    monkeypatch.setattr(io.sdk,'generate_presigned_url',delayed)
    def run():
        with Session(engine,expire_on_commit=False) as db:
            try: return MediaService(db,svc.runtime).initiate(ACTOR,uuid4(),intent(),uuid4())
            except SocialError as error: return error.code
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(run)
        assert entered.wait(5)
        assert future.cancel() is False  # caller cancellation did not stop I/O
        with svc.db.begin(): identity=svc.db.scalar(select(SocialMediaUpload.asset_id))
        try:
            with pytest.raises(SocialError):
                reconcile_owned(svc,ACTOR,identity,uuid4(),scope(svc,identity),uuid4())
        finally: release.set()
        assert future.result(5)=='MEDIA_GRANT_FENCED'
    assert totals(svc,identity)==(0,0,2*len(png()),1)
    with svc.db.begin():
        assert svc.db.get(SocialMediaWriteOwner,identity).state=='closed'


def test_pg_delayed_finalizer_after_expiry_cannot_mark_ready_or_release(pg_owned,monkeypatch):
    svc,io,engine=pg_owned
    grant=svc.initiate(ACTOR,uuid4(),intent(),uuid4())
    with svc.db.begin():
        io.objects[svc.db.get(SocialMediaUpload,grant.asset.id).quarantine_key]=(png(),'image/png',{})
    entered,release=Event(),Event()
    original=io.sdk.put_object
    def delayed(**kw):
        entered.set()
        if not release.wait(8): raise RuntimeError('test barrier timed out')
        return original(**kw)
    monkeypatch.setattr(io.sdk,'put_object',delayed)
    def complete():
        with Session(engine,expire_on_commit=False) as db:
            try: return MediaService(db,svc.runtime).complete(ACTOR,grant.asset.id,uuid4(),1,uuid4())
            except SocialError as error: return error.code
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(complete)
        assert entered.wait(5)
        assert future.cancel() is False
        with svc.db.begin(): svc.db.get(SocialMediaAsset,grant.asset.id).lease_expires_at=svc.now()-timedelta(seconds=1)
        try:
            with pytest.raises(SocialError):
                reconcile_owned(svc,ACTOR,grant.asset.id,uuid4(),scope(svc,grant.asset.id),uuid4())
            assert svc.cleanup()==0
        finally: release.set()
        assert future.result(5)=='MEDIA_LEASE_LOST'
    with svc.db.begin():
        assert svc.db.scalar(select(SocialMediaWriteAttempt.state).where(SocialMediaWriteAttempt.kind=='finalize'))=='completed'
        assert svc.db.get(SocialMediaAsset,grant.asset.id).state!='ready'
    assert totals(svc,grant.asset.id)==(0,0,2*len(png()),1)


def test_pg_owned_guard_follows_the_installing_schema(pg_owned,monkeypatch):
    svc,io,engine=pg_owned
    schema='b17_namespace_'+uuid4().hex
    with engine.begin() as conn: conn.execute(text('CREATE SCHEMA '+schema))
    scoped=create_engine(engine.url,pool_size=2,max_overflow=0,
        connect_args={'options':'-csearch_path='+schema})
    scripts=ScriptDirectory(str(Path(__file__).resolve().parents[2]/'alembic'))
    try:
        with scoped.begin() as conn,Operations.context(MigrationContext.configure(conn)):
            for revision in ('f38c61a9d203','c96d13e2f411','a42b86e1d310',
                    'b73e19a4f602','a490b15a0001','a701b15a0001','a706b17a0001'):
                scripts.get_revision(revision).module.upgrade()
        with Session(scoped,expire_on_commit=False) as db:
            nested=MediaService(db,svc.runtime)
            identity=failed_intent(nested,io,monkeypatch)
            assert reconcile_owned(nested,ACTOR,identity,uuid4(),scope(nested,identity),uuid4()).state=='archived'
            assert totals(nested,identity)==(1,0,2*len(png()),1)
        with engine.begin() as conn:
            assert conn.execute(text('SELECT count(*) FROM public.social_media_write_owners')).scalar()==0
    finally:
        scoped.dispose()
        with engine.begin() as conn: conn.execute(text('DROP SCHEMA '+schema+' CASCADE'))


@pytest.mark.parametrize('point',['before_commit','after_commit'])
def test_pg_lost_commit_ack_or_backend_loss_never_reports_false_completion(pg_owned,monkeypatch,point):
    svc,io,engine=pg_owned
    identity=failed_intent(svc,io,monkeypatch)
    body=scope(svc,identity); key=uuid4(); fired=[]
    def lose(session):
        if fired or not any(isinstance(obj,SocialMediaWriteOwner) and obj.state=='settled'
                for obj in session.identity_map.values()): return
        fired.append(point)
        if point=='before_commit':
            pid=session.connection().execute(text('SELECT pg_backend_pid()')).scalar_one()
            with engine.begin() as other: other.execute(text('SELECT pg_terminate_backend(:pid)'),{'pid':pid})
        else:
            raise RuntimeError('owned control loses acknowledgement after actual commit')
    event.listen(svc.db,point,lose)
    try:
        with pytest.raises((DBAPIError,InvalidRequestError,SocialError,RuntimeError)):
            reconcile_owned(svc,ACTOR,identity,key,body,uuid4())
    finally:
        event.remove(svc.db,point,lose)
        svc.db.close()
    assert fired==[point]
    with Session(engine,expire_on_commit=False) as fresh:
        restarted=MediaService(fresh,svc.runtime)
        if point=='after_commit':
            assert reconcile_owned(restarted,ACTOR,identity,key,body,uuid4()).state=='archived'
        else:
            with fresh.begin():
                assert fresh.get(SocialMediaWriteOwner,identity).state=='closed'
                assert fresh.get(SocialMediaUpload,identity).grant_settled_epoch==0
        assert totals(restarted,identity)[1:]==(0,2*len(png()),1)
    assert io.calls==[]
