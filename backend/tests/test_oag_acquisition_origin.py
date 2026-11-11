"""Prospective audit HTTP origin at real PostgreSQL and provider seams.

Mock HTTP supplies inert PDF bytes. The actual downloader, disk cache, receipt
adapter, ORM and retained replay run; this is not a live publisher observation.
"""
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json

import httpx
import pytest
from sqlalchemy import select

from models import Country, DocumentType, Extraction, IngestionJob, IngestionStatus, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains import audits
from seeding.extractors.reconciliation import IncompleteExtraction
from seeding.fetch_documents import fetch_document
from seeding.http_client import SeedingHttpClient
from seeding.oag_discovery import CountyAuditDiscovery
from seeding.types import DomainRunContext
from services.receipt_store import LocalReceiptStore

URL = 'https://www.oagkenya.go.ke/wp-content/uploads/2026/BLUE-BOOK-NATIONAL-GOVERNMENT-2024-2025.pdf'
BODY = b'%PDF-1.7\nOwned inert audit edition\n%%EOF'


def setup_source(db_session, tmp_path):
    if db_session.get_bind().dialect.name != 'postgresql':
        pytest.skip('requires owned PostgreSQL')
    country = Country(iso_code='KEN', name='Kenya', currency='KES', timezone='Africa/Nairobi', default_locale='en-KE')
    db_session.add(country)
    job = IngestionJob(domain='audits', status=IngestionStatus.RUNNING, dry_run=False,
                       started_at=datetime.now(timezone.utc), errors=[], meta={})
    db_session.add(job)
    db_session.flush()
    settings = SeedingSettings(cache_path=tmp_path/'cache', storage_path=tmp_path/'store',
        http_cache_enabled=False, rate_limit='10000/sec', pdf_download_timeout_seconds=5,
        pdf_download_max_bytes=65536, audits_county_start_budget_seconds=60)
    store = LocalReceiptStore(tmp_path/'receipts', max_bytes=65536)
    requests = []
    def serve(request):
        requests.append(request)
        return httpx.Response(200, content=BODY, headers={'content-type':'application/pdf'}, request=request)
    def client():
        return SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(serve)), receipt_store=store)
    with client() as first:
        source = fetch_document(db_session, first, settings, url=URL, country_id=country.id,
            publisher='Office of the Auditor-General', title=URL.rsplit('/',1)[-1],
            doc_type=DocumentType.AUDIT, dataset_id='oag_national_audits')
    db_session.commit()
    requests.clear()
    return settings, store, client, source, DomainRunContext(None, False, job.id), requests


def test_normal_ingestion_recovers_origin_before_held_parser(db_session, tmp_path, monkeypatch):
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    # The previous acquisition capability died with its client; only cached bytes
    # and an untrusted sidecar survive. Recovery must perform a new official GET.
    monkeypatch.setattr(audits, 'create_http_client', lambda _: client())
    monkeypatch.setattr('seeding.oag_discovery.discover_county_audit_documents',
                        lambda _: CountyAuditDiscovery())
    monkeypatch.setattr(audits.fetcher, '_discover_audit_pdfs_via_wp_api', lambda *a, **k: [])
    def held_parser(*args, **kwargs):
        raise IncompleteExtraction('owned unresolved content hold')
    monkeypatch.setattr('seeding.extractors.get_parser', lambda _: held_parser)
    result = audits.run(db_session, settings, context)
    origins = db_session.scalars(select(Extraction).where(
        Extraction.source_document_id == source.id, Extraction.extractor == 'pdf-receipt-v1')).all()
    assert origins, 'Normal ingestion never persisted the actual HTTP acquisition before the content hold'
    origin = next(r for r in origins if 'retained_pdf_validation' not in r.extracted_json['response_receipt'])
    receipt = origin.extracted_json['response_receipt']
    assert receipt['status'] == 200
    assert 'acquisition_kind' not in receipt
    assert receipt['request_url'] == receipt['response_url'] == URL
    assert receipt['digest'] == hashlib.sha256(BODY).hexdigest()
    assert store.read(receipt['storage_key']) == BODY
    assert len(requests) == 1 and requests[0].method == 'GET'
    assert any('owned unresolved content hold' in e for e in result.errors)
    assert not result.metadata['refresh_completion']['complete']
    assert db_session.get(SourceDocument, source.id).meta['audit_acquisition_origin_v1']['origin_extraction_id'] == origin.id


