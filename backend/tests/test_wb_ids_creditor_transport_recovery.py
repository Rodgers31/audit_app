"""World Bank IDS recovery through the real seeding client and source parsers."""

from datetime import date
from decimal import Decimal
from hashlib import sha256
from xml.etree import ElementTree

import httpx
import pytest

from seeding import isolated_parser
from seeding.config import SeedingSettings
from seeding.domains.national_debt import wb_ids_creditors as ids
from seeding.http_client import SeedingHttpClient
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_response
from tests.test_wb_ids_creditors import IDS_2024, IDS_TEST_RATE, _record


MULTILATERAL = "DT.DOD.MLAT.CD"
XML_NS = "http://www.worldbank.org"
RELEASE = "2025-11-01"


def _xml_response(series, year, rows, *, source_id="6", **metadata):
    root = ElementTree.Element(
        "wb:data",
        {
            "xmlns:wb": XML_NS,
            "page": "1",
            "pages": "1",
            "per_page": "400",
            "total": str(len(rows)),
            "lastupdated": RELEASE,
            **metadata,
        },
    )
    source = ElementTree.SubElement(
        root, "wb:source", id=source_id, name="International Debt Statistics"
    )
    for name, area_id, value in rows:
        record = _record(name, area_id, series, value, year)
        data = ElementTree.SubElement(source, "wb:data")
        for var in record["variable"]:
            ElementTree.SubElement(
                data, "wb:variable", concept=var["concept"], id=var["id"]
            ).text = var["value"]
        ElementTree.SubElement(data, "wb:value").text = (
            str(value) if value is not None else None
        )
    return ElementTree.tostring(root)


def _json_response(series, year, rows):
    return httpx.Response(
        200,
        json={
            "page": 1,
            "pages": 1,
            "per_page": 400,
            "total": len(rows),
            "lastupdated": RELEASE,
            "source": {
                "id": "6",
                "name": "International Debt Statistics",
                "data": [
                    _record(name, area, value=value, series=series, year=year)
                    for name, area, value in rows
                ],
            },
        },
    )


def _client(tmp_path, handler):
    settings = SeedingSettings(_env_file=None, max_retries=3, retry_backoff=0)
    return SeedingHttpClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        receipt_store=LocalReceiptStore(tmp_path / "ids"),
    )


