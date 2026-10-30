"""Real alarm proofs for each CLI dispatch, including slow source work."""
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('reports', [False, True])
def test_financial_dispatch_cannot_borrow_the_receipt_or_report_allowance(monkeypatch, reports):
    import seeding.cli as cli
    import seeding.generation_dispatch as dispatch
    import seeding.generation_limits as limits
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED','true')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED','true' if reports else 'false')
    monkeypatch.setattr(limits,'PENDING_BILLS_FINANCIAL_SECONDS',1)
    monkeypatch.setattr(limits,'DEFAULT_PHASE_SECONDS',1)
    monkeypatch.setattr(limits,'SOURCE_AND_RECEIPT_SECONDS',3)
    completed, recorded = [], []
    def slow_financial(*a, **kw):
        time.sleep(1.5)
        completed.append('financial')
    monkeypatch.setattr(dispatch,'dispatch_committed_generation',slow_financial)
    monkeypatch.setattr(dispatch,'dispatch_committed_report_generation',lambda *a, **kw:completed.append('report'))
    monkeypatch.setattr(dispatch,'record_generation_timeout',lambda *a, **kw:recorded.append(kw))
    started = time.monotonic()
    cli._post_commit_generation(object(),domain='pending_bills',ingestion_id=1,dry_run=False)
    elapsed = time.monotonic()-started
    assert completed == [], {'completed':completed,'elapsed':elapsed}
    assert len(recorded) == 1 and recorded[0]['financial_outcome'] is None
    assert recorded[0]['reports_started'] is False
    assert .8 <= elapsed < 1.4


def test_report_dispatch_has_its_own_hard_cap_and_preserves_financial_result(monkeypatch):
    import seeding.cli as cli
    import seeding.generation_dispatch as dispatch
    import seeding.generation_limits as limits
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED','true')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED','true')
    monkeypatch.setattr(limits,'PENDING_BILLS_FINANCIAL_SECONDS',1)
    monkeypatch.setattr(limits,'DEFAULT_PHASE_SECONDS',1)
    monkeypatch.setattr(limits,'SOURCE_AND_RECEIPT_SECONDS',3)
    financial = dict(state='failed',reason='GENERATION_DEADLINE_EXCEEDED',processed=3,
        baselines=1,unchanged=2,drafts_created=0,refused=0)
    finished, recorded = [], []
    monkeypatch.setattr(dispatch,'dispatch_committed_generation',lambda *a, **kw:financial)
    def slow_reports(*a, **kw):
        time.sleep(1.5)
        finished.append('report')
    monkeypatch.setattr(dispatch,'dispatch_committed_report_generation',slow_reports)
    monkeypatch.setattr(dispatch,'record_generation_timeout',lambda *a, **kw:recorded.append(kw))
    cli._post_commit_generation(object(),domain='pending_bills',ingestion_id=1,dry_run=False)
    assert finished == []
    assert len(recorded) == 1
    assert recorded[0]['financial_outcome'] is financial
    assert recorded[0]['reports_started'] is True


@pytest.mark.parametrize('spent,report_budget', [(38,2),(40,0)])
def test_report_allowance_does_not_reset_the_shared_run_deadline(monkeypatch, spent, report_budget):
    import seeding.cli as cli
    import seeding.generation_dispatch as dispatch
    clock = [100.0]
    monkeypatch.setattr(cli,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED','true')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED','true')
    entered, recorded = [], []
    @contextmanager
    def alarm(seconds):
        assert seconds > 0
        entered.append(seconds)
        yield
    monkeypatch.setattr(cli,'_domain_timeout',alarm)
    financial = dict(state='completed',reason='COMMITTED_EVIDENCE_CONSUMED',processed=1,
        baselines=1,unchanged=0,drafts_created=0,refused=0)
    def consume(*a, **kw):
        clock[0] += spent
        return financial
    monkeypatch.setattr(dispatch,'dispatch_committed_generation',consume)
    reports = []
    monkeypatch.setattr(dispatch,'dispatch_committed_report_generation',lambda *a, **kw:reports.append(True))
    monkeypatch.setattr(dispatch,'record_generation_timeout',lambda *a, **kw:recorded.append(kw))
    cli._post_commit_generation(object(),domain='pending_bills',ingestion_id=1,dry_run=False,deadline=150)
    assert entered == [40, *([report_budget] if report_budget else [])]
    assert reports == ([True] if report_budget else [])
    if report_budget == 0:
        assert recorded[0]['financial_outcome'] is financial
        assert recorded[0]['reports_started'] is False
    else:
        assert recorded == []
