"""Actual subprocess/finite-protocol regressions; no DB or live Meta reads.

The owned peer replaces only the trusted script path in these fixtures. The
actual production run_child, execute, protocol and admission code still runs.
Separate PostgreSQL/API tests qualify durable service behavior.
"""
import base64
import ctypes
from dataclasses import replace
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from uuid import UUID

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from middleware.request_resources import request_deadline
from social.connections import verification_execution as execution
from social.connections import verification_protocol as protocol
from social.connections.config import MetaConfig
from social.connections.service import ConnectionService
from social.connections.verification import SavedGrantVerificationAuthority
from social.service import SocialError


PEER = Path(__file__).with_name('fixtures') / 'meta_verification_hostile_peer.py'
ACCOUNT = UUID('22222222-2222-4222-8222-222222222222')
ACTOR = UUID('11111111-1111-4111-8111-111111111111')
KEY = UUID('33333333-3333-4333-8333-333333333333')
REQUEST = UUID('44444444-4444-4444-8444-444444444444')
BODY = {'expected_controls_version': 1, 'expected_state': 'a' * 64,
    'reason': 'Owned subprocess boundary regression'}


@pytest.fixture
def process_boundary(tmp_path, monkeypatch):
    if sys.platform != 'linux':
        pytest.skip('Production verification processes require Linux kernel lifecycle guards')
    monkeypatch.setattr(execution, '_admission', threading.BoundedSemaphore(1))
    monkeypatch.setattr(execution, '_closure_failed', threading.Event())
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    processes = []
    original = execution.subprocess.Popen

    def start(*args, **kwargs):
        child = original(*args, **kwargs)
        processes.append(child)
        return child

    monkeypatch.setattr(execution.subprocess, 'Popen', start)

    def peer(mode):
        directory = tmp_path / mode
        directory.mkdir(exist_ok=True)
        path = directory / 'peer.py'
        path.write_bytes(PEER.read_bytes())
        monkeypatch.setattr(execution, 'ENTRYPOINT', path)
        return path

    try:
        yield peer, processes
    finally:
        for child in processes:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=2)
            for stream in (child.stdin, child.stdout):
                if stream is not None and not stream.closed:
                    stream.close()


@pytest.fixture
def command(process_boundary):
    peer, processes = process_boundary
    engine = create_engine('postgresql+psycopg2://fixture:fixture@127.0.0.1:9/fixture')
    config = MetaConfig(enabled=True, app_configuration_validated=True, app_id='123',
        app_secret='inert-fixture-material', access_mode='owned_standard',
        redirect_uris=('https://example.test/admin/social/accounts/callback',),
        active_key_version='v1', encryption_keys={'v1': base64.urlsafe_b64encode(b'x' * 32).decode()})

    def invoke(mode='good', authority='valid', *, allowance=.8, context=True):
        peer(mode)
        port = SavedGrantVerificationAuthority(config)
        if authority == 'missing':
            port = None
        elif authority == 'mismatch':
            port = SavedGrantVerificationAuthority(replace(config, app_id='456'))
        elif authority == 'transport':
            port = SavedGrantVerificationAuthority(config, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})))
        session = Session(engine)
        token = request_deadline.set(time.monotonic() + allowance + execution.CLEANUP_SECONDS if context else None)
        try:
            service = ConnectionService(session, config, verification_authority=port)
            return service.verify_existing_grant(ACCOUNT, ACTOR, 'c' * 64,
                f'POST /api/v1/admin/social/accounts/{ACCOUNT}/verify-publishing-access', KEY, BODY, REQUEST)
        finally:
            request_deadline.reset(token)
            session.close()

    try:
        yield invoke, processes
    finally:
        engine.dispose()


def test_public_service_uses_real_subprocess_and_bound_success(command):
    invoke, processes = command
    value = invoke()
    assert len(processes) == 1 and processes[0].returncode == 0
    assert value['account_id'] == str(ACCOUNT)
    assert value['publishing_enabled'] is False
    assert value['controls_version'] == 2 and value['state_token'] != BODY['expected_state']


