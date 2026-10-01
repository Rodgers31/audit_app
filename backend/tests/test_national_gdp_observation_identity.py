"""#425: identity is reconciled independently of numeric differences.

Real PostgreSQL commit/reopen and public GDP HTTP; source-shaped synthetic
observations only. Contradictory historical evidence requires separate review.
"""
from contextlib import nullcontext
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from models import Country, GDPData, PovertyIndex, PopulationData, SourceDocument
from routers import economic
from seeding.config import SeedingSettings
from seeding.domains import national_gdp as domain
from seeding.types import DomainRunContext
from test_national_gdp_source_creation import pg, country, document, SPECS, snapshot


def run(db, tmp_path, monkeypatch, gdp=17, poverty=None):
    monkeypatch.setattr(domain, "create_http_client", lambda _: nullcontext(None))
    monkeypatch.setattr(
        domain.fetcher, "fetch_national_gdp_kes", lambda *a: {2024: gdp}
    )
    monkeypatch.setattr(domain.fetcher, "fetch_kenya_poverty", lambda *a: poverty or {})
    return domain.run(
        db,
        SeedingSettings(
            storage_path=tmp_path, cache_path=tmp_path, http_cache_enabled=False
        ),
        DomainRunContext(since=None, dry_run=False),
    )


def http(engine):
    app = FastAPI()
    app.include_router(economic.router)

    def dependency():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[economic.get_db] = dependency
    with TestClient(app) as client:
        response = client.get("/api/v1/economic/gdp", params={"year": 2024})
        assert response.status_code == 200, response.text
        return response.json()


def seed(db, gdp_value=17, poverty=False, cited=True):
    db.add(country())
    db.flush()
    gdp_doc = document(SPECS[0], id=100)
    poverty_doc = document(SPECS[1], id=101)
    for doc in (gdp_doc, poverty_doc):
        doc.meta = {
            **doc.meta,
            "publication_date": "2025-05-01",
            "shared": ["preserve"],
        }
    db.add_all([gdp_doc, poverty_doc])
    db.flush()
    db.add(
        GDPData(
            id=400,
            year=2024,
            gdp_value=gdp_value,
            currency="KES",
            source_document_id=100 if cited else None,
            meta={"note": "preserve"},
        )
    )
    if poverty:
        db.add(
            PovertyIndex(
                id=500,
                year=2022,
                poverty_headcount_rate=Decimal("38.6"),
                gini_coefficient=Decimal("0.387"),
                source_document_id=101 if cited else None,
                meta={"note": "preserve"},
            )
        )
    db.commit()


@pytest.mark.parametrize("fetched", [17, 18, 0])
@pytest.mark.parametrize("cited", [False, True])
def test_same_or_changed_value_reconciles_supported_identity_and_http(
    pg, tmp_path, monkeypatch, fetched, cited
):
    with Session(pg) as db:
        seed(db, cited=cited)
        before = snapshot(db)
        result = run(db, tmp_path, monkeypatch, fetched)
        assert (
            result.errors == []
            and result.items_updated == 1
            and result.items_created == 0
        )
        db.commit()
    with Session(pg) as db:
        row = db.get(GDPData, 400)
        assert (row.gdp_value, row.currency, row.source_document_id) == (
            Decimal(fetched),
            "KES",
            100,
        )
        assert row.meta["indicator"] == "NY.GDP.MKTP.CN" and row.meta["year"] == 2024
        assert row.meta["units"] == "KES" and row.meta["note"] == "preserve"
        assert row.confidence == Decimal("0.95")
        assert snapshot(db) == before, "shared source metadata must not be rewritten"
        repeat = run(db, tmp_path, monkeypatch, fetched)
        assert repeat.errors == [] and repeat.items_updated == repeat.items_created == 0
        db.commit()
    body = http(pg)
    assert len(body) == 1 and body[0]["currency"] == "KES"
    assert body[0]["source_document_id"] == 100 and body[0]["gdp_value"] == fetched


