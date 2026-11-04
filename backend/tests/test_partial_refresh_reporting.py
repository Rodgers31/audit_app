"""Partial primary commits must not be described as fixture-only refreshes."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from seeding.staleness import WARN, check_ingestion_freshness, hollow_run_findings


class _Session:
    def __init__(self, rows):
        self.rows = rows

    def query(self, _model):
        return self

    def filter(self, _condition):
        return self

    def all(self):
        return self.rows


def _job(domain, mode="partial", job_id=1):
    return SimpleNamespace(
        id=job_id, domain=domain, started_at=datetime(2026, 11, 4, 2, 44),
        status="completed", items_processed=5, items_created=0, items_updated=4,
        meta={"source_mode": mode, "source_fallback_reason": "coverage_incomplete",
              "source_detail": "four primary records committed; one source held",
              "oag_national_discovery": {"state": "completed"}},
    )


@pytest.mark.parametrize("domain", ["audits", "fiscal_summary", "pending_bills",
                                     "debt_timeline", "population", "revenue_by_source"])
@pytest.mark.parametrize("window", [False, True], ids=["current-run", "recent-window"])
def test_partial_warning_preserves_primary_commit_uncertainty(domain, window):
    job = _job(domain)
    findings = (check_ingestion_freshness(_Session([job]),
                now=datetime(2026, 11, 4, 3, tzinfo=timezone.utc), domains=[domain])
                if window else hollow_run_findings([job]))
    assert len(findings) == 1
    finding = findings[0]
    assert finding.level == WARN
    assert "publisher refresh incomplete" in finding.message
    assert "coverage_incomplete" in finding.message
    assert "SECONDARY" not in finding.message
    assert "still a fixture" not in finding.message


def test_recent_window_does_not_describe_fixture_nights_as_partial_refreshes():
    jobs = [_job("fiscal_summary", mode="fixture"),
            _job("fiscal_summary", job_id=2)]
    findings = check_ingestion_freshness(_Session(jobs),
        now=datetime(2026, 11, 4, 3, tzinfo=timezone.utc), domains=["fiscal_summary"])
    assert len(findings) == 1
    assert findings[0].level == WARN
    assert "1/2 partial" in findings[0].message
