"""Nightly source acceptance is separate from a successful partial commit."""
from types import SimpleNamespace

import pytest

from seeding import freshness
from tests.test_hollow_run_gate import HEALTHY_NIGHT, _run_step, _write_db
from tests.test_audits_domain_county_ingest import harness, _run, NATIONAL
from tests.test_blue_book_national_walk import national_doc


@pytest.mark.parametrize('domain,mode,status', [
    ('audits', 'live', 'completed_with_errors'),
    ('fiscal_summary', 'partial', 'completed'),
    ('pending_bills', 'partial', 'completed'),
])
def test_required_domain_gap_fails_actual_workflow(tmp_path, domain, mode, status):
    rows = [r for r in HEALTHY_NIGHT if r[0] != domain]
    rows.append((domain, status, 0, 4, 8105, mode, 'source_incomplete'))
    result = _run_step(_write_db(tmp_path, rows))
    out = result.stdout + result.stderr
    assert result.returncode == 1, out
    assert f'[INCOMPLETE] {domain}:' in out


def test_audit_reconciliation_hold_is_partial_even_when_other_pdfs_succeed(harness, monkeypatch):
    from datetime import datetime
    from models import SourceDocument, DocumentType, DocumentStatus
    from seeding.extractors.reconciliation import ReconciliationRequired
    session = harness['session']
    _run(session, budget=10_000)
    session.add(SourceDocument(
        country_id=session.query(SourceDocument).first().country_id,
        publisher='Office of the Auditor-General', title='national.pdf', url=NATIONAL,
        fetch_date=datetime(2026, 5, 1), doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    ))
    session.commit()
    import seeding.extractors as extractors
    original = extractors.get_parser
    def held(*args):
        raise ReconciliationRequired({'document_id': 2392, 'retire_ids': [136],
                                      'update_ids': [39], 'candidate_sha256': 'fixture-only'})
    monkeypatch.setattr(extractors, 'get_parser', lambda pid: held if pid == 'oag_blue_book' else original(pid))
    freshness.reset('audits')
    result = _run(session, budget=10_000)
    assert any('reconciliation review required' in e for e in result.errors)
    assert any(d.get('extractions') for d in result.metadata['documents'])
    assert freshness.get('audits')['mode'] == 'partial'


def test_county_success_does_not_hide_national_pending_fallback(monkeypatch):
    from seeding.domains import pending_bills
    def national(*args):
        freshness.mark_fixture('pending_bills', reason='brop_unavailable')
        return 18, 0, 0
    monkeypatch.setattr(pending_bills, '_seed_national', national)
    monkeypatch.setattr(pending_bills, '_seed_counties', lambda *args: (46, 0, 46))
    freshness.reset('pending_bills')
    result = pending_bills.run(None, None, SimpleNamespace(dry_run=False))
    assert result.items_processed == 64
    assert freshness.get('pending_bills')['mode'] == 'partial'
    assert result.metadata['refresh_components']['national']['reason'] == 'brop_unavailable'
    assert result.metadata['refresh_components']['counties']['records'] == 46


def test_fiscal_parse_failure_cannot_retain_live_verdict(monkeypatch):
    from contextlib import nullcontext
    from seeding.domains import fiscal_summary
    freshness.reset('fiscal_summary')
    def fetch(*args):
        freshness.mark_live('fiscal_summary', detail='fixture transport double')
        return {'fiscal_years': []}
    def refuse(*args):
        raise ValueError('demonstrated parse refusal')
    monkeypatch.setattr(fiscal_summary, 'create_http_client', lambda *args: nullcontext(object()))
    monkeypatch.setattr(fiscal_summary.fetcher, 'fetch_fiscal_summary_payload', fetch)
    monkeypatch.setattr(fiscal_summary.parser, 'parse_fiscal_summary_payload', refuse)
    result = fiscal_summary.run(None, None, SimpleNamespace(dry_run=False))
    assert result.errors == ['Parse failed: demonstrated parse refusal']
    assert freshness.get('fiscal_summary')['mode'] != 'live'


