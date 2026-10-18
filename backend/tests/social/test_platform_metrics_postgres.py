"""Owned PG17 schema/transport/reservation/history controls. No live APIs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from threading import Event

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from social.models import SocialAccount, SocialAuditEvent
from social.service import SocialError
from social.studio.analytics import collect, observations
from social.studio.models import MetricCollection, MetricObservation
from social.studio.platform_metrics import parse_counts
from test_platform_metrics import platform_fixture, body


def owned_url(raw):
    if not isinstance(raw,str) or '?' in raw:
        raise ValueError('Use owned loopback55476/b17_metrics fixture')
    url=make_url(raw)
    if (url.drivername!='postgresql+psycopg2' or url.host!='127.0.0.1' or url.port!=55476
            or url.database!='b17_metrics' or url.username!='metrics17' or url.query):
        raise ValueError('Use owned loopback55476/b17_metrics fixture')
    return url.set(query={'hostaddr':'127.0.0.1'})


@pytest.fixture(scope='module')
def metrics_pg():
    raw=os.environ.get('B17_METRICS_DATABASE_URL')
    if raw is None:pytest.skip('Owned B17 PostgreSQL fixture must be explicitly supplied')
    engine=create_engine(owned_url(raw),pool_size=2,max_overflow=0,hide_parameters=True,
        connect_args={'options':'-clock_timeout=5000 -cstatement_timeout=15000'})
    with engine.begin() as conn:
        assert conn.scalar(text('SHOW server_version_num')).startswith('17')
        assert conn.scalar(text("SELECT count(*) FROM pg_tables WHERE schemaname='public'"))==0
        scripts=ScriptDirectory(str(Path(__file__).parents[2]/'alembic'))
        with Operations.context(MigrationContext.configure(conn)):
            for revision in reversed(list(scripts.walk_revisions(base='base',head='a705b15a0001'))):revision.module.upgrade()
        for table in ['social_metric_collections','social_metric_observations','social_platform_credentials','social_audit_events']:
            assert conn.scalar(text('SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:name AS regclass)'),{'name':table})
    try:yield engine
    finally:
        engine.dispose()
        cleanup=create_engine(owned_url(raw),pool_size=1,max_overflow=0)
        with cleanup.begin() as conn:
            conn.execute(text('DROP SCHEMA public CASCADE'))
            conn.execute(text('CREATE SCHEMA public'))
        cleanup.dispose()


@pytest.fixture
def pg(metrics_pg):
    with metrics_pg.begin() as conn:
        tables=conn.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'social_%'" )).all()
        conn.execute(text('TRUNCATE '+','.join('"'+t+'"' for t in tables)+' CASCADE'))
    return metrics_pg


def seed(pg,platform):
    with Session(pg,expire_on_commit=False) as db:
        target,runtime,cmd=platform_fixture(db,platform)
        return target.id,runtime,cmd


def inert_read(port,req):
    raw=body(port.platform)
    return parse_counts(raw if port.platform=='threads' else raw['data'],port.platform,req.remote_id,datetime.now(timezone.utc))


@pytest.mark.parametrize('platform',['threads','tiktok'])
def test_actual_pg_concurrency_one_reservation_and_restart(pg,monkeypatch,platform):
    ident,runtime,cmd=seed(pg,platform)
    entered,release=Event(),Event()
    def read(port,req):
        entered.set()
        if not release.wait(5):raise RuntimeError('Fixture barrier timeout')
        return inert_read(port,req)
    monkeypatch.setattr('social.studio.analytics.bounded_collect',read)
    factory=sessionmaker(bind=pg)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(collect,factory,ident,runtime,enabled=True,authorization=cmd)
        assert entered.wait(5)
        # The account reservation committed and DB connection is free during I/O.
        with pytest.raises(SocialError,match='METRICS_COLLECTION_HELD'):
            collect(factory,ident,runtime,enabled=True,authorization=cmd)
        release.set()
        result=first.result(5)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(MetricCollection))==1
        assert db.scalar(select(func.count()).select_from(MetricObservation))==6
        history=observations(db,ident)
        assert history['collections'][0]['id']==str(result)
        assert history['collections'][0]['state']=='collected'
        assert db.get(SocialAccount,cmd.account_id).publishing_enabled is False
    with pytest.raises(IntegrityError),pg.begin() as conn:
        conn.execute(text("UPDATE social_metric_observations SET metric='{}'"))


@pytest.mark.parametrize('table,phase,mode',[
    ('social_metric_collections','reserve','suppress'),('social_metric_collections','reserve','backdate'),('social_audit_events','reserve','suppress'),
    ('social_audit_events','reserve','alter'),('social_metric_collections','finish','suppress'),
    ('social_metric_observations','finish','suppress'),('social_metric_observations','finish','alter'),
    ('social_audit_events','finish','suppress'),('social_audit_events','finish','alter')])
def test_actual_required_write_refusal(pg,monkeypatch,table,phase,mode):
    ident,runtime,cmd=seed(pg,'threads')
    def attack():
        effect="NEW.created_at='2000-01-01'::timestamptz; RETURN NEW;" if mode=='backdate' else 'RETURN NULL;' if mode=='suppress' else ("NEW.metric=jsonb_set(NEW.metric,'{value}','true'::jsonb); RETURN NEW;" if table=='social_metric_observations' else "NEW.details='{}'::jsonb; RETURN NEW;")
        with pg.begin() as conn:
            conn.execute(text('CREATE FUNCTION b17_metrics_hostile() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN '+effect+' END $$'))
            conn.execute(text('CREATE TRIGGER b17_metrics_hostile BEFORE '+('UPDATE' if table=='social_metric_collections' and phase=='finish' else 'INSERT')+' ON '+table+' FOR EACH ROW EXECUTE FUNCTION b17_metrics_hostile()'))
    calls=[]
    if phase=='reserve':attack()
    def read(port,req):
        calls.append(1)
        if phase=='finish':attack()
        return inert_read(port,req)
    monkeypatch.setattr('social.studio.analytics.bounded_collect',read)
    try:
        with pytest.raises((SocialError,IntegrityError,StaleDataError)):
            collect(sessionmaker(bind=pg),ident,runtime,enabled=True,authorization=cmd)
        with Session(pg) as db:
            assert db.scalar(select(func.count()).select_from(MetricObservation))==0
            assert db.scalar(select(func.count()).select_from(MetricCollection))==(1 if phase=='finish' else 0)
            assert db.scalar(select(func.count()).select_from(SocialAuditEvent).where(SocialAuditEvent.action=='metrics.collected'))==0
        assert len(calls)==(1 if phase=='finish' else 0)
    finally:
        with pg.begin() as conn:
            conn.execute(text('DROP TRIGGER b17_metrics_hostile ON '+table))
            conn.execute(text('DROP FUNCTION b17_metrics_hostile()'))


@pytest.mark.parametrize('platform',['threads','tiktok'])
def test_actual_interrupt_is_held_after_hour_and_restart(pg,monkeypatch,platform):
    ident,runtime,cmd=seed(pg,platform)
    def interrupt(*_):raise KeyboardInterrupt()
    monkeypatch.setattr('social.studio.analytics.bounded_collect',interrupt)
    factory=sessionmaker(bind=pg)
    with pytest.raises(KeyboardInterrupt):collect(factory,ident,runtime,enabled=True,authorization=cmd)
    with factory() as db,db.begin():
        row=db.scalar(select(MetricCollection));row.created_at=datetime.now(timezone.utc)-timedelta(days=1)
    with pytest.raises(SocialError,match='METRICS_COLLECTION_HELD'):collect(factory,ident,runtime,enabled=True,authorization=cmd)
