"""CoB WPDM publication-post evidence, paired with independently read PDF scope.

The post publication day describes report availability, not PDF creation or the
revision day. Both the original post day and subsequent modification are retained.
No mutable listing, retrieval timestamp or file-size label alone grants authority.
"""
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit, urlunsplit

MAX_METADATA_BYTES = 512 * 1024
PAIR_SECONDS = 900


def publisher_page_url(pdf_url):
    parsed = urlsplit(pdf_url)
    query = parse_qs(parsed.query, strict_parsing=True)
    if (parsed.scheme != 'https' or parsed.netloc not in ('cob.go.ke', 'www.cob.go.ke')
            or parsed.fragment or not re.fullmatch(r'/download/[a-z0-9-]+/', parsed.path)
            or set(query) != {'wpdmdl'} or len(query['wpdmdl']) != 1
            or not re.fullmatch(r'[1-9][0-9]{0,8}', query['wpdmdl'][0])):
        raise ValueError('Exact CoB download post required')
    return urlunsplit(parsed._replace(query='')), query['wpdmdl'][0]


def fetch_publisher_receipt(client, pdf_url, cache_dir):
    """One bounded native acquisition. No social-side transport or request reads."""
    page, _ = publisher_page_url(pdf_url)
    with TemporaryDirectory(prefix='report-post-', dir=Path(cache_dir)) as scratch:
        path = Path(scratch) / 'post.html'
        client.download_to_file(page, path, max_seconds=20, max_bytes=MAX_METADATA_BYTES)
        return client.download_receipt(page)


def _timestamp(value):
    if type(value) is not str:
        raise ValueError('Full publisher timestamp required')
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError('Publisher timezone required')
    return parsed


class _AttributeGuard(HTMLParser):
    """Reject ambiguous authority attributes before BeautifulSoup normalizes them."""
    fields = {'meta': {'property', 'content'}, 'time': {'datetime'},
              'article': {'id', 'class'}, 'a': {'href', 'onclick', 'title', 'class'}}

    def handle_starttag(self, tag, attrs):
        relevant = self.fields.get(tag, set())
        names = [key for key, _ in attrs if key in relevant]
        if len(names) != len(set(names)):
            raise ValueError('Ambiguous publisher authority attribute')