def ensure(db, context, source, client, settings, **kwargs):
    from seeding.domains.audits.acquisition import ensure_audit_origin
    return ensure_audit_origin(db, context, source.id, client, settings, max_seconds=kwargs.get('max_seconds', 5))


def receipt_rows(db):
    return db.scalars(select(Extraction).where(Extraction.extractor == 'pdf-receipt-v1').order_by(Extraction.id)).all()


def test_origin_and_new_job_replay_keep_original_time_and_immutable_bytes(db_session, tmp_path):
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    with client() as http:
        first = ensure(db_session, context, source, http, settings)
    assert first['state'] == 'persisted' and first['origin_qualified'] is True
    assert first['native_publication_authority'] is False
    assert len(receipt_rows(db_session)) == 2
    origin = db_session.get(Extraction, first['origin_extraction_id'])
    original = json.loads(json.dumps(origin.extracted_json))
    job = IngestionJob(domain='audits', status=IngestionStatus.RUNNING, dry_run=False,
        started_at=datetime.now(timezone.utc), errors=[], meta={})
    db_session.add(job); db_session.flush()
    with client() as http:
        second = ensure(db_session, DomainRunContext(None, False, job.id), source, http, settings)
    assert second['state'] == 'replayed'
    assert second['origin_extraction_id'] == first['origin_extraction_id']
    assert second['validation_extraction_id'] != first['validation_extraction_id']
    assert len(requests) == 1 and len(receipt_rows(db_session)) == 3
    db_session.expire_all()
    assert db_session.get(Extraction, origin.id).extracted_json == original
    proof = db_session.get(Extraction, second['validation_extraction_id']).extracted_json['response_receipt']
    assert proof['acquired_at'] == original['response_receipt']['acquired_at']
    assert proof['retained_pdf_validation']['ingestion_id'] == job.id
    assert proof['retained_pdf_validation']['validated_at'] >= job.started_at.isoformat()


@pytest.mark.parametrize('change', ['domain', 'stopped', 'dry_job', 'missing_job', 'missing_context',
    'bool_id', 'zero_id', 'negative_id', 'future_job', 'isolation', 'wrong_country', 'wrong_type',
    'wrong_publisher', 'wrong_url', 'duplicate_url', 'artifact_digest', 'artifact_size', 'artifact_type',
    'absent_file', 'corrupt_file', 'body_changed', 'mime', 'status'])
def test_refused_context_or_edition_does_not_fetch_or_write_receipts(db_session, tmp_path, change):
    from datetime import timedelta
    from sqlalchemy import text
    from seeding.domains.audits.acquisition import AuditOriginUnavailable
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    job = db_session.get(IngestionJob, context.job_id)
    if change == 'domain': job.domain = 'pending_bills'
    elif change == 'stopped': job.status = IngestionStatus.FAILED
    elif change == 'dry_job': job.dry_run = True
    elif change == 'missing_job': context.job_id = 98765
    elif change == 'missing_context': context = None
    elif change == 'bool_id': context.job_id = True
    elif change == 'zero_id': context.job_id = 0
    elif change == 'negative_id': context.job_id = -1
    elif change == 'future_job': job.started_at = datetime.now(timezone.utc) + timedelta(days=1)
    elif change == 'wrong_country': db_session.get(Country, source.country_id).iso_code = 'UGA'
    elif change == 'wrong_type': source.doc_type = DocumentType.REPORT
    elif change == 'wrong_publisher': source.publisher = 'Wrong publisher'
    elif change == 'wrong_url': source.url = 'https://publisher.invalid/audit.pdf'
    elif change == 'duplicate_url':
        db_session.add(SourceDocument(country_id=source.country_id, publisher=source.publisher,
            title='Duplicate', url=source.url, doc_type=DocumentType.AUDIT, fetch_date=source.fetch_date))
    elif change.startswith('artifact_'):
        artifact = dict(source.meta['pdf_artifact_v1'])
        artifact[{'artifact_digest':'sha256', 'artifact_size':'size_bytes', 'artifact_type':'schema_version'}[change]] = True if change == 'artifact_type' else 'wrong'
        source.meta = {**source.meta, 'pdf_artifact_v1': artifact}
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(source, 'meta')
    elif change == 'absent_file': __import__('pathlib').Path(source.file_path).unlink()
    elif change == 'corrupt_file': __import__('pathlib').Path(source.file_path).write_bytes(b'corrupt')
    elif change == 'body_changed': __import__('pathlib').Path(source.file_path).write_bytes(b'%PDF-1.7\nchanged\n%%EOF')
    elif change == 'mime': source.content_type = 'text/html'
    elif change == 'status': source.http_status = 206
    db_session.commit()
    if change == 'isolation':
        from sqlalchemy.orm import Session
        with db_session.get_bind().engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
            with Session(bind=connection) as isolated, client() as http:
                assert isolated.scalar(text('SHOW transaction_isolation')) == 'repeatable read'
                with pytest.raises(AuditOriginUnavailable, match='context_refused'):
                    ensure(isolated, context, source, http, settings)
        assert requests == [] and receipt_rows(db_session) == []
        return
    with client() as http, pytest.raises((AuditOriginUnavailable, ValueError)):
        ensure(db_session, context, source, http, settings)
    assert requests == [] and receipt_rows(db_session) == []


