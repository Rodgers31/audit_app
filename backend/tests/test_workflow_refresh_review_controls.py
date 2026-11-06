"""Freshly reported cross-master census and unsafe-diagnostic transition controls."""
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('actual_notification_fixture',ROOT/'.github/scripts/tests/test_seed_notifications.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


def test_actionable_unsafe_cog_diagnostic_change_is_not_unchanged():
    def needs(attempt,retained):
        n=fixture.healthy()
        r=json.loads(n['seed']['outputs']['report'])
        r.update(classification='unsafe',cache_eligible=False,selected_domains=['county_officials'],jobs=[],run_attempt=str(attempt))
        n['source_plan']['outputs']['domains']='["county_officials"]'
        n['seed']['result']='failure'
        n['seed']['outputs'].update(report=json.dumps(r),classification='unsafe',cache_eligible='false')
        n['revalidate'].update(result='skipped',outputs={})
        p={'version':1,'generator_sha256':r['generator_sha256'],'source_sha':r['source_sha'],'plan_sha256':r['plan_sha256'],
            'run_id':r['run_id'],'run_attempt':str(attempt),'job_floor':r['job_floor'],'scope':'diagnostics_only_not_source_acceptance',
            'rows':[{'domain':'county_officials','job_id':31,'validation':'valid','source_status':{
                'state':'unavailable','fixture_used':False,'stored_governors_retained':retained,'dated_stored_governors':retained,
                'oldest_age_seconds':86400,'newest_age_seconds':3600}}]}
        n['seed']['outputs']['source_diagnostics']=json.dumps(p)
        return n
    first=fixture.execute(needs(1,47));body=first['calls'][-1]['args']['body']
    second=fixture.execute(needs(2,46),attempt=2,issues=[{'number':888,'body':body}])
    assert 'CoG unavailable; retained governors=46' in second['summary']
    assert 'Actionable state: changed' in second['summary']
    assert [c['method']for c in second['calls']]==['listForRepo','update']


def test_two_real_gunicorn_masters_cannot_omit_other_serving_workers(tmp_path):
    import os,socket,subprocess,sys,signal,time,httpx
    app=tmp_path/'two_master_app.py'
    app.write_text('from fastapi import FastAPI,HTTPException\nfrom cache.invalidation import serving_census,InvalidationError\napp=FastAPI()\n@app.get("/census")\ndef census():\n try:return serving_census()\n except InvalidationError as e:raise HTTPException(503,e.reason)\n')
    with socket.socket()as reserve:
        reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
    masters=[]
    try:
        for index in range(2):
            with (tmp_path/f'master-{index}.log').open('w')as log:
                p=subprocess.Popen([sys.executable,'-m','gunicorn','--config','/dev/null','--workers','2','--reuse-port',
                    '--worker-class','uvicorn.workers.UvicornWorker','--bind',f'127.0.0.1:{port}',
                    '--timeout','20','--graceful-timeout','2','two_master_app:app'],cwd=tmp_path,
                    env={**os.environ,'PYTHONPATH':str(tmp_path)+':'+os.environ['PYTHONPATH']},stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                masters.append(p)
        end=time.monotonic()+20
        while True:
            children=[]
            for process in masters:
                assert process.poll() is None
                path=Path(f'/proc/{process.pid}/task/{process.pid}/children')
                children.append([int(x)for x in path.read_text().split()])
            if all(len(pids)==2 for pids in children):break
            assert time.monotonic()<end
            time.sleep(.05)
        actual={pid for pids in children for pid in pids}
        with httpx.Client(trust_env=False,timeout=2,headers={'Connection':'close'})as client:
            while True:
                try:response=client.get(f'http://127.0.0.1:{port}/census');break
                except httpx.HTTPError:
                    assert time.monotonic()<end
                    time.sleep(.05)
        assert response.status_code in (200,503),response.text
        if response.status_code==200:
            c=response.json();seen={int(worker.split(':')[0])for worker in c['workers']}
            assert seen==actual,(seen,actual,c)
    finally:
        for process in masters:
            if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=6)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=3)
            try:os.killpg(process.pid,0)
            except ProcessLookupError:pass
            else:raise AssertionError('owned Gunicorn process group remains')
