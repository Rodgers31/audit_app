from contextlib import contextmanager

import pytest

from seeding.generation_limits import (generation_phase_seconds, generation_envelope_seconds,
    bounded_generation_envelope_seconds, SOURCE_AND_RECEIPT_SECONDS)


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
    expected_phase = 600 if domain == 'pending_bills' else 30
    expected = expected_phase + (30 if reports else 0) + 10
    assert observed == [expected, 'financial', *(['reports'] if reports else [])]
    assert expected == generation_envelope_seconds(domain, include_reports=reports)
    assert generation_phase_seconds(domain) == expected_phase
    assert 40 <= expected <= 640
    assert generation_phase_seconds(domain, reports=True) == 30


@pytest.mark.parametrize('value', [None, 0, 1, 'false', [], {}])
def test_phase_selection_cannot_silently_change_the_bound(value):
    with pytest.raises(ValueError):
        generation_phase_seconds('pending_bills', reports=value)
    with pytest.raises(ValueError):
        generation_envelope_seconds('pending_bills', include_reports=value)


def test_default_nightly_step_contains_the_bounded_final_generation_envelope():
    from test_nightly_runtime_profile import workflow_profile
    total, job = workflow_profile()
    step = next(step for step in job['steps'] if step.get('name') == 'Seed planned domains')
    envelope = bounded_generation_envelope_seconds('pending_bills', include_reports=True,
        remaining_seconds=total)
    assert envelope + SOURCE_AND_RECEIPT_SECONDS <= total
    # Source and generation now share the total run deadline; cleanup remains
    # reserved there, rather than appending a fresh phase beyond the run cap.
    assert total + SOURCE_AND_RECEIPT_SECONDS < step['timeout-minutes'] * 60
    assert job['timeout-minutes'] * 60 >= step['timeout-minutes'] * 60 + 300


@pytest.mark.parametrize('remaining,expected', [(2000,640),(100,90),(11,1),(10.9,0),(10,0),(0,0),(-1,0)])
def test_generation_envelope_reserves_cleanup_inside_the_remaining_run(remaining, expected):
    assert bounded_generation_envelope_seconds('pending_bills', include_reports=True,
        remaining_seconds=remaining) == expected


@pytest.mark.parametrize('remaining', [True, '100', [], float('inf'), float('nan'), 10**1000])
def test_generation_envelope_refuses_unbounded_or_untyped_remaining_time(remaining):
    with pytest.raises(ValueError):
        bounded_generation_envelope_seconds('pending_bills', include_reports=True,
            remaining_seconds=remaining)


def test_cli_clamps_generation_to_remaining_run_time(monkeypatch):
    import seeding.cli as cli
    import seeding.generation_dispatch as dispatch
    observed = []
    @contextmanager
    def budget(seconds):
        observed.append(seconds)
        yield
    monkeypatch.setattr(cli.time, 'monotonic', lambda:100)
    monkeypatch.setattr(cli, '_domain_timeout', budget)
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED','true')
    monkeypatch.setattr(dispatch, 'dispatch_committed_generation', lambda *a, **kw:observed.append('financial'))
    monkeypatch.setattr(dispatch, 'dispatch_committed_report_generation', lambda *a, **kw:observed.append('reports'))
    cli._post_commit_generation(object(), domain='pending_bills', ingestion_id=1, dry_run=False, deadline=150)
    assert observed == [40, 'financial', 'reports']


def test_exhausted_run_never_enters_an_unbounded_zero_second_alarm(monkeypatch):
    import seeding.cli as cli
    import seeding.generation_dispatch as dispatch
    monkeypatch.setattr(cli.time, 'monotonic', lambda:100)
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED','true')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED','true')
    def refuse(*a, **kw):
        raise AssertionError('No generation phase or alarm may start')
    monkeypatch.setattr(cli, '_domain_timeout', refuse)
    monkeypatch.setattr(dispatch, 'dispatch_committed_generation', refuse)
    monkeypatch.setattr(dispatch, 'dispatch_committed_report_generation', refuse)
    recorded = []
    monkeypatch.setattr(dispatch, 'record_generation_timeout', lambda *a, **kw:recorded.append(kw))
    cli._post_commit_generation(object(), domain='pending_bills', ingestion_id=1, dry_run=False, deadline=105)
    assert recorded == [dict(domain='pending_bills', ingestion_id=1, reports_started=False,
        financial_outcome={'state':'unavailable','reason':'generation_run_budget_exhausted',
            **dict.fromkeys(dispatch.COUNTERS,0)})]


@pytest.mark.parametrize('deadline', [True, '100', [], float('inf'), float('nan'), 10**1000])
def test_cli_refuses_invalid_deadlines_before_opening_a_factory(deadline):
    import seeding.cli as cli
    with pytest.raises(ValueError):
        cli._post_commit_generation(object(), domain='pending_bills', ingestion_id=1,
            dry_run=False, deadline=deadline)


@pytest.mark.parametrize('dry_run,flag', [(True,'true'), (False,'false')])
def test_exhausted_run_keeps_disabled_and_dry_hooks_without_factory_reads(monkeypatch, dry_run, flag):
    import seeding.cli as cli
    import seeding.generation_dispatch as dispatch
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED',flag)
    monkeypatch.setattr(cli.time, 'monotonic', lambda:100)
    def refuse(*a, **kw):
        raise AssertionError('No source or telemetry factory may open')
    monkeypatch.setattr(dispatch, 'record_generation_timeout', refuse)
    cli._post_commit_generation(object(), domain='pending_bills', ingestion_id=1,
        dry_run=dry_run, deadline=100)
