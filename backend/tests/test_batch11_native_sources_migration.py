"""Actual reserved revision ordering and preservation on owned PostgreSQL."""
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from batch11_native_sources_fixture.owned_postgres import command_environment
from test_batch11_native_sources import cra_url, BACKEND


@pytest.fixture
def migrated(cra_url):
    name = "batch11_602_migration_" + uuid4().hex
    admin = create_engine(cra_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c: c.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(cra_url).set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url)
    def migrate(operation, target):
        return subprocess.run([sys.executable, "-m", "alembic", operation, target], cwd=BACKEND,
                              env=command_environment(url), text=True, capture_output=True, timeout=90)
    try: yield engine, migrate
    finally:
        engine.dispose()
        with admin.connect() as c: c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def test_reserved_migration_is_single_ordered_head_and_empty_round_trip(migrated):
    engine, migrate = migrated
    assert migrate("upgrade", "head").returncode == 0
    # Alembic heads has no positional target; execute its real command separately.
    result = subprocess.run([sys.executable, "-m", "alembic", "heads"], cwd=BACKEND,
                            env=command_environment(), text=True, capture_output=True, timeout=20)
    assert result.returncode == 0 and result.stdout.strip() == "e602b11a0001 (head)"
    with engine.connect() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "e602b11a0001"
        before = c.execute(text("SELECT c.relname,c.relrowsecurity,c.relacl::text FROM pg_class c WHERE c.relname IN ('etl_dispatch_commands','etl_dispatch_domains','etl_dispatch_worker') ORDER BY 1")).all()
    assert migrate("downgrade", "e554b10a0001").returncode == 0
    assert migrate("upgrade", "head").returncode == 0
    with engine.connect() as c:
        after = c.execute(text("SELECT c.relname,c.relrowsecurity,c.relacl::text FROM pg_class c WHERE c.relname IN ('etl_dispatch_commands','etl_dispatch_domains','etl_dispatch_worker') ORDER BY 1")).all()
        assert before == after and all(row.relrowsecurity is True for row in after)


def test_ready_worker_refuses_upgrade_and_prior_history_is_preserved(migrated):
    engine, migrate = migrated
    assert migrate("upgrade", "e554b10a0001").returncode == 0
    identity = uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO etl_dispatch_worker VALUES (1,:g,now(),now()+interval '30 seconds',true)"), {"g": uuid4()})
        audit = c.scalar(text("INSERT INTO admin_audit_log(actor_id,action,target_type,target_id,payload,created_at) VALUES ('inert','etl.trigger','etl_command',:id,'{}',now()) RETURNING id"), {"id": str(identity)})
        c.execute(text("INSERT INTO etl_dispatch_commands(id,actor_id,idempotency_key,source,domain,dry_run,generation,status,version,created_at,updated_at,audit_id) VALUES (:id,'inert',:key,'knbs','population',false,:g,'queued',1,now(),now(),:audit)"), {"id": identity, "key": uuid4(), "g": uuid4(), "audit": audit})
        before = c.execute(text("SELECT * FROM etl_dispatch_commands")).one()
    result = migrate("upgrade", "head")
    assert result.returncode != 0 and "Stop dedicated worker before changing native source mappings" in result.stderr
    with engine.begin() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "e554b10a0001"
        c.execute(text("UPDATE etl_dispatch_worker SET ready=false"))
    assert migrate("upgrade", "head").returncode == 0
    with engine.connect() as c: assert c.execute(text("SELECT * FROM etl_dispatch_commands")).one() == before


def test_new_pair_only_and_history_blocks_downgrade(migrated):
    engine, migrate = migrated
    assert migrate("upgrade", "head").returncode == 0
    with engine.begin() as c:
        c.execute(text("INSERT INTO etl_dispatch_domains(domain) VALUES ('cra')"))
        with pytest.raises(IntegrityError, match="ck_etl_dispatch_domain"):
            with c.begin_nested(): c.execute(text("INSERT INTO etl_dispatch_domains(domain) VALUES ('opendata')"))
        for source, domain in (("cra", "cra"), ("opendata", "cra"), ("cra", "revenue_by_source"), ("cra", "audits")):
            def insert():
                identity = uuid4()
                audit = c.scalar(text("INSERT INTO admin_audit_log(actor_id,action,target_type,target_id,payload,created_at) VALUES ('inert','etl.trigger','etl_command',:id,'{}',now()) RETURNING id"), {"id": str(identity)})
                c.execute(text("INSERT INTO etl_dispatch_commands(id,actor_id,idempotency_key,source,domain,dry_run,generation,status,version,created_at,updated_at,audit_id) VALUES (:id,'inert',:key,:source,:domain,false,:g,'queued',1,now(),now(),:audit)"), {"id": identity, "key": uuid4(), "source": source, "domain": domain, "g": uuid4(), "audit": audit})
            if (source, domain) == ("cra", "cra"): insert()
            else:
                with pytest.raises(IntegrityError, match="ck_etl_dispatch_mapping"):
                    with c.begin_nested(): insert()
    result = migrate("downgrade", "e554b10a0001")
    assert result.returncode != 0 and "CRA mapping history exists" in result.stderr
    with engine.connect() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "e602b11a0001"
        assert c.scalar(text("SELECT count(*) FROM etl_dispatch_commands")) == 1


def test_ready_worker_refuses_downgrade_and_every_allowed_pair_survives_upgrade(migrated):
    engine, migrate = migrated
    assert migrate("upgrade", "head").returncode == 0
    pairs = (("oag", "audits"), ("treasury", "fiscal_summary"), ("cob", "counties_budget"),
             ("knbs", "population"), ("cra", "cra"))
    with engine.begin() as c:
        for source, domain in pairs:
            identity = uuid4()
            audit = c.scalar(text("INSERT INTO admin_audit_log(actor_id,action,target_type,target_id,payload,created_at) VALUES ('inert','etl.trigger','etl_command',:id,'{}',now()) RETURNING id"), {"id": str(identity)})
            c.execute(text("INSERT INTO etl_dispatch_commands(id,actor_id,idempotency_key,source,domain,dry_run,generation,status,version,created_at,updated_at,audit_id) VALUES (:id,'inert',:key,:source,:domain,false,:g,'queued',1,now(),now(),:audit)"),
                      {"id": identity, "key": uuid4(), "source": source, "domain": domain, "g": uuid4(), "audit": audit})
        c.execute(text("DELETE FROM etl_dispatch_commands WHERE source='cra'"))
        c.execute(text("INSERT INTO etl_dispatch_worker VALUES (1,:g,now(),now()+interval '30 seconds',true)"), {"g": uuid4()})
        before = c.execute(text("SELECT * FROM etl_dispatch_commands ORDER BY id")).all()
    result = migrate("downgrade", "e554b10a0001")
    assert result.returncode != 0 and "Stop dedicated worker before changing native source mappings" in result.stderr
    with engine.begin() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "e602b11a0001"
        c.execute(text("UPDATE etl_dispatch_worker SET ready=false"))
    # With the worker stopped and no CRA history, downgrade keeps the four accepted pairs.
    assert migrate("downgrade", "e554b10a0001").returncode == 0
    with engine.connect() as c:
        assert c.execute(text("SELECT * FROM etl_dispatch_commands ORDER BY id")).all() == before
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "e554b10a0001"
