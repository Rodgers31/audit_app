"""Combined OAG volume availability from an exact, dated publisher RSS entry.

RSS dates describe catalogue entries, not publication of the current PDF body.
The PDF title page independently supplies the institution and fiscal year.
Nothing here qualifies findings, financial cells, or an inferred publication day.
"""
from datetime import datetime
from email.utils import format_datetime, parsedate_to_datetime
import hashlib
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.parse import urldefrag, urljoin
import xml.etree.ElementTree as ET

VERSION = 'oag-combined-catalogue-v1'
CONTENT_TYPE = 'application/rss+xml'
MAX_METADATA_BYTES = 512 * 1024
PAIR_SECONDS = 900
_ATOM = '{http://www.w3.org/2005/Atom}'
_YEAR = r'(20\d{2})[/\-](20\d{2})'
_PREFIX = r"AUDITOR[ -]GENERAL'S REPORT ON (?:THE )?COUNTY GOVERNMENTS"
_COVER_PREFIX = r"(?:" + _PREFIX + r"|REPORT OF THE AUDITOR-GENERAL ON THE COUNTY GOVERNMENTS)"
_KIND = r'COUNTY (EXECUTIVES|ASSEMBLIES)'


def _normal(value):
    return ' '.join(value.translate(str.maketrans({'’': "'", '‘': "'", '–': '-', '—': '-'})).split()).upper()


def catalogue_url(period):
    from .native_report_authority import _fy
    year = period.removeprefix('FY ')
    canonical, start, end = _fy(year)
    if canonical != period:
        raise ValueError('Canonical annual OAG period required')
    return (f'https://www.oagkenya.go.ke/document-category/{start[:4]}-{end[:4]}'
            '-county-government-audit-reports/feed/')


def scope_fields(period, institution):
    if institution not in ('executives', 'assemblies'):
        raise ValueError('Reviewed combined institution required')
    from .native_report_authority import _fy
    canonical, start, end = _fy(period.removeprefix('FY '))
    if canonical != period:
        raise ValueError('Canonical annual OAG period required')
    entity = 'County Governments of Kenya: County ' + institution.title()
    return dict(period=period, start=start, end=end, institution=institution,
                volume=1 if institution == 'executives' else 2, entity=entity,
                scope_key=hashlib.sha256(entity.casefold().encode()).hexdigest()[:32])


def combined_scope(pages):
    """One complete reviewed title page; contradictory cover labels refuse."""
    from .native_report_authority import _fy
    from .cob_report_scope import has_subperiod_scope
    candidates = []
    for page, text in pages:
        value = _normal(text)
        match = re.fullmatch(_COVER_PREFIX + r' FOR THE YEAR ' + _YEAR
                            + r' VOLUME (1|2|I|II)\s*[:\-]?\s*' + _KIND, value)
        if match:
            period, _, _ = _fy(f'{match[1]}/{match[2]}')
            fields = scope_fields(period, match[4].lower())
            if match[3] not in ({'1', 'I'} if fields['volume'] == 1 else {'2', 'II'}):
                raise ValueError('OAG volume and institution differ')
            candidates.append({**fields, 'page': page})
    if not candidates:
        return None
    identities = {(s['period'], s['institution']) for s in candidates}
    if len(identities) != 1:
        raise ValueError('Conflicting combined title pages')
    scope = candidates[0]
    cover = ' '.join(_normal(text) for _, text in pages)
    for match in re.finditer(_KIND + r'\s*[:\-]?\s*' + _YEAR, cover):
        period, _, _ = _fy(f'{match[2]}/{match[3]}')
        if (period, match[1].lower()) not in identities:
            raise ValueError('Conflicting combined cover scope')
    if has_subperiod_scope(cover):
        raise ValueError('Annual combined report required')
    return scope


