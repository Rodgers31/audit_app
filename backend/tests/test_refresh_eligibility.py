"""Execute the real Actions selection against only its declared direct needs."""
import copy
import json
import os
from pathlib import Path
import subprocess
import shutil

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SHA = 'a' * 40
PLAN = 'b' * 64


def needs_fixture():
    needs = {
        'source_plan': {'result': 'success', 'outputs': {'source_sha': SHA, 'plan_sha256': PLAN, 'dry_run': 'false', 'bootstrap': 'false'}},
        'migrate': {'result': 'success', 'outputs': {'source_sha': SHA, 'schema_head': 'a756b20a0001'}},
        'seed': {'result': 'failure', 'outputs': {'cache_eligible': 'true', 'classification': 'required_source_incomplete',
                    'source_sha': SHA, 'plan_sha256': PLAN, 'schema_head': 'a756b20a0001', 'report_version': '1'}},
        'bootstrap': {'result': 'skipped', 'outputs': {}},
        'validate': {'result': 'success', 'outputs': {}},
    }
    jobs,plan,context=execution_fixture()
    report=classify(jobs,plan,context)
    report['plan_sha256']=PLAN
    needs['source_plan']['outputs']['domains']=json.dumps(report['selected_domains'])
    needs['seed']['outputs']['report']=json.dumps(report)
    return needs


def expression_selected(needs, *, cancelled=False, inputs=None):
    """Evaluate the actual expression subset with documented Actions equality.

    This is a bounded local evaluator, not a hosted GitHub execution. Unlike
    JavaScript ==, Actions string equality ignores case and cross-types use
    numeric coercion. The actual shell preflight below is the HTTP authority.
    """
    import ast
    import re
    job = yaml.safe_load((ROOT / '.github/workflows/seed.yml').read_text())['jobs']['revalidate']
    visible = {key:value for key,value in needs.items() if key in job['needs']}
    expression = job['if'].strip().removeprefix('${{').removesuffix('}}').strip()
    expression = re.sub(r'!(?!=)', 'not ', expression).replace('&&',' and ').replace('||',' or ')
    tree = ast.parse('('+expression.strip()+')',mode='eval')
    values = {'needs':visible,'github':{'sha':SHA,'event':{'inputs':inputs or {}}}}
    def number(v):
        if v is None or v == '': return 0
        if type(v) in (bool,int,float): return float(v)
        if type(v) is str:
            try:
                parsed=json.loads(v)
                return float(parsed) if type(parsed) in (int,float) else float('nan')
            except (ValueError,TypeError): return float('nan')
        return float('nan')
    def equal(a,b):
        if type(a) is str and type(b) is str:return a.casefold()==b.casefold()
        if type(a) is type(b):return a==b if type(a) not in (dict,list) else a is b
        return number(a)==number(b)
    def evaluate(n):
        if isinstance(n,ast.Constant):return n.value
        if isinstance(n,ast.Name):return values.get(n.id, {'true':True,'false':False,'null':None}.get(n.id,''))
        if isinstance(n,ast.Attribute):
            value=evaluate(n.value);return value.get(n.attr,'') if type(value)is dict else ''
        if isinstance(n,ast.Call):
            if n.func.id=='cancelled':return cancelled
            if n.func.id=='success':return all(x['result']=='success' for x in visible.values())
            raise AssertionError('Unhandled Actions function')
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.Not):return not evaluate(n.operand)
        if isinstance(n,ast.BoolOp):
            if isinstance(n.op,ast.And):return all(evaluate(v)for v in n.values)
            return any(evaluate(v)for v in n.values)
        if isinstance(n,ast.Compare) and len(n.ops)==1:
            result=equal(evaluate(n.left),evaluate(n.comparators[0]))
            return not result if isinstance(n.ops[0],ast.NotEq) else result
        raise AssertionError('Unhandled Actions expression node')
    return bool(evaluate(tree.body))


