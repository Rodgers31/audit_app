"""Append source-bound workbook cells; never replace budget or revenue facts.

Ownership the writer re-proves on every call, on the writing transaction:
  * the observation is the exact RUNNING native or dispatch IngestionJob the CLI
    wrote for this claim, with that kind's metadata and no other (a legacy loader
    or hand-made observation is not a native OpenData owner);
  * the durable claim is entered, unreturned, unreleased and acquired no later
    than the observation started, and the observation is not from the future;
  * the live runner holds the OpenData key on its exact lock backend, and supplies
    the entry nonce whose digest the durable claim records. Transaction age or
    another backend holding the same key cannot establish this identity;
  * the supplied fetch time is an aware datetime inside the owned run.
Refusal raises before any effect; the caller's transaction rolls back. Nothing
here releases, expires or rewrites a claim.
"""
from datetime import datetime, timedelta
from enum import Enum
from hashlib import md5, sha256
import json
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from models import Country, DocumentStatus, DocumentType, Extraction, IngestionJob, IngestionStatus, SeedingDomainClaim, SourceDocument
from .parser import EXTRACTOR, parse_publication
from .source import OpenDataSourceRefused, URL, REPORT_URL, CONTENT_TYPE
from seeding.exclusion import DomainExecution, entry_digest

TOLERANCE = timedelta(seconds=5)
TITLE = "KNBS Economic Survey 2026: County Governments’ Revenue (Table 5.13)"
NATIVE_META = frozenset({"since", "seeding_claim_id"})
DISPATCH_META = NATIVE_META | {"dispatch_command_id", "dispatch_claim_token"}


def execution_lock_key(domain):
    # Same derivation as seeding.exclusion.DomainExecution.key (asserted by test).
    return int.from_bytes(sha256(("seeding:" + domain).encode()).digest()[:8], "big") & ((1 << 63) - 1)


def canonical(value):
    """Type-strict JSON identity: True != 1 and 39.0 != 39, unlike dict equality."""
    try:
        return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        raise OpenDataSourceRefused("OpenData observation is not strict JSON") from None


def storage_record(session, values):
    """Normalize intended timestamp casts while retaining strict JSON types."""
    record = {}
    for key, value in values.items():
        if isinstance(value, datetime):
            # These columns store timestamp without time zone. PostgreSQL casts
            # aware parameters in the session zone; never assume that zone is UTC.
            if value.utcoffset() is not None:
                value = session.scalar(text("SELECT timezone(current_setting('TimeZone'), CAST(:value AS timestamptz))"),
                                       {"value": value})
            value = value.isoformat()
        elif isinstance(value, Enum):
            value = value.value
        record[key] = value
    return record


def require_readback(session, document_id, expected_document, extraction_id, expected_extraction):
    # Fire deferred triggers before success while any refusal can roll back.
    session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    # Read complete identity sets through Core, bypassing ORM cached instances.
    # An unexpected sibling is not hidden by selecting only returned primary IDs.
    documents = session.execute(select(SourceDocument.__table__).where(SourceDocument.url == URL)).mappings().all()
    extractions = session.execute(select(Extraction.__table__).where(
        Extraction.source_document_id == document_id)).mappings().all()
    for table, rows, identity, expected in (
        (SourceDocument.__table__, documents, document_id, expected_document),
        (Extraction.__table__, extractions, extraction_id, expected_extraction),
    ):
        if len(rows) != 1 or rows[0]["id"] != identity:
            raise OpenDataSourceRefused("OpenData persisted readback differs: " + table.name)
        actual = {key: value for key, value in rows[0].items() if key != "id"}
        if canonical(storage_record(session, actual)) != expected:
            raise OpenDataSourceRefused("OpenData persisted readback differs: " + table.name)


