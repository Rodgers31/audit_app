"""Independent adversarial controls over actual OAG acquisition boundaries.

HTTP is an inert MockTransport; the downloader, receipt adapter and PostgreSQL
ORM execute. No live acquisition or production adoption is established.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select, update

from models import DocumentType, Extraction, IngestionJob, IngestionStatus, SourceDocument
from seeding.fetch_documents import fetch_document
from seeding.http_client import SeedingHttpClient
from seeding.types import DomainRunContext
from test_oag_acquisition_origin import BODY, URL, ensure, receipt_rows, setup_source


def fetch(db, source, client, settings, context, **changes):
    arguments = dict(url=source.url, country_id=source.country_id,
        publisher=source.publisher, title=source.title, doc_type=source.doc_type,
        dataset_id='oag_national_audits', acquisition_context=context)
    arguments.update(changes)
    return fetch_document(db, client, settings, **arguments)


@pytest.mark.parametrize('mismatch', ['country', 'publisher', 'doc_type', 'dataset'])
def test_declared_fetch_association_cannot_qualify_existing_different_source(db_session, tmp_path, mismatch):
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    before = deepcopy(dict(source.meta))
    old_identity = (source.country_id, source.publisher, source.doc_type, source.title, source.md5)
    changes = {
        'country': {'country_id': 987654},
        'publisher': {'publisher': 'A different institution'},
        'doc_type': {'doc_type': DocumentType.REPORT},
        'dataset': {'dataset_id': 'not-an-audit-dataset'},
    }[mismatch]
    with client() as http:
        with pytest.raises(ValueError):
            fetch(db_session, source, http, settings, context, **changes)
    assert requests == []
    assert receipt_rows(db_session) == []
    assert source.meta == before
    assert (source.country_id, source.publisher, source.doc_type, source.title, source.md5) == old_identity


@pytest.mark.parametrize('invalid', ['wrong_domain', 'stopped_job', 'dry_run'])
def test_invalid_origin_context_cannot_mutate_source_before_refusal(db_session, tmp_path, invalid):
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    job = db_session.get(IngestionJob, context.job_id)
    if invalid == 'wrong_domain': job.domain = 'pending_bills'
    elif invalid == 'stopped_job': job.status = IngestionStatus.FAILED
    else: context.dry_run = True
    db_session.flush()
    before = deepcopy(dict(source.meta))
    old = (source.title, source.last_seen_at, source.md5)
    with client() as http:
        with pytest.raises(ValueError):
            fetch(db_session, source, http, settings, context, title='Caller must not rename this source')
    assert requests == [] and receipt_rows(db_session) == []
    assert source.meta == before
    assert (source.title, source.last_seen_at, source.md5) == old


@pytest.mark.parametrize('changed', ['job_status', 'source_publisher', 'source_digest', 'source_duplicate'])
def test_current_rows_are_rechecked_after_actual_acquisition(db_session, tmp_path, changed):
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    def serve(request):
        requests.append(request)
        if changed == 'job_status':
            db_session.execute(update(IngestionJob).where(IngestionJob.id == context.job_id).values(status=IngestionStatus.FAILED))
        elif changed == 'source_publisher':
            db_session.execute(update(SourceDocument).where(SourceDocument.id == source.id).values(publisher='changed after acquisition started'))
        elif changed == 'source_digest':
            db_session.execute(update(SourceDocument).where(SourceDocument.id == source.id).values(md5='0'*32))
        else:
            db_session.add(SourceDocument(country_id=source.country_id, publisher=source.publisher,
                title='Concurrent duplicate source', url=source.url, doc_type=source.doc_type,
                fetch_date=datetime.now(timezone.utc)))
            db_session.flush()
        return httpx.Response(200, content=BODY, headers={'content-type':'application/pdf'}, request=request)
    with SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(serve)), receipt_store=store) as http:
        with pytest.raises(ValueError):
            ensure(db_session, context, source, http, settings)
    assert len(requests) == 1
    assert receipt_rows(db_session) == []


def test_exported_or_local_sidecar_cannot_create_runtime_origin(db_session, tmp_path):
    from services.response_receipts import capture_response
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    receipt = capture_response(httpx.Response(200, content=BODY,
        headers={'content-type':'application/pdf'}, request=httpx.Request('GET', URL)), store, source_kind='pdf')
    with client() as http:
        http._download_receipts = {URL: dict(receipt)}
        result = ensure(db_session, context, source, http, settings)
    assert result['origin_qualified'] is True
    assert db_session.scalars(select(Extraction.extractor)).all() == ['pdf-receipt-v1', 'pdf-receipt-v1']
    # The JSON copy is insufficient: a new actual downloader GET was necessary.
    assert len(requests) == 1
    original = db_session.get(Extraction, result['origin_extraction_id']).extracted_json['response_receipt']
    assert original['acquired_at'] != receipt['acquired_at']


def test_old_origin_mutation_after_validation_cannot_reuse_session_snapshot(db_session, tmp_path):
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    with client() as http:
        first = ensure(db_session, context, source, http, settings)
    origin = db_session.get(Extraction, first['origin_extraction_id'])
    changed = deepcopy(origin.extracted_json)
    changed['response_receipt']['content_encoding'] = 'changed original after validation'
    origin.extracted_json = changed
    db_session.flush()
    before = len(receipt_rows(db_session))
    with client() as http, pytest.raises(ValueError):
        ensure(db_session, context, source, http, settings)
    assert len(receipt_rows(db_session)) == before
    assert len(requests) == 1


def test_later_fetch_without_origin_context_does_not_keep_stale_qualified_origin(db_session, tmp_path):
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    with client() as http:
        fetched = fetch(db_session, source, http, settings, context)
    assert fetched.meta['audit_acquisition_origin_v1']['origin_qualified'] is True
    old_origin = deepcopy(fetched.meta['audit_acquisition_origin_v1'])
    changed_body = b'%PDF-1.7\nA later publisher edition\n%%EOF'
    settings.pdf_cache_ttl_seconds = 0
    with SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=changed_body, headers={'content-type':'application/pdf'}, request=request))), receipt_store=store) as http:
        fetched = fetch(db_session, source, http, settings, None)
    assert fetched.meta['pdf_artifact_v1']['sha256'] != old_origin['digest']
    origin = fetched.meta.get('audit_acquisition_origin_v1')
    assert not origin or origin.get('origin_qualified') is not True, 'Changed PDF edition retained a stale qualified origin diagnostic'


def test_preflight_must_read_current_source_association_without_identity_map_reuse(db_session, tmp_path):
    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    cached_publisher = source.publisher
    db_session.execute(update(SourceDocument).where(SourceDocument.id == source.id)
        .values(publisher='Current database publisher differs')
        .execution_options(synchronize_session=False))
    assert source.publisher == cached_publisher
    # Scalar DB reads prove the current source while preserving the stale ORM
    # object that a long-lived ingestion session can already have loaded.
    current = db_session.scalar(select(SourceDocument.publisher).where(SourceDocument.id == source.id))
    assert current != cached_publisher
    before_meta = deepcopy(db_session.scalar(select(SourceDocument.meta).where(SourceDocument.id == source.id)))
    before_title = db_session.scalar(select(SourceDocument.title).where(SourceDocument.id == source.id))
    with client() as http:
        with pytest.raises(ValueError):
            fetch(db_session, source, http, settings, context, title='Must never rename a different current source')
    assert requests == [] and receipt_rows(db_session) == []
    assert db_session.scalar(select(SourceDocument.meta).where(SourceDocument.id == source.id)) == before_meta
    assert db_session.scalar(select(SourceDocument.title).where(SourceDocument.id == source.id)) == before_title


def test_other_transaction_source_change_during_http_cannot_bank_layer_two_mutations(db_session, tmp_path):
    from sqlalchemy import delete, text
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.orm import Session
    from models import Country

    engine = db_session.get_bind().engine
    owned = {}
    # These rows must be visible to the independent writer; unlike the usual
    # case fixture this session commits its own uniquely allocated rows.
    with Session(engine) as owner:
        try:
            settings, store, client, source, context, requests = setup_source(owner, tmp_path)
            owned = dict(source=source.id, job=context.job_id, country=source.country_id)
            before_meta = deepcopy(source.meta)
            before_title = source.title
            settings.pdf_cache_ttl_seconds = 0
            changed = []
            blocked = []
            def serve(request):
                requests.append(request)
                try:
                    with engine.begin() as independent:
                        independent.execute(text("SET LOCAL lock_timeout='100ms'"))
                        independent.execute(update(SourceDocument).where(SourceDocument.id == owned['source'])
                            .values(publisher='Publisher changed by independent committed transaction'))
                    changed.append(True)
                except DBAPIError as exc:
                    # A real row lock is an acceptable stronger serialization.
                    if getattr(exc.orig, 'pgcode', None) != '55P03':
                        raise
                    blocked.append(True)
                return httpx.Response(200, content=BODY, headers={'content-type':'application/pdf'}, request=request)
            error = None
            with SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(serve)), receipt_store=store) as http:
                try:
                    fetched = fetch(owner, source, http, settings, context, title='Rename requires the same current publisher')
                except ValueError as exc:
                    error = exc
            assert len(requests) == 1
            if changed:
                assert error is not None, 'Fetch returned after L2 writes despite a committed current-source reassignment during HTTP'
                assert owner.scalar(select(SourceDocument.meta).where(SourceDocument.id == owned['source'])) == before_meta
                assert owner.scalar(select(SourceDocument.title).where(SourceDocument.id == owned['source'])) == before_title
                assert owner.scalars(select(Extraction.id).where(Extraction.source_document_id == owned['source'])).all() == []
            else:
                assert blocked and error is None
                assert fetched.meta['audit_acquisition_origin_v1']['origin_qualified'] is True
                assert fetched.publisher == 'Office of the Auditor-General'
        finally:
            owner.rollback()
            if owned:
                with engine.begin() as cleanup:
                    cleanup.execute(delete(Extraction).where(Extraction.source_document_id == owned['source']))
                    cleanup.execute(delete(SourceDocument).where(SourceDocument.id == owned['source']))
                    cleanup.execute(delete(IngestionJob).where(IngestionJob.id == owned['job']))
                    cleanup.execute(delete(Country).where(Country.id == owned['country']))
                    assert cleanup.scalar(select(SourceDocument.id).where(SourceDocument.id == owned['source'])) is None
                    assert cleanup.scalar(select(IngestionJob.id).where(IngestionJob.id == owned['job'])) is None
                    assert cleanup.scalar(select(Country.id).where(Country.id == owned['country'])) is None


def test_direct_origin_hostile_shape_matrix_never_qualifies_or_writes(db_session, tmp_path):
    from types import SimpleNamespace
    from seeding.domains.audits.acquisition import ensure_audit_origin

    settings, store, client, source, context, requests = setup_source(db_session, tmp_path)
    hostile = [None, True, False, 0, -1, '', '1', {}, [], float('nan'), float('inf'), -float('inf')]
    malformed_contexts = [None, {}, [], '', 0, True, object(), SimpleNamespace(),
        SimpleNamespace(job_id=True, dry_run=False), SimpleNamespace(job_id=context.job_id, dry_run=0),
        {'job_id': context.job_id, 'dry_run': False}, SimpleNamespace(job_id=context.job_id)]
    with client() as http:
        for source_id in hostile:
            with pytest.raises(ValueError):
                ensure_audit_origin(db_session, context, source_id, http, settings, max_seconds=5)
        for seconds in hostile:
            with pytest.raises(ValueError):
                ensure_audit_origin(db_session, context, source.id, http, settings, max_seconds=seconds)
        for bad_context in malformed_contexts:
            with pytest.raises(ValueError):
                ensure_audit_origin(db_session, bad_context, source.id, http, settings, max_seconds=5)
    assert len(hostile) * 2 + len(malformed_contexts) == 36
    assert requests == [] and receipt_rows(db_session) == []