@pytest.mark.parametrize("fetched", [17, 18])
@pytest.mark.parametrize(
    "conflict",
    [
        "source",
        "currency",
        "indicator",
        "country",
        "units",
        "year",
        "scope",
        "source_url",
        "metadata",
        "locator",
        "duplicate",
    ],
)
def test_conflicting_gdp_refuses_even_when_value_changes(
    pg, tmp_path, monkeypatch, fetched, conflict
):
    with Session(pg) as db:
        seed(db)
        row = db.get(GDPData, 400)
        if conflict == "source":
            row.source_document_id = 101
        elif conflict == "currency":
            row.currency = "USD"
        elif conflict == "metadata":
            row.meta = ["malformed"]
        elif conflict == "locator":
            row.page_ref = "PDF p. 42"
        elif conflict == "duplicate":
            db.add(
                GDPData(year=2024, gdp_value=17, currency="KES", source_document_id=100)
            )
        else:
            row.meta = {
                conflict: {
                    "indicator": "SP.POP.TOTL",
                    "country": "UGA",
                    "units": "millions",
                    "year": 2023,
                    "scope": "county",
                    "source_url": "https://example.invalid/other",
                }[conflict]
            }
        db.commit()
        before = (
            db.execute(text("SELECT row_to_json(g)::text FROM gdp_data g ORDER BY id"))
            .scalars()
            .all()
        )
        docs = snapshot(db)
        result = run(db, tmp_path, monkeypatch, fetched)
        assert result.errors and result.items_updated == result.items_created == 0
        db.commit()
    with Session(pg) as db:
        assert (
            db.execute(text("SELECT row_to_json(g)::text FROM gdp_data g ORDER BY id"))
            .scalars()
            .all()
            == before
        )
        assert snapshot(db) == docs
    body = http(pg)
    assert body and body[0]["gdp_value"] == 17
    if conflict == "currency":
        assert body[0]["currency"] == "USD"


@pytest.mark.parametrize(
    "values",
    [
        {"headcount": Decimal("38.6"), "gini": Decimal("0.387")},
        {"headcount": Decimal("0")},
        {"gini": Decimal("0")},
    ],
)
@pytest.mark.parametrize("cited", [False, True])
def test_poverty_identity_missing_values_zero_and_retry(
    pg, tmp_path, monkeypatch, values, cited
):
    with Session(pg) as db:
        seed(db, poverty=True, cited=cited)
        result = run(db, tmp_path, monkeypatch, poverty={2022: values})
        assert result.errors == [] and result.items_updated == 2
        db.commit()
    with Session(pg) as db:
        row = db.get(PovertyIndex, 500)
        assert row.source_document_id == 101 and row.meta["note"] == "preserve"
        assert row.poverty_headcount_rate == values.get("headcount")
        assert (
            row.gini_coefficient == values.get("gini")
            and row.extreme_poverty_rate is None
        )
        assert row.meta["indicators"] == ["SI.POV.NAHC", "SI.POV.GINI"]
        repeat = run(db, tmp_path, monkeypatch, poverty={2022: values})
        assert not repeat.errors and repeat.items_updated == repeat.items_created == 0
        db.commit()


@pytest.mark.parametrize(
    "conflict", ["source", "gini_scale", "year", "country_id", "locator"]
)
def test_late_poverty_identity_refusal_rolls_back_gdp_then_corrected_retry(
    pg, tmp_path, monkeypatch, conflict
):
    values = {2022: {"headcount": Decimal("38.6"), "gini": Decimal("0.387")}}
    with Session(pg) as db:
        seed(db, poverty=True)
        row = db.get(PovertyIndex, 500)
        if conflict == "source":
            row.source_document_id = 100
        elif conflict == "locator":
            row.source_page = 42
        else:
            row.meta = {
                conflict: {"gini_scale": "0-100", "year": 2015, "country_id": True}[
                    conflict
                ]
            }
        db.add(GDPData(id=401, year=2025, gdp_value=19, currency="KES"))
        db.add(
            PopulationData(
                id=79, year=2019, total_population=51_202_827, source_document_id=100
            )
        )
        db.commit()
        docs = snapshot(db)
        db.add(country(9, "UGA", "Uganda", "UGX"))
        result = run(db, tmp_path, monkeypatch, 18, values)
        assert result.errors and result.items_updated == result.items_created == 0
        db.commit()
    with Session(pg) as db:
        assert db.get(GDPData, 400).gdp_value == 17 and db.get(GDPData, 401) is not None
        assert db.get(Country, 9).iso_code == "UGA" and snapshot(db) == docs
        assert db.get(PopulationData, 79).total_population == 51_202_827
        row = db.get(PovertyIndex, 500)
        # Explicit correction of newly owned fixture; no production relabel.
        row.source_document_id = 101
        row.meta = {}
        row.source_page = None
        db.commit()
        result = run(db, tmp_path, monkeypatch, 18, values)
        assert not result.errors and result.items_updated == 2
        db.commit()
    with Session(pg) as db:
        assert db.get(GDPData, 400).gdp_value == 18 and db.get(GDPData, 401) is None
        assert db.get(PovertyIndex, 500).source_document_id == 101


def test_annual_writer_never_relabels_quarterly_gdp(pg, tmp_path, monkeypatch):
    with Session(pg) as db:
        db.add(country())
        db.flush()
        db.add(GDPData(id=400, year=2024, quarter="Q1", gdp_value=4, currency="USD"))
        db.commit()
        result = run(db, tmp_path, monkeypatch)
        assert not result.errors and result.items_created == 1
        db.commit()
    with Session(pg) as db:
        q = db.get(GDPData, 400)
        assert (q.quarter, q.gdp_value, q.currency, q.source_document_id) == (
            "Q1",
            Decimal(4),
            "USD",
            None,
        )
        annual = db.scalar(select(GDPData).where(GDPData.quarter.is_(None)))
        assert annual.gdp_value == 17 and annual.currency == "KES"


