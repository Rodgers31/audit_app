"""Synthetic run context shared by the eligibility and browser refresh tests."""
import json
from datetime import datetime
from types import SimpleNamespace

from seeding.current_run import PRIOR_STEPS, classify, plan_identity
from seeding.source_plan import SourcePlan


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


def execution_fixture():
    plan = SourcePlan(('fiscal_summary', 'pending_bills'), False, False)
    context = dict(source_sha=SHA, admitted_sha=SHA, planned_sha=SHA, schema_head='a756b20a0001',
        planned_identity=plan_identity(plan), prior_success='true', cli_outcome='success',
        cli_executed='true', cli_exit='0', floor=30, run_id='1234', run_attempt='1',
        cli_run_id='1234', cli_run_attempt='1', cli_floor='30',
        cli_started='2026-11-04T02:00:00Z', cli_finished='2026-11-04T02:44:00Z')
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
