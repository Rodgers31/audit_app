"""Executed controls for review 495: lexical scope and full-response authority.

All transport is MockTransport and all bytes/DB rows belong to these tests.
The tiny PDF-shaped source exercises ingestion capabilities, not PDF rendering.
"""
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from models import DebtTimeline, Extraction, SourceDocument
from seeding.config import SeedingSettings
from seeding.http_client import PdfDownloadIncomplete, SeedingHttpClient
from seeding.pdf_download import _looks_like_whole_pdf
from services.figure_qualification import (
    ObservationIdentity,
    evaluate_qualification,
    qualify_rows,
)

URL = "https://treasury.go.ke/review-495-owned-source.pdf"
BODY = b"%PDF-1.7\n7\n" + b"x" * 400 + b"\n%%EOF\n"
HEAD = BODY[:200]


def settings(tmp_path):
    return SeedingSettings(
        _env_file=None, storage_path=tmp_path, cache_path=tmp_path,
        http_cache_enabled=False,
    )


class InterruptedBody(httpx.SyncByteStream):
    def __init__(self, body):
        self.body = body

    def __iter__(self):
        if self.body:
            yield self.body
        raise httpx.ReadTimeout("owned interrupted response")


def stream_response(status, body, *, interrupted=False, offset=None):
    headers = {"content-type": "application/pdf"}
    if offset is not None:
        headers["content-range"] = f"bytes {offset}-{len(BODY)-1}/{len(BODY)}"
    stream = InterruptedBody(body) if interrupted else httpx.ByteStream(body)
    return httpx.Response(status, headers=headers, stream=stream)


def download(client, dest, part):
    return client.download_to_file(
        URL, dest, max_seconds=5, resume_part=part,
        completion_check=_looks_like_whole_pdf,
    )


def actual_pdf_qualification(db, doc, client, config, dest):
    """Fresh source parse -> capability -> writer -> persisted reader result."""
    from seeding.parse_cache import parse_with_cache
    from seeding.pdf_evidence import (
        bind_parse_receipt, bind_pdf_evidence, cell_evidence,
        receipt_for_pdf, seal_pdf_observations,
    )

    doc.url = URL
    db.flush()
    records = parse_with_cache(
        dest, cache_dir=dest.parent / "parsed", kind="review-495-source",
        parse_fn=lambda: [{"amount": int(dest.read_bytes().splitlines()[1])}],
    )
    receipt = receipt_for_pdf(client, config, dest, URL, "review-495-source-v1")
    identity = {
        "measure": "allocated_amount", "entity_id": None, "geography": "KEN",
        "period": "2024", "unit": "KES", "basis": "actual", "dimensions": {},
    }
    item = cell_evidence(
        receipt=bind_parse_receipt(receipt, records), identity=identity,
        raw_value=records[0]["amount"], value=records[0]["amount"],
        raw_unit="KES", factor="1", locator={"page": 1, "cell": "owned amount"},
    )
    seal_pdf_observations([item])
    bound = bind_pdf_evidence(
        db, doc, [item], identity=identity, values={"allocated_amount": 7},
    )[0]
    extraction_id = bound["receipt"]["extraction_id"]
    ext = db.get(Extraction, extraction_id) if extraction_id else None
    result = evaluate_qualification(
        ObservationIdentity(**identity), 7, source=doc, evidence=bound,
        receipt=ext.extracted_json["response_receipt"] if ext else None,
    )
    return result, receipt