@pytest.mark.parametrize('contradiction', [False, True])
def test_missing_completion_or_stored_document_hold_fails_workflow(tmp_path, contradiction):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from models import IngestionJob
    url = _write_db(tmp_path, HEALTHY_NIGHT)
    engine = create_engine(url)
    with Session(engine) as session:
        job = session.execute(select(IngestionJob).where(IngestionJob.domain == 'audits')).scalar_one()
        meta = dict(job.meta)
        if contradiction:
            meta.update(documents=[{
                'doc_id': 2392, 'extraction_attempt': {'status': 'partial', 'error': 'ReconciliationRequired'},
            }])
        else:
            meta.pop('refresh_completion', None)
        job.meta = meta
        session.commit()
    engine.dispose()
    result = _run_step(url)
    assert result.returncode == 1, result.stdout + result.stderr
    assert '[INCOMPLETE] audits:' in result.stdout


@pytest.mark.parametrize('county', [False, True])
def test_pending_records_skipped_by_real_writer_cannot_certify_component(monkeypatch, county):
    from contextlib import nullcontext
    from seeding.domains import pending_bills as pb
    from services.publication_gate import COUNTY_PENDING_BILLS_PUBLICATION, NATIONAL_PENDING_BILLS_PUBLICATION
    class Session:
        def begin_nested(self):
            return nullcontext()
    def national(*args):
        freshness.mark_live('pending_bills')
        return 2, 0, 2
    def fetch(*args, **kwargs):
        freshness.mark_live('pending_bills')
        return {'pending_bills': [{
            'entity_name': 'Fixture entity', 'entity_type': 'national' if county else 'county',
            'category': 'mda' if county else 'county', 'fiscal_year': 'FY2025/26',
            'total_pending': '10', 'as_at': '2026-06-30', 'table': 'fixture table', 'page': 1,
        }], 'publication': COUNTY_PENDING_BILLS_PUBLICATION if county else NATIONAL_PENDING_BILLS_PUBLICATION}
    monkeypatch.setattr(pb, 'create_http_client', lambda *args: nullcontext(object()))
    monkeypatch.setattr(pb.fetcher, 'fetch_county_payables_payload' if county else 'fetch_pending_bills_payload', fetch)
    if county:
        monkeypatch.setattr(pb, '_seed_national', national)
    else:
        monkeypatch.setattr(pb, '_seed_counties', lambda *args: (46, 0, 46))
    freshness.reset('pending_bills')
    result = pb.run(Session(), None, SimpleNamespace(dry_run=False))
    assert result.metadata['refresh_completion']['complete'] is False
    assert freshness.get('pending_bills')['mode'] != 'live'


@pytest.mark.parametrize('stats', [{}, {'created': 0}, {'created': True}, {'created': 1}],
                         ids=['empty', 'zero', 'boolean', 'missing-evidence'])
def test_national_parser_statistics_need_actual_extraction_evidence(harness, monkeypatch, stats):
    from datetime import datetime
    from models import SourceDocument, DocumentType, DocumentStatus, Extraction
    import seeding.extractors as extractors
    session = harness['session']
    _run(session, budget=10_000)
    session.add(SourceDocument(
        country_id=session.query(SourceDocument).first().country_id,
        publisher='Office of the Auditor-General', title='national.pdf', url=NATIONAL,
        fetch_date=datetime(2026, 5, 1), doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    ))
    session.commit()
    original = extractors.get_parser
    monkeypatch.setattr(extractors, 'get_parser', lambda pid: (lambda *args: dict(stats))
                        if pid == 'oag_blue_book' else original(pid))
    result = _run(session, budget=10_000)
    national = session.query(SourceDocument).filter_by(url=NATIONAL).one()
    assert session.query(Extraction).filter_by(source_document_id=national.id).count() == 0
    assert result.errors
    assert result.metadata['refresh_completion']['complete'] is False


