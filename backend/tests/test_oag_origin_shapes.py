"""Persisted original acquisition shapes refuse deterministically, including -O."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from models import DocumentStatus
from seeding.retained_report_receipts import _check_origin
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_response

URL = 'https://www.oagkenya.go.ke/owned.pdf'
BODY = b'%PDF-1.7\nowned\n%%EOF'


@pytest.mark.parametrize('change', ['missing_acquired', 'acquired_none', 'acquired_bool',
    'acquired_naive', 'checked_absent', 'checked_none', 'checked_list', 'checked_string',
    'checked_time_absent', 'checked_time_bool', 'status_bool', 'size_bool', 'request_list',
    'empty', 'unknown', 'list', 'none'])
def test_persisted_original_malformed_shapes_are_explicit_refusals(tmp_path, change):
    response = httpx.Response(200, content=BODY, headers={'content-type':'application/pdf'},
        request=httpx.Request('GET', URL))
    receipt = dict(capture_response(response, LocalReceiptStore(tmp_path), source_kind='pdf'))
    checksum = receipt['digest']
    if change == 'missing_acquired': receipt.pop('acquired_at')
    elif change == 'acquired_none': receipt['acquired_at'] = None
    elif change == 'acquired_bool': receipt['acquired_at'] = True
    elif change == 'acquired_naive': receipt['acquired_at'] = '2026-11-05T00:00:00'
    elif change == 'checked_absent': receipt.pop('byte_check')
    elif change == 'checked_none': receipt['byte_check'] = None
    elif change == 'checked_list': receipt['byte_check'] = []
    elif change == 'checked_string': receipt['byte_check'] = 'matched'
    elif change == 'checked_time_absent': receipt['byte_check'].pop('checked_at')
    elif change == 'checked_time_bool': receipt['byte_check']['checked_at'] = True
    elif change == 'status_bool': receipt['status'] = True
    elif change == 'size_bool': receipt['byte_size'] = True
    elif change == 'request_list': receipt['request'] = []
    elif change == 'empty': receipt = {}
    elif change == 'unknown': receipt = {'version': 999}
    elif change == 'list': receipt = []
    elif change == 'none': receipt = None
    with pytest.raises(ValueError):
        _check_origin(SimpleNamespace(status=DocumentStatus.AVAILABLE), receipt,
            url=URL, checksum=checksum, size=len(BODY), at=datetime.now(timezone.utc))
