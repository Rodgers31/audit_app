"""Actual public handlers must expose the shared per-measure evidence contract."""
import pytest


@pytest.mark.parametrize("table", ["economic_indicators", "poverty_indices"])
def test_missing_economic_branches_are_supported(client, table):
    response = client.get(f"/api/v1/provenance/verify/{table}")
    assert response.status_code == 200
    assert response.json()["reason"] == "no_rows"


from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from sqlalchemy import event
from models import (
    BudgetLine,
    DebtTimeline,
    EconomicIndicator,
    Extraction,
    FigureBasis,
    GDPData,
    Loan,
    PovertyIndex,
    RevenueBySource,
    SourceDocument,
    DocumentStatus,
    DocumentType,
)
from services.figure_qualification import (
    row_identities,
    evaluate_qualification,
    qualify_rows,
)

TABLES = [
    "budget_lines",
    "loans",
    "gdp_data",
    "economic_indicators",
    "poverty_indices",
    "debt_timeline",
    "revenue_by_source",
]
PRIMARY = dict(
    budget_lines="allocated_amount",
    loans="outstanding",
    gdp_data="gdp_value",
    economic_indicators="unemployment_rate",
    poverty_indices="poverty_headcount_rate",
    debt_timeline="total",
    revenue_by_source="amount_billion_kes",
)


def observation(db, country, entity, period, table, tmp_path, *, value=0, kind="api"):
    from seeding.domains.national_gdp import _ensure_gdp_source_document

    if table == "gdp_data":
        doc = _ensure_gdp_source_document(db)
    else:
        doc = SourceDocument(
            country_id=country.id,
            publisher="Central Bank of Kenya",
            title="Observed official estimate",
            url="https://www.centralbank.go.ke/data",
            fetch_date=datetime(2026, 1, 1),
            doc_type=DocumentType.REPORT,
            status=DocumentStatus.ARCHIVED,
            meta={},
        )
        db.add(doc)
        db.flush()
    common = {"source_document_id": doc.id}
    if table == "budget_lines":
        row = BudgetLine(
            entity_id=entity.id,
            period_id=period.id,
            category="Total",
            allocated_amount=value,
            actual_spent=None,
            currency="KES",
            provenance=[],
            **common,
        )
    elif table == "loans":
        row = Loan(
            entity_id=entity.id,
            lender="Official creditor",
            principal=value,
            outstanding=value,
            interest_rate=None,
            issue_date=datetime(2024, 1, 1),
            currency="KES",
            provenance=[],
            **common,
        )
    elif table == "gdp_data":
        row = GDPData(
            year=2024,
            gdp_value=value,
            currency="KES",
            meta={
                "source": "World Bank NY.GDP.MKTP.CN",
                "scope": "national",
                "data_quality": "official",
            },
            **common,
        )
    elif table == "economic_indicators":
        row = EconomicIndicator(
            indicator_type="unemployment_rate",
            indicator_date=datetime(2024, 1, 1),
            value=value,
            unit="percent",
            meta={},
            **common,
        )
    elif table == "poverty_indices":
        row = PovertyIndex(
            year=2024,
            poverty_headcount_rate=value,
            extreme_poverty_rate=None,
            gini_coefficient=None,
            meta={},
            **common,
        )
    elif table == "debt_timeline":
        row = DebtTimeline(
            year=2024,
            total=value,
            external=value,
            domestic=0,
            gdp=100,
            gdp_ratio=value,
            unit="KES",
            meta={},
            **common,
        )
    else:
        row = RevenueBySource(
            fiscal_year="FY 2024/25",
            revenue_type="PAYE",
            category="tax",
            amount_billion_kes=value,
            meta={},
            **common,
        )
    if table == "loans":
        row.provenance = [{"as_at": "2024-01-01"}]
    db.add(row)
    db.flush()
    measure = PRIMARY[table]
    identity = row_identities(table, row, {entity.id: entity}, {period.id: period})[
        measure
    ]
    raw = json.dumps(
        {"observation": str(value), "identity": identity.model_dump()}, sort_keys=True
    ).encode()
    path = tmp_path / sha256(raw).hexdigest()
    path.write_bytes(raw)
    checked = sha256(path.read_bytes()).hexdigest()
    receipt = {
        "source_kind": kind,
        "status": 200,
        "content_type": "application/pdf" if kind == "pdf" else "application/json",
        "request_url": doc.url,
        "acquired_at": "2026-01-01T00:00:00Z",
        "digest": sha256(raw).hexdigest(),
        "byte_size": len(raw),
        "storage_key": str(path),
        "parser_version": "test-parser-v1",
        "byte_check": {
            "status": "matched",
            "sha256": checked,
            "checked_at": "2026-01-01T00:00:01Z",
        },
    }
    extraction = Extraction(
        source_document_id=doc.id,
        extractor="pdf-receipt-v1" if kind == "pdf" else "http-response-v1",
        extracted_json={"response_receipt": receipt},
    )
    db.add(extraction)
    db.flush()
    evidence = {
        "version": 1,
        "source_kind": kind,
        "identity": identity.model_dump(),
        "receipt": {"extraction_id": extraction.id, "digest": receipt["digest"]},
        "raw_value": str(value),
        "raw_unit": identity.unit,
        "value": str(value),
        "unit": identity.unit,
        "locator": {"page": 1, "table": "Table 1", "cell": measure}
        if kind == "pdf"
        else (
            {"table": "revenueStreams", "cell": measure, "edition": "FY 2024/25"}
            if kind == "web"
            else {"json_path": "$.observation"}
        ),
        "transformation": {"operation": "identity"},
        "checks": dict.fromkeys(
            ("identity", "value", "transport", "bytes", "locator"), True
        ),
        "reconciliation": {"status": "matched"},
    }
    # Independently reparse the retained response, not the normalized row.
    decoded = json.loads(path.read_bytes())
    receipt["observations"] = [
        {
            "identity": decoded["identity"],
            "locator": evidence["locator"],
            "raw_value": decoded["observation"],
            "raw_unit": identity.unit,
        }
    ]
    extraction.extracted_json = {"response_receipt": receipt}
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(extraction, "extracted_json")
    if hasattr(row, "meta"):
        row.meta = {**row.meta, "source_evidence": [evidence]}
    else:
        row.provenance = [{"as_at": "2024-01-01", "source_evidence": [evidence]}]
    db.commit()
    return row, doc, evidence, receipt, extraction


