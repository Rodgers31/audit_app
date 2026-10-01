"""Explicit county instruments, commit/reopen and actual public readers on PostgreSQL.

Run only through a destination-sanitized child with a newly owned loopback DB.
This is synthetic provenance/behavior evidence, not verification of Kenyan debt.
"""
import os
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import (
    Base,
    Country,
    Entity,
    EntityType,
    SourceDocument,
    DocumentType,
    FigureBasis,
    Loan,
    DebtCategory,
    CountyDebtInstrument,
    CountyDebtObservation,
)
from services.county_debt import record_county_debt_observation, county_debt_rows
from services.financial_publication import county_debt_summary


@pytest.fixture
def pg():
    raw = os.environ.get("COUNTY_INSTRUMENT_TEST_URL")
    if not raw:
        pytest.skip("Requires explicitly owned synthetic loopback PostgreSQL")
    url = make_url(raw)
    assert (
        url.host == "127.0.0.1"
        and url.port == 55415
        and url.database == "round10_session4_415"
    )
    assert not any(
        os.environ.get(k) for k in ("PGSERVICE", "PGSERVICEFILE", "PGOPTIONS")
    )
    control = create_engine(url)
    schema = "r10s4_" + uuid.uuid4().hex
    with control.begin() as c:
        c.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            seed(db)
        yield engine
    finally:
        engine.dispose()
        with control.begin() as c:
            c.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            assert (
                c.execute(
                    text("SELECT count(*) FROM pg_namespace WHERE nspname=:s"),
                    {"s": schema},
                ).scalar()
                == 0
            )
        control.dispose()


def seed(db):
    db.add(
        Country(
            id=1,
            iso_code="KEN",
            name="Owned synthetic Kenya",
            currency="KES",
            timezone="Africa/Nairobi",
            default_locale="en_KE",
        )
    )
    db.flush()
    db.add_all(
        [
            Entity(
                id=1,
                country_id=1,
                type=EntityType.COUNTY,
                canonical_name="Mombasa County",
                slug="mombasa-county",
            ),
            Entity(
                id=2,
                country_id=1,
                type=EntityType.NATIONAL,
                canonical_name="National Government",
                slug="national",
            ),
            SourceDocument(
                id=1,
                country_id=1,
                title="Owned synthetic county borrowing account",
                publisher="Owned fixture",
                url="https://example.invalid/county-debt.pdf",
                doc_type=DocumentType.LOAN,
                fetch_date=datetime(2025, 7, 1),
            ),
            SourceDocument(
                id=2,
                country_id=1,
                title="Owned competing account",
                publisher="Owned fixture",
                url="https://example.invalid/competing.pdf",
                doc_type=DocumentType.LOAN,
                fetch_date=datetime(2025, 7, 1),
            ),
        ]
    )
    db.commit()


def write(db, reference="A", amount=20, **overrides):
    args = dict(
        entity_id=1,
        identity_namespace="county-contract-register",
        instrument_reference=reference,
        lender="Synthetic County Bank",
        issue_date=datetime(2020, 1, 1),
        currency="KES",
        as_at=date(2025, 6, 30),
        source_document_id=1,
        page_ref="p.1",
        basis=FigureBasis.ACTUAL,
        principal=100,
        outstanding=amount,
    )
    args.update(overrides)
    return record_county_debt_observation(db, **args)


def summary(db):
    return county_debt_summary(county_debt_rows(db, [1]))


