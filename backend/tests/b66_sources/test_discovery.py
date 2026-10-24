"""No real publisher traffic: bounded injected HTTPX transports and real parser."""
from hashlib import sha256
from pathlib import Path
import signal
from threading import Thread

import httpx
import pytest

from seeding.config import SeedingSettings
from seeding.domains import opendata
from seeding.domains.opendata import discovery as d, parser, source
from seeding.types import DomainRunContext

PAYLOAD = (Path(__file__).resolve().parents[1] / 'fixtures/opendata/Chapter-5-Public-Finance.xlsx').read_bytes()
SETTINGS = SeedingSettings(_env_file=None, opendata_ingestion_enabled=True, knbs_release_discovery_enabled=True)


def pages(report=source.REPORT_URL, workbook=source.URL, payload=PAYLOAD):
    return {d.INDEX: ('text/html', f'<a href="{report}">Economic Survey</a>'.encode()),
            report: ('text/html', f'<a href="{workbook}">Public Finance</a>'.encode()),
            workbook: (source.CONTENT_TYPE, payload)}


def transport(mapping=None, *, status=None, headers=None, requests=None):
    mapping = pages() if mapping is None else mapping
    def respond(request):
        if requests is not None:
            requests.append(request)
        kind, body = mapping[str(request.url)]
        return httpx.Response(status or 200, headers={'content-type': kind, **(headers or {})}, stream=httpx.ByteStream(body))
    return httpx.MockTransport(respond)


def test_pinned_official_release_is_eligible_and_identity_bound():
    calls = []
    receipt, payload, checked = d.discover(SETTINGS, transport=transport(requests=calls))
    assert receipt['status'] == 'pinned_contract_eligible' and receipt['artifact_sha256'] == source.SHA256
    assert receipt['publication_date'] is None and receipt['report_year_label'] == '2026'
    assert receipt['public_qualification'] == 'not_granted' and payload == PAYLOAD and checked.utcoffset() is not None
    assert len(calls) == receipt['requests'] == 3 and receipt['response_bytes'] < d.MAX_BYTES
    parsed = parser.parse_publication(payload)
    assert (parsed['numeric_cells'], parsed['missing_cells']) == (2125, 83)
    assert any(x['status'] == 'published_discrepancy' for x in parsed['reconciliations'])


def test_conditional_pages_still_check_workbook_identity():
    prior, _, _ = d.discover(SETTINGS, transport=transport(headers={'etag': '"owned-v1"'}))
    calls = []
    def respond(request):
        calls.append(request)
        if str(request.url) != source.URL:
            assert request.headers['if-none-match'] == '"owned-v1"'
            return httpx.Response(304)
        assert 'if-none-match' not in request.headers
        return httpx.Response(200, headers={'content-type': source.CONTENT_TYPE}, content=PAYLOAD + b'changed')
    receipt, payload, _ = d.discover(SETTINGS, prior['pages'], transport=httpx.MockTransport(respond))
    assert payload is None and receipt['status'] == 'quarantined_review_candidate' and len(calls) == 3
    assert receipt['artifact_sha256'] == sha256(PAYLOAD + b'changed').hexdigest()


@pytest.mark.parametrize('mode', ['compatible_reissue', 'same_url_changed_bytes', 'new_url_same_bytes', 'new_edition', 'pdf', 'malformed'])
def test_unknown_editions_are_visible_candidates_without_extraction(mode):
    report, workbook, payload = source.REPORT_URL, source.URL, PAYLOAD
    if mode in ('compatible_reissue', 'same_url_changed_bytes'): payload += b'zip-comment-change'
    if mode == 'new_url_same_bytes': workbook = workbook.replace('.xlsx', '-alias.xlsx')
    if mode == 'new_edition':
        report = report.replace('2026', '2027'); workbook = workbook.replace('/2026/', '/2027/')
    if mode == 'pdf': payload = b'%PDF-1.7 inert unsupported PDF'
    if mode == 'malformed': payload = b'not an archive'
    receipt, accepted, _ = d.discover(SETTINGS, transport=transport(pages(report, workbook, payload)))
    assert accepted is None and receipt['status'] == 'quarantined_review_candidate'
    assert receipt['reason'] == 'unreviewed_edition_or_url_or_content_identity'
    assert receipt['artifact_sha256'] == sha256(payload).hexdigest() and receipt['workbook_url'] == workbook
    assert receipt['reference_periods'] is None and receipt['public_qualification'] == 'not_granted'


@pytest.mark.parametrize('url', ['http://www.knbs.or.ke/reports/', 'https://knbs.or.ke/reports/',
    'https://www.knbs.or.ke.evil.invalid/reports/', 'https://user@www.knbs.or.ke/reports/',
    'https://www.knbs.or.ke:443/reports/', 'https://www.knbs.or.ke/reports/?x=1',
    'https://www.knbs.or.ke/reports/#x', 'file:///tmp/a.xlsx', None, True])