def capture_post_metadata(pdf_receipt, publisher_receipt, *, domain, period):
    from bs4 import BeautifulSoup
    from .native_report_authority import retained_body
    if domain not in ('national_budget', 'pending_bills'):
        raise ValueError('Reviewed CoB post contract required')
    page, identifier = publisher_page_url(pdf_receipt['request_url'])
    body = retained_body(publisher_receipt, domain, 'text/html')
    if (len(body) > MAX_METADATA_BYTES or publisher_receipt['request_url'] != page
            or publisher_receipt['response_url'] != page):
        raise ValueError('Exact bounded publication post required')
    guard = _AttributeGuard()
    guard.feed(body.decode('utf-8'))
    guard.close()
    soup = BeautifulSoup(body, 'html.parser')
    def meta(name):
        nodes = soup.find_all('meta', attrs={'property':name})
        if len(nodes) != 1 or type(nodes[0].get('content')) is not str:
            raise ValueError('One publisher metadata field required')
        return nodes[0]['content']
    if meta('og:type') != 'article' or meta('og:url') != page:
        raise ValueError('Exact publisher post identity required')
    title = ' '.join(meta('og:title').split())
    title_pattern = (r'NATIONAL GOVERNMENT BUDGET IMPLEMENTATION REVIEW REPORT FY (20\d{2}/(?:20\d{2}|\d{2}))'
        if domain == 'national_budget' else
        r'COUNTY GOVERNMENTS BUDGET IMPLEMENTATION REVIEW REPORT FOR THE FINANCIAL YEAR (20\d{2}/(?:20\d{2}|\d{2}))')
    match = re.fullmatch(title_pattern, title, re.I)
    from .native_report_authority import _fy
    if match is None or _fy(match[1])[0] != period:
        raise ValueError('Publisher title and PDF annual scope differ')
    year = int(period[3:7])
    page_pattern = (rf'/download/national-government-budget-implementation-review-report-(?:for-the-)?fy-{year}-(?:{year+1}|{str(year+1)[-2:]})/'
        if domain == 'national_budget' else
        rf'/download/county-governments-budget-implementation-review-report-for-the-financial-year-{year}-(?:{year+1}|{str(year+1)[-2:]})/')
    if not re.fullmatch(page_pattern, urlsplit(page).path):
        raise ValueError('Publisher post URL and PDF edition differ')
    published_raw, modified_raw = meta('article:published_time'), meta('article:modified_time')
    published, modified = _timestamp(published_raw), _timestamp(modified_raw)
    pdf_time, page_time = _timestamp(pdf_receipt['acquired_at']), _timestamp(publisher_receipt['acquired_at'])
    if (not published <= modified <= min(pdf_time, page_time)
            or abs((pdf_time-page_time).total_seconds()) > PAIR_SECONDS):
        raise ValueError('Contemporaneous retained artifact and post required')
    articles = soup.select('article.wpdmpro.status-publish')
    if len(articles) != 1 or articles[0].get('id') != 'post-'+identifier:
        raise ValueError('One published download post required')
    times = articles[0].select('.post-materials time')
    if (len(times) != 1 or _timestamp(times[0].get('datetime')) != published
            or times[0].get_text(' ', strip=True) != f'{published:%B} {published.day}, {published:%Y}'):
        raise ValueError('Visible publisher day differs')
    parent = times[0].find_parent('a')
    publish_day_label = f' Publish Time : {published:%B} {published.day}, {published:%Y} '
    publish_time_prefixes = tuple(
        f'{publish_day_label}{hour}:{published:%M} '
        for hour in (str(published.hour), f'{published:%H}')
    )
    if (parent is None or parent.get('href') != page
            or not str(parent.get('title','')).startswith(publish_time_prefixes)):
        raise ValueError('Explicit visible publish time required')
    links = articles[0].select('a.wpdm-download-link')
    if len(links) != 1 or links[0].get('onclick') != f"location.href='{pdf_receipt['request_url']}';return false;":
        raise ValueError('Exact article-to-artifact download link required')
    return dict(kind='cob-publisher-post-v1', post_url=page, post_id=identifier,
        title=title, published_at=published_raw, modified_at=modified_raw,
        document_url=pdf_receipt['request_url'], document_checksum=pdf_receipt['digest'],
        period=period), published.date()


def validate_stored_post(value, pdf_receipt, *, started=None, finished=None):
    """Validate stored linkage/chronology only; committed readers never download."""
    context = value.get('publication_authority')
    if context is None:
        return
    receipt = context['receipt']
    observations = receipt['observations']
    page, identifier = publisher_page_url(value['document_url'])
    if (context['kind'] != 'cob-publisher-post-v1' or context['post_url'] != page
            or context['post_id'] != identifier or context['period'] != value['period']
            or context['document_url'] != value['document_url']
            or context['document_checksum'] != value['document_checksum']
            or type(observations) is not list or observations != [{k:v for k,v in context.items() if k != 'receipt'}]
            or receipt['parser_version'] != 'cob-publisher-post-v1'
            or type(receipt['status']) is not int or receipt['status'] != 200
            or receipt['request']['method'] != 'GET' or receipt['request_url'] != page
            or receipt['response_url'] != page or receipt['request']['url'] != page
            or receipt['content_type'].split(';')[0].strip().lower() != 'text/html'
            or not re.fullmatch('[0-9a-f]{64}', receipt['digest'])
            or receipt['storage_key'] != receipt['digest']
            or receipt['byte_check']['status'] != 'matched'
            or receipt['byte_check']['sha256'] != receipt['digest']
            or type(receipt['byte_size']) is not int or not 0 < receipt['byte_size'] <= MAX_METADATA_BYTES):
        raise ValueError('Stored publisher post binding differs')
    published, modified = _timestamp(context['published_at']), _timestamp(context['modified_at'])
    acquired, checked = _timestamp(receipt['acquired_at']), _timestamp(receipt['byte_check']['checked_at'])
    pdf_time = _timestamp(pdf_receipt['acquired_at'])
    if (published.date().isoformat() != value['published_on'] or not published <= modified <= min(acquired,pdf_time)
            or acquired > checked or abs((acquired-pdf_time).total_seconds()) > PAIR_SECONDS
            or started is not None and not started <= acquired <= checked <= finished):
        raise ValueError('Stored publisher post chronology differs')
