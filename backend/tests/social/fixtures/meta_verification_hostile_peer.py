"""Owned subprocess peer for executor boundary tests; no app or provider calls.

Tests copy this file into an owned directory whose name selects one scenario.
Production protocol input has no path, mode or transport selector.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    mode = Path(__file__).parent.name
    if mode == 'stdin_stall':
        time.sleep(30)
    value = json.loads(sys.stdin.buffer.read())
    if mode == 'environment':
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).with_name('.env'))
        print(json.dumps({'inherited_secret': 'META_EXECUTOR_TOY_SECRET' in os.environ,
            'dotenv_loaded': os.environ.get('META_EXECUTOR_DOTENV') == 'owned-sentinel'}), flush=True)
        return 0
    if mode == 'descriptor':
        try:
            os.fstat(value['fd'])
        except OSError:
            inherited = False
        else:
            inherited = True
        print(json.dumps({'inherited': inherited}), flush=True)
        return 0
    if mode == 'descendant':
        child = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import time; time.sleep(30)'],
            stdout=sys.stdout, stderr=subprocess.DEVNULL, close_fds=True)
        Path(__file__).with_name('descendant.json').write_text(json.dumps({
            'leader': os.getpid(), 'pgid': os.getpgrp(), 'descendant': child.pid}))
        return 0
    command = value.get('command', {})
    body = command.get('body', {})
    result = {'account_id': command.get('account_id'), 'publishing_enabled': False,
        'controls_version': body.get('expected_controls_version', 1) + 1,
        'state_token': 'b' * 64, 'enable_available': False, 'enable_blockers': [],
        'global_publishing_enabled': False, 'delivery_holds': []}
    response = {'version': 1, 'nonce': value.get('nonce'),
        'command_hash': hashlib.sha256(json.dumps(command, allow_nan=False, separators=(',', ':')).encode()).hexdigest(),
        'kind': 'success', 'value': result}
    if mode.startswith('error_'):
        response.pop('value')
        response.update(kind='error', code='PRIVACY_GRANT_BLOCKED', status=503)
        if mode == 'error_privacy_409':
            response['status'] = 409
        elif mode == 'error_bool_status':
            response['status'] = True
        elif mode == 'error_float_status':
            response['status'] = 503.0
        elif mode == 'error_string_status':
            response['status'] = '503'
        elif mode == 'error_unknown_pair':
            response['status'] = 418
        elif mode == 'error_unknown_code':
            response['code'] = 'UNTRUSTED_CHILD_CODE'
        elif mode == 'error_child_message':
            response['message'] = 'UNTRUSTED_PRIVATE_CHILD_MESSAGE'
        elif mode == 'error_missing_status':
            response.pop('status')
    if mode == 'unchanged_state':
        result['state_token'] = body['expected_state']
    elif mode == 'wrong_nonce':
        response['nonce'] = 'x' * 64
    elif mode == 'wrong_hash':
        response['command_hash'] = 'x' * 64
    elif mode == 'bool_version':
        response['version'] = True
    elif mode == 'enabled':
        result['publishing_enabled'] = True
    elif mode == 'old_controls':
        result['controls_version'] -= 1
    elif mode == 'wrong_account':
        result['account_id'] = '00000000-0000-0000-0000-000000000002'
    encoded = json.dumps(response)
    if mode == 'duplicate':
        encoded = encoded.replace('"version": 1', '"version": 1,"version": 1')
    elif mode == 'nonfinite':
        encoded = encoded.replace('"controls_version": 2', '"controls_version": NaN')
    elif mode == 'malformed':
        encoded = '{"version":'
    elif mode == 'trailing':
        encoded += '{}'
    elif mode == 'oversize':
        encoded = 'x' * 262144
    if mode == 'ignore_term':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(30)
    elif mode == 'late':
        time.sleep(2)
    print(encoded, flush=True)
    if mode == 'no_eof':
        time.sleep(30)
    elif mode == 'stdout_closed':
        os.close(1)
        time.sleep(30)
    elif mode == 'nonzero':
        return 7
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