def _title_scope(title, scope):
    value = _normal(title)
    year = rf"{scope['start'][:4]}[/\-]{scope['end'][:4]}"
    institution = 'COUNTY ' + scope['institution'].upper()
    volume = '(?:1|I)' if scope['volume'] == 1 else '(?:2|II)'
    patterns = (
        _PREFIX + r'\s*[,\-]?\s*' + institution + r'\s*\-?\s*' + year,
        _PREFIX + ' FOR THE YEAR ' + year + r' VOLUME ' + volume + r'\s*[:\-]?\s*' + institution,
        r'GREEN BOOK ' + institution + r' VOL\.? ' + volume + r',? ' + year,
    )
    if not any(re.fullmatch(pattern, value) for pattern in patterns):
        raise ValueError('Catalogue title and independently read cover differ')


def _aware(value):
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError('Offset-aware acquisition required')
    return parsed


def _entry_time(raw):
    # No two-digit-year pivot, upload path, build date, or retrieval-day fallback.
    if type(raw) is not str or not re.fullmatch(
        r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} [A-Z][a-z]{2} 20\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}', raw
    ):
        raise ValueError('Full publisher RSS entry timestamp required')
    result = parsedate_to_datetime(raw)
    if result.utcoffset() is None or format_datetime(result) != raw:
        raise ValueError('Unambiguous RSS entry timestamp required')
    return result


def _field(item, name, *, attributes=None):
    matches = [c for c in item if c.tag.rsplit('}', 1)[-1] == name]
    if (len(matches) != 1 or matches[0].tag != name or list(matches[0])
            or matches[0].attrib != (attributes or {})):
        raise ValueError('One unambiguous RSS field required')
    return matches[0].text or ''


def _link(raw, feed):
    url, fragment = urldefrag(urljoin(feed, raw))
    if fragment not in ('', 'new_tab'):
        raise ValueError('Exact catalogue PDF link required')
    return url


def fetch_catalogue_receipt(client, period):
    url = catalogue_url(period)
    with TemporaryDirectory(prefix='oag-catalogue-') as scratch:
        client.download_to_file(url, Path(scratch) / 'entry.xml',
                                max_seconds=20, max_bytes=MAX_METADATA_BYTES)
        return client.download_receipt(url)


def capture_catalogue_report(receipt, publisher_receipt, pages):
    try:
        from .native_report_authority import retained_body, _capture
        scope = combined_scope(pages)
        if scope is None:
            raise ValueError('Combined title page required')
        feed = catalogue_url(scope['period'])
        listing = retained_body(publisher_receipt, 'audits', CONTENT_TYPE)
        if (len(listing) > MAX_METADATA_BYTES or publisher_receipt['request_url'] != feed
                or publisher_receipt['response_url'] != feed
                or b'<!DOCTYPE' in listing.upper() or b'<!ENTITY' in listing.upper()):
            raise ValueError('Bounded exact publisher feed required')
        root = ET.fromstring(listing)
        channels = root.findall('channel')
        if root.tag != 'rss' or root.attrib != {'version': '2.0'} or len(channels) != 1:
            raise ValueError('Reviewed RSS channel required')
        channel = channels[0]
        year = f"{scope['start'][:4]}-{scope['end'][:4]}"
        expected = {' '.join((year + separator + 'County Government Audit Reports - Office of the Auditor-General').upper().split())
                    for separator in ('-', ' ')}
        if _normal(_field(channel, 'title')) not in expected:
            raise ValueError('Publisher channel fiscal year required')
        selfs = channel.findall(_ATOM + 'link')
        if (len(selfs) != 1 or selfs[0].attrib != {'href': feed, 'rel': 'self', 'type': CONTENT_TYPE}):
            raise ValueError('Exact RSS self identity required')
        items = [item for item in channel.findall('item')
                 if _link(_field(item, 'link'), feed) == receipt['request_url']]
        if len(items) != 1:
            raise ValueError('One exact report catalogue entry required')
        item = items[0]
        title = _field(item, 'title')
        _title_scope(title, scope)
        raw_time = _field(item, 'pubDate')
        timestamp = _entry_time(raw_time)
        guid = _field(item, 'guid', attributes={'isPermaLink': 'false'})
        if not re.fullmatch(r'https://www\.oagkenya\.go\.ke/\?post_type=dlp_document&p=[1-9][0-9]{0,8}', guid):
            raise ValueError('Exact OAG document-entry identity required')
        metadata = dict(kind=VERSION, catalogue_url=feed, document_url=receipt['request_url'],
            document_checksum=receipt['digest'], title=title, period=scope['period'],
            institution=scope['institution'], volume=scope['volume'], cover_page=scope['page'],
            entry_guid=guid, entry_timestamp=raw_time, catalogued_on=timestamp.date().isoformat())
        return _capture(receipt, domain='audits', entity=scope['entity'], scope_key=scope['scope_key'],
            period=scope['period'], start=scope['start'], end=scope['end'], published=None,
            locator=f"PDF title page {scope['page']}; exact official RSS entry {guid}; catalogue date only, PDF publication date not stated",
            catalogue=metadata, publisher_receipt=publisher_receipt), None
    except (ValueError, TypeError, KeyError, AttributeError, OSError, ET.ParseError):
        return None, 'native_report_date_or_scope_unavailable'


