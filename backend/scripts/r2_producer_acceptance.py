"""Root-operated acceptance packet. Default refuses; no provider work on import.

Live execution requires Linux/Python3.12, literal destinations, exact clean app
HEAD/tree, explicit switches and fixed budgets BEFORE imports/secret/object IO.
Only whitelisted summaries are emitted. Never attach source bodies or a DB.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from copy import deepcopy
import dataclasses
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

ACCOUNT = '6929fa03fad58c2f93c70196ec498c69'
BUCKET = 'audit-source-evidence-v1'
HEAD = '420cdc1887502940db32403fe26c6158789f9bc3'
TREE = '093b3c321197943c0a647f1e763212982ee7cef4'
PDF_SHA = '5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3'
PDF_SIZE = 53561211
ORACLE_SHA = 'cbaa3d98e2aaa96071d90260aff69cd619cf7ffe6794a89f27556cd7b08c33e4'
MEMORY = 8 * 1024**3
TIMEOUT = 720
MARKER = b'audit-app issue137 bounded private-source acceptance marker v1\n'
MARKER_SHA = hashlib.sha256(MARKER).hexdigest()
URL = 'https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN'
PDF_URL = 'https://example.invalid/retained-cbirr-annual.pdf'
SECRET_NAMES = ('RECEIPT_R2_ACCESS_KEY_ID', 'RECEIPT_R2_SECRET_ACCESS_KEY', 'RECEIPT_R2_CONTROL_TOKEN')
SAFE_REFUSALS = frozenset('''arguments_invalid live_not_authorized destination_mismatch
runner_physical_budget
source_or_head_mismatch budget_mismatch publisher_fetch_not_authorized runtime_parity_mismatch
owned_paths_required owned_paths_refused checkout_mismatch checkout_dirty resolved_settings_mismatch
adapter_mismatch public_storage_io marker_readback_mismatch fresh_process_read_failed
fresh_process_receipt_invalid publisher_body_limit publisher_request_refused publisher_repeat_refused
publisher_encoding_refused publisher_deadline publisher_observation_count publisher_receipt_failed economic_persistence_failed
economic_sql_count economic_public_count retained_pdf_mismatch fresh_parse_required pdf_output_count
pdf_retained_qualification complete_pdf_semantics_mismatch budget_persistence_failed budget_sql_count
budget_qualification_inputs budget_publisher_authority_fabricated budget_public_inputs
budget_qualification_count budget_public_refused pilot_receipt_identity pilot_qualification_refused marker_capture_failed producer_budget_exceeded'''.split())


class Refusal(Exception):
    pass


class BudgetExpired(BaseException):
    pass


class Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise Refusal('arguments_invalid')


def arguments(argv):
    parser = Arguments(add_help=False)
    parser.add_argument('--stage', choices=['pilot', 'pdf', 'marker-read'])
    parser.add_argument('--repo')
    parser.add_argument('--output')
    parser.add_argument('--expected-account')
    parser.add_argument('--expected-bucket')
    parser.add_argument('--expected-jurisdiction')
    parser.add_argument('--expected-head')
    parser.add_argument('--expected-source-sha256')
    parser.add_argument('--memory-budget-bytes')
    parser.add_argument('--timeout-seconds')
    parser.add_argument('--allow-live-r2', action='store_true')
    parser.add_argument('--allow-official-worldbank', action='store_true')
    return parser.parse_args(argv)


def guards(args, *, system=None, version=None, git=None):
    # No secret reads, source/object reads, mkdir or package imports precede this.
    if not args.allow_live_r2 or args.stage is None:
        raise Refusal('live_not_authorized')
    if (args.expected_account, args.expected_bucket, args.expected_jurisdiction) != (ACCOUNT, BUCKET, 'default'):
        raise Refusal('destination_mismatch')
    if args.expected_head != HEAD or args.expected_source_sha256 != PDF_SHA:
        raise Refusal('source_or_head_mismatch')
    if args.memory_budget_bytes != str(MEMORY) or args.timeout_seconds != str(TIMEOUT):
        raise Refusal('budget_mismatch')
    if args.stage == 'pilot' and not args.allow_official_worldbank:
        raise Refusal('publisher_fetch_not_authorized')
    if (system or platform.system()) != 'Linux' or (version or sys.version_info[:2]) != (3, 12):
        raise Refusal('runtime_parity_mismatch')
    if not args.repo or not args.output:
        raise Refusal('owned_paths_required')
    if 'round20_private' in args.repo or 'round20_private' in args.output:
        raise Refusal('owned_paths_refused')
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    if 'round20_private' in str(repo) or 'round20_private' in str(output) or output.suffix != '.json':
        raise Refusal('owned_paths_refused')
    def actual_git(command):
        return subprocess.check_output(['git', *command], cwd=repo, stderr=subprocess.DEVNULL, text=True).strip()
    read_git = git or actual_git
    if read_git(['rev-parse', 'HEAD']) != HEAD or read_git(['rev-parse', 'HEAD^{tree}']) != TREE:
        raise Refusal('checkout_mismatch')
    if read_git(['status', '--porcelain', '--untracked-files=no']):
        raise Refusal('checkout_dirty')
    return repo, output


def rss_bytes():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak * 1024 if platform.system() == 'Linux' else peak)


@contextmanager
def budgets():
    # Address-space limit is a hard allocation guard, not a claim that RSS=AS.
    # Linux RSS is separately measured in bytes and checked before PASS.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES') < 15_000_000_000:
        raise Refusal('runner_physical_budget')
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
    def expired(*_):
        raise BudgetExpired()
    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(TIMEOUT)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def configure_environment(repo, work):
    # Overwrite every DB/runtime destination before importing application code.
    os.environ.update(DATABASE_URL='sqlite:///' + str(work / 'inert.sqlite'),
                      SECRET_BACKEND='env', SECRET_KEY='owned-acceptance-dummy-key',
                      AUTO_SEEDER_ENABLED='false', AUTO_WARMUP_ENABLED='false',
                      PYTHON_DOTENV_DISABLED='1', ENVIRONMENT='testing', TESTING='true', REDIS_URL='')
    sys.path.insert(0, str(repo / 'backend'))
    # Pydantic's explicit _env_file=None is used below. Disable any remaining
    # dotenv consumers, including imports from the application database module.
    import dotenv
    dotenv.load_dotenv = lambda *a, **kw: False
    from pydantic_settings.sources import DotEnvSettingsSource
    DotEnvSettingsSource.__call__ = lambda self: {}
    logging.disable(logging.CRITICAL)


def settings_for(work):
    from seeding.config import SeedingSettings
    value = SeedingSettings(_env_file=None, receipt_storage_backend='r2',
        receipt_r2_account_id=ACCOUNT, receipt_r2_bucket=BUCKET,
        receipt_r2_jurisdiction='default', receipt_max_bytes=64*1024**2,
        receipt_part_max_bytes=32*1024**2, receipt_storage_timeout_seconds=120,
        parse_cache_enabled=False, http_cache_enabled=False, max_retries=1,
        http_follow_redirects=False, timeout_seconds=30,
        cache_path=work/'cache', storage_path=work/'storage', rate_limit='60/min')
    resolved = (value.receipt_storage_backend, value.receipt_r2_account_id,
                value.receipt_r2_bucket, value.receipt_r2_jurisdiction,
                value.receipt_max_bytes, value.receipt_part_max_bytes,
                value.receipt_storage_timeout_seconds, value.parse_cache_enabled,
                value.http_cache_enabled, value.max_retries, value.http_follow_redirects)
    if resolved != ('r2', ACCOUNT, BUCKET, 'default', 67108864, 33554432, 120, False, False, 1, False):
        raise Refusal('resolved_settings_mismatch')
    return value


def counted_store(settings, *, transport=None, offline=False):
    from services.receipt_store import configured_receipt_store
    from services.r2_receipt_store import R2ReceiptStore
    if offline:
        from config import secrets
        with patch.object(secrets, 'get_secret', return_value='SyntheticOnlyCredentials1234567890'):
            store = configured_receipt_store(settings)
    else:
        store = configured_receipt_store(settings)  # Root/job only; no fallback.
    if type(store) is not R2ReceiptStore or store.storage_scope != 'r2_private':
        raise Refusal('adapter_mismatch')
    if transport is not None:
        store._transport = transport
    counts = {'control_get': 0, 'manifest_get': 0, 'part_get': 0,
              'manifest_put': 0, 'part_put': 0, 'uploaded_bytes': 0,
              'downloaded_object_bytes': 0}
    actual = store._request
    def measured(method, path, **kw):
        if kw.get('control'):
            counts['control_get'] += 1
        else:
            kind = 'manifest' if '/manifests/' in path else 'part'
            counts[kind + '_' + method.lower()] += 1
            if method == 'PUT': counts['uploaded_bytes'] += len(kw['body'])
        result = actual(method, path, **kw)
        if not kw.get('control') and method == 'GET':
            counts['downloaded_object_bytes'] += len(result[1])
        return result
    store._request = measured
    return store, counts


def sqlite_session(work):
    from sqlalchemy import create_engine, event, Text
    from sqlalchemy.orm import Session
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles
    @compiles(JSONB, 'sqlite')
    def sqlite_json(element, compiler, **kw):
        return 'TEXT'
    from models import Base, Country
    engine = create_engine('sqlite:///' + str(work/'acceptance.sqlite'))
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _record):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(Country(iso_code='KEN', name='Kenya', currency='KES',
                        timezone='Africa/Nairobi', default_locale='en-KE'))
    session.flush()
    return session


def canonical(value):
    from seeding.parse_cache import _encode
    return json.dumps(_encode(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def compare_pdf_output(captured):
    # A comparison projection cannot add authority to runtime receipts.
    projected = deepcopy(captured)
    for row in projected['converted_records']:
        for e in row.get('source_evidence',[]):
            receipt = e['_response_receipt']
            receipt['storage_scope'] = 'local'
            receipt['byte_check']['checked_at'] = '2026-10-07T00:00:00+00:00'
    if digest(projected) != ORACLE_SHA:
        raise Refusal('complete_pdf_semantics_mismatch')


def public_zero_io(counts, action):
    before = dict(counts)
    result = action()
    if counts != before:
        raise Refusal('public_storage_io')
    return result


def marker_read(store, counts):
    if store.read(MARKER_SHA) != MARKER:
        raise Refusal('marker_readback_mismatch')
    return {'marker_sha256': MARKER_SHA, 'marker_bytes': len(MARKER), 'r2_authenticated_read': True}


def fresh_marker_child(args):
    command = [sys.executable, str(Path(__file__).resolve()), '--stage', 'marker-read',
        '--repo', args.repo, '--output', str(Path(args.output).with_name('marker-child.json')),
        '--expected-account', ACCOUNT, '--expected-bucket', BUCKET,
        '--expected-jurisdiction', 'default', '--expected-head', HEAD,
        '--expected-source-sha256', PDF_SHA, '--memory-budget-bytes', str(MEMORY),
        '--timeout-seconds', str(TIMEOUT), '--allow-live-r2']
    keep = ('PATH', 'VIRTUAL_ENV', 'PYTHONPATH', *SECRET_NAMES)
    env = {key: os.environ[key] for key in keep if key in os.environ}
    result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            timeout=150, text=True)
    if result.returncode != 0:
        raise Refusal('fresh_process_read_failed')
    try:
        report = json.loads(result.stdout)
    except ValueError:
        raise Refusal('fresh_process_receipt_invalid') from None
    if report.get('status') != 'PASS' or report.get('marker_sha256') != MARKER_SHA:
        raise Refusal('fresh_process_receipt_invalid')
    if rss_bytes()+report['peak_rss_bytes'] > MEMORY:
        raise Refusal('producer_budget_exceeded')
    return {'fresh_os_read_passed': True, 'fresh_os_read_peak_bytes': report['peak_rss_bytes'],
            'parent_plus_child_peak_upper_bound_bytes':rss_bytes()+report['peak_rss_bytes']}


def worldbank_pilot(settings, store, counts, work, *, transport=None):
    import httpx
    from seeding.http_client import SeedingHttpClient
    from seeding.domains.economic_indicators import fetcher
    from seeding.domains.economic_indicators.parser import parse_economic_payload
    from seeding.domains.economic_indicators.writer import persist_economic_records
    from seeding.types import DomainRunContext
    from models import EconomicIndicator, Extraction
    from routers.economic import get_economic_indicators

    class BoundedStream(httpx.SyncByteStream):
        def __init__(self, stream, deadline): self.stream, self.deadline = stream, deadline
        def __iter__(self):
            total = 0
            for chunk in self.stream:
                if time.monotonic() >= self.deadline: raise Refusal('publisher_deadline')
                total += len(chunk)
                if total > 1024*1024: raise Refusal('publisher_body_limit')
                yield chunk
            if time.monotonic() >= self.deadline: raise Refusal('publisher_deadline')
        def close(self): self.stream.close()
    class OnePublisher(httpx.BaseTransport):
        def __init__(self): self.inner = transport or httpx.HTTPTransport(retries=0,trust_env=False); self.requests = 0
        def handle_request(self, request):
            if str(request.url.copy_with(query=None)) != URL or request.method != 'GET' or dict(request.url.params) != {'format':'json','per_page':'20','date':'2015:2026'}:
                raise Refusal('publisher_request_refused')
            self.requests += 1
            if self.requests != 1: raise Refusal('publisher_repeat_refused')
            request.headers['accept-encoding'] = 'identity'
            deadline = time.monotonic()+30
            response = self.inner.handle_request(request)
            if response.headers.get('content-encoding','identity').lower() != 'identity':
                response.close()
                raise Refusal('publisher_encoding_refused')
            response.stream = BoundedStream(response.stream,deadline)
            return response
        def close(self): self.inner.close()
    boundary = OnePublisher()
    selected = {'NY.GDP.MKTP.CN': fetcher._WB_INDICATORS['NY.GDP.MKTP.CN']}
    with httpx.Client(transport=boundary, timeout=30, trust_env=False, follow_redirects=False) as upstream:
        with SeedingHttpClient(settings, client=upstream, receipt_store=store) as client:
            with patch.object(fetcher, '_WB_INDICATORS', selected):
                payload = fetcher._fetch_wb_indicators(client)
    if not payload or len(payload) > 12:
        raise Refusal('publisher_observation_count')
    # The fetcher can catch failures; require intact actual-acquisition evidence.
    from services.response_receipts import receipt_is_sealed
    evidence = [e for row in payload for e in row.get('source_evidence', [])]
    if not evidence or any(not receipt_is_sealed(e.get('_response_receipt')) or
        e['_response_receipt']['storage_scope'] != 'r2_private' or
        e['_response_receipt']['byte_check']['status'] != 'matched' or
        not e['checks']['transport'] for e in evidence):
        raise Refusal('publisher_receipt_failed')
    from datetime import datetime
    from urllib.parse import urlsplit, parse_qs
    first = evidence[0]['_response_receipt']
    identity_fields = ('digest','byte_size','storage_key','status','parser_version','acquired_at')
    if any(tuple(e['_response_receipt'].get(k) for k in identity_fields)!=tuple(first.get(k) for k in identity_fields) for e in evidence):
        raise Refusal('pilot_receipt_identity')
    sha,size,key = first.get('digest'),first.get('byte_size'),first.get('storage_key')
    request = urlsplit(first.get('request_url',''))
    if not isinstance(sha,str) or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha) or key!=sha or type(size) is not int or not 0<size<=1024*1024 or first.get('status')!=200 or first.get('parser_version')!='worldbank-observation-v1' or first.get('source_kind')!='api' or request.scheme!='https' or request.netloc!='api.worldbank.org' or request.path!='/v2/country/KEN/indicator/NY.GDP.MKTP.CN' or parse_qs(request.query)!={'format':['json'],'per_page':['20'],'date':['2015:2026']}:
        raise Refusal('pilot_receipt_identity')
    acquired = datetime.fromisoformat(first['acquired_at'])
    checked = datetime.fromisoformat(first['byte_check']['checked_at'])
    if acquired.tzinfo is None or checked.tzinfo is None or checked<acquired:
        raise Refusal('pilot_receipt_identity')
    json_receipt = {'digest':sha,'byte_size':size,'storage_key':key,'http_status':200,
        'parser_version':'worldbank-observation-v1','source_kind':'api','storage_scope':'r2_private',
        'digest_scope':'response.content','request_url':URL,'request_query':{'format':'json','per_page':'20','date':'2015:2026'},
        'content_type':'application/json','acquired_at':acquired.isoformat(),'byte_checked_at':checked.isoformat(),
        'observations':len(first.get('observations',[])),'publisher_http_authority':True}
    records = parse_economic_payload(payload)
    session = sqlite_session(work)
    stats = persist_economic_records(session, records, settings, DomainRunContext(None, False))
    if stats.errors or stats.created != len(records) or stats.skipped:
        raise Refusal('economic_persistence_failed')
    session.commit()
    rows = session.query(EconomicIndicator).all()
    if len(rows) != len(payload) or session.query(Extraction).count() != 1:
        raise Refusal('economic_sql_count')
    public = public_zero_io(counts, lambda: asyncio.run(get_economic_indicators(
        response=None, indicator_type='total_national_gdp', entity_id=None,
        start_date=None, end_date=None, min_confidence=0, limit=100, db=session)))
    if len(public) != len(rows): raise Refusal('economic_public_count')
    from decimal import Decimal
    from models import SourceDocument
    extraction = session.query(Extraction).one()
    sql_receipt = extraction.extracted_json.get('response_receipt')
    source = session.get(SourceDocument,extraction.source_document_id)
    if extraction.extractor!='http-response-v1' or not isinstance(sql_receipt,dict) or any(sql_receipt.get(k)!=first.get(k) for k in identity_fields) or source is None or source.url!=URL or source.publisher!='World Bank':
        raise Refusal('pilot_qualification_refused')
    by_period = {p['date']:p for p in payload}
    if len(by_period)!=len(payload):raise Refusal('pilot_qualification_refused')
    for row in rows:
        p = by_period.get(row.indicator_date.date().isoformat())
        if p is None or p.get('source_url')!=URL or 'Citation: https://data.worldbank.org/indicator/NY.GDP.MKTP.CN?locations=KE' not in p.get('notes','') or row.meta.get('notes')!=p.get('notes') or row.indicator_type!='total_national_gdp' or row.entity_id is not None or row.unit!='KES_millions' or row.source_document_id!=source.id or Decimal(str(row.value))!=Decimal(str(p['value'])):
            raise Refusal('pilot_qualification_refused')
    by_id = {r.id:r for r in rows}
    for published in public:
        row = by_id.get(published.id)
        if row is None or published.value!=float(row.value) or published.indicator_date!=row.indicator_date.isoformat() or set(published.qualifications)!={'total_national_gdp'}:
            raise Refusal('pilot_qualification_refused')
        q = published.qualifications['total_national_gdp'].model_dump(mode='json')
        expected_identity = {'measure':'total_national_gdp','entity_id':None,'geography':'KEN',
            'period':str(row.indicator_date.year),'unit':row.unit,'basis':'actual','dimensions':{}}
        if q['identity']!=expected_identity or q['status']!='verified' or q['reason']!='retained_source_and_observation_matched' or q['digest']!=sha or q['source_kind']!='api' or not q['value_checked'] or not q['document_bytes_checked'] or q['locator']!=by_period[row.indicator_date.date().isoformat()]['source_evidence'][0]['locator'] or q['source_url']!=URL or q['receipt_id']!=extraction.id or q['source_document_id']!=source.id or q['publisher']!=source.publisher:
            raise Refusal('pilot_qualification_refused')
    report = {'publisher_http_attempts':boundary.requests, 'worldbank_observations': len(payload), 'sqlite_economic_rows':len(rows),
              'sqlite_receipt_extractions':1, 'json_receipt':json_receipt,
              'qualification_fields_checked':len(public),'verified_qualification_fields':len(public),
              'qualification_status_counts':{'verified':len(public)},
              'qualification_reason_counts':{'retained_source_and_observation_matched':len(public)},
              'qualification_source_url':URL,
              'public_rows':len(public), 'public_object_gets':0,
              'normalized_data_sha256': digest([{k:v for k,v in row.items() if k!='source_evidence'} for row in payload])}
    session.close()
    return report


def pdf_producer(settings, store, counts, work):
    from seeding import pdf_parsers, parse_cache
    from seeding.cob_cbirr import CbirrPdf
    from seeding.domains.counties_budget.fetcher import _download_and_parse_county_pdf
    from seeding.domains.counties_budget.parser import parse_budget_payload
    from seeding.domains.counties_budget.writer import persist_budget_records
    from seeding.types import DomainRunContext
    from services.response_receipts import receipt_is_sealed
    from services.figure_qualification import qualify_rows
    from models import Entity, EntityType, Country, BudgetLine, Extraction
    from seeding.utils import canonicalize_slug
    body = store.read(PDF_SHA)
    if len(body) != PDF_SIZE or hashlib.sha256(body).hexdigest() != PDF_SHA:
        raise Refusal('retained_pdf_mismatch')
    pdf = work/'retained-cbirr.pdf'
    pdf.write_bytes(body)
    del body
    captured = {}
    table_pages = []
    from pdfplumber.page import Page
    actual_tables = Page.extract_tables
    def track_page(self,*args,**kw):
        table_pages.append(self.page_number)
        return actual_tables(self,*args,**kw)
    actual_cache = parse_cache.parse_with_cache
    def capture(*args, **kw):
        result = actual_cache(*args, **kw)
        if not isinstance(result, parse_cache.FreshParseRecords):
            raise Refusal('fresh_parse_required')
        parser = kw['parse_fn'].__self__
        captured.update(tables=[dataclasses.asdict(t) for t in parser.tables],
                        parsed_records=result, revenue_coverage=parser.revenue_coverage)
        return result
    client = SimpleNamespace(receipt_store=store)
    with patch('seeding.cob_cbirr.download_cbirr', return_value=CbirrPdf(PDF_URL,pdf,PDF_SHA,None)), \
         patch.object(parse_cache, 'parse_with_cache', capture), \
         patch.object(Page,'extract_tables',track_page):
        converted = _download_and_parse_county_pdf(client, PDF_URL, settings)
    captured['converted_records'] = converted
    if table_pages != list(range(1,936)) or len(captured['tables']) != 1129 or len(converted or []) != 468:
        raise Refusal('pdf_output_count')
    evidence = [e for row in converted for e in row.get('source_evidence',[])]
    if len(evidence) != 378 or any(e['checks']['transport'] or
        e['_response_receipt']['status'] is not None or
        e['_response_receipt']['acquired_at'] is not None or
        e['_response_receipt']['acquisition_kind'] != 'local_cached_bytes' or
        e['_response_receipt']['storage_scope'] != 'r2_private' or
        e['_response_receipt']['byte_check']['status'] != 'matched' or
        not receipt_is_sealed(e['_response_receipt']) for e in evidence):
        raise Refusal('pdf_retained_qualification')
    # Comparison projection ONLY: expected provider and check time differ.
    # Runtime capabilities/receipts are never modified or persisted this way.
    compare_pdf_output(captured)
    del captured
    sql_report = pdf_sqlite_output(settings,counts,work,converted)
    return {'pdf_pages':935,'tables':1129,'records':468,'cell_evidence':378,
            'complete_projection_sha256':ORACLE_SHA,'provider_and_time_projection_only':True,
            'fresh_parse':True,'publisher_http_authority':False,**sql_report}


def expected_budget_qualifications(session, rows):
    """Independent row/identity assembly; evaluate the stored qualification rules.

    This never calls qualify_rows, the wrapper under verification. In particular
    a retained PDF cannot acquire HTTP status from successful R2 object reads.
    """
    from services.figure_qualification import ObservationIdentity, evaluate_qualification
    from models import Extraction
    output = {}
    for row in rows:
        doc, entity, period = row.source_document, row.entity, row.period
        if doc is None or entity is None or period is None:
            raise Refusal('budget_qualification_inputs')
        containers = row.provenance if isinstance(row.provenance,list) else [row.provenance]
        entries = [e for c in containers if isinstance(c,dict)
                   for e in c.get('source_evidence',[])]
        fields = {}
        for measure in ('allocated_amount','actual_spent','committed_amount'):
            identity = ObservationIdentity(measure=measure,entity_id=row.entity_id,
                geography=entity.canonical_name,period=period.label,unit=row.currency,
                basis=getattr(row.basis,'value',row.basis) or 'actual',dimensions={
                    name:getattr(row,name) for name in ('category','subcategory','line_type')})
            matching = [e for e in entries if isinstance(e,dict) and
                        isinstance(e.get('identity'),dict) and e['identity'].get('measure')==measure]
            if len(matching)>1: raise Refusal('budget_qualification_inputs')
            evidence = matching[0] if matching else None
            ref = evidence.get('receipt',{}) if evidence else {}
            extraction = session.get(Extraction,ref['extraction_id']) if type(ref.get('extraction_id')) is int else None
            receipt = extraction.extracted_json.get('response_receipt') if extraction else None
            if extraction and (extraction.extractor!='pdf-receipt-v1' or
                extraction.source_document_id!=row.source_document_id or
                not isinstance(receipt,dict) or receipt.get('digest')!=PDF_SHA or
                receipt.get('status') is not None or receipt.get('acquired_at') is not None or
                receipt.get('acquisition_kind')!='local_cached_bytes' or
                receipt.get('byte_check',{}).get('status')!='matched'):
                raise Refusal('budget_qualification_inputs')
            q = evaluate_qualification(identity,getattr(row,measure),source=doc,
                                       evidence=evidence,receipt=receipt).model_dump(mode='json')
            # R2 byte authority must not become publisher HTTP/value authority.
            if q['status']=='verified' or q['value_checked'] or q['document_bytes_checked']:
                raise Refusal('budget_publisher_authority_fabricated')
            if not q['reason'] or q['identity']!=identity.model_dump(mode='json'):
                raise Refusal('budget_qualification_inputs')
            fields[measure] = q
        output[row.id] = fields
    return output


def expected_county_public(rows, qualifications):
    """Pinned-source financial oracle from SQL inputs; no endpoint/summary calls.

    The complete retained oracle supplies one actual period/document. Refuse
    unexpected selector ambiguity rather than accepting an arbitrary summary.
    """
    county = [r for r in rows if r.entity.slug=='nairobi-county']
    if not county or len({r.period_id for r in rows})!=1:
        raise Refusal('budget_public_inputs')
    period = county[0].period
    classified = {}
    for row in county:
        if not row.subcategory and row.category.strip().lower() in ('total','recurrent','development'):
            classified.setdefault(row.category.strip().lower(),[]).append(row)
    selected = classified.get('total',[]) or classified.get('recurrent',[])+classified.get('development',[])
    if not selected or any(len(v)!=1 for v in classified.values()) or len({r.source_document_id for r in selected})!=1 or len({r.currency for r in selected})!=1:
        raise Refusal('budget_public_inputs')
    def amount(field):
        values = [getattr(r,field) for r in selected]
        return sum(float(v) for v in values) if all(v is not None for v in values) else None
    allocation,spent = amount('allocated_amount'),amount('actual_spent')
    rate = spent/allocation*100 if allocation and spent is not None else None
    absent = {}
    if allocation is None: absent['total_allocation']='allocation_not_reported'
    if spent is None: absent['total_spent']='spending_not_reported'
    if rate is None: absent['execution_rate']='spending_not_reported' if spent is None else 'no_positive_allocation'
    doc = selected[0].source_document
    sources = [{'id':doc.id,'title':doc.title,'publisher':doc.publisher,'url':doc.url,
        'page_refs':sorted({str(r.page_ref).strip() for r in selected if r.page_ref and str(r.page_ref).strip()})}]
    fiscal = {'id':period.id,'label':period.label,'start_date':period.start_date.isoformat(),
              'end_date':period.end_date.isoformat()}
    basis = 'reported_total' if classified.get('total') else 'recurrent_plus_development'
    county_q = {r.id:qualifications[r.id] for r in county}
    summary = {'fiscal_period':fiscal,'total_allocation':allocation,'total_spent':spent,
               'execution_rate':rate,'accounting_basis':basis,'currency':selected[0].currency,
               'sources':sources,'absent_reasons':absent,'budget_lines_count':len(selected),
               'figure_qualifications':county_q}
    title = ' '.join((doc.title or '').casefold().split())
    publisher = ' '.join((doc.publisher or '').casefold().split())
    source_code = 'cob_cbirr' if allocation is not None and publisher in (
        'controller of budget','office of the controller of budget') and (
        ('county' in title and 'budget implementation review' in title) or 'cbirr' in title) else None
    cash = {r.subcategory:r for r in county if r.category=='Revenue Receipts'}
    summary_osr = [r for r in county if r.category.strip().lower()=='own source revenue']
    revenue = float(summary_osr[0].actual_spent) if len(summary_osr)==1 and summary_osr[0].actual_spent is not None else None
    if cash and 'Total' in cash:
        values = [r.actual_spent for name,r in cash.items() if name!='Total']
        if all(v is not None and v>=0 for v in values) and cash['Total'].actual_spent is not None and abs(sum(float(v) for v in values)-float(cash['Total'].actual_spent))<=1000:
            own = [cash[n].actual_spent for n in ('Own Source Revenue','Facility Improvement Financing','Appropriations in Aid') if n in cash]
            revenue = sum(float(v) for v in own) if own and all(v is not None for v in own) else None
    return {'county_id':'nairobi-county','county_name':county[0].entity.canonical_name.removesuffix(' County'),
            'figure_qualifications':{'budget_lines':county_q},'financial_summary':summary,
            'fiscal_period':fiscal,'sources':sources,'accounting_basis':basis,'currency':selected[0].currency,
            'absent_reasons':absent,'total_budget':allocation,'budget_2025':allocation,'total_spent':spent,
            'budget_utilization':rate,'budget_execution_rate':rate,'budget_source':source_code,
            'revenue_2024':revenue,'expenditure_breakdown':{},'budget_allocation':{}}


def pdf_sqlite_output(settings, counts, work, converted, *, expected_extractions=1):
    from seeding.domains.counties_budget.parser import parse_budget_payload
    from seeding.domains.counties_budget.writer import persist_budget_records
    from seeding.types import DomainRunContext
    from services.figure_qualification import qualify_rows
    from models import Entity, EntityType, Country, BudgetLine, Extraction
    from seeding.utils import canonicalize_slug
    session = sqlite_session(work)
    country_id = session.query(Country.id).scalar()
    for slug, name in sorted({(canonicalize_slug(r['entity_slug']), r['entity']) for r in converted}):
        session.add(Entity(country_id=country_id,type=EntityType.COUNTY,slug=slug,canonical_name=name))
    session.flush()
    records = parse_budget_payload(converted)
    stats = persist_budget_records(session, records, settings, DomainRunContext(None, False))
    if stats.errors or stats.created != len(records) or stats.skipped or len(records)!=468:
        raise Refusal('budget_persistence_failed')
    session.commit()
    rows = session.query(BudgetLine).all()
    if len(rows)!=468 or session.query(Extraction).count()!=expected_extractions:
        raise Refusal('budget_sql_count')
    qualifications = public_zero_io(counts, lambda: qualify_rows(session,'budget_lines',rows))
    expected_q = expected_budget_qualifications(session,rows)
    if qualifications != expected_q: raise Refusal('budget_qualification_count')
    expected_public = expected_county_public(rows,expected_q)
    # Actual public county endpoint; no lifespan/startup or production session.
    import main as app_main
    @contextmanager
    def held(): yield session
    with patch.object(app_main,'get_db',lambda: iter([held()])), patch.object(app_main,'DATABASE_AVAILABLE',True):
        public = public_zero_io(counts, lambda: asyncio.run(app_main.get_county_budget('nairobi-county')))
    if not isinstance(public,dict) or any(key not in public or public[key]!=value for key,value in expected_public.items()):
        raise Refusal('budget_public_refused')
    session.close()
    return {'sqlite_budget_rows':468, 'sqlite_receipt_extractions':expected_extractions, 'public_object_gets':0,
            'qualification_fields_checked':sum(len(v) for v in expected_q.values()),
            'qualification_sha256':digest(expected_q),'public_contract_sha256':digest(expected_public)}


def run(args, repo, output):
    with budgets(), tempfile.TemporaryDirectory(prefix='r2-producer-owned-') as temporary:
        work = Path(temporary)
        configure_environment(repo, work)
        settings = settings_for(work)
        store, counts = counted_store(settings)
        start = time.monotonic()
        if args.stage == 'marker-read':
            details = marker_read(store,counts)
        elif args.stage == 'pilot':
            key, retained = store.put_and_read(MARKER)
            if key != MARKER_SHA or retained != MARKER: raise Refusal('marker_capture_failed')
            details = fresh_marker_child(args)
            details.update(worldbank_pilot(settings,store,counts,work))
        else:
            details = pdf_producer(settings,store,counts,work)
        peak = rss_bytes()
        if peak > MEMORY or time.monotonic()-start > TIMEOUT:
            raise Refusal('producer_budget_exceeded')
        return {'status':'PASS','scope':'actual Linux producer acceptance; disposable SQLite; no production DB',
            'stage':args.stage,'target_head':HEAD,'target_tree':TREE,'account':ACCOUNT,'bucket':BUCKET,
            'jurisdiction':'default','storage_scope':'r2_private','python':platform.python_version(),
            'system':platform.system(),'versions':{name:importlib.metadata.version(name) for name in
                ['pdfplumber','pdfminer.six','SQLAlchemy','httpx','botocore','pydantic']},
            'physical_memory_bytes':os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES'),
            'parse_cache_enabled':False,'http_cache_enabled':False,
            'publisher_http_attempts':0,'memory_budget_bytes':MEMORY,'peak_rss_bytes':peak,
            'rss_unit':'bytes (Linux ru_maxrss KiB multiplied by1024)',
            'elapsed_seconds':time.monotonic()-start,'r2_traffic':counts,**details}


def main(argv=None):
    output = None
    try:
        args = arguments(sys.argv[1:] if argv is None else argv)
        repo, output = guards(args)
        report = run(args,repo,output)
        exit_code = 0
    except Refusal as exc:
        reason = exc.args[0] if type(exc) is Refusal and len(exc.args)==1 and type(exc.args[0]) is str and exc.args[0] in SAFE_REFUSALS else 'acceptance_refused'
        report, exit_code = {'status':'FAILED','reason':reason}, 1
    except BaseException:
        # Never emit exception text, stack, credentials, provider/source body.
        report, exit_code = {'status':'FAILED','reason':'acceptance_runtime_failed'}, 1
    encoded = json.dumps(report,sort_keys=True)
    if output is not None:
        try:
            output.parent.mkdir(parents=True,exist_ok=True)
            temporary_output = output.with_name(output.name+'.pending')
            temporary_output.write_text(encoded+'\n')
            temporary_output.replace(output)
        except BaseException:
            report,exit_code={'status':'FAILED','reason':'receipt_write_failed'},1
            encoded=json.dumps(report)
    print(encoded)
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
