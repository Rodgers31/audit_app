"""Additive ownership migration on the explicit owned PostgreSQL fixture."""
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from test_batch7_etl_postgres import pg, post, URL
from test_batch7_etl_migration import migrate
from admin_etl_dispatch_worker import claim, finish, register_worker
from seeding.exclusion import reserve

pytestmark = pytest.mark.skipif(not URL, reason="Owned PostgreSQL required")


def test_upgrade_preserves_retained_batch7_claim_and_private_permissions(pg):
    client, factory, engine = pg
    assert migrate("e554d7c9a001", "downgrade").returncode == 0
    generation = register_worker(factory)
    identity = post(client, generation).json()["command"]["id"]
    token = str(uuid4())
    with engine.begin() as conn:
        conn.execute(text("UPDATE etl_dispatch_commands SET status='running',started_at=clock_timestamp(),updated_at=clock_timestamp(),claim_token=:token,version=2 WHERE id=:id"), {"token": token, "id": identity})
        conn.execute(text("UPDATE etl_dispatch_domains SET command_id=:id,claim_token=:token WHERE domain='audits'"), {"token": token, "id": identity})
        for role in ("anon", "authenticated"):
            conn.execute(text(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN CREATE ROLE {role}; END IF; END $$"))
    result = migrate("head", "upgrade")
    assert result.returncode == 0, result.stderr
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id::text,kind,command_id::text,returned_at,released_at FROM seeding_domain_claims")).one()
        assert tuple(row) == (token, "dispatch", identity, None, None)
        assert conn.scalar(text("SELECT relrowsecurity FROM pg_class WHERE relname='seeding_domain_claims'")) is True
        for role in ("anon", "authenticated"):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                assert conn.scalar(text("SELECT has_table_privilege(:role,'seeding_domain_claims',:privilege)"), {"role": role, "privilege": privilege}) is False
        assert conn.scalar(text("SELECT count(*) FROM ingestion_jobs")) == 0
    result = migrate("e554d7c9a001", "downgrade")
    assert result.returncode != 0 and "Seeding ownership history exists" in result.stderr
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL")) == 1
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "e572b8c9a001"


def test_native_released_history_cannot_be_discarded_by_downgrade(pg):
    _, _, engine = pg
    # An inert terminal receipt retains the exact run's history even after release.
    with engine.begin() as conn:
        job_id = conn.scalar(text("INSERT INTO ingestion_jobs(domain,status,dry_run,started_at,finished_at,items_processed,items_created,items_updated,errors,metadata) VALUES ('audits','COMPLETED',false,now(),now(),0,0,0,'[]','{}') RETURNING id"))
        conn.execute(text("INSERT INTO seeding_domain_claims(id,domain,kind,acquired_at,entered_at,entry_id,returned_at,released_at,job_id) VALUES (:id,'audits','native',now(),now(),:entry,now(),now(),:job)"), {"id": str(uuid4()), "entry": str(uuid4()), "job": job_id})
    result = migrate("e554d7c9a001", "downgrade")
    assert result.returncode != 0 and "Seeding ownership history exists" in result.stderr
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NOT NULL")) == 1


@pytest.mark.parametrize("columns,values", [
    # Native ownership is entered as it is acquired; a return needs an entry.
    ("kind,acquired_at", "'native',now()"),
    ("kind,command_id,acquired_at,returned_at,job_id", "'dispatch',:command,now(),now(),:job"),
    ("kind,acquired_at,entered_at", "'native',now(),now()"),
    ("kind,acquired_at,entered_at,entry_id", "'native',now(),now()-interval '1 hour',:entry"),
])
def test_entry_receipt_shapes_are_enforced_by_schema(pg, columns, values):
    client, factory, engine = pg
    generation = register_worker(factory)
    command = post(client, generation).json()["command"]["id"]
    with engine.begin() as conn:
        job = conn.scalar(text("INSERT INTO ingestion_jobs(domain,status,dry_run,started_at,finished_at,items_processed,items_created,items_updated,errors,metadata) VALUES ('audits','COMPLETED',false,now(),now(),0,0,0,'[]','{}') RETURNING id"))
    with pytest.raises(IntegrityError, match="ck_seeding_claim_entry"):
        with engine.begin() as conn:
            conn.execute(text(f"INSERT INTO seeding_domain_claims(id,domain,{columns}) VALUES (:id,'audits',{values})"),
                {"id": str(uuid4()), "command": command, "job": job, "entry": str(uuid4())})


def test_operator_release_is_recorded_as_reconciliation_not_a_fabricated_return(pg):
    _, factory, engine = pg
    identity = uuid4()
    with factory.begin() as db:
        assert reserve(db, "audits", identity)
    retained = {"id": str(identity)}
    # A retained, entered claim cannot be released without a return or a reconciliation record.
    with pytest.raises(IntegrityError, match="ck_seeding_claim_receipt"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE seeding_domain_claims SET released_at=clock_timestamp() WHERE id=:id"), retained)
    with pytest.raises(IntegrityError, match="ck_seeding_claim_reconciliation"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE seeding_domain_claims SET reconciled_by='operator', reconciliation='evidence' WHERE id=:id"), retained)
    with engine.begin() as conn:
        conn.execute(text("UPDATE seeding_domain_claims SET released_at=clock_timestamp(), reconciled_by='operator',"
            " reconciliation='writer processes stopped; effects reconciled' WHERE id=:id"), retained)
    with factory.begin() as db:
        assert reserve(db, "audits", uuid4())


def test_unentered_dispatch_claim_may_be_released_without_a_return(pg):
    client, factory, engine = pg
    generation = register_worker(factory)
    post(client, generation)
    _, token = claim(factory, generation)
    with engine.begin() as conn:
        conn.execute(text("UPDATE seeding_domain_claims SET released_at=clock_timestamp() WHERE id=:id"), {"id": str(token)})
    with pytest.raises(IntegrityError, match="ck_seeding_claim_entry|ck_seeding_claim_receipt"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE seeding_domain_claims SET entered_at=clock_timestamp(), entry_id=:entry WHERE id=:id"),
                {"entry": str(uuid4()), "id": str(token)})


@pytest.mark.parametrize("started", [False, True])
def test_migrated_batch7_claim_that_started_is_never_treated_as_unentered(pg, started):
    # Adversarial round 3: finish() released a migrated claim whose Batch 7 CLI
    # may already have run, because the backfill left it looking never-entered.
    client, factory, engine = pg
    assert migrate("e554d7c9a001", "downgrade").returncode == 0
    generation = register_worker(factory)
    identity = post(client, generation).json()["command"]["id"]
    token = str(uuid4())
    with engine.begin() as conn:
        conn.execute(text("UPDATE etl_dispatch_commands SET status='running',started_at=clock_timestamp(),updated_at=clock_timestamp(),"
            "claim_token=:token,execution_started=:started,version=2 WHERE id=:id"), {"token": token, "id": identity, "started": started})
        conn.execute(text("UPDATE etl_dispatch_domains SET command_id=:id,claim_token=:token WHERE domain='audits'"), {"token": token, "id": identity})
    result = migrate("head", "upgrade")
    assert result.returncode == 0, result.stderr
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT entered_at IS NOT NULL FROM seeding_domain_claims")) is started
    released = finish(factory, generation, UUID(identity), UUID(token), 0)
    with engine.connect() as conn:
        status, active = conn.execute(text("SELECT c.status, s.released_at IS NULL FROM etl_dispatch_commands c"
            " JOIN seeding_domain_claims s ON s.command_id=c.id")).one()
    # Never started: provably nothing ran, so it is freed as failed. Started: uncertain, retained.
    assert (released, status, active) == ((False, "interrupted", True) if started else (True, "failed", False))


@pytest.mark.parametrize("extra", ["", ",'ownership_refused',false", ",'ownership_refused','no'", ",'ownership_refused','true'", ",'ownership_refused',null", ",'ownership_refused',1"])
def test_unentered_claim_with_a_correlated_run_observation_stays_uncertain(pg, extra):
    # Only a genuine refusal row (ownership_refused = true) is ignored.
    client, factory, engine = pg
    generation = register_worker(factory)
    post(client, generation)
    command_id, token = claim(factory, generation)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO ingestion_jobs(domain,status,dry_run,started_at,finished_at,items_processed,items_created,items_updated,errors,metadata)"
            " VALUES ('audits','COMPLETED',false,now(),now(),1,1,0,'[]',jsonb_build_object('dispatch_command_id',CAST(:c AS text),'dispatch_claim_token',CAST(:t AS text)" + extra + "))"),
            {"c": str(command_id), "t": str(token)})
    assert finish(factory, generation, command_id, token, 0) is False
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT status FROM etl_dispatch_commands")) == "interrupted"
        assert conn.scalar(text("SELECT released_at IS NULL FROM seeding_domain_claims")) is True


@pytest.mark.parametrize("by,why", [(" ", "evidence"), ("operator", "   "), ("", "evidence")])
def test_blank_reconciliation_is_rejected(pg, by, why):
    _, factory, engine = pg
    identity = uuid4()
    with factory.begin() as db:
        assert reserve(db, "audits", identity)
    with pytest.raises(IntegrityError, match="ck_seeding_claim_reconciliation"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE seeding_domain_claims SET released_at=clock_timestamp(), reconciled_by=:by, reconciliation=:why WHERE id=:id"),
                {"by": by, "why": why, "id": str(identity)})