def test_exhausted_json_recovers_complete_register_with_same_year_and_actual_bytes(
    tmp_path,
    monkeypatch,
):
    class Today(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 11)

    monkeypatch.setattr(ids, "date", Today)
    monkeypatch.setenv("SEED_PARSER_ROOT", str(tmp_path))
    requests = []
    decoded_documents = []
    rows = [
        (name + "\xa0 ", area, value) for name, area, value in IDS_2024[MULTILATERAL]
    ]
    body = _xml_response(MULTILATERAL, 2024, rows)

    def worker(root, request, timeout):
        decoded_documents.append((request / "document").read_bytes())
        return isolated_parser.worker_main(request)

    monkeypatch.setattr(isolated_parser, "_worker", worker)

    def publisher(request):
        assert request.url.host == "api.worldbank.org"
        if "PA.NUS.FCRF" in request.url.path:
            assert request.url.params["date"] == "2024:2024"
            return httpx.Response(
                200, json=[{}, [{"date": "2024", "value": float(IDS_TEST_RATE)}]]
            )
        series = request.url.path.split("/series/")[1].split("/")[0]
        year = int(request.url.path.split("/time/YR")[1].split("/")[0])
        format_ = request.url.params["format"]
        requests.append((series, year, format_))
        if year > 2024:
            return _json_response(series, year, [("World", "WLD", None)])
        if series == MULTILATERAL:
            if format_ == "json":
                return httpx.Response(502)
            assert request.url.path.endswith("/data")
            return httpx.Response(
                200, content=body, headers={"content-type": "text/xml"}
            )
        if series in ids.INTEREST_SERIES.values():
            stock_series = next(
                stock
                for stock, interest in ids.INTEREST_SERIES.items()
                if series == interest
            )
            return _json_response(series, year, IDS_2024[stock_series])
        return _json_response(series, year, IDS_2024[series])

    with _client(tmp_path, publisher) as client:
        result = ids.fetch_external_creditors(
            client, published_external_kes_for_year=lambda year: {2024: 5.056e12}[year]
        )
        assert result["year"] == 2024
        assert result["checks"]["declaration_identity"] == "ok"
        assert result["checks"]["source_release"] == RELEASE
        assert result["coverage"]["status"] == "within_band"
        assert len(result["creditors"]) == len(result["loans"]) == 22
        assert (
            result["checks"]["interest"]["series"]["DT.INT.MLAT.CD"]["identity"] == "ok"
        )
        creditor = next(c for c in result["creditors"] if c.counterpart_id == "905")
        assert creditor.name == "World Bank-IDA"
        assert creditor.kes == Decimal("11872969000.0") * IDS_TEST_RATE
        evidence = creditor.source_evidence[0]
        receipt = evidence["_response_receipt"]
        assert (
            receipt["response_url"] == result["checks"]["recovery_urls"][MULTILATERAL]
        )
        assert receipt["byte_check"]["status"] == "matched"
        assert receipt["digest"] == sha256(body).hexdigest()
        assert client.receipt_store.read(receipt["storage_key"]) == body
        assert receipt["observations"] == []
        assert evidence["locator"]["xpath"] == "/wb:data/wb:source/wb:data[2]/wb:value"
        assert evidence["checks"]["value"] is False
        assert all(not loan["source_evidence"] for loan in result["loans"])
    assert [r[2] for r in requests if r[0] == MULTILATERAL] == [
        "json",
        "json",
        "json",
        "xml",
    ]
    assert decoded_documents == [body]


@pytest.mark.parametrize(
    "fault",
    [
        "wrong-source",
        "wrong-year",
        "wrong-country",
        "wrong-series",
        "partial",
        "truncated",
        "duplicate-area",
        "wrong-world",
        "missing-world",
        "no-data",
        "negative",
        "nan",
        "infinite",
        "unrepresentable",
        "doctype",
        "html",
        "redirect",
    ],
)
def test_unqualified_xml_never_advances_to_an_older_year(tmp_path, fault):
    series = ids.TOTAL_SERIES
    rows = [("World", "WLD", 100), ("France", "004", 100)]
    year = 2025
    metadata = {}
    source_id = "6"
    status = 200
    headers = {"content-type": "text/xml"}
    if fault == "wrong-source":
        source_id = "2"
    elif fault == "wrong-year":
        year = 2024
    elif fault == "partial":
        metadata["pages"] = "2"
    elif fault == "truncated":
        metadata["total"] = "3"
    elif fault == "duplicate-area":
        rows.append(("France renamed", "004", 100))
    elif fault == "wrong-world":
        rows[0] = ("World", "123", 100)
    elif fault == "missing-world":
        rows[0] = ("World", "WLD", None)
    elif fault == "no-data":
        rows = []
    elif fault in {"negative", "nan", "infinite", "unrepresentable"}:
        rows[0] = (
            "World",
            "WLD",
            {
                "negative": "-1",
                "nan": "NaN",
                "infinite": "Infinity",
                "unrepresentable": "1e400",
            }[fault],
        )
    elif fault == "html":
        headers["content-type"] = "text/html"
    elif fault == "redirect":
        status = 302
        headers["location"] = "https://example.com/ids.xml"

    body = _xml_response(series, year, rows, source_id=source_id, **metadata)
    if fault == "wrong-country":
        body = body.replace(b'id="KEN"', b'id="UGA"')
    elif fault == "wrong-series":
        body = body.replace(series.encode(), MULTILATERAL.encode())
    elif fault == "doctype":
        body = b'<!DOCTYPE data [<!ENTITY forged "100">]>' + body
    requests = []

    def publisher(request):
        requests.append(request.url)
        if request.url.params["format"] == "json":
            return httpx.Response(502)
        return httpx.Response(status, content=body, headers=headers)

    with _client(tmp_path, publisher) as client:
        with pytest.raises((ids.IdsCreditorError, httpx.HTTPStatusError)):
            ids.latest_year_with_data(client, candidates=[2025, 2024])
    assert len(requests) == 4
    assert all("/YR2025" in url.path for url in requests)


