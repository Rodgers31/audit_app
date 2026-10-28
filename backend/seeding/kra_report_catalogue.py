"""KRA catalogue availability, explicitly NOT report-publication authority.

Native producers pair one retained official annual wrapper with one exact
catalogue entry. Neither a listing day nor acquisition time becomes published_on.
Committed readers validate this saved binding without fetching any source.
"""
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.parse import urljoin

CATALOGUE_URL = 'https://www.kra.go.ke/component/search/?searchphrase=all&searchword=KRA+performance'
VERSION = 'kra-publisher-catalogue-v1'
MAX_METADATA_BYTES = 512 * 1024
MAX_WRAPPER_BYTES = 2 * 1024 * 1024
PAIR_SECONDS = 900


def fetch_catalogue_receipt(client):
    """Only the selected native dashboard needs this single capped request."""
    with TemporaryDirectory(prefix='kra-catalogue-') as scratch:
        client.download_to_file(CATALOGUE_URL, Path(scratch)/'catalogue.html',
                                max_seconds=20, max_bytes=MAX_METADATA_BYTES)
        return client.download_receipt(CATALOGUE_URL)


class _Attributes(HTMLParser):
    def handle_starttag(self, tag, attrs):
        names = [name for name, _ in attrs if name in {'href', 'class'}]
        if len(names) != len(set(names)):
            raise ValueError('Ambiguous catalogue attributes')


def annual_scope(url, period):
    from .native_report_authority import _fy
    match = re.fullmatch(r'https://www\.kra\.go\.ke/annual-revenue-performance-fy-(20\d{2})-(20\d{2})', url)
    if not match or _fy(f'{match[1]}/{match[2]}')[0] != period:
        raise ValueError('Exact official annual dashboard scope required')
    return _fy(f'{match[1]}/{match[2]}')


def _aware(value):
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError('Acquisition offset required')
    return parsed


def capture_catalogue_report(wrapper, catalogue, *, fiscal_year):
    """Exact title/link/category/full day, paired to parsed dashboard fiscal year."""
    try:
        from bs4 import BeautifulSoup
        from .native_report_authority import retained_body, _capture
        body = retained_body(wrapper, 'revenue_by_source', 'text/html')
        listing = retained_body(catalogue, 'revenue_by_source', 'text/html')
        if (len(body) > MAX_WRAPPER_BYTES or len(listing) > MAX_METADATA_BYTES
                or wrapper['response_url'] != wrapper['request_url']
                or catalogue['request_url'] != CATALOGUE_URL or catalogue['response_url'] != CATALOGUE_URL):
            raise ValueError('Exact bounded wrapper and catalogue required')
        period, start, end = annual_scope(wrapper['request_url'], fiscal_year)
        for raw in (body, listing):
            guard = _Attributes(); guard.feed(raw.decode('utf-8')); guard.close()
        page = BeautifulSoup(body, 'html.parser')
        titles = page.select('head > title')
        year = int(start[:4])
        if len(titles) != 1 or titles[0].get_text(' ',strip=True) != f'Annual Revenue Performance - FY {year}/{year+1} - KRA':
            raise ValueError('Exact annual wrapper title required')
        entries = []
        for entry in BeautifulSoup(listing, 'html.parser').select('div.content-wrapper'):
            links = entry.select('p.title a')
            matching = [a for a in links if urljoin(CATALOGUE_URL, a.get('href','')) == wrapper['request_url']]
            if matching:
                entries.append((entry, links, matching))
        if len(entries) != 1:
            raise ValueError('One exact catalogue entry required')
        entry, links, matching = entries[0]
        if len(links) != 1 or len(matching) != 1:
            raise ValueError('Ambiguous catalogue report identity')
        title = matching[0].get_text(' ',strip=True)
        headings = [h.get_text(' ',strip=True) for h in page.find_all('h2')]
        if not title or len(title) > 300 or headings.count(title) != 1:
            raise ValueError('Catalogue and visible wrapper title differ')
        sections = entry.select('p.item-section')
        if len(sections) != 1:
            raise ValueError('One dated category required')
        section = sections[0]
        categories, markers = section.select('span.item-cat'), section.select('span.result-created')
        if (len(categories) != 1 or categories[0].get_text(' ',strip=True) != '(KRA Revenue Performance)'
                or len(markers) != 1 or markers[0].get_text(strip=True)):
            raise ValueError('Reviewed catalogue category/date marker required')
        # Remove only the two verified labels. No arbitrary date in the result
        # description, footer, download size or another result may qualify.
        categories[0].extract(); markers[0].extract()
        if section.find(True) is not None:
            raise ValueError('Unexpected catalogue date markup')
        day_text = section.get_text(' ',strip=True)
        if not re.fullmatch(r'\d{2}/\d{2}/\d{4}',day_text):
            raise ValueError('Full catalogue day required')
        day = datetime.strptime(day_text,'%d/%m/%Y').date()
        metadata = dict(kind=VERSION, catalogue_url=CATALOGUE_URL, document_url=wrapper['request_url'],
            document_checksum=wrapper['digest'], title=title, category='KRA Revenue Performance',
            period=period, catalogued_on=day.isoformat())
        return _capture(wrapper, domain='revenue_by_source', entity='Kenya annual revenue performance',
            scope_key='annual-revenue', period=period, start=start, end=end, published=None,
            locator='Official KRA catalogue: exact annual report title/link/category and entry date; report publication date not stated',
            catalogue=metadata, publisher_receipt=catalogue), None
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        return None, 'native_report_date_or_scope_unavailable'


