"""Execute real boot/periodic reference writers and their public status ledger."""
import asyncio
import importlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Country, Entity, EntityType

module = importlib.import_module("services.auto_seeder")


async def tick(seeder, monkeypatch):
    hourly_waits = 0

    async def sleep(seconds):
        nonlocal hourly_waits
        if seconds == 3600:
            hourly_waits += 1
            if hourly_waits == 2:
                seeder.is_running = False
                raise asyncio.CancelledError

    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    seeder.is_running = True
    await seeder._refresh_loop()
    assert hourly_waits == 2


def public_status(client, seeder, monkeypatch):
    monkeypatch.setattr(module, "auto_seeder", seeder)
    response = client.get("/api/v1/system/seeder-status")
    assert response.status_code == 200, response.text
    status = response.json()["auto_seeder"]
    assert status["external_job_owner"]["job_health"] == "not_checked_here"
    assert "debt" not in status["next_refresh"]
    return status


def setup(seeder, db_session, monkeypatch):
    monkeypatch.setattr(module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(seeder.aggregator, "fetch_all_county_data",
                        AsyncMock(return_value=([], [])))


def foreign_references(db_session):
    foreign = Country(iso_code="UGA", name="Uganda", currency="UGX",
                          timezone="Africa/Kampala", default_locale="en_UG")
    db_session.add(foreign)
    db_session.flush()
    db_session.add_all([
        Entity(country_id=foreign.id, type=EntityType.COUNTY,
               canonical_name=f"{name} County", slug=f"foreign-{code}",
               meta={"sentinel": "foreign reference"})
        for code, name in module.KENYA_COUNTY_CODES.items()
    ])
    db_session.add(Entity(country_id=foreign.id, type=EntityType.NATIONAL,
                          canonical_name="Republic of Uganda", slug="foreign-national"))
    db_session.commit()
    return foreign.id


@pytest.mark.asyncio
@pytest.mark.parametrize("preexisting", [False, True])
@pytest.mark.parametrize("boot", [False, True])
async def test_missing_ken_fails_even_with_preexisting_foreign_references(
    client, db_session, monkeypatch, preexisting, boot,
):
    if preexisting:
        foreign_references(db_session)
    seeder = module.AutoSeeder()
    setup(seeder, db_session, monkeypatch)
    old = datetime.now(timezone.utc) - timedelta(days=8)
    seeder.last_refresh["counties"] = old
    seeder._fetch_stats["last_full_refresh"] = old.isoformat()
    seeder._consecutive_failures["counties"] = 1
    if boot:
        monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
        await seeder.seed_all_domains()
    else:
        await tick(seeder, monkeypatch)
    status = public_status(client, seeder, monkeypatch)
    assert status["fetch_stats"]["successful_fetches"] == 0
    assert status["fetch_stats"]["failed_fetches"] == (2 if boot else 1)
    assert status["fetch_stats"]["total_fetches"] == (2 if boot else 1)
    assert status["consecutive_failures"]["counties"] == 2
    if boot:
        assert status["consecutive_failures"]["national_entity"] == 1
    assert status["last_refresh"] == {"counties": old.isoformat()}
    assert status["fetch_stats"]["last_full_refresh"] == old.isoformat()
    assert status["next_refresh"]["counties"] == "Due now"
    assert db_session.query(Entity).count() == (48 if preexisting else 0)


@pytest.mark.asyncio
async def test_failed_boot_retries_next_tick_and_recovers_only_after_real_work(
    client, db_session, monkeypatch,
):
    seeder = module.AutoSeeder()
    setup(seeder, db_session, monkeypatch)
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    await seeder.seed_all_domains()
    assert public_status(client, seeder, monkeypatch)["next_refresh"]["counties"] == "Never run"
    await tick(seeder, monkeypatch)
    status = public_status(client, seeder, monkeypatch)
    assert status["fetch_stats"]["successful_fetches"] == 0
    assert status["fetch_stats"]["failed_fetches"] == 3
    assert status["consecutive_failures"]["counties"] == 2
    db_session.add(Country(iso_code="KEN", name="Kenya", currency="KES",
                           timezone="Africa/Nairobi", default_locale="en_KE"))
    db_session.commit()
    await tick(seeder, monkeypatch)
    status = public_status(client, seeder, monkeypatch)
    assert status["fetch_stats"]["successful_fetches"] == 1
    assert status["fetch_stats"]["failed_fetches"] == 3
    assert "counties" not in status["consecutive_failures"]
    last = datetime.fromisoformat(status["last_refresh"]["counties"])
    next_run = datetime.fromisoformat(status["next_refresh"]["counties"])
    assert next_run - last == timedelta(days=7)
    assert db_session.query(Entity).filter(Entity.type == EntityType.COUNTY).count() == 47


@pytest.mark.asyncio
async def test_valid_ken_boot_is_idempotent_and_cannot_reuse_foreign_references(
    client, db_session, seed_country, monkeypatch,
):
    foreign_id = foreign_references(db_session)
    ken_id = seed_country.id
    seeder = module.AutoSeeder()
    setup(seeder, db_session, monkeypatch)
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    for _ in range(2):
        await seeder.seed_all_domains()
        assert db_session.query(Entity).filter(Entity.country_id == ken_id,
                                               Entity.type == EntityType.COUNTY).count() == 47
        assert db_session.query(Entity).filter(Entity.country_id == ken_id,
                                               Entity.type == EntityType.NATIONAL).count() == 1
    status = public_status(client, seeder, monkeypatch)
    assert status["fetch_stats"]["successful_fetches"] == 4
    assert status["fetch_stats"]["failed_fetches"] == 0
    assert status["consecutive_failures"] == {}
    assert db_session.query(Entity).filter(Entity.country_id == foreign_id).count() == 48
    assert all(row.meta == {"sentinel": "foreign reference"}
               for row in db_session.query(Entity).filter(Entity.country_id == foreign_id,
                                                          Entity.type == EntityType.COUNTY))


@pytest.mark.asyncio
async def test_actual_sql_failure_cannot_advance_reference_success(
    client, monkeypatch, tmp_path,
):
    # No tables: the actual reference writer must hit a real OperationalError.
    engine = create_engine(f"sqlite:///{tmp_path / 'missing-tables.db'}")
    seeder = module.AutoSeeder()
    monkeypatch.setattr(module, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(seeder.aggregator, "fetch_all_county_data",
                        AsyncMock(return_value=([], [])))
    try:
        await tick(seeder, monkeypatch)
        status = public_status(client, seeder, monkeypatch)
        assert status["fetch_stats"]["successful_fetches"] == 0
        assert status["fetch_stats"]["failed_fetches"] == 1
        assert status["fetch_stats"]["last_full_refresh"] is None
        assert status["last_refresh"] == {}
        assert status["consecutive_failures"] == {"counties": 1}
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", ["counties", "national_entity"])
async def test_direct_reference_dispatch_requires_ken(db_session, monkeypatch, domain):
    seeder = module.AutoSeeder()
    setup(seeder, db_session, monkeypatch)
    with pytest.raises(ValueError, match="Kenya country.*KEN.*required"):
        await seeder._seed_domain(domain)
    assert db_session.query(Entity).count() == 0


@pytest.fixture()
def postgres_references():
    import os
    from uuid import uuid4
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from models import Base

    url = os.environ.get("AUDIT_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set AUDIT_TEST_POSTGRES_URL to a disposable local PostgreSQL database")
    if make_url(url).host not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("AUDIT_TEST_POSTGRES_URL must point to disposable local PostgreSQL")
    schema = f"references_{uuid4().hex}"
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        yield engine, sessionmaker(bind=engine)
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@pytest.mark.asyncio
async def test_postgres_failed_county_transaction_rolls_back_and_boot_continues(
    client, postgres_references, monkeypatch,
):
    from sqlalchemy import text

    engine, Session = postgres_references
    with Session() as db:
        db.add(Country(iso_code="KEN", name="Kenya", currency="KES",
                       timezone="Africa/Nairobi", default_locale="en_KE"))
        db.commit()
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE FUNCTION refuse_final_county() RETURNS trigger AS $$
            BEGIN
                IF NEW.slug = 'nairobi-047' THEN
                    RAISE EXCEPTION 'synthetic final county write refused';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        connection.execute(text("""
            CREATE TRIGGER refuse_county BEFORE INSERT ON entities
            FOR EACH ROW EXECUTE FUNCTION refuse_final_county()
        """))
    seeder = module.AutoSeeder()
    monkeypatch.setattr(module, "SessionLocal", Session)
    monkeypatch.setattr(seeder.aggregator, "fetch_all_county_data",
                        AsyncMock(return_value=([], [])))
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    await seeder.seed_all_domains()
    status = public_status(client, seeder, monkeypatch)
    assert status["fetch_stats"]["successful_fetches"] == 1
    assert status["fetch_stats"]["failed_fetches"] == 1
    assert status["last_refresh"].keys() == {"national_entity"}
    assert status["consecutive_failures"] == {"counties": 1}
    assert status["next_refresh"]["counties"] == "Never run"
    with Session() as db:
        assert db.query(Entity).filter(Entity.type == EntityType.COUNTY).count() == 0
        assert db.query(Entity).filter(Entity.type == EntityType.NATIONAL).count() == 1
    with engine.begin() as connection:
        connection.execute(text("DROP TRIGGER refuse_county ON entities"))
    await tick(seeder, monkeypatch)
    status = public_status(client, seeder, monkeypatch)
    assert status["fetch_stats"]["successful_fetches"] == 2
    assert status["fetch_stats"]["failed_fetches"] == 1
    assert status["consecutive_failures"] == {}
    with Session() as db:
        assert db.query(Entity).filter(Entity.type == EntityType.COUNTY).count() == 47


@pytest.mark.asyncio
async def test_actual_initial_seed_and_loop_keeps_failed_references_due(
    client, db_session, monkeypatch,
):
    seeder = module.AutoSeeder()
    setup(seeder, db_session, monkeypatch)
    waits = 0

    async def sleep(seconds):
        nonlocal waits
        if seconds == 3600:
            waits += 1
            if waits == 2:
                seeder.is_running = False
                raise asyncio.CancelledError

    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    seeder.is_running = True
    await seeder._initial_seed_and_loop()
    status = public_status(client, seeder, monkeypatch)
    assert waits == 2
    assert status["fetch_stats"]["successful_fetches"] == 0
    assert status["fetch_stats"]["failed_fetches"] == 3
    assert status["consecutive_failures"] == {"counties": 2, "national_entity": 1}
    assert status["last_refresh"] == {}
    assert status["next_refresh"]["counties"] == "Never run"


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", [["invalid"], "invalid", 1])
async def test_malformed_existing_reference_fails_counties_without_blocking_national(
    client, db_session, seed_country, monkeypatch, malformed,
):
    db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                          canonical_name="Mombasa County", slug="mombasa-001",
                          meta=malformed))
    db_session.commit()
    seeder = module.AutoSeeder()
    setup(seeder, db_session, monkeypatch)
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    await seeder.seed_all_domains()
    status = public_status(client, seeder, monkeypatch)
    assert status["fetch_stats"]["successful_fetches"] == 1
    assert status["fetch_stats"]["failed_fetches"] == 1
    assert status["last_refresh"].keys() == {"national_entity"}
    assert status["consecutive_failures"] == {"counties": 1}
    assert db_session.query(Entity).filter(Entity.type == EntityType.COUNTY).count() == 1
