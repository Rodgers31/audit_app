from decimal import Decimal
from datetime import datetime, timezone

import httpx

from models import DebtTimeline, SourceDocument, DocumentType
from seeding.config import SeedingSettings
from seeding.domains.debt_timeline import fetcher, parser, writer
from seeding.domains.national_debt import cbk_bulletin
from seeding.http_client import SeedingHttpClient
from services.receipt_store import LocalReceiptStore
from services.response_receipts import receipt_is_sealed


URL = 'https://www.centralbank.go.ke/uploads/statistical_bulletin/owned.pdf'


def _observed_payload(tmp_path, monkeypatch):
    settings = SeedingSettings(_env_file=None, storage_path=tmp_path,
        cbk_statistical_bulletin_url=URL, http_cache_enabled=False,
        rate_limit='1000/sec')
    body = b'%PDF-1.7\nowned bulletin transport; text port controlled below\n%%EOF'
    monkeypatch.setattr(cbk_bulletin, '_find_public_debt_page_text', lambda _: cbk_bulletin._located_text(
        '4.1.3 Deficit Financing and Public Debt\nShillings million\n'
        '2025/2026\nDecember 600000 400000 1000000', 56))
    with SeedingHttpClient(settings,
            client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
                200, content=body, headers={'content-type': 'application/pdf'}))),
            receipt_store=LocalReceiptStore(tmp_path / 'receipts')) as client:
        base = dict(metadata={}, timeline=[dict(year=2025, external=1, domestic=2, total=3)])
        payload, count = fetcher._overlay_cbk_public_debt(base, client, settings)
    assert count == 1
    return payload


def test_observed_debt_keeps_its_receipt_through_the_overlay_and_parser(tmp_path, monkeypatch):
    payload = _observed_payload(tmp_path, monkeypatch)
    record = parser.parse_debt_timeline_payload(payload)[0]
    assert record.total == 1000
    assert len(record.source_evidence) == 3
    assert all(receipt_is_sealed(item['_response_receipt']) for item in record.source_evidence)


def test_writer_uses_actual_bulletin_url_without_relabelling_old_source(db_session, seed_country, tmp_path, monkeypatch):
    old = SourceDocument(country_id=seed_country.id, title='CBK Statistical Bulletin Table 4.1.3',
        publisher='Central Bank of Kenya / National Treasury',
        url='https://www.centralbank.go.ke/statistics/government-finance-statistics/',
        fetch_date=datetime.now(timezone.utc), doc_type=DocumentType.REPORT)
    db_session.add(old)
    db_session.commit()
    original = (old.id, old.url, old.title, old.publisher)
    payload = _observed_payload(tmp_path, monkeypatch)
    record = parser.parse_debt_timeline_payload(payload)[0]
    writer.write_debt_timeline_records(db_session, [record], payload['metadata'])
    db_session.commit()
    row = db_session.query(DebtTimeline).one()
    assert row.total == Decimal('1000000000000')
    actual = db_session.get(SourceDocument, row.source_document_id)
    assert actual.url == URL
    assert actual.id != old.id
    assert (old.id, old.url, old.title, old.publisher) == original
    assert len(row.meta['source_evidence']) == 3


def test_actual_bulletin_does_not_reuse_an_unrelated_publisher(db_session, seed_country, tmp_path, monkeypatch):
    wrong = SourceDocument(country_id=seed_country.id, title='CBK Statistical Bulletin Table 4.1.3',
        publisher='Unrelated publisher', url=URL,
        fetch_date=datetime.now(timezone.utc), doc_type=DocumentType.REPORT)
    db_session.add(wrong)
    db_session.commit()
    payload = _observed_payload(tmp_path, monkeypatch)
    writer.write_debt_timeline_records(db_session,
        parser.parse_debt_timeline_payload(payload), payload['metadata'])
    db_session.commit()
    row = db_session.query(DebtTimeline).one()
    source = db_session.get(SourceDocument, row.source_document_id)
    assert source.id != wrong.id
    assert source.publisher == 'Central Bank of Kenya'
    assert wrong.publisher == 'Unrelated publisher'