def test_fiscal_malformed_payload_cannot_retain_live_verdict(monkeypatch):
    from contextlib import nullcontext
    from seeding.domains import fiscal_summary as fs
    def fetch(*args):
        freshness.mark_live('fiscal_summary')
        return None
    monkeypatch.setattr(fs, 'create_http_client', lambda *args: nullcontext(object()))
    monkeypatch.setattr(fs.fetcher, 'fetch_fiscal_summary_payload', fetch)
    freshness.reset('fiscal_summary')
    result = fs.run(None, None, SimpleNamespace(dry_run=False))
    assert result.errors
    assert freshness.get('fiscal_summary')['mode'] != 'live'


def test_brop_fallback_cannot_inherit_an_earlier_live_verdict(monkeypatch):
    from seeding.domains.pending_bills import fetcher
    from seeding.config import SeedingSettings
    def unavailable(*args):
        raise RuntimeError('retained transport failure: certificate has expired')
    monkeypatch.setattr(fetcher, '_discover_brop', lambda *args: None)
    monkeypatch.setattr(fetcher, '_fetch_from_treasury_brop', unavailable)
    monkeypatch.setattr('seeding.utils.load_json_resource', lambda **kwargs: {})
    freshness.mark_live('pending_bills', detail='previous invocation')
    fetcher.fetch_pending_bills_payload(object(), SeedingSettings(
        live_pdf_fetch_enabled=True, pending_bills_dataset_url='file:///inert-fixture.json'))
    observed = freshness.get('pending_bills')
    assert observed['mode'] == 'fixture'
    assert 'certificate has expired' in observed['detail']


@pytest.mark.parametrize('change', ['missing', 'null', 'integer', 'string', 'false',
                                  'zero-docs', 'error-count', 'deferred', 'boolean-count',
                                  'nan-count', 'dry-job', 'errors', 'held-doc',
                                  'missing-parser', 'unknown-parser', 'extraction-count'])
def test_completion_consumer_rejects_missing_malformed_and_contradictory_proof(change):
    from seeding.refresh_completion import required_refresh_failures
    job = SimpleNamespace(domain='audits', status='completed', errors=[], dry_run=False,
                          items_processed=813, meta={'source_mode': 'live', 'refresh_completion': {
                              'complete': True, 'accepted_documents': 1, 'errors': 0, 'deferred': False}})
    job.meta['documents'] = [{'doc_id': 2392, 'parser_id': 'oag_blue_book', 'extraction_outcome': 'accepted',
                              'extractions': {'existing': 813},
                              'loaded': {'processed': 813, 'created': 0, 'updated': 0, 'unchanged': 813, 'skipped': 0}}]
    assert required_refresh_failures([job]) == []
    proof = job.meta['refresh_completion']
    if change == 'missing':
        job.meta.pop('refresh_completion')
    elif change in ('null', 'integer', 'string', 'false'):
        proof['complete'] = {'null': None, 'integer': 1, 'string': 'true', 'false': False}[change]
    elif change == 'zero-docs':
        proof['accepted_documents'] = 0
    elif change == 'error-count':
        proof['errors'] = 1
    elif change == 'deferred':
        proof['deferred'] = True
    elif change == 'boolean-count':
        job.items_processed = True
    elif change == 'nan-count':
        job.items_processed = float('nan')
    elif change == 'dry-job':
        job.dry_run = True
    elif change == 'errors':
        job.errors = ['source acquisition failed']
    elif change == 'missing-parser':
        job.meta['documents'][0].pop('parser_id')
    elif change == 'unknown-parser':
        job.meta['documents'][0]['parser_id'] = 'unknown'
    elif change == 'extraction-count':
        job.meta['documents'][0]['extractions']['existing'] = 1
    else:
        job.meta['documents'] = [{'extraction_attempt': {'status': 'partial'}}]
    assert required_refresh_failures([job])


def test_intended_preview_is_distinct_from_live_completion():
    from seeding.refresh_completion import required_refresh_failures
    job = SimpleNamespace(domain='audits', status='completed', errors=[], dry_run=True,
                          items_processed=0, meta={})
    assert required_refresh_failures([job], dry_run=True) == []
    assert required_refresh_failures([job], dry_run=False)


