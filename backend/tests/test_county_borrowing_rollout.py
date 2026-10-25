"""Explicit producer selection; normal nightly scope stays frozen."""
from seeding.config import SeedingSettings
from seeding.source_plan import LEGACY_DOMAINS, DAILY, build_plan


def test_existing_daily_plan_is_observable_and_unchanged():
    plan = build_plan(event='schedule', schedule=DAILY, domain='', dry_run='false',
                      cra='false', opendata='false', discovery='false')
    assert plan.domains == LEGACY_DOMAINS
    assert len(plan.domains) == 15


def test_explicit_opt_in_registers_county_borrowing_producer(monkeypatch):
    import subprocess, sys, os
    env = {k: v for k, v in os.environ.items() if not k.startswith('SEED_')}
    env['SEED_COUNTY_BORROWING_INGESTION_ENABLED'] = 'true'
    result = subprocess.run([sys.executable, '-c',
        "from seeding.registries import REGISTRY,load_builtin_domains; load_builtin_domains(); assert callable(REGISTRY.get('county_borrowing')), 'explicit opt-in has no county borrowing producer'"],
        env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr



def test_settings_expose_default_off_county_borrowing():
    assert SeedingSettings(_env_file=None).model_dump().get('county_borrowing_ingestion_enabled') is False
