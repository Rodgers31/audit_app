"""Prospective API source binding through actual R2/SQL/public qualifications."""
import copy
import hashlib
import hmac
import json
import re
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from models import Base, Country, DocumentType, EconomicIndicator, Extraction, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains.economic_indicators import fetcher, parser, writer
from seeding.http_client import SeedingHttpClient
from seeding.types import DomainRunContext
from services.r2_receipt_store import R2ReceiptStore
from test_r2_receipt_store import ACCESS, ACCOUNT, CONTROL, R2_BUCKET, SECRET, Boundary


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(*args, **kwargs):
    return "JSON"


class SignedBoundary(Boundary):
    """Recalculate HMAC over the final HTTP request, rather than SDK objects."""
    def __call__(self, request):
        if request.url.host != "api.cloudflare.com":
            match = re.fullmatch(r"AWS4-HMAC-SHA256 Credential=([^/]+)/([^,]+), SignedHeaders=([^,]+), Signature=([0-9a-f]{64})", request.headers["authorization"])
            assert match
            access, scope, names, signature = match.groups()
            assert access == ACCESS
            day, region, service, end = scope.split("/")
            assert (region, service, end) == ("auto", "s3", "aws4_request")
            names = names.split(";")
            headers = "".join(name + ":" + re.sub(r"\s+", " ", request.headers[name].strip()) + "\n" for name in names)
            payload = hashlib.sha256(request.content).hexdigest()
            canonical = "\n".join([request.method, request.url.path, "", headers, ";".join(names), payload])
            string = "AWS4-HMAC-SHA256\n" + request.headers["x-amz-date"] + "\n" + scope + "\n" + hashlib.sha256(canonical.encode()).hexdigest()
            key = ("AWS4" + SECRET).encode()
            for part in (day, region, service, end):
                key = hmac.new(key, part.encode(), hashlib.sha256).digest()
            assert hmac.compare_digest(hmac.new(key, string.encode(), hashlib.sha256).hexdigest(), signature)
            if request.method == "PUT":
                assert "if-none-match" in names and request.headers["if-none-match"] == "*"
        return super().__call__(request)


def test_actual_worldbank_fetch_parse_write_read_all_indicators(tmp_path):
    from routers import economic

    boundary = SignedBoundary(tmp_path / "r2")
    store = R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL, max_bytes=1048576, part_max_bytes=4096, transport=httpx.MockTransport(boundary))
    settings = SeedingSettings(_env_file=None, storage_path=tmp_path / "cache", http_cache_enabled=False, rate_limit="1000/sec")
    template = json.loads((Path(__file__).parent / "fixtures/worldbank_gdp_2022.json").read_text())
    values = {"NY.GDP.MKTP.CN": 13489642000000, "NY.GDP.MKTP.KD.ZG": 3.25, "FP.CPI.TOTL.ZG": 7.66, "SL.UEM.TOTL.ZS": 5.69, "FP.CPI.TOTL": 155.123, "GC.REV.XGRT.GD.ZS": 19.37, "GC.XPN.TOTL.GD.ZS": 23.88}
    requests = []
    def publisher(request):
        assert request.url.host == "api.worldbank.org"
        code = request.url.path.rsplit("/", 1)[-1]
        payload = copy.deepcopy(template)
        payload[1][0]["indicator"]["id"] = code
        payload[1][0]["value"] = values[code]
        requests.append(str(request.url))
        return httpx.Response(200, json=payload)
    with SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(publisher)), receipt_store=store) as client:
        raw = fetcher._fetch_wb_indicators(client)
    records = parser.parse_economic_payload(raw)
    assert len(records) == 7
    engine = create_engine("sqlite:///" + str(tmp_path / "owned.sqlite"), connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            country = Country(iso_code="KEN", name="Kenya", currency="KES", timezone="Africa/Nairobi", default_locale="en")
            db.add(country)
            db.flush()
            historical = SourceDocument(country_id=country.id, publisher="World Bank", title="Historical landing citation", url="https://data.worldbank.org/indicator/NY.GDP.MKTP.CN?locations=KE", fetch_date=datetime(2020, 1, 1), doc_type=DocumentType.REPORT, meta={"preserve": "historical"})
            db.add(historical)
            db.commit()
            before = (historical.id, historical.url, historical.title, historical.fetch_date, copy.deepcopy(historical.meta))
            stats = writer.persist_economic_records(db, records, settings, DomainRunContext(since=None, dry_run=False))
            assert (stats.created, stats.updated, stats.errors) == (7, 0, [])
            db.commit()
            db.expire_all()
            rows = db.scalars(select(EconomicIndicator)).all()
            receipts = db.scalars(select(Extraction)).all()
            assert len(rows) == len(receipts) == 7
            for extraction in receipts:
                receipt = extraction.extracted_json["response_receipt"]
                assert receipt["storage_scope"] == "r2_private"
                assert receipt["byte_check"]["status"] == "matched"
                assert receipt["observations"] and receipt["parser_version"] == "worldbank-observation-v1"
                assert receipt["request_url"] in requests
            app = FastAPI()
            app.include_router(economic.router)
            def owned_db():
                yield db
            app.dependency_overrides[economic.get_db] = owned_db
            count = len(boundary.requests)
            with TestClient(app) as public:
                response = public.get("/api/v1/economic/indicators")
                assert response.status_code == 200
                body = response.json()
                assert len(body) == 7
                for entry in body:
                    qualification = entry["qualifications"][entry["indicator_type"]]
                    assert qualification["status"] == "verified", qualification
                    assert qualification["document_bytes_checked"] and qualification["value_checked"]
                assert len(boundary.requests) == count, "Public reads must not fetch source bytes"
                for row in rows:
                    source = db.get(SourceDocument, row.source_document_id)
                    evidence = row.meta["source_evidence"][0]
                    code = evidence["locator"]["indicator"]
                    assert source.url == "https://api.worldbank.org/v2/country/KEN/indicator/" + code
                    citation = "https://data.worldbank.org/indicator/" + code + "?locations=KE"
                    assert "Citation: " + citation in row.meta["notes"]
                historical = db.get(SourceDocument, before[0])
                assert (historical.id, historical.url, historical.title, historical.fetch_date, historical.meta) == before
                # Hostile receipt metadata remains conflicting at the actual public boundary.
                for extraction in receipts:
                    content = copy.deepcopy(extraction.extracted_json)
                    content["response_receipt"]["request_url"] = "https://hostile.example/source"
                    extraction.extracted_json = content
                db.commit()
                refused = public.get("/api/v1/economic/indicators")
                assert refused.status_code == 200
                for entry in refused.json():
                    qualification = entry["qualifications"][entry["indicator_type"]]
                    assert qualification["status"] == "conflicting"
                    assert qualification["reason"] == "receipt_request_source_mismatch"
                assert len(boundary.requests) == count
    finally:
        engine.dispose()
