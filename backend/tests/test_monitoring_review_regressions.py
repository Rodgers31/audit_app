"""Numeric HTTP observations must survive the Sentry privacy projection."""
import json

import pytest

from monitoring.instrumentation import before_send_filter


MARKER = 'INERT-543-PRIVATE-MARKER'


def event():
    return {'event_id': 'a' * 32, 'level': 'error'}


@pytest.mark.parametrize('code', [200, 418, 422, 500, 503])
def test_transaction_without_trace_data_keeps_legacy_numeric_http_status(code):
    value = event()
    value.update(type='transaction', start_timestamp=100, timestamp=101,
                 tags={'http.status_code': str(code), 'private': MARKER},
                 contexts={'trace': {'trace_id': 'b' * 32, 'span_id': 'c' * 16,
                                     'status': 'ok' if code < 400 else 'internal_error'},
                           'response': {'status_code': code, 'headers': {'private': MARKER},
                                        'body': MARKER}})
    result = before_send_filter(value, {})
    assert result is not None
    assert result.get('tags') == {'http.status_code': str(code)}
    assert result.get('contexts', {}).get('response') == {'status_code': code}
    assert MARKER not in json.dumps(result)


@pytest.mark.parametrize('code', [200, 422, 500])
def test_error_with_response_only_keeps_numeric_http_status(code):
    value = event()
    value['contexts'] = {'response': {'status_code': code, 'data': MARKER},
                         'private': {'value': MARKER}}
    result = before_send_filter(value, {})
    assert result is not None
    assert result.get('contexts') == {'response': {'status_code': code}}
    assert MARKER not in json.dumps(result)


@pytest.mark.parametrize('code', [200, 409, 500])
def test_http_child_span_keeps_legacy_status_tag_without_other_tags(code):
    value = event()
    value['spans'] = [{'span_id': 'b' * 16, 'op': 'http.client',
                      'start_timestamp': 100, 'timestamp': 101,
                      'tags': {'http.status_code': str(code), 'private': MARKER},
                      'data': {'http.response.status_code': code, 'http.url': MARKER}}]
    result = before_send_filter(value, {})
    assert result is not None
    assert result['spans'][0].get('tags') == {'http.status_code': str(code)}
    assert result['spans'][0]['data'] == {'http.response.status_code': code}
    assert MARKER not in json.dumps(result)


def test_legacy_child_span_keeps_fixed_status_name_tag():
    value = event()
    value['spans'] = [{'span_id': 'b' * 16, 'op': 'http.client',
                      'tags': {'status': 'invalid_argument', 'private': MARKER},
                      'data': {'http.response.status_code': 409}}]
    result = before_send_filter(value, {})
    assert result is not None
    assert result['spans'][0].get('tags') == {'status': 'invalid_argument'}
    assert MARKER not in json.dumps(result)


def test_legacy_numeric_status_data_remains_observable():
    value = event()
    value['spans'] = [{'data': {'http.status_code': 418, 'http.url': MARKER}}]
    result = before_send_filter(value, {})
    assert result is not None
    assert result['spans'][0].get('data') == {'http.status_code': 418}
    assert MARKER not in json.dumps(result)


def test_conflicting_status_aliases_are_refused():
    value = event()
    value['spans'] = [{'data': {'status_code': 200, 'http.response.status_code': 500}}]
    assert before_send_filter(value, {}) is None


@pytest.mark.parametrize('location', ['response', 'trace', 'span', 'event_tag', 'span_tag'])
@pytest.mark.parametrize('bad', [True, 200.0, 600, ' 200', MARKER])
def test_new_status_sources_refuse_invalid_metadata(location, bad):
    value = event()
    if location == 'response':
        value['contexts'] = {'response': {'status_code': bad}}
    elif location == 'trace':
        value['contexts'] = {'trace': {'data': {'http.status_code': bad}}}
    elif location == 'span':
        value['spans'] = [{'data': {'http.status_code': bad}}]
    elif location == 'event_tag':
        value['tags'] = {'http.status_code': bad}
    else:
        value['spans'] = [{'tags': {'http.status_code': bad}}]
    assert before_send_filter(value, {}) is None


def test_equal_status_aliases_and_private_neighbor_exclusion():
    value = event()
    value['contexts'] = {'response': {'status_code': 422, 'http.status_code': 422,
        'http.response.status_code': 422, 'headers': {'private': MARKER}}}
    value['tags'] = {'http.status_code': 422, 'status': MARKER, 'private': MARKER}
    result = before_send_filter(value, {})
    assert result['contexts']['response'] == {'status_code': 422, 'http.status_code': 422,
        'http.response.status_code': 422}
    assert result['tags'] == {'http.status_code': '422'}
    assert MARKER not in json.dumps(result)
