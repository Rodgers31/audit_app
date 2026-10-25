"""Committed native report readers. No source transport, parser or social writes."""
from datetime import date
from sqlalchemy import select, text, func

if __package__.startswith('backend.'):
    from backend.models import Extraction, SourceDocument, IngestionJob, IngestionStatus, DocumentStatus, Country
else:
    from models import Extraction, SourceDocument, IngestionJob, IngestionStatus, DocumentStatus, Country
from .native_report_authority import VERSION, KEY, DOMAINS, digest, official_url, lock_native_domain, source_identity
from .source_observations import SourceObservationUnavailable, _positive_id, _aware, _read_limits


def _job(db, ingestion_id, domain, *, scope_key=None):
    row = db.execute(select(IngestionJob,
        func.timezone(func.current_setting('TimeZone'), IngestionJob.started_at),
        func.timezone(func.current_setting('TimeZone'), IngestionJob.finished_at))
        .where(IngestionJob.id == ingestion_id)).one_or_none()
    # Validation follows any authority-lock wait. Transaction-start time can
    # predate a valid completion that became visible after acquiring the lock.
    now = db.scalar(select(func.statement_timestamp()))
    if row is None:
        raise SourceObservationUnavailable('Exact record ingestion lineage unavailable')
    job, started, finished = row
    if (job.domain != domain or job.dry_run is not False or job.status != IngestionStatus.COMPLETED
            or type(job.errors) is not list or job.errors or not isinstance(job.meta, dict)
            or job.meta.get('source_mode') != 'live' or started is None or finished is None
            or not started <= finished <= now):
        raise SourceObservationUnavailable('Exact record ingestion lineage unavailable')
    # National/KRA have one report series. Rolling audit jobs cover different
    # institutions; only a newer qualified observation of this auditee supersedes.
    if domain != 'audits' or scope_key is not None:
        conditions = [IngestionJob.domain == domain, IngestionJob.id > ingestion_id,
            IngestionJob.dry_run.is_(False),
            IngestionJob.status.in_([IngestionStatus.COMPLETED, IngestionStatus.COMPLETED_WITH_ERRORS]),
            IngestionJob.meta['source_mode'].astext.in_(['live', 'partial'])]
        if domain == 'audits':
            conditions.append(IngestionJob.meta['native_report_series'].has_key(scope_key))
        newer = db.scalar(select(IngestionJob.id).where(*conditions).order_by(IngestionJob.id.desc()).limit(1))
        if newer is not None:
            raise SourceObservationUnavailable('Current report authority unavailable')
    return job, started, finished


def _ids(job, domain):
    records = job.meta.get('native_report_records')
    ids = records.get(domain) if type(records) is dict else None
    if (type(ids) is not list or len(ids) > 1000 or any(type(v) is not int or not 0 < v <= 2147483647 for v in ids)
            or len(set(ids)) != len(ids)):
        raise SourceObservationUnavailable('Exact record ingestion lineage unavailable')
    return tuple(ids)


