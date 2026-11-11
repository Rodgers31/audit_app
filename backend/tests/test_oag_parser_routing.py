"""Exercise the OAG worker protocol without Docker or network acquisition."""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from models import DocumentStatus, IngestionStatus
from seeding import isolated_parser, oag_report_catalogue
from seeding.config import SeedingSettings
from seeding.domains.audits import fetcher
from seeding.extractors import oag_blue_book, oag_county_audit, oag_county_volume
from seeding.native_report_authority import DOMAINS, capture_pdf_report
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_response, capture_retained_pdf
from tests.test_oag_decorative_pages import write_pdf


@pytest.fixture
def parser_requests(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("SEED_PARSER_ROOT", str(tmp_path))
    backend = Path(__file__).resolve().parents[1]

    def local_worker(root, request, timeout):
        calls.append(json.loads((request / "request.json").read_bytes()))
        return subprocess.run(
            [sys.executable, "-I", "-B", "-c",
             "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
             "from seeding.isolated_parser import worker_main; "
             "sys.stdout.buffer.write(worker_main(Path(sys.argv[2])))",
             str(backend), str(request)],
            env={"PATH": "/usr/bin:/bin", "TMPDIR": str(root), "LC_ALL": "C"},
            check=True, capture_output=True, timeout=min(timeout, 15),
        ).stdout

    monkeypatch.setattr(isolated_parser, "_worker", local_worker)
    return calls


def test_report_capture_routes_fresh_and_retained_bodies(tmp_path, parser_requests):
    url = "https://www.oagkenya.go.ke/owned-fixture.pdf"
    feed = oag_report_catalogue.catalogue_url("FY 2023/24")
    path = tmp_path / "fixture.pdf"
    title = "AUDITOR-GENERAL'S REPORT ON COUNTY GOVERNMENTS"
    write_pdf(path, f"BT /F1 12 Tf 20 700 Td ({title} FOR THE YEAR 2023/2024 VOLUME 1 COUNTY EXECUTIVES) Tj ET".encode())
    pdf = path.read_bytes()
    rss = f'''<?xml version="1.0"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>
<title>2023-2024 County Government Audit Reports - Office of the Auditor-General</title>
<atom:link href="{feed}" rel="self" type="application/rss+xml"/>
<item><title>{title} - COUNTY EXECUTIVES 2023/2024</title><link>{url}</link>
<pubDate>Fri, 21 Feb 2025 05:51:28 +0000</pubDate>
<guid isPermaLink="false">https://www.oagkenya.go.ke/?post_type=dlp_document&amp;p=1</guid>
</item></channel></rss>'''.encode("utf-16")
    store = LocalReceiptStore(tmp_path / "receipts")

    def acquire(body, address, kind, mime):
        response = httpx.Response(200, content=body, headers={"content-type": mime},
                                  request=httpx.Request("GET", address))
        return capture_response(response, store, source_kind=kind)

    original = acquire(pdf, url, "pdf", "application/pdf")
    publisher = acquire(rss, feed, "rss", "application/rss+xml")
    fresh, reason = capture_pdf_report(path, original, domain="audits", publisher_receipt=publisher)
    assert reason is None and fresh.value["catalogued_on"] == "2025-02-21"

    # Supply owned job/source rows at the DB query boundary. Receipt restore,
    # byte readback, report parsing and publication validation all run normally.
    session = Mock(info={})
    session.get_bind.return_value.dialect.name = "postgresql"
    session.scalar.return_value = "read committed"
    job = dict(id=7, domain="audits", status=IngestionStatus.RUNNING, dry_run=False,
               started_at=datetime.now(timezone.utc))
    source = dict(id=9, publisher=DOMAINS["audits"][2], status=DocumentStatus.AVAILABLE,
                  md5=None, artifact=None)
    session.execute.side_effect = [
        SimpleNamespace(mappings=lambda: SimpleNamespace(one_or_none=lambda: job)),
        SimpleNamespace(mappings=lambda: [source]),
        SimpleNamespace(one_or_none=lambda: (11, dict(original))),
    ]
    restored = capture_retained_pdf(session, SimpleNamespace(job_id=7, dry_run=False), store,
                                    domain="audits", url=url, body=pdf)
    current_publisher = acquire(rss, feed, "rss", "application/rss+xml")
    replay, reason = capture_pdf_report(path, restored, domain="audits", publisher_receipt=current_publisher)
    assert reason is None and replay.value["document_checksum"] == fresh.value["document_checksum"]
    assert replay.receipt["acquired_at"] == original["acquired_at"]
    assert replay.receipt["retained_pdf_validation"]["ingestion_id"] == 7
    assert [(call["operation"], call["sha256"]) for call in parser_requests] == [
        ("seeding.native_report_cover:extract_cover_texts", original["digest"]),
        ("seeding.oag_report_catalogue:_catalogue_entry", publisher["digest"]),
    ] * 2
    hostile_rss = rss.decode("utf-16").replace("<rss ", "<!DOCTYPE rss>\n<rss ").encode("utf-16")
    hostile = acquire(hostile_rss, feed, "rss", "application/rss+xml")
    assert capture_pdf_report(path, restored, domain="audits", publisher_receipt=hostile) == (
        None, "native_report_date_or_scope_unavailable",
    )
    assert parser_requests[-1]["sha256"] == hostile["digest"]


def test_oag_page_readers_return_existing_types_and_quarantine_reason(tmp_path, parser_requests, monkeypatch):
    path = tmp_path / "report.pdf"
    write_pdf(path, b"BT /F1 12 Tf 20 700 Td (Audit report) Tj ET")
    page = oag_blue_book.PageText(1, "Audit report", "pdfplumber")
    assert oag_blue_book.read_pages(path, ocr_enabled=False) == [page]
    assert oag_county_volume.read_head(str(path)) == [page]
    assert oag_county_audit.read_pages(str(path)) == [(1, "Audit report")]
    client = Mock()
    client.get.return_value.content = path.read_bytes()
    extract = Mock(return_value=[{"finding": "owned fixture"}])
    monkeypatch.setattr(fetcher, "_extract_findings_from_text", extract)
    url = "https://www.oagkenya.go.ke/owned-fixture.pdf"
    settings = SeedingSettings(audits_ocr_enabled=False)
    assert fetcher._download_and_parse_audit_pdf(client, url, settings) == extract.return_value
    extract.assert_called_once_with("Audit report\n", url)

    path.write_bytes(b"<html>not a PDF</html>")
    with pytest.raises(oag_county_audit.CountyAuditError) as error:
        oag_county_audit.read_pages(str(path))
    assert error.value.reason == "pdf_unreadable"
    assert error.value.detail
    assert [call["operation"] for call in parser_requests] == [
        "seeding.extractors.oag_blue_book:read_pages",
        "seeding.extractors.oag_county_volume:read_head",
        "seeding.extractors.oag_county_audit:read_pages",
        "seeding.domains.audits.fetcher:_read_audit_pdf_text",
        "seeding.extractors.oag_county_audit:read_pages",
    ]