@pytest.mark.parametrize("status", [401, 404, 429, 502])
def test_transport_failure_is_bounded_and_refuses_before_older_year(tmp_path, status):
    requests = []

    def publisher(request):
        requests.append(request.url)
        return httpx.Response(status)

    with _client(tmp_path, publisher) as client:
        with pytest.raises(httpx.HTTPStatusError):
            ids.latest_year_with_data(client, candidates=[2025, 2024])
    expected = {
        401: ["json"],
        404: ["json"],
        429: ["json"] * 3,
        502: ["json"] * 3 + ["xml"] * 3,
    }
    assert [url.params["format"] for url in requests] == expected[status]
    assert all("/YR2025" in url.path for url in requests)


def test_only_a_complete_empty_world_observation_can_advance_year(tmp_path):
    series = ids.TOTAL_SERIES
    requests = []

    def publisher(request):
        requests.append(request.url)
        if "/YR2024" in request.url.path:
            return _json_response(series, 2024, [("World", "WLD", 100)])
        if request.url.params["format"] == "json":
            raise httpx.ReadTimeout("simulated publisher timeout", request=request)
        body = _xml_response(series, 2025, [("World", "WLD", None)])
        return httpx.Response(
            200, content=body, headers={"content-type": "application/xml"}
        )

    with _client(tmp_path, publisher) as client:
        assert ids.latest_year_with_data(client, candidates=[2025, 2024]) == 2024
    assert [url.params["format"] for url in requests] == [
        "json",
        "json",
        "json",
        "xml",
        "json",
    ]


def test_recovery_cannot_mix_world_bank_releases(tmp_path):
    def publisher(request):
        series = request.url.path.split("/series/")[1].split("/")[0]
        format_ = request.url.params["format"]
        if series == MULTILATERAL:
            if format_ == "json":
                return httpx.Response(502)
            body = _xml_response(
                series, 2024, IDS_2024[series], lastupdated="2025-10-01"
            )
            return httpx.Response(
                200, content=body, headers={"content-type": "text/xml"}
            )
        return _json_response(series, 2024, IDS_2024[series])

    with _client(tmp_path, publisher) as client:
        with pytest.raises(ids.IdsCreditorError, match="IDS release differs"):
            ids.fetch_creditors(client, 2024)


@pytest.mark.parametrize("provenance", ["cached", "other-request"])
def test_valid_publisher_bytes_cannot_reuse_unrelated_acquisition(tmp_path, provenance):
    series = ids.TOTAL_SERIES
    url = f"{ids._IDS_BASE}/{series}/counterpart-area/all/time/YR2024?format=json&per_page=400"
    response = _json_response(series, 2024, [("World", "WLD", 100)])
    response.request = httpx.Request("GET", url)
    with _client(tmp_path, lambda _: pytest.fail("unexpected HTTP request")) as client:
        if provenance == "cached":
            response.extensions["seeding_cache"] = True
        else:
            unrelated = _json_response(series, 2024, [("World", "WLD", 100)])
            unrelated.request = httpx.Request("GET", "https://example.com/ids.json")
            response.extensions["response_receipt"] = capture_response(
                unrelated, client.receipt_store
            )
        with pytest.raises(
            ids.IdsCreditorError, match="does not match the live request"
        ):
            ids._parse_series_response(client, response, url, series, 2024, xml=False)
