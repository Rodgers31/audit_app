"""Actual complete supported Alembic chain, private grants and retained history."""
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from test_batch10_etl_mappings import mapping_url, MAPPINGS

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def migrated(mapping_url):
    from sqlalchemy.engine import make_url
    name = "batch10_mappings_migration_" + uuid4().hex
    admin = create_engine(mapping_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text('CREATE DATABASE "' + name + '"'))
    url = make_url(mapping_url).set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url)
    def migrate(operation, target):
        env = {"PATH": os.environ['PATH'], "DATABASE_URL": url, "PYTHON_DOTENV_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(BACKEND)}
        return subprocess.run([sys.executable, '-m', 'alembic', operation, target], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=90)
    try:
        yield engine, migrate
    finally:
        engine.dispose()
        with admin.connect() as c:
            c.execute(text('DROP DATABASE "' + name + '"'))
        admin.dispose()


def test_complete_chain_and_empty_round_trip_preserves_private_schema(migrated):
    engine, migrate = migrated
    result = migrate('upgrade','head')
    assert result.returncode == 0, result.stderr
    with engine.begin() as c:
        assert c.scalar(text('SELECT version_num FROM alembic_version')) == 'e554b10a0001'
        for role in ('anon','authenticated'):
            c.execute(text(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN CREATE ROLE {role}; END IF; END $$"))
        c.execute(text("INSERT INTO ingestion_jobs(domain,status,dry_run,started_at,items_processed,items_created,items_updated,errors,metadata) VALUES ('audits','PENDING',false,now(),0,0,0,'[]',jsonb_build_object('manual_trigger',true))"))
    for operation,target in [('downgrade','e583b9c9a001'),('upgrade','head')]:
        result = migrate(operation,target)
        assert result.returncode == 0, result.stderr
    with engine.connect() as c:
        assert c.scalar(text('SELECT status::text FROM ingestion_jobs')) == 'PENDING'
        for table in ('etl_dispatch_commands','etl_dispatch_domains','etl_dispatch_worker'):
            assert c.scalar(text('SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:t AS regclass)'),{'t':table}) is True
            for role in ('anon','authenticated'):
                for privilege in ('SELECT','INSERT','UPDATE','DELETE'):
                    assert c.scalar(text('SELECT has_table_privilege(:r,:t,:p)'), {'r':role,'t':table,'p':privilege}) is False
        for role in ('anon','authenticated'):
            with c.begin_nested():
                c.execute(text('SET LOCAL ROLE '+role))
                with pytest.raises(ProgrammingError,match='permission denied'):
                    with c.begin_nested():
                        c.execute(text('SELECT * FROM etl_dispatch_commands'))
                c.execute(text('RESET ROLE'))


def test_upgrade_refuses_ready_worker_preserves_old_oag_history(migrated):
    engine,migrate = migrated
    result=migrate('upgrade','e583b9c9a001')
    assert result.returncode==0,result.stderr
    with engine.begin() as c:
        c.execute(text("INSERT INTO etl_dispatch_worker VALUES (1,:g,now(),now()+interval '30 seconds',true)"),{'g':uuid4()})
        audit=c.scalar(text("INSERT INTO admin_audit_log(actor_id,actor_email,action,target_type,target_id,payload,created_at) VALUES ('inert','inert@example.invalid','etl.trigger','etl_command','inert','{}',now()) RETURNING id"))
        identity=uuid4()
        c.execute(text("INSERT INTO etl_dispatch_commands(id,actor_id,idempotency_key,source,domain,dry_run,generation,status,version,created_at,updated_at,audit_id) VALUES (:id,'inert',:key,'oag','audits',false,:g,'queued',1,now(),now(),:audit)"),{'id':identity,'key':uuid4(),'g':uuid4(),'audit':audit})
    failed=migrate('upgrade','head')
    assert failed.returncode!=0 and 'Stop dedicated worker' in failed.stderr
    with engine.begin() as c:
        assert c.scalar(text('SELECT version_num FROM alembic_version'))=='e583b9c9a001'
        c.execute(text('UPDATE etl_dispatch_worker SET ready=false'))
    result=migrate('upgrade','head')
    assert result.returncode==0,result.stderr
    with engine.connect() as c:
        assert c.scalar(text('SELECT id FROM etl_dispatch_commands'))==identity
        assert c.scalar(text('SELECT count(*) FROM etl_dispatch_domains'))==0


def test_schema_enforces_all_source_domain_pairs_and_downgrade_retains_history(migrated):
    engine,migrate=migrated
    result=migrate('upgrade','head')
    assert result.returncode==0,result.stderr
    with engine.begin() as c:
        for source in (*MAPPINGS,'opendata','cra'):
            for domain in MAPPINGS.values():
                identity=uuid4()
                statement=text("INSERT INTO etl_dispatch_commands(id,actor_id,idempotency_key,source,domain,dry_run,generation,status,version,created_at,updated_at,audit_id) VALUES (:id,'inert',:key,:source,:domain,false,:g,'queued',1,now(),now(),:audit)")
                def insert():
                    audit=c.scalar(text("INSERT INTO admin_audit_log(actor_id,actor_email,action,target_type,target_id,payload,created_at) VALUES ('inert','inert@example.invalid','etl.trigger','etl_command','inert','{}',now()) RETURNING id"))
                    c.execute(statement, {'id':identity,'key':uuid4(),'source':source,'domain':domain,'g':uuid4(),'audit':audit})
                if MAPPINGS.get(source)==domain:
                    insert()
                else:
                    with pytest.raises(IntegrityError,match='ck_etl_dispatch_mapping'):
                        with c.begin_nested(): insert()
    refused=migrate('downgrade','e583b9c9a001')
    assert refused.returncode!=0 and 'New mapping history exists' in refused.stderr
    with engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM etl_dispatch_commands'))==4
        assert c.scalar(text('SELECT version_num FROM alembic_version'))=='e554b10a0001'