@pytest.mark.parametrize("table", TABLES)
def test_seven_actual_verify_handlers_match_retained_zero(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path, table
):
    row, doc, *_ = observation(
        db_session, seed_country, seed_entity, seed_fiscal_period, table, tmp_path
    )
    response = client.get(f"/api/v1/provenance/verify/{table}")
    assert response.status_code == 200, response.text
    q = response.json()["qualifications"][PRIMARY[table]]
    assert q["status"] == "verified", q["reason"]
    assert q["value_checked"] and q["document_bytes_checked"]
    assert q["source_document_id"] == doc.id
    assert response.json()["verification_status"] == "verified"


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize(
    "damage,reason",
    [
        ("geography", "observation_identity_mismatch"),
        ("period", "observation_identity_mismatch"),
        ("unit", "observation_identity_mismatch"),
        ("value", "normalized_value_mismatch"),
        ("bytes", "retained_bytes_digest_mismatch"),
        ("missing", "receipt_missing"),
    ],
)
def test_actual_verify_handlers_cannot_upgrade_bad_evidence(
    client,
    db_session,
    seed_country,
    seed_entity,
    seed_fiscal_period,
    tmp_path,
    table,
    damage,
    reason,
):
    row, doc, evidence, receipt, extraction = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        table,
        tmp_path,
        value=7,
    )
    if damage in ("geography", "period", "unit"):
        evidence["identity"][damage] = "wrong"
    elif damage == "value":
        evidence["value"] = "8"
    elif damage == "bytes":
        receipt["byte_check"]["sha256"] = "f" * 64
    elif damage == "missing":
        evidence["receipt"]["extraction_id"] = 999999
    if hasattr(row, "meta"):
        row.meta = {**row.meta, "source_evidence": [evidence]}
    else:
        row.provenance = [{"as_at": "2024-01-01", "source_evidence": [evidence]}]
    extraction.extracted_json = {"response_receipt": receipt}
    db_session.commit()
    q = client.get(f"/api/v1/provenance/verify/{table}").json()["qualifications"][
        PRIMARY[table]
    ]
    assert q["status"] != "verified"
    assert q["reason"] == reason
    assert q["value_checked"] is False