@pytest.mark.parametrize('value', [None, True, False, 0, -1, float('nan'), float('inf'), '5'])
def test_direct_acquisition_rejects_hostile_time_bounds(db_session, tmp_path, value):
    from seeding.domains.audits.acquisition import AuditOriginUnavailable
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    with client() as http, pytest.raises(AuditOriginUnavailable, match='limits_refused'):
        ensure(db_session, context, source, http, settings, max_seconds=value)
    assert requests == [] and receipt_rows(db_session) == []


def test_default_download_ceiling_is_intersected_with_receipt_limit(db_session, tmp_path):
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    settings.pdf_download_max_bytes = SeedingSettings().pdf_download_max_bytes
    with client() as http:
        assert ensure(db_session, context, source, http, settings)['origin_qualified'] is True


@pytest.mark.parametrize('failure', ['different_edition', 'html', 'partial', 'http_failure', 'interrupted'])
def test_partial_or_wrong_official_response_writes_no_origin_and_cleans_temp(db_session, tmp_path, monkeypatch, failure):
    import tempfile
    from seeding.domains.audits.acquisition import AuditOriginUnavailable
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    scratch = tmp_path/'owned-scratch'; scratch.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(scratch))
    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield b'%PDF-1.7\npartial'
            raise httpx.ReadError('owned interrupted stream')
    def serve(request):
        body = b'%PDF-1.7\ndifferent\n%%EOF' if failure == 'different_edition' else b'<html>not a PDF</html>' if failure == 'html' else BODY
        return httpx.Response(206 if failure == 'partial' else 503 if failure == 'http_failure' else 200,
            headers={'content-type':'text/html' if failure == 'html' else 'application/pdf'},
            stream=Interrupted() if failure == 'interrupted' else httpx.ByteStream(body), request=request)
    with SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(serve)), receipt_store=store) as http:
        with pytest.raises((AuditOriginUnavailable, ValueError)):
            ensure(db_session, context, source, http, settings)
    assert receipt_rows(db_session) == []
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize('stage', ['put', 'final_persistence_read'])
def test_retention_refusal_rolls_back_origin_and_keeps_failed_retention(db_session, tmp_path, stage):
    from services.receipt_retention import RetentionScope
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    class RefusingStore(LocalReceiptStore):
        reads = 0
        def put(self, body):
            if stage == 'put': raise ValueError('owned retention refusal')
            return super().put(body)
        def read(self, key):
            self.reads += 1
            if stage == 'final_persistence_read' and self.reads >= 3:
                raise OSError('owned readback interrupted')
            return super().read(key)
    refusing = RefusingStore(tmp_path/'refusing', max_bytes=65536)
    scope = RetentionScope()
    try:
        with client() as http:
            http.receipt_store = refusing
            with pytest.raises(ValueError): ensure(db_session, context, source, http, settings)
        assert receipt_rows(db_session) == []
        assert scope.summary()['missing'] == 1
    finally:
        scope.close()


def test_stale_origin_requires_new_actual_get_and_preserves_old_original(db_session, tmp_path):
    from datetime import timedelta
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    with client() as http:
        first = ensure(db_session, context, source, http, settings)
    origin = db_session.get(Extraction, first['origin_extraction_id'])
    old = json.loads(json.dumps(origin.extracted_json))
    # Owned DB tampering models an expired original, without editing a runtime
    # capability or using it as the new acquisition.
    old['response_receipt']['acquired_at'] = (datetime.now(timezone.utc)-timedelta(days=31)).isoformat()
    origin.extracted_json = old
    db_session.commit()
    with client() as http:
        second = ensure(db_session, context, source, http, settings)
    assert second['state'] == 'persisted' and second['reason'] == 'origin_stale'
    assert second['origin_extraction_id'] != first['origin_extraction_id']
    assert len(requests) == 2
    assert db_session.get(Extraction, first['origin_extraction_id']).extracted_json == old


