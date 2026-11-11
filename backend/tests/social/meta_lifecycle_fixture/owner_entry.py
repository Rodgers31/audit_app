"""Actual production main with explicit inert input/DNS phase witnesses."""
import ctypes
import json
import os
from pathlib import Path
import signal
import socket
import sys
import types

APP_ROOT = globals().get('APP_ROOT')
PHASE_DIRECTORY = globals().get('PHASE_DIRECTORY')
if type(APP_ROOT) is not str or type(PHASE_DIRECTORY) is not str:
    raise ValueError('Owned fixture bootstrap required')
sys.path.insert(0, APP_ROOT)
os.environ['DATABASE_URL'] = 'postgresql+psycopg2://inert@127.0.0.1:9/inert'
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
from social.connections.verification_process import main
directory = Path(PHASE_DIRECTORY)
mode = directory.name
marker = directory / 'phase.json'
def publish(value):
    temporary = marker.with_suffix('.tmp')
    temporary.write_text(json.dumps(value))
    temporary.replace(marker)

if mode == 'input':
    original_stdin = sys.stdin
    class Input:
        def read(self, size):
            observed = ctypes.c_int()
            libc = ctypes.CDLL(None)
            libc.prctl(2, ctypes.byref(observed), 0, 0, 0)
            publish({'pid': os.getpid(), 'pgid': os.getpgrp(),
                'parent': os.getppid(), 'phase': 'actual main stdin.buffer.read',
                'alarm_seconds': signal.getitimer(signal.ITIMER_REAL)[0],
                'parent_death_signal': observed.value})
            return original_stdin.buffer.read(size)
    sys.stdin = types.SimpleNamespace(buffer=Input())
else:
    from social.connections.service import ConnectionService
    from social.connections.provider import MetaProvider
    from social.connections.verification_budget import current_budget
    def resolver(*args, **kwargs):
        observed = ctypes.c_int()
        ctypes.CDLL(None).prctl(2, ctypes.byref(observed), 0, 0, 0)
        publish({'pid': os.getpid(), 'pgid': os.getpgrp(),
            'parent': os.getppid(), 'phase': 'actual MetaProvider DNS resolver',
            'deadline': current_budget.get().deadline,
            'alarm_seconds': signal.getitimer(signal.ITIMER_REAL)[0],
            'parent_death_signal': observed.value})
        signal.pause()
        raise RuntimeError('fixture resolver must never reach network')
    def body(self, *args):
        socket.getaddrinfo = resolver
        provider = MetaProvider(self.config)
        try: return provider._request('GET', 'me', token='inert-fixture-token')
        finally: provider.close()
    ConnectionService._verify_existing_grant = body
raise SystemExit(main())
