"""Project ownership at the actual PostgreSQL commit/identity-map boundary."""
import argparse
import asyncio
import importlib
import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from threading import Event, current_thread
from time import monotonic
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from models import (
    Base,
    Country,
    DocumentType,
    Entity,
    EntityType,
    IngestionJob,
    IngestionStatus,
    PopulationData,
    SourceDocument,
)
from seeding.domains.stalled_projects import writer

references = importlib.import_module("services.auto_seeder")
EDITION = {
    "url": "https://example.test/cob-current.pdf",
    "sha256": "synthetic-new-hash",
    "title": "Synthetic COB edition",
    "as_of": "2026-09-30",
    "fiscal_year": "FY2025/26",
    "period": "annual",
}


def incoming():
    return [
        {
            "county": writer.normalise_county(name),
            "tables": [
                {
                    "caption": "Synthetic source table",
                    "rows": [
                        {
                            "project_name": f"Cited project in {name}",
                            "source_page": 7,
                            "estimated_value_kes": 0,
                            "amount_paid_kes": None,
                        }
                    ],
                }
            ],
        }
        for name in references.KENYA_COUNTY_CODES.values()
    ]


@pytest.fixture
def pg_projects(monkeypatch):
    address = os.environ.get("AUDIT_TEST_POSTGRES_URL")
    if not address:
        pytest.skip("Set AUDIT_TEST_POSTGRES_URL to disposable loopback PostgreSQL")
    url = make_url(address)
    assert url.get_backend_name() == "postgresql"
    assert url.host in {"127.0.0.1", "localhost", "::1"}
    assert url.port and url.port != 5432
    schema = "project_persistence_test_" + uuid4().hex
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
        monkeypatch.setattr(references, "SessionLocal", Session)
        with Session() as db:
            ken = Country(
                iso_code="KEN",
                name="Synthetic Kenya",
                currency="KES",
                timezone="Africa/Nairobi",
                default_locale="en_KE",
            )
            db.add(ken)
            db.flush()
            next_id = 5
            for code, name in references.KENYA_COUNTY_CODES.items():
                row_id = 3 if name == "Nairobi" else 4 if name == "Mombasa" else next_id
                if name not in {"Nairobi", "Mombasa"}:
                    next_id += 1
                db.add(
                    Entity(
                        id=row_id,
                        country_id=ken.id,
                        type=EntityType.COUNTY,
                        canonical_name=f"{name} County",
                        slug=f"stable-{code}",
                        alt_names=[name, "retained alias"],
                        meta={
                            "county_reference": {
                                "code": "999",
                                "source": "old-reference",
                            },
                            "metrics": {
                                "FY2024/25": {"budget": 0, "county_code": code}
                            },
                            "population": 0,
                            "economic_profile": {"retain": True},
                            "unknown": {
                                "unicode": "Ὀδυσσεύς",
                                "values": [0, None, False],
                            },
                            "stalled_projects": {
                                "schema": 2,
                                "source": {"sha256": "old"},
                                "rows": [{"project_name": "Retained older project"}],
                            },
                            "stalled_projects_count": 1,
                        },
                    )
                )
            for source_id in (1823, 2541):
                db.add(
                    SourceDocument(
                        id=source_id,
                        country_id=ken.id,
                        publisher="Retained synthetic publisher",
                        title=str(source_id),
                        url=f"https://example.test/{source_id}.pdf",
                        md5="a" * 32,
                        fetch_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                        doc_type=DocumentType.OTHER,
                        meta={"retain": True},
                    )
                )
            db.add(
                PopulationData(
                    id=79,
                    year=2019,
                    total_population=51202827,
                    male_population=25485390,
                    female_population=25717437,
                    meta={"dataset_id": "SP.POP.TOTL"},
                )
            )
            db.commit()
        yield engine, Session
    finally:
        engine.dispose()
        with admin.begin() as db:
            db.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def snapshot(Session):
    with Session() as db:
        return {
            r.id: (r.canonical_name, r.slug, r.alt_names, deepcopy(r.meta))
            for r in db.query(Entity).order_by(Entity.id)
        }


