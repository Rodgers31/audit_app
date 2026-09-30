"""A web debt no-op must never certify a successful debt refresh."""

import asyncio
import importlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

module = importlib.import_module("services.auto_seeder")


async def one_tick(seeder, monkeypatch):
    """Execute the real background loop, stopping at its second hourly wait."""
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


@pytest.mark.asyncio
async def test_idle_loop_does_not_certify_noop_debt_or_full_refresh(monkeypatch):
    seeder = module.AutoSeeder()
    county_success = datetime.now(timezone.utc)
    seeder.last_refresh["counties"] = county_success
    debt_noop = AsyncMock(return_value=None)
    monkeypatch.setattr(seeder, "_seed_debt_live", debt_noop)
    monkeypatch.setattr(module, "SessionLocal", lambda: pytest.fail("unexpected DB"))

    await one_tick(seeder, monkeypatch)

    status = seeder.get_status()
    assert status["fetch_stats"]["successful_fetches"] == 0
    assert status["fetch_stats"]["total_fetches"] == 0
    assert status["fetch_stats"]["last_full_refresh"] is None
    assert status["last_refresh"] == {"counties": county_success.isoformat()}
    assert "debt" not in status["next_refresh"]
    debt_noop.assert_not_called()


@pytest.mark.asyncio
async def test_boot_does_not_credit_noop_debt(monkeypatch):
    seeder = module.AutoSeeder()
    counties = AsyncMock()
    national = AsyncMock()
    debt_noop = AsyncMock(return_value=None)
    monkeypatch.setattr(seeder, "_seed_counties_live", counties)
    monkeypatch.setattr(seeder, "_ensure_national_entity", national)
    monkeypatch.setattr(seeder, "_seed_debt_live", debt_noop)
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    await seeder.seed_all_domains()
    assert seeder.get_status()["fetch_stats"]["successful_fetches"] == 2
    assert "debt" not in seeder.last_refresh
    counties.assert_awaited_once()
    national.assert_awaited_once()
    debt_noop.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("direct", [False, True])
async def test_legacy_debt_dispatch_refuses_before_io(monkeypatch, direct):
    seeder = module.AutoSeeder()
    monkeypatch.setattr(module, "SessionLocal", lambda: pytest.fail("unexpected DB"))
    with pytest.raises(ValueError, match="national_debt.*dedicated seeding runner"):
        if direct:
            await seeder._seed_debt_live()
        else:
            await seeder._seed_domain("debt")
    assert seeder.get_status()["fetch_stats"]["successful_fetches"] == 0


@pytest.mark.asyncio
async def test_loop_credits_real_county_reference_write(
    db_session, seed_country, monkeypatch
):
    from models import Entity, EntityType

    seeder = module.AutoSeeder()
    seeder._consecutive_failures["counties"] = 2
    # Use the actual reference writer with no network payload.
    monkeypatch.setattr(module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(
        seeder.aggregator, "fetch_all_county_data", AsyncMock(return_value=([], []))
    )
    await one_tick(seeder, monkeypatch)

    assert db_session.query(Entity).filter(Entity.type == EntityType.COUNTY).count() == 47
    status = seeder.get_status()
    assert status["fetch_stats"]["successful_fetches"] == 1
    assert status["fetch_stats"]["total_fetches"] == 1
    assert status["fetch_stats"]["failed_fetches"] == 0
    assert status["fetch_stats"]["last_full_refresh"] is not None
    assert "counties" in status["last_refresh"]
    assert "debt" not in status["last_refresh"]
    assert status["consecutive_failures"] == {}


@pytest.mark.asyncio
async def test_failed_county_write_retains_retry_and_failure_accounting(monkeypatch):
    seeder = module.AutoSeeder()
    last_success = datetime.now(timezone.utc) - timedelta(days=8)
    seeder.last_refresh["counties"] = last_success
    seeder._fetch_stats["last_full_refresh"] = last_success.isoformat()
    seeder._consecutive_failures["counties"] = 1

    def failed_db():
        raise RuntimeError("synthetic unavailable DB")

    monkeypatch.setattr(module, "SessionLocal", failed_db)
    monkeypatch.setattr(
        seeder.aggregator, "fetch_all_county_data", AsyncMock(return_value=([], []))
    )
    await one_tick(seeder, monkeypatch)

    status = seeder.get_status()
    assert status["fetch_stats"]["successful_fetches"] == 0
    assert status["fetch_stats"]["total_fetches"] == 1
    assert status["fetch_stats"]["failed_fetches"] == 1
    assert status["consecutive_failures"] == {"counties": 2}
    assert status["last_refresh"]["counties"] == last_success.isoformat()
    assert status["next_refresh"]["counties"] == "Due now"
    assert status["fetch_stats"]["last_full_refresh"] == last_success.isoformat()


def test_public_status_reports_dedicated_debt_owner_without_job_health(
    client, monkeypatch
):
    seeder = module.AutoSeeder()
    monkeypatch.setattr(module, "auto_seeder", seeder)
    response = client.get("/api/v1/system/seeder-status")
    assert response.status_code == 200
    body = response.json()
    status = body["auto_seeder"]
    assert "debt" not in status["last_refresh"]
    assert "debt" not in status["next_refresh"]
    assert {"national_debt", "debt_timeline"}.issubset(
        status["external_job_owner"]["domains"]
    )
    assert status["external_job_owner"]["job_health"] == "not_checked_here"
    assert "national_debt" in body["note"]
    assert "job health is not reported here" in body["note"]