@pytest.mark.parametrize(
    "kind,value",
    [
        ("gdp", True),
        ("gdp", Decimal("NaN")),
        ("gdp", Decimal("Infinity")),
        ("gdp", -1),
        ("gdp", None),
        ("headcount", True),
        ("headcount", Decimal("NaN")),
        ("headcount", 101),
        ("gini", Decimal("Infinity")),
        ("gini", Decimal("-0.1")),
        ("gini", Decimal("1.01")),
    ],
)
def test_invalid_measure_is_atomic_refusal(pg, tmp_path, monkeypatch, kind, value):
    with Session(pg) as db:
        seed(db, poverty=True)
        docs = snapshot(db)
        result = run(
            db,
            tmp_path,
            monkeypatch,
            value if kind == "gdp" else 18,
            {2022: {kind: value}} if kind != "gdp" else {},
        )
        assert result.errors and result.items_created == result.items_updated == 0
        db.commit()
    with Session(pg) as db:
        assert db.get(GDPData, 400).gdp_value == 17 and snapshot(db) == docs
        assert db.get(PovertyIndex, 500).poverty_headcount_rate == Decimal("38.6")


@pytest.mark.parametrize("vintage", ["2025-05-01", "2024-12-31"])
def test_observation_vintage_must_agree_with_cited_source(
    pg, tmp_path, monkeypatch, vintage
):
    with Session(pg) as db:
        seed(db)
        row = db.get(GDPData, 400)
        row.meta = {"publication_date": vintage}
        db.commit()
        docs = snapshot(db)
        result = run(db, tmp_path, monkeypatch, 18)
        assert bool(result.errors) == (vintage != "2025-05-01")
        db.commit()
    with Session(pg) as db:
        assert snapshot(db) == docs
        assert db.get(GDPData, 400).meta["publication_date"] == vintage
        assert db.get(GDPData, 400).gdp_value == (18 if vintage == "2025-05-01" else 17)


def test_precision_retry_and_publication_withholding_are_preserved(
    pg, tmp_path, monkeypatch
):
    values = {2022: {"headcount": Decimal("38.625"), "gini": Decimal("0.3875")}}
    with Session(pg) as db:
        seed(db, poverty=True)
        for row in (db.get(GDPData, 400), db.get(PovertyIndex, 500)):
            row.publishable = False
            row.quarantine_reason = "synthetic_review_required"
        db.commit()
        result = run(db, tmp_path, monkeypatch, poverty=values)
        assert not result.errors and result.items_updated == 2
        db.commit()
    with Session(pg) as db:
        p = db.get(PovertyIndex, 500)
        assert p.poverty_headcount_rate == Decimal(
            "38.63"
        ) and p.gini_coefficient == Decimal("0.388")
        for row in (db.get(GDPData, 400), p):
            assert (
                not row.publishable
                and row.quarantine_reason == "synthetic_review_required"
            )
        result = run(db, tmp_path, monkeypatch, poverty=values)
        assert not result.errors and result.items_updated == 0
        db.commit()


def test_late_database_failure_undoes_new_sources_and_caller_can_commit_retry(
    pg, tmp_path, monkeypatch
):
    from sqlalchemy import event

    with Session(pg) as db:
        db.add(country())
        db.commit()
        db.add(country(9, "UGA", "Uganda", "UGX"))

        def reject(conn, cursor, statement, params, context, executemany):
            if statement.startswith("INSERT INTO poverty_indices"):
                raise RuntimeError("synthetic late persistence failure")

        event.listen(pg, "before_cursor_execute", reject)
        try:
            result = run(
                db, tmp_path, monkeypatch, poverty={2022: {"headcount": Decimal("0")}}
            )
            assert result.errors and result.items_created == result.items_updated == 0
            db.commit()
        finally:
            event.remove(pg, "before_cursor_execute", reject)
    with Session(pg) as db:
        assert db.get(Country, 9) is not None
        assert (
            db.query(GDPData).count()
            == db.query(PovertyIndex).count()
            == db.query(SourceDocument).count()
            == 0
        )
        result = run(
            db, tmp_path, monkeypatch, poverty={2022: {"headcount": Decimal("0")}}
        )
        assert not result.errors and result.items_created == 2
        db.commit()
    with Session(pg) as db:
        assert db.scalar(select(PovertyIndex)).poverty_headcount_rate == 0