def controls(engine):
    with engine.connect() as db:
        return {
            t: [
                dict(r._mapping)
                for r in db.execute(text(f"SELECT * FROM {t} ORDER BY id"))
            ]
            for t in ("source_documents", "population_data")
        }


def run_operation(db, operation, *, dry_run=False):
    if operation == "write":
        return writer.write(incoming(), EDITION, db, dry_run=dry_run)
    return writer.clear_owned_keys(
        db, dry_run=dry_run, legacy_only=operation == "legacy_clear"
    )


@pytest.mark.parametrize("operation", ["write", "clear", "legacy_clear"])
def test_preloaded_projects_preserve_newer_reference_and_other_metadata(
    pg_projects, operation
):
    engine, Session = pg_projects
    protected = controls(engine)
    worker = references.AutoSeeder()
    with Session() as stale:
        held = stale.query(
            Entity
        ).all()  # Keep actual stale identity-map entries alive.
        assert held[0].meta["county_reference"]["source"] == "old-reference"
        assert asyncio.run(worker._seed_counties_live())["updated"] == 47
        with Session() as other:
            for row in other.query(Entity):
                row.meta = {
                    **row.meta,
                    "metrics": {"FY2025/26": {"budget": 123}},
                    "population": 234,
                    "economic_profile": {"newer": True},
                    "unknown": {"newer": [None, 0, False]},
                }
            other.commit()
        before = snapshot(Session)
        run_operation(stale, operation)
    after = snapshot(Session)
    for pk, row in after.items():
        assert row[:3] == before[pk][:3]
        assert {
            k: v for k, v in row[3].items() if not k.startswith(writer.OWNED_PREFIX)
        } == {
            k: v
            for k, v in before[pk][3].items()
            if not k.startswith(writer.OWNED_PREFIX)
        }
        if operation == "write":
            block = row[3][writer.OWNED_PREFIX]
            assert block["source"]["sha256"] == EDITION["sha256"]
            assert block["rows"][0]["source_url"] == EDITION["url"]
            assert block["rows"][0]["source_page"] == 7
            assert block["rows"][0]["estimated_value_kes"] == 0
            assert block["rows"][0]["amount_paid_kes"] is None
        elif operation == "legacy_clear":
            assert row[3][writer.OWNED_PREFIX] == before[pk][3][writer.OWNED_PREFIX]
        else:
            assert not writer.owned_keys(row[3])
    assert controls(engine) == protected


