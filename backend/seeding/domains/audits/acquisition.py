"""Prospective OAG acquisition, independent of content/publication acceptance.

A legacy cache is only an edition comparison. It cannot originate HTTP proof.
An absent or stale origin earns a new origin only from a complete official GET,
exact cached-edition equality, provider retention/readback and DB readback.
"""
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace

from models import Country, DocumentStatus, DocumentType, Extraction, IngestionJob, IngestionStatus, SourceDocument
from sqlalchemy import select, text

from ...native_report_authority import DOMAINS, digest, source_identity
from ...pdf_artifact import artifact_matches_document, file_identity
from ...retained_report_receipts import aware, original_fields, _check_origin, verified_retained_pdf
from services.receipt_store import configured_receipt_store
from services.response_receipts import (
    acquisition_is_intact, capture_retained_pdf, copy_receipt, persist_receipt, seal_receipt,
)

KEY = 'audit_acquisition_origin_v1'
_MAX_BYTES = 64 * 1024 * 1024
# The downloader remains bounded by the existing setting and caller budget.
_MAX_SECONDS = 600


class AuditOriginUnavailable(ValueError):
    """Closed diagnostic vocabulary, without provider messages or credentials."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _job(session, context, *, lock=False):
    if (session is None or context is None or type(getattr(context, 'job_id', None)) is not int
            or context.job_id <= 0 or getattr(context, 'dry_run', None) is not False
            or session.get_bind().dialect.name != 'postgresql'):
        raise AuditOriginUnavailable('context_refused')
    if session.scalar(text('SHOW transaction_isolation')) != 'read committed':
        raise AuditOriginUnavailable('context_refused')
    query = select(IngestionJob.id, IngestionJob.domain, IngestionJob.status,
        IngestionJob.dry_run, IngestionJob.started_at).where(IngestionJob.id == context.job_id)
    row = session.execute(query.with_for_update() if lock else query).mappings().one_or_none()
    job = SimpleNamespace(**row) if row is not None else None
    now = datetime.now(timezone.utc)
    if (job is None or job.domain != 'audits' or job.status != IngestionStatus.RUNNING
            or job.dry_run is not False or job.started_at is None or aware(job.started_at) > now):
        raise AuditOriginUnavailable('context_refused')
    return job


def validate_audit_fetch(session, context, *, url, country_id, publisher, doc_type, dataset_id, lock=False):
    """Check declared identity and running job before any Layer-2 mutation/IO."""
    from ...native_report_authority import official_url
    with session.no_autoflush:
        _job(session, context, lock=lock)
        if (dataset_id not in ('oag_national_audits', 'oag_county_audits')
                or type(country_id) is not int or country_id <= 0
                or publisher != DOMAINS['audits'][2] or doc_type != DocumentType.AUDIT
                or not official_url(url, 'audits')
                or session.scalar(select(Country.iso_code).where(Country.id == country_id)) != 'KEN'):
            raise AuditOriginUnavailable('source_refused')
        query = select(SourceDocument).where(SourceDocument.url == url).limit(2).execution_options(populate_existing=True)
        sources = session.scalars(query.with_for_update() if lock else query).all()
        if len(sources) > 1:
            raise AuditOriginUnavailable('source_ambiguous')
        if sources and (sources[0].country_id != country_id or sources[0].publisher != publisher
                or sources[0].doc_type != doc_type or type(sources[0].meta) not in (dict, type(None))):
            raise AuditOriginUnavailable('source_refused')
    return sources[0] if sources else None


def _scope(session, context, source_id, *, lock=False):
    from ...native_report_authority import official_url
    job = _job(session, context, lock=lock)
    if type(source_id) is not int or source_id <= 0:
        raise AuditOriginUnavailable('source_refused')
    query = select(SourceDocument).where(SourceDocument.id == source_id).execution_options(populate_existing=True)
    source = session.scalar(query.with_for_update() if lock else query)
    if (source is None or source.status != DocumentStatus.AVAILABLE
            or type(source.http_status) is not int or source.http_status != 200
            or source.content_type != 'application/pdf'
            or source.doc_type != DocumentType.AUDIT or source.publisher != DOMAINS['audits'][2]
            or not official_url(source.url, 'audits')
            or session.scalar(select(Country.iso_code).where(Country.id == source.country_id)) != 'KEN'):
        raise AuditOriginUnavailable('source_refused')
    # The URL is not a row identity. Refuse ambiguous source registrations,
    # including an otherwise different country/type sharing that same URL.
    peers = session.scalars(select(SourceDocument.id).where(SourceDocument.url == source.url).limit(2)).all()
    if peers != [source.id]:
        raise AuditOriginUnavailable('source_ambiguous')
    return source, job


def _edition(source, path, max_bytes):
    if not source.file_path or Path(source.file_path).resolve() != path.resolve():
        raise AuditOriginUnavailable('edition_changed')
    if not path.is_file() or not 0 < path.stat().st_size <= max_bytes:
        raise AuditOriginUnavailable('bytes_unavailable')
    from ...http_client import PdfDownloadError
    try:
        identity = file_identity(path)
    except (OSError, PdfDownloadError) as exc:
        raise AuditOriginUnavailable('bytes_unavailable') from exc
    artifact = source.meta.get('pdf_artifact_v1') if type(source.meta) is dict else None
    if (not artifact_matches_document(artifact, source)
            or any(artifact[k] != identity[k] for k in identity)):
        raise AuditOriginUnavailable('edition_changed')
    return path.read_bytes()


def ensure_audit_origin(session, context, source_id, client, settings, *, max_seconds):
    """Return exact current-job replay proof, or refuse without a receipt write.

    No commit, source edit, source adoption or publication authority is granted.
    The caller owns the transaction and banks a negative diagnostic separately.
    """
    configured_cap = settings.pdf_download_max_bytes
    if (type(configured_cap) is not int or configured_cap <= 0
            or type(max_seconds) not in (int, float) or not math.isfinite(max_seconds)
            or not 0 < max_seconds <= _MAX_SECONDS):
        raise AuditOriginUnavailable('limits_refused')
    cap = min(configured_cap, _MAX_BYTES)
    source, job = _scope(session, context, source_id)
    path = Path(source.file_path) if source.file_path else Path('')
    body = _edition(source, path, cap)
    initial = digest(source_identity(source))
    store = getattr(client, 'receipt_store', None)
    if store is None:
        store = configured_receipt_store(settings)
    if (type(getattr(store, 'storage_scope', None)) is not str or not store.storage_scope
            or type(getattr(store, 'max_bytes', None)) is not int or store.max_bytes < len(body)):
        raise AuditOriginUnavailable('retention_refused')
    checksum = hashlib.sha256(body).hexdigest()
    gap = None
    try:
        value, _ = verified_retained_pdf(session, context, store, domain='audits', url=source.url, body=body)
    except ValueError as exc:
        from services.response_receipts import _RETAINED_REFUSAL_REASONS
        gap = _RETAINED_REFUSAL_REASONS.get(str(exc), 'authority_refused_unknown')
        if gap not in ('origin_missing', 'origin_stale', 'origin_invalid'):
            raise AuditOriginUnavailable(gap) from exc
    state = 'replayed'
    # An existing proof is revalidated below. Neither sidecars nor cached local
    # receipts can enter the prospective branch as an acquisition capability.
    if gap is not None:
        receipt = client.download_receipt(source.url) if hasattr(client, 'download_receipt') else None
        if not acquisition_is_intact(receipt):
            with tempfile.TemporaryDirectory(prefix='audit-origin-') as temporary:
                downloaded = Path(temporary) / 'edition.pdf'
                try:
                    client.download_to_file(source.url, downloaded, max_seconds=max_seconds,
                        max_bytes=min(cap, store.max_bytes), raise_for_status=True)
                    if downloaded.stat().st_size > min(cap, store.max_bytes):
                        raise AuditOriginUnavailable('bytes_unavailable')
                    if file_identity(downloaded) != file_identity(path) or downloaded.read_bytes() != body:
                        raise AuditOriginUnavailable('edition_changed')
                    receipt = client.download_receipt(source.url)
                except AuditOriginUnavailable:
                    raise
                except Exception as exc:
                    raise AuditOriginUnavailable('acquisition_failed') from exc
        if not acquisition_is_intact(receipt):
            raise AuditOriginUnavailable('origin_unconfirmed')
        # A native/cell parser seal is not reinterpreted as an acquisition.
        try:
            receipt = copy_receipt(receipt, parser_version='unparsed-acquisition-v1')
            _check_origin(source, original_fields(receipt), url=source.url,
                checksum=checksum, size=len(body), at=datetime.now(timezone.utc))
            if receipt.get('storage_scope') != store.storage_scope or receipt._store is not store:
                raise AuditOriginUnavailable('destination_changed')
            if store.read(checksum) != body:
                raise AuditOriginUnavailable('readback_mismatch')
        except AuditOriginUnavailable:
            raise
        except (ValueError, TypeError, KeyError, OSError) as exc:
            raise AuditOriginUnavailable('origin_unconfirmed') from exc
        state = 'persisted'
    # Re-read current rows after network I/O, then keep the exact source/job
    # locked through the immutable receipt writes. A stopped job cannot resume
    # using a RUNNING object left in the session identity map.
    source, job = _scope(session, context, source_id, lock=True)
    if digest(source_identity(source)) != initial or _edition(source, path, cap) != body:
        raise AuditOriginUnavailable('edition_changed')
    with session.begin_nested():
        if state == 'persisted':
            seal_receipt(receipt, [])  # acquisition inventory only; no financial observation
            origin = persist_receipt(session, source, receipt, extractor='pdf-receipt-v1')
            stored = session.scalar(select(Extraction.extracted_json).where(Extraction.id == origin.id))
            _check_origin(source, original_fields(stored['response_receipt']), url=source.url,
                checksum=checksum, size=len(body), at=datetime.now(timezone.utc))
        replay = capture_retained_pdf(session, context, store, domain='audits', url=source.url, body=body)
        seal_receipt(replay, [])
        validation = persist_receipt(session, source, replay, extractor='pdf-receipt-v1')
        stored = session.scalar(select(Extraction.extracted_json).where(Extraction.id == validation.id))
        if digest(stored['response_receipt']) != digest(dict(replay)):
            raise AuditOriginUnavailable('readback_mismatch')
        from ...retained_report_receipts import validate_retained_pdf
        proof = stored['response_receipt']['retained_pdf_validation']
        validate_retained_pdf(session, source, stored['response_receipt'], job,
            started=aware(job.started_at), finished=datetime.now(timezone.utc))
    return dict(version=1, state=state, reason=gap, source_document_id=source.id,
        ingestion_id=job.id, origin_extraction_id=proof['origin_extraction_id'],
        validation_extraction_id=validation.id, origin_acquisition_hash=proof['origin_acquisition_hash'],
        validated_at=proof['validated_at'], digest=checksum, byte_size=len(body),
        retained_bytes=True, origin_qualified=True, native_publication_authority=False)