def require_ownership(session, context, lock=True):
    """Return the run's (job start, database now) after proving native ownership.

    ``lock=False`` is the pre-fetch check: it reads the claim without a row lock,
    so no lock is held across the network fetch; ``persist`` re-proves with it.
    """
    if type(context.job_id) is not int or context.job_id <= 0 or type(context.dry_run) is not bool:
        raise OpenDataSourceRefused("OpenData requires an owned native ingestion observation")
    job = session.get(IngestionJob, context.job_id)
    if job is None or job.domain != "opendata" or job.status != IngestionStatus.RUNNING or job.dry_run != context.dry_run or type(job.meta) is not dict:
        raise OpenDataSourceRefused("OpenData requires an exact running native observation")
    token = job.meta.get("seeding_claim_id")
    try:
        if type(token) is not str or str(UUID(token)) != token:
            raise ValueError
        identity = UUID(token)
    except ValueError:
        raise OpenDataSourceRefused("OpenData observation has no canonical ownership identity") from None
    claim = session.get(SeedingDomainClaim, identity, with_for_update=lock)
    if claim is None or claim.domain != "opendata" or claim.entered_at is None or claim.released_at is not None or claim.returned_at is not None:
        raise OpenDataSourceRefused("OpenData durable domain ownership is unavailable")
    since = job.meta.get("since")
    if claim.kind == "native":
        shape = claim.command_id is None and set(job.meta) == NATIVE_META
    elif claim.kind == "dispatch":
        shape = (claim.command_id is not None and set(job.meta) == DISPATCH_META
                 and job.meta.get("dispatch_command_id") == str(claim.command_id)
                 and job.meta.get("dispatch_claim_token") == token)
    else:
        shape = False
    if not shape or not (since is None or type(since) is str):
        raise OpenDataSourceRefused("OpenData observation metadata differs from its native or dispatch owner")
    # Interpret the naive observation column in the session time zone, as the
    # shared terminal-observation check does, against the database clock.
    start, now = session.execute(select(
        func.timezone(func.current_setting("TimeZone"), IngestionJob.started_at), func.clock_timestamp())
        .where(IngestionJob.id == job.id)).one()
    if start is None or not max(claim.acquired_at, claim.entered_at) - TOLERANCE <= start <= now + TOLERANCE:
        raise OpenDataSourceRefused("OpenData observation time is outside its durable ownership")
    execution = context.ownership
    if (type(execution) is not DomainExecution or execution.domain != "opendata"
            or execution.identity != identity or execution.entered is not True
            or not isinstance(execution.entry, UUID)
            or entry_digest(execution.entry) != claim.entry_id
            or execution.command_id != claim.command_id
            or execution.engine is not session.get_bind()
            or type(execution.pid) is not int):
        raise OpenDataSourceRefused("OpenData execution lock identity is unavailable")
    try:
        continuous = execution.continuous()
    except SQLAlchemyError:
        continuous = False
    if continuous is not True:
        raise OpenDataSourceRefused("OpenData execution lock is no longer held by its runner")
    key = execution_lock_key("opendata")
    held = session.scalar(text("""SELECT EXISTS (SELECT 1 FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid
        WHERE l.locktype='advisory' AND l.granted AND l.pid=:pid
        AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
        AND l.classid=:high AND l.objid=:low AND l.objsubid=1
        AND a.xact_start IS NOT NULL AND a.xact_start <= :entered)"""),
        {"high": key >> 32, "low": key & 0xffffffff, "entered": claim.entered_at, "pid": execution.pid})
    if held is not True:
        raise OpenDataSourceRefused("OpenData domain execution lock is not held; durable ownership retained")
    return start, now


