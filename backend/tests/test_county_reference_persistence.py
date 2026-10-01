"""Real county writer, commit/reopen and public ledger on disposable PostgreSQL."""
import asyncio
import importlib
import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Event, current_thread
from time import monotonic
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from models import (
    Audit,
    Base,
    BudgetLine,
    Country,
    DocumentType,
    Entity,
    EntityType,
    FiscalPeriod,
    Loan,
    Severity,
    SourceDocument,
)

module = importlib.import_module("services.auto_seeder")


@pytest.fixture
def pg_references(monkeypatch):
    address = os.environ.get("AUDIT_TEST_POSTGRES_URL")
    if not address:
        pytest.skip("Set AUDIT_TEST_POSTGRES_URL to disposable loopback PostgreSQL")
    url = make_url(address)
    assert url.get_backend_name() == "postgresql"
    assert url.host in {"127.0.0.1", "localhost", "::1"}
    assert url.port and url.port != 5432
    schema = "county_reference_test_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as db:
        db.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        url,
        connect_args={
            "options": f"-csearch_path={schema} -cstatement_timeout=10000 -clock_timeout=5000",
        },
    )
    Session = sessionmaker(bind=engine)
    try:
        Base.metadata.create_all(engine)
        monkeypatch.setattr(module, "SessionLocal", Session)
        yield engine, Session
    finally:
        engine.dispose()
        with admin.begin() as db:
            db.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def country(Session, iso="KEN"):
    with Session() as db:
        row = Country(
            iso_code=iso,
            name=iso,
            currency="KES",
            timezone="Africa/Nairobi",
            default_locale="en_KE",
        )
        db.add(row)
        db.commit()
        return row.id


def existing(Session, ken, metadata):
    with Session() as db:
        for code, name in module.KENYA_COUNTY_CODES.items():
            db.add(
                Entity(
                    country_id=ken,
                    type=EntityType.COUNTY,
                    canonical_name=f"{name} County",
                    slug=f"stable-{ken}-{code}",
                    alt_names=[name, "preserved alias"],
                    meta=deepcopy(metadata) if code == "001" else {"code": code},
                )
            )
        db.commit()


def snapshot(Session, ken):
    with Session() as db:
        return {
            row.canonical_name: (row.id, row.slug, row.alt_names, row.meta)
            for row in db.query(Entity).filter_by(
                country_id=ken, type=EntityType.COUNTY
            )
        }


def seeder(monkeypatch):
    worker = module.AutoSeeder()
    monkeypatch.setattr(
        worker.aggregator, "fetch_all_county_data", AsyncMock(return_value=([], []))
    )
    return worker


def public_status(client, worker, monkeypatch):
    monkeypatch.setattr(module, "auto_seeder", worker)
    response = client.get("/api/v1/system/seeder-status")
    assert response.status_code == 200, response.text
    body = response.json()["auto_seeder"]
    assert body["external_job_owner"]["job_health"] == "not_checked_here"
    return body