@pytest.mark.parametrize("operation", ["write", "clear", "legacy_clear"])
@pytest.mark.parametrize("first_writer", ["reference", "projects"])
@pytest.mark.parametrize("mixed", [False, True])
def test_both_start_orders_preserve_committed_namespaces(
    pg_projects, operation, first_writer, mixed
):
    engine, Session = pg_projects
    protected = controls(engine)
    if mixed:
        add_excluded(Session)
    before = snapshot(Session)
    worker = references.AutoSeeder()
    entered, release, second_started = Event(), Event(), Event()
    state = {}

    def role():
        return (
            "reference" if current_thread().name.startswith("reference") else "projects"
        )

    def relevant(statement):
        return "FOR UPDATE" in statement or statement.lower().lstrip().startswith(
            "update entities"
        )

    def observe_before(connection, _cursor, statement, _params, _ctx, _many):
        if relevant(statement) and role() != first_writer:
            state["pid"] = connection.connection.driver_connection.get_backend_pid()
            second_started.set()

    def observe_after(_connection, _cursor, statement, _params, _ctx, _many):
        if relevant(statement) and role() == first_writer and not entered.is_set():
            entered.set()
            assert release.wait(5), "first writer gate timed out"

    def project_operation():
        with Session() as db:
            held = db.query(Entity).all()
            assert len(held) == len(before)
            return run_operation(db, operation)

    event.listen(engine, "before_cursor_execute", observe_before)
    event.listen(engine, "after_cursor_execute", observe_after)
    try:
        with ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="reference"
        ) as refs, ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="projects"
        ) as projects:

            def start(which):
                return (
                    refs.submit(lambda: asyncio.run(worker._seed_counties_live()))
                    if which == "reference"
                    else projects.submit(project_operation)
                )

            try:
                first = start(first_writer)
                assert entered.wait(3)
                second = start(
                    "projects" if first_writer == "reference" else "reference"
                )
                assert second_started.wait(3)
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
                        assert (
                            not second.done()
                        ), "competing operation did not wait for row locks"
                        Event().wait(0.01)
                    else:
                        pytest.fail("PostgreSQL lock wait was not observed")
                release.set()
                first.result(timeout=6)
                second.result(timeout=6)
            finally:
                release.set()
    finally:
        event.remove(engine, "before_cursor_execute", observe_before)
        event.remove(engine, "after_cursor_execute", observe_after)
    after = snapshot(Session)
    for pk, row in after.items():
        if pk >= 1000:
            assert row == before[pk]
            continue
        assert row[:3] == before[pk][:3]
        assert row[3]["county_reference"]["source"] == "static_county_reference"
        assert {
            k: v
            for k, v in row[3].items()
            if k != "county_reference" and not k.startswith(writer.OWNED_PREFIX)
        } == {
            k: v
            for k, v in before[pk][3].items()
            if k != "county_reference" and not k.startswith(writer.OWNED_PREFIX)
        }
        if operation == "write":
            assert row[3][writer.OWNED_PREFIX] == writer.build_county_block(
                next(
                    c
                    for c in incoming()
                    if c["county"] == writer.normalise_county(row[0])
                ),
                EDITION,
            )
        elif operation == "legacy_clear":
            assert row[3][writer.OWNED_PREFIX] == before[pk][3][writer.OWNED_PREFIX]
        else:
            assert not writer.owned_keys(row[3])
    assert controls(engine) == protected


@pytest.mark.parametrize("operation", ["write", "clear", "legacy_clear"])
def test_dry_run_noop_and_edition_removal(pg_projects, operation):
    engine, Session = pg_projects
    before = snapshot(Session)
    updates = []

    def observe(_conn, _cursor, statement, _params, _ctx, _many):
        if statement.lower().lstrip().startswith("update entities"):
            updates.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        with Session() as db:
            run_operation(db, operation, dry_run=True)
            assert not db.dirty
        assert snapshot(Session) == before and not updates
        with Session() as db:
            first = run_operation(db, operation)
        assert updates  # A real positive write, not vacuous no-op success.
        updates.clear()
        with Session() as db:
            assert run_operation(db, operation) == (
                first if operation == "write" else {"entities": 0, "keys": 0}
            )
        assert not updates
        if operation == "write":
            with Session() as db:
                writer.write(incoming()[:1], {**EDITION, "sha256": "next"}, db)
            stored = snapshot(Session)
            assert sum(writer.OWNED_PREFIX in r[3] for r in stored.values()) == 1
            assert (
                next(
                    r[3][writer.OWNED_PREFIX]["source"]["sha256"]
                    for r in stored.values()
                    if writer.OWNED_PREFIX in r[3]
                )
                == "next"
            )
    finally:
        event.remove(engine, "before_cursor_execute", observe)


@pytest.mark.parametrize("operation", ["write", "clear", "legacy_clear"])
@pytest.mark.parametrize("bad", [[], False, 0, "invalid"])
def test_malformed_metadata_refuses_atomically(pg_projects, operation, bad):
    _, Session = pg_projects
    with Session() as db:
        db.query(Entity).order_by(Entity.id.desc()).first().meta = bad
        db.commit()
    before = snapshot(Session)
    with Session() as db:
        with pytest.raises(ValueError, match="metadata"):
            run_operation(db, operation)
        assert not db.dirty
        db.commit()  # Cannot accidentally commit earlier county mutations after refusal.
    assert snapshot(Session) == before


