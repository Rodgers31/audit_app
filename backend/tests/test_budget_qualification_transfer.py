"""Budget qualification evidence survives bounded context selection.

Run without app startup: pytest --confcutdir=tests tests/test_budget_qualification_transfer.py
The byte estimate replays captured SELECTs against a newly owned SQLite file;
it measures selected UTF-8 values, not PostgreSQL wire bytes or provider egress.
"""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import socket
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB, dialect
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from models import (
    BudgetLine, Country, DocumentType, Entity, EntityType, Extraction,
    FiscalPeriod, SourceDocument,
)
from services.figure_qualification import qualify_rows


@compiles(JSONB, "sqlite")
def _sqlite_jsonb(element, compiler, **kwargs):
    return "JSON"


IDENTITY = {
    "measure": "allocated_amount", "entity_id": 1, "geography": "Baringo County",
    "period": "FY2024/25", "unit": "KES", "basis": "actual",
    "dimensions": {"category": "Total", "subcategory": None, "line_type": "total"},
}
LARGE = "unrelated-" * 8192


@pytest.fixture
def context(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Qualification fixture must not acquire remote bytes")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    engine = create_engine(f"sqlite:///{tmp_path / 'qualification.sqlite'}")
    for model in (Country, Entity, FiscalPeriod, SourceDocument, Extraction, BudgetLine):
        model.__table__.create(engine)
    retained = json.dumps({"identity": IDENTITY, "value": "100"}, sort_keys=True).encode()
    retained_path = tmp_path / "retained.json"
    retained_path.write_bytes(retained)
    digest = sha256(retained_path.read_bytes()).hexdigest()
    receipt = {
        "source_kind": "api", "status": 200, "content_type": "application/json",
        "request_url": "https://cob.go.ke/fixture", "acquired_at": "2026-01-01T00:00:00Z",
        "parser_version": "fixture-v1", "digest": digest, "byte_size": len(retained),
        "storage_key": str(retained_path),
        "byte_check": {"status": "matched", "sha256": digest,
                       "checked_at": "2026-01-01T00:00:01Z"},
        "observations": [{"identity": deepcopy(IDENTITY), "raw_value": "100",
                          "raw_unit": "KES", "locator": {"json_path": "$.value"}}],
    }
    evidence = {
        "version": 1, "source_kind": "api", "identity": deepcopy(IDENTITY),
        "receipt": {"extraction_id": 1, "digest": digest, "source_document_id": 1},
        "raw_value": "100", "raw_unit": "KES", "value": "100", "unit": "KES",
        "locator": {"json_path": "$.value"}, "transformation": {"operation": "identity"},
        "checks": dict.fromkeys(("identity", "value", "transport", "bytes", "locator"), True),
        "reconciliation": {"status": "matched"},
    }
    with Session(engine) as db:
        db.add_all([
            Country(id=1, iso_code="KEN", name="Kenya", currency="KES", timezone="Africa/Nairobi",
                    default_locale="en", meta={"unused": LARGE}),
            Country(id=2, iso_code="UGA", name="Uganda", currency="UGX", timezone="Africa/Kampala",
                    default_locale="en", meta={"unused": LARGE}),
            Entity(id=1, country_id=1, type=EntityType.COUNTY, canonical_name="Baringo County",
                   slug="baringo", meta={"unused": LARGE}, alt_names=[LARGE]),
            FiscalPeriod(id=1, country_id=1, label="FY2024/25", start_date=datetime(2024, 7, 1),
                         end_date=datetime(2025, 6, 30)),
        ])
        for doc_id in (1, 2):
            db.add(SourceDocument(id=doc_id, country_id=1, publisher="Controller of Budget",
                                  title=LARGE, url="https://cob.go.ke/fixture", file_path=LARGE,
                                  fetch_date=datetime(2026, 1, 1), doc_type=DocumentType.BUDGET,
                                  content_type="application/json", meta={"unused": LARGE}))
        db.add(Extraction(id=1, source_document_id=1, extractor="http-response-v1",
                          extracted_json={"response_receipt": receipt, "unused": LARGE}))
        db.add(BudgetLine(id=1, entity_id=1, period_id=1, category="Total", line_type="total",
                          allocated_amount=100, actual_spent=None, committed_amount=None,
                          currency="KES", source_document_id=1,
                          provenance=[{"source_evidence": [evidence]}]))
        db.commit()
    try:
        yield engine, evidence, receipt, digest
    finally:
        engine.dispose()


def expected(digest, status="verified", reason="retained_source_and_observation_matched", *, source_id=1, kind="api"):
    qualified = {
        "status": status, "reason": reason, "source_kind": kind,
        "identity": deepcopy(IDENTITY), "source_document_id": source_id,
        "source_url": "https://cob.go.ke/fixture", "publisher": "Controller of Budget",
        "receipt_id": None, "digest": None, "locator": None,
        "document_bytes_checked": False, "value_checked": False,
    }
    if status == "verified":
        qualified.update(receipt_id=1, digest=digest, locator={"json_path": "$.value"},
                         document_bytes_checked=True, value_checked=True)
    return qualified


CASES = [
    ("valid", "verified", "retained_source_and_observation_matched"),
    ("root-null", "qualified", "receipt_missing"),
    ("root-list", "qualified", "receipt_missing"),
    ("root-string", "qualified", "receipt_missing"),
    ("root-number", "qualified", "receipt_missing"),
    ("root-bool", "qualified", "receipt_missing"),
    ("root-empty", "qualified", "receipt_missing"),
    ("payload-null", "qualified", "receipt_missing"),
    ("payload-list", "qualified", "receipt_missing"),
    ("payload-string", "qualified", "receipt_missing"),
    ("payload-number", "qualified", "receipt_missing"),
    ("payload-empty", "qualified", "invalid_source_kind"),
    ("missing-extraction", "qualified", "receipt_missing"),
    ("wrong-extractor", "qualified", "receipt_missing"),
    ("modelled-origin", "modelled", "explicit_model_origin"),
    ("projected-origin", "projected", "explicit_projection"),
    ("source-classification", "modelled", "explicit_model_origin"),
    ("estimate-classification", "modelled", "explicit_model_origin"),
    ("malformed-meta-list", "verified", "retained_source_and_observation_matched"),
    ("malformed-meta-string", "verified", "retained_source_and_observation_matched"),
    ("country", "conflicting", "source_country_mismatch"),
    ("entity-country", "conflicting", "source_country_mismatch"),
    ("missing-country", "conflicting", "source_country_mismatch"),
    ("missing-period", "conflicting", "observation_identity_mismatch"),
    ("receipt-association", "conflicting", "receipt_source_document_mismatch"),
    ("mixed-sources", "conflicting", "receipt_source_document_mismatch"),
    ("ambiguity", "conflicting", "multiple_observation_evidence"),
    ("period", "conflicting", "observation_identity_mismatch"),
    ("transport", "qualified", "unsuccessful_response"),
    ("byte-check", "conflicting", "retained_bytes_not_matched"),
    ("observation", "conflicting", "receipt_observation_mismatch"),
    ("many-observations", "verified", "retained_source_and_observation_matched"),
]


@pytest.mark.parametrize("case,status,reason", CASES)
def test_complete_budget_qualification_matches_pre_projection_contract(context, case, status, reason):
    engine, evidence, receipt, digest = context
    with Session(engine) as db:
        doc, entity, extraction, row = (db.get(model, 1) for model in (SourceDocument, Entity, Extraction, BudgetLine))
        if case.startswith("root-"):
            extraction.extracted_json = {"root-null": None, "root-list": [{"response_receipt": receipt}],
                                         "root-string": json.dumps({"response_receipt": receipt}),
                                         "root-number": 1, "root-bool": True, "root-empty": {}}[case]
        elif case.startswith("payload-"):
            extraction.extracted_json = {"response_receipt": {"payload-null": None, "payload-list": [receipt],
                                                               "payload-string": json.dumps(receipt),
                                                               "payload-number": 1, "payload-empty": {}}[case]}
        elif case == "missing-extraction":
            db.delete(extraction)
        elif case == "wrong-extractor":
            extraction.extractor = "ordinary-parser"
        elif case == "modelled-origin":
            doc.meta = {"origin": "app_model", "unused": LARGE}
        elif case == "projected-origin":
            doc.meta = {"origin": "projection", "unused": LARGE}
        elif case == "source-classification":
            doc.meta = {"source_classification": "test_fixture", "unused": LARGE}
        elif case == "estimate-classification":
            doc.meta = {"source_classification": "modelled_estimate", "unused": LARGE}
        elif case == "malformed-meta-list":
            doc.meta = [{"origin": "app_model"}]
        elif case == "malformed-meta-string":
            doc.meta = json.dumps({"origin": "app_model"})
        elif case == "country":
            doc.country_id = 2
        elif case == "entity-country":
            entity.country_id = 2
        elif case == "missing-country":
            db.query(Country).filter(Country.id == 1).delete(synchronize_session=False)
        elif case == "missing-period":
            db.query(FiscalPeriod).filter(FiscalPeriod.id == 1).delete(synchronize_session=False)
        elif case == "receipt-association":
            extraction.source_document_id = 2
        elif case == "mixed-sources":
            evidence["receipt"]["source_document_id"] = 2
        elif case == "period":
            evidence["identity"]["period"] = "FY2023/24"
        elif case in ("transport", "byte-check", "observation", "many-observations"):
            if case == "transport":
                receipt["status"] = 404
            elif case == "byte-check":
                receipt["byte_check"]["status"] = "mismatch"
            elif case == "observation":
                receipt["observations"][0]["raw_value"] = "101"
            else:
                receipt["observations"] = [{"locator": {"json_path": f"$.other{n}"}} for n in range(120)] + receipt["observations"]
            extraction.extracted_json = {"response_receipt": receipt, "unused": LARGE}
        row.provenance = [{"source_evidence": [evidence] * (2 if case == "ambiguity" else 1)}]
        db.commit()
    with Session(engine) as db:
        row = db.get(BudgetLine, 1)
        output = qualify_rows(db, "budget_lines", [row])
    q = expected(digest, status, reason, source_id=2 if case == "mixed-sources" else 1)
    if case == "missing-period":
        q["identity"]["period"] = "period:1"
    if case == "ambiguity":
        q["source_kind"] = "unknown"
    if reason == "receipt_missing" or case in ("payload-empty", "transport", "byte-check", "observation"):
        q["receipt_id"] = 1
    if case in ("transport", "byte-check", "observation"):
        q["digest"] = digest
    full = {"allocated_amount": q}
    for measure in ("actual_spent", "committed_amount"):
        full[measure] = {**expected(digest, "unavailable", "value_not_reported", kind="unknown"),
                         "identity": {**q["identity"], "measure": measure}}
    assert output == {1: full}


def test_budget_qualification_does_not_transfer_unrelated_context_payloads(context):
    engine, _, _, _ = context
    statements, clauses = [], []

    def capture(conn, cursor, sql, params, execution_context, executemany):
        if sql.lstrip().upper().startswith("SELECT"):
            statements.append((sql, params))

    def compile_clause(conn, clause, multiparams, params, options):
        clauses.append(str(clause.compile(dialect=dialect())))

    with Session(engine) as db:
        row = db.get(BudgetLine, 1)
        event.listen(engine, "before_cursor_execute", capture)
        event.listen(engine, "before_execute", compile_clause)
        try:
            output = qualify_rows(db, "budget_lines", [row])
        finally:
            event.remove(engine, "before_cursor_execute", capture)
            event.remove(engine, "before_execute", compile_clause)
    assert output[1]["allocated_amount"]["status"] == "verified"
    assert len(statements) == 5  # Includes all context, with no lazy SELECTs.
    selected = []
    raw = engine.raw_connection()
    try:
        for sql, params in statements:
            cursor = raw.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            selected.append(([d[0] for d in cursor.description], sum(len(str(v).encode()) for r in rows for v in r if v is not None)))
            cursor.close()
    finally:
        raw.close()
    byte_count = sum(size for _, size in selected)
    print(f"qualification context selected UTF-8 bytes={byte_count}; columns={[cols for cols, _ in selected]}")
    assert byte_count < 100_000, f"Unrelated context payloads transferred: {byte_count} bytes"
    extraction_sql = next(sql for sql in clauses if "FROM extractions" in sql)
    assert "extractions.extracted_json[" in extraction_sql
    assert "extractions.extracted_json AS" not in extraction_sql
    assert [len(cols) for cols, _ in selected] == [6, 4, 2, 2, 4]


@pytest.mark.parametrize("table", ["loans", "gdp_data", "economic_indicators", "poverty_indices", "debt_timeline", "revenue_by_source"])
def test_other_qualification_tables_keep_full_publication_context(context, table):
    engine, evidence, _, _ = context
    row = SimpleNamespace(
        id=7, source_document_id=1, entity_id=1, basis=None,
        meta={"source_evidence": [evidence]},
        provenance=[{"as_at": "2024-01-01", "source_evidence": [evidence]}],
        currency="KES", year=2024, quarter=None, gdp_value=100, gdp_growth_rate=None,
        outstanding=100, principal=100, interest_rate=None, lender="Official creditor", debt_category=None,
        indicator_type="unemployment_rate", indicator_date=datetime(2024, 1, 1), value=100, unit="percent",
        poverty_headcount_rate=100, extreme_poverty_rate=None, gini_coefficient=None,
        external=100, domestic=0, total=100, gdp=100, gdp_ratio=100,
        fiscal_year="FY2024/25", revenue_type="PAYE", category="tax", amount_billion_kes=100,
        share_of_total_pct=None, target_billion_kes=None, performance_pct=None, yoy_growth_pct=None,
    )
    selected_models = []

    class QueryRecorder:
        def __init__(self, db):
            self.db = db

        def query(self, *fields):
            selected_models.append(fields)
            return self.db.query(*fields)

    with Session(engine) as db:
        output = qualify_rows(QueryRecorder(db), table, [row])
    assert output[7]
    assert selected_models == [(SourceDocument,), (Entity,), (Country,), (Extraction,)]