@pytest.mark.parametrize("mode", ["whole_200", "interrupted_then_206", "broken_at_eof", "restart_200"])
def test_stream_completion_and_actual_qualification(
    db_session, seed_source_doc, tmp_path, mode,
):
    calls = []

    def handler(request):
        calls.append(request.headers.get("range"))
        if mode == "whole_200":
            return stream_response(200, BODY)
        if mode == "broken_at_eof":
            return stream_response(200, BODY, interrupted=True)
        if len(calls) == 1:
            return stream_response(200, HEAD, interrupted=True)
        assert calls[-1] == f"bytes={len(HEAD)}-"
        if mode == "restart_200":
            # A complete replacement 200 is genuinely one entire response.
            return stream_response(200, BODY)
        return stream_response(206, BODY[len(HEAD):], offset=len(HEAD))

    config = settings(tmp_path)
    dest, part = tmp_path / "source.pdf", tmp_path / "source.part"
    with SeedingHttpClient(config, client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        assert download(client, dest, part) == len(BODY)
        assert dest.read_bytes() == BODY
        receipt = client.download_receipt(URL)
        complete_response = mode in {"whole_200", "restart_200"}
        assert (receipt is not None) == complete_response
        q, parsed_receipt = actual_pdf_qualification(
            db_session, seed_source_doc, client, config, dest,
        )
        if complete_response:
            assert receipt["status"] == 200
            assert receipt["digest"] == hashlib.sha256(BODY).hexdigest()
            assert client.receipt_store.read(receipt["storage_key"]) == BODY
            assert q.status == "verified"
            assert q.document_bytes_checked and q.value_checked
        else:
            assert q.status == "qualified" and q.reason == "unsuccessful_response"
            assert not q.document_bytes_checked and not q.value_checked
            assert parsed_receipt["status"] is None
            assert parsed_receipt["byte_check"]["status"] == "matched"
        assert calls == ([None] if mode in {"whole_200", "broken_at_eof"} else [None, "bytes=200-"])


def test_across_calls_resume_clears_previous_full_receipt(
    db_session, seed_source_doc, tmp_path,
):
    stage = "positive"
    calls = []

    def handler(request):
        calls.append((stage, request.headers.get("range")))
        if stage == "positive":
            return stream_response(200, BODY)
        if stage == "stalled":
            if request.headers.get("range") is None:
                return stream_response(200, HEAD, interrupted=True)
            return stream_response(206, b"", interrupted=True, offset=len(HEAD))
        assert request.headers.get("range") == "bytes=200-"
        return stream_response(206, BODY[len(HEAD):], offset=len(HEAD))

    config = settings(tmp_path)
    dest, part = tmp_path / "source.pdf", tmp_path / "source.part"
    with SeedingHttpClient(config, client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        download(client, dest, part)
        assert client.download_receipt(URL)["status"] == 200
        dest.unlink()
        stage = "stalled"
        with pytest.raises(PdfDownloadIncomplete, match="stalled"):
            download(client, dest, part)
        assert part.read_bytes() == HEAD
        assert client.download_receipt(URL) is None
        stage = "resume"
        download(client, dest, part)
        assert dest.read_bytes() == BODY
        assert client.download_receipt(URL) is None
        q, receipt = actual_pdf_qualification(db_session, seed_source_doc, client, config, dest)
        assert q.status == "qualified" and q.reason == "unsuccessful_response"
        assert not q.document_bytes_checked and not q.value_checked
        assert receipt["status"] is None
        assert calls == [
            ("positive", None), ("stalled", None), ("stalled", "bytes=200-"),
            ("stalled", "bytes=200-"), ("resume", "bytes=200-"),
        ]


def test_preexisting_whole_partial_does_not_reuse_old_acquisition(
    db_session, seed_source_doc, tmp_path,
):
    calls = []

    def handler(request):
        calls.append(request)
        return stream_response(200, BODY)

    config = settings(tmp_path)
    dest, part = tmp_path / "source.pdf", tmp_path / "source.part"
    with SeedingHttpClient(config, client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        download(client, dest, part)
        assert client.download_receipt(URL) is not None
        dest.rename(part)
        download(client, dest, part)
        assert len(calls) == 1
        assert client.download_receipt(URL) is None
        q, receipt = actual_pdf_qualification(db_session, seed_source_doc, client, config, dest)
        assert q.status == "qualified" and q.reason == "unsuccessful_response"
        assert not q.document_bytes_checked and not q.value_checked
        assert receipt["status"] is None


def test_debt_gdp_create_and_update_keep_independent_verified_operand(
    db_session, seed_country, tmp_path,
):
    from seeding.domains.debt_timeline.fetcher import _enrich_with_wb_gdp
    from seeding.domains.debt_timeline.parser import parse_debt_timeline_payload
    from seeding.domains.debt_timeline.writer import write_debt_timeline_records

    original = json.loads((Path(__file__).parent / "fixtures/worldbank_gdp_2022.json").read_bytes())
    original[1].append({**original[1][0], "date": "2021", "value": 12000000000000})
    original[0]["total"] = 2
    retained = []
    ids = None
    for update in (False, True):
        original[1][0]["value"] = 13489642000001 if update else 13489642000000
        body = json.dumps(original).encode()
        retained.append(body)
        config = settings(tmp_path)
        with SeedingHttpClient(config, client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=body, headers={"content-type": "application/json"}),
        ))) as client:
            payload = _enrich_with_wb_gdp({"timeline": [
                {"year": year, "external": 5, "domestic": 5, "total": 10, "source": f"Owned debt source {year}"}
                for year in (2021, 2022)
            ]}, client)
        assert write_debt_timeline_records(db_session, parse_debt_timeline_payload(payload), {}) == ((0, 2) if update else (2, 0))
        db_session.commit()
        db_session.expire_all()
        rows = db_session.query(DebtTimeline).order_by(DebtTimeline.year).all()
        assert len(rows) == 2
        current_ids = [r.id for r in rows]
        assert ids is None or current_ids == ids
        ids = current_ids
        assert rows[0].gdp == Decimal("12000000000000")
        assert rows[1].gdp == Decimal(str(original[1][0]["value"]))
        qualifications = qualify_rows(db_session, "debt_timeline", rows)
        operand_docs, receipt_ids = set(), set()
        for row in rows:
            evidence, = row.meta["source_evidence"]
            operand_docs.add(evidence["receipt"]["source_document_id"])
            receipt_ids.add(evidence["receipt"]["extraction_id"])
            assert evidence["identity"]["measure"] == "gdp"
            assert evidence["receipt"]["source_document_id"] != row.source_document_id
            assert qualifications[row.id]["gdp"]["status"] == "verified"
            assert qualifications[row.id]["total"]["status"] == "qualified"
            assert qualifications[row.id]["gdp_ratio"]["status"] == "qualified"
        assert len(operand_docs) == len(receipt_ids) == 1
        assert db_session.get(SourceDocument, next(iter(operand_docs))).publisher == "World Bank"
        ext = db_session.get(Extraction, next(iter(receipt_ids)))
        assert ext.extracted_json["response_receipt"]["digest"] == hashlib.sha256(body).hexdigest()
    # An update changes the new immutable receipt, never the previous bytes.
    extractions = db_session.query(Extraction).all()
    assert len(extractions) == 2
    assert {e.extracted_json["response_receipt"]["digest"] for e in extractions} == {
        hashlib.sha256(body).hexdigest() for body in retained
    }
