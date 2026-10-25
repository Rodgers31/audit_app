"""Native report availability authority over retained official publisher bytes.

This is independent of financial cell qualification. It emits no amounts and
performs no network I/O. Only native producers can carry the runtime capability
through parsing; exported JSON cannot grant publication authority.
"""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

if __package__.startswith('backend.'):
    from backend.services.response_receipts import acquisition_is_intact, copy_receipt, receipt_is_sealed, seal_receipt, persist_receipt
else:
    from services.response_receipts import acquisition_is_intact, copy_receipt, receipt_is_sealed, seal_receipt, persist_receipt

VERSION = 'native-report-authority-v1'
KEY = 'native_report_authority_v1'
DOMAINS = {
    'national_budget': ('cob', ('cob.go.ke', 'www.cob.go.ke'), 'Controller of Budget', '/budget'),
    'revenue_by_source': ('kra', ('kra.go.ke', 'www.kra.go.ke'), 'Kenya Revenue Authority', '/budget'),
    'audits': ('oag', ('oagkenya.go.ke', 'www.oagkenya.go.ke'), 'Office of the Auditor-General', '/audits'),
}
_TOKEN = object()
_DATE_LABEL = re.compile(r"^(?:Publication date|Published on):[ \t]*(.+?)[ \t]*$", re.I)
_MONTHS = {name.lower():i for i,name in enumerate(('January','February','March','April','May','June','July','August','September','October','November','December'),1)}


def _full_date(value):
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
        return date.fromisoformat(value)
    match = re.fullmatch(r'(\d{1,2}) ([A-Za-z]+) (\d{4})',value)
    if match and match[2].lower() in _MONTHS:
        return date(int(match[3]),_MONTHS[match[2].lower()],int(match[1]))
    raise ValueError('Full publisher day required')


def source_identity(source):
    metadata = source.meta if type(source.meta) is dict else {}
    artifact = metadata.get('pdf_artifact_v1')
    if type(artifact) is dict:
        artifact = {k:v for k,v in artifact.items() if k not in {'verification_time','verification_time_reason'}}
    return dict(country_id=source.country_id, publisher=source.publisher, title=source.title,
        url=source.url, md5=source.md5, content_type=source.content_type,
        http_status=source.http_status, artifact=artifact)



def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class NativeReportAuthority:
    def __init__(self, value, receipt, *, token=None):
        if token is not _TOKEN:
            raise TypeError('Native publisher parser capability required')
        self.value, self.receipt = deepcopy(value), deepcopy(receipt)
        self._snapshot = digest(value)

    def __deepcopy__(self, memo):
        result = NativeReportAuthority(self.value, self.receipt, token=_TOKEN)
        result._snapshot = self._snapshot
        memo[id(self)] = result
        return result

    def __reduce_ex__(self, protocol):
        return dict, (self.value,)


def official_url(url, domain):
    try:
        parsed = urlsplit(url)
        return (domain in DOMAINS and parsed.scheme == 'https' and parsed.hostname in DOMAINS[domain][1]
                and parsed.username is None and parsed.password is None and parsed.port in (None, 443)
                and not parsed.fragment)
    except (TypeError, ValueError, AttributeError):
        return False


def retained_body(receipt, domain, content_type):
    if (not acquisition_is_intact(receipt) or receipt.get('parser_result_origin')
            or type(receipt.get('status')) is not int or receipt['status'] != 200
            or receipt.get('request', {}).get('method') != 'GET'
            or not official_url(receipt.get('request_url'), domain)
            or not official_url(receipt.get('response_url'), domain)
            or str(receipt.get('content_type', '')).split(';')[0].strip().lower() != content_type
            or receipt.get('byte_check', {}).get('status') != 'matched'
            or receipt.get('byte_check', {}).get('sha256') != receipt.get('digest')
            or type(receipt.get('byte_size')) is not int or not 0 < receipt['byte_size'] <= 64*1024*1024):
        raise ValueError('Retained official acquisition required')
    body = receipt._store.read(receipt['storage_key'])
    if type(body) is not bytes or len(body) != receipt['byte_size'] or hashlib.sha256(body).hexdigest() != receipt['digest']:
        raise ValueError('Retained source bytes differ')
    return body