@pytest.mark.parametrize('mode', ['malformed', 'duplicate', 'nonfinite', 'bool_version',
    'wrong_nonce', 'wrong_hash', 'wrong_account', 'enabled', 'old_controls',
    'trailing', 'oversize', 'nonzero', 'no_eof', 'stdout_closed', 'late', 'ignore_term'])
def test_hostile_or_unfinished_child_never_confirms_command(mode, command):
    invoke, processes = command
    with pytest.raises(SocialError) as caught:
        invoke(mode)
    assert caught.value.code == 'GRANT_VERIFICATION_UNCONFIRMED'
    assert caught.value.retryable is False
    assert len(processes) == 1 and processes[0].poll() is not None


@pytest.mark.parametrize('authority', ['missing', 'mismatch', 'transport'])
def test_missing_or_unserializable_authority_refuses_before_spawn(authority, command):
    invoke, processes = command
    with pytest.raises(SocialError) as caught:
        invoke(authority=authority)
    assert caught.value.code == 'GRANT_VERIFICATION_UNAVAILABLE'
    assert not processes


def test_original_state_token_cannot_confirm_a_new_proof(command):
    invoke, _ = command
    with pytest.raises(SocialError) as caught:
        invoke('unchanged_state')
    assert caught.value.code == 'GRANT_VERIFICATION_UNCONFIRMED'


@pytest.mark.parametrize('mode,status', [('error_privacy_409', 409), ('error_privacy_503', 503)])
def test_known_refusal_preserves_its_original_status_with_static_message(mode, status, command):
    invoke, processes = command
    with pytest.raises(SocialError) as caught:
        invoke(mode)
    assert caught.value.code == 'PRIVACY_GRANT_BLOCKED'
    assert caught.value.status == status and caught.value.retryable is False
    assert 'UNTRUSTED_PRIVATE_CHILD_MESSAGE' not in caught.value.message
    assert processes[0].returncode == 0


@pytest.mark.parametrize('mode', ['error_bool_status', 'error_float_status', 'error_string_status',
    'error_unknown_pair', 'error_unknown_code', 'error_child_message', 'error_missing_status'])
def test_child_cannot_supply_an_arbitrary_status_or_message(mode, command):
    invoke, processes = command
    with pytest.raises(SocialError) as caught:
        invoke(mode)
    assert caught.value.code == 'GRANT_VERIFICATION_UNCONFIRMED'
    assert 'UNTRUSTED_PRIVATE_CHILD_MESSAGE' not in caught.value.message
    assert processes[0].returncode == 0


@pytest.mark.parametrize('stage', ['model_validate', 'model_dump'])
def test_result_finishing_after_deadline_is_unconfirmed(stage, command, monkeypatch):
    clock = {'offset': 0.0}
    monkeypatch.setattr(execution, 'monotonic', lambda: time.monotonic() + clock['offset'])
    if stage == 'model_validate':
        original = execution.AccountPublishingDTO.model_validate

        def finish_late(cls, *args, **kwargs):
            value = original(*args, **kwargs)
            clock['offset'] = 21.0
            return value

        monkeypatch.setattr(execution.AccountPublishingDTO, stage, classmethod(finish_late))
    else:
        original = execution.AccountPublishingDTO.model_dump

        def finish_late(self, *args, **kwargs):
            value = original(self, *args, **kwargs)
            clock['offset'] = 21.0
            return value

        monkeypatch.setattr(execution.AccountPublishingDTO, stage, finish_late)
    invoke, _ = command
    with pytest.raises(SocialError) as caught:
        invoke(context=False)
    assert caught.value.code == 'GRANT_VERIFICATION_UNCONFIRMED'


@pytest.mark.parametrize('number', ['NaN', 'Infinity', '-Infinity', '1e9999', '-1e9999'])
def test_nested_nonfinite_json_is_refused(number):
    with pytest.raises(ValueError):
        protocol.decode(('{"nested":{"number":' + number + '}}').encode())


