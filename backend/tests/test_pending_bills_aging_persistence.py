"""Source-shaped controls through the actual atomic writer and public reader.

The tiny acquired bytes are inert fixtures, not official live-source acceptance.
"""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256

import httpx
import pytest
from sqlalchemy.orm import Session

from models import Entity, EntityType, Extraction, Loan, SourceDocument
from seeding.domains.pending_bills import aging
from seeding.domains.pending_bills.parser import PendingBillRecord
from seeding.domains.pending_bills.writer import write_pending_bills
from seeding.parse_cache import parse_with_cache
from seeding.pdf_evidence import (
    bind_parse_receipt,
    cell_evidence,
    seal_pdf_observations,
)
from seeding.pdf_parsers import KENYAN_COUNTIES
from services.pending_bills_aging import aging_observations
from services.publication_gate import COUNTY_PENDING_BILLS_PUBLICATION
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_response, copy_receipt

URL = "https://cob.go.ke/b83-inert-aging-fixture.pdf"


def synthetic_tables():
    header = [
        [
            "County",
            "County Executives Ageing analysis (Amount in Kshs.Millions)",
            None,
            None,
            None,
            "Total (Kshs. Millions)",
        ],
        [None, *aging.BANDS, None],
    ]
    rows = [[n, "1.00", "2.00", "3.00", "4.00", "10.00"] for n in KENYAN_COUNTIES]
    rows[KENYAN_COUNTIES.index("Nandi")] = ["Nandi", "-", "-", "-", "-", "-"]
    return [
        (53, [*deepcopy(header), *rows[:20]]),
        (54, [*header, *rows[20:], ["Total", "46", "92", "138", "184", "460"]]),
    ]


def payables_entries():
    return [
        dict(
            county=n,
            as_at=aging.AS_AT,
            table="Table 2.10",
            page=51,
            executive_millions=None if n == "Nandi" else "10.00",
        )
        for n in KENYAN_COUNTIES
    ]


def source_input(tmp_path, monkeypatch):
    body = b"%PDF-B83-INERT-EXECUTABLE-FIXTURE"
    monkeypatch.setattr(aging, "ARTIFACT_SHA256", sha256(body).hexdigest())
    path = tmp_path / "input.pdf"
    path.write_bytes(body)
    cohort = aging.parse_aging_tables(synthetic_tables(), payables_entries())
    parsed = parse_with_cache(
        path,
        cache_dir=tmp_path / "parse",
        kind="b83-aging-fixture",
        parse_fn=lambda: [cohort],
        enabled=False,
    )
    response = httpx.Response(
        200,
        content=body,
        headers={"content-type": "application/pdf"},
        request=httpx.Request("GET", URL),
    )
    receipt = capture_response(
        response, LocalReceiptStore(tmp_path / "receipts"), source_kind="pdf"
    )
    receipt = copy_receipt(receipt, parser_version="b83-inert-aging-fixture-v1")
    receipt = bind_parse_receipt(receipt, parsed)
    observation = aging.prepare_aging(parsed, receipt)
    records, evidence = [], []
    for county in KENYAN_COUNTIES:
        if county == "Nandi":
            continue
        record = PendingBillRecord(
            entity_name=f"{county} County",
            entity_type="county",
            category="county",
            fiscal_year="FY2025/26",
            total_pending=Decimal(11000000),
            as_at=aging.AS_AT,
            source_table="Table 2.10",
            source_page=51,
        )
        cell = cell_evidence(
            receipt=receipt,
            identity=dict(
                measure="outstanding",
                entity_id=None,
                geography=record.entity_name,
                period=aging.AS_AT,
                unit="KES",
                basis="actual",
                dimensions={
                    "lender": f"Pending Bills — County Governments ({record.entity_name})",
                    "debt_category": "pending_bills",
                },
            ),
            raw_value="11",
            value="11000000",
            raw_unit="KES million",
            factor="1000000",
            locator={
                "page": 51,
                "table": "Table 2.10",
                "cell": f"{county} / Grand Total",
            },
        )
        record.source_evidence = [cell]
        evidence.append(cell)
        records.append(record)
    seal_pdf_observations(evidence)
    return records, observation


