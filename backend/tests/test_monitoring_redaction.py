"""Observable Sentry privacy regressions; all SDK transport is memory-only.

These verify local configuration/serialization, never deployed exporter safety.
"""
from copy import deepcopy
from datetime import datetime, timezone, tzinfo
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from monitoring.instrumentation import before_send_filter


MARKER = 'INERT-525-PRIVATE-MARKER'
EVENT_ID = 'a' * 32


def event():
    return {'event_id': EVENT_ID, 'level': 'error', 'timestamp': 1791475200.0,
            'exception': {'values': [{'type': 'RuntimeError', 'value': 'ordinary failure',
                'stacktrace': {'frames': [{'filename': 'worker.py', 'function': 'run', 'lineno': 12}]}}]}}


def test_ordinary_error_capture_remains_usable():
    result = before_send_filter(event(), {})
    assert result is not None
    assert result['event_id'] == EVENT_ID and result['level'] == 'error'
    assert result['exception']['values'][0]['type'] == 'RuntimeError'


@pytest.mark.parametrize('surface', ['request', 'headers', 'spans', 'breadcrumbs', 'frames', 'extra', 'text'])
def test_direct_event_excludes_private_containers_and_preserves_error_identity(surface):
    value = event()
    if surface == 'request':
        value['request'] = {'method': 'POST', 'url': 'https://example.test/callback?code=' + MARKER,
                            'query_string': 'signed_request=' + MARKER, 'data': {'code': MARKER}}
    elif surface == 'headers':
        value['request'] = {'headers': {'authorization': 'Bearer ' + MARKER,
                                       'cOoKiE': 'session=' + MARKER, 'x-private': MARKER}}
    elif surface == 'spans':
        value['spans'] = [{'op': 'http.client', 'span_id': 'a' * 16, 'trace_id': 'b' * 32,
                          'start_timestamp': 1791475199.0, 'timestamp': 1791475200.0,
                          'description': 'GET https://example.test/status?code=' + MARKER,
                          'data': {'http.url': 'https://example.test/status?code=' + MARKER}}]
    elif surface == 'breadcrumbs':
        value['breadcrumbs'] = {'values': [{'type': 'http', 'category': 'http',
            'message': 'callback?code=' + MARKER, 'data': {'url': 'https://example.test/?code=' + MARKER}}]}
    elif surface == 'frames':
        value['exception']['values'][0]['stacktrace']['frames'][0]['vars'] = {'private_bundle': MARKER}
        value['threads'] = {'values': [{'stacktrace': {'frames': [{'vars': {'keys': MARKER}}]}}]}
    elif surface == 'extra':
        value.update(extra={'private_bundle': MARKER}, user={'id': MARKER},
                     tags={'private': MARKER}, contexts={'private': {'value': MARKER}})
    else:
        value.update(message=MARKER, logentry={'message': MARKER, 'formatted': MARKER, 'params': [MARKER]})
        value['exception']['values'][0]['value'] = MARKER
    result = before_send_filter(deepcopy(value), {})
    assert result is not None, 'A usable operational error must still be captured'
    assert result['event_id'] == EVENT_ID and result['level'] == 'error'
    assert MARKER not in json.dumps(result)


@pytest.mark.parametrize('bad', [None, [], '', {'request': []}, {'exception': {'values': 'invalid'}}])
def test_direct_malformed_event_is_refused_without_unchanged_fallback(bad):
    assert before_send_filter(bad, {}) is None


def test_unsupported_timezone_is_refused_without_invoking_private_callback():
    class BadZone(tzinfo):
        def utcoffset(self, value):
            raise RuntimeError(MARKER)
    value = event()
    value['timestamp'] = datetime(2026, 10, 8, tzinfo=BadZone())
    assert before_send_filter(value, {}) is None


def test_unsupported_event_type_does_not_invoke_string_subclass_equality():
    class HostileText(str):
        def __eq__(self, other):
            raise RuntimeError(MARKER)
        def __ne__(self, other):
            raise RuntimeError(MARKER)
    value = event()
    value['type'] = HostileText('transaction')
    assert before_send_filter(value, {}) is None


def test_known_utc_datetime_preserves_operational_timestamp():
    value = event()
    value['timestamp'] = datetime(2026, 10, 8, tzinfo=timezone.utc)
    result = before_send_filter(value, {})
    assert result['timestamp'] == value['timestamp'].timestamp()