def test_direct_url_boundary(url):
    with pytest.raises(source.OpenDataSourceRefused): d.official_url(url, 'index')


@pytest.mark.parametrize('status', [301,302,307,308,403,404,304])
def test_redirect_status_and_unsolicited_304_refuse(status):
    with pytest.raises(source.OpenDataSourceRefused):
        d.discover(SETTINGS, transport=transport(status=status, headers={'location': 'https://evil.invalid/'}))


@pytest.mark.parametrize('headers', [{'content-length': str(d.MAX_BYTES + 1)}, {'content-length': '-1'},
    {'content-encoding': 'gzip'}, {'content-type': 'application/pdf'}])
def test_headers_refuse_before_consumption(headers):
    with pytest.raises(source.OpenDataSourceRefused): d.discover(SETTINGS, transport=transport(headers=headers))


def test_streamed_overflow_no_content_length():
    mapping = pages(); mapping[d.INDEX] = ('text/html', b'x' * (d.MAX_PAGE_BYTES + 1))
    with pytest.raises(source.OpenDataSourceRefused, match='byte budget'): d.discover(SETTINGS, transport=transport(mapping))


def test_retry_exhaustion_is_bounded(monkeypatch):
    monkeypatch.setattr(d.time, 'sleep', lambda seconds: None)
    calls = []
    with pytest.raises(source.OpenDataSourceRefused, match='retry/backoff exhausted'):
        d.discover(SETTINGS, transport=transport(status=503, requests=calls))
    assert len(calls) == 2


def test_request_bound_includes_retries(monkeypatch):
    monkeypatch.setattr(d.time, 'sleep', lambda seconds: None)
    calls = []
    mapping = pages()
    def respond(request):
        calls.append(request)
        if len(calls) % 2: return httpx.Response(503)
        kind, body = mapping[str(request.url)]
        return httpx.Response(200, headers={'content-type':kind}, content=body)
    receipt, payload, _ = d.discover(SETTINGS, transport=httpx.MockTransport(respond))
    assert receipt['requests'] == 6 and payload == PAYLOAD


def test_runtime_guard_and_timer_restoration(monkeypatch):
    original = signal.getsignal(signal.SIGALRM)
    def respond(request):
        signal.getsignal(signal.SIGALRM)(signal.SIGALRM, None)
        raise AssertionError('unreachable')
    with pytest.raises(source.OpenDataSourceRefused, match='runtime budget'):
        d.discover(SETTINGS, transport=httpx.MockTransport(respond))
    assert signal.getsignal(signal.SIGALRM) == original and signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_worker_thread_direct_call_cannot_bypass_hard_deadline():
    errors = []
    def call():
        try: d.discover(SETTINGS, transport=transport())
        except source.OpenDataSourceRefused as exc: errors.append(str(exc))
    t = Thread(target=call); t.start(); t.join(2)
    assert not t.is_alive() and errors == ['KNBS discovery requires enforceable main-thread deadline']


@pytest.mark.parametrize('value', [None, False, True, 0, 1, [], {'unknown':{}}, {d.INDEX:{}}])
def test_bad_prior_state_cannot_certify_no_change(value):
    if value is None:
        with pytest.raises(source.OpenDataSourceRefused): d.discover(SETTINGS, value, transport=transport(status=304))
    else:
        with pytest.raises((source.OpenDataSourceRefused, TypeError)): d.discover(SETTINGS, value, transport=transport())


@pytest.mark.parametrize('value', ['', 'TRUE', '1', 'yes', 1, None])
def test_malformed_discovery_optin(value):
    with pytest.raises(ValueError): SeedingSettings(_env_file=None, knbs_release_discovery_enabled=value)


@pytest.mark.parametrize('flags', [(False,False),(True,False),(False,True)])
def test_disabled_direct_discovery_has_no_requests(flags):
    calls = []
    settings = SeedingSettings(_env_file=None, opendata_ingestion_enabled=flags[0], knbs_release_discovery_enabled=flags[1])
    with pytest.raises(source.OpenDataSourceRefused, match='disabled'):
        d.discover(settings, transport=transport(requests=calls))
    assert not calls


def test_handler_selects_discovery_only_after_native_ownership(monkeypatch):
    order = []
    monkeypatch.setattr(opendata.writer, 'require_ownership', lambda *a, **k: order.append('owner'))
    monkeypatch.setattr(opendata, 'previous_pages', lambda *a: None)
    monkeypatch.setattr(opendata, 'last_recorded_edition', lambda *a: None)
    original = d.discover
    def local(settings, previous):
        order.append('discover')
        return original(settings, previous, transport=transport())
    monkeypatch.setattr(d, 'discover', local)
    monkeypatch.setattr(source, 'fetch_publication', lambda: pytest.fail('Discovery opt-in ignored'))
    monkeypatch.setattr(opendata.writer, 'persist', lambda *a: {'created': 0, 'unchanged': 1})
    result = opendata.run(None, SETTINGS, DomainRunContext(None, False, job_id=1))
    assert order == ['owner','discover','owner'] and result.metadata['release_discovery']['status'] == 'pinned_contract_eligible'
    assert result.metadata['unchanged'] == 1


