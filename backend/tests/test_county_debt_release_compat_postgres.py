"""County release reads on owned predecessor, partial and adopted schemas."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError, InternalError
from sqlalchemy.orm import Session

from models import Base, CountyDebtInstrument, CountyDebtObservation, DebtCategory
from services.county_debt import county_debt_rows
from services.financial_publication import county_debt_summary
from test_county_instrument_identity_postgres import seed, legacy, write


@pytest.fixture
def release_pg():
    raw = os.environ.get("COUNTY_RELEASE_TEST_URL")
    if not raw:
        pytest.skip("Requires owned synthetic loopback PostgreSQL")
    url = make_url(raw)
    assert url.host == "127.0.0.1" and url.database.startswith("r10_county_release_")
    assert not any(
        os.environ.get(k) for k in ("PGSERVICE", "PGSERVICEFILE", "PGOPTIONS")
    )
    control = create_engine(url)
    schema = "county_release_" + uuid.uuid4().hex
    with control.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        # Preserve the established legacy ORM without introducing either new table.
        Base.metadata.create_all(
            engine,
            tables=[
                t
                for t in Base.metadata.sorted_tables
                if t.name not in ("county_debt_instruments", "county_debt_observations")
            ],
        )
        with Session(engine) as db:
            seed(db)
        yield engine
    finally:
        engine.dispose()
        with control.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            assert (
                conn.execute(
                    text("SELECT count(*) FROM pg_namespace WHERE nspname=:s"),
                    {"s": schema},
                ).scalar()
                == 0
            )
        control.dispose()


@pytest.fixture
def release_client(release_pg, monkeypatch):
    import main, database
    from fastapi.testclient import TestClient
    from config.settings import Settings

    assert not main.AUTO_SEEDER_ENABLED and not main._WARMUP_ENABLED
    assert Settings(_env_file=None).REDIS_URL == ""

    def get_db():
        with Session(release_pg) as db:
            yield db

    monkeypatch.setattr(main, "get_db", get_db)
    main.app.dependency_overrides[database.get_db] = get_db
    client = TestClient(main.app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()
        main.app.dependency_overrides.pop(database.get_db, None)
        main.clear_all_caches()


def county_http(client):
    import main

    responses = []
    for path in (
        "/api/v1/counties",
        "/api/v1/counties/code:001",
        "/api/v1/counties/code:001/comprehensive",
        "/api/v1/counties/code:001/debt",
    ):
        main.clear_all_caches()
        response = client.get(path)
        body = response.json()
        if response.status_code == 200:
            body = (
                body[0]
                if isinstance(body, list)
                else body["debt"]
                if path.endswith("/comprehensive")
                else body
            )
        responses.append((path, response.status_code, body))
    return responses


def test_predecessor_preserves_sourced_legacy_and_pending_bills(
    release_pg, release_client
):
    with Session(release_pg) as db:
        db.add(legacy(amount=20))
        bill = legacy(amount=7)
        bill.lender = "Owned arrears account"
        bill.debt_category = DebtCategory.PENDING_BILLS
        bill.provenance = {
            "category": "county",
            "publication": "cob_cbirr_year_end",
            "as_at": "2025-06-30",
            "source_url": "https://example.invalid/county.pdf",
            "table": "Owned synthetic payables table",
        }
        db.add(bill)
        db.commit()
        rows = county_debt_rows(db, [1])
        assert len(rows) == 2
        assert county_debt_summary(rows)["total_debt"] == 20
        from services.publication_gate import county_pending_bills

        assert county_pending_bills(rows) == 7
    for path, status, body in county_http(release_client):
        assert status == 200, (path, body)
        assert body["total_debt"] == 20, (path, body)
        assert body["pending_bills"] == 7, (path, body)


@pytest.mark.parametrize(
    "missing", ["county_debt_instruments", "county_debt_observations"]
)
def test_partial_schema_is_explicit_failure(release_pg, release_client, missing):
    Base.metadata.create_all(release_pg)
    with release_pg.begin() as conn:
        conn.execute(text(f"DROP TABLE {missing} CASCADE"))
    with Session(release_pg) as db:
        with pytest.raises(RuntimeError, match="Incomplete county debt schema"):
            county_debt_rows(db, [1])
    for path, status, body in county_http(release_client):
        assert status >= 500, (path, body)


def test_schema_adoption_is_seen_without_process_or_session_restart(
    release_pg, release_client
):
    with Session(release_pg) as db:
        assert county_debt_rows(db, [1]) == []
        # Adoption becomes visible to this same session on the next call.
        Base.metadata.create_all(
            db.connection(),
            tables=[CountyDebtInstrument.__table__, CountyDebtObservation.__table__],
        )
        write(db)
        write(db, "B", 30)
        db.commit()
        assert county_debt_summary(county_debt_rows(db, [1]))["total_debt"] == 50
    for path, status, body in county_http(release_client):
        assert status == 200 and body["total_debt"] == 50, (path, status, body)


def test_existing_table_query_error_does_not_become_legacy_only(
    release_pg, release_client
):
    Base.metadata.create_all(release_pg)
    with Session(release_pg) as db:
        db.add(legacy(amount=20))
        db.commit()
    with release_pg.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE county_debt_observations RENAME COLUMN as_at TO damaged_as_at"
            )
        )
    with Session(release_pg) as db:
        with pytest.raises(ProgrammingError) as exc:
            county_debt_rows(db, [1])
        assert exc.value.orig.pgcode == "42703"
    for path, status, body in county_http(release_client):
        assert status >= 500, (path, body)


def test_database_failure_does_not_become_absent_schema(release_pg):
    with Session(release_pg) as db:
        with pytest.raises(ProgrammingError):
            db.execute(text("SELECT * FROM deliberately_missing_relation"))
        with pytest.raises(InternalError) as exc:
            county_debt_rows(db, [1])
        assert exc.value.orig.pgcode == "25P02"


@pytest.mark.parametrize(
    "removed",
    [
        ("county_debt_instruments", "county_debt_observations"),
        ("county_debt_instruments",),
        ("county_debt_observations",),
    ],
)
def test_sqlite_native_inspection_preserves_absent_and_partial_contract(
    db_session, removed
):
    assert db_session.get_bind().dialect.name == "sqlite"
    for name in removed:
        db_session.execute(text(f"DROP TABLE {name}"))
    if len(removed) == 2:
        assert county_debt_rows(db_session, [1]) == []
    else:
        with pytest.raises(RuntimeError, match="Incomplete county debt schema"):
            county_debt_rows(db_session, [1])
