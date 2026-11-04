"""Actual clean-process startup refusals, with only inert explicit configuration."""
import os
import subprocess
import sys

import pytest


def child(script, **overrides):
    names = ('PATH','HOME','TMPDIR','XDG_CACHE_HOME','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONOPTIMIZE',
             'ENVIRONMENT','SECRET_BACKEND','SECRET_KEY','SUPABASE_URL','DATABASE_URL',
             'REDIS_URL','AUTO_SEED_ENABLED','AUTO_SEEDER_ENABLED','AWS_EC2_METADATA_DISABLED')
    env = {name:os.environ[name] for name in names if name in os.environ}
    env.update(overrides)
    env.pop('PYTHONOPTIMIZE', None)
    optimization = ['-' + 'O' * sys.flags.optimize] if sys.flags.optimize else []
    return subprocess.run([sys.executable,*optimization,'-c',script],env=env,text=True,capture_output=True,timeout=15)


def test_ordinary_startup_retains_required_security_layers():
    result = child("""import main
names={m.cls.__name__ for m in main.app.user_middleware}
missing={'RateLimitMiddleware','AuditLogMiddleware','SecurityHeadersMiddleware','RequestResourceMiddleware'}-names
if missing: raise SystemExit('REQUIRED_SECURITY_MISSING:'+','.join(sorted(missing)))
print('REQUIRED_SECURITY_PRESENT')
""",WEB_CONCURRENCY='1')
    assert result.returncode == 0,result.stdout+result.stderr
    assert 'REQUIRED_SECURITY_PRESENT' in result.stdout


@pytest.mark.parametrize('failure', ['import','registration'])
def test_required_security_failure_stops_actual_application_startup(failure):
    setup = """import builtins
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if name=='middleware.security': raise RuntimeError('INERT_SECURITY_SETUP_FAILURE')
    return original(name,*args,**kwargs)
builtins.__import__=guarded
""" if failure == 'import' else """from fastapi import FastAPI
original=FastAPI.add_middleware
def guarded(self,cls,*args,**kwargs):
    if cls.__module__.startswith('middleware.'):
        raise RuntimeError('INERT_SECURITY_SETUP_FAILURE')
    return original(self,cls,*args,**kwargs)
FastAPI.add_middleware=guarded
"""
    result = child(setup+"""
try:
    import main
except RuntimeError as error:
    if str(error)!='INERT_SECURITY_SETUP_FAILURE': raise
    print('REQUIRED_SECURITY_STARTUP_REFUSED')
else:
    raise SystemExit('REQUIRED_SECURITY_STARTUP_WAS_ACCEPTED')
""",WEB_CONCURRENCY='1')
    assert result.returncode == 0,result.stdout+result.stderr
    assert 'REQUIRED_SECURITY_STARTUP_REFUSED' in result.stdout


def test_unqualified_worker_count_is_rejected_explicitly():
    result = child("""
try:
    import main
except RuntimeError as error:
    if 'Single-worker request admission' not in str(error): raise
    print('MULTIWORKER_ADMISSION_REFUSED')
else:
    raise SystemExit('MULTIWORKER_STARTUP_WAS_ACCEPTED')
""",WEB_CONCURRENCY='2')
    assert result.returncode == 0,result.stdout+result.stderr
    assert 'MULTIWORKER_ADMISSION_REFUSED' in result.stdout


def test_local_rate_budgets_reset_on_real_process_restart():
    script = """import asyncio
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse
from middleware.security import RateLimitMiddleware
async def run():
    limiter=RateLimitMiddleware(FastAPI(),calls=2,period=60)
    request=Request({'type':'http','path':'/x','method':'GET','headers':[],'client':('192.0.2.1',1)})
    async def accepted(request): return JSONResponse({'ok':True})
    values=[(await limiter.dispatch(request,accepted)).status_code for _ in range(3)]
    if values != [200,200,429]:
        raise SystemExit('LOCAL_RATE_SEQUENCE_INVALID:'+','.join(map(str,values)))
    print('LOCAL_BUDGET_NEW_PROCESS_200_200_429')
asyncio.run(run())
"""
    for _ in range(2):
        result=child(script)
        assert result.returncode == 0,result.stdout+result.stderr
        assert 'LOCAL_BUDGET_NEW_PROCESS_200_200_429' in result.stdout


@pytest.mark.parametrize('missing', ['RateLimitMiddleware', 'AuditLogMiddleware',
                                     'SecurityHeadersMiddleware', 'RequestResourceMiddleware'])
def test_startup_probe_rejects_each_missing_required_layer(monkeypatch, missing):
    original = child
    prefix = f"""from fastapi import FastAPI
add = FastAPI.add_middleware
def omit(self, cls, *args, **kwargs):
    if cls.__name__ != {missing!r}:
        return add(self, cls, *args, **kwargs)
FastAPI.add_middleware = omit
"""
    monkeypatch.setitem(globals(), 'child', lambda script, **overrides: original(prefix + script, **overrides))
    with pytest.raises(AssertionError, match='REQUIRED_SECURITY_MISSING:' + missing):
        test_ordinary_startup_retains_required_security_layers()


def test_restart_probe_rejects_a_limiter_that_never_refuses(monkeypatch):
    original = child
    prefix = """from middleware.security import RateLimitMiddleware
async def always_allow(self, request, call_next):
    return await call_next(request)
RateLimitMiddleware.dispatch = always_allow
"""
    monkeypatch.setitem(globals(), 'child', lambda script, **overrides: original(prefix + script, **overrides))
    with pytest.raises(AssertionError, match='LOCAL_RATE_SEQUENCE_INVALID:200,200,200'):
        test_local_rate_budgets_reset_on_real_process_restart()


def test_child_preserves_interpreter_optimization_without_ambient_flag(monkeypatch):
    monkeypatch.delenv('PYTHONOPTIMIZE', raising=False)
    result = child('import sys; print(sys.flags.optimize)')
    assert result.returncode == 0
    assert result.stdout.strip() == str(sys.flags.optimize)
