"""Offline OAG volume producer → current authority → read-only preview/digest.

Only discovery, transport and finding extraction use owned ports. Native source
capture, persistence, current readers and restricted SQL are production code.
All operational switches stay off; no detector/queue/provider is activated.
"""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import xml.etree.ElementTree as ET

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm.attributes import flag_modified

from models import Extraction, IngestionJob
from seeding import oag_discovery
import seeding.domains.audits as producer
from seeding.native_report_observations import read_native_report_record_ids, read_native_report_observation
from seeding.source_observations import SourceObservationUnavailable
from services.response_receipts import capture_response
from social.generation.contracts import SourceObservation
from social.generation.models import GenerationControls, SourceCursor, SourceEvent
from social.generation.preview import preview
from social.generation.service import DETECTOR_VERSION, semantic_fingerprint, report_release_state
from social.generation.service import consume_observation
from social.generation.social_copy import render_social
from social.generation.worker_authority import capture_worker_authority, verify_worker_authority
from social.models import SocialPost, SocialPostRevision, SocialMediaAsset
from social.media.models import SocialMediaUpload
from social.service import SocialError, SocialService
from native_worker_fixture import restricted
from test_audit_report_editions import install, run_cli
from test_b83_generation_postgres import pg, no_publication
from test_oag_combined_catalogue import input_pair, FIXTURES, FEED


def install_volume(monkeypatch, tmp_path, *, unavailable=False, retained=False,
                   kinds=('executives', 'assemblies'), edition='2023-24'):
    assert edition in ('2022-23', '2023-24')
    year = '2022-2023' if edition == '2022-23' else '2023-2024'
    feed_body = (FIXTURES / ('county-audit-catalogue-' + edition + '.xml')).read_bytes()
    documents = {}
    for kind in kinds:
        (tmp_path / kind).mkdir(parents=True, exist_ok=True)
        cover = ("REPORT OF THE AUDITOR-GENERAL ON THE COUNTY GOVERNMENTS FOR THE YEAR 2022/2023 "
                 + f"VOLUME {1 if kind == 'executives' else 2} - COUNTY {kind.upper()}") if edition == '2022-23' else None
        path, _, _ = input_pair(tmp_path / kind, kind=kind, cover=cover)
        item = next(i for i in ET.fromstring(feed_body).findall('channel/item') if kind.upper() in i.findtext('link'))
        link = item.findtext('link').split('#')[0]
        documents[link if link.startswith('https://') else 'https://www.oagkenya.go.ke' + link] = path.read_bytes()
    current_urls = list(documents)
    feeds = {}
    for fixture in ('2022-23', '2023-24'):
        feed_year = '2022-2023' if fixture == '2022-23' else '2023-2024'
        address = FEED.replace('2023-2024', feed_year)
        feeds[address] = (FIXTURES / ('county-audit-catalogue-' + fixture + '.xml')).read_bytes()
        # Real discovery also retains previously registered older volumes.
        # The owned transport must serve those existing fixture files too.
        for item in ET.fromstring(feeds[address]).findall('channel/item'):
            link = item.findtext('link').split('#')[0]
            url = link if link.startswith('https://') else 'https://www.oagkenya.go.ke' + link
            prior = tmp_path / (hashlib.sha256(url.encode()).hexdigest() + '.pdf')
            if prior.exists() and url not in documents: documents[url] = prior.read_bytes()
    # Reuse the inert finding/discovery ports. Exercise the volume lane below,
    # including its real fetch_document and native authority calls.
    install(monkeypatch, tmp_path, documents, already=retained)
    with producer.create_http_client(None) as client:
        pass
    downloads = []
    def download_feed(url, path, **limits):
        assert url in feeds and limits == dict(max_seconds=20, max_bytes=512*1024)
        downloads.append(url)
        if unavailable:
            raise TimeoutError('Owned unavailable publisher')
        body = feeds[url]
        path.write_bytes(body)
        client.receipts[url] = capture_response(httpx.Response(200, content=body,
            headers={'content-type': 'application/rss+xml'}, request=httpx.Request('GET', url)),
            client.receipt_store, source_kind='rss')
    client.download_to_file = download_feed
    if retained:
        def cached(owner, url, **kwargs):
            path = tmp_path / (hashlib.sha256(url.encode()).hexdigest() + '.pdf')
            assert path.read_bytes() == documents[url]
            return path
        monkeypatch.setattr('seeding.fetch_documents.get_or_download_pdf', cached)
    fiscal_year = year.replace('-', '/')
    volumes = [oag_discovery.OagDocument(url=url, fiscal_year=fiscal_year, kind=kind,
        found_on='year_page', listed_at=f'https://www.oagkenya.go.ke/{year}-county-government-audit-reports/')
        for url, kind in zip(current_urls, kinds)]
    monkeypatch.setattr(oag_discovery, 'discover_county_audit_documents', lambda *a, **kw:
        oag_discovery.CountyAuditDiscovery(listing_fiscal_years=[fiscal_year], documents=volumes))
    def parser(db, doc, settings):
        ext = Extraction(source_document_id=doc.id, page_number=1, extractor='oag_county_volume',
            confidence=.9, extracted_json={'schema': 'owned_inert_findings'})
        db.add(ext); db.flush()
        return dict(created=0 if retained else 1, skipped=1 if retained else 0,
            reason='already_extracted' if retained else 'owned_new', fresh_extraction_ids=[ext.id])
    monkeypatch.setattr('seeding.extractors.get_parser', lambda parser_id: parser)
    return downloads