@pytest.mark.parametrize("operation", ["write", "clear", "legacy_clear"])
def test_pending_metadata_refuses_before_autoflush(pg_projects, operation):
    engine, Session = pg_projects
    before = snapshot(Session)
    with Session() as db:
        held = db.query(Entity).all()
        held[0].meta = {**held[0].meta, "pending": "caller edit"}
        asyncio.run(references.AutoSeeder()._seed_counties_live())
        newer = snapshot(Session)
        with pytest.raises(ValueError, match="pending Entity"):
            run_operation(db, operation)
        assert not db.dirty
        db.commit()
    assert newer != before and snapshot(Session) == newer


@pytest.mark.parametrize("operation", ["write", "clear", "legacy_clear"])
def test_late_database_refusal_rolls_back_all_projects(pg_projects, operation):
    engine, Session = pg_projects
    before = snapshot(Session)
    with engine.begin() as db:
        db.execute(
            text(
                """CREATE FUNCTION refuse_project() RETURNS trigger AS $$
            BEGIN IF NEW.id = 49 THEN RAISE EXCEPTION 'synthetic final-row refusal'; END IF;
            RETURN NEW; END; $$ LANGUAGE plpgsql"""
            )
        )
        db.execute(
            text(
                "CREATE TRIGGER refuse_project BEFORE UPDATE ON entities FOR EACH ROW EXECUTE FUNCTION refuse_project()"
            )
        )
    with Session() as db:
        with pytest.raises(Exception, match="synthetic final-row refusal"):
            run_operation(db, operation)
        assert not db.dirty
        assert db.is_active
        db.commit()
    assert snapshot(Session) == before


@pytest.mark.parametrize("operation", ["write", "clear", "legacy_clear"])
@pytest.mark.parametrize("missing", [None, {}])
def test_missing_metadata_is_supported(pg_projects, operation, missing):
    _, Session = pg_projects
    with Session() as db:
        db.query(Entity).order_by(Entity.id.desc()).first().meta = missing
        db.commit()
    with Session() as db:
        run_operation(db, operation)
    stored = snapshot(Session)[49][3]
    assert stored is None or isinstance(stored, dict)
    if operation == "write":
        assert stored[writer.OWNED_PREFIX]["source"]["sha256"] == EDITION["sha256"]


def test_interrupted_project_mutation_cannot_be_committed(pg_projects, monkeypatch):
    from seeding.cli import DomainTimeoutError

    _, Session = pg_projects
    before = snapshot(Session)
    original = writer.build_county_block

    def interrupt(county, edition):
        if county["county"] == "Kwale":
            raise DomainTimeoutError("synthetic project timeout")
        return original(county, edition)

    monkeypatch.setattr(writer, "build_county_block", interrupt)
    with Session() as db:
        with pytest.raises(DomainTimeoutError, match="synthetic project timeout"):
            writer.write(incoming(), EDITION, db)
        assert not db.dirty
        db.commit()
    assert snapshot(Session) == before


