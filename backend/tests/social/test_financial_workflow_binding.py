"""Resolve actual runner flag bindings and exercise the financial dispatch gate."""
from pathlib import Path
import re

import pytest
import yaml

from seeding import generation_dispatch as bridge
from seeding import source_observations

ROOT = Path(__file__).resolve().parents[3]
FLAGS = ('SOCIAL_GENERATION_HOOK_ENABLED', 'SOCIAL_REPORT_GENERATION_ENABLED',
         'SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED')


def runner_flags(variables):
    """Small evaluator for the repo-variable/fallback expressions in this job.

    Read workflow/job/step precedence, rather than copying the desired env map.
    No arbitrary Actions expression or project code is evaluated here.
    """
    workflow = yaml.safe_load((ROOT / '.github/workflows/seed.yml').read_text())
    job = workflow['jobs']['seed']
    steps = [s for s in job['steps'] if s.get('name') == 'Seed planned domains']
    assert len(steps) == 1
    bound = {**workflow.get('env', {}), **job.get('env', {}), **steps[0].get('env', {})}
    result = {}
    for key in FLAGS:
        if key not in bound:
            continue
        raw = bound[key]
        match = re.fullmatch(r"\$\{\{ vars\.([A-Z_]+) \|\| '([^']*)' \}\}", raw)
        assert match, f'Unreviewed generation flag expression: {key}'
        result[key] = variables.get(match[1]) or match[2]
    return result


def apply_runner_flags(monkeypatch, variables):
    for key in FLAGS:
        monkeypatch.delenv(key, raising=False)
    for key, value in runner_flags(variables).items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize('domain', ['national_budget', 'pending_bills', 'revenue_by_source'])
def test_explicit_workflow_financial_flag_reaches_native_dispatch(monkeypatch, domain):
    apply_runner_flags(monkeypatch, dict(SOCIAL_GENERATION_HOOK_ENABLED='true',
        SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED='true'))
    calls = []
    def records(factory, *, ingestion_id, domain):
        calls.append(('read', ingestion_id, domain))
        return (17,)
    def invoke(factory, ids, ingestion_id, domain):
        calls.append(('consume', ids, ingestion_id, domain))
        return dict(state='completed', reason='COMMITTED_EVIDENCE_CONSUMED',
            processed=1, drafts_created=0, baselines=1, unchanged=0, refused=0)
    monkeypatch.setattr(source_observations, 'read_native_financial_record_ids', records)
    monkeypatch.setattr(bridge, '_invoke', invoke)
    telemetry = []
    monkeypatch.setattr(bridge, '_record_outcome', lambda *a, **kw: telemetry.append(a[-1]))
    result = bridge.dispatch_committed_generation(object(), domain=domain,
        ingestion_id=23, dry_run=False, include_reports=False)
    assert calls == [('read', 23, domain), ('consume', (17,), 23, domain)]
    assert result['state'] == 'completed' and result['baselines'] == 1
    assert telemetry == [result]


@pytest.mark.parametrize('raw,reason', [(None, 'financial_environment_disabled'),
    ('', 'financial_environment_disabled'), ('false', 'financial_environment_disabled'),
    ('TRUE', 'invalid_financial_hook_flag'), (' true ', 'invalid_financial_hook_flag'),
    ('1', 'invalid_financial_hook_flag')])
def test_workflow_default_and_invalid_flags_never_open_financial_reader(monkeypatch, raw, reason):
    variables = dict(SOCIAL_GENERATION_HOOK_ENABLED='true', SOCIAL_REPORT_GENERATION_ENABLED='true')
    if raw is not None:
        variables['SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED'] = raw
    apply_runner_flags(monkeypatch, variables)
    def forbidden(*a, **kw):
        pytest.fail('Financial flag opened a source reader or consumer')
    monkeypatch.setattr(source_observations, 'read_native_financial_record_ids', forbidden)
    monkeypatch.setattr(bridge, '_invoke', forbidden)
    monkeypatch.setattr(bridge, '_record_outcome', lambda *a, **kw: None)
    result = bridge.dispatch_committed_generation(forbidden, domain='pending_bills',
        ingestion_id=23, dry_run=False, include_reports=False)
    assert result['reason'] == reason
    assert result['processed'] == result['drafts_created'] == 0


def test_financial_flag_alone_cannot_enable_global_hook_or_dry_run(monkeypatch):
    apply_runner_flags(monkeypatch, {'SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED': 'true'})
    def forbidden(*a, **kw):
        pytest.fail('Financial ceiling bypassed global/dry-run admission')
    monkeypatch.setattr(source_observations, 'read_native_financial_record_ids', forbidden)
    monkeypatch.setattr(bridge, '_invoke', forbidden)
    assert bridge.dispatch_committed_generation(forbidden, domain='pending_bills', ingestion_id=23, dry_run=False) is None
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'true')
    assert bridge.dispatch_committed_generation(forbidden, domain='pending_bills', ingestion_id=23, dry_run=True) is None