def configured_off(factory, monkeypatch):
    for key in ('SOCIAL_GENERATION_HOOK_ENABLED', 'SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED',
                'SOCIAL_MEDIA_ENABLED', 'SOCIAL_NATIVE_ENABLED', 'SOCIAL_WORKER_SUPERVISOR_ENABLED'):
        monkeypatch.setenv(key, 'false')
    with factory.begin() as db:
        db.add(GenerationControls(id=1, drafts_enabled=False, shadow_enabled=False,
                                  source_allowlist=[], targets=[]))


def ingest(factory, monkeypatch, tmp_path, **kwargs):
    downloads = install_volume(monkeypatch, tmp_path, **kwargs)
    code, job, metadata, status, errors = run_cli(factory, monkeypatch, tmp_path)
    assert code == 0 and not errors, (metadata, errors)
    return job, metadata, downloads


def read(factory, job):
    ids = read_native_report_record_ids(factory, ingestion_id=job, domain='audits')
    return [SourceObservation.model_validate(read_native_report_observation(factory,
        record_id=record, ingestion_id=job, domain='audits')) for record in ids]


def off_and_empty(factory):
    with factory() as db:
        cfg = db.get(GenerationControls, 1)
        assert not cfg.drafts_enabled and not cfg.shadow_enabled
        for model in (SocialPost, SocialMediaAsset, SocialMediaUpload, SourceEvent):
            assert db.scalar(select(func.count()).select_from(model)) == 0
    no_publication(factory)


def test_volume_producer_current_reader_caption_and_preview_stay_off(pg, monkeypatch, tmp_path):
    factory, _ = pg; configured_off(factory, monkeypatch)
    job, metadata, downloads = ingest(factory, monkeypatch, tmp_path)
    values = read(factory, job)
    assert len(values) == 2 and downloads == [FEED]
    assert {v.report.institution for v in values} == {'executives', 'assemblies'}
    for value in values:
        assert value.report.published_on is None and str(value.report.catalogued_on) == '2025-02-21'
        copy = render_social(value, version='catalogue-availability-v4')
        assert 'Human review is required' in copy and 'AuditGava' in copy
        assert value.report.canonical_url == 'https://www.auditgava.com/audits'
    result = preview(factory, dict(domain='audits', record_ids=[v.report.source_record_id for v in values],
        ingestion_id=job, reports=True, backfill=False))
    assert result['drafts_enabled'] is False
    assert [r['status'] for r in result['results']] == ['baseline', 'baseline']
    with factory() as db: assert db.scalar(select(func.count()).select_from(SourceCursor)) == 0
    off_and_empty(factory)


def test_retained_pdf_replay_rechecks_catalogue_without_new_release(pg, monkeypatch, tmp_path):
    factory, _ = pg; configured_off(factory, monkeypatch)
    job, _, _ = ingest(factory, monkeypatch, tmp_path)
    before = read(factory, job)
    with factory.begin() as db:
        for value in before:
            db.add(SourceCursor(source_type=value.source_type, source_key=value.source_key,
                detector_version=DETECTOR_VERSION, evidence_version=value.evidence_version,
                sequence=0, fingerprint=semantic_fingerprint(value), report_state=report_release_state(value)))
    newer, metadata, downloads = ingest(factory, monkeypatch, tmp_path, retained=True)
    after = read(factory, newer)
    assert len(after) == 2 and downloads == [FEED]
    assert {semantic_fingerprint(v) for v in before} == {semantic_fingerprint(v) for v in after}
    with factory() as db:
        for value in after:
            receipt = db.get(Extraction, value.report.source_record_id).extracted_json['response_receipt']
            assert receipt['retained_pdf_validation']['ingestion_id'] == newer
            old = next(v for v in before if v.source_key == value.source_key)
            assert value.report.retrieved_at == old.report.retrieved_at
    result = preview(factory, dict(domain='audits', record_ids=[v.report.source_record_id for v in after],
        ingestion_id=newer, reports=True, backfill=False))
    assert result['drafts_enabled'] is False and all(r['status'] == 'unchanged' for r in result['results'])
    off_and_empty(factory)


