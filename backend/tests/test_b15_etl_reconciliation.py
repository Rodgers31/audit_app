"""Native Treasury reconciliation must complete before any writer is entered."""
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from seeding.config import SeedingSettings
from seeding.domains import fiscal_summary
from seeding.types import DomainRunContext
from services import trust_guards


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("failure_at", [0, 1])
def test_reconciliation_failure_never_enters_writer(monkeypatch, dry_run, failure_at):
    records = [SimpleNamespace(fiscal_year="2025/26"), SimpleNamespace(fiscal_year="2026/27")]
    monkeypatch.setattr(fiscal_summary, "create_http_client", lambda settings: nullcontext(None))
    monkeypatch.setattr(fiscal_summary.fetcher, "fetch_fiscal_summary_payload", lambda *args: {})
    monkeypatch.setattr(fiscal_summary.parser, "parse_fiscal_summary_payload", lambda payload: records)
    writes = []
    monkeypatch.setattr(fiscal_summary.writer, "write_fiscal_summary_records",
                        lambda *args: (writes.append(args) or (2, 0)))
    def broken_guard(record):
        if record is records[failure_at]:
            raise RuntimeError("private upstream diagnostics")
        return []
    monkeypatch.setattr(trust_guards, "check_fiscal_summary", broken_guard)
    with pytest.raises(RuntimeError, match="Fiscal reconciliation unavailable"):
        fiscal_summary.run(None, SeedingSettings(), DomainRunContext(None, dry_run))
    assert writes == []


def test_validated_rows_alone_reach_writer(monkeypatch):
    clean = SimpleNamespace(fiscal_year="2025/26")
    bad = SimpleNamespace(fiscal_year="2026/27")
    monkeypatch.setattr(fiscal_summary, "create_http_client", lambda settings: nullcontext(None))
    monkeypatch.setattr(fiscal_summary.fetcher, "fetch_fiscal_summary_payload", lambda *args: {})
    monkeypatch.setattr(fiscal_summary.parser, "parse_fiscal_summary_payload", lambda payload: [clean, bad])
    monkeypatch.setattr(trust_guards, "check_fiscal_summary", lambda rec: [] if rec is clean else ["does not reconcile"])
    received = []
    def write(session, records, metadata):
        received.extend(records)
        return (1, 0)
    monkeypatch.setattr(fiscal_summary.writer, "write_fiscal_summary_records", write)
    result = fiscal_summary.run(None, SeedingSettings(), DomainRunContext(None, False))
    assert received == [clean]
    assert result.items_created == 1
    assert result.errors == ["Quarantined 2026/27: does not reconcile"]