def test_existing_jsonb_changes_are_durable_without_authorizing_code_cleanup(
    pg_references,
    client,
    monkeypatch,
    caplog,
):
    engine, Session = pg_references
    ken = country(Session)
    before_meta = {
        "code": "047",
        "sentinel": "retained",
        "metrics": {"FY2024/25": {"county_code": "047", "budget": 0}},
        "population": 0,
        "budget": 0,
        "last_updated": "2025-01-01",
        "data_source": "sourced",
        "economic_profile": {"source": "retired fixture", "value": 123},
        "audit_summary": {"source": "retired fixture"},
        "stalled_projects": [
            {"source_url": "https://example.test/project.pdf", "page": 7}
        ],
        "newer": {"hash": "synthetic hash", "as_at": "2026-09-30"},
    }
    existing(Session, ken, before_meta)
    before = snapshot(Session, ken)
    with Session() as db:
        entity_id = before["Mombasa County"][0]
        period = FiscalPeriod(
            country_id=ken,
            label="FY2024/25",
            start_date=datetime(2024, 7, 1),
            end_date=datetime(2025, 6, 30),
        )
        source = SourceDocument(
            country_id=ken,
            publisher="Synthetic publisher",
            title="Synthetic source",
            url="https://example.test/source.pdf",
            doc_type=DocumentType.BUDGET,
            md5="synthetic-hash",
            fetch_date=datetime(2025, 9, 1, tzinfo=timezone.utc),
        )
        db.add_all([period, source])
        db.flush()
        db.add_all(
            [
                BudgetLine(
                    entity_id=entity_id,
                    period_id=period.id,
                    source_document_id=source.id,
                    category="Total",
                    allocated_amount=0,
                    currency="KES",
                    page_ref="p.7",
                ),
                Loan(
                    entity_id=entity_id,
                    source_document_id=source.id,
                    lender="Synthetic",
                    principal=0,
                    outstanding=0,
                    issue_date=datetime(2024, 7, 1),
                    currency="KES",
                ),
                Audit(
                    entity_id=entity_id,
                    period_id=period.id,
                    source_document_id=source.id,
                    finding_text="Synthetic finding",
                    severity=Severity.INFO,
                    amount=0,
                    page_ref="p.7",
                ),
            ]
        )
        db.commit()
    worker = seeder(monkeypatch)
    with caplog.at_level("INFO", logger="auto_seeder"):
        result = asyncio.run(worker._seed_counties_live())
    after = snapshot(Session, ken)
    reference = after["Mombasa County"][3].get("county_reference")
    assert (
        reference is not None
    ), "Owned reference metadata disappeared after PostgreSQL commit/reopen"
    assert reference["code"] == "001"
    assert reference["source"] == "static_county_reference"
    assert datetime.fromisoformat(reference["last_changed_at"]).tzinfo is not None
    for name, (row_id, slug, aliases, meta) in before.items():
        assert after[name][:3] == (row_id, slug, aliases)
        assert {
            k: v for k, v in after[name][3].items() if k != "county_reference"
        } == meta
    assert result == {"created": 0, "updated": 47, "unchanged": 0, "reused": 47}
    assert "0 created, 47 updated, 0 unchanged" in caplog.text
    status = public_status(client, worker, monkeypatch)
    assert status["county_reference_refresh"]["counts"] == result
    with Session() as db:
        for table in (BudgetLine, Loan, Audit):
            assert db.query(table).one().entity_id == entity_id
    updates = []

    def observe(_c, _cur, statement, _p, _ctx, _many):
        if statement.lstrip().lower().startswith("update entities"):
            updates.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        result = asyncio.run(worker._seed_counties_live())
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert result == {"created": 0, "updated": 0, "unchanged": 47, "reused": 47}
    assert updates == []
    assert snapshot(Session, ken) == after
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    asyncio.run(worker._check_and_refresh())
    status = public_status(client, worker, monkeypatch)
    assert status["fetch_stats"]["successful_fetches"] == 1
    assert status["county_reference_refresh"]["counts"]["unchanged"] == 47
    assert status["last_refresh"].keys() == {"counties"}
    assert snapshot(Session, ken) == after


@pytest.mark.parametrize(
    "changed_at",
    [True, 1, "garbage", [], {}, "2025-01-01T00:00:00", "2999-01-01T00:00:00+00:00"],
)
def test_malformed_owned_timestamp_cannot_certify_unchanged(
    pg_references,
    monkeypatch,
    changed_at,
):
    _, Session = pg_references
    ken = country(Session)
    existing(
        Session,
        ken,
        {
            "county_reference": {
                "code": "001",
                "source": "static_county_reference",
                "last_changed_at": changed_at,
            }
        },
    )
    before = snapshot(Session, ken)
    with pytest.raises(ValueError, match="metadata"):
        asyncio.run(seeder(monkeypatch)._seed_counties_live())
    assert snapshot(Session, ken) == before


