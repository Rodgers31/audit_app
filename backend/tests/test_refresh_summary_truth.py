"""Successful execution must keep partial source coverage visible."""
from types import SimpleNamespace
from copy import deepcopy

from seeding.config import SeedingSettings
from seeding.domains.fiscal_summary import fetcher
from seeding.freshness import get, reset
from test_hollow_run_gate import HEALTHY_NIGHT, _run_step, _write_db


def test_partial_night_never_claims_all_domains_success(tmp_path):
    rows = [r if r[0] != 'debt_timeline' else (*r[:5], 'partial', 'gdp_refresh_unavailable')
            for r in HEALTHY_NIGHT]
    result = _run_step(_write_db(tmp_path, rows))
    assert result.returncode == 0, result.stdout + result.stderr
    assert '[PARTIAL] debt_timeline:' in result.stdout
    assert 'Refresh completed with source gaps' in result.stdout
    assert 'All domains completed successfully.' not in result.stdout


def test_completed_with_errors_is_a_warning_in_the_final_summary(tmp_path):
    rows = [('fiscal_summary', 'completed_with_errors', 0, 1, 1, 'live', None)]
    result = _run_step(_write_db(tmp_path, rows), domain='fiscal_summary')
    assert result.returncode == 0, result.stdout + result.stderr
    assert '[WARN] fiscal_summary:' in result.stdout
    assert 'Refresh completed with source gaps or ingestion warnings' in result.stdout
    assert 'All domains completed successfully.' not in result.stdout


def test_a_budget_update_cannot_hide_unreadable_fiscal_editions(monkeypatch):
    payload = {'fiscal_years': [{'fiscal_year': 'FY 2026/27', 'appropriated_budget': 5485.7}]}
    monkeypatch.setattr(fetcher, 'load_json_resource', lambda **k: deepcopy(payload))
    monkeypatch.setattr(fetcher, '_fetch_cob_headlines', lambda *a: (None, None, None))
    monkeypatch.setattr(fetcher, '_fetch_budget_estimates', lambda *a: (SimpleNamespace(fiscal_year='FY 2026/27'), 'read'))
    monkeypatch.setattr(fetcher, '_apply_budget_estimates', lambda p, e: (p, 'updated'))
    monkeypatch.setattr(fetcher, '_fetch_revenue_estimates', lambda *a, **k: (None, 'unavailable'))
    facts = {'budget_summary_listing_status': 'read', 'budget_summary_editions': {
        'https://www.treasury.go.ke/missing.pdf': {'fiscal_year': 'FY 2025/26', 'status': 'unreadable(HTTPError)'}}}
    monkeypatch.setattr(fetcher, '_fetch_budget_summary_editions', lambda *a: ([], facts))
    reset('fiscal_summary')
    result = fetcher.fetch_fiscal_summary_payload(None, SeedingSettings(_env_file=None, enrich_with_worldbank=False, live_pdf_fetch_enabled=True))
    assert get('fiscal_summary')['mode'] == 'partial'
    assert result['_run_facts']['refresh_components']['budget']['state'] == 'live'
    assert result['_run_facts']['refresh_components']['framework']['state'] == 'unavailable'