def persist(session, context, payload, parsed, fetched_at):
    start, now = require_ownership(session, context)
    if (type(fetched_at) is not datetime or fetched_at.utcoffset() is None
            or not start - TOLERANCE <= fetched_at <= now + TOLERANCE):
        raise OpenDataSourceRefused("OpenData fetch time must be an aware time inside the owned run")
    # Direct callers must bind the observations to the actual workbook too.
    expected = parse_publication(payload)
    validated = canonical(expected)
    if type(parsed) is not dict or canonical(parsed) != validated:
        raise OpenDataSourceRefused("OpenData parsed observations differ from publication bytes")
    supplied, parsed = parsed, expected

    def result(created, unchanged):
        # Parent flush hooks must not change the child's intended observations
        # or the caller's subsequent terminal counters/metadata.
        if canonical(supplied) != validated or canonical(parsed) != validated:
            raise OpenDataSourceRefused("OpenData parsed observations changed during persistence")
        return {"created": created, "unchanged": unchanged}

    country = session.scalar(select(Country).where(Country.iso_code == "KEN"))
    if country is None:
        raise OpenDataSourceRefused("OpenData requires an existing Kenya country row; run bootstrap separately")
    # Find all same-source candidates before validating their associations.
    documents = session.scalars(select(SourceDocument).where(
        SourceDocument.url == URL).execution_options(populate_existing=True)).all()
    if len(documents) > 1:
        raise OpenDataSourceRefused("OpenData existing source document identity is ambiguous")
    document = documents[0] if documents else None
    checksum = md5(payload, usedforsecurity=False).hexdigest()
    metadata = {"dataset": parsed["dataset"], "sheet": parsed["sheet"], "range": parsed["range"],
                "artifact_sha256": parsed["artifact_sha256"], "artifact_bytes": len(payload),
                "publication_stage": "mixed_as_published", "report_url": REPORT_URL,
                "report_publication_month": "2026-04", "workbook_publication_date": None,
                "verification_status": "source_extracted_not_publication_qualified"}
    if document is not None and (
        document.country_id != country.id or document.publisher != "Kenya National Bureau of Statistics"
        or document.url != URL or document.file_path is not None
        or document.title != TITLE or document.md5 != checksum or document.doc_type != DocumentType.REPORT
        or document.status != DocumentStatus.AVAILABLE or document.content_type != CONTENT_TYPE
        or type(document.http_status) is not int or document.http_status != 200
        or type(document.meta) is not dict or canonical(document.meta) != canonical(metadata)
        or document.last_verified_at is None):
        raise OpenDataSourceRefused("OpenData existing source document provenance differs; investigate before retry")
    # Intent is explicit before INSERT; required values/defaults are not learned
    # from RETURNING or ORM state after a database trigger has run.
    document_values = dict(country_id=country.id, publisher="Kenya National Bureau of Statistics",
        title=TITLE, url=URL, file_path=None, fetch_date=fetched_at, md5=checksum,
        doc_type=DocumentType.REPORT, status=DocumentStatus.AVAILABLE, content_type=CONTENT_TYPE,
        http_status=200, last_verified_at=fetched_at, last_seen_at=fetched_at, created_at=fetched_at)
    if document is None:
        if context.dry_run:
            return result(0, 0)
        expected_document = canonical(storage_record(session, {**document_values, "metadata": metadata}))
        document = SourceDocument(**document_values, meta=metadata)
        session.add(document)
        session.flush()
    else:
        # Replay retains its original timestamps; new fetch time never rewrites
        # the first source observation. Other provenance was validated above.
        expected_document = canonical(storage_record(session, {**document_values, "metadata": metadata,
            "fetch_date": document.fetch_date, "last_verified_at": document.last_verified_at,
            "last_seen_at": document.last_seen_at, "created_at": document.created_at}))
    existing = session.scalars(select(Extraction).where(
        Extraction.source_document_id == document.id).execution_options(populate_existing=True)).all()
    extraction_values = dict(source_document_id=document.id, page_number=None,
                             extracted_json=parsed, extractor=EXTRACTOR, confidence=None, created_at=fetched_at)
    if existing:
        stored = existing[0]
        if (len(existing) != 1 or stored.extractor != EXTRACTOR
                or type(stored.extracted_json) is not dict or canonical(stored.extracted_json) != canonical(parsed)
                or stored.page_number is not None or stored.confidence is not None):
            raise OpenDataSourceRefused("OpenData existing source-bound extraction differs; investigate before retry")
        expected_extraction = canonical(storage_record(session, {**extraction_values, "created_at": stored.created_at}))
        require_readback(session, document.id, expected_document, stored.id, expected_extraction)
        return result(0, 1)
    if context.dry_run:
        return result(0, 0)
    # Freeze JSON bytes before ORM/database hooks can mutate the row or aliases
    # shared with parsed observations. Generated primary IDs are checked apart.
    expected_extraction = canonical(storage_record(session, extraction_values))
    extraction = Extraction(**extraction_values)
    session.add(extraction)
    session.flush()
    require_readback(session, document.id, expected_document, extraction.id, expected_extraction)
    return result(1, 0)
