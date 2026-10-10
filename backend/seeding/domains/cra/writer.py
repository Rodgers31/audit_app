"""Append source-bound recommendations; never replace budget or revenue facts.

Ownership the writer re-proves on every call, on the writing transaction:
  * the observation is the exact RUNNING native or dispatch IngestionJob the CLI
    wrote for this claim, with that kind's metadata and no other (a legacy loader
    or hand-made observation is not a native CRA owner);
  * the durable claim is entered, unreturned, unreleased and acquired no later
    than the observation started, and the observation is not from the future;
  * the shared domain execution lock is still held by the entering runner: a
    backend holds the CRA key in a transaction that began no later than the
    claim's one-use entry. A contender can only take the key after the runner's
    lock ended, so its transaction starts later and does not count (without this
    the effects would land under a claim that can no longer be acknowledged);
  * the supplied fetch time is an aware datetime inside the owned run.
Refusal raises before any effect; the caller's transaction rolls back. Nothing
here releases, expires or rewrites a claim.
"""
from datetime import datetime, timedelta
from hashlib import md5, sha256
import json
from uuid import UUID

from sqlalchemy import func, select, text

from models import Country, DocumentStatus, DocumentType, Extraction, IngestionJob, IngestionStatus, SeedingDomainClaim, SourceDocument
from .parser import EXTRACTOR, PAGE, parse_publication
from .source import CraSourceRefused, URL

TOLERANCE = timedelta(seconds=5)
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
        raise CraSourceRefused("CRA observation is not strict JSON") from None


def require_ownership(session, context, lock=True):
    """Return the run's (job start, database now) after proving native ownership.

    ``lock=False`` is the pre-fetch check: it reads the claim without a row lock,
    so no lock is held across the network fetch; ``persist`` re-proves with it.
    """
    if type(context.job_id) is not int or context.job_id <= 0 or type(context.dry_run) is not bool:
        raise CraSourceRefused("CRA requires an owned native ingestion observation")
    job = session.get(IngestionJob, context.job_id)
    if job is None or job.domain != "cra" or job.status != IngestionStatus.RUNNING or job.dry_run != context.dry_run or type(job.meta) is not dict:
        raise CraSourceRefused("CRA requires an exact running native observation")
    token = job.meta.get("seeding_claim_id")
    try:
        if type(token) is not str or str(UUID(token)) != token:
            raise ValueError
        identity = UUID(token)
    except ValueError:
        raise CraSourceRefused("CRA observation has no canonical ownership identity") from None
    claim = session.get(SeedingDomainClaim, identity, with_for_update=lock)
    if claim is None or claim.domain != "cra" or claim.entered_at is None or claim.released_at is not None or claim.returned_at is not None:
        raise CraSourceRefused("CRA durable domain ownership is unavailable")
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
        raise CraSourceRefused("CRA observation metadata differs from its native or dispatch owner")
    # Interpret the naive observation column in the session time zone, as the
    # shared terminal-observation check does, against the database clock.
    start, now = session.execute(select(
        func.timezone(func.current_setting("TimeZone"), IngestionJob.started_at), func.clock_timestamp())
        .where(IngestionJob.id == job.id)).one()
    if start is None or not claim.acquired_at - TOLERANCE <= start <= now + TOLERANCE:
        raise CraSourceRefused("CRA observation time is outside its durable ownership")
    key = execution_lock_key("cra")
    held = session.scalar(text("""SELECT EXISTS (SELECT 1 FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid
        WHERE l.locktype='advisory' AND l.granted
        AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
        AND l.classid=:high AND l.objid=:low AND l.objsubid=1
        AND a.xact_start IS NOT NULL AND a.xact_start <= :entered)"""),
        {"high": key >> 32, "low": key & 0xffffffff, "entered": claim.entered_at})
    if held is not True:
        raise CraSourceRefused("CRA domain execution lock is not held; durable ownership retained")
    return start, now


def persist(session, context, payload, parsed, fetched_at):
    start, now = require_ownership(session, context)
    if (type(fetched_at) is not datetime or fetched_at.utcoffset() is None
            or not start - TOLERANCE <= fetched_at <= now + TOLERANCE):
        raise CraSourceRefused("CRA fetch time must be an aware time inside the owned run")
    # Direct callers must bind the observations to the actual publication too.
    expected = parse_publication(payload)
    if type(parsed) is not dict or canonical(parsed) != canonical(expected):
        raise CraSourceRefused("CRA parsed observations differ from publication bytes")
    country = session.scalar(select(Country).where(Country.iso_code == "KEN"))
    if country is None:
        raise CraSourceRefused("CRA requires an existing Kenya country row; run bootstrap separately")
    if context.dry_run:
        return {"created": 0, "unchanged": 0}
    documents = session.scalars(select(SourceDocument).where(
        SourceDocument.country_id == country.id, SourceDocument.publisher == "Commission on Revenue Allocation",
        SourceDocument.url == URL, SourceDocument.meta["artifact_sha256"].astext == parsed["artifact_sha256"])).all()
    if len(documents) > 1:
        raise CraSourceRefused("CRA existing source document identity is ambiguous")
    document = documents[0] if documents else None
    checksum = md5(payload, usedforsecurity=False).hexdigest()
    metadata = {"dataset": "cra_recommendations", "fiscal_year": "FY2026/27",
                "artifact_sha256": parsed["artifact_sha256"], "artifact_bytes": len(payload),
                "publication_stage": "recommendation"}
    if document is not None and (
        document.md5 != checksum or document.doc_type != DocumentType.REPORT
        or document.status != DocumentStatus.AVAILABLE or document.content_type != "application/pdf"
        or type(document.http_status) is not int or document.http_status != 200
        or type(document.meta) is not dict or canonical(document.meta) != canonical(metadata)
        or document.last_verified_at is None):
        raise CraSourceRefused("CRA existing source document provenance differs; investigate before retry")
    if document is None:
        document = SourceDocument(country_id=country.id, publisher="Commission on Revenue Allocation",
            title="CRA recommended shareable revenue allocation FY2026/27 (Table 5.2)", url=URL,
            fetch_date=fetched_at, md5=checksum,
            doc_type=DocumentType.REPORT, status=DocumentStatus.AVAILABLE, content_type="application/pdf",
            http_status=200, last_verified_at=fetched_at, last_seen_at=fetched_at,
            meta=metadata)
        session.add(document)
        session.flush()
    # Any extraction already on this document must be exactly this one. Another
    # parser version, extractor or a tampered row refuses; it is never appended to.
    existing = session.scalars(select(Extraction).where(Extraction.source_document_id == document.id)).all()
    if existing:
        stored = existing[0]
        if (len(existing) != 1 or stored.extractor != EXTRACTOR
                or type(stored.extracted_json) is not dict or canonical(stored.extracted_json) != canonical(parsed)
                or type(stored.page_number) is not int or stored.page_number != PAGE or stored.confidence is not None):
            raise CraSourceRefused("CRA existing source-bound extraction differs; investigate before retry")
        return {"created": 0, "unchanged": 1}
    session.add(Extraction(source_document_id=document.id, page_number=PAGE,
                           extracted_json=parsed, extractor=EXTRACTOR))
    session.flush()
    return {"created": 1, "unchanged": 0}
