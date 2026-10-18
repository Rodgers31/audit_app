"""No schema/import before opt-in; generation outcomes cannot impersonate ETL."""
import pytest

from seeding import generation_dispatch as bridge


@pytest.mark.parametrize("domain,dry_run", [("counties_budget", False), ("fiscal_summary", False), ("counties_budget", True)])
def test_default_off_opens_no_factory_or_social_hook(monkeypatch, domain, dry_run):
    monkeypatch.delenv("SOCIAL_GENERATION_HOOK_ENABLED", raising=False)
    def forbidden(*args):
        pytest.fail("Disabled generation entered a dependency")
    monkeypatch.setattr(bridge, "_invoke", forbidden)
    monkeypatch.setattr(bridge, "read_county_budget_record_ids", forbidden)
    assert bridge.dispatch_committed_generation(forbidden, domain=domain, ingestion_id=1, dry_run=dry_run) is None


@pytest.mark.parametrize("change", [{"processed": True}, {"processed": 0}, {"processed": 2}, {"refused": -1},
    {"drafts_created": float("nan")}, {"state": "success"}, {"reason": "private credentials"}, {"extra": 1}])
def test_malformed_hook_results_never_certify_success(change):
    valid = {"state": "completed", "reason": "COMMITTED_EVIDENCE_CONSUMED", "processed": 1,
             "drafts_created": 0, "baselines": 1, "unchanged": 0, "refused": 0}
    with pytest.raises(ValueError, match="Invalid generation outcome"):
        bridge._validate_result({**valid, **change}, 1)


def test_failed_partial_progress_is_preserved():
    value = {"state": "failed", "reason": "GENERATION_DATABASE_UNAVAILABLE", "processed": 1,
             "drafts_created": 1, "baselines": 0, "unchanged": 0, "refused": 0}
    assert bridge._validate_result(value, 2) == value


def test_refused_evidence_cannot_report_completed():
    value = {"state": "completed", "reason": "SOURCE_EVIDENCE_INELIGIBLE", "processed": 1,
             "drafts_created": 0, "baselines": 0, "unchanged": 0, "refused": 1}
    with pytest.raises(ValueError, match="Invalid generation outcome"):
        bridge._validate_result(value, 1)


@pytest.mark.parametrize("bad", [None, True, False, 0, -1, 2147483648, 1.0, "1", float("nan"), float("inf")])
def test_bridge_ids_refuse_before_opening_factory(monkeypatch, bad):
    monkeypatch.setenv("SOCIAL_GENERATION_HOOK_ENABLED", "true")
    def forbidden():
        pytest.fail("Invalid ID entered factory")
    with pytest.raises(ValueError, match="bounded ingestion"):
        bridge.dispatch_committed_generation(forbidden, domain="counties_budget", ingestion_id=bad, dry_run=False)


@pytest.mark.parametrize("raw", [None, {}, [], {"state": "completed", "processed": True},
    {"state": "completed", "processed": 1, "drafts_created": 0, "baselines": 0, "unchanged": 0, "refused": 1},
    {"state": "completed", "execution_unverified": "true", "processed": 1, "drafts_created": 0, "baselines": 1, "unchanged": 0, "refused": 0},
    {"state": "completed", "execution_unverified": True, "processed": 0}])
def test_operator_projection_never_hides_malformed_generation_receipts(raw):
    from routers.admin_operations import safe_job_metadata
    out = safe_job_metadata({"post_commit_generation": raw, "secret": "PRIVATE_DIAGNOSTIC"})
    receipt = out["post_commit_generation"]
    assert receipt["state"] == "unavailable" and receipt["execution_unverified"] is True
    assert receipt["processed"] is None
    assert "PRIVATE_DIAGNOSTIC" not in str(out)


@pytest.mark.parametrize('phase', ['financial', 'report'])
def test_native_report_alarm_preserves_confirmed_financial_progress(monkeypatch, phase):
    from seeding import cli
    from contextlib import nullcontext
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED', 'true')
    monkeypatch.setattr(cli, '_domain_timeout', lambda seconds: nullcontext())
    confirmed = {'state':'completed','reason':'COMMITTED_EVIDENCE_CONSUMED','processed':2,
                 'drafts_created':1,'baselines':1,'unchanged':0,'refused':0}
    def financial(*args, **kwargs):
        assert kwargs['include_reports'] is False
        if phase == 'financial': raise cli.DomainTimeoutError()
        return confirmed
    def report(*args, **kwargs): raise cli.DomainTimeoutError()
    recorded = {}
    monkeypatch.setattr(bridge, 'dispatch_committed_generation', financial)
    monkeypatch.setattr(bridge, 'dispatch_committed_report_generation', report)
    monkeypatch.setattr(bridge, '_record_outcome', lambda *args, key='post_commit_generation': recorded.update({key:args[-1]}))
    cli._post_commit_generation(object(), domain='counties_budget', ingestion_id=1, dry_run=False)
    financial_result = recorded['post_commit_generation']
    report_result = recorded['post_commit_report_generation']
    if phase == 'report':
        assert financial_result == confirmed
        assert report_result['execution_unverified'] is True and report_result['processed'] is None
    else:
        assert financial_result['execution_unverified'] is True and financial_result['processed'] is None
        assert report_result['processed'] == 0 and report_result['reason'] == 'report_generation_not_started'


def test_timeout_cannot_promote_malformed_financial_summary(monkeypatch):
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED', 'true')
    monkeypatch.setattr(bridge, '_record_outcome', lambda *args, **kwargs: None)
    result = bridge.record_generation_timeout(object(), domain='counties_budget', ingestion_id=1,
        financial_outcome={'processed':True}, reports_started=True)
    assert result['execution_unverified'] is True and result['processed'] is None
