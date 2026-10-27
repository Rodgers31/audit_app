"""Owned cached-source producer -> PostgreSQL -> draft-preview regression."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from copy import deepcopy

import httpx
import pytest
from sqlalchemy import select, delete, update, text

from models import Country, Entity, Extraction, SourceDocument, IngestionJob, IngestionStatus, DocumentStatus
from seeding.config import SeedingSettings
from seeding.types import DomainRunContext
from seeding.source_observations import read_native_report_record_ids
from social.generation.preview import preview
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_response, acquisition_is_intact
from test_b83_generation_postgres import pg, no_publication
from test_b86_native_postgres import enable
from test_native_publisher_metadata import inputs, listing, COUNTY_TITLE, COUNTY_PAGE
from test_cbirr_year_end_payables import _entries


@pytest.fixture(autouse=True)
def genuine_pdf_acquisitions(monkeypatch):
    # Legacy publisher fixtures default to an API acquisition. The retained
    # producer requires an actual PDF capture, never edited persisted JSON.
    import test_native_publisher_metadata as metadata
    def capture(response, store):
        kind = 'pdf' if response.headers.get('content-type') == 'application/pdf' else 'api'
        return capture_response(response, store, source_kind=kind)
    monkeypatch.setattr(metadata, 'capture_response', capture)


def test_actual_county_producer_cache_hit_keeps_exact_new_job_lineage(pg, tmp_path, monkeypatch):
    from seeding.domains import pending_bills as domain
    from seeding import cob_cbirr, pdf_parsers
    factory, _ = pg
    enable(factory, monkeypatch)
    from test_pending_bills_aging_persistence import populate_counties
    with factory.begin() as db:
        db.execute(delete(Entity))
        populate_counties(db, db.scalar(select(Country.id)))
    shared = LocalReceiptStore(tmp_path / 'receipts')
    path, _, _ = inputs(tmp_path, 'pending_bills')
    url = COUNTY_PAGE + '?wpdmdl=16482'
    state = {'fresh': True, 'receipts': {}}

    class Client:
        receipt_store = shared

        def get(self, requested, **kwargs):
            body = f'''<a href='#' onclick="location.href='{url}'">Download</a>'''.encode()
            return httpx.Response(200, content=body, request=httpx.Request('GET', requested))

        def download_receipt(self, requested):
            return state['receipts'].get(requested)

        def download_to_file(self, requested, destination, **kwargs):
            body = listing(COUNTY_TITLE, COUNTY_PAGE, 16482)
            destination.write_bytes(body)
            state['receipts'][requested] = capture_response(httpx.Response(200, content=body,
                headers={'content-type':'text/html'}, request=httpx.Request('GET', requested)), shared)

    client = Client()

    def download(*args):
        if state['fresh']:
            state['receipts'][url] = capture_response(httpx.Response(200, content=path.read_bytes(),
                headers={'content-type':'application/pdf'}, request=httpx.Request('GET', url)), shared, source_kind='pdf')
        return SimpleNamespace(path=path)

    class StockParser:
        def __init__(self, path): pass
        def parse(self): return _entries()

    monkeypatch.setattr(cob_cbirr, 'download_cbirr', download)
    monkeypatch.setattr(pdf_parsers, 'CbirrYearEndPayablesParser', StockParser)
    monkeypatch.setattr(domain, 'create_http_client', lambda _: nullcontext(client))
    settings = SeedingSettings(cache_path=tmp_path / 'cache', storage_path=tmp_path, parse_cache_enabled=False)
    (settings.cache_path / 'pdfs').mkdir(parents=True, exist_ok=True)
    ids = []
    for fresh in (True, False):
        state['fresh'] = fresh
        state['receipts'].clear()
        with factory.begin() as db:
            job = IngestionJob(domain='pending_bills', status=IngestionStatus.RUNNING, dry_run=False,
                started_at=datetime.now(timezone.utc), errors=[], meta={'source_mode':'live'})
            db.add(job); db.flush(); job_id = job.id
            errors = []
            domain._seed_counties(db, settings, DomainRunContext(None, False, job.id), errors)
            assert not errors, errors
            job.status = IngestionStatus.COMPLETED
            job.finished_at = datetime.now(timezone.utc)
        records = read_native_report_record_ids(factory, ingestion_id=job_id, domain='pending_bills')
        assert len(records) == 1, 'Cached-source success lost exact current-job report lineage'
        result = preview(factory, dict(domain='pending_bills', record_ids=list(records), ingestion_id=job_id,
            reports=True, backfill=False))
        assert result['results'][0]['status'] == 'baseline', result
        ids.append((job_id, records[0]))
    assert ids[0][0] != ids[1][0] and ids[0][1] != ids[1][1]
    no_publication(factory)


def retained_context(factory, tmp_path, domain):
    from test_native_publisher_postgres import ingest
    _, origin = ingest(factory, tmp_path, domain=domain)
    with factory.begin() as db:
        source = db.scalar(select(SourceDocument))
        source_id, url = source.id, source.url
        job = IngestionJob(domain=domain, status=IngestionStatus.RUNNING, dry_run=False,
            started_at=datetime.now(timezone.utc), errors=[], meta={'source_mode':'live'})
        db.add(job); db.flush(); job_id = job.id
    return source_id, origin, url, DomainRunContext(None, False, job_id)


def test_actual_streamed_pdf_origin_supports_retained_lineage(pg, tmp_path, monkeypatch):
    import test_native_publisher_metadata as metadata
    from seeding.http_client import SeedingHttpClient
    from services.response_receipts import capture_retained_pdf
    factory, _ = pg
    enable(factory, monkeypatch)
    store = LocalReceiptStore(tmp_path / 'receipts')
    def stream_capture(response, unused_store):
        if response.headers.get('content-type') != 'application/pdf':
            return capture_response(response, store)
        def serve(request):
            return httpx.Response(200, content=response.content,
                headers={'content-type':'application/pdf'}, request=request)
        with SeedingHttpClient(SeedingSettings(),
                client=httpx.Client(transport=httpx.MockTransport(serve)), receipt_store=store) as client:
            client.download_to_file(str(response.request.url), tmp_path / 'streamed.pdf',
                max_seconds=5, max_bytes=65536)
            return client.download_receipt(str(response.request.url))
    monkeypatch.setattr(metadata, 'capture_response', stream_capture)
    _, origin, url, context = retained_context(factory, tmp_path, 'pending_bills')
    with factory() as db:
        original = db.get(Extraction, origin).extracted_json['response_receipt']
        assert original['digest_scope'] == 'decoded_stream_body'
        receipt = capture_retained_pdf(db, context, store, domain='pending_bills',
            url=url, body=(tmp_path / 'report.pdf').read_bytes())
        assert receipt['digest_scope'] == original['digest_scope']
        assert receipt['acquired_at'] == original['acquired_at']
        assert acquisition_is_intact(receipt)
    no_publication(factory)


def test_retained_issuance_refuses_stale_snapshot_isolation(pg, tmp_path, monkeypatch):
    from services.response_receipts import capture_retained_pdf
    factory, _ = pg
    enable(factory, monkeypatch)
    _, _, url, context = retained_context(factory, tmp_path, 'pending_bills')
    store = LocalReceiptStore(tmp_path / 'receipts')
    body = (tmp_path / 'report.pdf').read_bytes()
    with factory() as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
        with pytest.raises(ValueError, match='READ COMMITTED'):
            capture_retained_pdf(db, context, store, domain='pending_bills', url=url, body=body)
    no_publication(factory)


@pytest.mark.parametrize('domain', ['pending_bills', 'national_budget'])
@pytest.mark.parametrize('post_state', ['missing', 'unchanged', 'modified'])
def test_cached_pdf_full_day_still_requires_current_publisher_post(pg, tmp_path, monkeypatch, domain, post_state):
    import test_native_publisher_metadata as metadata
    from services.response_receipts import capture_retained_pdf
    from seeding.native_report_authority import capture_pdf_report
    from seeding.cob_report_metadata import validate_stored_post
    factory, _ = pg
    enable(factory, monkeypatch)
    pdf_bytes = metadata.pdf_bytes
    monkeypatch.setattr(metadata, 'pdf_bytes', lambda **_: pdf_bytes(label='Publication date: 2026-09-04'))
    _, _, url, context = retained_context(factory, tmp_path, domain)
    store = LocalReceiptStore(tmp_path / 'receipts')
    path = tmp_path / 'report.pdf'
    with factory() as db:
        receipt = capture_retained_pdf(db, context, store, domain=domain, url=url, body=path.read_bytes())
        if post_state == 'missing':
            assert capture_pdf_report(path, receipt, domain=domain)[0] is None
            return
        page, title, identifier = (metadata.PAGE, metadata.TITLE, 16454) if domain == 'national_budget' else (COUNTY_PAGE, COUNTY_TITLE, 16482)
        html = listing(title, page, identifier)
        if post_state == 'modified':
            changed = (datetime.fromisoformat(receipt['acquired_at']) + timedelta(microseconds=1)).isoformat()
            html = html.replace(b'2026-10-14T08:40:37+00:00', changed.encode())
        current = metadata.acquisition(tmp_path, html, page, 'text/html')
        calls = []
        def loader(): calls.append(True); return current
        authority, reason = capture_pdf_report(path, receipt, domain=domain, publisher_loader=loader)
        assert calls == [True]
        if post_state == 'modified': assert authority is None
        else:
            assert authority is not None, reason
            value = deepcopy(authority.value)
            value.pop('publication_authority')
            with pytest.raises(ValueError, match='Current publisher post'):
                validate_stored_post(value, authority.receipt)
    no_publication(factory)


def test_retained_writer_refuses_publisher_check_before_current_job(pg, tmp_path, monkeypatch):
    from test_native_publisher_postgres import ingest
    from test_native_publisher_metadata import acquisition, TITLE, PAGE
    from services.response_receipts import capture_retained_pdf
    from seeding.native_report_authority import capture_pdf_report, persist_native_report
    factory, _ = pg
    enable(factory, monkeypatch)
    old_job, old_record = ingest(factory, tmp_path, domain='national_budget')
    post = acquisition(tmp_path, listing(TITLE, PAGE, 16454), PAGE, 'text/html')
    with factory.begin() as db:
        source = db.scalar(select(SourceDocument))
        job = IngestionJob(domain='national_budget', status=IngestionStatus.RUNNING, dry_run=False,
            started_at=datetime.now(timezone.utc), errors=[], meta={'source_mode':'live'})
        db.add(job); db.flush()
        context = DomainRunContext(None, False, job.id)
        path = tmp_path / 'report.pdf'
        receipt = capture_retained_pdf(db, context, LocalReceiptStore(tmp_path / 'receipts'),
            domain='national_budget', url=source.url, body=path.read_bytes())
        authority, reason = capture_pdf_report(path, receipt, domain='national_budget', publisher_receipt=post)
        assert authority is not None, reason
        with pytest.raises(ValueError, match='publisher post chronology'):
            with db.begin_nested():
                persist_native_report(db, source, authority, context=context, domain='national_budget')
        assert 'native_report_records' not in job.meta
    assert preview(factory, dict(domain='national_budget', record_ids=[old_record], ingestion_id=old_job,
        reports=True, backfill=False))['results'][0]['status'] == 'baseline'
    no_publication(factory)


@pytest.mark.parametrize('state', [IngestionStatus.COMPLETED, IngestionStatus.FAILED])
def test_retained_issuance_rechecks_externally_closed_job(pg, tmp_path, monkeypatch, state):
    from services.response_receipts import capture_retained_pdf
    factory, _ = pg
    enable(factory, monkeypatch)
    _, _, url, context = retained_context(factory, tmp_path, 'pending_bills')
    store = LocalReceiptStore(tmp_path / 'receipts')
    body = (tmp_path / 'report.pdf').read_bytes()
    with factory() as db:
        held = db.get(IngestionJob, context.job_id)
        assert held.status == IngestionStatus.RUNNING
        capture_retained_pdf(db, context, store, domain='pending_bills', url=url, body=body)
        with factory.begin() as other:
            other.execute(update(IngestionJob).where(IngestionJob.id == held.id)
                .values(status=state, finished_at=datetime.now(timezone.utc)))
        with pytest.raises(ValueError, match='running native job'):
            capture_retained_pdf(db, context, store, domain='pending_bills', url=url, body=body)
    no_publication(factory)


@pytest.mark.parametrize('field,value', [('content_encoding', 'gzip'), ('digest_scope', 'unreviewed')])
def test_retained_issuance_refuses_original_core_change(pg, tmp_path, monkeypatch, field, value):
    from services.response_receipts import capture_retained_pdf
    factory, _ = pg
    enable(factory, monkeypatch)
    _, origin, url, context = retained_context(factory, tmp_path, 'pending_bills')
    store = LocalReceiptStore(tmp_path / 'receipts')
    body = (tmp_path / 'report.pdf').read_bytes()
    with factory() as db:
        capture_retained_pdf(db, context, store, domain='pending_bills', url=url, body=body)
        with factory.begin() as other:
            ext = other.get(Extraction, origin)
            raw = deepcopy(ext.extracted_json)
            raw['response_receipt'][field] = value
            ext.extracted_json = raw
        with pytest.raises(ValueError):
            capture_retained_pdf(db, context, store, domain='pending_bills', url=url, body=body)
    no_publication(factory)


@pytest.mark.parametrize('field', ['status', 'publisher', 'country', 'country_iso', 'job'])
def test_writer_rechecks_current_source_and_job_after_lock(pg, tmp_path, monkeypatch, field):
    from services.response_receipts import capture_retained_pdf
    from seeding.native_report_authority import capture_pdf_report, persist_native_report
    from test_native_publisher_metadata import acquisition, TITLE, PAGE
    factory, _ = pg
    enable(factory, monkeypatch)
    sid, _, url, context = retained_context(factory, tmp_path, 'national_budget')
    path = tmp_path / 'report.pdf'
    store = LocalReceiptStore(tmp_path / 'receipts')
    class Abort(Exception): pass
    with pytest.raises(Abort):
        with factory.begin() as db:
            source = db.get(SourceDocument, sid)
            # Hold the same ORM state that a producer holds before it locks.
            country = db.get(Country, source.country_id)
            job = db.get(IngestionJob, context.job_id)
            receipt = capture_retained_pdf(db, context, store, domain='national_budget', url=url, body=path.read_bytes())
            post = acquisition(tmp_path, listing(TITLE, PAGE, 16454), PAGE, 'text/html')
            authority, reason = capture_pdf_report(path, receipt, domain='national_budget', publisher_receipt=post)
            assert authority is not None, reason
            with factory.begin() as other:
                current = other.get(SourceDocument, sid)
                if field == 'status': current.status = DocumentStatus.ARCHIVED
                elif field == 'publisher': current.publisher = 'Changed publisher'
                elif field == 'country_iso': other.get(Country, country.id).iso_code = 'ZZZ'
                elif field == 'job': other.get(IngestionJob, job.id).status = IngestionStatus.FAILED
                else:
                    foreign = Country(iso_code='ZZZ', name='Owned foreign country', currency='ZZZ', timezone='UTC', default_locale='en')
                    other.add(foreign); other.flush(); current.country_id = foreign.id
            with pytest.raises(ValueError):
                persist_native_report(db, source, authority, context=context, domain='national_budget')
            raise Abort()
    no_publication(factory)


@pytest.mark.parametrize('domain', ['pending_bills', 'national_budget'])
def test_retained_origin_keeps_original_time_and_one_provider_read_per_job(pg, tmp_path, monkeypatch, domain):
    from test_native_publisher_postgres import ingest, pending_write
    from seeding.pdf_evidence import receipt_for_pdf
    from seeding.native_report_authority import capture_pdf_report, persist_native_report
    from seeding.native_report_observations import read_native_report_observation
    factory, _ = pg
    enable(factory, monkeypatch)
    old_job, old_record = ingest(factory, tmp_path, domain=domain)
    path = tmp_path / 'report.pdf'
    store = LocalReceiptStore(tmp_path / 'receipts')
    reads = []
    original_read = store.read
    store.read = lambda key: (reads.append(key), original_read(key))[1]
    with factory.begin() as db:
        source = db.scalar(select(SourceDocument))
        original = deepcopy(db.get(Extraction, old_record).extracted_json['response_receipt'])
        job = IngestionJob(domain=domain, status=IngestionStatus.RUNNING, dry_run=False,
            started_at=datetime.now(timezone.utc), errors=[], meta={'source_mode':'live'})
        db.add(job); db.flush(); job_id = job.id
        context = DomainRunContext(None, False, job_id)
        client = SimpleNamespace(receipt_store=store, download_receipt=lambda _: None)
        args = dict(session=db, context=context, domain=domain)
        receipt = receipt_for_pdf(client, None, path, source.url, 'owned-native-parser', **args)
        companion = receipt_for_pdf(client, None, path, source.url, 'owned-aging-parser', **args)
        assert acquisition_is_intact(receipt) and acquisition_is_intact(companion)
        assert len(reads) == 1, 'Companion cohorts must share one real retention read'
        assert receipt['acquired_at'] == original['acquired_at']
        assert receipt['byte_check'] == original['byte_check']
        proof = receipt['retained_pdf_validation']
        assert proof['ingestion_id'] == job_id and proof['origin_extraction_id'] == old_record
        assert proof['validated_at'] > receipt['acquired_at']
        from test_native_publisher_metadata import acquisition, TITLE, PAGE
        page = COUNTY_PAGE if domain == 'pending_bills' else PAGE
        post = acquisition(tmp_path, listing(COUNTY_TITLE, COUNTY_PAGE, 16482) if domain == 'pending_bills' else listing(TITLE, PAGE, 16454), page, 'text/html')
        authority, reason = capture_pdf_report(path, receipt, domain=domain, publisher_receipt=post)
        assert authority is not None, reason
        if domain == 'pending_bills': pending_write(db, authority, context)
        else: persist_native_report(db, source, authority, context=context, domain=domain)
        job.status = IngestionStatus.COMPLETED
        job.finished_at = datetime.now(timezone.utc)
    records = read_native_report_record_ids(factory, ingestion_id=job_id, domain=domain)
    assert len(records) == 1 and records != (old_record,)
    observation = read_native_report_observation(factory, record_id=records[0], ingestion_id=job_id, domain=domain)
    assert observation['report']['retrieved_at'] == original['acquired_at']
    assert observation['report']['verified_at'] > original['byte_check']['checked_at']
    no_publication(factory)


@pytest.mark.parametrize('broken', ['missing', 'json_only', 'changed_bytes', 'archived', 'wrong_country',
    'changed_md5', 'missing_retention', 'origin_status', 'origin_digest', 'origin_time', 'origin_size'])
def test_cached_local_bytes_cannot_claim_missing_or_changed_origin(pg, tmp_path, monkeypatch, broken):
    from test_native_publisher_postgres import ingest
    from seeding.pdf_evidence import receipt_for_pdf
    from seeding.native_report_authority import capture_pdf_report
    factory, _ = pg
    enable(factory, monkeypatch)
    _, record = ingest(factory, tmp_path)
    path = tmp_path / 'report.pdf'
    store = LocalReceiptStore(tmp_path / 'receipts')
    with factory.begin() as db:
        source = db.scalar(select(SourceDocument))
        ext = db.get(Extraction, record)
        claimed = deepcopy(ext.extracted_json['response_receipt'])
        if broken in ('missing', 'json_only'): db.delete(ext)
        if broken == 'changed_bytes': path.write_bytes(path.read_bytes() + b' changed')
        if broken == 'archived': source.status = DocumentStatus.ARCHIVED
        if broken == 'wrong_country': db.get(Country, source.country_id).iso_code = 'ZZZ'
        if broken == 'changed_md5': source.md5 = 'b' * 32
        if broken.startswith('origin_'):
            value = deepcopy(ext.extracted_json)
            field = {'origin_status':'status', 'origin_digest':'digest', 'origin_time':'acquired_at', 'origin_size':'byte_size'}[broken]
            value['response_receipt'][field] = {'status':True, 'digest':'b'*64, 'acquired_at':'2099-01-01T00:00:00+00:00', 'byte_size':True}[field]
            ext.extracted_json = value
        job = IngestionJob(domain='pending_bills', status=IngestionStatus.RUNNING, dry_run=False,
            started_at=datetime.now(timezone.utc), errors=[], meta={'source_mode':'live'})
        db.add(job); db.flush()
        if broken == 'missing_retention': store.read = lambda _: b'wrong'
        client = SimpleNamespace(receipt_store=store, download_receipt=lambda _: claimed if broken == 'json_only' else None)
        receipt = receipt_for_pdf(client, None, path, source.url, 'owned-parser',
            session=db, context=DomainRunContext(None, False, job.id), domain='pending_bills')
        authority, _ = capture_pdf_report(path, receipt, domain='pending_bills')
        assert authority is None
        assert 'retained_pdf_validation' not in receipt
    no_publication(factory)