@pytest.mark.parametrize('documents', [None, [], [{}]], ids=['missing', 'empty', 'malformed'])
def test_audit_summary_cannot_replace_document_inventory(documents):
    from seeding.refresh_completion import required_refresh_failures
    meta = {'source_mode': 'live', 'refresh_completion': {
        'complete': True, 'accepted_documents': 1, 'errors': 0, 'deferred': False}}
    if documents is not None:
        meta['documents'] = documents
    job = SimpleNamespace(domain='audits', status='completed', errors=[], dry_run=False,
                          items_processed=1, meta=meta)
    assert required_refresh_failures([job])


@pytest.mark.parametrize('writer_counts,refreshed_year,expected_complete', [
    ((0, 0), 'FY2025/26', False), ((False, False), 'FY2025/26', False),
    ((0, 2), 'FY2025/26', False), ((-1, 2), 'FY2025/26', False),
    (('0', '1'), 'FY2025/26', False), ((0, 1), 'FY2019/20', False),
    ((0, 1), 'FY2025/26', True),
], ids=['zero', 'bools', 'extra', 'negative', 'strings', 'wrong-year', 'complete'])
def test_fiscal_completion_requires_confirmed_writer_inventory(monkeypatch, writer_counts, refreshed_year, expected_complete):
    from contextlib import nullcontext
    from seeding.domains import fiscal_summary as fs
    def fetch(*args):
        freshness.mark_live('fiscal_summary')
        return {'_run_facts': {'refresh_components': {
            'budget': {'state': 'live'},
            'revenue': {'state': 'live', 'refreshed_years': [refreshed_year], 'missing_years': []},
            'framework': {'state': 'live', 'unreadable_editions': {}, 'unconfirmed_years': {}},
        }}}
    monkeypatch.setattr(fs, 'create_http_client', lambda *args: nullcontext(object()))
    monkeypatch.setattr(fs.fetcher, 'fetch_fiscal_summary_payload', fetch)
    monkeypatch.setattr(fs.parser, 'parse_fiscal_summary_payload', lambda *args: [SimpleNamespace(fiscal_year='FY2025/26')])
    monkeypatch.setattr('services.trust_guards.check_fiscal_summary', lambda *args: [])
    monkeypatch.setattr(fs.writer, 'write_fiscal_summary_records', lambda *args: writer_counts)
    result = fs.run(None, None, SimpleNamespace(dry_run=False))
    assert result.metadata['refresh_completion']['complete'] is expected_complete
    assert (freshness.get('fiscal_summary')['mode'] == 'live') is expected_complete


@pytest.mark.parametrize('gap', ['missing-years', 'no-refreshed-years', 'unreadable', 'unconfirmed'])
def test_fiscal_live_labels_cannot_override_explicit_component_gaps(gap):
    from seeding.refresh_completion import required_refresh_failures
    components = {'budget': {'state': 'live'},
                  'revenue': {'state': 'live', 'refreshed_years': ['FY2025/26'], 'missing_years': []},
                  'framework': {'state': 'live', 'unreadable_editions': {}, 'unconfirmed_years': {}}}
    job = SimpleNamespace(domain='fiscal_summary', status='completed', errors=[], dry_run=False,
                          items_processed=1, meta={'source_mode': 'live', 'refresh_components': components,
                                                   'refresh_completion': {'complete': True, 'accepted_records': 1,
                                                                          'accepted_years': ['FY2025/26']}})
    assert required_refresh_failures([job]) == []
    if gap == 'missing-years': components['revenue']['missing_years'] = ['FY2025/26']
    elif gap == 'no-refreshed-years': components['revenue']['refreshed_years'] = []
    elif gap == 'unreadable': components['framework']['unreadable_editions'] = {'official.pdf': 'unreadable'}
    else: components['framework']['unconfirmed_years'] = {'FY2025/26': 'unconfirmed'}
    assert required_refresh_failures([job])


