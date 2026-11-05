"""Independent current-source nonmutation on failed actual PDF transfer.

Owned PostgreSQL, actual downloader/cache and ORM; inert MockTransport body.
"""
from copy import deepcopy
from datetime import datetime, timezone
import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session
from models import Country, Extraction, IngestionJob, SourceDocument
from seeding.fetch_documents import fetch_document
from seeding.http_client import SeedingHttpClient
from test_oag_acquisition_origin import setup_source


def test_failed_pdf_transfer_cannot_mutate_reassigned_current_source(db_session, tmp_path):
    engine = db_session.get_bind().engine
    owned = {}
    with Session(engine) as owner:
        try:
            settings, store, _, source, context, requests = setup_source(owner, tmp_path)
            owned = dict(source=source.id, job=context.job_id, country=source.country_id)
            before = dict(meta=deepcopy(source.meta), status=source.status,
                seen=source.last_seen_at, http_status=source.http_status, title=source.title)
            settings.pdf_cache_ttl_seconds = 0
            changed = []
            def serve(request):
                requests.append(request)
                with engine.begin() as independent:
                    independent.execute(update(SourceDocument).where(SourceDocument.id == owned['source'])
                        .values(publisher='Independent committed publisher after preflight'))
                changed.append(True)
                return httpx.Response(200, content=b'<html>owned non-PDF response</html>',
                    headers={'content-type':'application/pdf'}, request=request)
            error = None
            with SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(serve)), receipt_store=store) as client:
                try:
                    fetch_document(owner, client, settings, url=source.url, country_id=source.country_id,
                        publisher=source.publisher, title=source.title, doc_type=source.doc_type,
                        dataset_id='oag_national_audits', acquisition_context=context, max_seconds=5)
                except Exception as exc:
                    error = type(exc).__name__ + ': ' + str(exc)
            assert changed == [True] and len(requests) == 1
            assert error is not None
            print('actual_refusal=' + error)
            current = owner.execute(select(SourceDocument.meta,SourceDocument.status,SourceDocument.last_seen_at,
                SourceDocument.http_status,SourceDocument.title).where(SourceDocument.id == owned['source'])).one()
            assert dict(meta=current[0],status=current[1],seen=current[2],http_status=current[3],title=current[4]) == before, 'Failed transfer mutated the reassigned current source before identity refusal'
            assert owner.scalars(select(Extraction.id).where(Extraction.source_document_id == owned['source'])).all() == []
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


def test_same_source_failed_transfer_keeps_honest_failure_diagnostic(db_session, tmp_path):
    from models import DocumentStatus
    from seeding.http_client import PdfDownloadError
    import pytest
    settings, store, _, source, context, requests = setup_source(db_session, tmp_path)
    settings.pdf_cache_ttl_seconds = 0
    def serve(request):
        requests.append(request)
        return httpx.Response(200, content=b'<html>owned non-PDF response</html>',
            headers={'content-type':'application/pdf'}, request=request)
    with SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(serve)), receipt_store=store) as client:
        with pytest.raises(PdfDownloadError):
            fetch_document(db_session, client, settings, url=source.url, country_id=source.country_id,
                publisher=source.publisher, title=source.title, doc_type=source.doc_type,
                dataset_id='oag_national_audits', acquisition_context=context, max_seconds=5)
    assert len(requests) == 1
    assert source.status == DocumentStatus.FAILED
    assert source.meta['fetch_error']
    assert db_session.scalars(select(Extraction.id).where(Extraction.source_document_id == source.id)).all() == []