@pytest.mark.parametrize("fetch_ok", [True, False])
def test_actual_cli_records_project_commit_refusal_and_retry(
    pg_projects, monkeypatch, tmp_path, fetch_ok
):
    from contextlib import nullcontext
    from seeding import cli, freshness
    from seeding.config import SeedingSettings
    from seeding.domains import stalled_projects
    from seeding.domains.stalled_projects import fetcher

    engine, Session = pg_projects
    before = snapshot(Session)
    recs = [dict(c, reconciliation={"rows": 1}) for c in incoming()]

    def fetched(_settings, _client):
        if fetch_ok:
            freshness.mark_live("stalled_projects")
            return fetcher.FetchResult(ok=True, counties=recs, edition=EDITION)
        return fetcher._refuse(
            "synthetic_download_refusal", "retained previous edition"
        )

    monkeypatch.setattr(fetcher, "fetch", fetched)
    monkeypatch.setattr(
        stalled_projects, "create_http_client", lambda _s: nullcontext(None)
    )
    monkeypatch.setattr(cli, "SessionLocal", Session)
    monkeypatch.setattr(cli, "load_builtin_domains", lambda: None)
    with engine.begin() as db:
        db.execute(
            text(
                """CREATE FUNCTION refuse_project() RETURNS trigger AS $$
            BEGIN IF NEW.id = 49 THEN RAISE EXCEPTION 'synthetic project refusal'; END IF;
            RETURN NEW; END; $$ LANGUAGE plpgsql"""
            )
        )
        db.execute(
            text(
                "CREATE TRIGGER refuse_project BEFORE UPDATE ON entities FOR EACH ROW EXECUTE FUNCTION refuse_project()"
            )
        )
    settings = SeedingSettings(
        storage_path=tmp_path / "storage",
        cache_path=tmp_path / "cache",
        log_path=tmp_path / "seed.log",
        http_cache_enabled=False,
    )
    settings.ensure_directories()
    args = argparse.Namespace(
        domain=["stalled_projects"], all=False, dry_run=False, since=None
    )
    assert cli.run_seed_command(args, settings) == 1
    assert snapshot(Session) == before
    with Session() as db:
        failed = db.query(IngestionJob).one()
        assert failed.status == IngestionStatus.FAILED
        assert failed.items_updated == 0 and failed.finished_at is not None
        assert any("synthetic project refusal" in e for e in failed.errors)
        assert "cbirr_ingested" not in failed.meta
    with engine.begin() as db:
        db.execute(text("DROP TRIGGER refuse_project ON entities"))
    assert cli.run_seed_command(args, settings) == 0
    with Session() as db:
        retried = db.query(IngestionJob).order_by(IngestionJob.id.desc()).first()
        if fetch_ok:
            assert retried.status == IngestionStatus.COMPLETED
            assert retried.items_updated == 47
            assert retried.meta["cbirr_ingested"]["sha256"] == EDITION["sha256"]
        else:
            assert retried.status == IngestionStatus.COMPLETED_WITH_ERRORS
            assert retried.items_updated == 0
            assert retried.meta["cleared_legacy_keys"] == 47
            assert "cbirr_ingested" not in retried.meta
    if not fetch_ok:
        assert all(
            r[3][writer.OWNED_PREFIX] == before[pk][3][writer.OWNED_PREFIX]
            for pk, r in snapshot(Session).items()
        )


def add_excluded(Session, foreign_id=100):
    """Names/codes/slugs alone cannot claim Kenya's official county identity."""
    with Session() as db:
        ken = db.query(Country).filter_by(iso_code="KEN").one()
        foreign = Country(
            id=foreign_id,
            iso_code="SYN",
            name="Kenya",
            currency="XYZ",
            timezone="UTC",
            default_locale="en_US",
        )
        db.add(foreign)
        db.flush()
        cases = [
            (foreign.id, EntityType.COUNTY, "Nairobi County", "nairobi-001"),
            (foreign.id, EntityType.COUNTY, "Mombasa County", "mombasa-047"),
            (ken.id, EntityType.COUNTY, "Nairobi County Assembly", "nairobi-047"),
            (ken.id, EntityType.AGENCY, "Nairobi County", "agency-nairobi"),
            (ken.id, EntityType.COUNTY, "Nairob County", "typo-nairobi"),
            (ken.id, EntityType.COUNTY, "Unknown institution", "unknown-047"),
            (ken.id, EntityType.COUNTY, "", "nairobi-county"),
        ]
        for pk, (country_id, entity_type, name, slug) in enumerate(cases, 1000):
            db.add(
                Entity(
                    id=pk,
                    country_id=country_id,
                    type=entity_type,
                    canonical_name=name,
                    slug=slug,
                    meta={
                        "county_reference": {"code": "047"},
                        "stalled_projects": {
                            "schema": 2,
                            "source": {"sha256": "excluded-edition"},
                            "rows": [
                                {
                                    "project_name": "Excluded source-backed project",
                                    "source_url": "https://example.test/foreign.pdf",
                                    "source_page": 9,
                                }
                            ],
                        },
                        "stalled_projects_count": 1,
                        "foreign": {"values": [0, None, False]},
                    },
                )
            )
        db.commit()


