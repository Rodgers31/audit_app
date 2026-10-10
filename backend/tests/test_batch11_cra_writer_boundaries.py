"""CRA writer replay identity and ownership boundaries on owned PostgreSQL.

Each case acquires native CRA ownership with the real shared ``enter_domain``
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
from seeding.domains.cra import parser, source, writer
from seeding.exclusion import DomainExecution, enter_domain
from seeding.types import DomainRunContext
from test_batch11_native_sources import cra_url  # noqa: F401  (module-scoped owned PostgreSQL)

PDF = Path(__file__).resolve().parents[2] / "docs/admin/implementation/batch11-issue-602-evidence/fixtures/cra-fy2026-27.pdf"
PAYLOAD = PDF.read_bytes()
PARSED = parser.parse_publication(PAYLOAD)
EFFECTS = ("source_documents", "extractions", "budget_lines", "economic_indicators", "admin_audit_log")


@contextmanager
def owned(cra_url, dry_run=False):
    name = "batch11_602_" + uuid4().hex
    admin = create_engine(cra_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{make_url(cra_url).database}"'))
    engine = create_engine(make_url(cra_url).set(database=name))
    factory = sessionmaker(bind=engine)
    execution = None
    try:
        with factory.begin() as db:
            db.add(Country(iso_code="KEN", name="Kenya", currency="KES", timezone="Africa/Nairobi", default_locale="en"))
        execution = enter_domain(factory, "cra", dry_run)
        with factory.begin() as db:
            # The exact observation shape the native CLI writes before a handler.
            job = IngestionJob(domain="cra", status=IngestionStatus.RUNNING, dry_run=dry_run,
                started_at=datetime.now(timezone.utc), items_processed=0, items_created=0, items_updated=0,
                errors=[], meta={"since": None, "seeding_claim_id": str(execution.identity)})
            db.add(job)
            db.flush()
            job_id = job.id
        yield engine, factory, execution, DomainRunContext(since=None, dry_run=dry_run, job_id=job_id)
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


def test_valid_creation_then_exact_replay_is_unchanged(cra_url):
    with owned(cra_url) as (engine, factory, _, ctx):
        assert persist(factory, ctx) == {"created": 1, "unchanged": 0}
        assert persist(factory, ctx) == {"created": 0, "unchanged": 1}
        assert counts(engine) == {"source_documents": 1, "extractions": 1, "budget_lines": 0,
                                  "economic_indicators": 0, "admin_audit_log": 0}


@pytest.mark.parametrize("field,value", [("schema_version", "true"), ("page_number", "39.0"),
    ("schema_version", "1.0"), ("table", "5.2"), ("amounts_kes", "{}"), ("extra", "null")])
def test_replay_refuses_stored_extraction_with_changed_primitive_type(cra_url, field, value):
    with owned(cra_url) as (engine, factory, _, ctx):
        persist(factory, ctx)
        # Mutate in SQL: an ORM assignment of a Python-equal dict (True == 1,
        # 39.0 == 39) is skipped as unchanged and would never reach the row.
        with engine.begin() as c:
            c.execute(text("UPDATE extractions SET extracted_json=jsonb_set(extracted_json, CAST(:path AS text[]), CAST(:value AS jsonb))"),
                      {"path": "{" + field + "}", "value": value})
            stored = c.execute(text("SELECT extracted_json->:f FROM extractions"), {"f": field}).scalar_one()
            raw = c.execute(text("SELECT (extracted_json->:f)::text FROM extractions"), {"f": field}).scalar_one()
        assert raw == value and stored == {"true": True, "39.0": 39.0, "1.0": 1.0, "5.2": 5.2, "{}": {}, "null": None}[value]
        with engine.connect() as c:
            before = c.execute(text("SELECT id,extracted_json::text,page_number FROM extractions")).all()
        with pytest.raises(source.CraSourceRefused, match="existing source-bound extraction differs"):
            persist(factory, ctx)
        with engine.connect() as c:
            assert c.execute(text("SELECT id,extracted_json::text,page_number FROM extractions")).all() == before
        assert counts(engine)["extractions"] == 1 and counts(engine)["source_documents"] == 1


def test_replay_refuses_changed_extraction_columns(cra_url):
    with owned(cra_url) as (engine, factory, _, ctx):
        persist(factory, ctx)
        with engine.begin() as c:
            c.execute(text("UPDATE extractions SET page_number=40"))
        with pytest.raises(source.CraSourceRefused, match="existing source-bound extraction differs"):
            persist(factory, ctx)
        assert counts(engine)["extractions"] == 1


def test_lock_released_before_persist_refuses_with_claim_retained(cra_url):
    with owned(cra_url) as (engine, factory, execution, ctx):
        execution.close()
        with pytest.raises(source.CraSourceRefused, match="execution lock"):
            persist(factory, ctx)
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)
        with factory() as db:
            claim = db.get(SeedingDomainClaim, execution.identity)
            # Never auto-released: the durable claim stays for reconciliation.
            assert claim.released_at is None and claim.returned_at is None


@pytest.mark.parametrize("mutation", ["native_dispatch_metadata", "legacy_writer_metadata", "unknown_metadata",
                                      "stale_job", "future_job"])
def test_observation_shape_must_match_the_native_owner(cra_url, mutation):
    with owned(cra_url) as (engine, factory, _, ctx):
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
        with pytest.raises(source.CraSourceRefused):
            persist(factory, ctx)
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)


@pytest.mark.parametrize("fetched_at", [datetime(1970, 1, 1, tzinfo=timezone.utc),
    "tomorrow", datetime(2026, 10, 10, 12, 0), "2026-10-10T12:00:00+00:00", True, None])
def test_fetched_at_must_be_an_aware_time_inside_the_owned_run(cra_url, fetched_at):
    if fetched_at == "tomorrow":
        fetched_at = datetime.now(timezone.utc) + timedelta(days=1)
    with owned(cra_url) as (engine, factory, _, ctx):
        with pytest.raises(source.CraSourceRefused, match="fetch time"):
            with factory.begin() as db:
                writer.persist(db, ctx, PAYLOAD, PARSED, fetched_at)
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)


def test_dry_run_owner_validates_without_effects(cra_url):
    with owned(cra_url, dry_run=True) as (engine, factory, _, ctx):
        assert persist(factory, ctx) == {"created": 0, "unchanged": 0}
        assert counts(engine) == dict.fromkeys(EFFECTS, 0)


def test_writer_lock_key_is_the_shared_execution_key(cra_url):
    engine = create_engine(cra_url)
    try:
        assert writer.execution_lock_key("cra") == DomainExecution(sessionmaker(bind=engine), "cra", uuid4()).key
    finally:
        engine.dispose()


@pytest.mark.parametrize("mutation", ["tampered_amount_and_parser_hash", "other_parser_version", "foreign_extractor"])
def test_any_other_extraction_on_the_cra_document_refuses_instead_of_appending(cra_url, mutation):
    # Spec-review reproduction: replay matched only rows carrying the current
    # parser hash, so a tampered row with another hash survived beside a new one.
    with owned(cra_url) as (engine, factory, _, ctx):
        persist(factory, ctx)
        with engine.begin() as c:
            if mutation == "tampered_amount_and_parser_hash":
                c.execute(text("UPDATE extractions SET extracted_json=jsonb_set(jsonb_set(extracted_json,'{amounts_kes,national_government}','\"9\"'),'{parser_sha256}','\"0000\"')"))
            elif mutation == "other_parser_version":
                c.execute(text("UPDATE extractions SET extracted_json=jsonb_set(extracted_json,'{parser_sha256}','\"1111\"')"))
            else:
                c.execute(text("UPDATE extractions SET extractor='camelot'"))
            before = c.execute(text("SELECT id,extractor,extracted_json::text FROM extractions ORDER BY id")).all()
        with pytest.raises(source.CraSourceRefused, match="existing source-bound extraction differs"):
            persist(factory, ctx)
        with engine.connect() as c:
            assert c.execute(text("SELECT id,extractor,extracted_json::text FROM extractions ORDER BY id")).all() == before


def test_a_contender_holding_the_lock_key_is_not_the_entering_runner(cra_url):
    # Standards-review reproduction: the runner's lock backend dies, a contender
    # takes the same key (as it would just before its claim insert fails), and the
    # original runner must not write under a claim it can no longer acknowledge.
    with owned(cra_url) as (engine, factory, execution, ctx):
        with engine.connect() as c:
            assert c.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": execution.pid}) is True
        with pytest.raises(Exception):
            execution.close()  # its lock connection is gone; close() reports that and forgets it
        contender = DomainExecution(factory, "cra", uuid4())
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
            with pytest.raises(source.CraSourceRefused, match="execution lock"):
                persist(factory, ctx)
            assert counts(engine) == dict.fromkeys(EFFECTS, 0)
        finally:
            contender.close()