def preflight(needs):
    job=yaml.safe_load((ROOT/'.github/workflows/seed.yml').read_text())['jobs']['revalidate']
    step=next(s for s in job['steps']if s.get('name')=='Verify exact refresh eligibility before HTTP')
    visible={key:value for key,value in needs.items()if key in job['needs']}
    return subprocess.run(['bash','-eo','pipefail','-c',step['run']],cwd=ROOT,text=True,capture_output=True,timeout=10,
        env={'PATH':os.path.dirname(__import__('sys').executable)+':'+os.environ['PATH'],'REFRESH_NEEDS':json.dumps(visible),
             'GITHUB_SHA':SHA,'GITHUB_RUN_ID':'1234','GITHUB_RUN_ATTEMPT':'1'})


def selected(needs, *, cancelled=False, inputs=None):
    return expression_selected(needs,cancelled=cancelled,inputs=inputs) and preflight(needs).returncode==0


def test_known_source_gap_refreshes_committed_siblings():
    assert selected(needs_fixture())


def test_complete_run_refreshes_with_explicit_unselected_bootstrap():
    needs = needs_fixture()
    needs['seed']['result'] = 'success'
    needs['seed']['outputs']['classification'] = 'complete'
    receipt=json.loads(needs['seed']['outputs']['report']);receipt['classification']='complete';receipt['jobs'][0].update(required_completion='complete',source_mode='live')
    needs['seed']['outputs']['report']=json.dumps(receipt)
    assert selected(needs)


@pytest.mark.parametrize('job', ['source_plan', 'migrate', 'validate'])
@pytest.mark.parametrize('result', ['failure', 'cancelled', 'skipped', '', 'unknown'])
def test_unsafe_prerequisites_never_refresh(job, result):
    needs = needs_fixture(); needs[job]['result'] = result
    assert not selected(needs)


@pytest.mark.parametrize('field,value', [('cache_eligible', ''), ('cache_eligible', 'True'), ('cache_eligible', True),
    ('source_sha', 'c' * 40), ('schema_head', 'old'), ('plan_sha256', 'c' * 64),
    ('report_version', '2'), ('classification', 'unknown'), ('classification', 'complete')])
def test_malformed_or_wrong_identity_never_refreshes(field, value):
    needs = needs_fixture(); needs['seed']['outputs'][field] = value
    assert not selected(needs)


def test_cancelled_dry_and_bootstrap_mismatches_refuse():
    needs = needs_fixture()
    assert not selected(needs, cancelled=True)
    needs['source_plan']['outputs']['dry_run'] = 'true'
    assert not selected(needs)
    needs = needs_fixture(); needs['source_plan']['outputs']['bootstrap'] = 'true'
    assert not selected(needs)
    needs['bootstrap']['result'] = 'success'
    receipt=json.loads(needs['seed']['outputs']['report']);receipt['bootstrap_selected']=True
    needs['seed']['outputs']['report']=json.dumps(receipt)
    assert selected(needs)
    needs['bootstrap']['result'] = 'failure'
    assert not selected(needs)
    needs = needs_fixture(); needs['bootstrap']['result'] = 'success'
    assert not selected(needs)

# Classifier controls use inert native-result doubles. Real ORM/window execution
# is covered by test_hollow_run_gate and the dedicated PostgreSQL acceptance.
from datetime import datetime, timedelta
from types import SimpleNamespace
from seeding.current_run import classify, plan_identity, publish
from seeding.source_plan import SourcePlan


def execution_fixture():
    plan = SourcePlan(('fiscal_summary', 'pending_bills'), False, False)
    context = dict(source_sha=SHA, admitted_sha=SHA, planned_sha=SHA, schema_head='a756b20a0001',
        planned_identity=plan_identity(plan), prior_success='true', cli_outcome='success',
        cli_executed='true', cli_exit='0', floor=30, run_id='1234', run_attempt='1',
        cli_run_id='1234', cli_run_attempt='1', cli_floor='30',
        cli_started='2026-11-04T02:00:00Z', cli_finished='2026-11-04T02:44:00Z')
    from seeding.current_run import PRIOR_STEPS
    context.update(prior_job_status='success', prior_steps={name:{'outcome':'success','conclusion':'success','outputs':{}} for name in PRIOR_STEPS})
    jobs = []
    for i, domain in enumerate(plan.domains):
        meta = {'source_mode': 'live', 'execution_plan': {'planned_domains': list(plan.domains), 'execution_order': list(plan.domains)},
                'refresh_completion': {'complete': True}}
        if domain == 'fiscal_summary':
            meta.update(source_mode='partial', source_fallback_reason='fiscal_components_incomplete',
                refresh_completion={'complete':False,'accepted_records':1,'accepted_years':['FY 2022/23']},
                refresh_components={'budget':{'state':'live'},'revenue':{'state':'unavailable', 'refreshed_years':[], 'missing_years':['FY 2022/23']},
                                    'framework':{'state':'partial','unreadable_editions':{},'unconfirmed_years':{'FY 2022/23':'edition_prints_no_tax_or_non_tax_row'}}})
        else:
            meta['refresh_components'] = {'national':{'complete':True,'mode':'live','records':2,'accepted_records':2},
                                          'counties':{'complete':True,'records':46,'accepted_records':46}}
        processed = 1 if i == 0 else 48
        jobs.append(SimpleNamespace(id=31+i, domain=domain,status='completed',meta=meta,errors=[],dry_run=False,
            items_processed=processed,items_created=0,items_updated=processed,
            started_at=datetime(2026,11,4,2,1),finished_at=datetime(2026,11,4,2,40)))
    return jobs, plan, context


