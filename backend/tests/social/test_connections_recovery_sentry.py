"""Actual local frame exclusion evidence for #525; all transport/material inert.

These captures establish no deployed activation/exporter protection.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

CAPTURE = r"""
import base64,json
from uuid import UUID
import sentry_sdk
from sentry_sdk.transport import Transport
from monitoring.instrumentation import setup_sentry
from fastapi import FastAPI
from social.connections.crypto import CredentialCipher
from social.connections.recovery import parse_keyring, RecoveryKeyring,RecoveryProbe,verify_restoration
K=base64.urlsafe_b64encode(bytes(range(32))).decode()
M='INERT-SENTRY-CRYPTO-PRIVATE-MARKER'
O=UUID('77777777-7777-4777-8777-777777777777')
sent=[]
class T(Transport):
    def capture_envelope(self,envelope):
        for item in envelope.items:
            if item.type=='event':sent.append(item.payload.json)
sentry_sdk.init(dsn='https://fixture@example.invalid/1',transport=T(),default_integrations=False,auto_enabling_integrations=False)
sentry_sdk.capture_event({'message':'unsafe positive control','extra':{'private':M if 'M' in globals() else K}})
sentry_sdk.flush();assert len(sent)==1 and (M if 'M' in globals() else K) in json.dumps(sent.pop())
real_init=sentry_sdk.init
def memory_init(*args,**kwargs):
    kwargs.update(transport=T(),default_integrations=False,auto_enabling_integrations=False)
    return real_init(*args,**kwargs)
sentry_sdk.init=memory_init
setup_sentry(FastAPI(),dsn='https://fixture@example.invalid/1')
def bad_key():CredentialCipher('v1',{'v1':M+'é'})
def owner_mismatch():
    c=CredentialCipher('v1',{'v1':K});v,data=c.encrypt(O,'facebook_page',{'access_token':M})
    c.decrypt(UUID('88888888-8888-4888-8888-888888888888'),'facebook_page',v,data)
def unknown_version():
    c=CredentialCipher('v1',{'v1':K});c.decrypt(O,'facebook_page',M,b'corrupt')
def malformed_backup():parse_keyring(('{"marker":"'+M+'"').encode())
def recovery_owner_mismatch():
    a=RecoveryKeyring('v1',{'v1':K});v,data=a.cipher().encrypt(O,'facebook_page',{'access_token':M})
    verify_restoration(a,RecoveryKeyring('v1',{'v1':K}),[RecoveryProbe(UUID('88888888-8888-4888-8888-888888888888'),'facebook_page',v,data)])
summary=[]
for fn in [bad_key,owner_mismatch,unknown_version,malformed_backup,recovery_owner_mismatch]:
    try:fn()
    except Exception as ex:sentry_sdk.capture_exception(ex)
    sentry_sdk.flush()
    assert len(sent)==1, 'missing capture positive control'
    event=sent.pop()
    frames=[f for exc in event['exception']['values'] for f in exc.get('stacktrace',{}).get('frames',[]) if f.get('filename','').endswith(('social/connections/crypto.py','social/connections/recovery.py'))]
    encoded=json.dumps(frames)
    paths=[]
    for frame in frames:
        for key,value in frame.get('vars',{}).items():
            if M in json.dumps(value):paths.append(frame['filename']+':'+frame['function']+':vars.'+key)
    assert M not in json.dumps(event), 'private marker outside owned frames'
    summary.append({'mode':fn.__name__,'crypto_recovery_frame_marker_present':M in encoded,'frame_marker_paths':paths,'event_count':1})
print(json.dumps(summary))
"""

PERSIST_CAPTURE = r"""
import base64,json,pathlib,tempfile
from unittest.mock import patch
import sentry_sdk
from sentry_sdk.transport import Transport
from monitoring.instrumentation import setup_sentry
from fastapi import FastAPI
from social.connections.recovery import RecoveryKeyring,encode_keyring,write_keyring_backup
K=base64.urlsafe_b64encode(bytes(range(32))).decode();sent=[]
class T(Transport):
    def capture_envelope(self,envelope):
        for item in envelope.items:
            if item.type=='event':sent.append(item.payload.json)
sentry_sdk.init(dsn='https://fixture@example.invalid/1',transport=T(),default_integrations=False,auto_enabling_integrations=False)
sentry_sdk.capture_event({'message':'unsafe positive control','extra':{'private':M if 'M' in globals() else K}})
sentry_sdk.flush();assert len(sent)==1 and (M if 'M' in globals() else K) in json.dumps(sent.pop())
real_init=sentry_sdk.init
def memory_init(*args,**kwargs):
    kwargs.update(transport=T(),default_integrations=False,auto_enabling_integrations=False)
    return real_init(*args,**kwargs)
sentry_sdk.init=memory_init
setup_sentry(FastAPI(),dsn='https://fixture@example.invalid/1')
summary=[]
for mode in ['failed-fsync','encode-oversize']:
    try:
        if mode=='failed-fsync':
            with tempfile.TemporaryDirectory(prefix='adversarial-recovery-capture-') as d:
                with patch('os.fsync',side_effect=OSError('INERT-FAILURE')):
                    write_keyring_backup(pathlib.Path(d)/'backup',RecoveryKeyring('v1',{'v1':K}))
        else:encode_keyring(RecoveryKeyring('v1',{'v1':K,**{str(i):K for i in range(65)}}))
    except Exception as ex:sentry_sdk.capture_exception(ex)
    sentry_sdk.flush();assert len(sent)==1
    event=sent.pop();paths=[]
    for exc in event['exception']['values']:
        for f in exc.get('stacktrace',{}).get('frames',[]):
            if f.get('filename','').endswith('social/connections/recovery.py'):
                for name,value in f.get('vars',{}).items():
                    if K in json.dumps(value):paths.append(f['filename']+':'+f['function']+':vars.'+name)
    assert K not in json.dumps(event), 'private key outside owned frames'
    summary.append({'mode':mode,'credential_key_in_capture':bool(paths),'paths':paths,'event_count':1})
print(json.dumps(summary))
"""

def capture(source):
    backend = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, '-B', '-c', source], cwd=backend,
        env={'PATH': os.defpath, 'PYTHONPATH': str(backend), 'PYTHON_DOTENV_DISABLED': '1'},
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, 'Memory-only frame capture failed; captured payload is never printed'
    return json.loads(result.stdout)


def test_recovery_sentry_setup_excludes_owned_and_caller_frame_locals():
    evidence = capture(CAPTURE)
    assert len(evidence) == 5 and all(item['event_count'] == 1 for item in evidence)
    assert [item['crypto_recovery_frame_marker_present'] for item in evidence] == [False, False, False, False, False]


def test_recovery_failed_export_sentry_setup_excludes_raw_key_locals():
    evidence = capture(PERSIST_CAPTURE)
    assert len(evidence) == 2 and all(item['event_count'] == 1 for item in evidence)
    assert [item['credential_key_in_capture'] for item in evidence] == [False, False]