def test_newer_project_commit_is_read_under_reference_lock(pg_references, monkeypatch):
    engine, Session = pg_references
    ken = country(Session)
    existing(Session, ken, {"sentinel": "keep"})
    worker = seeder(monkeypatch)
    entered, state = Event(), {}

    def writer():
        def observe(connection, _cursor, statement, _params, _context, _many):
            if "FOR UPDATE" in statement:
                # The first locked reference SELECT uses this transaction's PID.
                state["pid"] = connection.connection.driver_connection.get_backend_pid()
                entered.set()

        event.listen(engine, "before_cursor_execute", observe)
        try:
            return asyncio.run(worker._seed_counties_live())
        finally:
            event.remove(engine, "before_cursor_execute", observe)

    with Session() as source_writer, ThreadPoolExecutor(max_workers=1) as pool:
        row = (
            source_writer.query(Entity).filter_by(canonical_name="Mombasa County").one()
        )
        row.meta = {
            **row.meta,
            "stalled_projects": [
                {
                    "name": "Newer sourced project",
                    "source_url": "https://example.test/new.pdf",
                    "page_ref": "p.7",
                    "as_at": "2026-09-30",
                    "source_hash": "keep-newer-hash",
                }
            ],
        }
        expected = deepcopy(row.meta)
        source_writer.flush()  # Actual PostgreSQL row lock and uncommitted newer JSON.
        future = pool.submit(writer)
        try:
            assert entered.wait(3)
            deadline = monotonic() + 3
            with engine.connect() as observer:
                while monotonic() < deadline:
                    waiting = observer.execute(
                        text(
                            "SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"
                        ),
                        {"pid": state["pid"]},
                    ).scalar_one()
                    observer.commit()
                    if waiting == "Lock":
                        break
                    assert not future.done(), "reference writer skipped the locked read"
                    Event().wait(0.01)
                else:
                    pytest.fail("did not observe PostgreSQL reference row lock wait")
            source_writer.commit()
            assert future.result(timeout=5)["updated"] == 47
        finally:
            source_writer.rollback()
    stored = snapshot(Session, ken)["Mombasa County"][3]
    assert {k: v for k, v in stored.items() if k != "county_reference"} == expected