def _fy(raw):
    match = re.fullmatch(r'(20\d{2})/(20\d{2}|\d{2})', raw)
    if not match:
        raise ValueError('Exact fiscal-year scope required')
    year, end = int(match[1]), int(match[2])
    if end < 100:
        end += year // 100 * 100
    if end != year + 1:
        raise ValueError('Consecutive fiscal-year scope required')
    return f'FY {year}/{str(end)[-2:]}', f'{year}-07-01', f'{end}-06-30'


def _capture(receipt, *, domain, entity, scope_key, period, start, end, published, locator):
    if date.fromisoformat(start) > date.fromisoformat(end) or date.fromisoformat(end) > published:
        raise ValueError('Completed annual reporting period required')
    acquired = datetime.fromisoformat(receipt['acquired_at'])
    checked = datetime.fromisoformat(receipt['byte_check']['checked_at'])
    if acquired.utcoffset() is None or checked.utcoffset() is None or not published <= acquired.date() or checked < acquired:
        raise ValueError('Publisher chronology invalid')
    body = receipt._store.read(receipt['storage_key'])
    if hashlib.sha256(body).hexdigest() != receipt['digest']:
        raise ValueError('Retained source changed during parsing')
    value = dict(domain=domain, entity=entity, scope_key=scope_key, period=period,
        period_start=start, period_end=end, published_on=published.isoformat(), locator=locator,
        document_checksum=receipt['digest'], document_md5=hashlib.md5(body, usedforsecurity=False).hexdigest(), document_url=receipt['request_url'])
    captured = copy_receipt(receipt, parser_version=VERSION)
    seal_receipt(captured, [value])
    return NativeReportAuthority(value, captured, token=_TOKEN)


def capture_kra_release(receipt):
    """KRA article's labelled full day and leading annual scope, not listing hints.

    Dashboard bundles/iframe dates and press-release listing dates cannot attest
    to the exact report. Unsupported layouts return an explicit refusal.
    """
    try:
        body = retained_body(receipt, 'revenue_by_source', 'text/html')
        if len(body) > 2*1024*1024:
            raise ValueError('Article byte limit exceeded')
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(body, 'html.parser')
        articles = soup.select('.blog-content')
        if len(articles) != 1:
            raise ValueError('One publisher article required')
        lead = articles[0].find('p')
        lead = lead.get_text(' ', strip=True) if lead else ''
        # The reviewed publisher lead states an achieved whole-year result.
        # A bare FY mention cannot distinguish a monthly result or a target.
        annual = re.fullmatch(
            r'The Kenya Revenue Authority \(KRA\) has surpassed the revenue target of '
            r'Kshs\. [0-9]+(?:[.,][0-9]+)* (?:Trillion|Billion) for the Financial Year '
            r'(20\d{2}/(?:20\d{2}|\d{2})) after collecting '
            r'Kshs\. [0-9]+(?:[.,][0-9]+)* (?:Trillion|Billion)\.', lead)
        if annual is None:
            raise ValueError('Reviewed annual achieved-results lead unavailable')
        years = [annual[1]]
        period, start, end = _fy(years[0])
        dates = [node.get_text(' ', strip=True) for node in soup.select('.bottom-wrapper p')
                 if node.get_text(' ', strip=True).startswith('PRESS RELEASE')]
        if len(dates) != 1 or not re.fullmatch(r'PRESS RELEASE \d{2}/\d{2}/\d{4}', dates[0]):
            raise ValueError('Full publisher-labelled article date unavailable')
        published = datetime.strptime(dates[0].removeprefix('PRESS RELEASE '), '%d/%m/%Y').date()
        return _capture(receipt, domain='revenue_by_source', entity='Kenya annual revenue performance',
            scope_key='annual-revenue', period=period, start=start, end=end, published=published,
            locator=dates[0]+'; article lead: Financial Year '+years[0]), None
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        return None, 'native_report_date_or_scope_unavailable'


