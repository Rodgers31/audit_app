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