def test_classifier_distinguishes_known_incomplete_source_and_keeps_required_red(tmp_path, monkeypatch):
    jobs, plan, context = execution_fixture()
    report = classify(jobs, plan, context)
    assert report['classification'] == 'required_source_incomplete' and report['cache_eligible'] is True
    assert report['jobs'][0]['required_completion'] == 'incomplete'
    from seeding.refresh_completion import required_refresh_failures
    assert required_refresh_failures(jobs)
    output = tmp_path / 'output'; output.touch(); monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    publish(report)
    written = dict(line.split('=',1) for line in output.read_text().splitlines())
    assert json.loads(written['report']) == report
    assert written['classification'] == 'required_source_incomplete'


@pytest.mark.parametrize('key,value', [('floor',None),('floor',True),('floor',-1),('admitted_sha','c'*40),
    ('source_sha',True),('planned_identity','c'*64),('prior_success','false'),('cli_exit','1'),('cli_exit',False),
    ('cli_outcome','failure'),('cli_executed','false'),('schema_head','old'),('cli_floor','29'),
    ('run_id','wrong'),('cli_run_id','1233'),('cli_run_attempt','2'),('cli_started','yesterday'),
    ('cli_finished','2026-11-04T01:00:00Z')])
def test_execution_context_is_fail_closed(key, value):
    jobs, plan, context = execution_fixture(); context[key] = value
    report = classify(jobs, plan, context)
    assert report['classification'] == 'unsafe' and report['cache_eligible'] is False


@pytest.mark.parametrize('mutation', ['empty','missing','duplicate','extra','old','running','failed','hollow','unknown','dry',
    'errors','wrong_error_shape','meta_list','meta_none','wrong_plan','unknown_complete','fake_complete','old_time','unfinished',
    'negative','boolean','nan','infinite','too_many','duplicate_id'])
def test_job_boundaries_refuse_all_unverified_inventory(mutation):
    jobs, plan, context = execution_fixture(); job = jobs[0]
    if mutation == 'empty': jobs = []
    elif mutation == 'missing': jobs.pop()
    elif mutation == 'duplicate': jobs.append(copy.deepcopy(job))
    elif mutation == 'extra': jobs.append(copy.deepcopy(job)); jobs[-1].domain='national_budget'
    elif mutation == 'old': job.id=30
    elif mutation in ('running','failed'): job.status=mutation
    elif mutation == 'hollow': job.items_processed=0; job.items_updated=0
    elif mutation == 'unknown': job.meta['source_mode']='unknown'
    elif mutation == 'dry': job.dry_run=True
    elif mutation == 'errors': job.errors=['arbitrary network/database failure']
    elif mutation == 'wrong_error_shape': job.errors={}
    elif mutation == 'meta_list': job.meta=[]
    elif mutation == 'meta_none': job.meta=None
    elif mutation == 'wrong_plan': job.meta['execution_plan']['planned_domains']=['audits']
    elif mutation == 'unknown_complete': job.meta['refresh_completion']={}
    elif mutation == 'fake_complete': job.meta['refresh_completion']['complete']=True
    elif mutation == 'old_time': job.started_at=datetime(2026,11,3)
    elif mutation == 'unfinished': job.finished_at=None
    elif mutation in ('negative','boolean','nan','infinite'): job.items_updated={'negative':-1,'boolean':True,'nan':float('nan'),'infinite':float('inf')}[mutation]
    elif mutation == 'too_many': jobs *= 10
    elif mutation == 'duplicate_id': jobs[1].id=job.id
    report = classify(jobs, plan, context)
    assert report['cache_eligible'] is False and report['classification'] == 'unsafe', (mutation,report)