def populate_counties(db, country_id):
    for name in KENYAN_COUNTIES:
        db.add(
            Entity(
                country_id=country_id,
                type=EntityType.COUNTY,
                canonical_name=f"{name} County",
                slug=name.lower().replace(" ", "-"),
            )
        )
    db.flush()


def write(db, records, cohort, **overrides):
    kwargs = dict(
        records=records,
        aging=cohort,
        source_url=URL,
        source_title="B83 inert executive fixture",
        publisher="Office of the Controller of Budget (OCOB)",
        publication=COUNTY_PENDING_BILLS_PUBLICATION,
        county_table={
            "as_at": aging.AS_AT,
            "table": "Table 2.10",
            "not_reported": ["Nandi"],
        },
    )
    kwargs.update(overrides)
    return write_pending_bills(db, **kwargs)


def test_source_writer_reader_idempotency_and_missing(
    db_session, seed_country, tmp_path, monkeypatch
):
    populate_counties(db_session, seed_country.id)
    records, cohort = source_input(tmp_path, monkeypatch)
    assert write(db_session, records, cohort) == (46, 0)
    result = aging_observations(db_session, as_at=aging.AS_AT)
    executive = result["county_executive"]
    assert executive["status"] == "qualified"
    assert executive["buckets"][0]["amount"] == 46000000
    assert executive["coverage"]["missing_counties"] == ["Nandi"]
    assert executive["complete_total"] is None
    assert executive["chart_supported"] is True
    assert result["national"]["buckets"] is None
    nandi = aging_observations(db_session, as_at=aging.AS_AT, county="Nandi County")[
        "county_executive"
    ]
    assert [b["amount"] for b in nandi["buckets"]] == [None] * 4
    assert nandi["chart_supported"] is False
    count = db_session.query(Extraction).count()
    assert write(db_session, records, cohort) == (0, 46)
    assert db_session.query(Extraction).count() == count
    from main import _pending_bills_summary_from_loans

    summary = _pending_bills_summary_from_loans(db_session)
    assert (
        summary["aging_observations"]["county_executive"]["reported_total"] == 460000000
    )
    assert summary["total_pending_amount"] is None
    assert summary["aging_buckets"] is None


@pytest.mark.parametrize("bad", [None, {}, [], True, "NaN", float("inf"), -1])
def test_hostile_cell_refused(bad):
    tables = synthetic_tables()
    tables[0][1][2][1] = bad
    if bad is None:
        parsed = aging.parse_aging_tables(tables, payables_entries())
        assert parsed["rows"][0]["amounts"][0] is None
    else:
        with pytest.raises(ValueError):
            aging.parse_aging_tables(tables, payables_entries())


def test_missing_continuation_duplicate_and_wrong_bands_refuse():
    with pytest.raises(ValueError, match="Incomplete"):
        aging.parse_aging_tables(synthetic_tables()[:1], payables_entries())
    tables = synthetic_tables()
    tables[1][1].append(tables[0][1][2])
    with pytest.raises(ValueError, match="Duplicated"):
        aging.parse_aging_tables(tables, payables_entries())
    tables = synthetic_tables()
    tables[0][1][1][1] = "0-30d"
    with pytest.raises(ValueError, match="bands"):
        aging.parse_aging_tables(tables, payables_entries())


def test_untrusted_json_or_late_corruption_rolls_back_entire_edition(
    db_session, seed_country, tmp_path, monkeypatch
):
    populate_counties(db_session, seed_country.id)
    records, cohort = source_input(tmp_path, monkeypatch)
    for candidate in [dict(cohort), deepcopy(cohort)]:
        if isinstance(candidate, aging.AgingIngestion):
            candidate["rows"][-1]["source_evidence"][0]["value"] = "123"
        with pytest.raises(ValueError):
            write(db_session, records, candidate)
        assert db_session.query(Loan).count() == 0
        assert db_session.query(SourceDocument).count() == 0
        assert db_session.query(Extraction).count() == 0


