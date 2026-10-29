from contextlib import contextmanager

import pytest

from seeding.generation_limits import generation_phase_seconds, generation_envelope_seconds


@pytest.mark.parametrize('domain', ['counties_budget', 'national_budget', 'revenue_by_source', 'audits', 'pending_bills'])
@pytest.mark.parametrize('reports', [False, True])
def test_cli_envelope_contains_exact_phase_budgets_and_receipt_reserve(domain, reports, monkeypatch):
    import seeding.cli as cli
    import seeding.generation_dispatch as dispatch
    observed = []

    @contextmanager
    def budget(seconds):
        observed.append(seconds)
        yield

    monkeypatch.setattr(cli, '_domain_timeout', budget)
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED', 'true' if reports else 'false')
    monkeypatch.setattr(dispatch, 'dispatch_committed_generation', lambda *a, **kw: observed.append('financial'))
    monkeypatch.setattr(dispatch, 'dispatch_committed_report_generation', lambda *a, **kw: observed.append('reports'))
    cli._post_commit_generation(object(), domain=domain, ingestion_id=1, dry_run=False)
    expected = generation_phase_seconds(domain) + (generation_phase_seconds(domain, reports=True) if reports else 0) + 10
    assert observed == [expected, 'financial', *(['reports'] if reports else [])]
    assert expected == generation_envelope_seconds(domain, include_reports=reports)
    assert 40 <= expected <= 160
    assert generation_phase_seconds(domain, reports=True) == 30


@pytest.mark.parametrize('value', [None, 0, 1, 'false', [], {}])
def test_phase_selection_cannot_silently_change_the_bound(value):
    with pytest.raises(ValueError):
        generation_phase_seconds('pending_bills', reports=value)
    with pytest.raises(ValueError):
        generation_envelope_seconds('pending_bills', include_reports=value)


def test_default_nightly_step_contains_the_largest_final_generation_envelope():
    from test_nightly_runtime_profile import workflow_profile
    total, job = workflow_profile()
    step = next(step for step in job['steps'] if step.get('name') == 'Seed planned domains')
    envelope = generation_envelope_seconds('pending_bills', include_reports=True)
    assert total + envelope < step['timeout-minutes'] * 60
    assert job['timeout-minutes'] * 60 >= step['timeout-minutes'] * 60 + 300
