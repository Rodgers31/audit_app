"""Bounded producer orchestration; synthetic parser, real conversion/receipts/SQL.

This is not a retained-PDF parse or a hosted R2 acceptance run. The fixed counts
exercise the producer's orchestration gates with explicitly synthetic input.
Run with --confcutdir=tests in an empty, dotenv-disabled test environment.
"""
from copy import deepcopy
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace
import weakref

import pytest

from seeding import parse_cache, pdf_parsers
from seeding.config import SeedingSettings
from services.response_receipts import receipt_is_sealed
from test_r2_receipt_store import Boundary


PRODUCER = Path(__file__).parents[1] / "scripts/r2_producer_acceptance.py"
BODY = b"%PDF-1.4\nBatch 8 synthetic orchestration bytes; not a parsed PDF.\n"
MARKER = "batch8-capture-channel-alive"


@pytest.fixture
def producer(monkeypatch):
    def deny_network(*args, **kwargs):
        raise AssertionError("Producer fixture attempted real network IO")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)
    spec = importlib.util.spec_from_file_location("owned_r2_producer", PRODUCER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_producer_passes_critical_lint_gate():
    result = subprocess.run(
        [sys.executable, "-m", "flake8", str(PRODUCER), "--count",
         "--select=E9,F63,F7,F82", "--show-source", "--statistics"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def harness(producer, monkeypatch, tmp_path):
    settings = SeedingSettings(_env_file=None, parse_cache_enabled=False,
                               cache_path=tmp_path / "cache", storage_path=tmp_path / "storage")
    boundary = Boundary(tmp_path / "objects")
    store = boundary.store()
    source_sha = store.put(BODY)
    monkeypatch.setattr(producer, "PDF_SHA", source_sha)
    monkeypatch.setattr(producer, "PDF_SIZE", len(BODY))
    state = SimpleNamespace(pages=935, tables=1129, records=468, cached=False,
                            fail_sql=False, observed=[], refs=[], heavyweight_refs=[])
    counts = {"read": 0, "put": 0}
    for operation in counts:
        original = getattr(store, operation)

        def measured(*args, _original=original, _operation=operation, **kwargs):
            counts[_operation] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(store, operation, measured)

    class HeavyRows(list):
        def __init__(self, rows):
            super().__init__(rows)
            state.heavyweight_refs.append(weakref.ref(self))

    class Coverage(dict):
        pass

    class SyntheticParser:
        def __init__(self, path):
            self.path = path

        def parse(self):
            # The real producer wraps this call and observes every page marker.
            from pdfplumber.page import Page
            for number in range(1, state.pages + 1):
                Page.extract_tables(SimpleNamespace(page_number=number))
            self.tables = [pdf_parsers.ExtractedTable(
                page_number=1, table_index=i, headers=[MARKER], rows=HeavyRows([["100"]]),
                bbox=(0, 0, 1, 1)) for i in range(state.tables)]
            self.revenue_coverage = Coverage({"Nairobi": {"status": MARKER}})
            state.heavyweight_refs.append(weakref.ref(self.revenue_coverage))
            rows = []
            for i in range(state.records):
                row = {"county": "Nairobi", "fiscal_year": "2024/25",
                       "category": "Total" if i == 0 else f"Synthetic {i}",
                       "allocated": "100", "absorbed": "50", "amounts_in": "kes",
                       "page_ref": "1", "notes": MARKER}
                if i < 189:
                    row["_pdf_cells"] = {
                        measure: {"raw_value": value, "raw_unit": "KES", "unit_checked": True,
                                  "locator": {"page": 1, "cell": f"synthetic-{i}-{measure}"}}
                        for measure, value in (("allocated_amount", "100"), ("actual_spent", "50"))
                    }
                rows.append(row)
            return rows

    monkeypatch.setattr(pdf_parsers, "CoBQuarterlyReportParser", SyntheticParser)
    from pdfplumber.page import Page
    monkeypatch.setattr(Page, "extract_tables", lambda *args, **kwargs: [])
    actual_parse = parse_cache.parse_with_cache

    def observed_parse(*args, **kwargs):
        result = actual_parse(*args, **kwargs)
        state.refs.append(weakref.ref(result))
        return list(result) if state.cached else result

    monkeypatch.setattr(parse_cache, "parse_with_cache", observed_parse)

    def observe_comparison(packet):
        # Known distinct data must pass through all four real capture fields.
        assert len(packet["tables"]) == 1129
        assert packet["tables"][0]["headers"] == [MARKER]
        assert len(packet["parsed_records"]) == 468
        assert packet["parsed_records"][0]["notes"] == MARKER
        assert packet["revenue_coverage"] == {"Nairobi": {"status": MARKER}}
        converted = packet["converted_records"]
        assert len(converted) == 468
        assert converted[0]["allocated_amount"] == 100
        assert converted[0]["actual_amount"] == 50
        entries = [e for row in converted for e in row["source_evidence"]]
        assert len(entries) == 378
        assert all(receipt_is_sealed(e["_response_receipt"]) for e in entries)
        assert all(e["checks"]["transport"] is False for e in entries)
        assert entries[0]["_response_receipt"]["status"] is None
        assert entries[0]["_response_receipt"]["acquired_at"] is None
        assert entries[0]["_response_receipt"]["acquisition_kind"] == "local_cached_bytes"
        assert state.refs[0]() is packet["parsed_records"]
        assert sum(ref() is not None for ref in state.heavyweight_refs) == 1130
        state.observed.append(MARKER)

    # The retained semantic oracle is unavailable; this observer is not that
    # oracle. compare_pdf_output itself has separate executed controls below.
    monkeypatch.setattr(producer, "compare_pdf_output", observe_comparison)
    actual_sql = producer.pdf_sqlite_output

    def sqlite_after_release(settings, counts, work, converted):
        gc.collect()
        assert state.refs[0]() is None, "Captured parse still retained during SQLite persistence"
        assert all(ref() is None for ref in state.heavyweight_refs), "Tables or revenue coverage still retained"
        state.observed.append("capture-released-before-sql")
        if state.fail_sql:
            raise producer.Refusal("budget_persistence_failed")
        report = actual_sql(settings, counts, work, converted)
        state.observed.append("real-sqlite-public-qualification-complete")
        return report

    monkeypatch.setattr(producer, "pdf_sqlite_output", sqlite_after_release)
    return SimpleNamespace(module=producer, state=state, store=store, settings=settings,
                           work=tmp_path, counts=counts, boundary=boundary)


def test_capture_conversion_release_and_sqlite_qualification(harness):
    h = harness
    report = h.module.pdf_producer(h.settings, h.store, h.counts, h.work)
    assert h.state.observed == [MARKER, "capture-released-before-sql",
                                "real-sqlite-public-qualification-complete"]
    assert report["publisher_http_authority"] is False
    assert report["sqlite_budget_rows"] == 468
    assert report["sqlite_receipt_extractions"] == 1
    assert report["qualification_fields_checked"] == 1404
    assert report["public_object_gets"] == 0
    assert h.store.read(h.module.PDF_SHA) == BODY
    print(json.dumps({"scope": "synthetic parser orchestration, real SQLite; no full PDF replay",
                      "source_sha256": h.module.PDF_SHA, "markers": h.state.observed,
                      "sql_rows": report["sqlite_budget_rows"],
                      "qualification_fields": report["qualification_fields_checked"]}))


@pytest.mark.parametrize("fault,reason", [
    ("bytes", "retained_pdf_mismatch"), ("cached", "fresh_parse_required"),
    ("pages", "pdf_output_count"), ("tables", "pdf_output_count"),
    ("records", "pdf_output_count"), ("receipt", "pdf_retained_qualification"),
    ("sql", "budget_persistence_failed"),
])
def test_capture_failures_do_not_report_success(harness, monkeypatch, fault, reason):
    h = harness
    if fault == "bytes":
        monkeypatch.setattr(h.module, "PDF_SIZE", len(BODY) + 1)
    elif fault == "cached":
        h.state.cached = True
    elif fault in ("pages", "tables", "records"):
        setattr(h.state, fault, getattr(h.state, fault) - 1)
    elif fault == "sql":
        h.state.fail_sql = True
    else:
        from seeding.domains.counties_budget import fetcher
        actual_convert = fetcher.convert_county_pdf_records

        def corrupt_receipt(*args, **kwargs):
            converted = actual_convert(*args, **kwargs)
            converted[0]["source_evidence"][0]["_response_receipt"]["status"] = 200
            return converted

        monkeypatch.setattr(fetcher, "convert_county_pdf_records", corrupt_receipt)
    with pytest.raises(h.module.Refusal, match=f"^{reason}$"):
        h.module.pdf_producer(h.settings, h.store, h.counts, h.work)
    assert "real-sqlite-public-qualification-complete" not in h.state.observed


def test_comparison_projection_never_changes_runtime_receipt(producer, monkeypatch):
    packet = {"tables": [], "parsed_records": [], "revenue_coverage": {},
              "converted_records": [{"source_evidence": [{"_response_receipt": {
                  "storage_scope": "r2_private", "status": None, "acquired_at": None,
                  "byte_check": {"checked_at": "original-time"}}}]}]}
    before = deepcopy(packet)
    # Literal expected canonical bytes are independent of the projection code.
    expected = b'{"converted_records":[{"source_evidence":[{"_response_receipt":{"acquired_at":null,"byte_check":{"checked_at":"2026-10-07T00:00:00+00:00"},"status":null,"storage_scope":"local"}}]}],"parsed_records":[],"revenue_coverage":{},"tables":[]}'
    monkeypatch.setattr(producer, "ORACLE_SHA", hashlib.sha256(expected).hexdigest())
    producer.compare_pdf_output(packet)
    assert packet == before
    packet["converted_records"][0]["source_evidence"][0]["_response_receipt"]["status"] = 200
    with pytest.raises(producer.Refusal, match="^complete_pdf_semantics_mismatch$"):
        producer.compare_pdf_output(packet)


def test_cli_default_refuses_without_storage_or_output(producer, capsys, tmp_path):
    assert producer.main([]) == 1
    assert json.loads(capsys.readouterr().out) == {"status": "FAILED", "reason": "live_not_authorized"}
    assert list(tmp_path.iterdir()) == []