@pytest.mark.parametrize("operation", ["write", "clear", "legacy_clear", "edition"])
@pytest.mark.parametrize("kenya_id,foreign_id", [(100, 200), (200, 100)])
@pytest.mark.parametrize("dry_run", [False, True])
def test_all_operations_use_kenya_official_identity(
    pg_projects, operation, kenya_id, foreign_id, dry_run
):
    engine, Session = pg_projects
    protected = controls(engine)
    with Session() as db:
        old = db.query(Country).filter_by(iso_code="KEN").one()
        old.iso_code = "OLD"
        db.flush()
        ken = Country(
            id=kenya_id,
            iso_code="KEN",
            name="Synthetic Kenya",
            currency="KES",
            timezone="Africa/Nairobi",
            default_locale="en_KE",
        )
        db.add(ken)
        db.flush()
        for entity in db.query(Entity):
            entity.country_id = ken.id
        db.commit()
    add_excluded(Session, foreign_id)
    before = snapshot(Session)
    with Session() as db:
        if operation == "edition":
            assert writer.published_edition(db) == {"sha256": "old"}
        else:
            result = run_operation(db, operation, dry_run=dry_run)
            assert result == (
                {"counties": 47, "rows": 47, "unmatched": []}
                if operation == "write"
                else {"entities": 47, "keys": 94 if operation == "clear" else 47}
            )
    after = snapshot(Session)
    assert {pk: row for pk, row in after.items() if pk >= 1000} == {
        pk: row for pk, row in before.items() if pk >= 1000
    }
    assert controls(engine) == protected
    for pk, row in after.items():
        if pk >= 1000:
            continue
        assert row[:3] == before[pk][:3]
        if operation == "edition" or dry_run:
            assert row == before[pk]
        elif operation == "write":
            assert row[3][writer.OWNED_PREFIX]["rows"][0]["estimated_value_kes"] == 0
            assert row[3][writer.OWNED_PREFIX]["rows"][0]["amount_paid_kes"] is None
            assert row[3][writer.OWNED_PREFIX]["source"]["sha256"] == EDITION["sha256"]
        elif operation == "clear":
            assert not writer.owned_keys(row[3])
        else:
            assert row[3][writer.OWNED_PREFIX] == before[pk][3][writer.OWNED_PREFIX]
            assert "stalled_projects_count" not in row[3]
        assert {
            k: v for k, v in row[3].items() if not k.startswith(writer.OWNED_PREFIX)
        } == {
            k: v
            for k, v in before[pk][3].items()
            if not k.startswith(writer.OWNED_PREFIX)
        }


@pytest.mark.parametrize("operation", ["write", "clear", "legacy_clear", "edition"])
def test_missing_kenya_refuses_without_borrowing_country(pg_projects, operation):
    engine, Session = pg_projects
    with Session() as db:
        ken = db.query(Country).filter_by(iso_code="KEN").one()
        ken.iso_code = "SYN"
        ken.name = "Kenya"
        db.commit()
    before, protected = snapshot(Session), controls(engine)
    with Session() as db:
        with pytest.raises(ValueError, match="Kenya.*KEN"):
            writer.published_edition(db) if operation == "edition" else run_operation(
                db, operation
            )
    assert snapshot(Session) == before and controls(engine) == protected


@pytest.mark.parametrize("operation", ["write", "clear", "legacy_clear", "edition"])
def test_duplicate_official_identity_refuses_atomically(pg_projects, operation):
    engine, Session = pg_projects
    with Session() as db:
        ken = db.query(Country).filter_by(iso_code="KEN").one()
        db.add(
            Entity(
                id=2000,
                country_id=ken.id,
                type=EntityType.COUNTY,
                canonical_name="Nairobi City County",
                slug="duplicate-nairobi",
                meta={"stalled_projects_count": 3},
            )
        )
        db.commit()
    before, protected = snapshot(Session), controls(engine)
    with Session() as db:
        with pytest.raises(ValueError, match="Ambiguous.*047"):
            writer.published_edition(db) if operation == "edition" else run_operation(
                db, operation
            )
        db.rollback()
        db.commit()
    assert snapshot(Session) == before and controls(engine) == protected


