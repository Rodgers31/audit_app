"""Bounded official release observation, separate from extraction approval.

Only the already reviewed URL/content pair may reach the pinned parser/writer.
An unknown edition, including a structurally compatible reissue, is a review
candidate until its units, labels and discrepancies have edition-specific review.
No raw HTML/workbook is saved to disk. Conditional state is a small native-job
receipt; a 304 reuses only observed links, never certifies financial freshness.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import math
import re
import signal
import threading
import time
from urllib.parse import urljoin, urlsplit

import httpx

from . import parser, source

INDEX = 'https://www.knbs.or.ke/reports/'
MAX_REQUESTS = 6
MAX_BYTES = 2 * 1024 * 1024
MAX_PAGE_BYTES = 256 * 1024
MAX_SECONDS = 45
MAX_PAGES = 2
RECEIPT_VERSION = 'knbs-discovery-v1'
_ACTIVE_DEADLINE = ContextVar('knbs_active_deadline', default=None)
REPORT_PATH = r'/reports/(20[0-9]{2})-economic-survey/'
WORKBOOK_PATH = r'/wp-content/uploads/20[0-9]{2}/(?:0[1-9]|1[0-2])/Chapter-5-Public-Finance(?:-[A-Za-z0-9]+)?\.xlsx'


def official_url(url, kind):
    if type(url) is not str or len(url) > 512 or not url.isascii():
        raise source.OpenDataSourceRefused('KNBS URL shape refused')
    parsed = urlsplit(url)
    path = REPORT_PATH if kind == 'report' else WORKBOOK_PATH if kind == 'workbook' else r'/reports/' if kind == 'index' else None
    if (path is None or parsed.scheme != 'https' or parsed.netloc != 'www.knbs.or.ke'
            or parsed.query or parsed.fragment or re.fullmatch(path, parsed.path) is None):
        raise source.OpenDataSourceRefused('KNBS URL is outside the official discovery contract')
    return url


@contextmanager
def deadline(seconds=MAX_SECONDS):
    # httpx timeouts alone cannot cap a slow trickle or a blocked transport.
    # Direct callers get the same hard budget; a worker-thread bypass refuses.
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= MAX_SECONDS:
        raise source.OpenDataSourceRefused('KNBS deadline budget state refused')
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, 'setitimer'):
        raise source.OpenDataSourceRefused('KNBS discovery requires enforceable main-thread deadline')
    started = time.monotonic()
    active = _ACTIVE_DEADLINE.get()
    if active is not None and active[1] <= started + seconds and signal.getsignal(signal.SIGALRM) is active[2]:
        # Reuse an earlier owned alarm rather than nesting it. Re-arming an
        # already-expired outer alarm inside inner cleanup can interrupt the
        # outer finally and leave the wrong handler installed after refusal.
        if signal.getitimer(signal.ITIMER_REAL)[0] <= 0:
            raise source.OpenDataSourceRefused('KNBS discovery runtime budget exhausted')
        yield active[0]
        return
    old_handler = signal.getsignal(signal.SIGALRM)
    old_timer = signal.getitimer(signal.ITIMER_REAL)
    def expired(*_):
        raise source.OpenDataSourceRefused('KNBS discovery runtime budget exhausted')
    signal.signal(signal.SIGALRM, expired)
    bound = min(seconds, old_timer[0]) if old_timer[0] else seconds
    token = _ACTIVE_DEADLINE.set((started, started + bound, expired))
    signal.setitimer(signal.ITIMER_REAL, bound)
    try:
        yield started
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        _ACTIVE_DEADLINE.reset(token)
        if old_timer[0]:
            signal.setitimer(signal.ITIMER_REAL, max(.000001, old_timer[0] - (time.monotonic() - started)), old_timer[1])


class Links(HTMLParser):
    def __init__(self, base, kind):
        super().__init__(convert_charrefs=True)
        self.base, self.kind, self.links = base, kind, set()
        self.count = 0

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        self.count += 1
        if self.count > 2048:
            raise source.OpenDataSourceRefused('KNBS listing link count exceeded')
        for name, href in attrs:
            if name != 'href' or href is None:
                continue
            url = urljoin(self.base, href)
            path = urlsplit(url).path
            # Ignore ordinary navigation; a source-shaped hostile link refuses.
            relevant = 'economic-survey' in path if self.kind == 'report' else 'Chapter-5-Public-Finance' in path
            if relevant:
                self.links.add(official_url(url, self.kind))
                if len(self.links) > 16:
                    raise source.OpenDataSourceRefused('KNBS source candidate count exceeded')


def page_state(value, url):
    if type(value) is not dict or set(value) != {'url', 'sha256', 'etag', 'last_modified', 'links'} or value['url'] != url:
        raise source.OpenDataSourceRefused('KNBS conditional page receipt shape refused')
    if type(value['sha256']) is not str or re.fullmatch('[0-9a-f]{64}', value['sha256']) is None:
        raise source.OpenDataSourceRefused('KNBS conditional page identity refused')
    for key in ('etag', 'last_modified'):
        v = value[key]
        if v is not None and (type(v) is not str or not v or len(v) > 256 or any(ord(c) < 32 or ord(c) > 126 for c in v)):
            raise source.OpenDataSourceRefused('KNBS conditional validator refused')
    links = value['links']
    if type(links) is not list or not 1 <= len(links) <= 16 or len(set(links)) != len(links):
        raise source.OpenDataSourceRefused('KNBS conditional links refused')
    for link in links:
        official_url(link, 'report' if url == INDEX else 'workbook')
    return value


def prior_pages(value):
    """A retained receipt is distinct from absence; never downgrade corruption."""
    if type(value) is not dict or len(value) != MAX_PAGES or INDEX not in value:
        raise source.OpenDataSourceRefused('KNBS prior pages refused')
    for url, state in value.items():
        official_url(url, 'index' if url == INDEX else 'report')
        page_state(state, url)
    reports = [url for url in value if url != INDEX]
    if len(reports) != 1 or reports[0] not in value[INDEX]['links']:
        raise source.OpenDataSourceRefused('KNBS prior pages association refused')
    return value


class FetchBudget:
    """One non-resettable budget per discovery. No caller-adjustable ceilings."""
    def __init__(self, client, started):
        self.client, self.started = client, started
        self.requests = self.bytes = 0

    def check(self):
        if (type(self.started) not in (int, float) or not math.isfinite(self.started)
                or self.started < 0 or self.started > time.monotonic()
                or type(self.requests) is not int or not 0 <= self.requests <= MAX_REQUESTS
                or type(self.bytes) is not int or not 0 <= self.bytes <= MAX_BYTES):
            raise source.OpenDataSourceRefused('KNBS fetch budget state refused')
        if time.monotonic() - self.started >= MAX_SECONDS:
            raise source.OpenDataSourceRefused('KNBS discovery runtime budget exhausted')

    def fetch(self, url, kind, previous=None):
        self.check()
        # A direct helper call cannot bypass discover()'s whole-call alarm.
        # The original budget origin is retained across every retry and fetch.
        with deadline(MAX_SECONDS - (time.monotonic() - self.started)):
            return self._fetch(url, kind, previous)

    def _fetch(self, url, kind, previous):
        official_url(url, kind)
        headers = {'User-Agent': 'KenyaAuditAppSeeder/1.0', 'Accept-Encoding': 'identity'}
        if previous is not None:
            if kind == 'workbook':
                raise source.OpenDataSourceRefused('KNBS workbook conditional bypass refused')
            page_state(previous, url)
            headers.update({k: previous[v] for k, v in (('If-None-Match', 'etag'), ('If-Modified-Since', 'last_modified')) if previous[v]})
        for attempt in range(2):
            self.check()
            if self.requests >= MAX_REQUESTS:
                raise source.OpenDataSourceRefused('KNBS request budget exhausted')
            self.requests += 1
            try:
                with self.client.stream('GET', url, headers=headers) as response:
                    self.check()
                    if str(response.url) != url:
                        raise source.OpenDataSourceRefused('KNBS transport changed URL')
                    if response.status_code == 304:
                        if previous is None or not any(k.startswith('If-') for k in headers):
                            raise source.OpenDataSourceRefused('KNBS unsolicited no-change response refused')
                        return None, previous
                    if response.status_code in (429, 500, 502, 503, 504):
                        if attempt == 0:
                            self.check()
                            time.sleep(.5)
                            continue
                        raise source.OpenDataSourceRefused('KNBS retry/backoff exhausted')
                    if response.status_code != 200:
                        raise source.OpenDataSourceRefused('KNBS expected 200; redirects are refused')
                    content_type = response.headers.get('content-type', '').split(';', 1)[0].strip().lower()
                    types = (source.CONTENT_TYPE, 'application/octet-stream') if kind == 'workbook' else ('text/html',)
                    if content_type not in types or response.headers.get('content-encoding', 'identity') != 'identity':
                        raise source.OpenDataSourceRefused('KNBS content type/encoding refused')
                    ceiling = source.MAX_BYTES if kind == 'workbook' else MAX_PAGE_BYTES
                    length = response.headers.get('content-length')
                    if length is not None and (not length.isascii() or not length.isdecimal() or int(length) > min(ceiling, MAX_BYTES - self.bytes)):
                        raise source.OpenDataSourceRefused('KNBS response byte budget exceeded')
                    data = bytearray()
                    for chunk in response.iter_bytes(chunk_size=65536):
                        self.check()
                        self.bytes += len(chunk)
                        if self.bytes > MAX_BYTES or len(data) + len(chunk) > ceiling:
                            raise source.OpenDataSourceRefused('KNBS response byte budget exceeded')
                        data.extend(chunk)
                    self.check()
                    if not data:
                        raise source.OpenDataSourceRefused('KNBS empty response refused')
                    return bytes(data), response.headers
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt:
                    raise source.OpenDataSourceRefused('KNBS transport retry exhausted') from None
                self.check()
                time.sleep(.5)
        raise source.OpenDataSourceRefused('KNBS retry exhausted')


def _page(budget, url, kind, prior):
    payload, state = budget.fetch(url, kind, prior)
    if payload is None:
        return state
    links = Links(url, 'report' if kind == 'index' else 'workbook')
    try:
        links.feed(payload.decode('utf-8', errors='strict'))
        links.close()
    except UnicodeError:
        raise source.OpenDataSourceRefused('KNBS listing encoding refused') from None
    if not links.links:
        raise source.OpenDataSourceRefused('KNBS listing has no supported source links')
    return page_state({'url': url, 'sha256': sha256(payload).hexdigest(),
        'etag': state.get('etag'), 'last_modified': state.get('last-modified'), 'links': sorted(links.links)}, url)


def discover(settings, previous=None, *, transport=None):
    """Observe latest official report. Return receipt + approved pinned bytes.

    Injected transport is for owned fixtures; it cannot bypass URL, byte,
    request, retry or hard runtime checks. All production ceilings are fixed.
    """
    if settings.opendata_ingestion_enabled is not True or settings.knbs_release_discovery_enabled is not True:
        raise source.OpenDataSourceRefused('KNBS discovery disabled; both explicit opt-ins required')
    prior = {} if previous is None else prior_pages(previous)
    with deadline() as started, httpx.Client(trust_env=False, follow_redirects=False,
            timeout=10, transport=transport) as client:
        budget = FetchBudget(client, started)
        index = _page(budget, INDEX, 'index', prior.get(INDEX))
        report_url = max(index['links'], key=lambda u: int(re.fullmatch(REPORT_PATH, urlsplit(u).path)[1]))
        report = _page(budget, report_url, 'report', prior.get(report_url))
        if len(report['links']) != 1:
            raise source.OpenDataSourceRefused('KNBS workbook identity ambiguous; review required')
        workbook_url = report['links'][0]
        payload, _ = budget.fetch(workbook_url, 'workbook')
        digest = sha256(payload).hexdigest()
        pinned = (report_url == source.REPORT_URL and workbook_url == source.URL
                  and digest == source.SHA256 and len(payload) == source.ARTIFACT_BYTES)
        reason = None if pinned else 'unreviewed_edition_or_url_or_content_identity'
        if pinned:
            # Validate the real accepted contract before declaring extraction eligible.
            parser.parse_publication(payload)
        checked = datetime.now(timezone.utc)
        receipt = {'version': RECEIPT_VERSION, 'checked_at': checked.isoformat(),
            'generated_by': 'seeding/domains/opendata/discovery.py',
            'generator_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
            'parser_sha256': sha256(Path(parser.__file__).read_bytes()).hexdigest(),
            'status': 'pinned_contract_eligible' if pinned else 'quarantined_review_candidate',
            'reason': reason, 'report_url': report_url,
            'report_year_label': re.fullmatch(REPORT_PATH, urlsplit(report_url).path)[1],
            'publication_date': None, 'reference_periods': None if not pinned else '2015/16-2025/26; raw labels in extraction',
            'workbook_url': workbook_url, 'artifact_sha256': digest, 'artifact_bytes': len(payload),
            'public_qualification': 'not_granted', 'pages': {INDEX: index, report_url: report},
            'requests': budget.requests, 'response_bytes': budget.bytes,
            'elapsed_seconds': round(time.monotonic() - started, 6),
            'budgets': {'requests': MAX_REQUESTS, 'response_bytes': MAX_BYTES,
                        'runtime_seconds': MAX_SECONDS, 'redirects': 0, 'retries_per_request': 1}}
        return receipt, payload if pinned else None, checked