@pytest.mark.parametrize('entry', ['event', 'breadcrumb'])
def test_unsupported_object_does_not_invoke_class_property(entry):
    from monitoring.instrumentation import before_breadcrumb_filter
    class HostileClassProperty:
        @property
        def __class__(self):
            raise RuntimeError(MARKER)
    if entry == 'event':
        value = event()
        value['extra'] = {'private': HostileClassProperty()}
        assert before_send_filter(value, {}) is None
    else:
        assert before_breadcrumb_filter({'data': {'private': HostileClassProperty()}}, {}) is None


SDK_CAPTURE = r'''
import json, os, sys
import sentry_sdk
from sentry_sdk.transport import Transport
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from monitoring.instrumentation import setup_sentry

M='INERT-525-PRIVATE-MARKER'
sent=[]; lost=[]; item_types=[]
class MemoryTransport(Transport):
    def capture_envelope(self, envelope):
        for item in envelope.items:
            item_types.append(item.type)
            if item.type in ('event','transaction'):
                sent.append((item.type,item.payload.json))
    def record_lost_event(self, reason, data_category=None, item=None, quantity=1):
        lost.append((reason,data_category,quantity))

# Exercise the real setup function and its hooks/options. Only transport and
# explicit integrations needed for this isolated child are injected here.
real_init=sentry_sdk.init
def memory_init(*args,**kwargs):
    kwargs.update(transport=MemoryTransport(),default_integrations=False,
                  auto_enabling_integrations=False)
    kwargs['integrations'] += [HttpxIntegration(),StarletteIntegration(),LoggingIntegration()]
    return real_init(*args,**kwargs)
sentry_sdk.init=memory_init
app=FastAPI()
setup_sentry(app,dsn='https://fixture@example.invalid/1')
mode=sys.argv[1]
if mode=='inbound':
    from social.http_boundary import SocialRoute
    app.router.route_class=SocialRoute
    @app.get('/fixture/callback/{outcome}')
    def callback(outcome: str):
        if outcome=='failure': raise RuntimeError('ordinary failure')
        return {'accepted':True}
    with TestClient(app,raise_server_exceptions=False) as browser:
        for outcome,status in [('success',200),('failure',500)]:
            response=browser.get('/fixture/callback/'+outcome,
                params={'code':M,'access_token':M,'state':M,'error_description':M})
            assert response.status_code==status, 'Application outcome changed'
    sentry_sdk.capture_event({'level':'error','message':'ordinary operation failed',
        'request':{'method':'GET','url':'https://example.test/status?code='+M,
                   'query_string':'code='+M,'headers':{'authorization':'Bearer '+M}}})
elif mode=='forms':
    @app.post('/fixture/privacy/data-deletion/{outcome}')
    async def callback(outcome: str, request: Request):
        body=await request.body()
        assert body.count(M.encode())==2, 'The signed form did not reach the application'
        if outcome=='failure': raise RuntimeError('ordinary failure')
        return {'accepted':True}
    with TestClient(app,raise_server_exceptions=False) as browser:
        for outcome,status in [('success',200),('failure',500)]:
            response=browser.post('/fixture/privacy/data-deletion/'+outcome,
                data={'signed_request':M,'capability':M})
            assert response.status_code==status, 'Application outcome changed'
elif mode=='frames':
    from social.connections.crypto import CredentialCipher
    def rejected_key():
        private_bundle=M
        CredentialCipher('v1',{'v1':private_bundle+'é'})
    try:rejected_key()
    except Exception as error:sentry_sdk.capture_exception(error)
elif mode=='supplied':
    sentry_sdk.capture_event({'level':'error','message':M,
        'request':{'method':'POST','url':'https://example.test/callback?code='+M,
                   'query_string':'code='+M,'data':{'signed_request':M},
                   'headers':{'authorization':'Bearer '+M,'COOKIE':M}},
        'extra':{'private_bundle':M},'tags':{'private':M},'user':{'id':M},
        'exception':{'values':[{'type':'RuntimeError','value':M,'stacktrace':{'frames':[
            {'filename':'worker.py','function':'run','lineno':12,'vars':{'keyring':M}}]}}]},
        'threads':{'values':[{'stacktrace':{'frames':[{'vars':{'private':M}}]}}]}})
elif mode=='breadcrumb_span':
    sentry_sdk.add_breadcrumb(type='http',category='http',message='request?code='+M,
        data={'url':'https://example.test/?code='+M,'request_body':M,'status_code':200})
    with sentry_sdk.start_transaction(name='ordinary_operation') as transaction:
        with transaction.start_child(op='http.client',description='GET https://example.test/?code='+M) as span:
            span.set_data('http.url','https://example.test/?code='+M)
            span.set_data('http.query','code='+M)
            span.set_data('private_bundle',M)
            span.set_data('http.response.status_code',200)
    sentry_sdk.capture_message('ordinary operation failed',level='error')
elif mode=='status':
    for code in (200,418,422,500,503):
        with sentry_sdk.start_transaction(name='ordinary_operation',op='http.server') as transaction:
            transaction.set_http_status(code)
            transaction.set_tag('private',M)
            with transaction.start_child(op='http.client',description=M) as span:
                span.set_http_status(code)
                span.set_tag('private',M)
elif mode=='profile':
    import time
    namespace={'time':time}
    exec(compile('def run():\n for _ in range(12): time.sleep(0.025)\n',M+'.py','exec'),namespace)
    with sentry_sdk.start_transaction(name='ordinary_operation'):
        namespace['run']()
elif mode=='refusals':
    sentry_sdk.capture_event({'level':'error','request':[]})
    with sentry_sdk.start_transaction(name='ordinary_operation') as transaction:
        with transaction.start_child(op='http.client') as span:
            span.set_data('http.response.status_code',True)
    sentry_sdk.capture_message('ordinary operation failed',level='error')
else:raise AssertionError('Unsupported isolated capture')
sentry_sdk.flush()
events=[value for kind,value in sent if kind=='event']
transactions=[value for kind,value in sent if kind=='transaction']
print(json.dumps({'mode':mode,'event_count':len(events),'transaction_count':len(transactions),
    'private_marker_present':M in json.dumps(sent),
    'error_identity_preserved':all(value.get('event_id') and value.get('level')=='error' for value in events),
    'span_count':sum(len(value.get('spans',[])) for value in transactions),
    'response_codes':[value.get('contexts',{}).get('response',{}).get('status_code') for value in transactions],
    'transaction_status_tags':[value.get('tags',{}).get('http.status_code') for value in transactions],
    'child_status_codes':[span.get('data',{}).get('http.response.status_code')
                          for value in transactions for span in value.get('spans',[])],
    'child_status_tags':[span.get('tags',{}).get('http.status_code')
                         for value in transactions for span in value.get('spans',[])],
    'item_types':item_types,
    'drop_count':sum(item[2] for item in lost)}))
'''


