"""PR782 review regressions: real workflow scripts, plan, CLI, and owned PG."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest
from sqlalchemy import text

from seeding import cli, source_plan
from seeding.config import SeedingSettings
from seeding.domains import cra, opendata
from seeding.registries import DomainRegistry
from seeding.types import DomainRunResult
from b66_sources.test_plan import workflow, ROOT
from b66_sources.test_native import opendata_pg, opendata_url, AUTH, query


def plan(**overrides):
    fields = dict(event='schedule', schedule=source_plan.WEEKLY, domain='', dry_run='false',
                  cra='true', opendata='true', discovery='false')
    return source_plan.build_plan(**(fields | overrides))


def summary_script(tmp_path, *, schedule=source_plan.WEEKLY, domain='', result='success', raw_domain=None):
    data,_ = workflow()
    step = next(s for s in data['jobs']['notify']['steps'] if s.get('name') == 'Create summary')
    p = plan(schedule=schedule) if not domain else plan(event='workflow_dispatch',schedule='',domain=domain)
    output=tmp_path/'plan-output';output.touch()
    plan_env={'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin','PYTHONPATH':str(ROOT/'backend'),
              'PYTHON_DOTENV_DISABLED':'1','PYTHONDONTWRITEBYTECODE':'1',
              'SEED_PLAN_EVENT':'schedule' if not domain else 'workflow_dispatch',
              'SEED_PLAN_SCHEDULE':schedule if not domain else '', 'SEED_PLAN_DOMAIN':domain,
              'SEED_CRA_INGESTION_ENABLED':'true','SEED_OPENDATA_INGESTION_ENABLED':'true',
              'SEED_KNBS_RELEASE_DISCOVERY_ENABLED':'false','GITHUB_OUTPUT':str(output)}
    checked=subprocess.run([sys.executable,'-m','seeding.source_plan','--check'],env=plan_env,cwd=ROOT,capture_output=True,text=True)
    assert checked.returncode==0,checked.stderr
    fields=dict(line.split('=',1) for line in output.read_text().splitlines())
    assert json.loads(fields['domains'])==json.loads(checked.stdout)['domains']==list(p.domains)
    values = {'github.event_name' : 'schedule' if not domain else 'workflow_dispatch',
              "github.event.inputs.domain || 'all'": domain or 'all',
              "github.event.inputs.dry_run || 'false'": 'false',
              "github.event.inputs.run_bootstrap || 'false'": 'false',
              'github.repository':'Rodgers31/audit_app'}
    def substitute(match):
        key=match[1].strip()
        return values.get(key,'success' if key.startswith('needs.') else '')
    script = re.sub(r'\$\{\{(.*?)\}\}',substitute,step['run'])
    summary=tmp_path/'summary.md'
    env={'PATH':'/usr/bin:/bin','GITHUB_STEP_SUMMARY':str(summary),'SEED_PLAN_DOMAIN':domain if raw_domain is None else raw_domain,
         'SEED_PLAN_EVENT':values['github.event_name'],'SEED_PLAN_SCHEDULE':schedule,
         'SEED_PLAN_BOOTSTRAP':'false','SEED_PLAN_RESULT':result,
         'SEED_PLANNED_DOMAINS':fields['domains'],'SEED_PLANNED_BOOTSTRAP':fields['bootstrap']}
    completed=subprocess.run(['/bin/bash','-e','-c',script],env=env,capture_output=True,text=True)
    assert completed.returncode == 0, completed.stderr
    return summary.read_text(),p


@pytest.mark.parametrize('schedule',[source_plan.DAILY,source_plan.WEEKLY])
def test_scheduled_summary_names_default_selection(tmp_path,schedule):
    receipt,p=summary_script(tmp_path,schedule=schedule)
    assert '| **Domain** | all' in receipt
    assert '| **Planned Domains** | ' in receipt
    for domain in p.domains: assert domain in receipt
    assert '| **Seed Status** | success |' in receipt


def test_sunday_bootstrap_summary_uses_actual_plan_not_absent_dispatch_input(tmp_path):
    receipt,p=summary_script(tmp_path)
    assert p.bootstrap is True
    assert '| **Bootstrap Planned** | true |' in receipt
    assert '| **Bootstrap Status** | success |' in receipt


def test_summary_does_not_certify_refused_or_missing_plan(tmp_path):
    receipt,_=summary_script(tmp_path,result='failure')
    assert '| **Planned Domains** | unverified' in receipt
    assert '| **Bootstrap Planned** | unverified' in receipt


def test_summary_env_values_never_execute_shell(tmp_path):
    marker=tmp_path/'unsafe'
    receipt,_=summary_script(tmp_path,domain='opendata',raw_domain=f'$(touch {marker}); `touch {marker}`')
    assert not marker.exists() and '$(touch' in receipt


def test_weekly_optional_handlers_are_not_starved_by_legacy_budget(opendata_pg,monkeypatch):
    """Real native jobs/claims/writers; virtual elapsed legacy work, no source network."""
    _,factory,engine,_=opendata_pg
    class Clock:
        now=0.0
        def monotonic(self): return self.now
    clock=Clock(); called=[]
    registry=DomainRegistry()
    def legacy(*,session,settings,context):
        name=session.get(__import__('models').IngestionJob,context.job_id).domain
        called.append(name)
        remaining=1320-clock.now
        clock.now+=min(600,remaining)+1
        if remaining < 600: raise cli.DomainTimeoutError('owned global budget boundary')
        from seeding.freshness import mark_live
        mark_live(name,detail='inert legacy budget fixture')
        return DomainRunResult(domain=name,items_processed=1)
    for name in source_plan.LEGACY_DOMAINS: registry.register(name,legacy)
    for name,module,cost in [('cra',cra,30),('opendata',opendata,45)]:
        def handler(*,session,settings,context,name=name,module=module,cost=cost):
            called.append(name)
            result=module.run(session,settings,context)
            clock.now+=cost
            return result
        registry.register(name,handler)
    now=lambda:datetime.now(timezone.utc)
    raw=(ROOT/'docs/admin/implementation/batch11-issue-602-evidence/fixtures/cra-fy2026-27.pdf').read_bytes()
    workbook=(ROOT/'backend/tests/fixtures/opendata/Chapter-5-Public-Finance.xlsx').read_bytes()
    monkeypatch.setattr(cra.source,'fetch_publication',lambda:(raw,now()))
    monkeypatch.setattr(opendata.source,'fetch_publication',lambda:(workbook,now()))
    monkeypatch.setattr(cli,'SessionLocal',factory)
    monkeypatch.setattr(cli,'load_builtin_domains',lambda:None)
    monkeypatch.setattr(cli,'REGISTRY',registry)
    monkeypatch.setattr(cli,'time',clock)
    args=cli.build_parser().parse_args(plan().argv[3:])
    code=cli.run_seed_command(args,SeedingSettings(_env_file=None,total_timeout_seconds=1320,
        domain_timeout_seconds=600,cra_ingestion_enabled=True,opendata_ingestion_enabled=True))
    jobs=query(engine,'SELECT domain,status::text,metadata FROM ingestion_jobs ORDER BY id')
    states={j['domain']:j['status'] for j in jobs}
    assert code==1, 'Exhausting budget must still fail visibly'
    assert called[:2]==['cra','opendata'], (called,states)
    assert states['cra']==states['opendata']=='COMPLETED'
    assert any(j['metadata'].get('dropped_by_global_budget') for j in jobs if j['domain'] in source_plan.LEGACY_DOMAINS)
    assert len(query(engine,'SELECT 1 FROM extractions'))==2
    assert not query(engine,'SELECT 1 FROM seeding_domain_claims WHERE released_at IS NULL')
    assert not query(engine,'SELECT 1 FROM budget_lines')


def test_calendar_is_truthful_about_optional_knbs_observation(monkeypatch):
    from routers import etl_admin
    monkeypatch.setattr(etl_admin.SmartScheduler,'_is_day_of_week',lambda *a:True)
    report=asyncio.run(etl_admin.get_source_schedule('opendata'))
    assert report['evidence']=='calendar_plan'
    assert 'calendar plan' in report['reason'].lower()
    assert 'pinned' in report['reason'].lower() and 'quarantin' in report['reason'].lower()
    assert 'Continuous dataset updates via API' not in json.dumps(report)
    health=asyncio.run(etl_admin.get_etl_health())
    assert health['worker_status']==health['data_freshness']=='unverified'
    assert health['manual_trigger']['available'] is False


def test_capability_copy_distinguishes_discovery_from_semantic_admission(opendata_pg):
    from admin_etl_dispatch_worker import register_worker
    client,factory,_,_=opendata_pg
    register_worker(factory)
    report=client.get('/api/v1/admin/etl/dispatch',headers=AUTH).json()
    text=report['sources']['opendata']['reason'].lower()
    assert report['evidence']=='worker_dispatch' and report['sources']['opendata']['available'] is True
    assert 'pinned' in text and 'discovery' in text and 'quarantin' in text and 'unqualified' in text


@pytest.mark.parametrize('hostile', ['opendata; touch marker', '$(touch marker)', '`touch marker`', 'population\n--all'])
def test_real_workflow_shell_requires_domain_guard_not_just_nonzero(tmp_path,hostile):
    data,_=workflow()
    script=next(s['run'] for s in data['jobs']['seed']['steps'] if s.get('name')=='Seed planned domains')
    env={'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin','PYTHONPATH':str(ROOT/'backend'),
         'PYTHON_DOTENV_DISABLED':'1','PYTHONDONTWRITEBYTECODE':'1',
         'SEED_PLAN_EVENT':'workflow_dispatch','SEED_PLAN_DOMAIN':hostile}
    child=subprocess.run(['/bin/bash','-e','-c',script],cwd=ROOT,env=env,capture_output=True,text=True)
    assert child.returncode==2 and 'Source plan refused: Unknown source plan domain' in child.stderr,child
    assert not (ROOT/'backend/marker').exists()
    # A missing child is a setup failure, not successful boundary coverage.
    missing=script.replace('python -m','/nonexistent/b67-python -m')
    child=subprocess.run(['/bin/bash','-e','-c',missing],cwd=ROOT,env=env,capture_output=True,text=True)
    assert child.returncode not in (0,2) and 'No such file or directory' in child.stderr and 'Source plan refused:' not in child.stderr


@pytest.mark.parametrize('domains,bootstrap', [((),False),(('opendata','opendata'),False),(('opendata\nbootstrap=true',),False),(('opendata',),'false')])
def test_direct_malformed_plan_cannot_publish_step_outputs(tmp_path,monkeypatch,domains,bootstrap):
    output=tmp_path/'output';output.write_text('untouched\n')
    monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    with pytest.raises(ValueError,match='Invalid source plan output'):
        source_plan.write_plan_outputs(source_plan.SourcePlan(domains,bootstrap,False))
    assert output.read_text()=='untouched\n'


@pytest.mark.parametrize('domains,bootstrap,dry_run', [
    ((),False,False), (['opendata'],False,False),
    (('opendata','opendata'),False,False), ((True,),False,False),
    (('opendata\nbootstrap=true',),False,False),
    (('opendata',),float('nan'),False), (('opendata',),'false',False),
    (('opendata',),False,float('nan')), (('opendata',),False,0),
])
def test_direct_malformed_plan_cannot_launch_native_cli(domains,bootstrap,dry_run):
    with pytest.raises(ValueError,match='Invalid source plan'):
        _ = source_plan.SourcePlan(domains,bootstrap,dry_run).argv


@pytest.mark.parametrize('mode,status,exit_code,extractions',[('normal','COMPLETED',0,1),('candidate','COMPLETED_WITH_ERRORS',1,0),('failure','FAILED',1,0)])
def test_actual_workflow_launcher_to_native_job_and_result_gate(opendata_pg,tmp_path,mode,status,exit_code,extractions):
    from b66_sources.pg_plugin import command_environment
    _,_,engine,url=opendata_pg
    with engine.begin() as db:db.execute(text('UPDATE batch11_control SET mode=:m'),{'m':mode})
    backend=ROOT/'backend'
    env=command_environment(url)
    env.update({'PYTHONPATH':os.pathsep.join([str(backend/'tests/b66_sources/child'),str(backend/'tests'),str(backend)]),
        'PATH':str(Path(sys.executable).parent)+':/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin',
        'B66_SOURCE_CHILD':'true','SEED_OPENDATA_INGESTION_ENABLED':'true','SEED_KNBS_RELEASE_DISCOVERY_ENABLED':'true',
        'SEED_PLAN_EVENT':'workflow_dispatch','SEED_PLAN_DOMAIN':'opendata','SEED_PLAN_DRY_RUN':'false',
        'SEED_STORAGE_PATH':str(tmp_path/'storage'),'SEED_CACHE_PATH':str(tmp_path/'cache')})
    data,_=workflow()
    script=next(s['run'] for s in data['jobs']['seed']['steps'] if s.get('name')=='Seed planned domains')
    child=subprocess.run(['/bin/bash','-e','-c',script],cwd=ROOT,env=env,capture_output=True,text=True,timeout=25)
    assert child.returncode==(1 if mode=='failure' else 0),child.stderr
    first=json.loads(child.stdout.splitlines()[0]); assert first['domains']==['opendata'] and first['evidence']=='selection_plan_only'
    jobs=query(engine,'SELECT status::text,metadata FROM ingestion_jobs')
    assert len(jobs)==1 and jobs[0]['status']==status
    check=next(s['run'] for s in data['jobs']['seed']['steps'] if s.get('name')=='Check ingestion job results')
    gate=subprocess.run(['/bin/bash','-e','-c',check],cwd=ROOT,env=env,capture_output=True,text=True,timeout=15)
    assert '--- Ingestion Job Results ---' in gate.stdout,gate.stderr
    assert gate.returncode==exit_code,(gate.stdout,gate.stderr)
    if mode=='candidate':assert '[REFUSED] opendata' in gate.stdout and '[FAIL] opendata this run' in gate.stdout
    if mode=='failure':assert '[FAIL] opendata:' in gate.stdout
    assert len(query(engine,'SELECT 1 FROM extractions'))==extractions
    assert not query(engine,'SELECT 1 FROM budget_lines')