def current_native_report(db, record_id, ingestion_id, *, domain, lock=False):
    """Revalidate exact source/receipt/job, locking inputs for a draft mutation.

    Source writers take the same document lock before replacing authority. At
    READ COMMITTED, refresh after the lock wait observes a completed replacement.
    This port needs ingestion/admin source access; no worker grant is introduced.
    """
    _positive_id(record_id)
    _positive_id(ingestion_id)
    if domain not in DOMAINS:
        raise SourceObservationUnavailable('Current report authority unavailable')
    if lock and db.scalar(text('SHOW transaction_isolation')) != 'read committed':
        raise SourceObservationUnavailable('Current report authority unavailable')
    if lock:
        lock_native_domain(db, domain)
    ext = db.get(Extraction, record_id)
    if ext is None or ext.extractor != VERSION:
        raise SourceObservationUnavailable('Stored publisher date receipt required')
    source_query = select(SourceDocument).where(SourceDocument.id == ext.source_document_id)
    if lock:
        source_query = source_query.with_for_update()
    source = db.execute(source_query.execution_options(populate_existing=True)).scalar_one_or_none()
    job, started, finished = _job(db, ingestion_id, domain)
    if record_id not in _ids(job, domain):
        raise SourceObservationUnavailable('Exact record ingestion lineage unavailable')
    meta = source.meta if source and type(source.meta) is dict else {}
    active = meta.get(KEY)
    binding = active.get(domain) if type(active) is dict else None
    if (type(binding) is not dict or type(binding.get('extraction_id')) is not int
            or binding['extraction_id'] != record_id or type(binding.get('ingestion_id')) is not int
            or binding['ingestion_id'] != ingestion_id or type(binding.get('country_id')) is not int
            or binding['country_id'] != source.country_id
            or binding.get('source_identity') != source_identity(source) or source.publisher != DOMAINS[domain][2]
            or source.status != DocumentStatus.AVAILABLE or not official_url(source.url, domain)):
        raise SourceObservationUnavailable('Current report authority unavailable')
    country = db.get(Country, source.country_id)
    if country is None or country.iso_code != "KEN":
        raise SourceObservationUnavailable("Current report authority unavailable")
    raw = ext.extracted_json
    receipt = raw.get('response_receipt') if type(raw) is dict else None
    observations = receipt.get('observations') if type(receipt) is dict else None
    value = observations[0] if type(observations) is list and len(observations) == 1 else None
    if (type(value) is not dict or value.get('domain') != domain or value.get('document_url') != source.url
            or receipt.get('parser_version') != VERSION or type(receipt.get('status')) is not int or receipt['status'] != 200
            or receipt.get('request', {}).get('method') != 'GET' or receipt.get('request_url') != source.url
            or not official_url(receipt.get('response_url'), domain)
            or receipt.get('digest') != value.get('document_checksum')
            or receipt.get('storage_key') != receipt.get('digest')
            or receipt.get('byte_check', {}).get('status') != 'matched'
            or receipt.get('byte_check', {}).get('sha256') != receipt.get('digest')
            or type(receipt.get('byte_size')) is not int or not 0 < receipt['byte_size'] <= 64*1024*1024
            or binding.get('authority_hash') != digest(dict(receipt=receipt, value=value, country_id=source.country_id,
                                                         publisher=source.publisher, ingestion_id=job.id, source_identity=source_identity(source)))):
        raise SourceObservationUnavailable('Stored publisher date receipt required')
    if domain == 'audits':
        _job(db, ingestion_id, domain, scope_key=value.get('scope_key'))
    try:
        published = date.fromisoformat(value['published_on'])
        acquired = _aware(receipt['acquired_at'])
        verified = _aware(receipt['byte_check']['checked_at'])
        if not published <= acquired.date() or not started <= acquired <= verified <= finished:
            raise ValueError
        from importlib import import_module
        contracts = import_module('backend.social.generation.contracts' if __package__.startswith('backend.') else 'social.generation.contracts')
        report = dict(native_domain=domain, scope_key=value['scope_key'], entity_id=source.country_id,
            source_record_id=ext.id, authority_fingerprint=binding['authority_hash'], entity=value['entity'],
            period=value['period'], period_start=value['period_start'], period_end=value['period_end'],
            source_document_id=source.id, document_url=source.url, document_checksum=value['document_checksum'],
            publisher=source.publisher, published_on=value['published_on'], retrieved_at=acquired.isoformat(),
            verified_at=verified.isoformat(), canonical_url='https://www.auditgava.com'+DOMAINS[domain][3],
            locator=value['locator'], publication_extraction_id=ext.id, qualification_extraction_id=ext.id)
        contracts.NativeReportEvidence.model_validate(report)
    except (ValueError, TypeError, KeyError):
        raise SourceObservationUnavailable('Exact report period and publication locator required') from None
    return dict(schema_version=1, source_type=DOMAINS[domain][0],
        source_key=f'{DOMAINS[domain][0]}:native:{domain}:{source.country_id}:{value["scope_key"]}',
        evidence_version=job.id, ingestion_id=str(job.id), category='dataset_availability',
        title=f'{source.publisher} report availability', committed=True, fixture=False,
        quarantined=False, publishable=True, correction_pending=False, facts=[], report=report)


def _session(factory):
    db = factory()
    if db.new or db.dirty or db.deleted or db.identity_map or db.in_transaction():
        raise SourceObservationUnavailable('Fresh committed-reader session required')
    if db.get_bind().dialect.name != 'postgresql':
        db.close()
        raise SourceObservationUnavailable('PostgreSQL committed snapshot required')
    return db


def read_native_report_record_ids(factory, *, ingestion_id, domain):
    _positive_id(ingestion_id)
    with _session(factory) as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        _read_limits(db)
        job, _, _ = _job(db, ingestion_id, domain)
        return _ids(job, domain)


def read_native_report_observation(factory, *, record_id, ingestion_id, domain):
    _positive_id(record_id)
    _positive_id(ingestion_id)
    with _session(factory) as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        _read_limits(db)
        return current_native_report(db, record_id, ingestion_id, domain=domain)
