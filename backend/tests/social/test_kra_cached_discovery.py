"""The actual HTTP cache must not discard a live annual-wrapper acquisition."""
from datetime import date, datetime, timezone

import httpx
import pytest
from sqlalchemy import func, select

from models import IngestionJob, IngestionStatus, RevenueBySource
from seeding.config import SeedingSettings
from seeding.domains.revenue_by_source import fetcher, kra_discovery, parser, writer
from seeding.generation_dispatch import dispatch_committed_report_generation
from seeding.http_client import SeedingHttpClient
from seeding.rate_limiter import RateLimiter
from seeding.source_observations import read_native_report_record_ids
from seeding.source_observations import SourceObservationUnavailable
from seeding.storage import SimpleHTTPCache
from seeding.types import DomainRunContext
from social.generation.preview import preview
from social.models import SocialPost
from test_api_admin import key, make_client
from test_b83_generation_postgres import no_publication, pg
from test_b86_native_postgres import enable
from test_kra_catalogue_postgres import CATALOGUE, URL, Publisher, request


def cached_publisher(tmp_path, monkeypatch):
    bodies = Publisher(tmp_path / 'receipts')
    calls = []

    def transport(req):
        url = str(req.url)
        calls.append(url)
        if url == CATALOGUE:
            body = bodies.catalogue
        elif url == URL:
            body = bodies.wrapper
        elif url == 'https://krarevenue2526testingdashboard.bolt.host':
            body = bodies.shell
        elif url.startswith('https://krarevenue2526testingdashboard.bolt.host/assets/'):
            body = bodies.bundle
        else:
            return httpx.Response(404)
        return httpx.Response(200, content=body, headers={'content-type': 'text/html'})

    # Fix the edition calendar, while retaining real discovery, HTTP receipt
    # capture, disk cache, streamed catalogue transfer and dashboard parsing.
    candidates = list(kra_discovery.slug_candidates(date(2026, 10, 27)))
    monkeypatch.setattr(kra_discovery, 'slug_candidates', lambda today: candidates)
    settings = SeedingSettings(kra_revenue_url=URL, http_cache_enabled=True)
    client = SeedingHttpClient(settings, RateLimiter(1000, 1),
        SimpleHTTPCache(tmp_path / 'http-cache'),
        httpx.Client(transport=httpx.MockTransport(transport)),
        receipt_store=bodies.receipt_store)
    return settings, client, calls


def cached_ingest(factory, settings, client):
    with factory.begin() as db:
        job = IngestionJob(domain='revenue_by_source', status=IngestionStatus.RUNNING,
            dry_run=False, started_at=datetime.now(timezone.utc), errors=[],
            meta={'source_mode': 'live'})
        db.add(job)
        db.flush()
        rows, status = fetcher._apply_kra_live([], client, settings)
        assert status.startswith('promoted'), status
        stats = writer.persist_revenue_records(db, parser.parse_revenue_payload(rows),
            settings, DomainRunContext(None, False, job.id))
        assert stats.processed >= 5 and not stats.errors
        job.status = IngestionStatus.COMPLETED
        job.finished_at = datetime.now(timezone.utc)
        job_id = job.id
    return job_id


def test_live_cached_client_commits_catalogue_baseline_backfill_and_no_duplicate(pg, tmp_path, monkeypatch):
    factory, engine = pg
    enable(factory, monkeypatch)
    settings, client, calls = cached_publisher(tmp_path, monkeypatch)
    with client:
        job = cached_ingest(factory, settings, client)
    assert calls.count(URL) == calls.count(CATALOGUE) == 1
    ids = read_native_report_record_ids(factory, ingestion_id=job, domain='revenue_by_source')
    assert len(ids) == 1, 'The fresh wrapper probe must survive discovery with cache enabled'
    assert preview(factory, request(job, ids[0]))['results'][0]['status'] == 'baseline'
    result = dispatch_committed_report_generation(factory, domain='revenue_by_source',
        ingestion_id=job, dry_run=False)
    assert result['baselines'] == 1 and result['drafts_created'] == 0
    api = make_client(engine)
    body = {k: v for k, v in request(job, ids[0], backfill=True,
        reason='Owner reviewed current catalogue availability').items() if k != 'reports'}
    route = '/api/v1/admin/social/generation/detect-reports'
    first = api.post(route, json=body, headers=key())
    assert first.status_code == 200 and first.json()['results'][0]['status'] == 'draft_created'
    again = api.post(route, json=body | {'reason': 'New command, same genuine report'}, headers=key())
    assert again.status_code == 200 and again.json()['results'][0]['status'] == 'unchanged'
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPost)) == 1
    no_publication(factory)


def test_prior_cache_remains_ineligible_without_a_new_live_acquisition(pg, tmp_path, monkeypatch):
    factory, _ = pg
    settings, client, calls = cached_publisher(tmp_path, monkeypatch)
    with client:
        # A persisted response from an earlier acquisition has no current-job
        # receipt. Reusing its bytes must never manufacture fresh authority.
        client.get(URL)
        job = cached_ingest(factory, settings, client)
    assert calls.count(URL) == 1
    with pytest.raises(SourceObservationUnavailable, match='Exact record ingestion lineage unavailable'):
        read_native_report_record_ids(factory, ingestion_id=job, domain='revenue_by_source')
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(RevenueBySource)) >= 5
        assert db.scalar(select(func.count()).select_from(SocialPost)) == 0
    no_publication(factory)


@pytest.mark.parametrize('status,method,url', [
    (400, 'GET', URL), (404, 'GET', URL), (429, 'GET', URL),
    (500, 'GET', URL), (503, 'GET', URL),
    (200, 'GET', 'https://unrelated.invalid/wrapper'), (200, 'POST', URL),
])
def test_supplied_response_cannot_parse_an_http_or_request_context_failure(tmp_path, monkeypatch, status, method, url):
    settings, client, calls = cached_publisher(tmp_path, monkeypatch)
    body = Publisher(tmp_path / 'body').wrapper
    supplied = httpx.Response(status, content=body, headers={'content-type': 'text/html'},
        request=httpx.Request(method, url))
    with client:
        assert fetcher._read_release(client, URL, 'FY 2025/26', response=supplied) is None
    assert calls == [], 'A refused wrapper must not fetch a nested dashboard'


def test_checked_redirect_response_preserves_existing_numeric_behavior(tmp_path, monkeypatch):
    _, client, _ = cached_publisher(tmp_path, monkeypatch)
    body = Publisher(tmp_path / 'body').wrapper
    redirect = httpx.Response(302, request=httpx.Request('GET', URL))
    supplied = httpx.Response(200, content=body, headers={'content-type': 'text/html'},
        request=httpx.Request('GET', URL + '/'), history=[redirect])
    with client:
        result = fetcher._read_release(client, URL, 'FY 2025/26', response=supplied)
    assert result is not None and len(result.heads) >= 5
