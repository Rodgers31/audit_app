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
    'pending_bills': ('cob', ('cob.go.ke', 'www.cob.go.ke'), 'Office of the Controller of Budget (OCOB)', '/debt'),
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
    def __init__(self, value, receipt, *, token=None, publisher_receipt=None):
        if token is not _TOKEN:
            raise TypeError('Native publisher parser capability required')
        self.value, self.receipt = deepcopy(value), deepcopy(receipt)
        self.publisher_receipt = deepcopy(publisher_receipt)
        self._snapshot = digest(value)

    def __deepcopy__(self, memo):
        result = NativeReportAuthority(self.value, self.receipt, token=_TOKEN, publisher_receipt=self.publisher_receipt)
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


def _capture(receipt, *, domain, entity, scope_key, period, start, end, published, locator, publication=None, publisher_receipt=None, catalogue=None):
    evidence_day = date.fromisoformat(catalogue['catalogued_on']) if catalogue is not None else published
    if date.fromisoformat(start) > date.fromisoformat(end) or date.fromisoformat(end) > evidence_day:
        raise ValueError('Completed annual reporting period required')
    acquired = datetime.fromisoformat(receipt['acquired_at'])
    checked = datetime.fromisoformat(receipt['byte_check']['checked_at'])
    if acquired.utcoffset() is None or checked.utcoffset() is None or not evidence_day <= acquired.date() or checked < acquired:
        raise ValueError('Publisher chronology invalid')
    body = receipt._store.read(receipt['storage_key'])
    if hashlib.sha256(body).hexdigest() != receipt['digest']:
        raise ValueError('Retained source changed during parsing')
    value = dict(domain=domain, entity=entity, scope_key=scope_key, period=period,
        period_start=start, period_end=end, published_on=published.isoformat() if published is not None else None, locator=locator,
        document_checksum=receipt['digest'], document_md5=hashlib.md5(body, usedforsecurity=False).hexdigest(), document_url=receipt['request_url'])
    retained_publisher = None
    if publication is not None:
        retained_publisher = copy_receipt(publisher_receipt, parser_version='cob-publisher-post-v1')
        seal_receipt(retained_publisher, [publication])
        value['publication_authority'] = {**publication, 'receipt':dict(retained_publisher)}
    if publication is not None:
        from .cob_report_metadata import validate_stored_post
        validate_stored_post(value, receipt)
    if catalogue is not None:
        from .kra_report_catalogue import VERSION as catalogue_version, validate_stored_catalogue
        retained_publisher = copy_receipt(publisher_receipt, parser_version=catalogue_version)
        seal_receipt(retained_publisher, [catalogue])
        value.update(evidence_kind='publisher_catalogue', catalogued_on=catalogue['catalogued_on'],
            catalogue_url=catalogue['catalogue_url'], catalogue_authority={**catalogue,'receipt':dict(retained_publisher)})
        validate_stored_catalogue(value, receipt)
    captured = copy_receipt(receipt, parser_version=VERSION)
    seal_receipt(captured, [value])
    return NativeReportAuthority(value, captured, token=_TOKEN, publisher_receipt=retained_publisher)


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


def capture_pdf_report(path: Path, receipt, *, domain, publisher_receipt=None, publisher_loader=None):
    """Read the first three actual PDF pages; caller text/cache is never authority."""
    if domain not in ('national_budget', 'audits', 'pending_bills'):
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
        if len(candidates) > 1:
            raise ValueError('Ambiguous PDF publication dates')
        published = _full_date(candidates[0][2][1]) if candidates else None
        text = ' '.join(' '.join(content.split()) for _, content in pages)
        if domain in ('national_budget', 'pending_bills'):
            heading = ('NATIONAL GOVERNMENT BUDGET IMPLEMENTATION REVIEW REPORT' if domain == 'national_budget'
                       else 'COUNTY GOVERNMENTS BUDGET IMPLEMENTATION REVIEW REPORT')
            scope = re.findall(heading+r'(?: FOR THE)?\s+(?:FY|FINANCIAL YEAR)\s*(20\d{2}/(?:20\d{2}|\d{2}))\b', text, re.I)
            # Quarterly scope is deliberately not promoted as an annual report.
            scopes = {_fy(raw) for raw in scope}
            from .cob_report_scope import has_subperiod_scope
            if len(scopes) != 1 or has_subperiod_scope(text):
                raise ValueError('Exact annual national report scope required')
            period, start, end = scopes.pop()
            entity, scope_key = (('National Government of Kenya', 'annual-budget') if domain == 'national_budget'
                                 else ('County Governments of Kenya', 'annual-county-payables-report'))
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
        publication = None
        retained = 'retained_pdf_validation' in receipt
        if (published is None or retained) and publisher_receipt is None and publisher_loader is not None:
            publisher_receipt = publisher_loader()
            if publisher_receipt is None:
                raise ValueError('Retained publisher post unavailable')
        if retained and publisher_receipt is None:
            raise ValueError('Current publisher post required for retained reuse')
        if publisher_receipt is not None:
            from .cob_report_metadata import capture_post_metadata
            publication, post_day = capture_post_metadata(receipt, publisher_receipt, domain=domain, period=period)
            if published is not None and published != post_day:
                raise ValueError('PDF and publisher post dates conflict')
            published = post_day
            locator = f'Publisher post {publication["post_url"]}; article:published_time corroborated by visible Publish Time; PDF cover scope'
        elif candidates:
            locator = f'PDF page {candidates[0][0]}; {candidates[0][1]}'
        else:
            raise ValueError('Full publisher publication date required')
        return _capture(receipt, domain=domain, entity=entity, scope_key=scope_key,
            period=period, start=start, end=end, published=published, locator=locator,
            publication=publication, publisher_receipt=publisher_receipt), None
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        return None, 'native_report_date_or_scope_unavailable'