def test_new_unaged_write_clears_pointer_without_deleting_history(
    db_session, seed_country, tmp_path, monkeypatch
):
    populate_counties(db_session, seed_country.id)
    records, cohort = source_input(tmp_path, monkeypatch)
    write(db_session, records, cohort)
    assert (
        aging_observations(db_session, as_at="2025-06-30")["county_executive"]["status"]
        == "unavailable"
    )
    count = db_session.query(Extraction).count()
    write(db_session, records, None)
    assert (
        aging_observations(db_session, as_at=aging.AS_AT)["county_executive"]["status"]
        == "unavailable"
    )
    assert db_session.query(Extraction).count() == count


def test_real_http_summary_and_county_keep_scopes(
    client, db_session, seed_country, tmp_path, monkeypatch
):
    populate_counties(db_session, seed_country.id)
    records, cohort = source_input(tmp_path, monkeypatch)
    write(db_session, records, cohort)
    summary = client.get("/api/v1/pending-bills/summary")
    assert summary.status_code == 200
    assert (
        summary.json()["aging_observations"]["county_executive"]["reported_total"]
        == 460000000
    )
    assert summary.json()["aging_observations"]["national"]["buckets"] is None
    county = client.get("/api/v1/pending-bills/counties/nandi")
    assert county.status_code == 200
    assert county.json()["total_pending"] is None
    assert county.json()["aging_buckets"] is None
    assert [
        b["amount"]
        for b in county.json()["aging_observations"]["county_executive"]["buckets"]
    ] == [None] * 4


def test_same_url_changed_artifact_and_source_mutation_are_refused(
    db_session, seed_country, tmp_path, monkeypatch
):
    populate_counties(db_session, seed_country.id)
    records, cohort = source_input(tmp_path, monkeypatch)
    write(db_session, records, cohort)
    bad = deepcopy(cohort)
    bad["artifact_sha256"] = "b" * 64
    with pytest.raises(ValueError):
        write(db_session, records, bad)
    doc = db_session.query(SourceDocument).one()
    doc.url = "https://cob.go.ke/different-edition.pdf"
    db_session.flush()
    assert (
        aging_observations(db_session, as_at=aging.AS_AT)["county_executive"]["status"]
        == "unavailable"
    )


def test_printed_zero_preserved_and_grouping_refused():
    tables = synthetic_tables()
    tables[0][1][2][1] = "0.00"
    result = aging.parse_aging_tables(tables, payables_entries())
    assert result["rows"][0]["amounts"][0] == "0.00"
    assert any(
        n["code"] == "bands_differ_from_printed_total"
        for n in result["rows"][0]["reader_notes"]
    )
    tables[0][1][2][1] = "1,23.00"
    with pytest.raises(ValueError, match="grouping"):
        aging.parse_aging_tables(tables, payables_entries())


def test_genuine_current_edition_continuation_qualifications_and_units():
    import json
    from pathlib import Path
    from seeding.pdf_parsers import county_payables_rows, classify_payables_row

    # Genuine extracted cells, source/hash/locator attributed in the fixture.
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/cbirr_2025_26_executive_aging.json"
        ).read_text()
    )
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "retained_payables",
        Path(__file__).parent / "fixtures/cbirr_county_payables_tables.py",
    )
    retained = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(retained)
    rows, _ = county_payables_rows(retained.FY2526_TABLE_PAGES)
    entries = []
    for county, row in rows.items():
        entry = classify_payables_row(row)
        entry.update(as_at="2026-06-30", table="Table 2.10")
        entries.append(entry)
    result = aging.parse_aging_tables(fixture["tables"], entries)
    assert result["artifact_sha256"] == fixture["source"]["sha256"]
    assert result["summary"]["amounts"] == [
        "44208110000.00",
        "28834120000.00",
        "22241100000.00",
        "70235180000.00",
        "165518510000.00",
    ]
    nandi = next(r for r in result["rows"] if r["county"] == "Nandi")
    assert nandi["raw_cells"] == ["0", "0", "0", "0", "0.00"]
    assert nandi["amounts"] == [None] * 5
    assert any(
        n["code"] == "publisher_says_aging_not_provided" for n in nandi["reader_notes"]
    )
    lamu = next(r for r in result["rows"] if r["county"] == "Lamu")
    assert (
        lamu["amounts"][1] == "0.00"
    )  # A real printed zero without the Nandi refusal.
    assert (
        next(r for r in result["rows"] if r["county"] == "Baringo")["amounts"][2]
        is None
    )
    assert any(
        n["code"] == "known_payables_executive_sum_differs"
        for n in result["summary"]["reader_notes"]
    )
    assert result["reconciliation"][0]["reported_count"] == 46


