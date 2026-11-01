"""An operator acquisition is exactly four reviewed PDFs, never broad discovery."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

CHOICE = 'oag-combined-catalogue-20261101'
MANIFEST = Path(__file__).resolve().parents[2] / 'docs/operations/2026-11-01-oag-catalogue-acceptance/manifest.json'


def execute(monkeypatch, **overrides):
    from seeding import source_plan as plan
    for key in list(os.environ):
        if key.startswith(('SEED_PLAN_', 'SEED_CRA_', 'SEED_OPENDATA_', 'SEED_KNBS_', 'SEED_COUNTY_BORROWING_')):
            monkeypatch.delenv(key)
    values = dict(SEED_PLAN_EVENT='workflow_dispatch', SEED_PLAN_DOMAIN='audits',
                  SEED_PLAN_DRY_RUN='false', SEED_PLAN_AUDITS_SOURCE_ACCEPTANCE=CHOICE)
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, 'argv', ['source_plan', '--execute'])
    calls = []
    monkeypatch.setattr(plan.subprocess, 'run', lambda argv, **kw: (calls.append((argv, kw)) or SimpleNamespace(returncode=0)))
    return plan.main(), calls


def test_operator_executes_only_exact_reviewed_manifest_with_fresh_child_cache(monkeypatch):
    monkeypatch.setenv('SEED_PDF_CACHE_TTL_SECONDS', '4321')
    result, calls = execute(monkeypatch)
    assert result == 0 and len(calls) == 1
    argv, options = calls[0]
    assert argv == [sys.executable, '-m', 'seeding.cli', 'seed', '--domain', 'audits',
                    '--audits-source-manifest', str(MANIFEST), '--no-dry-run']
    assert options['env']['SEED_PDF_CACHE_TTL_SECONDS'] == '0'
    assert os.environ['SEED_PDF_CACHE_TTL_SECONDS'] == '4321'
    assert '--audits-observe-listing' not in argv


@pytest.mark.parametrize('overrides', [
    {'SEED_PLAN_EVENT': 'schedule', 'SEED_PLAN_SCHEDULE': '0 3 * * 0', 'SEED_PLAN_DOMAIN': ''},
    {'SEED_PLAN_DOMAIN': ''}, {'SEED_PLAN_DOMAIN': 'national_budget'},
    {'SEED_PLAN_DRY_RUN': 'true'}, {'SEED_PLAN_BOOTSTRAP': 'true'},
    {'SEED_PLAN_AUDITS_REVIEW': 'oag-2542-20261026'},
    {'SEED_PLAN_REACQUIRE_PENDING_BILLS_PDF': 'true'},
    {'SEED_PLAN_AUDITS_SOURCE_ACCEPTANCE': 'arbitrary'},
])
def test_incompatible_selection_never_invokes_cli(monkeypatch, overrides):
    result, calls = execute(monkeypatch, **overrides)
    assert result == 2 and calls == []


def test_new_manifest_is_pinned_and_receipt_identifies_actual_packet():
    from seeding.domains.audits.scope import parse_manifest, receipt_for
    raw = MANIFEST.read_bytes()
    entries = parse_manifest(raw)
    assert len(entries) == 4
    assert {(e['fiscal_year'], e['institution']) for e in entries} == {
        (year, kind) for year in ('2022/2023', '2023/2024') for kind in ('assemblies', 'executives')}
    import hashlib
    assert receipt_for(entries, raw=raw)['manifest_sha256'] == hashlib.sha256(raw).hexdigest()


def test_new_manifest_modified_bytes_are_not_reviewed():
    from seeding.domains.audits.scope import parse_manifest, AuditSourceScopeError
    value = json.loads(MANIFEST.read_bytes())
    value['deferred_sources'][0]['source_url'] = 'https://example.com/arbitrary.pdf'
    with pytest.raises(AuditSourceScopeError):
        parse_manifest(json.dumps(value).encode())