def validate_stored_catalogue(value, wrapper, *, started=None, finished=None):
    """Check the immutable paired receipts and current job; never re-download."""
    context = value.get('catalogue_authority')
    if context is None:
        if any(key in value for key in ('evidence_kind','catalogued_on','catalogue_url')):
            raise ValueError('Catalogue binding required')
        return
    receipt = context['receipt']
    period, start, end = annual_scope(value['document_url'],value['period'])
    if (value['domain'] != 'revenue_by_source' or value['published_on'] is not None
            or value['evidence_kind'] != 'publisher_catalogue' or 'publication_authority' in value
            or value['entity'] != 'Kenya annual revenue performance' or value['scope_key'] != 'annual-revenue'
            or value['period_start'] != start or value['period_end'] != end
            or context['kind'] != VERSION or value['catalogue_url'] != CATALOGUE_URL
            or context['catalogue_url'] != CATALOGUE_URL or context['category'] != 'KRA Revenue Performance'
            or context['document_url'] != value['document_url'] or context['document_checksum'] != value['document_checksum']
            or context['period'] != period or context['catalogued_on'] != value['catalogued_on']
            or type(context['title']) is not str or not 0 < len(context['title']) <= 300
            or receipt['observations'] != [{k:v for k,v in context.items() if k != 'receipt'}]
            or receipt['parser_version'] != VERSION or type(receipt['status']) is not int or receipt['status'] != 200
            or receipt['request']['method'] != 'GET' or receipt['request']['url'] != CATALOGUE_URL
            or receipt['request_url'] != CATALOGUE_URL or receipt['response_url'] != CATALOGUE_URL
            or receipt['content_type'].split(';')[0].strip().lower() != 'text/html'
            or not re.fullmatch('[0-9a-f]{64}',receipt['digest']) or receipt['storage_key'] != receipt['digest']
            or receipt['byte_check']['status'] != 'matched' or receipt['byte_check']['sha256'] != receipt['digest']
            or type(receipt['byte_size']) is not int or not 0 < receipt['byte_size'] <= MAX_METADATA_BYTES):
        raise ValueError('Stored catalogue binding differs')
    day = date.fromisoformat(value['catalogued_on'])
    acquired, checked = _aware(receipt['acquired_at']), _aware(receipt['byte_check']['checked_at'])
    original = _aware(wrapper['acquired_at'])
    if (not date.fromisoformat(end) <= day <= min(acquired.date(),original.date())
            or acquired > checked or abs((original-acquired).total_seconds()) > PAIR_SECONDS
            or started is not None and not started <= acquired <= checked <= finished):
        raise ValueError('Stored catalogue chronology differs')
