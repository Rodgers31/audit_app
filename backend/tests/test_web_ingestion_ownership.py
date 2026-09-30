import importlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

module = importlib.import_module("services.auto_seeder")


@pytest.mark.asyncio
async def test_weekly_tick_never_dispatches_heavy_domains(monkeypatch):
    seeder = module.AutoSeeder()
    seeder.last_refresh = {
        name: datetime.now(timezone.utc) - timedelta(days=40)
        for name in module.REFRESH_SCHEDULE
    }
    run = AsyncMock()
    monkeypatch.setattr(seeder, "_seed_domain", run)
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    await seeder._check_and_refresh()
    names = [call.args[0] for call in run.call_args_list]
    assert "counties" in names  # The scheduler actually ran.
    assert "economic" not in names
    assert not {"population", "audits", "budgets", "counties_budget"}.intersection(names)


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", ["audits", "counties_budget", "budgets"])
async def test_direct_web_dispatch_cannot_run_registry(monkeypatch, domain):
    from seeding import registries

    run = Mock()
    monkeypatch.setattr(registries, "load_builtin_domains", lambda: None)
    monkeypatch.setattr(registries, "REGISTRY", {domain: run})
    with pytest.raises(ValueError, match="dedicated"):
        await module.AutoSeeder()._seed_registry_domain(domain)
    run.assert_not_called()


@pytest.mark.asyncio
async def test_web_scheduler_never_schedules_deep_parsing(monkeypatch):
    from types import SimpleNamespace
    import main

    scheduler = Mock()
    # Capability presence is exercised separately with real isolated packages.
    monkeypatch.setattr(main, "_discovery_pipeline_class", lambda: Mock())
    original = main.importlib.import_module
    monkeypatch.setattr(
        main.importlib,
        "import_module",
        lambda name: SimpleNamespace(AsyncIOScheduler=lambda: scheduler)
        if name == "apscheduler.schedulers.asyncio"
        else original(name),
    )
    await main._setup_etl_scheduler()
    scheduled = [call.kwargs.get("args") for call in scheduler.add_job.call_args_list]
    assert ["oag", "light"] in scheduled
    assert not any(args and args[-1] == "deep" for args in scheduled)


@pytest.mark.asyncio
async def test_admin_cannot_start_deep_job_inside_web_worker(monkeypatch):
    import main
    from fastapi import HTTPException

    runner = AsyncMock(return_value={})
    monkeypatch.setattr(main, "_run_job", runner)
    before = dict(main._etl_jobs)
    with pytest.raises(HTTPException) as exc:
        await main.run_etl_job(source="oag", job="deep", _actor=object())
    assert exc.value.status_code == 409
    assert main._etl_jobs == before
    runner.assert_not_called()


@pytest.mark.asyncio
async def test_direct_job_execution_cannot_bypass_web_guard(monkeypatch):
    import main

    discover = AsyncMock(return_value=[])
    monkeypatch.setattr(main, "_discover", discover)
    with pytest.raises(ValueError, match="dedicated"):
        await main._run_job("oag", "deep")
    discover.assert_not_called()


@pytest.mark.asyncio
async def test_boot_dispatch_preserves_unrelated_domains(monkeypatch):
    seeder = module.AutoSeeder()
    run = AsyncMock()
    monkeypatch.setattr(seeder, "_seed_domain", run)
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    await seeder.seed_all_domains()
    assert [c.args[0] for c in run.call_args_list] == [
        "counties", "national_entity", "debt"
    ]
