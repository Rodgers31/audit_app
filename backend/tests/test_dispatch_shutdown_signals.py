"""Real OS signals must not abort the supervisor's readiness cleanup.

Each signal experiment runs in its own process. Only lease/DB seams are inert;
main, serve, signal delivery and the final fenced readiness write are real.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


CHILD = r'''
import json,signal,sys,types
from contextlib import contextmanager
from uuid import uuid4
import admin_etl_dispatch_worker as worker
import admin_etl_dispatch_adapter as adapter

first,second,phase=sys.argv[1:]
generation=uuid4()
row=types.SimpleNamespace(generation=generation,ready=True)
commits=[]; calls=[]
class DB:
    def scalar(self,*a):return row
    def scalars(self,*a):return []
class Factory:
    @contextmanager
    def begin(self):
        yield DB()
        commits.append(row.ready)
factory=Factory()
sys.modules['database']=types.SimpleNamespace(SessionLocal=factory)
adapter.supported_registry=lambda:True
worker.enabled=lambda:True
def deliver(name):signal.raise_signal(getattr(signal,name))
def register(*a):
    if phase=='register':deliver(first)
    return generation
worker.register_worker=register
def claim(*a):
    calls.append('claim')
    if len(calls)>2:raise RuntimeError('shutdown was not observed')
    deliver(first)
    return None
worker.claim=claim
class Keeper:
    def __init__(self,**kw):pass
    def start(self):pass
    def join(self,**kw):deliver(second)
worker.threading.Thread=Keeper
def forbidden(*a,**kw):raise AssertionError('No command should start during stop')
worker.subprocess.Popen=forbidden
prior={s:signal.getsignal(s) for s in (signal.SIGINT,signal.SIGTERM)}
result=worker.main()
print(json.dumps({'exit':result,'ready':row.ready,'commits':commits,
    'handlers_restored':all(signal.getsignal(s)==h for s,h in prior.items()),
    'claim_calls':len(calls)}))
'''


@pytest.mark.parametrize('phase', ['register', 'idle'])
@pytest.mark.parametrize('first', ['SIGINT', 'SIGTERM'])
@pytest.mark.parametrize('second', ['SIGINT', 'SIGTERM'])
def test_repeated_shutdown_signals_preserve_readiness_commit(phase, first, second):
    backend = Path(__file__).resolve().parents[1]
    env = {'PATH': os.defpath, 'PYTHONPATH': str(backend),
           'PYTHON_DOTENV_DISABLED': '1', 'PYTHONDONTWRITEBYTECODE': '1',
           'DATABASE_URL': 'postgresql+psycopg2://inert:inert@127.0.0.1:1/inert'}
    run = subprocess.run([sys.executable, '-B', '-c', CHILD, first, second, phase],
                         cwd=backend, env=env, capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, 'Supervisor terminated before durable shutdown cleanup: ' + run.stderr[-500:]
    result = json.loads(run.stdout)
    assert result['exit'] == 0
    assert result['ready'] is False and result['commits'] == [False], result
    assert result['handlers_restored'] is True
    assert result['claim_calls'] == (0 if phase == 'register' else 1)
