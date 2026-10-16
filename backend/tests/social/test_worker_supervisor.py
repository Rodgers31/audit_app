"""Actual stdlib subprocesses, signals, fixed argv and default-off exec."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest
import social_worker_supervisor as supervisor


def test_off_execs_exact_web_without_children_or_worker_import(monkeypatch):
    expected = ['gunicorn','main:app','--worker-class','uvicorn.workers.UvicornWorker','--bind','0.0.0.0:10000',
                '--access-logfile','-','--error-logfile','-','--log-level','info','--timeout','120','--keep-alive','5',
                '--max-requests','1000','--max-requests-jitter','100']
    class Exec(BaseException): pass
    calls = []
    monkeypatch.setattr(os, 'execvp', lambda *args: calls.append(args) or (_ for _ in ()).throw(Exec()))
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('OFF spawned child'))
    monkeypatch.setenv('PORT', '10000')
    monkeypatch.delenv('SOCIAL_WORKER_SUPERVISOR_ENABLED', raising=False)
    with pytest.raises(Exec): supervisor.main()
    assert calls == [('gunicorn', expected)]
    monkeypatch.undo()
    # A fresh interpreter has no SQLAlchemy/SDK/application modules from import.
    result = subprocess.run([sys.executable,'-c',"import sys,social_worker_supervisor; assert not any(x.startswith(('sqlalchemy','social.worker','httpx','boto')) for x in sys.modules)"],
                            env={**os.environ,'PYTHONPATH':str(Path(supervisor.__file__).parent)}, capture_output=True)
    assert result.returncode == 0, result.stderr.decode()


def test_fixed_child_argv_contains_env_reference_and_no_dsn():
    secret = 'postgresql://worker:PRIVATE_SECRET@localhost/fixture'
    env = dict(SOCIAL_WORKER_DATABASE_URL=secret, SOCIAL_WORKER_ROLE='restricted_worker', WEB_CONCURRENCY='9')
    argv = supervisor.worker_command(env, 8)
    assert secret not in ' '.join(argv) and 'PRIVATE_SECRET' not in ' '.join(argv)
    assert argv[:4] == [sys.executable, '-m', 'social.worker', '--native-meta']
    assert argv[argv.index('--database-url-env')+1] == 'SOCIAL_WORKER_DATABASE_URL'


@pytest.mark.parametrize('flag', ['TRUE','1','',True])
def test_supervisor_flag_is_strict(flag):
    with pytest.raises(ValueError): supervisor.settings({'SOCIAL_WORKER_SUPERVISOR_ENABLED':flag})


def launch(tmp_path, *, web_exit=False, worker_exit=False, hang=False):
    child = tmp_path / 'child.py'
    child.write_text('''import os,signal,sys,time
name,folder,mode=sys.argv[1:]
open(folder+'/'+name+'.pid','w').write(str(os.getpid()))
def stop(sig,frame):
    if mode!='hang':
        open(folder+'/'+name+'.closed','w').write('closed')
        sys.exit(0)
signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)
if mode=='exit': sys.exit(7)
while True: time.sleep(.02)
''')
    script = '''import sys
from social_worker_supervisor import supervise
child,folder,wm,sm=sys.argv[1:]
raise SystemExit(supervise([sys.executable,child,'web',folder,wm],lambda fd:[sys.executable,child,'worker',folder,sm],1))
'''
    proc = subprocess.Popen([sys.executable,'-c',script,str(child),str(tmp_path), 'exit' if web_exit else 'wait',
                             'exit' if worker_exit else 'hang' if hang else 'wait'],
                            env={**os.environ,'PYTHONPATH':str(Path(supervisor.__file__).parent)}, stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    deadline = time.monotonic()+8
    while time.monotonic()<deadline:
        if (tmp_path/'worker.pid').exists() and (tmp_path/'web.pid').exists(): return proc
        if proc.poll() is not None: break
        time.sleep(.01)
    out,err=proc.communicate(timeout=5)
    pytest.fail(f'Children did not start: {out} {err}')


def assert_gone(tmp_path):
    for file in tmp_path.glob('*.pid'):
        with pytest.raises(ProcessLookupError): os.kill(int(file.read_text()),0)


def test_repeated_signals_drain_and_reap_only_owned_children(tmp_path):
    proc=launch(tmp_path)
    try:
        for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGTERM): proc.send_signal(sig)
        out,err=proc.communicate(timeout=8)
        assert proc.returncode == 0, out+err
        assert (tmp_path/'worker.closed').exists() and (tmp_path/'web.closed').exists()
        assert '"release_proof":null' in out  # Exit/signalling alone is never proof.
        assert_gone(tmp_path)
    finally:
        if proc.poll() is None: proc.kill();proc.wait()


def test_worker_failure_leaves_web_available_and_never_restarts(tmp_path):
    proc=launch(tmp_path,worker_exit=True)
    try:
        time.sleep(.2)
        assert proc.poll() is None and not (tmp_path/'web.closed').exists()
        proc.terminate();out,err=proc.communicate(timeout=8)
        assert 'social_worker_unavailable' in out and '"exit_code":7' in out
        assert out.count('social_supervisor_started') == 1
        assert_gone(tmp_path)
    finally:
        if proc.poll() is None: proc.kill();proc.wait()


def test_web_failure_stops_worker_and_exits_nonzero(tmp_path):
    proc=launch(tmp_path,web_exit=True)
    out,err=proc.communicate(timeout=8)
    assert proc.returncode == 1, out+err
    assert (tmp_path/'worker.closed').exists()
    assert_gone(tmp_path)


def test_deadline_kill_retains_holds_and_never_claims_clean_completion(tmp_path):
    proc=launch(tmp_path,hang=True)
    proc.terminate();out,err=proc.communicate(timeout=8)
    assert proc.returncode == 1, out+err
    assert '"deadline_kill":true' in out and '"release_proof":null' in out
    assert '"ownership_retained":true' in out
    assert not (tmp_path/'worker.closed').exists()
    assert_gone(tmp_path)


@pytest.mark.parametrize('field,value', [('version',True),('owner_id',123),('owner_id',None),('generation',True),('extra','PRIVATE_RECEIPT_SECRET')])
def test_malformed_closure_receipt_keeps_web_alive_without_release_proof(tmp_path,field,value):
    import uuid
    proof=dict(version=1,owner_id=str(uuid.uuid4()),generation=1,providers_closed=True,executor_closed=True,claims_drained=True)
    proof[field]=value
    script='''import os,sys
from social_worker_supervisor import supervise
proof,folder=sys.argv[1:]
web=[sys.executable,'-c','import time; time.sleep(60)']
def worker(fd):
 return [sys.executable,'-c','import os,sys;os.write(int(sys.argv[1]),sys.argv[2].encode())',str(fd),proof]
raise SystemExit(supervise(web,worker,1))
'''
    log=tmp_path/'supervisor.log'
    with log.open('w') as output:
        proc=subprocess.Popen([sys.executable,'-c',script,json.dumps(proof),str(tmp_path)],stdout=output,stderr=subprocess.STDOUT,
            env={**os.environ,'PYTHONPATH':str(Path(supervisor.__file__).parent)})
        try:
            deadline=time.monotonic()+6
            while 'social_worker_unavailable' not in log.read_text() and proc.poll() is None and time.monotonic()<deadline:
                time.sleep(.01)
            assert proc.poll() is None, log.read_text()
            assert '"release_proof":null' in log.read_text()
            assert 'PRIVATE_RECEIPT_SECRET' not in log.read_text()
        finally:
            proc.terminate();proc.wait(timeout=6)


@pytest.mark.parametrize('seconds',[True,0,-1,float('nan'),float('inf'),None])
def test_direct_supervisor_api_cannot_bypass_finite_deadline(seconds):
    with pytest.raises(ValueError): supervisor.supervise([],lambda fd:[],seconds)