def lock_native_domain(session, domain):
    """Serialize native completion and draft admission with bounded transaction locks."""
    if domain not in DOMAINS:
        raise ValueError('Reviewed native domain required')
    if session.get_bind().dialect.name == 'postgresql':
        from sqlalchemy import text
        # Stable disjoint application namespace; no global/advisory session lock.
        # Materialization and the consumed configured value order the existing
        # timeout bound before acquiring the same transaction-scoped mutex.
        session.execute(text("""WITH bounds AS MATERIALIZED (
            SELECT set_config('lock_timeout', CASE WHEN setting::bigint=0 THEN '2000'
                ELSE LEAST(setting::bigint,2000)::text END, true) AS configured
            FROM pg_settings WHERE name='lock_timeout')
            SELECT pg_advisory_xact_lock(802, :domain)
            FROM bounds WHERE configured IS NOT NULL"""),
            {'domain': list(DOMAINS).index(domain)+1}).one()


def _audit_series_head(session, previous_id, candidate, value):
    """One current edition per auditee; preserve the full receipt inventory."""
    if previous_id is None:
        return candidate.id
    if type(previous_id) is not int or not 0 < previous_id <= 2147483647:
        raise ValueError('Exact audit series head required')
    if previous_id == candidate.id:
        return candidate.id
    from sqlalchemy import select
    if __package__.startswith('backend.'):
        from backend.models import Extraction
    else:
        from models import Extraction
    previous = session.execute(select(Extraction.extractor, Extraction.source_document_id,
        Extraction.extracted_json['response_receipt']['observations'])
        .where(Extraction.id == previous_id)).one_or_none()
    if (previous is None or previous[0] != VERSION or type(previous[2]) is not list
            or len(previous[2]) != 1 or type(previous[2][0]) is not dict):
        raise ValueError('Intact audit series receipt required')
    old = previous[2][0]
    if (old.get('domain') != 'audits' or old.get('scope_key') != value['scope_key']
            or not isinstance(old.get('document_checksum'), str)
            or re.fullmatch('[a-f0-9]{64}', old['document_checksum']) is None):
        raise ValueError('Exact audit series scope required')
    try:
        before = tuple(date.fromisoformat(old[k]) for k in ('period_start','period_end','published_on'))
        after = tuple(date.fromisoformat(value[k]) for k in ('period_start','period_end','published_on'))
    except (KeyError, TypeError, ValueError):
        raise ValueError('Full audit edition chronology required') from None
    if not before[0] <= before[1] <= before[2]:
        raise ValueError('Full audit edition chronology required')
    if before == after:
        if old['document_checksum'] != value['document_checksum']:
            raise ValueError('Conflicting same-release audit editions')
        return candidate.id if previous[1] == candidate.source_document_id else previous_id
    if all(a <= b for a,b in zip(before, after)):
        return candidate.id
    if all(a >= b for a,b in zip(before, after)) and previous[1] != candidate.source_document_id:
        return previous_id
    # Reusing a URL cannot replace the source binding of the chosen newer
    # edition with an older body. The caller's transaction must roll back.
    raise ValueError('Conflicting audit edition chronology')


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
    if authority is None:
        _invalidate_native_report(session, source, domain)
        return None
    # A source may have changed in another transaction before this lock. Every
    # identity/edition guard below must inspect the locked row, not ORM cache.
    session.refresh(source, ['meta', 'url', 'publisher', 'status', 'md5', 'country_id'])
    active = dict((source.meta or {}).get(KEY) or {})
    active.pop(domain, None)
    source.meta = {**(source.meta or {}), KEY: active}
    if (not isinstance(authority, NativeReportAuthority) or authority._snapshot != digest(authority.value)
            or not receipt_is_sealed(authority.receipt) or authority.receipt.get('observations') != [authority.value]
            or authority.value['domain'] != domain or authority.value['document_url'] != source.url
            or not official_url(source.url, domain) or source.publisher != DOMAINS[domain][2]
            or type(context.job_id) is not int or context.job_id <= 0):
        raise ValueError('Intact native report/job authority required')
    metadata = [authority.value[key] for key in ('publication_authority','catalogue_authority') if key in authority.value]
    if len(metadata) > 1 or bool(metadata) != (authority.publisher_receipt is not None):
        raise ValueError('Retained publisher metadata capability required')
    if 'retained_pdf_validation' in authority.receipt and authority.publisher_receipt is None:
        raise ValueError('Current publisher post required for retained reuse')
    if authority.publisher_receipt is not None:
        retained_body(authority.publisher_receipt, domain, 'text/html')
        context_value = metadata[0]
        if (not receipt_is_sealed(authority.publisher_receipt) or type(context_value) is not dict
                or digest(context_value['receipt']) != digest(dict(authority.publisher_receipt))):
            raise ValueError('Intact retained publisher metadata required')
        from .kra_report_catalogue import validate_stored_catalogue
        validate_stored_catalogue(authority.value, authority.receipt)
    country_iso = session.scalar(select(Country.iso_code)
        .where(Country.id == source.country_id).with_for_update(read=True))
    if country_iso != 'KEN':
        raise ValueError('Kenyan native report country required')
    artifact = (source.meta or {}).get('pdf_artifact_v1')
    if (source.status.name == 'ARCHIVED'
            or source.md5 is not None and source.md5 != authority.value['document_md5']
            or artifact is not None and (type(artifact) is not dict
                or artifact.get('sha256') != authority.value['document_checksum']
                or artifact.get('md5') != authority.value['document_md5'])):
        raise ValueError('Current native source artifact differs from parsed report')
    job = session.execute(select(IngestionJob).where(IngestionJob.id == context.job_id)
        .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if job is None or job.domain != domain or job.dry_run is not False or job.status != IngestionStatus.RUNNING:
        raise ValueError('Exact running native ingestion job required')
    if 'retained_pdf_validation' in authority.receipt:
        from .retained_report_receipts import aware, validate_retained_pdf
        from .cob_report_metadata import validate_stored_post
        from datetime import timezone
        started, finished = aware(job.started_at), datetime.now(timezone.utc)
        validate_stored_post(authority.value, authority.receipt, started=started, finished=finished)
        validate_retained_pdf(session, source, authority.receipt, job,
            started=started, finished=finished)
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
    scope = authority.value['scope_key']
    if domain == 'audits':
        previous = series.get(scope)
        if previous is not None and previous not in ids:
            raise ValueError('Audit series head is outside this job')
        series[scope] = _audit_series_head(session, previous, ext, authority.value)
    else:
        series[scope] = ext.id
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


def _invalidate_native_report(session, source, domain):
    """Remove only the locked source's current domain binding, without JSON egress."""
    from sqlalchemy import select, update, func, text
    if __package__.startswith('backend.'):
        from backend.models import SourceDocument
    else:
        from models import SourceDocument
    dialect = session.get_bind().dialect.name
    if dialect == 'postgresql':
        from sqlalchemy.dialects.postgresql import array
        kind = func.jsonb_typeof(SourceDocument.meta[KEY])
        present = SourceDocument.meta[KEY].has_key(domain)
        removal = SourceDocument.meta.op('#-')(array([KEY, domain]))
    elif dialect == 'sqlite':
        path = '$.' + KEY
        kind = func.json_type(SourceDocument.meta, path)
        present = func.json_type(SourceDocument.meta, path + '.' + domain).isnot(None)
        removal = func.json_remove(SourceDocument.meta, path + '.' + domain)
    else:
        raise ValueError('Native authority invalidation dialect unavailable')
    query = select(kind, present).where(SourceDocument.id == source.id)
    shape, exists = session.execute(query).one()
    if shape not in (None, 'null', 'object'):
        raise ValueError('Native authority binding container invalid')
    if exists:
        session.execute(update(SourceDocument).where(SourceDocument.id == source.id)
            .values(meta=removal).execution_options(synchronize_session=False))
    # The ORM may still hold the previous binding. Expire, never merge it back
    # into the narrow database update or fetch unrelated metadata for readback.
    session.expire(source, ['meta'])
    # A prior write can have queued a deferred trigger even when this binding
    # is absent. Keep the constraint/readback barrier on the no-write path too.
    if dialect == 'postgresql':
        session.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
    stored_shape, stored = session.execute(query).one()
    allowed_shapes = ('object',) if exists else (None, 'null', 'object')
    if stored_shape not in allowed_shapes or stored:
        raise ValueError('Native authority invalidation readback differs')