def capture_pdf_report(path: Path, receipt, *, domain):
    """Read the first three actual PDF pages; caller text/cache is never authority."""
    if domain not in ('national_budget', 'audits'):
        return None, 'native_report_domain_unavailable'
    try:
        body = retained_body(receipt, domain, 'application/pdf')
        if path.read_bytes() != body:
            raise ValueError('PDF input differs from retained bytes')
        import io
        import pdfplumber
        from pdfminer.pdfexceptions import PDFException
        from pdfplumber.utils.exceptions import PdfminerException
        pages = []
        try:
            with pdfplumber.open(io.BytesIO(body), pages=[1,2,3]) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ''
                    if len(page_text) > 100000:
                        raise ValueError('Bounded cover text required')
                    pages.append((page.page_number, page_text))
        except (PDFException, PdfminerException):
            raise ValueError('Malformed retained PDF') from None
        candidates = [(page, line.strip(), _DATE_LABEL.fullmatch(line.strip()))
            for page, content in pages for line in content.splitlines() if _DATE_LABEL.fullmatch(line.strip())]
        if len(candidates) != 1:
            raise ValueError('One explicit full publisher publication date required')
        page, span, match = candidates[0]
        published = _full_date(match[1])
        text = ' '.join(' '.join(content.split()) for _, content in pages)
        if domain == 'national_budget':
            scope = re.findall(r'NATIONAL GOVERNMENT BUDGET IMPLEMENTATION REVIEW REPORT(?: FOR THE)?\s+(?:FY|FINANCIAL YEAR)\s*(20\d{2}/(?:20\d{2}|\d{2}))\b', text, re.I)
            # Quarterly scope is deliberately not promoted as an annual report.
            if len(set(scope)) != 1 or re.search(r'FIRST (?:THREE|SIX|NINE)|QUARTER|HALF.YEAR', text, re.I):
                raise ValueError('Exact annual national report scope required')
            period, start, end = _fy(scope[0])
            entity, scope_key = 'National Government of Kenya', 'annual-budget'
        else:
            scopes = re.findall(r'REPORT OF THE AUDITOR.GENERAL ON (.{3,160}?) FOR THE YEAR ENDED 30 JUNE (20\d{2})\b', text, re.I)
            if len(set(scopes)) != 1:
                raise ValueError('Exact auditee and annual report scope required')
            auditee, year = scopes[0]
            if not re.fullmatch(r'[A-Za-z0-9 ,&()/-]{3,160}', auditee):
                raise ValueError('Bounded audited institution required')
            entity = ' '.join(auditee.split())
            scope_key = hashlib.sha256(entity.casefold().encode()).hexdigest()[:32]
            period, start, end = _fy(f'{int(year)-1}/{year}')
        return _capture(receipt, domain=domain, entity=entity, scope_key=scope_key,
            period=period, start=start, end=end, published=published, locator=f'PDF page {page}; {span}'), None
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        return None, 'native_report_date_or_scope_unavailable'


def lock_native_domain(session, domain):
    """Serialize native completion and draft admission with bounded transaction locks."""
    if domain not in DOMAINS:
        raise ValueError('Reviewed native domain required')
    if session.get_bind().dialect.name == 'postgresql':
        from sqlalchemy import text
        # Stable disjoint application namespace; no global/advisory session lock.
        session.execute(text("SELECT set_config('lock_timeout', CASE WHEN setting::bigint=0 THEN '2000' ELSE LEAST(setting::bigint,2000)::text END, true) FROM pg_settings WHERE name='lock_timeout'"))
        session.execute(text('SELECT pg_advisory_xact_lock(802, :domain)'),
                        {'domain': list(DOMAINS).index(domain)+1})


