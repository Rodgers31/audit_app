"""Real PostgreSQL JSONB, row locking, rollback and reopen controls.

ORM-created isolated schemas exercise existing storage contracts; no migration
or production parity is claimed and no new DDL is required by the feature.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy.orm import Session
from models import Country, Extraction, Loan, SourceDocument
from services.pending_bills_aging import EXTRACTOR, aging_observations
from test_pending_bills_aging_persistence import populate_counties, source_input, write


import os
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from models import Base


@pytest.fixture
def pg_engine():
    raw = os.environ.get("PENDING_BILLS_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("Requires an explicitly owned loopback PostgreSQL database")
    url = make_url(raw)
    assert url.host == "127.0.0.1" and url.get_backend_name() == "postgresql"
    assert url.database.startswith("b83_")
    assert not any(
        os.environ.get(k) for k in ("PGSERVICE", "PGSERVICEFILE", "PGOPTIONS")
    )
    args = dict(hostaddr="127.0.0.1", sslmode="disable", gssencmode="disable")
    control = create_engine(url, connect_args=args)
    schema = "b83_aging_" + uuid.uuid4().hex
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url, connect_args={**args, "options": f"-csearch_path={schema}"}
    )
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(
                Country(
                    iso_code="KEN",
                    name="Inert Kenya",
                    currency="KES",
                    timezone="Africa/Nairobi",
                    default_locale="en_KE",
                )
            )
            db.commit()
        yield engine
    finally:
        engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            assert (
                connection.execute(
                    text("SELECT count(*) FROM pg_namespace WHERE nspname=:s"),
                    {"s": schema},
                ).scalar()
                == 0
            )
        control.dispose()


def test_postgres_commit_reopen_replay_and_late_rollback(
    pg_engine, tmp_path, monkeypatch
):
    records, cohort = source_input(tmp_path, monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db, db.query(Country).one().id)
        write(db, records, cohort)
        db.commit()
    with Session(pg_engine) as db:
        assert db.query(Loan).count() == 46
        assert (
            db.query(Extraction).filter(Extraction.extractor == EXTRACTOR).count() == 1
        )
        result = aging_observations(db, as_at="2026-06-30")["county_executive"]
        assert result["buckets"][0]["amount"] == 46000000
        from copy import deepcopy

        invalid = deepcopy(cohort)
        invalid["rows"][-1]["source_evidence"][0]["value"] = "0"
        import pytest

        with pytest.raises(ValueError):
            write(db, records, invalid, source_title="Refused correction")
        db.commit()
    with Session(pg_engine) as db:
        assert db.query(SourceDocument).count() == 1
        assert (
            aging_observations(db, as_at="2026-06-30")["county_executive"][
                "reported_total"
            ]
            == 460000000
        )
        write(db, records, cohort)
        db.commit()
    with Session(pg_engine) as db:
        assert (
            db.query(Extraction).filter(Extraction.extractor == EXTRACTOR).count() == 1
        )
        assert db.query(Loan).count() == 46


def test_concurrent_county_writers_serialize_one_active_aging_cohort(
    pg_engine, tmp_path, monkeypatch
):
    records, cohort = source_input(tmp_path, monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db, db.query(Country).one().id)
        db.commit()
    barrier = Barrier(2)

    def worker():
        with Session(pg_engine) as db:
            barrier.wait(timeout=10)
            result = write(db, records, cohort)
            db.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        assert sorted(f.result(timeout=45) for f in futures) == [(0, 46), (46, 0)]
    with Session(pg_engine) as db:
        assert db.query(SourceDocument).count() == 1
        assert (
            db.query(Extraction).filter(Extraction.extractor == EXTRACTOR).count() == 1
        )
        assert (
            aging_observations(db, as_at="2026-06-30")["county_executive"]["status"]
            == "qualified"
        )


def test_postgres_only_current_stock_source_and_batch_authorize_aging(
    pg_engine, tmp_path, monkeypatch
):
    records, cohort = source_input(tmp_path, monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db, db.query(Country).one().id)
        write(db, records, cohort)
        db.commit()
    with Session(pg_engine) as db:
        row = db.query(Loan).first()
        row.provenance = {**row.provenance, "publication_batch": "b" * 64}
        db.flush()
        assert (
            aging_observations(db, as_at="2026-06-30")["county_executive"]["status"]
            == "unavailable"
        )
        db.rollback()
        assert (
            aging_observations(db, as_at="2026-06-30")["county_executive"]["status"]
            == "qualified"
        )
        replacement = tmp_path / "replacement"
        replacement.mkdir()
        new_records, _ = source_input(replacement, monkeypatch)
        write(db, new_records, None, source_title="B84 new unaged report title")
        db.commit()
    with Session(pg_engine) as db:
        assert db.query(SourceDocument).count() == 2
        assert (
            db.query(Extraction).filter(Extraction.extractor == EXTRACTOR).count() == 1
        )
        assert (
            aging_observations(db, as_at="2026-06-30")["county_executive"]["status"]
            == "unavailable"
        )


def test_postgres_committed_replacement_cannot_change_an_earlier_stock_snapshot(
    pg_engine, tmp_path, monkeypatch
):
    records, cohort = source_input(tmp_path, monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db, db.query(Country).one().id)
        write(db, records, cohort)
        db.commit()
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    new_records, new_cohort = source_input(replacement, monkeypatch)
    with Session(pg_engine) as reader:
        context = {
            (row.source_document_id, row.provenance["publication_batch"])
            for row in reader.query(Loan).all()
        }
        with Session(pg_engine) as writer:
            write(
                writer,
                new_records,
                new_cohort,
                source_title="B84 concurrent replacement",
            )
            writer.commit()
        assert (
            aging_observations(reader, as_at="2026-06-30", stock_context=context)[
                "county_executive"
            ]["status"]
            == "unavailable"
        )
        assert (
            aging_observations(reader, as_at="2026-06-30")["county_executive"]["status"]
            == "qualified"
        )
