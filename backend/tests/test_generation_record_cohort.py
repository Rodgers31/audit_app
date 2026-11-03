"""A malformed reader result is not evidence of an empty committed cohort."""
import pytest

from seeding import generation_dispatch as bridge, source_observations as readers

PHASES = [(domain, reports) for reports, domains in (
    (False, ('counties_budget', 'national_budget', 'pending_bills', 'revenue_by_source')),
    (True, ('counties_budget', 'national_budget', 'pending_bills', 'revenue_by_source', 'audits')),
) for domain in domains]

MALFORMED = [
    pytest.param(None, id='none'), pytest.param(False, id='false'),
    pytest.param(0, id='zero'), pytest.param('', id='empty-string'),
    pytest.param({}, id='empty-mapping'), pytest.param(True, id='true'),
    pytest.param({1}, id='set'), pytest.param((True,), id='boolean-id'),
    pytest.param((0,), id='zero-id'), pytest.param((-1,), id='negative-id'),
    pytest.param((1.0,), id='float-id'), pytest.param((float('nan'),), id='nan-id'),
    pytest.param((float('inf'),), id='infinite-id'),
    pytest.param((2147483648,), id='overflow-id'),
    pytest.param((1, 1), id='duplicate-id'),
    pytest.param(tuple(range(1, 1002)), id='oversized'),
]


def dispatch(monkeypatch, domain, reports, cohort):
    for flag in ('SOCIAL_GENERATION_HOOK_ENABLED', 'SOCIAL_REPORT_GENERATION_ENABLED',
                 'SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED'):
        monkeypatch.setenv(flag, 'true')
    monkeypatch.setattr(bridge, 'read_county_budget_record_ids', lambda *a, **kw: cohort)
    monkeypatch.setattr(readers, 'read_native_financial_record_ids', lambda *a, **kw: cohort)
    monkeypatch.setattr(readers, 'read_native_report_record_ids', lambda *a, **kw: cohort)
    invocations, receipts = [], []
    def invoke(factory, ids, ingestion_id, **kwargs):
        invocations.append(ids)
        return dict(state='completed', reason='COMMITTED_EVIDENCE_CONSUMED',
            processed=len(ids), baselines=len(ids), unchanged=0, refused=0, drafts_created=0)
    monkeypatch.setattr(bridge, '_invoke', invoke)
    monkeypatch.setattr(bridge, '_invoke_reports', invoke)
    monkeypatch.setattr(bridge, '_record_outcome', lambda *a, **kw: receipts.append(a[3]))
    def factory():
        pytest.fail('The injected reader boundary must not access a database')
    method = bridge.dispatch_committed_report_generation if reports else bridge.dispatch_committed_generation
    result = method(factory, domain=domain, ingestion_id=1, dry_run=False,
                    **({} if reports else {'include_reports': False}))
    return result, invocations, receipts


@pytest.mark.parametrize('domain,reports', PHASES)
@pytest.mark.parametrize('cohort', MALFORMED)
def test_malformed_cohort_refuses_before_generation(monkeypatch, domain, reports, cohort):
    result, invocations, receipts = dispatch(monkeypatch, domain, reports, cohort)
    assert invocations == []
    assert result['state'] == 'failed'
    assert result['reason'] == ('report_source_read_failed' if reports else 'generation_source_read_failed')
    assert all(result[counter] == 0 for counter in bridge.COUNTERS)
    assert receipts == [result]


@pytest.mark.parametrize('domain,reports', PHASES)
@pytest.mark.parametrize('cohort', [(), []], ids=['empty-tuple', 'empty-list'])
def test_explicit_empty_cohort_remains_a_completed_noop(monkeypatch, domain, reports, cohort):
    result, invocations, receipts = dispatch(monkeypatch, domain, reports, cohort)
    assert result == dict(state='completed', reason='no_new_record_lineage',
        processed=0, drafts_created=0, baselines=0, unchanged=0, refused=0)
    assert invocations == [] and receipts == [result]


@pytest.mark.parametrize('domain,reports', PHASES)
@pytest.mark.parametrize('cohort', [(1,), [1, 2147483647], tuple(range(1, 1001))],
                         ids=['one', 'bounded-list', 'maximum-cohort'])
def test_valid_cohort_reaches_generation_exactly_once(monkeypatch, domain, reports, cohort):
    result, invocations, receipts = dispatch(monkeypatch, domain, reports, cohort)
    assert result['state'] == 'completed' and result['processed'] == len(cohort)
    assert len(invocations) == 1 and tuple(invocations[0]) == tuple(cohort)
    assert receipts == [result]