def test_duplicate_nested_protocol_keys_are_refused():
    with pytest.raises(ValueError):
        protocol.decode(b'{"nested":{"version":1,"version":1}}')


def test_child_inherits_neither_ambient_secret_nor_dotenv_configuration(process_boundary, monkeypatch):
    peer, processes = process_boundary
    path = peer('environment')
    path.with_name('.env').write_text('META_EXECUTOR_DOTENV=owned-sentinel\n')
    monkeypatch.setenv('META_EXECUTOR_TOY_SECRET', 'must-not-cross')
    value = json.loads(execution.run_child({}, time.monotonic() + .8))
    assert value == {'inherited_secret': False, 'dotenv_loaded': False}
    assert processes[0].returncode == 0


def test_explicitly_inheritable_parent_descriptor_stays_closed(process_boundary, tmp_path):
    peer, processes = process_boundary
    peer('descriptor')
    with (tmp_path / 'descriptor-sentinel').open('w') as stream:
        os.set_inheritable(stream.fileno(), True)
        value = json.loads(execution.run_child({'fd': stream.fileno()}, time.monotonic() + .8))
    assert value == {'inherited': False}
    assert processes[0].returncode == 0


def test_blocked_stdin_is_bounded_and_child_reaped(process_boundary):
    peer, processes = process_boundary
    peer('stdin_stall')
    with pytest.raises(SocialError) as caught:
        execution.run_child({'padding': 'x' * 100000}, time.monotonic() + .3)
    assert caught.value.code == 'GRANT_VERIFICATION_UNCONFIRMED'
    assert processes[0].poll() is not None


def test_cleanup_interruption_still_closes_pipes_and_holds_admission(process_boundary, monkeypatch):
    peer, processes = process_boundary
    peer('ignore_term')
    original = execution._reap

    def interrupt(child, *, kill):
        original(child, kill=kill)
        raise KeyboardInterrupt('owned fixture cleanup interruption')

    monkeypatch.setattr(execution, '_reap', interrupt)
    with pytest.raises((SocialError, KeyboardInterrupt)):
        execution.run_child({}, time.monotonic() + .2)
    assert processes[0].poll() is not None
    assert processes[0].stdin.closed and processes[0].stdout.closed
    assert execution._closure_failed.is_set()
    assert not execution._admission.acquire(blocking=False)


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux process-group/subreaper contract')
def test_exited_leader_cannot_leave_a_live_descendant_and_free_admission(process_boundary):
    peer, processes = process_boundary
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    identities = None
    try:
        path = peer('descendant')
        with pytest.raises(SocialError) as caught:
            execution.run_child({}, time.monotonic() + .8)
        assert caught.value.code == 'GRANT_VERIFICATION_UNCONFIRMED'
        identities = json.loads(path.with_name('descendant.json').read_text())
        assert identities['leader'] == identities['pgid'] == processes[0].pid
        status_path = Path('/proc') / str(identities['descendant']) / 'stat'
        status = status_path.read_text().rsplit(')', 1)[1].split()[0] if status_path.exists() else None
        available = execution._admission.acquire(blocking=False)
        if available:
            execution._admission.release()
        assert not (status not in (None, 'Z') and available)
        assert execution._closure_failed.is_set() or execution._group_gone(processes[0])
    finally:
        try:
            if identities is None and 'path' in locals() and path.with_name('descendant.json').exists():
                identities = json.loads(path.with_name('descendant.json').read_text())
            if identities is not None:
                assert identities['pgid'] == processes[0].pid
                try:
                    os.killpg(identities['pgid'], signal.SIGKILL)
                except ProcessLookupError:
                    pass
                until = time.monotonic() + 2
                while True:
                    try:
                        pid, _ = os.waitpid(identities['descendant'], os.WNOHANG)
                    except ChildProcessError:
                        assert not (Path('/proc') / str(identities['descendant'])).exists()
                        break
                    if pid == identities['descendant']:
                        break
                    assert time.monotonic() < until, 'owned descendant was not positively reaped'
                    time.sleep(.01)
        finally:
            assert libc.prctl(36, previous.value, 0, 0, 0) == 0
