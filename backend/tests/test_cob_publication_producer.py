"""Actual small PDF parser and retained bytes; no source/provider network calls."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import pickle

import httpx
import pytest

from seeding.config import SeedingSettings
from seeding.domains.counties_budget.fetcher import convert_county_pdf_records
from seeding.domains.counties_budget.parser import parse_budget_payload
from seeding.domains.counties_budget.publication import capture_publication_date, PublicationDateEvidence
from seeding.parse_cache import parse_with_cache
from seeding.pdf_evidence import bind_parse_receipt
from seeding.pdf_parsers import CoBQuarterlyReportParser
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_response

URL = 'https://cob.go.ke/owned-sanitized-report.pdf'


def pdf_bytes(actual='0', label='Publication date: 2026-07-01'):
    """Write a valid source PDF with text and ruled cells; no PDF library install."""
    commands = []
    def text(x, y, value):
        value = value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        commands.append(f'BT /F1 10 Tf {x} {y} Td ({value}) Tj ET')
    text(25, 810, 'Controller of Budget County Budget Implementation Review FY2025/26 Annual')
    text(25, 790, label)
    columns = [20, 160, 340, 510]
    for x in columns:
        commands.append(f'{x} 680 m {x} 760 l S')
    for y in [680, 700, 720, 740, 760]:
        commands.append(f'20 {y} m 510 {y} l S')
    for x, value in zip(columns, ['County', 'Allocated (Kshs.Million)', 'Absorbed (Kshs.Million)']):
        text(x + 4, 747, value)
    for y, county, amount in [(727, 'Nairobi', actual), (707, 'Mombasa', '1'), (687, 'Kisumu', '1')]:
        for x, value in zip(columns, [county, '10', amount]):
            text(x + 4, y, value)
    stream = '\n'.join(commands).encode()
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 850] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    body, offsets = bytearray(b'%PDF-1.4\n'), [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(body)); body.extend(f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(body)
    body.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        body.extend(f'{offset:010d} 00000 n \n'.encode())
    body.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(body)


def acquired(tmp_path, actual='0', label='Publication date: 2026-07-01'):
    body = pdf_bytes(actual, label)
    path = tmp_path / ('report-' + sha256(body).hexdigest() + '.pdf')
    path.write_bytes(body)
    store = LocalReceiptStore(tmp_path / 'receipts')
    response = httpx.Response(200, content=body, headers={'content-type': 'application/pdf'}, request=httpx.Request('GET', URL))
    receipt = capture_response(response, store, source_kind='pdf')
    parsed = parse_with_cache(path, cache_dir=tmp_path / 'cache', kind='cob-producer-control',
        parse_fn=CoBQuarterlyReportParser(path).parse, enabled=False)
    receipt = bind_parse_receipt(receipt, parsed)
    date, refusal = capture_publication_date(path, receipt)
    payload = convert_county_pdf_records(parsed, URL, receipt['digest'], receipt=receipt,
        publication_evidence=date, publication_refusal=refusal)
    return path, receipt, parse_budget_payload(payload), date, refusal


def test_real_pdf_date_cells_and_parser_envelope(tmp_path):
    _, receipt, records, evidence, refusal = acquired(tmp_path)
    assert refusal is None and evidence.value['publication_date'] == '2026-07-01'
    assert evidence.value['locator'] == {'page': 1, 'text_span': 'Publication date: 2026-07-01'}
    assert len(records) == 3 and records[0].actual_amount == 0
    assert all(isinstance(r.publication_evidence, PublicationDateEvidence) for r in records)
    assert all(r.source_evidence[0]['checks']['locator'] for r in records)
    assert receipt['digest'] == evidence.value['digest']


@pytest.mark.parametrize('label', ['September 2026', 'Publication date: September 2026',
    'CreationDate: 2026-07-01', 'Publication date: 2099-01-01', 'Publication date: 2026-02-30'])
def test_no_invented_full_publisher_date(tmp_path, label):
    _, _, records, evidence, reason = acquired(tmp_path, label=label)
    assert evidence is None and reason is not None
    assert all(r.publication_evidence is None for r in records)


def test_runtime_authority_does_not_roundtrip_through_json_or_pickle(tmp_path):
    _, _, _, evidence, _ = acquired(tmp_path)
    assert type(pickle.loads(pickle.dumps(evidence))) is dict
    with pytest.raises(TypeError, match='actual retained PDF'):
        PublicationDateEvidence(evidence.value, evidence.receipt)
    assert deepcopy(evidence)._snapshot == evidence._snapshot


@pytest.mark.parametrize('value', ['TRUE', 1, 0, None, 'yes'])
def test_qualification_switch_requires_explicit_boolean(value):
    with pytest.raises(ValueError):
        SeedingSettings(cob_verified_qualification_enabled=value)


def test_qualification_switch_default_off():
    assert SeedingSettings().cob_verified_qualification_enabled is False


from test_counties_budget_domain import sqlite_session, bootstrap


def test_existing_null_source_metadata_remains_supported_with_qualification_off(sqlite_session, bootstrap, tmp_path):
    from datetime import datetime, timezone
    from models import Country, SourceDocument, DocumentType
    from seeding.domains.counties_budget.writer import persist_budget_records
    from seeding.types import DomainRunContext
    from sqlalchemy import select
    country = sqlite_session.scalar(select(Country))
    doc = SourceDocument(country_id=country.id, publisher='Controller of Budget', title='Owned null-metadata control',
        url=URL, doc_type=DocumentType.BUDGET, meta=None, fetch_date=datetime.now(timezone.utc))
    sqlite_session.add(doc); sqlite_session.flush()
    assert doc.meta is None
    records = parse_budget_payload([dict(entity_slug='nairobi-county', entity='Nairobi City County',
        period_label='FY2025/26', start_date='2025-07-01', end_date='2026-06-30', category='Total',
        actual_amount='0', source_url=URL, data_quality='official')])
    stats = persist_budget_records(sqlite_session, records, SeedingSettings(), DomainRunContext(None, False))
    assert stats.created == 1 and not stats.errors
    assert stats.qualification['enabled'] is False
    assert doc.meta['data_quality'] == 'official'


def test_established_nairobi_alias_does_not_allow_a_different_county(sqlite_session, bootstrap, tmp_path):
    from models import Entity, BudgetLine
    from seeding.domains.counties_budget.writer import persist_budget_records
    from seeding.types import DomainRunContext
    from sqlalchemy import select
    entity = sqlite_session.scalar(select(Entity))
    entity.canonical_name = 'Mombasa County'
    _, _, records, _, _ = acquired(tmp_path)
    nairobi = [r for r in records if r.entity_slug == 'nairobi-county']
    assert len(nairobi) == 1
    settings = SeedingSettings(cob_verified_qualification_enabled=True)
    stats = persist_budget_records(sqlite_session, nairobi, settings, DomainRunContext(None, False, 1))
    assert stats.created == 1 and stats.qualification['qualified'] == 0
    assert stats.qualification['reasons'] == {'actual_spending_evidence_unverified': 1}
    assert sqlite_session.scalar(select(BudgetLine.publishable)) is False