def test_distinct_ids_repeat_correction_new_snapshot_commit_reopen(pg):
    with Session(pg) as db:
        a = write(db)
        assert write(db) == a
        write(db, "B", 30)
        db.commit()
    with Session(pg) as db:
        assert db.query(CountyDebtInstrument).count() == 2
        assert db.query(CountyDebtObservation).count() == 2
        assert summary(db)["total_debt"] == 50
        with pytest.raises(ValueError, match="explicit correction"):
            write(db, amount=25)
        db.commit()
        assert summary(db)["total_debt"] == 50
        write(db, amount=25, correct=True)
        db.commit()
    with Session(pg) as db:
        assert summary(db)["total_debt"] == 55
        assert db.get(CountyDebtObservation, a).revision == 2
        write(db, amount=0, as_at=date(2026, 6, 30))
        db.commit()
        assert (
            summary(db)["total_debt_absent_reason"]
            == "incompatible_or_missing_reporting_dates"
        )
        write(db, "B", 0, as_at=date(2026, 6, 30))
        db.commit()
    with Session(pg) as db:
        assert summary(db)["total_debt"] == 0
        assert db.query(CountyDebtObservation).count() == 4
        write(db, amount=None, as_at=date(2027, 6, 30))
        write(db, "B", 0, as_at=date(2027, 6, 30))
        db.commit()
    with Session(pg) as db:
        assert summary(db)["total_debt"] is None
        assert (
            summary(db)["total_debt_absent_reason"]
            == "outstanding_not_reported_or_invalid"
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("instrument_reference", None),
        ("instrument_reference", ""),
        ("instrument_reference", " A "),
        ("identity_namespace", None),
        ("identity_namespace", ""),
        ("entity_id", 2),
        ("source_document_id", 999),
        ("as_at", None),
        ("as_at", "2025-06-30"),
        ("basis", None),
        ("currency", "kes"),
        ("currency", None),
        ("page_ref", ""),
        ("page_ref", "prose"),
        ("outstanding", True),
        ("outstanding", False),
        ("outstanding", -1),
        ("outstanding", "NaN"),
        ("outstanding", "Infinity"),
        ("outstanding", {}),
        ("outstanding", "0.001"),
        ("principal", []),
        ("provenance", []),
        ("provenance", {"instrument_id": "prose"}),
        ("debt_category", DebtCategory.PENDING_BILLS),
    ],
)
def test_missing_ambiguous_and_invalid_writes_leave_no_partial_state(pg, field, value):
    with Session(pg) as db:
        write(db)
        db.commit()
        with pytest.raises(ValueError):
            write(db, "B", **{field: value})
        db.commit()
    with Session(pg) as db:
        assert summary(db)["total_debt"] == 20
        assert db.query(CountyDebtInstrument).count() == 1
        assert db.query(CountyDebtObservation).count() == 1


def test_competing_sources_namespaces_and_terms(pg):
    with Session(pg) as db:
        write(db)
        write(db, source_document_id=2)
        db.commit()
        assert (
            summary(db)["total_debt_absent_reason"]
            == "duplicate_instrument_observations"
        )
        db.query(CountyDebtObservation).filter_by(source_document_id=2).delete()
        write(db, identity_namespace="another-issuer")
        db.commit()
        assert summary(db)["total_debt"] == 40
        with pytest.raises(ValueError, match="Conflicting instrument terms"):
            write(db, currency="USD")
        db.commit()
        assert summary(db)["total_debt"] == 40


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"currency": "USD"}, "unsupported_currency"),
        ({"basis": FigureBasis.PROJECTED}, "unreported_accounting_basis"),
        ({"outstanding": None}, "outstanding_not_reported_or_invalid"),
    ],
)
def test_latest_ineligible_snapshot_never_resurrects_old_amount(pg, overrides, reason):
    with Session(pg) as db:
        if "currency" in overrides:
            write(db, currency="USD")
        else:
            write(db)
            write(db, as_at=date(2026, 6, 30), **overrides)
        db.commit()
    with Session(pg) as db:
        assert summary(db)["total_debt"] is None
        assert summary(db)["total_debt_absent_reason"] == reason


def legacy(amount=99, entity_id=1):
    return Loan(
        entity_id=entity_id,
        lender="Synthetic County Bank",
        issue_date=datetime(2020, 1, 1),
        currency="KES",
        principal=amount,
        outstanding=amount,
        source_document_id=1,
        page_ref="p.1",
        basis=FigureBasis.ACTUAL,
        provenance={"instrument_id": "A", "as_at": "2025-06-30"},
    )


def test_no_historical_guessing_national_constraint_unchanged(pg):
    with Session(pg) as db:
        db.add(legacy(entity_id=2))
        db.commit()
        db.add(legacy(entity_id=2))
        with pytest.raises(IntegrityError) as error:
            db.commit()
        assert error.value.orig.diag.constraint_name == "uq_loans_entity_lender_date"
        db.rollback()
        assert db.query(Loan).one().outstanding == 99
        write(db)
        db.add(legacy())
        db.commit()
        assert (
            summary(db)["total_debt_absent_reason"]
            == "mixed_instrument_representations"
        )