def capture(mode):
    backend = Path(__file__).resolve().parents[1]
    environment = {'PATH': os.defpath, 'PYTHONPATH': str(backend), 'PYTHON_DOTENV_DISABLED': '1',
                   'SENTRY_TRACES_SAMPLE_RATE': '1.0', 'SENTRY_PROFILES_SAMPLE_RATE': '1.0'}
    result = subprocess.run([sys.executable, '-B', '-c', SDK_CAPTURE, mode],
                            cwd=backend, env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, 'Isolated memory capture failed; payload is never printed'
    return json.loads(result.stdout)


@pytest.mark.parametrize('mode,events,transactions', [
    ('inbound',1,2), ('forms',1,2), ('frames',1,0), ('supplied',1,0), ('breadcrumb_span',1,1),
])
def test_real_setup_sdk_excludes_markers_and_preserves_operational_captures(mode, events, transactions):
    result = capture(mode)
    assert result['event_count'] == events and result['transaction_count'] == transactions
    assert result['error_identity_preserved']
    if mode == 'breadcrumb_span': assert result['span_count'] == 1
    if mode in ('inbound', 'forms'): assert result['response_codes'] == [200,500]
    assert result['private_marker_present'] is False


def test_real_sdk_preserves_numeric_transaction_and_child_status():
    result = capture('status')
    codes = [200,418,422,500,503]
    assert result['event_count'] == 0 and result['transaction_count'] == result['span_count'] == len(codes)
    assert result['response_codes'] == result['child_status_codes'] == codes
    assert result['transaction_status_tags'] == result['child_status_tags'] == list(map(str, codes))
    assert result['private_marker_present'] is False


def test_configured_profile_channel_is_excluded_while_transaction_survives():
    result = capture('profile')
    assert result['transaction_count'] == 1 and result['event_count'] == 0
    assert result['item_types'] == ['transaction']
    assert result['private_marker_present'] is False


def test_real_sdk_records_refused_payload_loss_and_still_emits_healthy_error():
    result = capture('refusals')
    assert result['event_count'] == 1 and result['transaction_count'] == 0
    assert result['drop_count'] >= 2
    assert result['private_marker_present'] is False