@pytest.mark.parametrize("table", TABLES)
def test_url_hash_and_id_only_keep_archived_history_qualified(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path, table
):
    row, doc, *_ = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        table,
        tmp_path,
        value=7,
    )
    if hasattr(row, "meta"):
        row.meta = {k: v for k, v in row.meta.items() if k != "source_evidence"}
    else:
        row.provenance = []
    doc.md5 = "a" * 32
    db_session.commit()
    body = client.get(f"/api/v1/provenance/verify/{table}").json()
    assert body["qualifications"][PRIMARY[table]]["status"] == "qualified"
    assert body["value"] is not None
    assert body["qualifications"][PRIMARY[table]]["value_checked"] is False


def test_poverty_and_gdp_serializers_preserve_zero_and_null(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path
):
    observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "poverty_indices",
        tmp_path,
    )
    observation(
        db_session, seed_country, seed_entity, seed_fiscal_period, "gdp_data", tmp_path
    )
    poverty = client.get("/api/v1/economic/poverty").json()[0]
    assert poverty["poverty_headcount_rate"] == 0
    assert poverty["extreme_poverty_rate"] is None
    assert poverty["qualifications"]["extreme_poverty_rate"]["status"] == "unavailable"
    gdp = client.get("/api/v1/economic/gdp").json()[0]
    assert gdp["gdp_value"] == 0
    assert gdp["qualifications"]["gdp_value"]["status"] == "verified"


def test_official_round_estimate_is_not_an_app_model(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path
):
    row, doc, *_ = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "debt_timeline",
        tmp_path,
        value=100_000_000_000,
    )
    row.domestic = 100_000_000_000
    row.external = 100_000_000_000
    row.meta = {}
    db_session.commit()
    body = client.get("/api/v1/provenance/verify/debt_timeline").json()
    assert body["verification_status"] == "publishable"
    assert body["qualifications"]["total"]["status"] == "qualified"
    row.meta = {"origin": "app_model"}
    db_session.commit()
    assert (
        client.get("/api/v1/provenance/verify/debt_timeline").json()["qualifications"][
            "total"
        ]["status"]
        == "modelled"
    )


def test_projection_remains_projection_with_a_matching_receipt(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path
):
    row, doc, *_ = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "gdp_data",
        tmp_path,
        value=7,
    )
    row.basis = FigureBasis.PROJECTED
    db_session.commit()
    assert (
        client.get("/api/v1/economic/gdp").json()[0]["qualifications"]["gdp_value"][
            "status"
        ]
        == "projected"
    )


def test_debt_ratio_requires_gdp_receipt(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path
):
    observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "debt_timeline",
        tmp_path,
        value=7,
    )
    ratio = client.get("/api/v1/debt/timeline").json()["timeline"][0]["qualifications"][
        "gdp_ratio"
    ]
    assert ratio["status"] == "qualified"
    assert ratio["reason"] == "ratio_operands_not_independently_checked"


def test_batch_qualifier_has_constant_query_count(
    db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path
):
    row, *_ = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "gdp_data",
        tmp_path,
        value=7,
    )
    db_session.refresh(row)
    calls = []

    def query(*args):
        calls.append(args[2])

    event.listen(db_session.bind, "before_cursor_execute", query)
    try:
        qualify_rows(db_session, "gdp_data", [row] * 100)
    finally:
        event.remove(db_session.bind, "before_cursor_execute", query)
    assert len(calls) == 3  # document + referenced receipt; no entity for national


@pytest.mark.parametrize(
    "bad", [True, "NaN", "Infinity", None, {}, [], -1, "1e1000000"]
)
def test_pure_evaluator_refuses_hostile_numbers(bad):
    from services.figure_qualification import ObservationIdentity

    identity = ObservationIdentity(
        measure="value", geography="KEN", period="2024", unit="KES", basis="actual"
    )
    assert evaluate_qualification(identity, bad).status == "unavailable"