@pytest.mark.parametrize('change', ['destination', 'missing_bytes', 'corrupt_bytes'])
def test_retained_origin_storage_refusal_is_distinct_and_cannot_create_authority(db_session, tmp_path, change):
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    with client() as http:
        ensure(db_session, context, source, http, settings)
    count = len(receipt_rows(db_session))
    checksum = hashlib.sha256(BODY).hexdigest()
    if change == 'destination': store.storage_scope = 'different-private-destination'
    elif change == 'missing_bytes': store._path(checksum).unlink()
    else: store._path(checksum).write_bytes(b'corrupt')
    from sqlalchemy.orm import Session
    # A fresh DB session cannot inherit the one-read immutable provider snapshot.
    with Session(bind=db_session.get_bind(), join_transaction_mode='create_savepoint') as cold:
        with client() as http, pytest.raises((OSError, ValueError)):
            ensure(cold, context, source, http, settings)
    assert len(receipt_rows(db_session)) == count and len(requests) == 1


def test_actual_r2_adapter_conditional_existing_put_and_replay(db_session, tmp_path):
    from test_r2_receipt_store import Boundary
    settings, local, client, source, context, requests = setup_source(db_session, tmp_path)
    boundary = Boundary(tmp_path/'provider')
    store = boundary.store()
    # Existing object is idempotent retention, not an acquisition or incident.
    store.put(BODY)
    with client() as http:
        http.receipt_store = store
        first = ensure(db_session, context, source, http, settings)
    puts = [r for r in boundary.requests if r.method == 'PUT']
    assert len(puts) >= 2 and any(puts[i].url == puts[j].url for i in range(len(puts)) for j in range(i))
    with client() as http:
        http.receipt_store = boundary.store()
        second = ensure(db_session, context, source, http, settings)
    assert first['origin_extraction_id'] == second['origin_extraction_id']
    assert len(requests) == 1


def test_origin_recovery_uses_remaining_fetch_budget(db_session, tmp_path, monkeypatch):
    from types import SimpleNamespace
    import seeding.fetch_documents as fetching
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    clock = iter([100.0, 102.0])
    monkeypatch.setattr(fetching, 'time', SimpleNamespace(monotonic=lambda: next(clock)), raising=False)
    caps = []
    with client() as http:
        download = http.download_to_file
        def observed(url, path, **kwargs):
            caps.append(kwargs['max_seconds'])
            return download(url, path, **kwargs)
        monkeypatch.setattr(http, 'download_to_file', observed)
        fetched = fetch_document(db_session, http, settings, url=URL, country_id=source.country_id,
            publisher=source.publisher, title=source.title, doc_type=source.doc_type,
            dataset_id='oag_national_audits', acquisition_context=context, max_seconds=5)
    assert caps and caps[0] <= 3, 'Origin recovery restarted the full per-document download budget'
    assert fetched.meta['audit_acquisition_origin_v1']['origin_qualified'] is True


def test_origin_and_revalidation_are_auxiliary_evidence_not_findings(db_session, tmp_path):
    from seeding.domains.audits.scope import verify_extraction_evidence
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    with client() as http:
        proof = ensure(db_session, context, source, http, settings)
    # Explicit inert canonical finding seam: this checks SQL classification,
    # not source-plan admission or whether a national PDF is a county volume.
    entry = dict(fiscal_year='2024/2025', institution='executives', label='Owned auxiliary classification')
    finding = Extraction(source_document_id=source.id, extractor='oag_county_volume', page_number=1,
        extracted_json=dict(schema='oag_county_volume/v1', fiscal_year=entry['fiscal_year'],
            volume_kind=entry['institution'], finding_text='Owned inert source evidence',
            entity_name='County Executive of Example', severity='WARNING'))
    db_session.add(finding); db_session.flush()
    verify_extraction_evidence(db_session, source, entry)
    assert len(receipt_rows(db_session)) == 2
    assert proof['native_publication_authority'] is False
