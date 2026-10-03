"""Owned transport controls and retained publisher bytes through actual writers.

Real document tests opt into SAFE retained paths; no network or production DB.
HTTP controls are simulated acquisition tests, not publisher observations.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import gzip
import json
import os
from pathlib import Path

import httpx
import pytest

from models import BudgetLine, Entity, EntityType, Extraction, Loan, SourceDocument
from seeding.config import SeedingSettings
from seeding.http_client import SeedingHttpClient
from seeding.pdf_download import cached_pdf_meta, get_or_download_pdf
from seeding.pdf_evidence import (
    bind_pdf_evidence,
    cell_evidence,
    receipt_for_pdf,
    seal_pdf_observations,
)
from seeding.types import DomainRunContext


@pytest.fixture
def settings(tmp_path):
    value = SeedingSettings(
        storage_path=tmp_path / "store",
        cache_path=tmp_path / "cache",
        log_path=tmp_path / "logs/seed.log",
        http_cache_enabled=False,
        rate_limit="10000/sec",
    )
    value.ensure_directories()
    return value


def transport_client(settings, handler):
    return SeedingHttpClient(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_completed_stream_retains_actual_bytes_and_changed_same_url(settings):
    url = "https://publisher.invalid/actual-body.pdf"
    bodies = [b"%PDF-1.7\noriginal\n%%EOF", b"%PDF-1.7\nchanged\n%%EOF"]

    def handler(request):
        return httpx.Response(
            200,
            content=bodies.pop(0),
            headers={"content-type": "application/pdf"},
            request=request,
        )

    with transport_client(settings, handler) as client:
        path = get_or_download_pdf(
            client,
            url,
            cache_dir=settings.cache_path / "pdfs",
            ttl_seconds=0,
            max_seconds=5,
        )
        original = cached_pdf_meta(path.parent, url)["response_receipt"]
        assert original["status"] == 200
        assert original["digest"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert original["byte_check"]["status"] == "matched"
        path = get_or_download_pdf(
            client, url, cache_dir=path.parent, ttl_seconds=0, max_seconds=5
        )
        changed = cached_pdf_meta(path.parent, url)["response_receipt"]
        assert changed["digest"] != original["digest"]
        from services.receipt_store import LocalReceiptStore

        store = LocalReceiptStore(settings.storage_path / "response-receipts")
        assert store.read(original["digest"]) == b"%PDF-1.7\noriginal\n%%EOF"
        assert store.read(changed["digest"]) == path.read_bytes()


def test_partial_response_does_not_claim_whole_body_transport(settings, tmp_path):
    url = "https://publisher.invalid/ranged.pdf"

    def handler(request):
        return httpx.Response(
            206,
            content=b"%PDF-1.7\nrange\n%%EOF",
            headers={"content-type": "application/pdf"},
            request=request,
        )

    with transport_client(settings, handler) as client:
        client.download_to_file(url, tmp_path / "body.pdf", max_seconds=5)
        assert client.download_receipt(url) is None


def test_compressed_stream_receipt_hashes_consumed_decoded_bytes(settings, tmp_path):
    body = b"%PDF-1.7\ncompressed source\n%%EOF"
    with transport_client(
        settings,
        lambda request: httpx.Response(
            200,
            content=gzip.compress(body),
            headers={"content-type": "application/pdf", "content-encoding": "gzip"},
            request=request,
        ),
    ) as client:
        path = tmp_path / "decoded.pdf"
        client.download_to_file(
            "https://publisher.invalid/compressed.pdf", path, max_seconds=5
        )
        receipt = client.download_receipt("https://publisher.invalid/compressed.pdf")
        assert receipt["digest"] == hashlib.sha256(body).hexdigest()
        assert (
            receipt["content_encoding"] == "gzip"
            and receipt["digest_scope"] == "decoded_stream_body"
        )
        assert path.read_bytes() == body


def local_receipt(settings, tmp_path):
    path = tmp_path / "retained.pdf"
    path.write_bytes(b"%PDF-1.7\nlocal source\n%%EOF")
    return receipt_for_pdf(object(), settings, path, path.as_uri(), "owned-control-v1")


def test_local_bytes_have_no_invented_transport(settings, tmp_path):
    receipt = local_receipt(settings, tmp_path)
    assert receipt["status"] is None and receipt["content_type"] is None
    assert receipt["acquisition_kind"] == "local_cached_bytes"
    assert receipt["byte_check"]["status"] == "matched"


def test_changed_cached_bytes_conflict_with_retained_transport(settings):
    url = "https://publisher.invalid/reissued.pdf"
    with transport_client(
        settings,
        lambda request: httpx.Response(
            200,
            content=b"%PDF-1.7\nold\n%%EOF",
            headers={"content-type": "application/pdf"},
            request=request,
        ),
    ) as client:
        path = get_or_download_pdf(
            client,
            url,
            cache_dir=settings.cache_path / "pdfs",
            ttl_seconds=0,
            max_seconds=5,
        )
        path.write_bytes(b"%PDF-1.7\nnew\n%%EOF")
        receipt = receipt_for_pdf(client, settings, path, url, "owned-control-v1")
    assert receipt["byte_check"]["status"] == "conflict"
    assert receipt["digest"] != receipt["byte_check"]["sha256"]


def draft(receipt):
    return cell_evidence(
        receipt=receipt,
        identity={
            "measure": "allocated_amount",
            "entity_id": None,
            "geography": "KEN",
            "period": "2025/26",
            "unit": "KES",
            "basis": "actual",
            "dimensions": {
                "category": "Health",
                "subcategory": None,
                "line_type": None,
            },
        },
        raw_value="12.5",
        value="12500000",
        raw_unit="KES million",
        factor="1000000",
        locator={"page": 4, "table": "Owned control", "cell": "Health / Allocation"},
    )


def test_json_dataset_cannot_self_attest_a_pdf_receipt(
    settings, tmp_path, db_session, seed_source_doc
):
    observation = draft(local_receipt(settings, tmp_path))
    seal_pdf_observations([observation])
    with pytest.raises(ValueError, match="actual parser ingestion envelope"):
        bind_pdf_evidence(
            db_session, seed_source_doc, [dict(observation)], identity={}, values={}
        )
    assert db_session.query(Extraction).count() == 0


def test_cached_response_preserves_unknown_acquisition(settings):
    from seeding.pdf_evidence import receipt_for_response

    response = httpx.Response(
        200,
        content=b"%PDF-1.7\ncache\n%%EOF",
        headers={"content-type": "application/pdf"},
        request=httpx.Request("GET", "https://publisher.invalid/cached.pdf"),
    )
    response.extensions["seeding_cache"] = True
    with transport_client(
        settings, lambda request: pytest.fail("No request expected")
    ) as client:
        receipt = receipt_for_response(client, response, "owned-control-v1")
        assert (
            receipt["status"] is None
            and receipt["acquisition_kind"]
            == "cached_response_without_acquisition_receipt"
        )
        receipt["acquired_at"] = "2026-09-01T00:00:00Z"
        response.extensions["response_receipt"] = receipt
        assert (
            receipt_for_response(client, response, "owned-control-v2")["acquired_at"]
            == "2026-09-01T00:00:00Z"
        )


def test_annual_real_text_fixture_locates_complete_total_cells():
    from seeding.domains.national_budget.sector_expenditure import (
        parse_sector_expenditure,
        _parse_summary_block,
    )

    data = json.loads(
        (
            Path(__file__).parent / "fixtures/cob/ngbirr_fy2025_26_annual_pages.json"
        ).read_text()
    )
    pages = {int(page): text for page, text in data["pages"].items()}
    accepted = parse_sector_expenditure(pages).accepted
    assert len(accepted) == 10
    # Physical pages containing the printed complete Total rows. Three
    # summaries begin on the preceding page; pin the cell pages explicitly.
    expected = {
        "ARUD": 94,
        "Education": 112,
        "EIICT": 131,
        "EPWNR": 160,
        "GECA": 181,
        "GJLO": 210,
        "Health": 243,
        "National Security": 255,
        "PAIR": 262,
        "SPCR": 324,
    }
    for sector in accepted:
        assert sector.total_locator is not None
        assert sector.total_locator["page"] == expected[sector.code]
        assert any(
            _parse_summary_block(line).get("total") == sector.total
            for line in pages[sector.total_locator["page"]].splitlines()
            if line.startswith("Total")
        )


@pytest.mark.parametrize(
    "field", ["page", "raw_value", "raw_unit", "period", "unit", "value", "factor"]
)
def test_modified_cell_cannot_keep_matched_claim(
    settings, tmp_path, db_session, seed_source_doc, field
):
    observation = draft(local_receipt(settings, tmp_path))
    seal_pdf_observations([observation])
    evidence = deepcopy(observation)
    if field == "page":
        evidence["locator"]["page"] = 8
    elif field in ("period", "unit"):
        evidence["identity"][field] = "2024/25" if field == "period" else "USD"
    elif field == "factor":
        evidence["transformation"]["factor"] = "1000000000"
    else:
        evidence[field] = {
            "raw_value": "99",
            "raw_unit": "USD million",
            "value": "999",
        }[field]
    result = bind_pdf_evidence(
        db_session,
        seed_source_doc,
        [evidence],
        identity={
            "entity_id": 1,
            "geography": "KEN",
            "period": "2025/26",
            "unit": "KES",
            "basis": "actual",
            "dimensions": {
                "category": "Health",
                "subcategory": None,
                "line_type": None,
            },
        },
        values={"allocated_amount": Decimal("12500000")},
    )[0]
    assert result["reconciliation"]["status"] == "conflict"
    assert not all(result["checks"].values())
    persisted = db_session.get(Extraction, result["receipt"]["extraction_id"])
    assert persisted.extractor == "pdf-receipt-v1"
    assert (
        persisted.extracted_json["response_receipt"]["observations"][0]["raw_value"]
        == "12.5"
    )


def retained_path(variable, digest):
    path = os.environ.get(variable)
    if not path:
        pytest.skip(f"SAFE retained document path required: {variable}")
    path = Path(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    return path


def test_retained_brop_actual_parser_and_writer(settings, db_session, seed_country):
    from seeding.domains.pending_bills.fetcher import _fetch_from_treasury_brop
    from seeding.domains.pending_bills.parser import parse_pending_bills_payload
    from seeding.domains.pending_bills.writer import write_pending_bills

    path = retained_path(
        "PDF_EVIDENCE_REAL_BROP",
        "39c2e290ecdb6be0d8768344514711a5b0c6a350f0416ed81e529cded60def24",
    )
    db_session.add(
        Entity(
            country_id=seed_country.id,
            canonical_name="National Government",
            slug="national",
            type=EntityType.NATIONAL,
        )
    )
    with transport_client(
        settings, lambda request: pytest.fail("Local byte test cannot fetch")
    ) as client:
        payload = _fetch_from_treasury_brop(client, path.as_uri())
    records = parse_pending_bills_payload(payload)
    assert len(records) == 2
    created, updated = write_pending_bills(
        db_session,
        records,
        source_url=payload["source_url"],
        source_title=payload["source_title"],
        publication=payload["publication"],
        publisher=payload["publisher"],
    )
    assert (created, updated) == (2, 0)
    db_session.flush()
    loans = db_session.query(Loan).all()
    assert len(loans) == 2 and db_session.query(Extraction).count() == 1
    for loan in loans:
        observation = loan.provenance["source_evidence"][0]
        assert observation["identity"]["period"] == "2026-06-30"
        assert observation["identity"]["measure"] == "outstanding"
        assert observation["checks"] == {
            "identity": True,
            "value": True,
            "locator": True,
            "bytes": True,
            "transport": False,
        }
        assert Decimal(observation["value"]) == loan.outstanding
        receipt = db_session.get(
            Extraction, observation["receipt"]["extraction_id"]
        ).extracted_json["response_receipt"]
        assert len(receipt["observations"]) == 2
        assert receipt["status"] is None


def test_retained_cbirr_original_and_continuation_cell_pages(
    settings, db_session, seed_country, monkeypatch
):
    from seeding import pdf_parsers
    from seeding.domains.counties_budget.fetcher import convert_county_pdf_records
    from seeding.domains.counties_budget.parser import parse_budget_payload
    from seeding.domains.counties_budget.writer import persist_budget_records

    path = retained_path(
        "PDF_EVIDENCE_REAL_CBIRR",
        "5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3",
    )
    # Actual extraction from the two full consolidated budget pages, bounded
    # instead of walking the unrelated 933 pages. Real parser guards still run.
    tables = pdf_parsers.extract_all_tables(path, pages=[43, 44])
    monkeypatch.setattr(pdf_parsers, "extract_all_tables", lambda ignored: tables)
    parsed = pdf_parsers.CoBQuarterlyReportParser(path).parse()
    receipt = receipt_for_pdf(
        object(), settings, path, path.as_uri(), "cob-county-budget-v1"
    )
    payload = convert_county_pdf_records(
        parsed, path.as_uri(), receipt["digest"], receipt=receipt
    )
    records = parse_budget_payload(payload)
    for name in pdf_parsers.KENYAN_COUNTIES:
        from seeding.utils import slugify_entity

        db_session.add(
            Entity(
                country_id=seed_country.id,
                canonical_name=f"{name} County",
                slug=slugify_entity(name),
                type=EntityType.COUNTY,
            )
        )
    db_session.flush()
    result = persist_budget_records(
        db_session, records, settings, DomainRunContext(since=None, dry_run=False)
    )
    assert result.created >= 141 and not result.errors
    db_session.flush()
    evidence = [
        e
        for row in db_session.query(BudgetLine).all()
        for p in row.provenance
        for e in p.get("source_evidence", [])
    ]
    assert {e["locator"]["page"] for e in evidence} == {43, 44}
    bad = [
        {
            "identity": e["identity"],
            "checks": e["checks"],
            "reconciliation": e["reconciliation"],
            "raw_value": e["raw_value"],
            "value": e["value"],
        }
        for e in evidence
        if not (
            e["checks"]["locator"] and e["checks"]["value"] and e["checks"]["identity"]
        )
    ]
    assert not bad, bad[:3]
    assert all(e["checks"]["transport"] is False for e in evidence)
    assert db_session.query(Extraction).count() == 1


def test_nonfinite_cell_and_absence_do_not_claim_zero(settings, tmp_path):
    value = draft(local_receipt(settings, tmp_path))
    assert value["checks"]["value"]
    for raw in (None, "NaN", "Infinity"):
        observation = cell_evidence(
            receipt=value["_response_receipt"],
            identity=value["identity"],
            raw_value=raw,
            value="0",
            raw_unit="KES million",
            factor="1000000",
            locator=None,
        )
        assert (
            not observation["checks"]["value"] and not observation["checks"]["locator"]
        )


def test_cash_total_receipt_never_uses_accrual_or_summary():
    from seeding.pdf_parsers import CoBQuarterlyReportParser, ExtractedTable

    table = ExtractedTable(
        page_number=60,
        table_index=0,
        headers=[
            "Revenue Stream",
            "Annual Target Kshs.",
            "Actual Receipts Kshs.",
            "Total Revenues accrual Kshs.",
        ],
        rows=[["Grand Total", "100", "70", "95"]],
        bbox=(0, 0, 1, 1),
    )
    cells = CoBQuarterlyReportParser._cash_total_cells(
        [table], Decimal(100), Decimal(70)
    )
    assert cells["actual_spent"]["raw_value"] == "70"
    assert "column 3" in cells["actual_spent"]["locator"]["cell"]
    assert (
        CoBQuarterlyReportParser._cash_total_cells([table], Decimal(100), Decimal(95))
        == {}
    )
    table.headers[2] = "Summary collection Kshs."
    assert (
        CoBQuarterlyReportParser._cash_total_cells([table], Decimal(100), Decimal(70))
        == {}
    )


def test_retained_cbirr_payables_parser_and_writer(settings, db_session, seed_country):
    from seeding.pdf_parsers import CbirrYearEndPayablesParser, KENYAN_COUNTIES
    from seeding.domains.pending_bills.fetcher import (
        county_payables_payload,
        check_county_payables_entries,
    )
    from seeding.domains.pending_bills.parser import parse_pending_bills_payload
    from seeding.domains.pending_bills.writer import write_pending_bills
    from seeding.utils import slugify_entity

    path = retained_path(
        "PDF_EVIDENCE_REAL_CBIRR",
        "5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3",
    )
    entries = CbirrYearEndPayablesParser(path).parse()
    check_county_payables_entries(entries, path.as_uri())
    receipt = receipt_for_pdf(
        object(), settings, path, path.as_uri(), "cob-year-end-payables-v1"
    )
    payload = county_payables_payload(entries, path.as_uri(), receipt=receipt)
    for name in KENYAN_COUNTIES:
        db_session.add(
            Entity(
                country_id=seed_country.id,
                canonical_name=f"{name} County",
                slug=slugify_entity(name),
                type=EntityType.COUNTY,
            )
        )
    db_session.flush()
    records = parse_pending_bills_payload(payload)
    expected = sum(e["status"] == "reported" for e in entries)
    created, updated = write_pending_bills(
        db_session,
        records,
        source_url=payload["source_url"],
        source_title=payload["source_title"],
        publication=payload["publication"],
        publisher=payload["publisher"],
        county_table=payload["county_table"],
    )
    assert (created, updated) == (expected, 0)
    db_session.flush()
    assert db_session.query(Extraction).count() == 1
    for loan in db_session.query(Loan).all():
        observation = loan.provenance["source_evidence"][0]
        assert observation["identity"]["period"] == "2026-06-30"
        assert observation["checks"]["identity"] and observation["checks"]["value"]
        assert observation["locator"]["page"] in (51, 52)
        assert observation["checks"]["transport"] is False
    assert "Nandi" in payload["county_table"]["not_reported"]