@pytest.mark.parametrize("table", TABLES)
def test_forged_row_booleans_and_values_cannot_replace_receipt_observation(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path, table
):
    row, doc, evidence, receipt, extraction = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        table,
        tmp_path,
        value=7,
    )
    field = PRIMARY[table]
    setattr(row, "value" if table == "economic_indicators" else field, Decimal("8"))
    evidence["value"] = evidence["raw_value"] = "8"
    if hasattr(row, "meta"):
        row.meta = {**row.meta, "source_evidence": [evidence]}
    else:
        row.provenance = [{"as_at": "2024-01-01", "source_evidence": [evidence]}]
    db_session.commit()
    q = client.get(f"/api/v1/provenance/verify/{table}").json()["qualifications"][field]
    assert q["status"] == "conflicting"
    assert q["reason"] == "receipt_observation_mismatch"


@pytest.mark.parametrize("table", TABLES)
def test_missing_source_observation_is_qualified(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path, table
):
    row, doc, evidence, receipt, extraction = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        table,
        tmp_path,
        value=7,
    )
    receipt.pop("observations")
    extraction.extracted_json = {"response_receipt": dict(receipt)}
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(extraction, "extracted_json")
    db_session.commit()
    q = client.get(f"/api/v1/provenance/verify/{table}").json()["qualifications"][
        PRIMARY[table]
    ]
    assert q["status"] == "qualified"
    assert q["reason"] == "receipt_observation_missing"


def test_wrong_receipt_source_association_is_conflicting(
    client,
    db_session,
    seed_country,
    seed_entity,
    seed_fiscal_period,
    seed_source_doc,
    tmp_path,
):
    row, doc, evidence, receipt, extraction = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "poverty_indices",
        tmp_path,
        value=7,
    )
    extraction.source_document_id = seed_source_doc.id
    db_session.commit()
    q = client.get("/api/v1/economic/poverty").json()[0]["qualifications"][
        "poverty_headcount_rate"
    ]
    assert q["reason"] == "receipt_source_document_mismatch"
    assert q["status"] == "conflicting"


def test_amount_receipt_does_not_verify_loan_terms(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path
):
    row, *_ = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "loans",
        tmp_path,
        value=7,
    )
    row.interest_rate = 4
    db_session.commit()
    q = client.get("/api/v1/provenance/verify/loans").json()["qualifications"]
    assert q["outstanding"]["status"] == "verified"
    assert q["interest_rate"]["status"] == "qualified"


def test_api_evidence_cannot_have_invented_pdf_page(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path
):
    row, doc, evidence, receipt, extraction = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "poverty_indices",
        tmp_path,
        value=7,
    )
    evidence["locator"]["page"] = 1
    row.meta = {**row.meta, "source_evidence": [evidence]}
    db_session.commit()
    q = client.get("/api/v1/economic/poverty").json()[0]["qualifications"][
        "poverty_headcount_rate"
    ]
    assert q["status"] == "conflicting" and q["reason"] == "non_pdf_page_locator"


@pytest.mark.parametrize("table", TABLES)
def test_actual_chart_serializers_use_same_qualification(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path, table
):
    if table == "loans":
        from models import EntityType

        seed_entity.type = EntityType.NATIONAL
        db_session.flush()
    row, *_ = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        table,
        tmp_path,
        value=7,
    )
    if table == "budget_lines":
        payload = client.get(
            f"/api/v1/entities/{seed_entity.id}/periods/{seed_fiscal_period.id}/budget_lines"
        ).json()["items"][0]
    elif table == "loans":
        payload = client.get("/api/v1/debt/loans").json()["loans"][0]
    elif table == "debt_timeline":
        payload = client.get("/api/v1/debt/timeline").json()["timeline"][0]
    elif table == "revenue_by_source":
        payload = client.get("/api/v1/budget/enhanced").json()["revenue_by_source"][0][
            "sources"
        ][0]
    else:
        route = {
            "gdp_data": "gdp",
            "poverty_indices": "poverty",
            "economic_indicators": "indicators",
        }[table]
        payload = client.get(f"/api/v1/economic/{route}").json()[0]
    chart_q = payload["qualifications"][PRIMARY[table]]
    verify_q = client.get(
        f"/api/v1/provenance/verify/{table}", params={"record_id": row.id}
    ).json()["qualifications"][PRIMARY[table]]
    assert chart_q == verify_q
    assert chart_q["status"] == "verified"


