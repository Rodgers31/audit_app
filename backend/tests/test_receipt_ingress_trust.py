"""Actual ingestion and public handlers reject input-provided receipt authority."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import pickle

import httpx
import pytest

from models import EconomicIndicator, Extraction, SourceDocument, DocumentType
from seeding.config import SeedingSettings
from seeding.domains.economic_indicators.parser import parse_economic_payload
from seeding.domains.economic_indicators.writer import persist_economic_records
from seeding.observations import worldbank_observations
from seeding.types import DomainRunContext
from services.figure_qualification import qualify_rows
from services.receipt_store import LocalReceiptStore
from services.response_receipts import persist_evidence, persist_receipt


RAW = Path(__file__).parent / "fixtures/worldbank_gdp_2022.json"
URL = "https://api.worldbank.org/v2/country/KEN/indicator/SL.UEM.TOTL.ZS"


def acquired(tmp_path, *, years=(2024,), value=7, store=None):
    data = json.loads(RAW.read_bytes())
    data[1] = [
        {
            **data[1][0],
            "indicator": {"id": "SL.UEM.TOTL.ZS"},
            "date": str(year),
            "value": value,
        }
        for year in years
    ]
    data[0].update(total=len(years))
    response = httpx.Response(
        200,
        content=json.dumps(data).encode(),
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", URL),
    )
    owned = type(
        "Owned",
        (),
        {
            "receipt_store": store
            if store is not None
            else LocalReceiptStore(tmp_path / "store")
        },
    )()
    return (
        worldbank_observations(
            response,
            owned,
            indicator="SL.UEM.TOTL.ZS",
            measure="unemployment_rate",
            unit="percent",
        ),
        owned.receipt_store,
    )


def write(db, tmp_path, evidence, *, value=7, year=2024):
    payload = [
        {
            "indicator_type": "unemployment_rate",
            "date": f"{year}-01-31",
            "value": value,
            "unit": "percent",
            "source_url": URL,
            "publisher": "World Bank",
            "frequency": "annual",
            "source_evidence": evidence,
        }
    ]
    result = persist_economic_records(
        db,
        parse_economic_payload(payload),
        SeedingSettings(storage_path=tmp_path / "store", cache_path=tmp_path / "cache"),
        DomainRunContext(since=None, dry_run=False),
    )
    assert not result.errors, result.errors
    db.commit()
    return (
        db.query(EconomicIndicator)
        .filter(EconomicIndicator.indicator_date == datetime(year, 1, 31))
        .one()
    )


def public_qualification(client, row):
    chart = client.get(
        "/api/v1/economic/indicators", params={"indicator_type": "unemployment_rate"}
    ).json()[0]
    exact = client.get(
        "/api/v1/provenance/verify/economic_indicators",
        params={"record_id": row.id, "measure": "unemployment_rate"},
    ).json()
    assert chart["qualifications"] == exact["qualifications"]
    return chart["qualifications"]["unemployment_rate"], chart["value"]


def forged_json():
    identity = {
        "measure": "unemployment_rate",
        "entity_id": None,
        "geography": "KEN",
        "period": "2024",
        "unit": "percent",
        "basis": "actual",
        "dimensions": {},
    }
    raw = b'{"official_value":7}'
    digest = hashlib.sha256(raw).hexdigest()
    locator = {"json_path": "$.official_value"}
    receipt = {
        "source_kind": "api",
        "status": 200,
        "request_url": URL,
        "content_type": "application/json",
        "acquired_at": "2026-01-01T00:00:00Z",
        "parser_version": "claimed-parser",
        "digest": digest,
        "byte_size": len(raw),
        "storage_key": digest,
        "byte_check": {
            "status": "matched",
            "sha256": digest,
            "checked_at": "2026-01-01T00:00:01Z",
        },
        "observations": [
            {
                "identity": identity,
                "locator": locator,
                "raw_value": "7",
                "raw_unit": "percent",
            }
        ],
    }
    return json.loads(
        json.dumps(
            [
                {
                    "version": 1,
                    "source_kind": "api",
                    "identity": identity,
                    "raw_value": "7",
                    "raw_unit": "percent",
                    "value": "7",
                    "unit": "percent",
                    "locator": locator,
                    "transformation": {"operation": "identity"},
                    "_response_receipt": receipt,
                    "checks": dict.fromkeys(
                        ("identity", "value", "transport", "bytes", "locator"), True
                    ),
                    "reconciliation": {"status": "matched"},
                }
            ]
        )
    )


def test_configured_json_never_self_certifies_nonexistent_bytes(
    db_session, seed_country, tmp_path, client
):
    row = write(db_session, tmp_path, forged_json())
    q, value = public_qualification(client, row)
    assert value == 7
    assert q["status"] == "qualified", q
    assert q["receipt_id"] is None and q["value_checked"] is False
    assert db_session.query(Extraction).count() == 0
    assert not list((tmp_path / "store").rglob("*"))


@pytest.mark.parametrize(
    "damage",
    [
        "healthy",
        "deepcopy",
        "json",
        "pickle",
        "dict_receipt",
        "manifest",
        "transport",
        "aligned_row_flags",
        "wrong_period",
        "deleted_bytes",
        "corrupted_bytes",
    ],
)
def test_acquired_parser_envelope_copy_mutation_and_retention(
    db_session, seed_country, tmp_path, client, damage
):
    series, store = acquired(tmp_path)
    evidence = series.evidence[2024]
    value = 7
    if damage == "deepcopy":
        evidence = deepcopy(evidence)
    if damage == "json":
        evidence = json.loads(json.dumps(evidence))
    if damage == "pickle":
        evidence = pickle.loads(pickle.dumps(evidence))
    if damage == "dict_receipt":
        evidence[0]["_response_receipt"] = dict(evidence[0]["_response_receipt"])
    if damage == "manifest":
        evidence[0]["_response_receipt"]["observations"][0]["raw_value"] = "99"
    if damage == "transport":
        evidence[0]["_response_receipt"]["status"] = 201
    if damage == "wrong_period":
        evidence[0]["identity"]["period"] = "2023"
    if damage == "aligned_row_flags":
        value = 99
        evidence[0].update(raw_value="99", value="99")
        evidence[0]["checks"] = dict.fromkeys(evidence[0]["checks"], True)
    if damage in ("deleted_bytes", "corrupted_bytes"):
        path = store._path(evidence[0]["_response_receipt"]["digest"])
        if damage == "deleted_bytes":
            path.unlink()
        else:
            path.write_bytes(b"corrupted")
    row = write(db_session, tmp_path, evidence, value=value)
    q, public_value = public_qualification(client, row)
    assert public_value == value
    assert (q["status"] == "verified") == (damage in ("healthy", "deepcopy")), q
    if damage == "wrong_period":
        assert (
            q["status"] == "conflicting"
            and q["reason"] == "observation_identity_mismatch"
        )
    if damage in ("json", "pickle", "dict_receipt", "manifest", "transport"):
        assert db_session.query(Extraction).count() == 0


def test_exported_exact_ref_cannot_be_reused_by_normalized_ingress(
    db_session, seed_country, tmp_path, client
):
    series, _ = acquired(tmp_path)
    original = write(db_session, tmp_path, series.evidence[2024])
    exported = json.loads(json.dumps(original.meta["source_evidence"]))
    assert public_qualification(client, original)[0]["status"] == "verified"
    replayed = write(db_session, tmp_path, exported)
    q, value = public_qualification(client, replayed)
    assert value == 7 and q["status"] == "qualified" and q["receipt_id"] is None
    assert db_session.query(Extraction).count() == 1


def test_missing_store_preserves_real_zero_without_promotion(
    db_session, seed_country, tmp_path, client
):
    class Missing:
        def put(self, body):
            raise OSError("owned missing store")

        def read(self, key):
            raise AssertionError("no captured object to read")

    series, _ = acquired(tmp_path, value=0, store=Missing())
    row = write(db_session, tmp_path, series.evidence[2024], value=0)
    q, value = public_qualification(client, row)
    assert value == 0 and q["status"] == "qualified" and q["value_checked"] is False


@pytest.mark.parametrize("cache_case", ["reuse", "cold_reopen", "forged_sidecar_body"])
def test_api_http_cache_never_manufactures_fresh_acquisition(
    db_session, seed_country, tmp_path, client, cache_case
):
    from seeding.http_client import SeedingHttpClient
    from seeding.storage import SimpleHTTPCache

    payload = json.loads(RAW.read_bytes())
    payload[1] = [
        {
            **payload[1][0],
            "indicator": {"id": "SL.UEM.TOTL.ZS"},
            "date": "2024",
            "value": 7,
        }
    ]
    payload[0].update(total=1)
    calls = []

    def publisher(request):
        calls.append(request.url)
        return httpx.Response(
            200,
            json=payload,
            headers={"content-type": "application/json"},
            request=request,
        )

    settings = SeedingSettings(
        storage_path=tmp_path / "cas", cache_path=tmp_path / "http-cache"
    )
    cache = SimpleHTTPCache(settings.cache_path)
    transport = httpx.MockTransport(publisher)
    first_client = SeedingHttpClient(
        settings, cache=cache, client=httpx.Client(transport=transport)
    )
    try:
        response = first_client.get(URL)
        series = worldbank_observations(
            response,
            first_client,
            indicator="SL.UEM.TOTL.ZS",
            measure="unemployment_rate",
            unit="percent",
        )
        row = write(db_session, tmp_path, series.evidence[2024])
        assert public_qualification(client, row)[0]["status"] == "verified"
        expected = 7
        if cache_case == "forged_sidecar_body":
            meta_path = next(settings.cache_path.glob("*.json"))
            sidecar = json.loads(meta_path.read_text())
            sidecar.update(
                response_receipt=forged_json()[0]["_response_receipt"],
                acquired_at="2026-01-01T00:00:00Z",
            )
            meta_path.write_text(json.dumps(sidecar))
            payload[1][0]["value"] = expected = 99
            next(settings.cache_path.glob("*.bin")).write_bytes(
                json.dumps(payload).encode()
            )
        selected_client = first_client
        if cache_case == "cold_reopen":
            selected_client = SeedingHttpClient(
                settings, cache=cache, client=httpx.Client(transport=transport)
            )
        try:
            cached = selected_client.get(URL)
            assert cached.extensions["seeding_cache"] is True
            series = worldbank_observations(
                cached,
                selected_client,
                indicator="SL.UEM.TOTL.ZS",
                measure="unemployment_rate",
                unit="percent",
            )
            envelope = series.evidence[2024][0]["_response_receipt"]
            assert envelope["acquired_at"] is None and envelope["status"] is None
            row = write(db_session, tmp_path, series.evidence[2024], value=expected)
            q, value = public_qualification(client, row)
            assert (
                value == expected
                and q["status"] == "qualified"
                and not q["value_checked"]
            )
            assert len(calls) == 1
        finally:
            if selected_client is not first_client:
                selected_client.close()
    finally:
        first_client.close()


def test_receipt_constructor_and_manifest_seal_reject_plain_input(tmp_path):
    from services.response_receipts import CapturedReceipt, seal_receipt

    raw = forged_json()[0]["_response_receipt"]
    with pytest.raises(TypeError):
        CapturedReceipt(raw)
    with pytest.raises(ValueError):
        seal_receipt(raw)


@pytest.mark.parametrize("change_before_copy", [False, True])
def test_parser_copy_cannot_reauthorize_a_sealed_or_changed_source_manifest(
    db_session, seed_country, tmp_path, client, change_before_copy
):
    from services.response_receipts import copy_receipt

    series, _ = acquired(tmp_path)
    evidence = deepcopy(series.evidence[2024])
    captured = evidence[0]["_response_receipt"]
    if change_before_copy:
        captured["observations"][0]["raw_value"] = "99"
    with pytest.raises(ValueError):
        copy_receipt(captured, parser_version="worldbank-observation-v1")
    evidence[0].update(raw_value="99", value="99")
    row = write(db_session, tmp_path, evidence, value=99)
    q, value = public_qualification(client, row)
    assert value == 99 and q["status"] != "verified"


def test_capture_and_persistence_readback_are_once_for_many_source_rows(
    db_session, seed_country, tmp_path
):
    class Counting(LocalReceiptStore):
        puts = reads = 0

        def put(self, body):
            self.puts += 1
            return super().put(body)

        def read(self, key):
            self.reads += 1
            return super().read(key)

    store = Counting(tmp_path / "counted")
    series, _ = acquired(tmp_path, years=range(2000, 2025), store=store)
    assert (store.puts, store.reads) == (1, 1)
    records = [
        {
            "indicator_type": "unemployment_rate",
            "date": f"{year}-01-31",
            "value": 7,
            "unit": "percent",
            "source_url": URL,
            "publisher": "World Bank",
            "source_evidence": series.evidence[year],
        }
        for year in series
    ]
    result = persist_economic_records(
        db_session,
        parse_economic_payload(records),
        SeedingSettings(storage_path=tmp_path / "store", cache_path=tmp_path / "cache"),
        DomainRunContext(since=None, dry_run=False),
    )
    assert not result.errors
    db_session.flush()
    assert db_session.query(Extraction).count() == 1
    assert (store.puts, store.reads) == (1, 2)
    rows = db_session.query(EconomicIndicator).all()
    assert len(rows) == 25
    assert all(
        q["unemployment_rate"]["status"] == "verified"
        for q in qualify_rows(db_session, "economic_indicators", rows).values()
    )
    assert (store.puts, store.reads) == (1, 2)  # Public metadata reads add no byte IO.


def test_captured_capability_cannot_change_source_association(
    db_session, seed_country, tmp_path
):
    series, _ = acquired(tmp_path)
    row = write(db_session, tmp_path, series.evidence[2024])
    other = SourceDocument(
        country_id=seed_country.id,
        title="Other source",
        publisher="World Bank",
        url=URL + "/other",
        fetch_date=datetime.now(),
        doc_type=DocumentType.REPORT,
    )
    db_session.add(other)
    db_session.flush()
    cloned = deepcopy(series.evidence[2024])
    result = persist_evidence(db_session, other, cloned)
    assert result[0]["receipt"]["extraction_id"] is None
    assert db_session.query(Extraction).count() == 1
    with pytest.raises(ValueError, match="different source"):
        persist_receipt(db_session, other, cloned[0]["_response_receipt"])


@pytest.mark.parametrize("damage", ["cache_hit", "poisoned_cache", "mutated_fresh"])
def test_pdf_normalized_cache_cannot_seal_source_values(
    db_session, seed_source_doc, tmp_path, damage
):
    from seeding.parse_cache import parse_with_cache
    from seeding.pdf_evidence import (
        bind_parse_receipt,
        cell_evidence,
        seal_pdf_observations,
        bind_pdf_evidence,
    )
    from services.response_receipts import capture_response, copy_receipt
    from services.figure_qualification import (
        evaluate_qualification,
        ObservationIdentity,
    )

    path = tmp_path / "owned-source.pdf"
    body = b"%PDF-1.7\n7\n%%EOF"
    path.write_bytes(body)
    calls = []

    def actual_parse():
        calls.append(1)
        return [{"amount": int(path.read_bytes().splitlines()[1])}]

    def parse():
        return parse_with_cache(
            path, cache_dir=tmp_path, kind="owned-trust-control", parse_fn=actual_parse
        )

    receipt = capture_response(
        httpx.Response(
            200,
            content=body,
            headers={"content-type": "application/pdf"},
            request=httpx.Request("GET", seed_source_doc.url),
        ),
        LocalReceiptStore(tmp_path / "cas"),
        source_kind="pdf",
    )
    receipt = copy_receipt(receipt, parser_version="owned-source-cell-v1")
    identity = {
        "measure": "allocated_amount",
        "entity_id": None,
        "geography": "KEN",
        "period": "2024",
        "unit": "KES",
        "basis": "actual",
        "dimensions": {},
    }

    def bind(records):
        item = cell_evidence(
            receipt=bind_parse_receipt(receipt, records),
            identity=identity,
            raw_value=records[0]["amount"],
            value=records[0]["amount"],
            raw_unit="KES",
            factor="1",
            locator={"page": 1, "cell": "owned amount"},
        )
        seal_pdf_observations([item])
        bound = bind_pdf_evidence(
            db_session,
            seed_source_doc,
            [item],
            identity=identity,
            values={"allocated_amount": records[0]["amount"]},
        )[0]
        ext = (
            db_session.get(Extraction, bound["receipt"]["extraction_id"])
            if bound["receipt"]["extraction_id"]
            else None
        )
        return evaluate_qualification(
            ObservationIdentity(**identity),
            records[0]["amount"],
            source=seed_source_doc,
            evidence=bound,
            receipt=ext.extracted_json["response_receipt"] if ext else None,
        )

    fresh = parse()
    assert bind(fresh).status == "verified"
    if damage == "mutated_fresh":
        fresh[0]["amount"] = 9
        selected = fresh
    else:
        if damage == "poisoned_cache":
            entry = next(tmp_path.glob("*.parse.json"))
            cached = json.loads(entry.read_text())
            cached["records"][0]["amount"] = 9
            entry.write_text(json.dumps(cached))
        selected = parse()
    q = bind(selected)
    assert calls == [1]  # Cache speed remains intact; no historical reparse.
    assert q.status == "qualified" and q.receipt_id is None
    assert selected[0]["amount"] == (7 if damage == "cache_hit" else 9)
    assert db_session.query(Extraction).count() == 1


def test_cbk_manifest_requires_the_exact_captured_parser_input(tmp_path):
    from services.response_receipts import capture_response
    from seeding.domains.economic_indicators.cbk_inflation import parse_cbk_inflation

    body = (
        Path(__file__).parent / "fixtures/cbk/inflation_rates_2026-09-26.html"
    ).read_bytes()
    receipt = capture_response(
        httpx.Response(
            200,
            content=body,
            headers={"content-type": "text/html"},
            request=httpx.Request("GET", "https://www.centralbank.go.ke/inflation/"),
        ),
        LocalReceiptStore(tmp_path),
        source_kind="web",
    )
    healthy = parse_cbk_inflation(body.decode(), receipt, source_bytes=body)
    assert healthy.records and all(r.get("source_evidence") for r in healthy.records)
    changed = parse_cbk_inflation(body.decode() + "changed", receipt, source_bytes=body)
    assert changed.records and all(
        not r.get("source_evidence") for r in changed.records
    )


def test_typed_ids_input_acquisition_cannot_certify_incomplete_kes_manifest(
    db_session, seed_country, tmp_path
):
    from seeding.domains.national_debt.wb_ids_creditors import (
        fetch_creditors,
        to_loan_rows,
    )
    from services.figure_qualification import (
        evaluate_qualification,
        ObservationIdentity,
    )
    from test_wb_ids_creditors import FakeIds, IDS_TEST_RATE

    client = FakeIds()
    client.receipt_store = LocalReceiptStore(tmp_path / "ids-cas")
    creditors, _ = fetch_creditors(client, 2024, IDS_TEST_RATE)
    row = to_loan_rows(creditors, 2024)[0]
    doc = SourceDocument(
        country_id=seed_country.id,
        publisher="World Bank",
        title=row["source_title"],
        url=row["source_url"],
        doc_type=DocumentType.LOAN,
        fetch_date=datetime.now(),
    )
    db_session.add(doc)
    db_session.flush()
    evidence = persist_evidence(db_session, doc, creditors[0].source_evidence)[0]
    extraction = db_session.get(Extraction, evidence["receipt"]["extraction_id"])
    receipt = extraction.extracted_json["response_receipt"]
    assert receipt["byte_check"]["status"] == "matched"
    assert receipt["observations"] == []
    q = evaluate_qualification(
        ObservationIdentity(**evidence["identity"]),
        row["outstanding"],
        source=doc,
        evidence=evidence,
        receipt=receipt,
    )
    assert q.status == "qualified" and q.reason == "receipt_observation_missing"
    assert evidence["reconciliation"]["reason"] == "independent_fx_operand_not_checked"


def test_ids_historical_kes_value_is_qualified_in_actual_loan_and_exact_handlers(
    db_session, seed_country, tmp_path, client
):
    from decimal import Decimal
    from models import Entity, EntityType, Loan
    from seeding.domains.national_debt.parser import parse_debt_payload
    from seeding.domains.national_debt.writer import write_debt_records
    from seeding.domains.national_debt.wb_ids_creditors import (
        fetch_creditors,
        to_loan_rows,
    )
    from test_wb_ids_creditors import FakeIds, IDS_TEST_RATE

    publisher = FakeIds()
    publisher.receipt_store = LocalReceiptStore(tmp_path / "ids-cas")
    creditors, _ = fetch_creditors(publisher, 2024, IDS_TEST_RATE)
    db_session.add(
        Entity(
            country_id=seed_country.id,
            type=EntityType.NATIONAL,
            canonical_name="National Government",
            slug="national-government",
        )
    )
    db_session.flush()
    inputs = to_loan_rows(creditors, 2024)
    expected = {
        r["lender"]: Decimal(r["outstanding"]).quantize(Decimal("0.01")) for r in inputs
    }
    created, updated = write_debt_records(
        db_session,
        parse_debt_payload({"loans": inputs}),
        dataset_id="owned-ids",
        job_id=1,
    )
    assert (created, updated) == (22, 0)
    db_session.commit()
    db_session.expire_all()
    stored = db_session.query(Loan).all()
    assert {r.lender: r.outstanding for r in stored} == expected
    assert all(
        r.interest_rate is None
        and "2024 (annual USD)" in r.provenance[-1]["source_note"]
        for r in stored
    )
    assert all(
        "independent FX operand" in r.provenance[-1]["source_note"]
        and "no genuine measurement date" in r.provenance[-1]["source_note"]
        for r in stored
    )
    payload = client.get("/api/v1/debt/loans").json()["loans"]
    assert len(payload) == 22
    for public in payload:
        verification = client.get(
            "/api/v1/provenance/verify/loans", params={"record_id": public["record_id"]}
        ).json()
        assert (
            "2024 (annual USD)" in verification["provenance_chain"][-1]["source_note"]
        )
        exact = verification["qualifications"]
        assert public["qualifications"] == exact
        assert exact["outstanding"]["status"] == "qualified"
        assert exact["outstanding"]["reason"] == "historical_source_not_value_checked"
        assert exact["interest_rate"]["status"] == "unavailable"
        assert public["outstanding_numeric"] == float(expected[public["lender"]])
    assert db_session.query(Extraction).count() == 0


@pytest.mark.parametrize("producer", ["worldbank", "kra", "independent_gdp_operand"])
def test_other_actual_typed_producers_on_owned_sqlite(tmp_path, monkeypatch, producer):
    """Exercise receipt wiring offline; PostgreSQL remains its separate gate."""
    from sqlalchemy import create_engine
    from models import Base
    from test_response_receipts import (
        test_actual_fetch_writer_commit_reopen_one_response_many_rows,
        test_retained_real_kra_dashboard_fetch_parser_writer,
        test_debt_gdp_retains_precision_and_independent_source,
    )

    engine = create_engine(f"sqlite:///{tmp_path / 'owned-receipts.sqlite'}")
    Base.metadata.create_all(engine)
    try:
        if producer == "worldbank":
            test_actual_fetch_writer_commit_reopen_one_response_many_rows(
                engine, tmp_path, monkeypatch
            )
        elif producer == "kra":
            test_retained_real_kra_dashboard_fetch_parser_writer(engine, tmp_path)
        else:
            test_debt_gdp_retains_precision_and_independent_source(engine, tmp_path)
    finally:
        engine.dispose()