def audit_fixture():
    jobs, _, context = execution_fixture()
    plan = SourcePlan(('audits',),False,False); job=jobs[0]; job.domain='audits'
    job.items_processed=4; job.items_updated=4; job.status='completed_with_errors'
    message='document 2392: reconciliation review required; 1 retirements, 1 revisions; published evidence preserved'
    job.errors=['extract failed for doc 2392: '+message]
    job.meta={'source_mode':'partial','source_fallback_reason':'audit_refresh_incomplete',
        'execution_plan':{'planned_domains':['audits'],'execution_order':['audits']},
        'refresh_completion':{'complete':False,'accepted_documents':1,'errors':1,'deferred':False},
        'documents':[{'doc_id':1,'parser_id':'oag_county_audit','extraction_outcome':'accepted',
            'extractions':{'existing':4},'loaded':{'processed':4,'created':0,'updated':0,'unchanged':4,'skipped':0}},
            {'doc_id':2392,'parser_id':'oag_blue_book','extraction_outcome':'pending','extraction_attempt':{'status':'partial',
             'error':'ReconciliationRequired: '+message,'source_sha256':'d'*64,
             'proposal':{'document_id':2392,'source_sha256':'d'*64,'candidate_sha256':'e'*64,'previous_sha256':'f'*64,
                         'retire_ids':[12],'update_ids':[13],'source_url':'https://private.invalid/token-secret'}}}]}
    context['planned_identity']=plan_identity(plan)
    return [job], plan, context


def test_known_native_hold_is_distinct_from_arbitrary_audit_failure():
    jobs,plan,context=audit_fixture()
    report=classify(jobs,plan,context)
    assert report['cache_eligible'] is True, report
    assert report['classification']=='required_source_incomplete'
    assert report['jobs'][0]['held_proposals'][0]['document_id']==2392
    assert 'private.invalid' not in json.dumps(report) and 'token-secret' not in json.dumps(report)
    jobs[0].errors.append('unrelated shell/network/database failure')
    assert classify(jobs,plan,context)['cache_eligible'] is False


@pytest.mark.parametrize('mutation',['error','proposal_sha','source_sha','document_id','deferred','accepted','retire_bool','missing_proposal'])
def test_unknown_or_inconsistent_hold_is_not_the_safe_subtype(mutation):
    jobs,plan,context=audit_fixture(); job=jobs[0]; attempt=job.meta['documents'][1]['extraction_attempt']
    if mutation=='error': attempt['error']='RuntimeError: failed'
    elif mutation=='proposal_sha': attempt['proposal']['candidate_sha256']='old'
    elif mutation=='source_sha': attempt['source_sha256']='c'*64
    elif mutation=='document_id': attempt['proposal']['document_id']=True
    elif mutation=='deferred': job.meta['refresh_completion']['deferred']=True
    elif mutation=='accepted': job.meta['refresh_completion']['accepted_documents']=2
    elif mutation=='retire_bool': attempt['proposal']['retire_ids']=[True]
    elif mutation=='missing_proposal': attempt.pop('proposal')
    assert classify(jobs,plan,context)['cache_eligible'] is False


@pytest.mark.parametrize('mutation',['state_only','garbage_years','all_live','no_accepted_write','impossible_fy','partition_overlap'])
def test_fiscal_known_subtype_requires_native_component_and_writer_evidence(mutation):
    jobs,plan,context=execution_fixture(); job=jobs[0]
    if mutation=='state_only':
        job.meta['refresh_components']={k:{'state':'partial'}for k in ('budget','revenue','framework')}
    elif mutation=='garbage_years':job.meta['refresh_components']['revenue']['missing_years']={}
    elif mutation=='all_live':
        c=job.meta['refresh_components'];c['revenue']={'state':'live','refreshed_years':['FY 2022/23'],'missing_years':[]};c['framework']={'state':'live','unreadable_editions':{},'unconfirmed_years':{}}
    elif mutation=='no_accepted_write':job.items_updated=0
    elif mutation=='impossible_fy':job.meta['refresh_completion']['accepted_years']=['FY 2022/99']
    elif mutation=='partition_overlap':job.meta['refresh_components']['revenue']['refreshed_years']=['FY 2022/23']
    assert classify(jobs,plan,context)['cache_eligible'] is False