def test_national_outcome_cannot_accept_stale_source_stamp(db_session, national_doc):
    from tests.test_blue_book_national_walk import _published
    from seeding.domains.audits.refresh_outcome import verify_outcome
    from seeding.extractors import oag_blue_book as bb
    from seeding.extractors.reconciliation import IncompleteExtraction
    _published(db_session, national_doc)
    national_doc.meta = {'extracted_md5': '0' * 32, 'extractor_version': bb.EXTRACTOR_VERSION}
    with pytest.raises(IncompleteExtraction):
        verify_outcome(db_session, national_doc, {'created': 0, 'existing': 3, 'skipped_unchanged': True}, 'oag_blue_book')


def test_national_outcome_count_must_match_retained_inventory(db_session, national_doc):
    from tests.test_blue_book_national_walk import _published
    from seeding.domains.audits.refresh_outcome import verify_outcome
    from seeding.extractors import oag_blue_book as bb
    from seeding.extractors.reconciliation import IncompleteExtraction
    _published(db_session, national_doc)
    national_doc.meta = {'extracted_md5': national_doc.md5, 'extractor_version': bb.EXTRACTOR_VERSION}
    with pytest.raises(IncompleteExtraction):
        verify_outcome(db_session, national_doc, {'created': 0, 'existing': 2}, 'oag_blue_book')


@pytest.mark.parametrize('processed', [0, 2, True], ids=['empty', 'mismatch', 'boolean'])
def test_national_only_loader_refusal_keeps_document_diagnostic_and_rows(
    db_session, national_doc, monkeypatch, processed
):
    from contextlib import nullcontext
    from copy import deepcopy
    from models import Audit, Extraction
    from seeding.domains import audits
    from seeding.domains.audits.writer import PersistenceStats
    from seeding.extractors import oag_blue_book as bb
    from seeding.oag_discovery import CountyAuditDiscovery
    from seeding.types import DomainRunContext
    from seeding.config import SeedingSettings
    from tests.test_blue_book_national_walk import _published
    _published(db_session, national_doc)
    national_doc.meta = {'extracted_md5': national_doc.md5, 'extractor_version': bb.EXTRACTOR_VERSION}
    db_session.commit()
    def rows():
        db_session.expire_all()
        return ([(r.id, deepcopy(r.extracted_json)) for r in db_session.query(Extraction).order_by(Extraction.id)],
                [(r.id, r.finding_text, r.source_hash) for r in db_session.query(Audit).order_by(Audit.id)])
    before = rows()
    monkeypatch.setattr(audits, 'create_http_client', lambda *args: nullcontext(object()))
    monkeypatch.setattr(audits.fetcher, '_discover_audit_pdfs_via_wp_api', lambda *args, **kwargs: [])
    monkeypatch.setattr('seeding.oag_discovery.discover_county_audit_documents', lambda *args, **kwargs: CountyAuditDiscovery())
    monkeypatch.setattr('seeding.fetch_documents.fetch_document', lambda *args, **kwargs: national_doc)
    monkeypatch.setattr('seeding.extractors.get_parser', lambda pid: (lambda *args: {
        'created': 0, 'existing': 3, 'skipped_unchanged': True}) if pid == 'oag_blue_book' else None)
    def invalid_loader(session, doc, settings, context, **kwargs):
        victim = session.query(Audit).filter_by(source_document_id=doc.id).order_by(Audit.id).first()
        victim.finding_text = 'INERT WRITE MUST ROLL BACK'
        session.flush()
        return PersistenceStats(processed=processed)
    monkeypatch.setattr('seeding.domains.audits.loader.load_blue_book_extractions', invalid_loader)
    result = audits.run(db_session, SeedingSettings(), DomainRunContext(since=None, dry_run=False))
    db_session.commit()
    assert any(f'audit load incomplete for doc {national_doc.id}' in error for error in result.errors)
    assert not any('NameError' in error or 'free variable' in error for error in result.errors)
    assert result.metadata['refresh_completion']['complete'] is False
    assert rows() == before