def test_successful_run_does_not_commit_callers_outer_transaction(
    pg, tmp_path, monkeypatch
):
    with Session(pg) as db:
        seed(db)
        result = run(db, tmp_path, monkeypatch, 18)
        assert not result.errors and result.items_updated == 1
        db.rollback()
    with Session(pg) as db:
        assert db.get(GDPData, 400).gdp_value == 17


@pytest.mark.parametrize(
    "key,value",
    [
        ("covers_through_year", 2023),
        ("covers_through_year", True),
        ("covers_through_year", "2024"),
        ("covers_through_year", 2024.0),
        ("publication_date", "2023-12-31"),
        ("publication_date", "malformed"),
    ],
)
@pytest.mark.parametrize("new_row", [False, True])
def test_source_vintage_must_support_existing_or_new_observation(
    pg, tmp_path, monkeypatch, key, value, new_row
):
    with Session(pg) as db:
        seed(db)
        doc = db.get(SourceDocument, 100)
        doc.meta = {**doc.meta, key: value}
        if new_row:
            db.delete(db.get(GDPData, 400))
        db.commit()
        before = snapshot(db)
        result = run(db, tmp_path, monkeypatch, 18)
        assert result.errors and result.items_created == result.items_updated == 0
        db.commit()
    with Session(pg) as db:
        assert snapshot(db) == before
        assert db.query(GDPData).count() == (0 if new_row else 1)
        if not new_row:
            assert db.get(GDPData, 400).gdp_value == 17


@pytest.mark.parametrize("basis", ["modelled", "projected"])
def test_fetched_actual_does_not_overwrite_another_basis(
    pg, tmp_path, monkeypatch, basis
):
    from models import FigureBasis

    with Session(pg) as db:
        seed(db)
        row = db.get(GDPData, 400)
        row.basis = FigureBasis(basis)
        db.commit()
        result = run(db, tmp_path, monkeypatch, 18)
        assert result.errors and result.items_updated == 0
        db.commit()
    with Session(pg) as db:
        row = db.get(GDPData, 400)
        assert row.gdp_value == 17 and row.basis == FigureBasis(basis)


@pytest.mark.parametrize(
    "declaration",
    [
        {"forecast": True},
        {"is_projection": True},
        {"is_estimate": True},
        {"data_quality": "estimated"},
    ],
)
def test_fetched_actual_refuses_contradictory_metadata_basis(
    pg, tmp_path, monkeypatch, declaration
):
    with Session(pg) as db:
        seed(db)
        row = db.get(GDPData, 400)
        row.meta = declaration
        db.commit()
        result = run(db, tmp_path, monkeypatch, 18)
        assert result.errors and result.items_updated == 0
        db.commit()
    with Session(pg) as db:
        assert (
            db.get(GDPData, 400).gdp_value == 17
            and db.get(GDPData, 400).meta == declaration
        )


@pytest.mark.parametrize("poverty", [False, True])
def test_coherent_vintage_and_actual_basis_preserve_optional_declarations(
    pg, tmp_path, monkeypatch, poverty
):
    from models import FigureBasis

    with Session(pg) as db:
        seed(db, poverty=poverty)
        doc = db.get(SourceDocument, 101 if poverty else 100)
        doc.meta = {**doc.meta, "covers_through_year": 2024}
        row = db.get(PovertyIndex, 500) if poverty else db.get(GDPData, 400)
        row.basis = FigureBasis.ACTUAL
        row.meta = {
            "basis": "actual",
            "forecast": False,
            "is_projection": False,
            "publication_date": "2025-05-01",
            "covers_through_year": 2024,
            "note": "preserve",
        }
        db.commit()
        docs = snapshot(db)
        values = (
            {2022: {"headcount": Decimal("38.6"), "gini": Decimal("0.387")}}
            if poverty
            else {}
        )
        result = run(db, tmp_path, monkeypatch, 18, values)
        assert not result.errors
        db.commit()
    with Session(pg) as db:
        row = db.get(PovertyIndex, 500) if poverty else db.get(GDPData, 400)
        assert row.basis == FigureBasis.ACTUAL and row.meta["is_projection"] is False
        assert row.meta["publication_date"] == "2025-05-01" and snapshot(db) == docs


def test_observation_coverage_type_cannot_borrow_numeric_equality(
    pg, tmp_path, monkeypatch
):
    with Session(pg) as db:
        seed(db)
        doc = db.get(SourceDocument, 100)
        doc.meta = {**doc.meta, "covers_through_year": 2024}
        row = db.get(GDPData, 400)
        row.meta = {"covers_through_year": 2024.0}
        db.commit()
        result = run(db, tmp_path, monkeypatch, 18)
        assert result.errors and result.items_updated == 0
        db.commit()
    with Session(pg) as db:
        assert db.get(GDPData, 400).gdp_value == 17