def validate_stored_catalogue(value, pdf, *, started=None, finished=None):
    context = value['catalogue_authority']
    scope = scope_fields(value['period'], context['institution'])
    feed = catalogue_url(scope['period'])
    receipt = context['receipt']
    _title_scope(context['title'], scope)
    timestamp = _entry_time(context['entry_timestamp'])
    if (value['domain'] != 'audits' or value['published_on'] is not None
            or value['evidence_kind'] != 'publisher_catalogue' or 'publication_authority' in value
            or value['entity'] != scope['entity'] or value['scope_key'] != scope['scope_key']
            or value['period_start'] != scope['start'] or value['period_end'] != scope['end']
            or context['kind'] != VERSION or value['catalogue_url'] != feed or context['catalogue_url'] != feed
            or context['document_url'] != value['document_url'] or context['document_checksum'] != value['document_checksum']
            or context['period'] != scope['period'] or type(context['volume']) is not int or context['volume'] != scope['volume']
            or type(context['cover_page']) is not int or not 1 <= context['cover_page'] <= 3
            or type(context['title']) is not str or not 0 < len(context['title']) <= 300
            or not re.fullmatch(r'https://www\.oagkenya\.go\.ke/\?post_type=dlp_document&p=[1-9][0-9]{0,8}', context['entry_guid'])
            or context['catalogued_on'] != value['catalogued_on'] or value['catalogued_on'] != timestamp.date().isoformat()
            or receipt['observations'] != [{k: v for k, v in context.items() if k != 'receipt'}]
            or receipt['parser_version'] != VERSION or type(receipt['status']) is not int or receipt['status'] != 200
            or receipt['request'] != {'method': 'GET', 'url': feed} or receipt['request_url'] != feed or receipt['response_url'] != feed
            or receipt['content_type'].split(';')[0].strip().lower() != CONTENT_TYPE
            or not re.fullmatch('[0-9a-f]{64}', receipt['digest']) or receipt['storage_key'] != receipt['digest']
            or receipt['byte_check']['status'] != 'matched' or receipt['byte_check']['sha256'] != receipt['digest']
            or type(receipt['byte_size']) is not int or not 0 < receipt['byte_size'] <= MAX_METADATA_BYTES):
        raise ValueError('Stored OAG catalogue binding differs')
    acquired, checked = _aware(receipt['acquired_at']), _aware(receipt['byte_check']['checked_at'])
    original = _aware(pdf['acquired_at'])
    retained = pdf.get('retained_pdf_validation')
    pair = _aware(retained['validated_at']) if retained is not None else original
    if (not datetime.fromisoformat(scope['end']).date() <= timestamp.date()
            or timestamp > min(original, acquired) or acquired > checked
            or abs((pair - acquired).total_seconds()) > PAIR_SECONDS
            or started is not None and not started <= acquired <= checked <= finished):
        raise ValueError('Stored OAG catalogue chronology differs')
