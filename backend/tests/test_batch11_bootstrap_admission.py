"""#603: retained ownership and atomic admission at real PostgreSQL/process seams."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("batch11_bootstrap_fixture")


@pytest.fixture(scope="module")
def admission_postgres():
    from batch11_bootstrap_fixture.postgres import postgres
    with postgres() as url:
        yield url


@pytest.fixture
def admission_database(admission_postgres):
    admin = create_engine(admission_postgres)
    schema = "batch11_bootstrap_" + uuid4().hex
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(admission_postgres).update_query_dict({"options": "-csearch_path=" + schema})
    try:
        yield url
    finally:
        with admin.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def run_probe(tmp_path, url, mode):
    env = dict(PATH=os.environ["PATH"], PYTHONPATH=f'{FIXTURE}:{ROOT / "backend"}',
        DATABASE_URL=url.render_as_string(hide_password=False), PYTHON_DOTENV_DISABLED="1",
        PYTHONDONTWRITEBYTECODE="1", BATCH11_BOOTSTRAP_INERT="1", JWT_SECRET_KEY="inert-bootstrap-key",
        AUTO_SEEDER_ENABLED="false", AUTO_WARMUP_ENABLED="false", SEED_STORAGE_PATH=str(tmp_path / "cache"))
    command = [sys.executable, str(FIXTURE / "probe.py"), mode]
    child = subprocess.Popen(command, cwd=ROOT / "backend", env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        output, _ = child.communicate(timeout=50)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        output, _ = child.communicate(timeout=10)
        pytest.fail("SETUP/TIMEOUT: " + output)
    print("COMMAND", command, "EXIT", child.returncode, "\n" + output)
    assert child.returncode == 0, "SETUP/PROCESS failure: " + output
    rows = [json.loads(line.removeprefix("ADMISSION_RESULT ")) for line in output.splitlines()
        if line.startswith("ADMISSION_RESULT ")]
    assert len(rows) == 1
    return rows[0]


@pytest.mark.parametrize("mode", ["retained_fresh", "retained_stale", "untagged", "active_ready", "race", "race_force"])
def test_startup_retains_nonbudget_ownership_without_any_effect(tmp_path, admission_database, mode):
    result = run_probe(tmp_path, admission_database, mode)
    assert result["after"] == result["before"], "CONFLICTING_BOOTSTRAP_EFFECT: retained owner was bypassed"
    assert result["startup_effects"] == [], "CONFLICTING_STARTUP_EFFECT: scheduler started behind retained owner"
    assert result["ready"] is (mode == "active_ready")
    if mode.startswith("retained"):
        assert result["writer_exit"] == -9


@pytest.mark.parametrize("mode", ["schema_failure", "query_failure"])
def test_ownership_uncertainty_is_visible_and_has_no_effect(tmp_path, admission_database, mode):
    result = run_probe(tmp_path, admission_database, mode)
    assert result["ready"] is False
    assert result["reason"] == "reference_initialization_failed"
    assert result["startup_effects"] == []
    if result["after"] is not None:
        assert result["after"] == result["before"], "UNCERTAIN_STORAGE_EFFECT"


def test_completed_native_owner_allows_normal_bootstrap(tmp_path, admission_database):
    result = run_probe(tmp_path, admission_database, "completed")
    assert result["ready"] is True
    assert result["after"]["tables"]["entities"] == 48
    assert result["startup_effects"] == ["scheduler"]
    assert all(row[8] != "None" for row in result["after"]["claims"])


@pytest.mark.parametrize("barrier", ["bootstrap_block", "bootstrap_committed_block"])
@pytest.mark.parametrize("restart", ["restart_fresh", "restart_stale"])
def test_interrupted_bootstrap_retains_all_admission_domains(tmp_path, admission_database, barrier, restart):
    import select
    env = dict(PATH=os.environ["PATH"], PYTHONPATH=f'{FIXTURE}:{ROOT / "backend"}',
        DATABASE_URL=admission_database.render_as_string(hide_password=False),
        PYTHON_DOTENV_DISABLED="1", PYTHONDONTWRITEBYTECODE="1", BATCH11_BOOTSTRAP_INERT="1",
        JWT_SECRET_KEY="inert-bootstrap-key", AUTO_SEEDER_ENABLED="false", AUTO_WARMUP_ENABLED="false",
        SEED_STORAGE_PATH=str(tmp_path / "cache"))
    child = subprocess.Popen([sys.executable, str(FIXTURE / "probe.py"), barrier],
        cwd=ROOT / "backend", env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        while True:
            assert select.select([child.stdout], [], [], 15)[0], "Bootstrap barrier timed out"
            line = child.stdout.readline()
            print("BOOTSTRAP_LOG", line.rstrip())
            if line.strip() == "BOOTSTRAP_ENTERED":
                break
            assert line, "Bootstrap exited before owned barrier"
        os.killpg(child.pid, signal.SIGKILL)
        child.communicate(timeout=5)
        assert child.returncode == -9
        result = run_probe(tmp_path, admission_database, restart)
        assert result["after"] == result["before"], "INTERRUPTED_BOOTSTRAP_OWNERSHIP_BYPASSED"
        assert result["startup_effects"] == []
        from bootstrap import BOOTSTRAP_EFFECT_DOMAINS
        retained = result["after"]["claims"]
        assert {r[1] for r in retained} == set(BOOTSTRAP_EFFECT_DOMAINS) | {"national_budget"}
        assert all(r[8] == "None" for r in retained)
        assert result["ready"] is (barrier == "bootstrap_committed_block")
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)


def test_atomic_claim_set_rolls_back_partial_reservations(admission_database, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from models import Base, SeedingDomainClaim
    from seeding import exclusion
    engine = create_engine(admission_database)
    factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    retained = exclusion.enter_domain(factory, "zz-owned", False)
    retained.close()  # no return, durable uncertainty survives the lock's end
    original = exclusion.reserve
    seen = []
    def observed(db, domain, *args, **kwargs):
        seen.append((domain, db.scalar(text("SELECT txid_current()"))))
        value = original(db, domain, *args, **kwargs)
        with engine.connect() as independent:
            assert independent.scalar(text("SELECT count(*) FROM seeding_domain_claims")) == 1
        return value
    monkeypatch.setattr(exclusion, "reserve", observed)
    try:
        with pytest.raises(exclusion.DomainBusyError, match="retained"):
            exclusion.enter_domains(factory, ("aa-owned", "zz-owned"), "aa-owned")
        assert len(seen) == 2 and seen[0][1] == seen[1][1]
        with factory() as observer:
            assert [c.id for c in observer.query(SeedingDomainClaim)] == [retained.identity]
    finally:
        engine.dispose()


def test_group_receipt_refusal_preserves_lock_then_valid_release(admission_database):
    from datetime import datetime, timezone
    from sqlalchemy.orm import sessionmaker
    from models import Base, IngestionJob, IngestionStatus, SeedingDomainClaim
    from seeding import exclusion
    engine = create_engine(admission_database)
    factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    group = exclusion.enter_domains(factory, ("bootstrap_reference_data", "audits"), "bootstrap_reference_data")
    try:
        with factory.begin() as db:
            job = IngestionJob(domain="bootstrap_reference_data", status=IngestionStatus.COMPLETED,
                dry_run=False, started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
                meta={"seeding_claim_ids": {"audits": "forged"}}, errors=[])
            db.add(job)
            db.flush()
            job_id = job.id
        with pytest.raises(exclusion.DomainOwnershipError, match="receipt unverified"):
            group.acknowledge(job_id)
        assert group.continuous()
        with factory.begin() as db:
            assert db.query(SeedingDomainClaim).filter(SeedingDomainClaim.released_at.is_(None)).count() == 2
            db.get(IngestionJob, job_id).meta = {"seeding_claim_ids": group.claim_ids}
        group.acknowledge(job_id)
        with factory() as observer:
            assert observer.query(SeedingDomainClaim).filter(SeedingDomainClaim.released_at.is_(None)).count() == 0
    finally:
        group.close()
        engine.dispose()


@pytest.mark.parametrize("fault", ["dry_run", "missing_claim", "entry_nonce", "backend_loss"])
def test_group_release_refuses_uncertain_members(admission_database, monkeypatch, fault):
    from datetime import datetime, timezone
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.exc import SQLAlchemyError
    from models import Base, IngestionJob, IngestionStatus, SeedingDomainClaim
    from seeding import exclusion
    engine = create_engine(admission_database)
    factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    group = exclusion.enter_domains(factory, ("bootstrap_reference_data", "audits"), "bootstrap_reference_data")
    try:
        with factory.begin() as db:
            job = IngestionJob(domain="bootstrap_reference_data", status=IngestionStatus.COMPLETED,
                dry_run=fault == "dry_run", started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc), meta={"seeding_claim_ids": group.claim_ids}, errors=[])
            db.add(job)
            db.flush()
            job_id = job.id
            if fault == "missing_claim":
                db.delete(db.get(SeedingDomainClaim, group.members["audits"].identity))
        if fault == "entry_nonce":
            group.members["audits"].entry = uuid4()
        if fault == "backend_loss":
            continuous = group.continuous
            def lost_after_proof():
                result = continuous()
                with engine.begin() as observer:
                    assert observer.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": group.guard.pid}) is True
                return result
            monkeypatch.setattr(group, "continuous", lost_after_proof)
        with factory() as observer:
            expected = sorted(str(c.id) for c in observer.query(SeedingDomainClaim))
        with pytest.raises((exclusion.DomainOwnershipError, SQLAlchemyError)):
            group.acknowledge(job_id)
        with factory() as observer:
            rows = observer.query(SeedingDomainClaim).all()
            assert sorted(str(c.id) for c in rows) == expected
            assert all(c.released_at is None and c.returned_at is None for c in rows)
    finally:
        group.close()
        engine.dispose()


def test_current_builtin_writer_inventory_is_fenced():
    from bootstrap import BOOTSTRAP_EFFECT_DOMAINS, BOOTSTRAP_DOMAIN
    from seeding.registries import _BUILTIN_DOMAIN_PACKAGES
    domains = {name.rsplit(".", 1)[1] for name in _BUILTIN_DOMAIN_PACKAGES}
    assert domains == (set(BOOTSTRAP_EFFECT_DOMAINS) - {BOOTSTRAP_DOMAIN}) | {"national_budget"}


@pytest.mark.parametrize("mode", ["normal", "alter_release", "alter_receipt", "deferred_release"])
def test_group_release_proves_exact_persisted_values(admission_database, mode):
    from datetime import datetime, timezone
    from sqlalchemy.orm import sessionmaker
    from models import Base, IngestionJob, IngestionStatus, SeedingDomainClaim
    from seeding.exclusion import DomainOwnershipError, enter_domains
    engine = create_engine(admission_database)
    factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    group = enter_domains(factory, ("bootstrap_reference_data", "audits"), "bootstrap_reference_data")
    try:
        with factory.begin() as db:
            job = IngestionJob(domain="bootstrap_reference_data", status=IngestionStatus.COMPLETED,
                dry_run=False, started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
                meta={"seeding_claim_ids": group.claim_ids}, errors=[])
            db.add(job)
            db.flush()
            job_id = job.id
            if mode == "deferred_release":
                db.execute(text("""CREATE FUNCTION change_group_release() RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN UPDATE seeding_domain_claims SET released_at=NULL WHERE id=NEW.id; RETURN NULL; END $$"""))
                db.execute(text("""CREATE CONSTRAINT TRIGGER change_group_release AFTER UPDATE ON seeding_domain_claims
                    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.released_at IS NOT NULL)
                    EXECUTE FUNCTION change_group_release()"""))
            elif mode != "normal":
                change = "NEW.released_at := NULL;" if mode == "alter_release" else (
                    "NEW.returned_at := NEW.acquired_at; NEW.released_at := NEW.acquired_at;")
                db.execute(text("CREATE FUNCTION change_group_release() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                    + change + " RETURN NEW; END $$"))
                db.execute(text("CREATE TRIGGER change_group_release BEFORE UPDATE ON seeding_domain_claims "
                    "FOR EACH ROW EXECUTE FUNCTION change_group_release()"))
        if mode == "normal":
            group.acknowledge(job_id)
        else:
            refused = False
            try:
                group.acknowledge(job_id)
            except DomainOwnershipError as exc:
                assert "stored release unverified" in str(exc)
                refused = True
            assert refused, "STORED_RELEASE_FALSE_SUCCESS"
        with factory() as observer:
            rows = observer.query(SeedingDomainClaim).all()
            assert len(rows) == 2
            if mode == "normal":
                assert all(c.released_at is not None and c.job_id == job_id for c in rows)
            else:
                assert all(c.released_at is None and c.returned_at is None and c.job_id is None for c in rows)
        if mode != "normal":
            assert group.continuous()
    finally:
        group.close()
        engine.dispose()


@pytest.mark.parametrize("domains", [None, (), ([],), (True,), ("a", "a"), ("",)])
def test_malformed_group_cannot_acquire(domains, db_session):
    from sqlalchemy.orm import sessionmaker
    from seeding.exclusion import DomainOwnershipError, enter_domains
    with pytest.raises(DomainOwnershipError, match="Invalid bootstrap ownership set"):
        enter_domains(sessionmaker(bind=db_session.get_bind()), domains, "a")