def test_unavailable_shared_catalogue_is_attempted_once_and_retires_prior_authority(pg, monkeypatch, tmp_path):
    factory, _ = pg; configured_off(factory, monkeypatch)
    job, _, _ = ingest(factory, monkeypatch, tmp_path)
    before = read(factory, job)
    newer, metadata, downloads = ingest(factory, monkeypatch, tmp_path, unavailable=True)
    assert downloads == [FEED]
    assert metadata['oag_report_catalogues']['FY 2023/24']['status'] == 'unavailable'
    with pytest.raises(SourceObservationUnavailable): read(factory, newer)
    for value in before:
        with pytest.raises(SourceObservationUnavailable):
            read_native_report_observation(factory, record_id=value.report.source_record_id,
                ingestion_id=job, domain='audits')
    off_and_empty(factory)


@pytest.mark.parametrize('broken', ['catalogue', 'origin'])
def test_changed_stored_evidence_cannot_requalify(pg, monkeypatch, tmp_path, broken):
    factory, _ = pg; configured_off(factory, monkeypatch)
    job, _, _ = ingest(factory, monkeypatch, tmp_path)
    value = read(factory, job)[0]
    with factory.begin() as db:
        row = db.get(Extraction, value.report.source_record_id)
        data = deepcopy(row.extracted_json)
        if broken == 'catalogue': data['response_receipt']['observations'][0]['catalogue_authority']['catalogued_on'] = '2025-02-22'
        else: data['response_receipt']['digest'] = 'f' * 64
        row.extracted_json = data; flag_modified(row, 'extracted_json')
    with pytest.raises(SourceObservationUnavailable):
        read_native_report_observation(factory, record_id=value.report.source_record_id,
            ingestion_id=job, domain='audits')
    off_and_empty(factory)


def test_restricted_digest_accepts_current_catalogue_and_refuses_changed_job(restricted, monkeypatch, tmp_path):
    factory, _, worker, _ = restricted; configured_off(factory, monkeypatch)
    job, _, _ = ingest(factory, monkeypatch, tmp_path)
    value = read(factory, job)[0].model_dump(mode='json')
    with factory.begin() as db: witness = capture_worker_authority(db, value)
    assert witness is not None
    with worker.begin() as conn: assert verify_worker_authority(conn, value, witness) is None
    for table in ('source_documents', 'extractions', 'ingestion_jobs'):
        with pytest.raises(Exception) as exc:
            with worker.begin() as conn: conn.execute(text('SELECT * FROM ' + table + ' LIMIT 1'))
        assert exc.value.orig.pgcode == '42501'
    with factory.begin() as db:
        row = db.get(IngestionJob, job); row.meta = dict(row.meta, native_report_series={})
        flag_modified(row, 'meta')
    with worker.begin() as conn:
        with pytest.raises(SocialError, match='SOURCE_REVIEW_REQUIRED'):
            verify_worker_authority(conn, value, witness)
    off_and_empty(factory)


def test_new_fiscal_volume_creates_one_review_draft_and_concurrent_replay_creates_none(pg, monkeypatch, tmp_path):
    """Synthetic PDF covers plus genuine RSS shapes, not a claimed publisher revision.

    Only nonfinancial draft admission in this owned fixture is enabled. All
    environment hooks, financial generation, delivery/media/workers stay off.
    """
    factory, _ = pg; configured_off(factory, monkeypatch)
    with factory.begin() as db:
        cfg = db.get(GenerationControls, 1); cfg.drafts_enabled = True; cfg.source_allowlist = ['oag']
    old_job, _, _ = ingest(factory, monkeypatch, tmp_path, edition='2022-23', kinds=('executives',))
    old = read(factory, old_job)[0]
    with factory.begin() as db:
        assert consume_observation(SocialService(db), old)['status'] == 'baseline'
    job, _, _ = ingest(factory, monkeypatch, tmp_path, kinds=('executives',))
    current = read(factory, job)[0]
    assert preview(factory, dict(domain='audits', record_ids=[current.report.source_record_id],
        ingestion_id=job, reports=True, backfill=False))['results'][0]['status'] == 'eligible_change'
    def detect(_):
        with factory.begin() as db: return consume_observation(SocialService(db), current)
    with ThreadPoolExecutor(max_workers=3) as pool: outcomes = list(pool.map(detect, range(3)))
    assert sum(o['status'] == 'draft_created' for o in outcomes) == 1
    assert sum(o['status'] == 'unchanged' for o in outcomes) == 2
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPost)) == 1
        post = db.scalar(select(SocialPost)); revision = db.get(SocialPostRevision, post.current_revision_id)
        assert post.editorial_state == 'pending_review'
        assert 'FY 2023/24' in revision.document['master']['text']
        assert 'publication date is not stated. Human review is required' in revision.document['master']['text']
        assert revision.evidence_snapshot['source']['report']['canonical_url'] == 'https://www.auditgava.com/audits'
    no_publication(factory)