def persist_native_report(session, source, authority, *, context, domain):
    """Bind proof to the native transaction/job. No commit or silent promotion.

    The source lock serializes replacement and admission. Missing proof clears
    current authority on a producer update, while immutable old receipts remain.
    """
    from sqlalchemy import select
    if __package__.startswith('backend.'):
        from backend.models import SourceDocument, IngestionJob, IngestionStatus, Country
    else:
        from models import SourceDocument, IngestionJob, IngestionStatus, Country
    if domain not in DOMAINS:
        raise ValueError('Reviewed native domain required')
    if type(context.dry_run) is not bool:
        raise ValueError("Explicit native dry-run state required")
    if context.dry_run:
        return None
    lock_native_domain(session, domain)
    session.flush()
    session.execute(select(SourceDocument.id).where(SourceDocument.id == source.id).with_for_update()).scalar_one()
    session.refresh(source, ['meta'])
    active = dict((source.meta or {}).get(KEY) or {})
    active.pop(domain, None)
    source.meta = {**(source.meta or {}), KEY: active}
    if authority is None:
        session.flush()
        if session.get_bind().dialect.name == 'postgresql':
            from sqlalchemy import text
            session.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
        session.refresh(source, ['meta'])
        stored = (source.meta or {}).get(KEY)
        if type(stored) is not dict or domain in stored:
            raise ValueError('Native authority invalidation readback differs')
        return None
    if (not isinstance(authority, NativeReportAuthority) or authority._snapshot != digest(authority.value)
            or not receipt_is_sealed(authority.receipt) or authority.receipt.get('observations') != [authority.value]
            or authority.value['domain'] != domain or authority.value['document_url'] != source.url
            or not official_url(source.url, domain) or source.publisher != DOMAINS[domain][2]
            or type(context.job_id) is not int or context.job_id <= 0):
        raise ValueError('Intact native report/job authority required')
    country = session.get(Country, source.country_id)
    if country is None or country.iso_code != 'KEN':
        raise ValueError('Kenyan native report country required')
    artifact = (source.meta or {}).get('pdf_artifact_v1')
    if (source.status.name == 'ARCHIVED'
            or source.md5 is not None and source.md5 != authority.value['document_md5']
            or artifact is not None and (type(artifact) is not dict
                or artifact.get('sha256') != authority.value['document_checksum']
                or artifact.get('md5') != authority.value['document_md5'])):
        raise ValueError('Current native source artifact differs from parsed report')
    job = session.get(IngestionJob, context.job_id)
    if job is None or job.domain != domain or job.dry_run is not False or job.status != IngestionStatus.RUNNING:
        raise ValueError('Exact running native ingestion job required')
    ext = persist_receipt(session, source, authority.receipt, extractor=VERSION)
    receipt = ext.extracted_json['response_receipt']
    if (receipt.get('byte_check', {}).get('status') != 'matched'
            or digest(receipt) != digest(dict(authority.receipt))
            or ext.source_document_id != source.id or ext.extractor != VERSION):
        raise ValueError('Native report retention unavailable at persistence')
    identity = source_identity(source)
    binding = dict(extraction_id=ext.id, ingestion_id=job.id, country_id=source.country_id, source_identity=identity,
        authority_hash=digest(dict(receipt=receipt, value=authority.value, country_id=source.country_id,
                                  publisher=source.publisher, ingestion_id=job.id, source_identity=identity)))
    active = {**active, domain: binding}
    source.meta = {**source.meta, KEY: active}
    meta = dict(job.meta or {})
    records = dict(meta.get('native_report_records') or {})
    ids = list(records.get(domain) or [])
    if ext.id not in ids:
        ids.append(ext.id)
    if len(ids) > 1000:
        raise ValueError('Native report cohort limit exceeded')
    records[domain] = ids
    series = dict(meta.get('native_report_series') or {})
    series[authority.value['scope_key']] = ext.id
    job.meta = {**meta, 'native_report_records': records, 'native_report_series': series}
    expected_meta = digest(job.meta)
    session.flush()
    if session.get_bind().dialect.name == 'postgresql':
        from sqlalchemy import text
        session.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
    session.refresh(ext)
    session.refresh(job)
    if (digest(ext.extracted_json) != digest({'response_receipt':dict(authority.receipt)})
            or digest(job.meta) != expected_meta):
        raise ValueError('Native authority receipt/job readback differs')
    # Serialize JSON exactly: bool/number substitutions must not compare equal.
    session.refresh(source, ['meta'])
    if digest(source.meta[KEY][domain]) != digest(binding):
        raise ValueError('Native authority binding readback differs')
    return ext.id
