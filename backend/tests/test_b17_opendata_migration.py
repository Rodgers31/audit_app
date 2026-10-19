"""Actual additive mapping migration, stopped-worker/history refusal, prior ACL/RLS."""
import subprocess
import sys
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from batch11_native_sources_fixture.owned_postgres import command_environment
from test_b17_opendata_native import opendata_url, BACKEND

@pytest.fixture
def migrated(opendata_url):
    name = 'batch11_602_migration_' + uuid4().hex
    admin = create_engine(opendata_url, isolation_level='AUTOCOMMIT')
    with admin.connect() as c: c.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(opendata_url).set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url)
    def migrate(operation, target):
        return subprocess.run([sys.executable, *(['-O'] if sys.flags.optimize else []), '-m', 'alembic', operation, target], cwd=BACKEND, env=command_environment(url), capture_output=True, text=True, timeout=90)
    try: yield engine, migrate
    finally:
        engine.dispose()
        with admin.connect() as c: c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def insert(c, source, domain):
    identity=uuid4()
    audit=c.scalar(text("INSERT INTO admin_audit_log(actor_id,action,target_type,target_id,payload,created_at) VALUES ('inert','etl.trigger','etl_command',:id,'{}',now()) RETURNING id"),{'id':str(identity)})
    c.execute(text("INSERT INTO etl_dispatch_commands(id,actor_id,idempotency_key,source,domain,dry_run,generation,status,version,created_at,updated_at,audit_id) VALUES (:id,'inert',:key,:source,:domain,false,:g,'queued',1,now(),now(),:audit)"),{'id':identity,'key':uuid4(),'source':source,'domain':domain,'g':uuid4(),'audit':audit})


def test_prior_mappings_history_acl_rls_and_additive_roundtrip(migrated):
    engine,migrate=migrated
    assert migrate('upgrade','a705b15a0001').returncode==0
    with engine.begin() as c:
        for source,domain in [('oag','audits'),('treasury','fiscal_summary'),('cob','counties_budget'),('knbs','population'),('cra','cra')]: insert(c,source,domain)
        before=c.execute(text('SELECT * FROM etl_dispatch_commands ORDER BY id')).all()
        acl=c.execute(text("SELECT relname,relrowsecurity,relacl::text FROM pg_class WHERE relname IN ('etl_dispatch_commands','etl_dispatch_domains','etl_dispatch_worker') ORDER BY 1")).all()
        with pytest.raises(IntegrityError):
            with c.begin_nested(): insert(c,'opendata','opendata')
    assert migrate('upgrade','head').returncode==0
    with engine.begin() as c:
        assert c.scalar(text('SELECT version_num FROM alembic_version'))=='a756b20a0001'
        assert c.execute(text('SELECT * FROM etl_dispatch_commands ORDER BY id')).all()==before
        assert c.execute(text("SELECT relname,relrowsecurity,relacl::text FROM pg_class WHERE relname IN ('etl_dispatch_commands','etl_dispatch_domains','etl_dispatch_worker') ORDER BY 1")).all()==acl
        for source,domain in [('opendata','population'),('knbs','opendata'),('cra','opendata'),('opendata','cra')]:
            with pytest.raises(IntegrityError):
                with c.begin_nested(): insert(c,source,domain)
    assert migrate('downgrade','a705b15a0001').returncode==0
    assert migrate('upgrade','head').returncode==0


@pytest.mark.parametrize('operation,target,start', [('upgrade','head','a705b15a0001'),('downgrade','a705b15a0001','head')])
def test_ready_worker_refuses_schema_change(migrated,operation,target,start):
    engine,migrate=migrated
    assert migrate('upgrade',start).returncode==0
    with engine.begin() as c: c.execute(text("INSERT INTO etl_dispatch_worker VALUES (1,:g,now(),now()+interval '30 seconds',true)"),{'g':uuid4()})
    result=migrate(operation,target)
    assert result.returncode!=0 and 'Stop dedicated worker' in result.stderr


@pytest.mark.parametrize('kind',['domain','command'])
def test_new_history_prevents_downgrade(migrated,kind):
    engine,migrate=migrated
    assert migrate('upgrade','head').returncode==0
    with engine.begin() as c:
        if kind=='domain': c.execute(text("INSERT INTO etl_dispatch_domains(domain) VALUES ('opendata')"))
        else: insert(c,'opendata','opendata')
    result=migrate('downgrade','a705b15a0001')
    assert result.returncode!=0 and 'OpenData mapping history exists' in result.stderr
    with engine.connect() as c: assert c.scalar(text('SELECT version_num FROM alembic_version'))=='a756b20a0001'


def test_mapping_roundtrip_preserves_owned_media_history(migrated):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy.orm import Session
    from social.models import SocialMediaAsset
    from social.media.models import SocialMediaUpload, SocialMediaWriteOwner
    engine, migrate = migrated
    assert migrate('upgrade', 'a706b17a0001').returncode == 0
    actor, identity = uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    with Session(engine) as db, db.begin():
        db.add(SocialMediaAsset(id=identity, storage_provider='r2', bucket='inert', storage_key='original',
            original_filename='inert.png', created_by=actor))
        db.flush()
        db.add(SocialMediaUpload(asset_id=identity, actor_id=actor, initiation_key=uuid4(),
            request_hash='a'*64, quarantine_key='quarantine', declared_mime_type='image/png',
            declared_size=1, expires_at=now+timedelta(minutes=5), grant_renewal_deadline=now+timedelta(hours=1),
            reserved_bytes=2, reservation_released=0, quarantine_cleaned=0, finalization_settled=0))
        db.flush()
        db.add(SocialMediaWriteOwner(asset_id=identity, generation=uuid4(), binding_hash='b'*64, state='open'))
    def snapshot():
        with engine.connect() as connection:
            return {name: connection.execute(text('SELECT * FROM '+name+' ORDER BY 1')).all() for name in
                ('social_media_assets','social_media_uploads','social_media_write_owners','social_media_write_attempts')}
    before = snapshot()
    for operation, target in [('upgrade','head'), ('downgrade','a706b17a0001'), ('upgrade','head')]:
        assert migrate(operation, target).returncode == 0
        assert snapshot() == before
    refused = migrate('downgrade', 'a705b15a0001')
    assert refused.returncode != 0 and 'Owned write history prevents downgrade' in refused.stderr
    assert snapshot() == before