def test_unreviewed_same_url_artifact_refused_before_pdf_parse(tmp_path):
    path = tmp_path / "reissue.pdf"
    path.write_bytes(b"%PDF-different-reissue")
    with pytest.raises(ValueError, match="Unreviewed aging artifact"):
        aging.ExecutiveAgingParser(path, payables_entries()).parse()


@pytest.mark.parametrize("change", ["late_cell", "nandi_qualification"])
def test_corrupt_replay_never_borrows_prior_verified_extraction(
    db_session, seed_country, tmp_path, monkeypatch, change
):
    populate_counties(db_session, seed_country.id)
    records, cohort = source_input(tmp_path, monkeypatch)
    write(db_session, records, cohort)
    before = [(r.id, deepcopy(r.provenance)) for r in db_session.query(Loan).all()]
    bad = deepcopy(cohort)
    if change == "late_cell":
        bad["rows"][-1]["source_evidence"][0]["value"] = "123"
    else:
        next(r for r in bad["rows"] if r["county"] == "Nandi")["reader_notes"] = []
    with pytest.raises(ValueError, match="intact"):
        write(db_session, records, bad)
    assert before == [(r.id, r.provenance) for r in db_session.query(Loan).all()]
    assert aging_observations(db_session, as_at=aging.AS_AT)["county_executive"][
        "coverage"
    ]["missing_counties"] == ["Nandi"]


def test_empty_stock_cannot_silently_accept_an_aging_attempt(
    db_session, tmp_path, monkeypatch
):
    assert write_pending_bills(db_session, []) == (0, 0)
    with pytest.raises(ValueError, match="intact"):
        write(db_session, [], {"malformed": True})
    _, cohort = source_input(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="associated county stock"):
        write(db_session, [], cohort)


def test_public_read_uses_bounded_database_queries_and_no_object_reads(
    db_session, seed_country, tmp_path, monkeypatch
):
    from sqlalchemy import event

    populate_counties(db_session, seed_country.id)
    records, cohort = source_input(tmp_path, monkeypatch)
    write(db_session, records, cohort)
    monkeypatch.setattr(
        LocalReceiptStore,
        "read",
        lambda *a: (_ for _ in ()).throw(
            AssertionError("public read touched source bytes")
        ),
    )
    queries = []

    def record_query(conn, cursor, statement, parameters, context, many):
        queries.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", record_query)
    try:
        result = aging_observations(db_session, as_at=aging.AS_AT)["county_executive"]
    finally:
        event.remove(db_session.bind, "before_cursor_execute", record_query)
    assert result["reported_total"] == 460000000
    assert len(queries) <= 3


@pytest.mark.parametrize("amount", [True, False, -1, "NaN", "Infinity", "-Infinity"])
def test_payables_comparison_operands_are_validated(amount):
    entries = payables_entries()
    entries[0]["executive_millions"] = amount
    with pytest.raises(ValueError):
        aging.parse_aging_tables(synthetic_tables(), entries)