@pytest.mark.parametrize('started', [float('nan'), float('inf'), float('-inf'), True, -1, 10**20])
def test_direct_fetch_budget_refuses_invalid_runtime_origin(started):
    with httpx.Client(transport=transport()) as client:
        with pytest.raises(source.OpenDataSourceRefused, match='budget state'):
            d.FetchBudget(client, started).fetch(d.INDEX,'index')


def test_direct_fetch_installs_hard_remaining_deadline():
    import time
    def respond(request):
        handler = signal.getsignal(signal.SIGALRM)
        assert callable(handler), 'Direct helper has no enforceable whole-run alarm'
        handler(signal.SIGALRM, None)
        raise AssertionError('unreachable')
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(source.OpenDataSourceRefused, match='runtime budget'):
            d.FetchBudget(client, time.monotonic()).fetch(d.INDEX,'index')


def test_real_shorter_outer_alarm_is_restored_after_blocked_transport():
    import time
    original_handler = signal.getsignal(signal.SIGALRM)
    original_timer = signal.getitimer(signal.ITIMER_REAL)
    assert original_timer == (0.0,0.0)
    restored = []
    def outer(*_): restored.append('outer')
    def blocked(request):
        time.sleep(.6)
        raise AssertionError('Whole-call runtime alarm did not interrupt transport')
    signal.signal(signal.SIGALRM,outer)
    signal.setitimer(signal.ITIMER_REAL,.06)
    start = time.monotonic()
    try:
        with pytest.raises(source.OpenDataSourceRefused,match='runtime budget'):
            d.discover(SETTINGS,transport=httpx.MockTransport(blocked))
        assert time.monotonic()-start < .3
        assert signal.getsignal(signal.SIGALRM) is outer
        time.sleep(.01)
        assert restored == ['outer']
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,original_handler)


@pytest.mark.parametrize('field,value', [('requests',True),('requests',float('nan')),('requests',-1),('requests',7),
                                       ('bytes',True),('bytes',float('inf')),('bytes',-1),('bytes',d.MAX_BYTES+1)])
def test_direct_fetch_rejects_poisoned_counters(field,value):
    import time
    with httpx.Client(transport=transport()) as client:
        budget = d.FetchBudget(client,time.monotonic())
        setattr(budget,field,value)
        with pytest.raises(source.OpenDataSourceRefused,match='budget state'):
            budget.fetch(d.INDEX,'index')


def test_direct_fetch_request_and_cumulative_byte_bounds():
    import time
    calls = []
    mapping = pages(); mapping[source.URL] = (source.CONTENT_TYPE,b'x'*source.MAX_BYTES)
    with httpx.Client(transport=transport(mapping,requests=calls)) as client:
        budget = d.FetchBudget(client,time.monotonic())
        budget.fetch(source.URL,'workbook'); budget.fetch(source.URL,'workbook')
        with pytest.raises(source.OpenDataSourceRefused,match='byte budget'):
            budget.fetch(source.URL,'workbook')
    with httpx.Client(transport=transport(requests=calls)) as client:
        budget = d.FetchBudget(client,time.monotonic()); budget.requests = d.MAX_REQUESTS
        before = len(calls)
        with pytest.raises(source.OpenDataSourceRefused,match='request budget'):
            budget.fetch(d.INDEX,'index')
        assert len(calls) == before


@pytest.mark.parametrize('pages', [None, {}, [], True, {d.INDEX:None}])
def test_malformed_retained_pages_refuse_before_transport(monkeypatch,pages):
    from types import SimpleNamespace
    class Session:
        def scalars(self,query):
            return SimpleNamespace(all=lambda:[{'release_discovery':{'version':d.RECEIPT_VERSION,'pages':pages}}])
    monkeypatch.setattr(opendata.writer,'require_ownership',lambda *a,**k:None)
    monkeypatch.setattr(d,'discover',lambda *a:pytest.fail('Malformed retained state reached transport'))
    with pytest.raises(source.OpenDataSourceRefused,match='prior pages'):
        opendata.run(Session(),SETTINGS,DomainRunContext(None,False,job_id=1))


@pytest.mark.parametrize('receipt', [None,False,0,[],{}])
def test_present_malformed_receipt_is_not_legacy_absence(monkeypatch,receipt):
    from types import SimpleNamespace
    class Session:
        def scalars(self,query):
            return SimpleNamespace(all=lambda:[{'release_discovery':receipt}])
    monkeypatch.setattr(opendata.writer,'require_ownership',lambda *a,**k:None)
    monkeypatch.setattr(d,'discover',lambda *a:pytest.fail('Corrupt receipt silently became absence'))
    with pytest.raises(source.OpenDataSourceRefused,match='receipt version'):
        opendata.run(Session(),SETTINGS,DomainRunContext(None,False,job_id=1))