def test_actions_case_insensitive_selection_cannot_bypass_exact_http_preflight():
    needs=needs_fixture();needs['seed']['outputs']['cache_eligible']='True'
    assert expression_selected(needs) is True  # documented Actions semantics
    result=preflight(needs)
    assert result.returncode!=0 and 'Exact current-run refresh eligibility refused' in result.stderr


@pytest.mark.parametrize('field,value',[('run_id','old'),('run_attempt','2'),('version',True),('cli_exit',False),('dry_run',True)])
def test_preflight_rejects_stale_and_wrong_typed_report(field,value):
    needs=needs_fixture();report=json.loads(needs['seed']['outputs']['report']);report[field]=value
    needs['seed']['outputs']['report']=json.dumps(report)
    assert preflight(needs).returncode!=0


def test_plan_identity_phase_has_no_database_import_dependency(tmp_path):
    import sys
    doc=yaml.safe_load((ROOT/'.github/workflows/seed.yml').read_text())
    step=next(s for s in doc['jobs']['source_plan']['steps']if s.get('name')=='Validate whitelisted plan')
    output=tmp_path/'outputs';output.touch()
    env={'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin','PYTHONPATH':str(ROOT/'backend'),
        'GITHUB_OUTPUT':str(output),'GITHUB_SHA':SHA,'DATABASE_URL':'inert-invalid-driver://no-network',
        'PYTHON_DOTENV_DISABLED':'1','PYTHONDONTWRITEBYTECODE':doc['env']['PYTHONDONTWRITEBYTECODE'],
        'SEED_PLAN_EVENT':'workflow_dispatch','SEED_PLAN_DOMAIN':'pending_bills',
        'SEED_PLAN_DRY_RUN':'false','SEED_PLAN_BOOTSTRAP':'false'}
    result=subprocess.run(['bash','-eo','pipefail','-c',step['run']],cwd=ROOT,env=env,text=True,capture_output=True,timeout=10)
    assert result.returncode==0,result.stdout+result.stderr
    from tests.test_healthcheck_is_bounded import _outputs
    fields=_outputs(output.read_text())
    assert fields['source_sha']==SHA and len(fields['plan_sha256'])==64 and fields['dry_run']=='false'


@pytest.mark.parametrize('exit_code',[0,1,2,17])
def test_actual_cli_shell_retains_verified_child_exit(tmp_path,exit_code):
    import sys
    doc=yaml.safe_load((ROOT/'.github/workflows/seed.yml').read_text())
    step=next(s for s in doc['jobs']['seed']['steps']if s.get('name')=='Seed planned domains')
    package=tmp_path/'backend/seeding';package.mkdir(parents=True)
    (package/'__init__.py').touch()
    (package/'source_plan.py').write_text(f'raise SystemExit({exit_code})\n')
    output=tmp_path/'outputs';output.touch()
    env={'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin','GITHUB_OUTPUT':str(output),
        'GITHUB_RUN_ID':'1234','GITHUB_RUN_ATTEMPT':'1','SEED_JOB_FLOOR':'30','PYTHONDONTWRITEBYTECODE':'1'}
    result=subprocess.run(['bash','-eo','pipefail','-c',step['run']],cwd=tmp_path,env=env,text=True,capture_output=True,timeout=10)
    fields=dict(line.split('=',1)for line in output.read_text().splitlines())
    assert result.returncode==exit_code,result.stderr
    assert fields['executed']=='true' and fields['exit_code']==str(exit_code) and fields['job_floor']=='30'
    assert fields['run_id']=='1234' and fields['run_attempt']=='1'


