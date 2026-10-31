"""Revalidate cached CoB/OAG bytes against a persisted original acquisition.

Download sidecars are never authority. The original HTTP acquisition stays
unchanged; a separate, job-bound check records the retained-byte validation.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from types import SimpleNamespace

from sqlalchemy import select, text

if __package__.startswith('backend.'):
    from backend.models import Country, DocumentStatus, DocumentType, Extraction, IngestionJob, IngestionStatus, SourceDocument
else:
    from models import Country, DocumentStatus, DocumentType, Extraction, IngestionJob, IngestionStatus, SourceDocument
from .native_report_authority import DOMAINS, VERSION, digest, official_url

KEY = 'retained_pdf_validation'
MAX_AGE = timedelta(days=30)
FIELDS = {'version', 'source_document_id', 'origin_extraction_id', 'ingestion_id',
          'origin_acquisition_hash', 'validated_at'}
_BODY_TOKEN = object()


def aware(value):
    result = datetime.fromisoformat(value) if type(value) is str else value
    if not isinstance(result, datetime):
        raise ValueError('Retained acquisition timestamp required')
    return result.replace(tzinfo=timezone.utc) if result.utcoffset() is None else result.astimezone(timezone.utc)


def original_fields(receipt):
    return {k: deepcopy(v) for k, v in receipt.items()
            if k not in ('observations', 'parser_version', KEY)}


def _origin_query():
    # Exclude potentially large per-cell manifests in PostgreSQL, not Python.
    return Extraction.extracted_json['response_receipt'].op('-')('observations')


def _check_origin(source, receipt, *, url, checksum, size, at):
    if (type(receipt) is not dict or type(receipt.get('version')) is not int or receipt['version'] != 1
            or receipt.get('digest_scope') not in ('response.content', 'decoded_stream_body')
            or KEY in receipt or receipt.get('acquisition_kind') is not None
            or receipt.get('parser_result_origin') or receipt.get('failure_reason')
            or type(receipt.get('status')) is not int or receipt['status'] != 200
            or receipt.get('source_kind') != 'pdf' or receipt.get('request') != {'method':'GET', 'url':url}
            or receipt.get('request_url') != url or receipt.get('response_url') != url
            or str(receipt.get('content_type') or '').split(';')[0].strip().lower() != 'application/pdf'
            or receipt.get('digest') != checksum or receipt.get('storage_key') != checksum
            or type(receipt.get('byte_size')) is not int or receipt['byte_size'] != size
            or receipt.get('byte_check', {}).get('status') != 'matched'
            or receipt.get('byte_check', {}).get('sha256') != checksum):
        raise ValueError('Original retained HTTP acquisition required')
    acquired, checked = aware(receipt['acquired_at']), aware(receipt['byte_check']['checked_at'])
    # Serialized acquisition timestamps must themselves be timezone-explicit.
    if (datetime.fromisoformat(receipt['acquired_at']).utcoffset() is None
            or datetime.fromisoformat(receipt['byte_check']['checked_at']).utcoffset() is None
            or not acquired <= checked <= at or at-acquired > MAX_AGE):
        raise ValueError('Original acquisition is stale or unordered')
    if source.status != DocumentStatus.AVAILABLE:
        raise ValueError('Current available source required')


class RetainedBody:
    """One immutable, bounded provider read shared by this ingestion session."""
    def __init__(self, body, checksum, storage_scope, origin_hash, *, token=None):
        if token is not _BODY_TOKEN:
            raise TypeError('Checked retained-body capability required')
        self.body, self.checksum, self.storage_scope = body, checksum, storage_scope
        self.origin_hash = origin_hash

    def read(self, key):
        if key != self.checksum:
            raise ValueError('Different retained object requested')
        return self.body


def verified_retained_pdf(session, context, store, *, domain, url, body):
    if (domain not in ('national_budget', 'pending_bills', 'audits') or not official_url(url, domain)
            or type(body) is not bytes or not 0 < len(body) <= 64*1024*1024
            or not body.startswith(b'%PDF-') or not body[-2048:].rstrip().endswith(b'%%EOF')
            or context is None or type(context.job_id) is not int or context.job_id <= 0
            or type(context.dry_run) is not bool or session.get_bind().dialect.name != 'postgresql'):
        raise ValueError('Bounded native retained-source context required')
    if session.scalar(text('SHOW transaction_isolation')) != 'read committed':
        raise ValueError('Current READ COMMITTED acquisition context required')
    # Producer sessions can already hold the job in their identity map. Query
    # scalar columns so an externally stopped job cannot reuse stale RUNNING.
    row = session.execute(select(IngestionJob.id, IngestionJob.domain,
        IngestionJob.status, IngestionJob.dry_run, IngestionJob.started_at)
        .where(IngestionJob.id == context.job_id)).mappings().one_or_none()
    job = SimpleNamespace(**row) if row is not None else None
    now = datetime.now(timezone.utc)
    if (job is None or job.domain != domain or job.status != IngestionStatus.RUNNING
            or job.dry_run is not context.dry_run or not aware(job.started_at) <= now):
        raise ValueError('Exact running native job required')
    source_scope = [SourceDocument.url == url, Country.iso_code == 'KEN']
    if domain == 'pending_bills':
        # Use the same explicit REPORT lane as the pending-bills writer.
        # A budget row may independently describe these same PDF bytes.
        source_scope.append(SourceDocument.doc_type == DocumentType.REPORT)
    elif domain == 'audits':
        source_scope.extend((SourceDocument.doc_type == DocumentType.AUDIT,
                             SourceDocument.publisher == DOMAINS[domain][2]))
    else:
        source_scope.append(SourceDocument.publisher == DOMAINS[domain][2])
    sources = list(session.execute(select(SourceDocument.id, SourceDocument.country_id,
        SourceDocument.publisher, SourceDocument.url, SourceDocument.md5, SourceDocument.status,
        SourceDocument.meta['pdf_artifact_v1'].label('artifact')).join(Country).where(
        *source_scope).limit(2)).mappings())
    if len(sources) != 1:
        raise ValueError('One retained native source required')
    source = SimpleNamespace(**sources[0])
    if source.publisher != DOMAINS[domain][2]:
        raise ValueError('Current native retained publisher required')
    checksum = hashlib.sha256(body).hexdigest()
    receipt_column = Extraction.extracted_json['response_receipt']
    row = session.execute(select(Extraction.id, _origin_query()).where(
        Extraction.source_document_id == source.id,
        Extraction.extractor.in_(['pdf-receipt-v1', VERSION]),
        receipt_column['digest'].astext == checksum,
        ~receipt_column.has_key(KEY),
        receipt_column['status'].astext == '200',
    ).order_by(Extraction.id.desc()).limit(1)).one_or_none()
    if row is None:
        raise ValueError('No persisted original PDF acquisition')
    identity, original = row
    _check_origin(source, original, url=url, checksum=checksum, size=len(body), at=now)
    artifact = source.artifact
    md5 = hashlib.md5(body, usedforsecurity=False).hexdigest()
    if (source.md5 is not None and source.md5 != md5
            or artifact is not None and (type(artifact) is not dict
                or artifact.get('sha256') != checksum or artifact.get('md5') != md5)):
        raise ValueError('Current source edition differs')
    if getattr(store, 'storage_scope', None) != original.get('storage_scope'):
        raise ValueError('Retained storage destination changed')
    cache = session.info.setdefault('retained_pdf_bodies_v1', {})
    cache_key = (domain, job.id, source.id, identity, checksum)
    checked_store = cache.get(cache_key)
    origin_hash = digest(original_fields(original))
    if isinstance(checked_store, RetainedBody) and checked_store.origin_hash != origin_hash:
        raise ValueError('Original acquisition changed after retained validation')
    if not isinstance(checked_store, RetainedBody):
        retained = store.read(checksum)
        if type(retained) is not bytes or retained != body:
            raise ValueError('Retained provider bytes differ')
        checked_store = RetainedBody(retained, checksum, original.get('storage_scope'), origin_hash, token=_BODY_TOKEN)
        cache[cache_key] = checked_store
    if checked_store.read(checksum) != body:
        raise ValueError('Retained snapshot differs')
    value = original_fields(original)
    value.update(parser_version='unparsed-acquisition-v1')
    value[KEY] = dict(version=1, source_document_id=source.id, origin_extraction_id=identity,
                     ingestion_id=job.id, origin_acquisition_hash=origin_hash,
                     validated_at=datetime.now(timezone.utc).isoformat())
    return value, checked_store


def validate_retained_pdf(session, source, receipt, job, *, started, finished):
    """Recheck the immutable origin and exact new-job binding after writer locks."""
    proof = receipt.get(KEY)
    if (job.domain not in ('national_budget', 'pending_bills', 'audits')
            or source.publisher != DOMAINS[job.domain][2] or not official_url(source.url, job.domain)
            or type(proof) is not dict or set(proof) != FIELDS or type(proof['version']) is not int
            or proof['version'] != 1
            or any(type(proof[k]) is not int or proof[k] <= 0
                   for k in ('source_document_id', 'origin_extraction_id', 'ingestion_id'))
            or proof['source_document_id'] != source.id or proof['ingestion_id'] != job.id):
        raise ValueError('Exact retained PDF lineage required')
    checked = aware(proof['validated_at'])
    if datetime.fromisoformat(proof['validated_at']).utcoffset() is None or not started <= checked <= finished:
        raise ValueError('Current-job retained validation required')
    row = session.execute(select(Extraction.source_document_id, Extraction.extractor, _origin_query())
        .where(Extraction.id == proof['origin_extraction_id'])).one_or_none()
    if row is None or row[0] != source.id or row[1] not in ('pdf-receipt-v1', VERSION):
        raise ValueError('Stored original acquisition unavailable')
    original = row[2]
    _check_origin(source, original, url=source.url, checksum=receipt['digest'], size=receipt['byte_size'], at=checked)
    if (digest(original_fields(original)) != proof['origin_acquisition_hash']
            or digest(original_fields(original)) != digest(original_fields(receipt))):
        raise ValueError('Original acquisition binding changed')
    return checked
