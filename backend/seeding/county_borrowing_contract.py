"""Finite, reviewed official editions. Reissues require a code/source review."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import httpx

EDITIONS = {e['id']: e for e in json.loads((Path(__file__).with_name('fixtures') / 'county_borrowing_editions.json').read_text())}
MAX_BYTES = 40 * 1024 * 1024
MAX_SECONDS = 60


class CountyBorrowingRefused(ValueError):
    """Fixed diagnostic for refused source or persistence contracts."""


def edition(key):
    if type(key) is not str or key not in EDITIONS:
        raise CountyBorrowingRefused('Unsupported county borrowing edition')
    return EDITIONS[key]


def fetch_publication(key):
    spec = edition(key)
    started = time.monotonic()
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=15) as client:
        with client.stream('GET', spec['url'], headers={'User-Agent': 'KenyaAuditAppSeeder/1.0', 'Accept-Encoding': 'identity'}) as response:
            if (response.status_code != 200 or response.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/pdf'):
                raise CountyBorrowingRefused('County borrowing requires a 200 PDF from the reviewed URL')
            if response.headers.get('content-encoding', 'identity').strip().lower() != 'identity':
                raise CountyBorrowingRefused('County borrowing encoded response refused')
            body = bytearray()
            for chunk in response.iter_raw():
                if time.monotonic() - started > MAX_SECONDS or len(body) + len(chunk) > min(MAX_BYTES, spec['size_bytes']):
                    raise CountyBorrowingRefused('County borrowing transport exceeded its byte or time bound')
                body.extend(chunk)
    return bytes(body), datetime.now(timezone.utc)

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import pdfplumber

EXTRACTOR = 'county_borrowing_v1'
DATASET = 'county_borrowing'


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':'))
    except (ValueError, TypeError):
        raise CountyBorrowingRefused('County borrowing evidence must be finite strict JSON') from None


def expected_extraction(key):
    spec = edition(key)
    if type(spec['instruments']) is not list or len(spec['instruments']) > 47:
        raise CountyBorrowingRefused('County borrowing instrument mapping exceeds its bound')
    for record in spec['instruments']:
        if (type(record) is not dict or record.get('obligation_kind') != 'direct_county_borrowing'
                or record.get('basis') != 'actual' or record.get('currency') != 'KES'
                or record.get('county_slug') not in spec['county_slugs']
                or record.get('page_ref') not in {'p.' + p for p in spec['pages']}):
            raise CountyBorrowingRefused('Only reviewed actual county contract stock mappings are supported')
    return {'schema_version': 1, 'dataset': DATASET, 'edition': key,
            'artifact_sha256': spec['sha256'], 'artifact_bytes': spec['size_bytes'],
            'scope': spec['scope'], 'county_slugs': deepcopy(spec['county_slugs']),
            'status': spec['status'], 'reason': spec['reason'],
            'reporting_period_end': spec['reporting_period_end'],
            'complete_liability_coverage': False, 'pages': deepcopy(spec['pages']),
            'instruments': deepcopy(spec['instruments']),
            'parser_sha256': sha256(Path(__file__).read_bytes()).hexdigest()}


def parse_publication(key, payload):
    spec = edition(key)
    if (type(payload) is not bytes or not 1 <= len(payload) <= MAX_BYTES
            or len(payload) != spec['size_bytes'] or sha256(payload).hexdigest() != spec['sha256']
            or not payload.startswith(b'%PDF-') or b'%%EOF' not in payload[-1024:]):
        raise CountyBorrowingRefused('County borrowing PDF edition changed, incomplete or unreviewed')
    try:
        with pdfplumber.open(BytesIO(payload)) as pdf:
            if len(pdf.pages) != spec['page_count']:
                raise CountyBorrowingRefused('County borrowing PDF page count differs')
            for page, expected in spec['pages'].items():
                actual = ' '.join((pdf.pages[int(page)-1].extract_text() or '').split())
                if sha256(actual.encode()).hexdigest() != expected:
                    raise CountyBorrowingRefused('County borrowing visible source text differs from the reviewed page')
    except CountyBorrowingRefused:
        raise
    except Exception:
        raise CountyBorrowingRefused('County borrowing PDF could not be read') from None
    return expected_extraction(key)


def document_fields(key, country_id):
    from models import DocumentStatus, DocumentType
    spec = edition(key)
    return dict(country_id=country_id, url=spec['url'], publisher=spec['publisher'], title=spec['title'],
                md5=spec['md5'], doc_type=DocumentType.REPORT, status=DocumentStatus.AVAILABLE,
                content_type='application/pdf', http_status=200, file_path=None)


def document_metadata(key):
    spec = edition(key)
    return {'dataset': DATASET, 'edition': key, 'artifact_sha256': spec['sha256'],
            'artifact_bytes': spec['size_bytes'], 'storage_key': spec['sha256']}


def document_matches(document, key, country_id):
    return (all(getattr(document, k) == v for k, v in document_fields(key, country_id).items())
            and type(document.http_status) is int and document.last_verified_at is not None
            and type(document.meta) is dict and canonical(document.meta) == canonical(document_metadata(key)))
