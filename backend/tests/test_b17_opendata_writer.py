"""OpenData writer replay identity and ownership boundaries on owned PostgreSQL.

Each case acquires native OpenData ownership with the real shared ``enter_domain``
and the real parser output of the reviewed PDF, then calls the writer the way
the handler does, inside one transaction. A refusal must leave zero effects.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from models import Country, IngestionJob, IngestionStatus, SeedingDomainClaim
from seeding.domains.opendata import parser, source, writer
from seeding.exclusion import DomainExecution, enter_domain
from seeding.types import DomainRunContext
from test_b17_opendata_native import opendata_url  # noqa: F401  (module-scoped owned PostgreSQL)

PDF = Path(__file__).resolve().parents[2] / "backend/tests/fixtures/opendata/Chapter-5-Public-Finance.xlsx"
PAYLOAD = PDF.read_bytes()
PARSED = parser.parse_publication(PAYLOAD)
EFFECTS = ("source_documents", "extractions", "budget_lines", "economic_indicators", "admin_audit_log")


@contextmanager
def owned(opendata_url, dry_run=False, before_enter=None):
    name = "batch11_602_" + uuid4().hex
    admin = create_engine(opendata_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{make_url(opendata_url).database}"'))
    engine = create_engine(make_url(opendata_url).set(database=name))
    factory = sessionmaker(bind=engine)
    execution = None
    try:
        with factory.begin() as db:
            db.add(Country(iso_code="KEN", name="Kenya", currency="KES", timezone="Africa/Nairobi", default_locale="en"))
        if before_enter is not None:
            before_enter(engine)
        execution = enter_domain(factory, "opendata", dry_run)
        with factory.begin() as db:
            # The exact observation shape the native CLI writes before a handler.
            job = IngestionJob(domain="opendata", status=IngestionStatus.RUNNING, dry_run=dry_run,
                started_at=datetime.now(timezone.utc), items_processed=0, items_created=0, items_updated=0,
                errors=[], meta={"since": None, "seeding_claim_id": str(execution.identity)})
            db.add(job)
            db.flush()
            job_id = job.id
        yield engine, factory, execution, DomainRunContext(since=None, dry_run=dry_run, job_id=job_id, ownership=execution)
    finally:
        if execution is not None:
            execution.close()
        engine.dispose()
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def counts(engine):
    with engine.connect() as c:
        return {t: c.scalar(text("SELECT count(*) FROM " + t)) for t in EFFECTS}


def persist(factory, ctx, parsed=PARSED, fetched_at=None):
    with factory.begin() as db:
        return writer.persist(db, ctx, PAYLOAD, parsed, fetched_at or datetime.now(timezone.utc))


def test_valid_creation_then_exact_replay_is_unchanged(opendata_url):
    with owned(opendata_url) as (engine, factory, _, ctx):
        assert persist(factory, ctx) == {"created": 1, "unchanged": 0}
        assert persist(factory, ctx) == {"created": 0, "unchanged": 1}
        assert counts(engine) == {"source_documents": 1, "extractions": 1, "budget_lines": 0,
                                  "economic_indicators": 0, "admin_audit_log": 0}


@pytest.mark.parametrize("field,value", [("numeric_cells", "true"), ("missing_cells", "83.0"),
    ("numeric_cells", "2125.0"), ("table", "5.13"), ("rows", "{}"), ("extra", "null")])
def test_replay_refuses_stored_extraction_with_changed_primitive_type(opendata_url, field, value):
    with owned(opendata_url) as (engine, factory, _, ctx):
        persist(factory, ctx)
        # Mutate in SQL: an ORM assignment of a Python-equal dict (True == 1,
        # 39.0 == 39) is skipped as unchanged and would never reach the row.
        with engine.begin() as c:
            c.execute(text("UPDATE extractions SET extracted_json=jsonb_set(extracted_json, CAST(:path AS text[]), CAST(:value AS jsonb))"),
                      {"path": "{" + field + "}", "value": value})
            stored = c.execute(text("SELECT extracted_json->:f FROM extractions"), {"f": field}).scalar_one()
            raw = c.execute(text("SELECT (extracted_json->:f)::text FROM extractions"), {"f": field}).scalar_one()
        assert raw == value and stored == {"true": True, "83.0": 83.0, "2125.0": 2125.0, "5.13": 5.13, "{}": {}, "null": None}[value]
        with engine.connect() as c:
            before = c.execute(text("SELECT id,extracted_json::text,page_number FROM extractions")).all()
        with pytest.raises(source.OpenDataSourceRefused, match="existing source-bound extraction differs"):
            persist(factory, ctx)
        with engine.connect() as c:
            assert c.execute(text("SELECT id,extracted_json::text,page_number FROM extractions")).all() == before
        assert counts(engine)["extractions"] == 1 and counts(engine)["source_documents"] == 1


def test_replay_refuses_changed_extraction_columns(opendata_url):
    with owned(opendata_url) as (engine, factory, _, ctx):
        persist(factory, ctx)
        with engine.begin() as c:
            c.execute(text("UPDATE extractions SET page_number=40"))
        with pytest.raises(source.OpenDataSourceRefused, match="existing source-bound extraction differs"):
            persist(factory, ctx)
        assert counts(engine)["extractions"] == 1


def test_lock_released_before_persist_refuses_with_claim_retained(opendata_url):
    with owned(opendata_url) as (engine, factory, execution, ctx):
        execution.close()
        with pytest.raises(source.OpenDataSourceRefused, match="execution lock"):
            persist(factory, ctx)
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)
        with factory() as db:
            claim = db.get(SeedingDomainClaim, execution.identity)
            # Never auto-released: the durable claim stays for reconciliation.
            assert claim.released_at is None and claim.returned_at is None


@pytest.mark.parametrize("mutation", ["native_dispatch_metadata", "legacy_writer_metadata", "unknown_metadata",
                                      "stale_job", "future_job"])
def test_observation_shape_must_match_the_native_owner(opendata_url, mutation):
    with owned(opendata_url) as (engine, factory, _, ctx):
        with factory.begin() as db:
            job = db.get(IngestionJob, ctx.job_id)
            if mutation == "native_dispatch_metadata":
                job.meta = {**job.meta, "dispatch_command_id": str(uuid4()), "dispatch_claim_token": str(uuid4())}
            elif mutation == "legacy_writer_metadata":
                job.meta = {**job.meta, "writer": "legacy_etl", "counts_scope": "ownership_only"}
            elif mutation == "unknown_metadata":
                job.meta = {**job.meta, "operator": "x"}
            elif mutation == "stale_job":
                job.started_at = datetime(1970, 1, 1, tzinfo=timezone.utc)
            else:
                job.started_at = datetime.now(timezone.utc) + timedelta(days=1)
        with pytest.raises(source.OpenDataSourceRefused):
            persist(factory, ctx)
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)


@pytest.mark.parametrize("fetched_at", [datetime(1970, 1, 1, tzinfo=timezone.utc),
    "tomorrow", datetime(2026, 10, 10, 12, 0), "2026-10-10T12:00:00+00:00", True, None])
def test_fetched_at_must_be_an_aware_time_inside_the_owned_run(opendata_url, fetched_at):
    if fetched_at == "tomorrow":
        fetched_at = datetime.now(timezone.utc) + timedelta(days=1)
    with owned(opendata_url) as (engine, factory, _, ctx):
        with pytest.raises(source.OpenDataSourceRefused, match="fetch time"):
            with factory.begin() as db:
                writer.persist(db, ctx, PAYLOAD, PARSED, fetched_at)
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)


def test_dry_run_owner_validates_without_effects(opendata_url):
    with owned(opendata_url, dry_run=True) as (engine, factory, _, ctx):
        assert persist(factory, ctx) == {"created": 0, "unchanged": 0}
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)


def test_writer_lock_key_is_the_shared_execution_key(opendata_url):
    engine = create_engine(opendata_url)
    try:
        assert writer.execution_lock_key("opendata") == DomainExecution(sessionmaker(bind=engine), "opendata", uuid4()).key
    finally:
        engine.dispose()


@pytest.mark.parametrize("mutation", ["tampered_amount_and_parser_hash", "other_parser_version", "foreign_extractor"])
def test_any_other_extraction_on_the_opendata_document_refuses_instead_of_appending(opendata_url, mutation):
    # Spec-review reproduction: replay matched only rows carrying the current
    # parser hash, so a tampered row with another hash survived beside a new one.
    with owned(opendata_url) as (engine, factory, _, ctx):
        persist(factory, ctx)
        with engine.begin() as c:
            if mutation == "tampered_amount_and_parser_hash":
                c.execute(text("UPDATE extractions SET extracted_json=jsonb_set(jsonb_set(extracted_json,'{rows,47,cells,AH,raw}','\"9\"'),'{parser_sha256}','\"0000\"')"))
            elif mutation == "other_parser_version":
                c.execute(text("UPDATE extractions SET extracted_json=jsonb_set(extracted_json,'{parser_sha256}','\"1111\"')"))
            else:
                c.execute(text("UPDATE extractions SET extractor='camelot'"))
            before = c.execute(text("SELECT id,extractor,extracted_json::text FROM extractions ORDER BY id")).all()
        with pytest.raises(source.OpenDataSourceRefused, match="existing source-bound extraction differs"):
            persist(factory, ctx)
        with engine.connect() as c:
            assert c.execute(text("SELECT id,extractor,extracted_json::text FROM extractions ORDER BY id")).all() == before


def test_a_contender_holding_the_lock_key_is_not_the_entering_runner(opendata_url):
    # Standards-review reproduction: the runner's lock backend dies, a contender
    # takes the same key (as it would just before its claim insert fails), and the
    # original runner must not write under a claim it can no longer acknowledge.
    with owned(opendata_url) as (engine, factory, execution, ctx):
        with engine.connect() as c:
            assert c.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": execution.pid}) is True
        with pytest.raises(Exception):
            execution.close()  # its lock connection is gone; close() reports that and forgets it
        contender = DomainExecution(factory, "opendata", uuid4())
        deadline = __import__("time").monotonic() + 10
        while True:
            try:
                contender.open()
                break
            except Exception:
                if __import__("time").monotonic() > deadline:
                    raise
        try:
            assert contender.continuous() is True
            with pytest.raises(source.OpenDataSourceRefused, match="execution lock"):
                persist(factory, ctx)
            assert counts(engine) == dict.fromkeys(EFFECTS, 0)
        finally:
            contender.close()


def test_observation_before_dispatch_entry_refuses(opendata_url):
    with owned(opendata_url) as (engine, factory, execution, ctx):
        with engine.begin() as db:
            db.execute(text("UPDATE seeding_domain_claims SET acquired_at=entered_at-interval '1 minute' WHERE id=:id"),
                       {"id": execution.identity})
            db.execute(text("UPDATE ingestion_jobs SET started_at=(SELECT acquired_at FROM seeding_domain_claims WHERE id=:id) WHERE id=:job"),
                       {"id": execution.identity, "job": ctx.job_id})
        with pytest.raises(source.OpenDataSourceRefused, match="observation time"):
            persist(factory, ctx)
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)


def test_same_url_with_different_artifact_refuses_instead_of_append(opendata_url):
    with owned(opendata_url) as (engine, factory, _, ctx):
        persist(factory, ctx)
        with engine.begin() as db:
            db.execute(text("UPDATE source_documents SET metadata=jsonb_set(metadata,'{artifact_sha256}','\"different\"')"))
        before = counts(engine)
        with pytest.raises(source.OpenDataSourceRefused, match="provenance differs"):
            persist(factory, ctx)
        assert counts(engine) == before


def test_preopened_contender_cannot_impersonate_dead_runner(opendata_url):
    from sqlalchemy.exc import SQLAlchemyError
    holders = []
    def preopen(engine):
        connection = engine.connect()
        connection.execute(text("SELECT txid_current()"))
        holders.append(connection)
    try:
        with owned(opendata_url, before_enter=preopen) as (engine, factory, execution, ctx):
            contender = holders[0]
            with engine.connect() as db:
                entered = db.scalar(text("SELECT entered_at FROM seeding_domain_claims WHERE id=:id"), {"id": execution.identity})
                assert db.scalar(text("SELECT xact_start FROM pg_stat_activity WHERE pid=:pid"),
                                 {"pid": contender.scalar(text("SELECT pg_backend_pid()"))}) <= entered
                assert db.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": execution.pid}) is True
            with pytest.raises(SQLAlchemyError):
                execution.close()
            assert contender.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": execution.key}) is True
            with pytest.raises(source.OpenDataSourceRefused, match="execution lock"):
                persist(factory, ctx)
            assert counts(engine) == dict.fromkeys(EFFECTS, 0)
            contender.close()
            holders.clear()
    finally:
        for holder in holders:
            holder.close()


@pytest.mark.parametrize("mutation", ["missing", "wrong_nonce", "wrong_owner"])
def test_claim_reader_cannot_reconstruct_live_ownership(opendata_url, mutation):
    with owned(opendata_url) as (engine, factory, execution, ctx):
        if mutation == "missing":
            ctx.ownership = None
        elif mutation == "wrong_nonce":
            execution.entry = uuid4()
        else:
            ctx.ownership = DomainExecution(factory, "opendata", execution.identity)
        with pytest.raises(source.OpenDataSourceRefused, match="execution lock"):
            persist(factory, ctx)
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)


@pytest.mark.parametrize("association", ["country", "publisher"])
def test_same_source_url_with_foreign_association_refuses_replay(opendata_url, association):
    with owned(opendata_url) as (engine, factory, _, ctx):
        assert persist(factory, ctx) == {"created": 1, "unchanged": 0}
        with engine.begin() as db:
            if association == "country":
                other = db.scalar(text("INSERT INTO countries(iso_code,name,currency,timezone,default_locale) "
                    "VALUES ('UGA','Uganda','UGX','Africa/Kampala','en') RETURNING id"))
                db.execute(text("UPDATE source_documents SET country_id=:country"), {"country": other})
            else:
                db.execute(text("UPDATE source_documents SET publisher='Unreviewed publisher'"))
            before = db.execute(text("SELECT id,country_id,publisher,url FROM source_documents ORDER BY id")).all()
        with pytest.raises(source.OpenDataSourceRefused, match="provenance differs"):
            persist(factory, ctx)
        with engine.connect() as db:
            assert db.execute(text("SELECT id,country_id,publisher,url FROM source_documents ORDER BY id")).all() == before
        assert counts(engine)["source_documents"] == counts(engine)["extractions"] == 1


@pytest.mark.parametrize("table,change", [
    ("source_documents", "NEW.publisher := 'Unreviewed publisher';"),
    ("source_documents", "NEW.url := 'https://unreviewed.invalid/changed';"),
    ("extractions", "NEW.extracted_json := jsonb_set(NEW.extracted_json,'{numeric_cells}','true');"),
    ("extractions", "NEW.extractor := 'unreviewed-extractor';"),
    ("source_documents", "NEW.created_at := NEW.created_at + interval '1 second';"),
    ("extractions", "NEW.created_at := NEW.created_at + interval '1 second';"),
])
def test_inserted_source_values_are_read_back_before_success(opendata_url, table, change):
    with owned(opendata_url) as (engine, factory, _, ctx):
        with engine.begin() as db:
            db.execute(text("CREATE FUNCTION b17_change_insert() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                            + change + " RETURN NEW; END $$"))
            db.execute(text(f"CREATE TRIGGER b17_change_insert BEFORE INSERT ON {table} "
                            "FOR EACH ROW EXECUTE FUNCTION b17_change_insert()"))
        with pytest.raises(source.OpenDataSourceRefused, match="readback"):
            persist(factory, ctx)
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)


@pytest.mark.parametrize("table,change", [
    ("source_documents", "UPDATE source_documents SET publisher='Unreviewed publisher' WHERE id=NEW.id;"),
    ("extractions", "UPDATE extractions SET extracted_json=jsonb_set(extracted_json,'{numeric_cells}','true') WHERE id=NEW.id;"),
    ("extractions", "DELETE FROM extractions WHERE id=NEW.id;"),
])
def test_deferred_insert_changes_are_checked_before_commit(opendata_url, table, change):
    with owned(opendata_url) as (engine, factory, _, ctx):
        with engine.begin() as db:
            db.execute(text("CREATE FUNCTION b17_defer_insert() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                            + change + " RETURN NULL; END $$"))
            db.execute(text(f"CREATE CONSTRAINT TRIGGER b17_defer_insert AFTER INSERT ON {table} "
                            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION b17_defer_insert()"))
        with pytest.raises(source.OpenDataSourceRefused, match="readback"):
            persist(factory, ctx)
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)


@pytest.mark.parametrize("table", ["source_documents", "extractions"])
def test_suppressed_insert_cannot_report_success(opendata_url, table):
    from sqlalchemy.exc import SQLAlchemyError
    with owned(opendata_url) as (engine, factory, _, ctx):
        with engine.begin() as db:
            db.execute(text("CREATE FUNCTION b17_suppress_insert() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$"))
            db.execute(text(f"CREATE TRIGGER b17_suppress_insert BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION b17_suppress_insert()"))
        with pytest.raises((source.OpenDataSourceRefused, SQLAlchemyError)):
            persist(factory, ctx)
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)


@pytest.mark.parametrize("table", ["source_documents", "extractions"])
def test_deferred_unexpected_sibling_is_refused(opendata_url, table):
    with owned(opendata_url) as (engine, factory, _, ctx):
        if table == "source_documents":
            change = """IF NEW.title NOT LIKE '%unexpected sibling%' THEN
                INSERT INTO source_documents(country_id,publisher,title,url,file_path,fetch_date,md5,doc_type,status,
                    content_type,http_status,last_verified_at,last_seen_at,metadata,created_at)
                SELECT country_id,publisher,title || ' (unexpected sibling)',url,file_path,fetch_date,md5,doc_type,status,
                    content_type,http_status,last_verified_at,last_seen_at,metadata,created_at
                FROM source_documents WHERE id=NEW.id; END IF;"""
        else:
            change = """IF NEW.extractor <> 'unexpected-sibling' THEN
                INSERT INTO extractions(source_document_id,page_number,extracted_json,extractor,confidence,created_at)
                SELECT source_document_id,page_number,extracted_json,'unexpected-sibling',confidence,created_at
                FROM extractions WHERE id=NEW.id; END IF;"""
        with engine.begin() as db:
            db.execute(text("CREATE FUNCTION b17_duplicate_insert() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                            + change + " RETURN NULL; END $$"))
            db.execute(text(f"CREATE CONSTRAINT TRIGGER b17_duplicate_insert AFTER INSERT ON {table} "
                            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION b17_duplicate_insert()"))
        with pytest.raises(source.OpenDataSourceRefused, match="readback"):
            persist(factory, ctx)
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)


def test_new_write_and_replay_use_the_real_non_utc_session_zone(opendata_url):
    from sqlalchemy import event
    def configure(engine):
        @event.listens_for(engine, "checkout")
        def set_zone(connection, record, proxy):
            with connection.cursor() as cursor:
                cursor.execute("SET TIME ZONE 'Africa/Nairobi'")
            connection.commit()
    # Set the zone before acquiring ownership AND creating the naive-column job;
    # changing it only after job creation invalidates the existing time guard.
    with owned(opendata_url, before_enter=configure) as (engine, factory, _, ctx):
        with factory() as db:
            assert db.scalar(text("SHOW TimeZone")) == "Africa/Nairobi"
        assert persist(factory, ctx) == {"created": 1, "unchanged": 0}
        assert persist(factory, ctx) == {"created": 0, "unchanged": 1}
        assert counts(engine)["source_documents"] == counts(engine)["extractions"] == 1


@pytest.mark.parametrize("model", ["source", "extraction"])
def test_orm_hook_cannot_rewrite_both_intent_and_persisted_json(opendata_url, model):
    from copy import deepcopy
    from sqlalchemy import event
    from models import SourceDocument, Extraction
    target = SourceDocument if model == "source" else Extraction
    def alter(mapper, connection, row):
        if model == "source":
            row.meta["verification_status"] = "tampered-before-insert"
        else:
            row.extracted_json["numeric_cells"] = True
    with owned(opendata_url) as (engine, factory, _, ctx):
        event.listen(target, "before_insert", alter)
        try:
            with pytest.raises(source.OpenDataSourceRefused, match="readback"):
                persist(factory, ctx, parsed=deepcopy(PARSED))
        finally:
            event.remove(target, "before_insert", alter)
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)


@pytest.mark.parametrize("field,value", [("numeric_cells", True), ("artifact_sha256", "a" * 64)])
def test_parent_flush_cannot_change_validated_caller_observations(opendata_url, field, value):
    from copy import deepcopy
    from sqlalchemy import event
    from models import SourceDocument
    supplied = deepcopy(PARSED)
    def alter(mapper, connection, row):
        supplied[field] = value
    with owned(opendata_url) as (engine, factory, _, ctx):
        event.listen(SourceDocument, "before_insert", alter)
        try:
            with pytest.raises(source.OpenDataSourceRefused):
                persist(factory, ctx, parsed=supplied)
        finally:
            event.remove(SourceDocument, "before_insert", alter)
        assert supplied[field] == value
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)
