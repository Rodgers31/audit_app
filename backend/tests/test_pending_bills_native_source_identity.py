"""Native source selection refuses changed capabilities before any DB access."""
from copy import deepcopy
from unittest.mock import patch

import pytest

from seeding.domains.pending_bills.writer import _get_or_create_source_document
from seeding.native_report_authority import NativeReportAuthority, capture_pdf_report, digest
from test_native_publisher_metadata import inputs


def captured(tmp_path):
    path, receipt, publisher = inputs(tmp_path, 'pending_bills')
    authority, reason = capture_pdf_report(path, receipt, domain='pending_bills', publisher_receipt=publisher)
    assert authority is not None, reason
    return authority


def test_genuine_native_capability_creates_a_source(db_session, seed_country, tmp_path):
    authority = captured(tmp_path)
    source = _get_or_create_source_document(db_session, authority.value['document_url'],
        'Owned native source', native_report_authority=authority)
    assert source.country_id == seed_country.id
    assert source.url == authority.value['document_url']


@pytest.mark.parametrize('change', ['period', 'url', 'snapshot', 'reconstructed', 'period_and_snapshot'])
def test_changed_native_capability_refuses_before_query(db_session, tmp_path, change):
    authority = captured(tmp_path)
    if change in ('period', 'period_and_snapshot'):
        authority.value['period'] = 'FY 2024/25'
        if change == 'period_and_snapshot':
            authority._snapshot = digest(authority.value)
    elif change == 'url':
        authority.value['document_url'] += '&changed=1'
    elif change == 'snapshot':
        authority._snapshot = '0' * 64
    else:
        rebuilt = object.__new__(NativeReportAuthority)
        rebuilt.value, rebuilt.receipt = deepcopy(authority.value), authority.receipt
        authority = rebuilt
    with patch.object(db_session, 'query', side_effect=AssertionError('Invalid capability reached SQL')):
        with pytest.raises(ValueError, match='Intact native'):
            _get_or_create_source_document(db_session, authority.value['document_url'],
                'Owned native source', native_report_authority=authority)


def test_fresh_native_report_keeps_existing_budget_lane_separate(db_session, seed_country, tmp_path):
    from datetime import datetime, timezone
    from models import DocumentType, SourceDocument
    authority = captured(tmp_path)
    budget = SourceDocument(country_id=seed_country.id, title='Owned budget record',
        url=authority.value['document_url'], publisher='Office of the Controller of Budget (OCOB)',
        doc_type=DocumentType.BUDGET, fetch_date=datetime.now(timezone.utc), meta={'owned_budget': True})
    db_session.add(budget);db_session.flush()
    source = _get_or_create_source_document(db_session, authority.value['document_url'],
        'Owned pending report', native_report_authority=authority)
    assert source.id != budget.id and source.doc_type == DocumentType.REPORT
    assert budget.title == 'Owned budget record' and budget.meta == {'owned_budget': True}


def test_two_report_candidates_still_refuse_before_source_mutation(db_session, seed_country, tmp_path):
    from datetime import datetime, timezone
    from models import DocumentType, SourceDocument
    authority = captured(tmp_path)
    for title in ('Owned report one', 'Owned report two'):
        db_session.add(SourceDocument(country_id=seed_country.id, title=title,
            url=authority.value['document_url'], publisher='Office of the Controller of Budget (OCOB)',
            doc_type=DocumentType.REPORT, fetch_date=datetime.now(timezone.utc), meta={'owned': title}))
    db_session.flush()
    with pytest.raises(ValueError, match='Ambiguous native pending bills source identity'):
        _get_or_create_source_document(db_session, authority.value['document_url'],
            'Unexpected replacement', native_report_authority=authority)
    assert {r.title for r in db_session.query(SourceDocument).all()} == {'Owned report one', 'Owned report two'}