@pytest.mark.parametrize("first_writer", ["reference", "projects"])
def test_reference_check_and_project_write_both_complete_with_legacy_id_order(
    pg_references, monkeypatch, first_writer
):
    from seeding.domains.stalled_projects import writer as project_writer

    engine, Session = pg_references
    ken = country(Session)
    with Session() as db:
        next_id = 5
        for code, name in module.KENYA_COUNTY_CODES.items():
            if name == "Nairobi":
                row_id = 3
            elif name == "Mombasa":
                row_id = 4
            else:
                row_id = next_id
                next_id += 1
            db.add(
                Entity(
                    id=row_id,
                    country_id=ken,
                    type=EntityType.COUNTY,
                    canonical_name=f"{name} County",
                    slug=f"stable-{code}",
                    meta={
                        "code": code,
                        "county_reference": {
                            "code": code,
                            "source": "static_county_reference",
                            "last_changed_at": "2025-01-01T00:00:00+00:00",
                        },
                        "stalled_projects": {"schema": 2, "rows": []},
                        "unrelated": {"retain": True},
                    },
                )
            )
        db.commit()
    before = snapshot(Session, ken)
    worker = seeder(monkeypatch)
    entered, release, second_started = Event(), Event(), Event()
    state = {}
    edition = {
        "url": "https://example.test/new-edition.pdf",
        "title": "Synthetic new project edition",
        "as_of": "2026-09-30",
        "sha256": "retain-new-source-hash",
    }
    counties = [
        {
            "county": project_writer.normalise_county(name),
            "tables": [
                {
                    "caption": "Synthetic sourced project table",
                    "rows": [
                        {
                            "project_name": f"New project in {name}",
                            "source_page": 7,
                            "estimated_value_kes": 0,
                            "amount_paid_kes": 0,
                        }
                    ],
                }
            ],
        }
        for name in module.KENYA_COUNTY_CODES.values()
    ]

    def role():
        return (
            "reference" if current_thread().name.startswith("reference") else "projects"
        )

    def relevant(statement):
        return "FOR UPDATE" in statement or statement.lower().lstrip().startswith(
            "update entities"
        )

    def before_statement(connection, _cursor, statement, _params, _ctx, _many):
        if relevant(statement) and role() != first_writer:
            state[
                "second_pid"
            ] = connection.connection.driver_connection.get_backend_pid()
            second_started.set()

    def after_statement(_connection, _cursor, statement, _params, _ctx, _many):
        if relevant(statement) and role() == first_writer and not entered.is_set():
            entered.set()
            assert release.wait(5), "first writer gate timed out"

    def reference():
        return asyncio.run(worker._seed_counties_live())

    def projects():
        with Session() as db:
            return project_writer.write(counties, edition, db)

    event.listen(engine, "before_cursor_execute", before_statement)
    event.listen(engine, "after_cursor_execute", after_statement)
    try:
        with ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="reference"
        ) as refs, ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="projects"
        ) as sources:
            try:
                first = (
                    refs.submit(reference)
                    if first_writer == "reference"
                    else sources.submit(projects)
                )
                assert entered.wait(3), "first writer did not take its database locks"
                second = (
                    sources.submit(projects)
                    if first_writer == "reference"
                    else refs.submit(reference)
                )
                assert second_started.wait(3)
                deadline = monotonic() + 3
                with engine.connect() as observer:
                    while monotonic() < deadline:
                        waiting = observer.execute(
                            text(
                                "SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"
                            ),
                            {"pid": state["second_pid"]},
                        ).scalar_one()
                        observer.commit()
                        if waiting == "Lock":
                            break
                        assert (
                            not second.done()
                        ), "competing writer bypassed database locks"
                        Event().wait(0.01)
                    else:
                        pytest.fail(
                            "did not observe the competing PostgreSQL writer waiting"
                        )
                release.set()
                first_result = first.result(timeout=6)
                second_result = second.result(timeout=6)
            finally:
                release.set()
    finally:
        event.remove(engine, "before_cursor_execute", before_statement)
        event.remove(engine, "after_cursor_execute", after_statement)
    reference_result, project_result = (
        (first_result, second_result)
        if first_writer == "reference"
        else (second_result, first_result)
    )
    assert reference_result == {
        "created": 0,
        "updated": 0,
        "unchanged": 47,
        "reused": 47,
    }
    assert project_result == {"counties": 47, "rows": 47, "unmatched": []}
    after = snapshot(Session, ken)
    for name, (_, _, _, meta) in after.items():
        assert after[name][:3] == before[name][:3]
        assert meta["county_reference"] == before[name][3]["county_reference"]
        assert meta["unrelated"] == {"retain": True}
        project = meta["stalled_projects"]
        assert project["source"]["sha256"] == edition["sha256"]
        assert project["rows"][0]["source_url"] == edition["url"]
        assert project["rows"][0]["source_page"] == 7
        assert project["rows"][0]["estimated_value_kes"] == 0


def test_new_references_have_no_unsourced_metrics_even_with_fetch_payload(
    pg_references,
    monkeypatch,
):
    _, Session = pg_references
    ken = country(Session)
    worker = seeder(monkeypatch)
    fetch = AsyncMock(
        return_value=(
            [
                {"name": "Mombasa", "population": 123},
                {"name": "Kwale", "population": 0},
            ],
            [{"county": "Mombasa", "budget": 456}],
        )
    )
    monkeypatch.setattr(worker.aggregator, "fetch_all_county_data", fetch)
    result = asyncio.run(worker._seed_counties_live())
    assert result == {"created": 47, "updated": 0, "unchanged": 0, "reused": 0}
    fetch.assert_not_called()
    rows = snapshot(Session, ken)
    assert len(rows) == 47
    for code, name in module.KENYA_COUNTY_CODES.items():
        meta = rows[f"{name} County"][3]
        assert meta["code"] == code
        assert meta["county_reference"]["code"] == code
        assert set(meta) == {"code", "county_reference"}