def test_missing_publication_batch_cannot_match_missing_metadata(
    db_session, seed_country, tmp_path, monkeypatch
):
    populate_counties(db_session, seed_country.id)
    records, cohort = source_input(tmp_path, monkeypatch)
    write(db_session, records, cohort)
    doc = db_session.query(SourceDocument).one()
    metadata = deepcopy(doc.meta)
    metadata.pop("pending_bills_publication_batch")
    metadata["pending_bills_aging_v1"].pop("publication_batch")
    doc.meta = metadata
    db_session.flush()
    assert (
        aging_observations(db_session, as_at=aging.AS_AT)["county_executive"]["status"]
        == "unavailable"
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_fetcher_default_and_opt_in_share_download_but_attest_fresh_payables(
    tmp_path, monkeypatch, enabled
):
    from types import SimpleNamespace
    from seeding import cob_cbirr, pdf_evidence, pdf_parsers, parse_cache
    from seeding.config import SeedingSettings
    from seeding.domains.pending_bills import fetcher

    body = b"%PDF-INERT-FETCHER-CONTROL"
    monkeypatch.setattr(aging, "ARTIFACT_SHA256", sha256(body).hexdigest())
    path = tmp_path / "same.pdf"
    path.write_bytes(body)
    entries = payables_entries()
    for entry in entries:
        entry["status"] = "not_reported" if entry["county"] == "Nandi" else "reported"

    class StockParser:
        def __init__(self, path):
            pass

        def parse(self):
            return entries

    class AgeParser:
        def __init__(self, path, entries):
            self.entries = entries

        def parse(self):
            return [aging.parse_aging_tables(synthetic_tables(), self.entries)]

    url = "https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482"
    receipt = capture_response(
        httpx.Response(
            200,
            content=body,
            headers={"content-type": "application/pdf"},
            request=httpx.Request("GET", url),
        ),
        LocalReceiptStore(tmp_path / "fetcher-receipts"),
        source_kind="pdf",
    )
    downloads = []

    def download(*args):
        downloads.append(args[1])
        return SimpleNamespace(path=path)

    calls = []
    actual_parse = parse_cache.parse_with_cache

    def parse(*args, **kwargs):
        calls.append((kwargs["kind"], kwargs["enabled"]))
        return actual_parse(*args, **kwargs)

    monkeypatch.setattr(cob_cbirr, "download_cbirr", download)
    monkeypatch.setattr(pdf_parsers, "CbirrYearEndPayablesParser", StockParser)
    monkeypatch.setattr(aging, "ExecutiveAgingParser", AgeParser)
    monkeypatch.setattr(
        pdf_evidence,
        "receipt_for_pdf",
        lambda *a: copy_receipt(receipt, parser_version="inert-fetcher-v1"),
    )
    monkeypatch.setattr(parse_cache, "parse_with_cache", parse)
    monkeypatch.setattr(fetcher, "year_end_cbirr_links", lambda _: [url])
    monkeypatch.setattr(
        fetcher, "county_payables_payload", lambda *a, **kw: {"existing_contract": True}
    )
    if enabled:
        monkeypatch.setenv("SEED_PENDING_BILLS_AGING_ENABLED", "true")
    else:
        monkeypatch.delenv("SEED_PENDING_BILLS_AGING_ENABLED", raising=False)
    client = SimpleNamespace(get=lambda *a, **kw: SimpleNamespace(text="inert listing"))
    settings = SeedingSettings(
        _env_file=None,
        cache_path=tmp_path,
        live_pdf_fetch_enabled=True,
        parse_cache_enabled=True,
    )
    from seeding.domains.counties_budget import fetcher as budget_fetcher

    monkeypatch.setattr(budget_fetcher, "_pdf_stack_versions", lambda: "inert-stack")
    if enabled:
        # Cached positive comparison cells are not fresh source attestations.
        # Seed a stale parse, then let the current parser expose the real control.
        entries[0]["executive_millions"] = "999"
        actual_parse(
            path,
            cache_dir=tmp_path / "pdfs",
            kind="cob_cbirr_year_end_payables",
            parse_fn=StockParser(path).parse,
            enabled=True,
            key_extra="inert-stack",
        )
        entries[0]["executive_millions"] = "10.00"
    result = fetcher.fetch_county_payables_payload(client, settings)
    if enabled:
        assert not any(
            n["code"] == "payables_executive_total_differs"
            for n in result["aging"]["rows"][0]["reader_notes"]
        )
    assert downloads == [url]
    assert result["existing_contract"] is True
    assert calls[0] == ("cob_cbirr_year_end_payables", not enabled)
    if enabled:
        assert calls[1] == ("cob_executive_aging_v1", False)
        aging.require_intact_aging(result["aging"])
    else:
        assert "aging" not in result and len(calls) == 1