@pytest.mark.parametrize('mutation',['empty','duplicate','failed','hollow','wrong_floor','missing_generator','unknown_completion'])
def test_actual_preflight_validates_full_current_inventory(mutation):
    needs=needs_fixture();report=json.loads(needs['seed']['outputs']['report'])
    if mutation=='empty':report['jobs']=[]
    elif mutation=='duplicate':report['jobs'][1]=report['jobs'][0]
    elif mutation=='failed':report['jobs'][0]['status']='failed'
    elif mutation=='hollow':report['jobs'][0].update(processed=0,created=0,updated=0)
    elif mutation=='wrong_floor':report['job_floor']=-1
    elif mutation=='missing_generator':report.pop('generator_sha256')
    elif mutation=='unknown_completion':report['jobs'][0]['required_completion']='unknown'
    needs['seed']['outputs']['report']=json.dumps(report)
    result=preflight(needs)
    assert result.returncode!=0
    assert 'Typed current-run refresh eligibility refused' in result.stderr


def test_actual_failed_gate_outputs_reach_preflight_through_declared_job_outputs(tmp_path,monkeypatch):
    from sqlalchemy import create_engine,select
    from sqlalchemy.orm import Session
    from models import IngestionJob
    from tests.test_hollow_run_gate import _write_db,_run_step
    url=_write_db(tmp_path,[('fiscal_summary','completed',0,1,1,'partial','fiscal_components_incomplete')])
    engine=create_engine(url)
    with Session(engine)as session:
        job=session.scalar(select(IngestionJob));native,_,_=execution_fixture()
        meta=native[0].meta;meta['execution_plan']={'planned_domains':['fiscal_summary'],'execution_order':['fiscal_summary']}
        job.meta=meta;session.commit()
    engine.dispose()
    output=tmp_path/'outputs';output.touch();monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    result=_run_step(url,domain='fiscal_summary')
    assert result.returncode==1,result.stdout+result.stderr
    fields=dict(line.split('=',1)for line in output.read_text().splitlines())
    doc=yaml.safe_load((ROOT/'.github/workflows/seed.yml').read_text())
    # Execute the declared output address resolution, including output on a failed step.
    import re
    mapped={}
    for name,address in doc['jobs']['seed']['outputs'].items():
        found=re.fullmatch(r'\$\{\{ steps\.results\.outputs\.(\w+) \}\}',address)
        assert found,address
        mapped[name]=fields.get(found[1],'')
    needs=needs_fixture();needs['seed']['outputs']=mapped
    report=json.loads(fields['report'])
    needs['source_plan']['outputs'].update(plan_sha256=report['plan_sha256'],domains=json.dumps(report['selected_domains']))
    assert selected(needs),preflight(needs).stderr