def test_mixed_new_changed_and_unchanged_counts(pg_references, monkeypatch):
    _, Session = pg_references
    ken = country(Session)
    with Session() as db:
        db.add_all(
            [
                Entity(
                    country_id=ken,
                    type=EntityType.COUNTY,
                    canonical_name="Mombasa County",
                    slug="stable-mombasa",
                    meta={"unrelated": "keep"},
                ),
                Entity(
                    country_id=ken,
                    type=EntityType.COUNTY,
                    canonical_name="Kwale County",
                    slug="stable-kwale",
                    meta={
                        "county_reference": {
                            "code": "002",
                            "source": "static_county_reference",
                            "last_changed_at": "2025-01-01T00:00:00+00:00",
                        }
                    },
                ),
            ]
        )
        db.commit()
    before = snapshot(Session, ken)
    result = asyncio.run(seeder(monkeypatch)._seed_counties_live())
    assert result == {"created": 45, "updated": 1, "unchanged": 1, "reused": 2}
    assert snapshot(Session, ken)["Kwale County"] == before["Kwale County"]


def test_real_county_readers_keep_legacy_official_slug_and_pk_identity(
    pg_references,
    client,
    monkeypatch,
):
    import main

    _, Session = pg_references
    ken = country(Session)
    existing(
        Session, ken, {"code": "047", "metrics": {"FY2024/25": {"county_code": "047"}}}
    )
    worker = seeder(monkeypatch)

    def get_db():
        with Session() as db:
            yield db

    monkeypatch.setattr(main, "get_db", get_db)
    monkeypatch.setattr(main, "DATABASE_AVAILABLE", True)
    monkeypatch.setattr(
        main.InternalAPIClient, "get_county_data", AsyncMock(return_value=None)
    )
    ids = snapshot(Session, ken)
    # Same stored PK, slug and historical URL must still resolve the same name.
    expected = {}
    for name, official, legacy in [
        ("Mombasa", "001", "047"),
        ("Nairobi", "047", "001"),
    ]:
        row_id, slug, _, _ = ids[f"{name} County"]
        for identifier in (str(row_id), slug, legacy, f"code:{official}"):
            expected[f"/api/v1/counties/{identifier}"] = (name, official)
        expected[f"/api/v1/counties/code/{official}"] = (name, official)
    before_response = {}
    for refresh in (False, True):
        if refresh:
            asyncio.run(worker._seed_counties_live())
        main.clear_all_caches()
        for route, (name, official) in expected.items():
            response = client.get(route)
            assert response.status_code == 200, (route, response.text)
            body = response.json()
            assert (body["name"], body["code"]) == (name, official)
            if refresh:
                assert body["id"] == before_response[route]
            else:
                before_response[route] = body["id"]
    assert (
        snapshot(Session, ken)["Mombasa County"][3]["metrics"]["FY2024/25"][
            "county_code"
        ]
        == "047"
    )


@pytest.mark.parametrize("metadata", [None, {}])
def test_missing_metadata_can_receive_owned_reference(
    pg_references, monkeypatch, metadata
):
    _, Session = pg_references
    ken = country(Session)
    existing(Session, ken, metadata)
    asyncio.run(seeder(monkeypatch)._seed_domain("counties"))
    stored = snapshot(Session, ken)["Mombasa County"][3]
    assert stored["county_reference"]["code"] == "001"
    assert set(stored) == {"county_reference"}


@pytest.mark.parametrize(
    "metadata",
    [
        [],
        ["invalid"],
        "",
        "invalid",
        0,
        1,
        False,
        {"county_reference": None},
        {"county_reference": []},
    ],
)
def test_malformed_metadata_refuses_atomic_refresh_and_success(
    pg_references,
    client,
    monkeypatch,
    metadata,
):
    _, Session = pg_references
    ken = country(Session)
    existing(Session, ken, metadata)
    before = snapshot(Session, ken)
    worker = seeder(monkeypatch)
    with pytest.raises(ValueError, match="metadata"):
        asyncio.run(worker._seed_counties_live())
    assert snapshot(Session, ken) == before
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    asyncio.run(worker._check_and_refresh())
    status = public_status(client, worker, monkeypatch)
    assert status["last_refresh"] == {}
    assert status["fetch_stats"]["successful_fetches"] == 0
    assert status["fetch_stats"]["failed_fetches"] == 1
    assert status["county_reference_refresh"] is None
    assert snapshot(Session, ken) == before