def test_postgres_fk_identity_observation_uniqueness_and_invalid_money(pg):
    with Session(pg) as db:
        a = write(db)
        db.commit()
        obs = db.get(CountyDebtObservation, a)
        for statement, params, expected in [
            (
                "UPDATE county_debt_observations SET outstanding=:v",
                {"v": "NaN"},
                "23514",
            ),
            ("UPDATE county_debt_observations SET instrument_id=999", {}, "23503"),
            (
                "INSERT INTO county_debt_instruments (entity_id,identity_namespace,instrument_reference,lender,issue_date,currency,debt_category) SELECT entity_id,identity_namespace,instrument_reference,lender,issue_date,currency,debt_category FROM county_debt_instruments",
                {},
                "23505",
            ),
            (
                "INSERT INTO county_debt_observations (instrument_id,as_at,source_document_id,page_ref,basis,provenance) SELECT instrument_id,as_at,source_document_id,page_ref,basis,provenance FROM county_debt_observations",
                {},
                "23505",
            ),
        ]:
            with pytest.raises(IntegrityError) as error:
                with db.begin_nested():
                    db.execute(text(statement), params)
            assert error.value.orig.pgcode == expected
        db.commit()
        assert summary(db)["total_debt"] == 20


def test_public_county_readers_selected_cohort(pg, monkeypatch):
    import main, database
    from fastapi.testclient import TestClient
    from config.settings import Settings

    assert not main.AUTO_SEEDER_ENABLED and not main._WARMUP_ENABLED
    assert Settings(_env_file=None).REDIS_URL == ""
    print(
        "RESOLVED seeder=false warmup=false redis=empty engine=owned_loopback libpq=owned_loopback"
    )

    def get_db():
        with Session(pg) as db:
            yield db

    monkeypatch.setattr(main, "get_db", get_db)
    main.app.dependency_overrides[database.get_db] = get_db
    client = TestClient(main.app)  # No lifespan/background jobs.
    try:
        with Session(pg) as db:
            write(db)
            write(db, "B", 30)
            db.commit()
        for suffix in ("comprehensive", "", "debt"):
            main.clear_all_caches()
            response = client.get(
                "/api/v1/counties/code:001" + ("/" + suffix if suffix else "")
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            payload = payload["debt"] if suffix == "comprehensive" else payload
            assert payload["total_debt"] == 50, payload
        main.clear_all_caches()
        response = client.get("/api/v1/counties")
        assert response.status_code == 200, response.text
        assert response.json()[0]["total_debt"] == 50, response.json()
        with Session(pg) as db:
            write(db, amount=0, correct=True)
            write(db, "B", 0, correct=True)
            db.commit()
        for suffix in ("comprehensive", "", "debt"):
            main.clear_all_caches()
            response = client.get(
                "/api/v1/counties/code:001" + ("/" + suffix if suffix else "")
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            payload = payload["debt"] if suffix == "comprehensive" else payload
            assert payload["total_debt"] == 0, payload
        with Session(pg) as db:
            write(db, amount=None, correct=True)
            db.commit()
        main.clear_all_caches()
        payload = client.get("/api/v1/counties/code:001/debt").json()
        assert payload["debt_outstanding"] is None and payload["debt_principal"] is None
        assert (
            payload["debt_breakdown"] == {} and payload["debt_sustainability"] is None
        )
    finally:
        main.app.dependency_overrides.clear()
        main.clear_all_caches()


def test_real_migration_fresh_existing_upgrade_refusal_rollback_recovery(monkeypatch):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from models import PopulationData

    raw = os.environ.get("COUNTY_INSTRUMENT_TEST_URL")
    if not raw:
        pytest.skip("Requires explicitly owned synthetic loopback PostgreSQL")
    url = make_url(raw)
    assert (
        url.host == "127.0.0.1"
        and url.port == 55415
        and url.database == "round10_session4_415"
    )
    root = Path(__file__).resolve().parents[1]
    control = create_engine(url, isolation_level="AUTOCOMMIT")
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    assert ScriptDirectory.from_config(cfg).get_heads() == ["c415a10d2026"]
    schema = "r10s4_migration_" + uuid.uuid4().hex
    with control.begin() as c:
        c.execute(text(f"CREATE DATABASE {schema}"))
    scoped = url.set(database=schema)
    engine = create_engine(scoped)
    monkeypatch.setenv("DATABASE_URL", scoped.render_as_string(hide_password=False))

    def fingerprint():
        with engine.connect() as c:
            return (
                [
                    tuple(row)
                    for row in c.execute(
                        text(
                            "SELECT id,title,url FROM source_documents WHERE id IN (1823,2541) ORDER BY id"
                        )
                    )
                ],
                c.execute(
                    text("SELECT total_population FROM population_data WHERE id=79")
                ).scalar(),
                c.execute(text("SELECT outstanding FROM loans")).scalar(),
            )

    try:
        command.upgrade(cfg, "ea1645a4c0b5")
        assert "county_debt_instruments" not in inspect(engine).get_table_names()
        with Session(engine) as db:
            seed(db)
            db.add_all(
                [
                    SourceDocument(
                        id=i,
                        country_id=1,
                        title=f"Protected owned fixture {i}",
                        publisher="Owned fixture",
                        url=f"https://example.invalid/protected-{i}.pdf",
                        doc_type=DocumentType.REPORT,
                        fetch_date=datetime(2025, 7, 1),
                    )
                    for i in (1823, 2541)
                ]
            )
            db.add(
                PopulationData(
                    id=79,
                    entity_id=2,
                    year=2025,
                    total_population=51_202_827,
                    source_document_id=1823,
                )
            )
            db.add(legacy(entity_id=2))
            db.commit()
        before = fingerprint()
        command.upgrade(cfg, "head")
        assert fingerprint() == before
        with Session(engine) as db:
            write(db)
            write(db, "B", 30)
            db.commit()
            assert summary(db)["total_debt"] == 50
        # Compare exactly the new ORM-owned tables against migrated DDL.
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from sqlalchemy import MetaData

        target = MetaData()
        for table in (
            CountyDebtInstrument.__table__,
            CountyDebtObservation.__table__,
            Entity.__table__,
            SourceDocument.__table__,
            Country.__table__,
        ):
            table.to_metadata(target)

        def include(obj, name, type_, reflected, compare_to):
            table_name = (
                name
                if type_ == "table"
                else getattr(getattr(obj, "table", None), "name", None)
            )
            return table_name in {"county_debt_instruments", "county_debt_observations"}

        with engine.connect() as c:
            diffs = compare_metadata(
                MigrationContext.configure(c, opts={"include_object": include}), target
            )
            assert diffs == [], diffs
            assert "uq_loans_entity_lender_date" in {
                u["name"] for u in inspect(c).get_unique_constraints("loans")
            }
        with pytest.raises(RuntimeError, match="evidence exists"):
            command.downgrade(cfg, "ea1645a4c0b5")
        with Session(engine) as db:
            assert summary(db)["total_debt"] == 50
            assert db.query(CountyDebtObservation).count() == 2
        assert fingerprint() == before
        with engine.connect() as c:
            assert (
                c.execute(text("SELECT version_num FROM alembic_version")).scalar()
                == "c415a10d2026"
            )
        # Remove only owned synthetic new accounts, then exercise supported downgrade.
        with engine.begin() as c:
            c.execute(text("DELETE FROM county_debt_observations"))
            c.execute(text("DELETE FROM county_debt_instruments"))
        command.downgrade(cfg, "ea1645a4c0b5")
        assert "county_debt_instruments" not in inspect(engine).get_table_names()
        assert fingerprint() == before
        command.upgrade(cfg, "head")
        with Session(engine) as db:
            write(db)
            write(db, "B", 30)
            db.commit()
            assert summary(db)["total_debt"] == 50
        assert fingerprint() == before
        print(
            "MIGRATION existing-data upgrade, exact new-table ORM parity, populated downgrade refusal/rollback, empty downgrade/recovery passed; protected synthetic rows unchanged"
        )
    finally:
        engine.dispose()
        with control.begin() as c:
            c.execute(text(f"DROP DATABASE {schema}"))
    schema = "r10s4_fresh_" + uuid.uuid4().hex
    with control.begin() as c:
        c.execute(text(f"CREATE DATABASE {schema}"))
    scoped = url.set(database=schema)
    engine = create_engine(scoped)
    monkeypatch.setenv("DATABASE_URL", scoped.render_as_string(hide_password=False))
    try:
        command.upgrade(cfg, "head")
        with Session(engine) as db:
            seed(db)
            write(db)
            write(db, "B", 30)
            db.commit()
            assert summary(db)["total_debt"] == 50
        print("MIGRATION fresh replay head and commit/reopen total=50 passed")
    finally:
        engine.dispose()
        with control.begin() as c:
            c.execute(text(f"DROP DATABASE {schema}"))
        control.dispose()


@pytest.mark.parametrize(
    "mutation", ["url", "bad_port", "page", "provenance", "source_meta"]
)
def test_direct_orm_bad_evidence_withholds_without_crashing(pg, mutation):
    with Session(pg) as db:
        a = write(db)
        db.commit()
        observation = db.get(CountyDebtObservation, a)
        if mutation == "url":
            observation.source_document.url = "javascript:alert(1)"
        elif mutation == "bad_port":
            observation.source_document.url = "https://example.invalid:bad/account.pdf"
        elif mutation == "page":
            observation.page_ref = ""
        elif mutation == "provenance":
            observation.provenance = ["malformed"]
        else:
            observation.source_document.meta = ["malformed"]
        db.commit()
    with Session(pg) as db:
        result = summary(db)
        assert result["total_debt"] is None, result
        assert result["total_debt_absent_reason"]
        from services.financial_publication import county_debt_instrument_fields

        fields = county_debt_instrument_fields(county_debt_rows(db, [1])[0])
        assert fields["outstanding"] is None and fields["principal"] is None, fields
        assert (
            fields["absent_reasons"]["outstanding"]
            == result["total_debt_absent_reason"]
        )


def test_timezone_repeat_and_source_refusal_before_writing(pg):
    from datetime import timezone

    with Session(pg) as db:
        a = write(db, issue_date=datetime(2020, 1, 1, tzinfo=timezone.utc))
        db.commit()
    with Session(pg) as db:
        assert write(db, issue_date=datetime(2020, 1, 1, tzinfo=timezone.utc)) == a
        db.get(SourceDocument, 2).url = "javascript:alert(1)"
        db.commit()
        with pytest.raises(ValueError):
            write(db, "B", source_document_id=2)
        with pytest.raises(ValueError):
            write(db, "B", as_at=date(2019, 1, 1))
        db.commit()
        assert db.query(CountyDebtInstrument).count() == 1


def test_downgrade_empty_check_cannot_drop_a_concurrently_committed_account(
    pg, monkeypatch
):
    """Force the actual check/drop interleaving, with a second PostgreSQL session."""
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    from alembic import op
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.exc import OperationalError

    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/c415a10d2026_county_debt_observations.py"
    )
    spec = importlib.util.spec_from_file_location("county_debt_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    committed = []
    blocked = []
    with pg.begin() as connection:

        class GatedBind:
            def execute(self, statement):
                result = connection.execute(statement)
                if str(statement).startswith("SELECT EXISTS"):
                    checked = result.scalar()
                    assert checked is False
                    try:
                        with Session(pg) as writer:
                            writer.execute(text("SET LOCAL lock_timeout='200ms'"))
                            write(writer)
                            writer.commit()
                            committed.append(True)
                    except OperationalError as error:
                        assert error.orig.pgcode == "55P03"
                        blocked.append(True)
                    return SimpleNamespace(scalar=lambda: checked)
                return result

        with Operations.context(MigrationContext.configure(connection)):
            monkeypatch.setattr(op, "get_bind", lambda: GatedBind())
            migration.downgrade()
    assert (
        not committed
    ), "An account committed after the empty check was silently dropped"
    assert blocked == [
        True
    ], "The downgrade must block concurrent writes through check/drop"
    with pg.connect() as c:
        assert (
            c.execute(text("SELECT to_regclass('county_debt_observations')")).scalar()
            is None
        )