def test_only_excluded_editions_cannot_certify_kenya(pg_projects):
    _, Session = pg_projects
    add_excluded(Session)
    with Session() as db:
        for entity in db.query(Entity).filter(Entity.id < 1000):
            entity.meta = {
                k: v
                for k, v in entity.meta.items()
                if not k.startswith(writer.OWNED_PREFIX)
            }
        db.commit()
    with Session() as db:
        assert writer.published_edition(db) is None


def test_official_aliases_preserve_legacy_pk_slug_and_projects(pg_projects):
    from main import _resolve_county_entity

    _, Session = pg_projects
    with Session() as db:
        for entity in db.query(Entity):
            source_county = next(
                c
                for c in incoming()
                if c["county"] == writer.normalise_county(entity.canonical_name)
            )
            entity.meta = {
                **entity.meta,
                writer.OWNED_PREFIX: writer.build_county_block(source_county, EDITION),
            }
        db.get(Entity, 3).canonical_name = "Nairobi City County"
        db.get(Entity, 3).slug = "nairobi-001"
        db.get(Entity, 4).slug = "mombasa-047"
        db.query(Entity).filter_by(
            canonical_name="Tharaka Nithi County"
        ).one().canonical_name = "Tharaka-Nithi County"
        db.query(Entity).filter_by(
            canonical_name="Murang'a County"
        ).one().canonical_name = "Murang’a County"
        db.commit()
    before = snapshot(Session)
    with Session() as db:
        for route, pk in [
            ("001", 3),
            ("047", 4),
            ("code:047", 3),
            ("code:001", 4),
            ("nairobi-001", 3),
            ("mombasa-047", 4),
        ]:
            assert _resolve_county_entity(db, route).id == pk
        assert run_operation(db, "legacy_clear") == {"entities": 47, "keys": 47}
    after = snapshot(Session)
    for pk in before:
        assert after[pk][:3] == before[pk][:3]
        assert after[pk][3][writer.OWNED_PREFIX] == before[pk][3][writer.OWNED_PREFIX]
    with Session() as db:
        assert run_operation(db, "write") == {
            "counties": 47,
            "rows": 47,
            "unmatched": [],
        }


def test_edition_refreshes_stale_identity_map(pg_projects):
    _, Session = pg_projects
    with Session() as stale:
        held = stale.query(Entity).all()
        assert held[0].meta[writer.OWNED_PREFIX]["source"] == {"sha256": "old"}
        with Session() as fresh:
            run_operation(fresh, "clear")
        assert writer.published_edition(stale) is None


@pytest.mark.parametrize("operation", ["write", "clear", "legacy_clear", "edition"])
@pytest.mark.parametrize("pending", ["id", "iso", "new", "delete"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_pending_country_cannot_borrow_or_commit_identity(
    pg_projects, operation, pending, dry_run
):
    engine, Session = pg_projects
    add_excluded(Session)
    before, protected = snapshot(Session), controls(engine)
    with Session() as db:
        ken = db.query(Country).filter_by(iso_code="KEN").one()
        if pending == "id":
            ken.id = 100  # Existing foreign country's PK.
        elif pending == "iso":
            ken.iso_code = "OLD"
        elif pending == "new":
            db.add(
                Country(
                    iso_code="NEW",
                    name="Pending country",
                    currency="XYZ",
                    timezone="UTC",
                    default_locale="en_US",
                )
            )
        else:
            db.delete(ken)
        with pytest.raises(ValueError, match="pending.*Country"):
            if operation == "edition":
                writer.published_edition(db)
            else:
                run_operation(db, operation, dry_run=dry_run)
        if dry_run or operation == "edition":
            assert db.dirty or db.new or db.deleted  # Read refusal keeps caller work.
        else:
            assert not db.dirty and not db.new and not db.deleted
        db.rollback()
        db.commit()
    assert snapshot(Session) == before and controls(engine) == protected
    with Session() as db:
        assert db.query(Country).filter_by(iso_code="KEN").one().id == 1
        assert db.query(Country).count() == 2