@pytest.mark.parametrize("ken_present", [False, True])
def test_foreign_namesakes_are_preserved_and_cannot_certify_ken(
    pg_references,
    client,
    monkeypatch,
    ken_present,
):
    _, Session = pg_references
    uga = country(Session, "UGA")
    existing(Session, uga, {"sentinel": "foreign"})
    before = snapshot(Session, uga)
    ken = country(Session) if ken_present else None
    worker = seeder(monkeypatch)
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    asyncio.run(worker.seed_all_domains())
    status = public_status(client, worker, monkeypatch)
    assert snapshot(Session, uga) == before
    assert status["fetch_stats"]["successful_fetches"] == (2 if ken_present else 0)
    assert status["fetch_stats"]["failed_fetches"] == (0 if ken_present else 2)
    if ken_present:
        assert len(snapshot(Session, ken)) == 47
    else:
        assert status["county_reference_refresh"] is None
        assert status["last_refresh"] == {}


def test_transaction_refusal_keeps_last_completion_and_retries_actual_changes(
    pg_references,
    client,
    monkeypatch,
    caplog,
):
    engine, Session = pg_references
    ken = country(Session)
    worker = seeder(monkeypatch)
    asyncio.run(worker._seed_counties_live())
    completed = deepcopy(
        public_status(client, worker, monkeypatch)["county_reference_refresh"]
    )
    # Change an owned field only. Trigger refuses the last update, after earlier writes.
    with Session() as db:
        for row in db.query(Entity).filter_by(country_id=ken):
            row.meta = {
                **row.meta,
                "county_reference": {
                    **row.meta["county_reference"],
                    "source": "outdated reference",
                    "extra": "keep",
                },
            }
        db.commit()
    before = snapshot(Session, ken)
    with engine.begin() as db:
        db.execute(
            text(
                """CREATE FUNCTION refuse_reference() RETURNS trigger AS $$
            BEGIN
                IF NEW.canonical_name = 'Nairobi County' THEN
                    RAISE EXCEPTION 'synthetic reference update refused';
                END IF;
                RETURN NEW;
            END; $$ LANGUAGE plpgsql"""
            )
        )
        db.execute(
            text(
                """CREATE TRIGGER refuse_reference BEFORE UPDATE ON entities
            FOR EACH ROW EXECUTE FUNCTION refuse_reference()"""
            )
        )
    old = datetime.now(timezone.utc) - timedelta(days=8)
    worker.last_refresh["counties"] = old
    worker._fetch_stats["last_full_refresh"] = old.isoformat()
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    with caplog.at_level("INFO", logger="auto_seeder"):
        asyncio.run(worker._check_and_refresh())
    assert "0 created, 47 updated" not in caplog.text
    assert snapshot(Session, ken) == before
    status = public_status(client, worker, monkeypatch)
    assert status["county_reference_refresh"] == completed
    assert status["last_refresh"] == {"counties": old.isoformat()}
    assert status["fetch_stats"]["last_full_refresh"] == old.isoformat()
    assert status["fetch_stats"]["successful_fetches"] == 0
    assert status["fetch_stats"]["failed_fetches"] == 1
    with engine.begin() as db:
        db.execute(text("DROP TRIGGER refuse_reference ON entities"))
    asyncio.run(worker._check_and_refresh())
    status = public_status(client, worker, monkeypatch)
    assert status["fetch_stats"]["successful_fetches"] == 1
    assert status["consecutive_failures"] == {}
    assert status["county_reference_refresh"]["counts"] == {
        "created": 0,
        "updated": 47,
        "unchanged": 0,
        "reused": 47,
    }
    for row in snapshot(Session, ken).values():
        assert row[3]["county_reference"]["source"] == "static_county_reference"
        assert row[3]["county_reference"]["extra"] == "keep"