def test_exact_verification_selector_does_not_return_another_measure(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path
):
    row, *_ = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "economic_indicators",
        tmp_path,
        value=7,
    )
    response = client.get(
        "/api/v1/provenance/verify/economic_indicators",
        params={"measure": "gdp_growth_rate"},
    )
    assert response.json()["reason"] == "no_rows"
    assert response.json()["qualifications"] == {}


def test_independent_ratio_operands_and_precision(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path
):
    from services.figure_qualification import qualify_ratio

    row, doc, evidence, receipt, extraction = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "gdp_data",
        tmp_path,
        value=100,
    )
    denominator = client.get("/api/v1/economic/gdp").json()[0]["qualifications"][
        "gdp_value"
    ]
    observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "debt_timeline",
        tmp_path,
        value=7,
    )
    numerator = client.get("/api/v1/debt/timeline").json()["timeline"][0][
        "qualifications"
    ]["total"]
    assert numerator["receipt_id"] != denominator["receipt_id"]
    good = qualify_ratio(numerator, denominator, 7, 7, 100)
    assert good["status"] == "verified"
    assert qualify_ratio(numerator, denominator, 0, 0, 100)["status"] == "verified"
    wrong_date = {
        **denominator,
        "identity": {**denominator["identity"], "period": "2023"},
    }
    assert (
        qualify_ratio(numerator, wrong_date, 7, 7, 100)["reason"]
        == "ratio_operand_identity_mismatch"
    )
    wrong_checks = {**denominator, "value_checked": False}
    assert qualify_ratio(numerator, wrong_checks, 7, 7, 100)["status"] == "qualified"
    assert qualify_ratio(numerator, denominator, 0, 7, 0)["status"] == "unavailable"
    assert qualify_ratio(numerator, denominator, 8, 7, 100)["status"] == "conflicting"
    assert (
        qualify_ratio(numerator, denominator, 7, "1e24", "1e-24")["status"]
        == "unavailable"
    )


def test_gini_conversion_uses_independent_raw_observation(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path
):
    row, doc, evidence, receipt, extraction = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "poverty_indices",
        tmp_path,
        value=7,
    )
    identity = row_identities("poverty_indices", row)["gini_coefficient"]
    transform = {
        "operation": "divide",
        "factor": "100",
        "rounding": 3,
        "rounding_mode": "ROUND_HALF_UP",
    }
    raw = json.dumps({"gini": 30.55}).encode()
    raw_file = tmp_path / "gini-response.json"
    raw_file.write_bytes(raw)
    parsed = json.loads(raw_file.read_bytes())
    receipt = {
        **receipt,
        "digest": sha256(raw).hexdigest(),
        "byte_size": len(raw),
        "storage_key": str(raw_file),
        "byte_check": {
            "status": "matched",
            "sha256": sha256(raw_file.read_bytes()).hexdigest(),
            "checked_at": "2026-01-01T00:00:01Z",
        },
    }
    locator = {"json_path": "$.gini"}
    receipt["observations"] = [
        {
            "identity": identity.model_dump(),
            "locator": locator,
            "raw_value": str(parsed["gini"]),
            "raw_unit": "percent",
            "transformation": transform,
        }
    ]
    evidence = {
        **evidence,
        "identity": identity.model_dump(),
        "receipt": {"extraction_id": extraction.id, "digest": receipt["digest"]},
        "raw_value": str(parsed["gini"]),
        "raw_unit": "percent",
        "value": "0.306",
        "unit": "coefficient",
        "locator": locator,
        "transformation": transform,
    }
    row.gini_coefficient = Decimal("0.306")
    row.meta = {**row.meta, "source_evidence": [evidence]}
    extraction.extracted_json = {"response_receipt": receipt}
    db_session.commit()
    q = client.get("/api/v1/economic/poverty").json()[0]["qualifications"][
        "gini_coefficient"
    ]
    assert q["status"] == "verified", q
    evidence["transformation"] = {**transform, "rounding_mode": "ROUND_HALF_EVEN"}
    row.meta = {**row.meta, "source_evidence": [evidence]}
    db_session.commit()
    q = client.get("/api/v1/economic/poverty").json()[0]["qualifications"][
        "gini_coefficient"
    ]
    assert (
        q["status"] == "qualified"
        and q["reason"] == "rounding_transformation_not_source_bound"
    )


