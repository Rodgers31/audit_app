"""Run the same HTTP contracts against persisted PostgreSQL Numeric/JSONB rows."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from models import Base
from tests.test_financial_absence_publication import (
    test_budget_line_readers_preserve_absence_and_sourced_zero,
    test_fiscal_history_does_not_invent_missing_money_or_ratio,
    test_county_debt_http_preserves_outstanding_zero,
    test_sources_sql_count_is_measured,
    test_final_comprehensive_ratio_requires_same_source_stock_day,
    test_fiscal_unknown_metadata_shape_does_not_destroy_sourced_amounts,
    test_unknown_fiscal_unit_is_withheld_with_reason,
)


@pytest.fixture(scope="module")
def financial_pg_engine():
    raw = os.environ.get("FINANCIAL_ABSENCE_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip(
            "Set FINANCIAL_ABSENCE_TEST_POSTGRES_URL to an owned loopback database"
        )
    url = make_url(raw)
    assert url.host in ("127.0.0.1", "localhost")
    assert url.get_backend_name() == "postgresql"
    schema = "round8_s4_" + uuid.uuid4().hex
    connect_args = {
        "hostaddr": "127.0.0.1",
        "sslmode": "disable",
        "gssencmode": "disable",
    }
    env_guard = pytest.MonkeyPatch()
    for key in (
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGHOSTADDR",
        "PGSSLMODE",
        "PGGSSENCMODE",
        "PGOPTIONS",
        "PGTARGETSESSIONATTRS",
    ):
        env_guard.delenv(key, raising=False)
    control = create_engine(url, connect_args=connect_args)
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url, connect_args={**connect_args, "options": f"-csearch_path={schema}"}
    )
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()
        env_guard.undo()


@pytest.fixture
def db_session(financial_pg_engine):
    with financial_pg_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(connection)
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.mark.parametrize(
    "level,expected",
    [
        ("0", 0),
        ("12", 12e9),
        ("-", None),
        ("NaN", None),
        (True, None),
        ("0,0", None),
        ("1,2", None),
    ],
)
def test_parser_transport_persists_explicit_gcp_levels(
    client, db_session, seed_country, tmp_path, monkeypatch, level, expected
):
    import asyncio
    import io
    import builtins
    from types import SimpleNamespace
    from etl.knbs_parser import KNBSParser
    from etl.kenya_pipeline import KenyaDataPipeline
    from etl.database_loader import DatabaseLoader
    from models import GDPData, Entity

    # Synthetic table, transport bytes and publisher, never an official amount.
    data = {"gdp_data": []}
    KNBSParser()._extract_gdp_from_table(
        [["Year", "GDP"], ["2024", level]], data, {"year": 2024, "source_page": 42}
    )
    loader = DatabaseLoader.__new__(DatabaseLoader)
    loader.engine = db_session.get_bind()
    loader.SessionLocal = lambda: Session(db_session.connection())
    pipeline = KenyaDataPipeline.__new__(KenyaDataPipeline)
    pipeline.knbs_ca_bundle = None
    pipeline.kenya_sources = {}
    pipeline.processed_manifest = {}
    pipeline.storage_path = tmp_path
    pipeline._ssl_verify_for = lambda *args: True
    pipeline._maybe_upload_to_s3 = lambda *args: None
    pipeline._save_manifest = lambda: None
    response = SimpleNamespace(
        content=b"%PDF-synthetic-GCP-fixture",
        headers={"content-type": "application/pdf"},
        raise_for_status=lambda: None,
    )
    pipeline.http = SimpleNamespace(get=lambda *args, **kwargs: response)
    pipeline.extractor = SimpleNamespace(
        extract_with_fallback=lambda *args: {"confidence": 1}
    )
    pipeline.knbs_parser = SimpleNamespace(
        counties=["Nairobi"], parse_document=lambda *args: data
    )
    pipeline.db_loader = loader
    pipeline.data_validator = SimpleNamespace(
        validate_budget_data=lambda *args: pytest.fail("Unexpected budget validation")
    )
    doc = {
        "url": "https://example.invalid/synthetic-gcp.pdf",
        "title": "Synthetic KNBS-shaped GCP fixture",
        "source": "KNBS",
        "source_key": "knbs",
        "doc_type": "economic",
        "year": 2024,
        "county": "Nairobi",
    }
    # Avoid document byte writes; all parser/transport/loader monetary code is real.
    with monkeypatch.context() as m:
        m.setattr(builtins, "open", lambda *args, **kwargs: io.BytesIO())
        result = asyncio.run(pipeline.download_and_process_document(dict(doc)))
    assert result.get("document_id") is not None, result
    rows = db_session.query(GDPData).all()
    if expected is None:
        assert rows == []
    else:
        assert len(rows) == 1
        row = rows[0]
        assert float(row.gdp_value) == expected
        assert row.currency == "KES" and row.year == 2024
        assert row.source_page == 42
        entity = db_session.get(Entity, row.entity_id)
        assert entity.canonical_name == "Nairobi County"
        response = client.get(
            f"/api/v1/economic/gdp?entity_id={row.entity_id}&year=2024"
        )
        assert response.status_code == 200, response.text
        assert response.json()[0]["gdp_value"] == expected
        assert response.json()[0]["source_document_id"] == row.source_document_id
        # Replay the real loader on identical transported observation.
        asyncio.run(
            loader._load_gdp_item(
                db_session,
                {
                    "gdp_value": expected,
                    "year": 2024,
                    "entity": {"canonical_name": "Nairobi County", "type": "COUNTY"},
                },
                row.source_document_id,
                seed_country.id,
            )
        )
        assert db_session.query(GDPData).count() == 1


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        (True, None),
        (False, None),
        (-1, None),
        ("-1", None),
        ("NaN", None),
        ("Infinity", None),
        ("bad", None),
        ([], None),
        ({}, None),
        ("0", 0),
        (0, 0),
        (12, 12),
    ],
)
def test_gdp_loader_rejects_hostile_levels_and_preserves_zero(
    client, db_session, seed_entity, seed_source_doc, value, expected
):
    import asyncio
    from etl.database_loader import DatabaseLoader
    from models import GDPData

    loader = DatabaseLoader.__new__(DatabaseLoader)
    loader.engine = db_session.get_bind()
    loader.SessionLocal = lambda: Session(db_session.connection())
    asyncio.run(
        loader._load_gdp_item(
            db_session,
            {
                "gdp_value": value,
                "year": 2024,
                "entity": {
                    "canonical_name": seed_entity.canonical_name,
                    "type": "COUNTY",
                },
            },
            seed_source_doc.id,
            seed_entity.country_id,
        )
    )
    rows = db_session.query(GDPData).all()
    if expected is None:
        assert rows == []
    else:
        assert len(rows) == 1 and float(rows[0].gdp_value) == expected
        response = client.get(
            f"/api/v1/economic/gdp?entity_id={rows[0].entity_id}&year=2024"
        )
        assert (
            response.status_code == 200 and response.json()[0]["gdp_value"] == expected
        )


@pytest.mark.parametrize(
    "currency,day,amount",
    [("KES", "2025-06-30", 0), ("KES", None, 20), ("USD", "2025-06-30", 20)],
)
def test_comprehensive_http_reader_capture(
    client,
    db_session,
    seed_entity,
    seed_fiscal_period,
    seed_source_doc,
    currency,
    day,
    amount,
):
    import json
    from pathlib import Path
    from models import BudgetLine, Loan, DebtCategory, FigureBasis
    from datetime import datetime

    seed_source_doc.publisher = "Synthetic County Treasury"
    seed_source_doc.title = "Synthetic debt and budget source-shaped control"
    seed_source_doc.url = "https://example.invalid/synthetic-account.pdf"
    db_session.add(
        BudgetLine(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            category="Total",
            allocated_amount=100,
            actual_spent=50,
            currency="KES",
            page_ref="p.42",
            basis=FigureBasis.ACTUAL,
            source_document_id=seed_source_doc.id,
        )
    )
    db_session.add(
        Loan(
            entity_id=seed_entity.id,
            lender="Synthetic Bank",
            principal=100,
            outstanding=amount,
            currency=currency,
            source_document_id=seed_source_doc.id,
            issue_date=datetime(2020, 1, 1),
            debt_category=DebtCategory.OTHER,
            basis=FigureBasis.ACTUAL,
            provenance={"as_at": day} if day else {},
            page_ref="p.42",
        )
    )
    db_session.flush()
    response = client.get("/api/v1/counties/001/comprehensive")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["debt"]["total_debt"] == (amount if currency == "KES" else None)
    assert body["debt"]["debt_to_budget_ratio"] == (0 if amount == 0 else None)
    target = os.environ.get("FINANCIAL_ABSENCE_HTTP_CAPTURE_DIR")
    if target:
        Path(
            target,
            f'ROUND8_SESSION_4_HTTP_{currency}_{"dated" if day else "undated"}.json',
        ).write_text(json.dumps(body, indent=2))