@pytest.mark.parametrize('fault',['diagnostics','grading','close','publish_log','contradictory_grade'])
def test_actual_terminal_gate_never_publishes_eligibility_after_unknown_failure(tmp_path,monkeypatch,fault):
    from sqlalchemy import create_engine,select
    from sqlalchemy.orm import Session
    from models import IngestionJob
    from tests import test_hollow_run_gate as gate
    url=gate._write_db(tmp_path,[('fiscal_summary','completed',0,1,1,'partial','fiscal_components_incomplete')])
    engine=create_engine(url)
    try:
        with Session(engine)as session:
            job=session.scalar(select(IngestionJob));native,_,_=execution_fixture()
            meta=native[0].meta;meta['execution_plan']={'planned_domains':['fiscal_summary'],'execution_order':['fiscal_summary']}
            job.meta=meta;session.commit()
    finally:engine.dispose()
    injection=tmp_path/'injection';injection.mkdir()
    setup='def fail(*a,**k):raise RuntimeError("INJECTED_TERMINAL_RESULT_FAILURE")\n'
    if fault=='diagnostics':setup+='from seeding import current_run\ncurrent_run.publish_diagnostics=fail\n'
    elif fault=='grading':setup+='from seeding import staleness\nstaleness.hollow_run_findings=fail\n'
    elif fault=='close':
        setup+='import database\noriginal=database.SessionLocal\ndef session():\n value=original();value.close=fail;return value\ndatabase.SessionLocal=session\n'
    elif fault=='publish_log':
        setup+='import builtins\noriginal=builtins.print\ndef print_(*a,**k):\n if a and str(a[0]).startswith("Current-run classification:"):fail()\n return original(*a,**k)\nbuiltins.print=print_\n'
    else:
        setup+='from seeding import staleness\nfrom types import SimpleNamespace\nstaleness.hollow_run_findings=lambda jobs:[SimpleNamespace(level="FAIL")]\n'
    (injection/'sitecustomize.py').write_text(setup)
    output=tmp_path/'outputs';output.touch();monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    actual_run=subprocess.run;captured=[]
    def instrument(*args,**kwargs):
        environment=kwargs.get('env',{})
        if environment.get('DATABASE_URL')==url and args[0][:2]==['bash','-e']:
            kwargs['env']={**environment,'PYTHONPATH':str(injection)+':'+environment['PYTHONPATH']}
            result=actual_run(*args,**kwargs);captured.append(result);return result
        return actual_run(*args,**kwargs)
    monkeypatch.setattr(subprocess,'run',instrument)
    try:gate._run_step(url,domain='fiscal_summary')
    except AssertionError:
        # The deliberate diagnostic fault precedes the inherited helper's
        # header witness. Verify the raw child rather than count setup as refusal.
        assert captured and 'RuntimeError: INJECTED_TERMINAL_RESULT_FAILURE' in captured[0].stderr
    assert len(captured)==1 and captured[0].returncode==1
    if fault!='contradictory_grade':
        assert 'RuntimeError: INJECTED_TERMINAL_RESULT_FAILURE' in captured[0].stderr
    fields=dict(line.split('=',1)for line in output.read_text().splitlines())
    if fault=='contradictory_grade':
        assert fields['cache_eligible']=='false' and fields['classification']=='unsafe'
        assert 'job_result_refused' in json.loads(fields['report'])['refusals']
    else:assert 'report' not in fields and 'cache_eligible' not in fields
    doc=yaml.safe_load((ROOT/'.github/workflows/seed.yml').read_text())
    import re
    mapped={}
    for name,address in doc['jobs']['seed']['outputs'].items():
        match=re.fullmatch(r'\$\{\{ steps\.results\.outputs\.(\w+) \}\}',address);assert match,address
        mapped[name]=fields.get(match[1],'')
    needs=needs_fixture();needs['seed']['outputs']=mapped
    if 'report'in fields:
        report=json.loads(fields['report'])
        needs['source_plan']['outputs'].update(plan_sha256=report['plan_sha256'],domains=json.dumps(report['selected_domains']))
    assert not selected(needs) and preflight(needs).returncode!=0


@pytest.mark.parametrize('accepted,seen',[(None,None),(0,1),(1,None),(1,0),(2,1)])
def test_complete_audits_receipt_requires_positive_coherent_document_inventory(accepted,seen):
    jobs,_,context=audit_fixture();plan=SourcePlan(('audits',),False,False);job=jobs[0]
    job.meta['documents']=job.meta['documents'][:1]
    job.meta['refresh_completion'].update(complete=True,errors=0)
    job.meta['source_mode']='live';job.errors=[];job.status='completed'
    report=classify(jobs,plan,context)
    assert report['classification']=='complete' and report['cache_eligible'] is True
    needs=needs_fixture()
    needs['seed']['result']='success'
    needs['seed']['outputs'].update(classification='complete',plan_sha256=report['plan_sha256'])
    needs['source_plan']['outputs'].update(domains='["audits"]',plan_sha256=report['plan_sha256'])
    needs['seed']['outputs']['report']=json.dumps(report)
    assert preflight(needs).returncode==0
    report['jobs'][0].update(accepted_documents=accepted,document_count=seen)
    needs['seed']['outputs']['report']=json.dumps(report)
    assert preflight(needs).returncode!=0


@pytest.mark.parametrize('outcome,conclusion,job_status,allowed', [
    ('success','success','success',True), ('failure','failure','failure',False),
    ('failure','success','success',False), ('skipped','skipped','success',False),
    ('cancelled','cancelled','cancelled',False)])
def test_real_classifier_previous_step_terminal_outcomes(outcome,conclusion,job_status,allowed):
    jobs,plan,context=execution_fixture()
    context['prior_steps']['dependencies'].update(outcome=outcome,conclusion=conclusion)
    context['prior_job_status']=job_status
    report=classify(jobs,plan,context)
    assert report['cache_eligible'] is allowed
    assert report['classification']==('required_source_incomplete' if allowed else 'unsafe')