@pytest.mark.parametrize(
    "url_field,reason",
    [
        ("request_url", "receipt_request_source_mismatch"),
        ("response_url", "receipt_response_source_mismatch"),
    ],
)
def test_wrong_acquisition_publisher_cannot_upgrade(
    client,
    db_session,
    seed_country,
    seed_entity,
    seed_fiscal_period,
    tmp_path,
    url_field,
    reason,
):
    row, doc, evidence, receipt, extraction = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "poverty_indices",
        tmp_path,
        value=7,
    )
    receipt[url_field] = "https://unrelated.example/data"
    extraction.extracted_json = {"response_receipt": dict(receipt)}
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(extraction, "extracted_json")
    db_session.commit()
    q = client.get("/api/v1/economic/poverty").json()[0]["qualifications"][
        "poverty_headcount_rate"
    ]
    assert q["status"] == "conflicting" and q["reason"] == reason


def test_external_web_embed_keeps_quantity_qualified(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path
):
    row, doc, evidence, receipt, extraction = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "revenue_by_source",
        tmp_path,
        value=7,
        kind="web",
    )
    # Same publisher host can bind a complete source-parser receipt.
    assert (
        qualify_rows(db_session, "revenue_by_source", [row])[row.id][
            "amount_billion_kes"
        ]["status"]
        == "verified"
    )
    receipt["request_url"] = "https://dashboard.bolt.host/dashboard"
    extraction.extracted_json = {"response_receipt": dict(receipt)}
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(extraction, "extracted_json")
    db_session.commit()
    response = client.get(
        f"/api/v1/provenance/verify/revenue_by_source?record_id={row.id}"
    ).json()
    q = response["qualifications"]["amount_billion_kes"]
    assert q["status"] == "qualified"
    assert q["reason"] == "embedded_publisher_chain_not_checked"
    assert row.amount_billion_kes == Decimal("7")


@pytest.mark.parametrize(
    "table", ["gdp_data", "economic_indicators", "poverty_indices"]
)
def test_exact_record_selects_county_without_guessing_national(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path, table
):
    row, *_ = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        table,
        tmp_path,
        value=7,
    )
    row.entity_id = seed_entity.id
    db_session.commit()
    response = client.get(f"/api/v1/provenance/verify/{table}?record_id={row.id}")
    assert response.status_code == 200
    q = response.json()["qualifications"][PRIMARY[table]]
    assert q["identity"]["entity_id"] == seed_entity.id
    assert (
        client.get(f"/api/v1/provenance/verify/{table}").json()["reason"] == "no_rows"
    )


def test_unit_conversion_cannot_cross_currency_and_rate_dimensions(
    client, db_session, seed_country, seed_entity, seed_fiscal_period, tmp_path
):
    row, doc, evidence, receipt, extraction = observation(
        db_session,
        seed_country,
        seed_entity,
        seed_fiscal_period,
        "poverty_indices",
        tmp_path,
        value=7,
    )
    evidence.update(raw_value="0.07", raw_unit="KES")
    evidence["transformation"] = {"operation": "multiply", "factor": "100"}
    receipt["observations"][0].update(raw_value="0.07", raw_unit="KES")
    row.meta = {**row.meta, "source_evidence": [evidence]}
    extraction.extracted_json = {"response_receipt": dict(receipt)}
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(extraction, "extracted_json")
    db_session.commit()
    q = client.get("/api/v1/economic/poverty").json()[0]["qualifications"][
        "poverty_headcount_rate"
    ]
    assert q["status"] == "qualified"
    assert q["reason"] == "independent_conversion_operand_not_checked"
