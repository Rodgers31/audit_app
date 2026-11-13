"""Execute the workflow's notification script offline; GitHub calls are intercepted."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = Path(os.environ.get('SEED_NOTIFICATION_WORKFLOW', ROOT / '.github/workflows/seed.yml'))
DOC = yaml.safe_load(WORKFLOW.read_text())
NODE = shutil.which('node')
KEYS = ('source_plan', 'healthcheck', 'migrate', 'seed', 'bootstrap', 'validate', 'revalidate')


def healthy(weekly=False):
    needs = {key: {'result': 'success', 'outputs': {}} for key in KEYS}
    needs['source_plan']['outputs'] = {'domains': '["audits"]', 'bootstrap': str(weekly).lower()}
    needs['bootstrap']['result'] = 'success' if weekly else 'skipped'
    needs['healthcheck']['outputs'] = {'has_failures': 'false', 'unprobed': '0'}
    sha, plan = 'a'*40, 'b'*64
    needs['source_plan']['outputs'].update(source_sha=sha, plan_sha256=plan, dry_run='false')
    needs['migrate']['outputs'] = {'source_sha':sha,'schema_head':'a756b20a0001'}
    receipt = dict(version=1,generator_sha256='d'*64,refusals=[],cli_exit=0,source_sha=sha,schema_head='a756b20a0001',plan_sha256=plan,
        dry_run=False,bootstrap_selected=weekly,job_floor=30,run_id='41268107359',run_attempt='1',
        cli_executed=True,cli_exit_zero=True,classification='complete',cache_eligible=True,
        selected_domains=['audits'],jobs=[dict(domain='audits',job_id=31,status='completed',source_mode='live',
            processed=4,created=0,updated=4,error_count=0,required_completion='complete',document_count=1,
            accepted_documents=1,held_proposals=[],retention={'state':'unverified'})])
    needs['seed']['outputs'] = {'report':json.dumps(receipt),'source_sha':sha,'schema_head':'a756b20a0001',
        'plan_sha256':plan,'classification':'complete','cache_eligible':'true','report_version':'1'}
    needs['revalidate']['outputs'] = {'backend':'true','pages':'true','protocol':'nightly-refresh-v2','source_sha':sha,'plan_sha256':plan,'run_id':'41268107359','run_attempt':'1','evidence_sha256':'e'*64}
    return needs


def execute(needs, *, event='schedule', inputs=None, issues=None, fail_api=None, attempt=1, env_overrides=None, nightly_enabled="true"):
    if NODE is None:
        raise AssertionError('Node is required to execute the actual workflow notification script')
    step = next(s for s in DOC['jobs']['notify']['steps'] if s.get('name') == 'Create issue on seeding/validation failure')
    # GitHub exposes only explicitly declared direct needs to this job.
    visible = {k: v for k, v in needs.items() if k in DOC['jobs']['notify']['needs']}
    inputs = inputs or {}
    values = {'toJSON(needs)': json.dumps(visible), 'toJSON(github.event.inputs)': json.dumps(inputs),
              'github.event_name': event, 'github.event.schedule': '0 2 * * 1-6' if event == 'schedule' else '',
              'github.run_attempt': str(attempt)}
    def value(expr):
        expr = expr.strip()
        if expr in values:
            return values[expr]
        match = re.fullmatch(r'needs\.(\w+)\.(result|outputs\.\w+)', expr)
        if match:
            item = visible.get(match[1], {})
            if match[2] == 'result':
                return item.get('result', '')
            return item.get('outputs', {}).get(match[2].split('.')[1], '')
        if expr == "github.event.inputs.domain || 'all'":
            return inputs.get('domain') or 'all'
        raise AssertionError(f'unhandled workflow expression: {expr}')
    env = {k: re.sub(r'\$\{\{(.*?)\}\}', lambda m: value(m[1]), str(v)) for k, v in step.get('env', {}).items()}
    env.update(env_overrides or {})
    program = r'''
const fixture = JSON.parse(process.argv[1]);
const calls = []; let summary = ''; let failure = null;
const context = {repo: {owner:'o', repo:'r'}, serverUrl:'https://github.com', runId:41268107359,
  eventName:fixture.event, payload:{inputs:fixture.inputs}};
const issues = {};
for (const method of ['listForRepo','create','update','createComment']) {
  issues[method] = async args => {
    calls.push({method,args});
    if (method === fixture.failApi) throw new Error('intercepted API failure');
    return {data: method === 'listForRepo' ? fixture.issues : {number:17}};
  };
}
const github = {rest:{issues}};
const core = {summary:{addRaw(value){summary += value; return this;}, async write(){}},
  setFailed(value){failure=String(value);}, info(){}, warning(){}};
const condition = fixture.condition.replace(/^\$\{\{\s*|\s*\}\}$/g,'');
(async () => {
  const jobSelected = new Function('github','vars','always',`return (${fixture.jobCondition});`)(
    {event_name:fixture.event},{INGESTION_NIGHTLY_ENABLED:fixture.nightlyEnabled},()=>true);
  const selected = jobSelected && new Function('needs','always','success',`return (${condition});`)(fixture.needs,()=>true,()=>true);
  if (selected) await new (Object.getPrototypeOf(async function(){}).constructor)('github','context','core','require',fixture.script)(github,context,core,require);
  process.stdout.write(JSON.stringify({calls,summary,failure,selected}));
})().catch(error => {process.stderr.write(String(error)); process.exitCode=1;});
'''
    fixture = {'needs': visible, 'script': step['with']['script'], 'condition': str(step.get('if', 'true')),
               'event': event, 'inputs': inputs, 'issues': issues or [], 'failApi': fail_api,
               'jobCondition': DOC['jobs']['notify']['if'], 'nightlyEnabled':nightly_enabled}
    proc = subprocess.run([NODE, '-e', program, json.dumps(fixture)], cwd=ROOT,
                          env={'PATH': os.environ['PATH'], **env}, text=True, capture_output=True, timeout=10)
    if proc.returncode:
        raise AssertionError(proc.stderr)
    return json.loads(proc.stdout)


class NotificationTests(unittest.TestCase):
    def test_source_plan_failure_does_not_name_blocked_jobs_as_failures(self):
        needs = {key: {'result': 'skipped', 'outputs': {}} for key in KEYS}
        needs['source_plan']['result'] = 'failure'
        result = execute(needs)
        issue = result['calls'][-1]['args']
        self.assertEqual(issue['title'], 'Data pipeline failed: Source plan')
        self.assertIn('**Failed Steps:** Source plan\n', issue['body'])
        self.assertIn('Health check execution (`healthcheck`) | skipped | skipped — blocked by source_plan', issue['body'])
        self.assertIn('Cache / page refresh (`revalidate`) | skipped | skipped — blocked by', issue['body'])
        self.assertIn('not verified', result['failure'])

    def test_early_admission_rejection_pages_and_names_blocked_jobs(self):
        needs = healthy(True)
        needs['migrate']['result'] = 'failure'
        for key in ('seed', 'bootstrap', 'validate', 'revalidate'):
            needs[key]['result'] = 'skipped'
        result = execute(needs)
        self.assertEqual([c['method'] for c in result['calls']], ['listForRepo', 'create'])
        body = result['calls'][-1]['args']['body']
        self.assertIn('Database admission', body)
        self.assertIn('blocked', body)
        self.assertIn('not verified', result['summary'])
        self.assertIn('migrate', result['summary'])
        self.assertIn('not verified', result['failure'])

    def test_bootstrap_only_failure_pages(self):
        needs = healthy(True); needs['bootstrap']['result'] = 'failure'
        needs['revalidate']['result'] = 'skipped'
        result = execute(needs)
        self.assertEqual(result['calls'][-1]['method'], 'create')
        issue = result['calls'][-1]['args']
        self.assertEqual(issue['title'], 'Data pipeline failed: Bootstrap')
        self.assertIn('skipped — blocked by bootstrap', issue['body'])

    def test_source_plan_failure_and_independent_health_failure_page(self):
        for key in ('source_plan', 'healthcheck'):
            with self.subTest(key=key):
                needs = healthy(); needs[key]['result'] = 'failure'
                result = execute(needs)
                self.assertEqual(result['calls'][-1]['method'], 'create')
                self.assertIn(key, result['summary'])

    def test_each_critical_result_is_fail_closed(self):
        for key in KEYS:
            for state in ('cancelled', 'skipped', '', 'pending', None):
                if key == 'bootstrap' and state == 'skipped':
                    continue
                with self.subTest(key=key,state=state):
                    needs = healthy(True)
                    if state is None:
                        needs.pop(key)
                    else:
                        needs[key]['result'] = state
                    result = execute(needs)
                    self.assertTrue(result['calls'], (key,state,result))
                    self.assertIn('not verified', result['summary'])
                    self.assertNotIn('pending', result['summary'])  # raw unknown states are not echoed

    def test_success_and_intentional_manual_exclusions_do_not_page(self):
        scenarios = [(healthy(), 'schedule', {}), (healthy(True),'schedule', {}),
                     (healthy(), 'workflow_dispatch', {'domain':'audits'})]
        for field in ('dry_run', 'run_validation'):
            needs = healthy(); needs['revalidate']['result'] = 'skipped'
            if field == 'run_validation': needs['validate']['result'] = 'skipped'
            scenarios.append((needs,'workflow_dispatch',{field:'true' if field=='dry_run' else 'false', 'domain':'audits'}))
        for needs,event,inputs in scenarios:
            with self.subTest(event=event,inputs=inputs):
                result = execute(needs,event=event,inputs=inputs)
                self.assertEqual(result['calls'], [])
                self.assertIsNone(result['failure'])
                self.assertIn('completed as planned', result['summary'])

    def test_cancelled_excluded_job_still_pages(self):
        needs = healthy(); needs['bootstrap']['result'] = 'cancelled'
        self.assertEqual(execute(needs)['calls'][-1]['method'], 'create')

    def test_validation_still_required_after_seed_failure(self):
        needs = healthy(); needs['seed']['result'] = 'failure'; needs['validate']['result'] = 'skipped'
        needs['revalidate']['result'] = 'skipped'
        result = execute(needs)
        self.assertIn('unexpectedly skipped', result['summary'])
        self.assertIn('Validation', result['calls'][-1]['args']['body'])

    def test_same_run_attempt_deduplicates_and_later_attempt_updates_managed_incident(self):
        needs = healthy(); needs['migrate']['result'] = 'failure'
        first = execute(needs)['calls'][-1]['args']
        existing = [{'number':17, 'body':first['body']}]
        self.assertEqual([c['method'] for c in execute(needs,issues=existing)['calls']], ['listForRepo'])
        self.assertEqual([c['method'] for c in execute(needs,issues=existing,attempt=2)['calls']], ['listForRepo','update'])

    def test_unmanaged_issues_are_not_modified(self):
        needs=healthy(); needs['seed']['result']='failure'
        result=execute(needs,issues=[{'number':3,'body':'human investigation'}, {'number':4,'body':'source outage','pull_request':{}}])
        self.assertEqual(result['calls'][-1]['method'],'create')

    def test_full_lookup_and_api_failure_fail_visibly_without_duplicate_create(self):
        needs=healthy(); needs['migrate']['result']='failure'
        for issues,fail_api in [([{'number':i,'body':''} for i in range(100)],None),([], 'listForRepo'),([], 'create')]:
            with self.subTest(fail_api=fail_api,count=len(issues)):
                with self.assertRaisesRegex(AssertionError, 'lookup|intercepted API failure'):
                    execute(needs,issues=issues,fail_api=fail_api)

    def test_untrusted_domain_and_result_never_enter_issue(self):
        needs=healthy(); needs['seed']['result']='secret-token|<script>'
        result=execute(needs,event='workflow_dispatch',inputs={'domain':'secret-token|<script>'})
        self.assertNotIn('secret-token', json.dumps(result))

    def test_disabled_schedule_is_intentional_and_manual_still_reports(self):
        needs=healthy(); needs['migrate']['result']='failure'
        disabled=execute(needs,nightly_enabled='false')
        self.assertFalse(disabled['selected'])
        self.assertEqual(disabled['calls'],[])
        self.assertEqual(disabled['summary'],'')
        manual=execute(needs,event='workflow_dispatch',nightly_enabled='false')
        self.assertEqual(manual['calls'][-1]['method'],'create')

    def test_scheduled_null_inputs_are_supported(self):
        result=execute(healthy(),env_overrides={'PIPELINE_INPUTS':'null'})
        self.assertEqual(result['calls'],[])
        self.assertIn('completed as planned',result['summary'])

    def test_malformed_notification_inputs_fail_visibly(self):
        for key,value in [('PIPELINE_NEEDS','{'),('PIPELINE_NEEDS','null'),
                          ('PIPELINE_INPUTS','['),('PIPELINE_INPUTS','[]')]:
            with self.subTest(key=key,value=value):
                with self.assertRaisesRegex(AssertionError,'SyntaxError|Invalid notification inputs'):
                    execute(healthy(),env_overrides={key:value})

    def test_health_reporting_keeps_warnings_partial_and_unknown_distinct(self):
        for outputs,expected in [({'has_failures':'true','unprobed':'0'},'Some required source diagnostics failed or remain unprobed'),
                                 ({'has_failures':'false','unprobed':'3'},'3 source(s) not probed'),
                                 ({'has_failures':'','unprobed':'0'},'missing or malformed'),
                                 ({'has_failures':'false','unprobed':'0'},'Endpoint reachability diagnostics')]:
            with self.subTest(outputs=outputs):
                needs=healthy(); needs['seed']['result']='failure'
                needs['healthcheck']['outputs']=outputs
                self.assertIn(expected,execute(needs)['calls'][-1]['args']['body'])

    def assert_health_message(self, outputs, expected, *, alert):
        needs = healthy()
        needs['healthcheck']['outputs'] = outputs
        if alert:
            needs['seed']['result'] = 'failure'
        result = execute(needs)
        summary = next(line for line in result['summary'].splitlines() if line.startswith('**Health Check:**'))
        self.assertIn(expected, summary)
        if alert:
            issue = result['calls'][-1]['args']['body']
            self.assertEqual(summary, next(line for line in issue.splitlines() if line.startswith('**Health Check:**')))
        else:
            # Unknown source output does not invent a new pipeline incident;
            # health job execution and the existing source alert remain separate.
            self.assertEqual(result['calls'], [])
        return summary

    def test_unknown_health_verdict_never_claims_partial_for_any_counter(self):
        for verdict in ('', 'wat', 'TRUE', 'False', None, False, True, 0, 1, [], {}):
            for count in ('0', '3', '', None, 'invalid'):
                for alert in (False, True):
                    with self.subTest(verdict=verdict, count=count, alert=alert):
                        message = self.assert_health_message({'has_failures': verdict, 'unprobed': count},
                            'Unknown — missing or malformed health-check verdict', alert=alert)
                        self.assertNotIn('Partial', message)
                        self.assertNotIn('✅', message)
        for outputs in ({}, {'unprobed': '3'}):
            with self.subTest(missing_verdict=outputs):
                self.assert_health_message(outputs, 'Unknown — missing or malformed health-check verdict', alert=True)

    def test_invalid_health_count_never_invents_budget_exhaustion(self):
        invalid = ('', None, False, True, 0, 3, 3.0, -1, '00', '03', '-1', '1.0', '1e1',
                   ' 3', '3 ', '999999', 'NaN', 'Infinity', '<script>', [], {})
        for count in invalid:
            for alert in (False, True):
                with self.subTest(count=count, alert=alert):
                    message = self.assert_health_message({'has_failures': 'false', 'unprobed': count},
                        'Unknown — missing or malformed unprobed source count', alert=alert)
                    self.assertNotIn('Partial', message)
                    self.assertNotIn('✅', message)
        self.assert_health_message({'has_failures': 'false'},
            'Unknown — missing or malformed unprobed source count', alert=True)

    def test_valid_health_contract_preserves_critical_partial_and_complete(self):
        cases = [({'has_failures': 'true', 'unprobed': count}, 'Some required source diagnostics failed or remain unprobed')
                 for count in ('0', '3', '', None, 'invalid')]
        cases += [({'has_failures': 'false', 'unprobed': '0'}, '✅ Endpoint reachability diagnostics'),
                  ({'has_failures': 'false', 'unprobed': '3'}, 'Partial — 3 source(s) not probed'),
                  ({'has_failures': 'false', 'unprobed': '99999'}, 'Partial — 99999 source(s) not probed')]
        for outputs, expected in cases:
            for alert in (False, True):
                with self.subTest(outputs=outputs, alert=alert):
                    self.assert_health_message(outputs, expected, alert=alert)

    def test_multiple_managed_incidents_are_ambiguous(self):
        needs=healthy(); needs['migrate']['result']='failure'
        body=execute(needs)['calls'][-1]['args']['body']
        with self.assertRaisesRegex(AssertionError,'multiple managed'):
            execute(needs,issues=[{'number':1,'body':body},{'number':2,'body':body}])

    def test_missing_bootstrap_plan_is_not_a_success(self):
        needs=healthy(); needs['source_plan']['outputs'].pop('bootstrap')
        result=execute(needs)
        self.assertEqual(result['calls'][-1]['method'],'create')
        self.assertIn('unverified plan',result['summary'])


class CurrentRunReportTests(unittest.TestCase):
    def test_known_incomplete_run_keeps_incident_red_after_successful_refresh(self):
        needs=healthy()
        receipt=json.loads(needs['seed']['outputs']['report'])
        receipt['classification']='required_source_incomplete'
        receipt['jobs'][0]['required_completion']='incomplete'
        receipt['jobs'][0]['source_mode']='partial'
        receipt['jobs'][0].update(domain='fiscal_summary',document_count=None,accepted_documents=None)
        receipt['selected_domains']=['fiscal_summary']
        needs['source_plan']['outputs']['domains']='["fiscal_summary"]'
        needs['seed']['outputs'].update(report=json.dumps(receipt),classification='required_source_incomplete')
        needs['seed']['result']='failure'
        result=execute(needs)
        self.assertIn('not verified',result['failure'])
        body=result['calls'][-1]['args']['body']
        self.assertIn('required_source_incomplete',body)
        self.assertIn('backend acknowledged; pages acknowledged',body)
        self.assertIn('| fiscal_summary | 31 | partial |',body)
        needs['revalidate'] = {'result': 'skipped', 'outputs': {}}
        skipped = execute(needs)['calls'][-1]['args']
        self.assertIn('Cache / page refresh', skipped['title'])
        self.assertIn('skipped — unexpectedly skipped', skipped['body'])

    def test_successful_backend_and_failed_pages_are_reported_separately(self):
        needs=healthy(); needs['revalidate']['result']='failure'
        needs['revalidate']['outputs'].update(backend='true',pages='')
        result=execute(needs)
        self.assertIn('backend acknowledged; pages unverified',result['summary'])
        self.assertIn('backend acknowledged; pages unverified',result['calls'][-1]['args']['body'])

    def test_report_identity_and_shape_tampering_never_certifies_completion(self):
        for field,value in [('version',True),('source_sha','c'*40),('run_id','old'),('run_attempt','2'),
                            ('jobs',[]),('selected_domains',[]),('cli_executed',1),('cli_exit_zero','true'),
                            ('cache_eligible','true'),('classification','unknown')]:
            with self.subTest(field=field,value=value):
                needs=healthy(); receipt=json.loads(needs['seed']['outputs']['report']); receipt[field]=value
                needs['seed']['outputs']['report']=json.dumps(receipt)
                result=execute(needs)
                self.assertIn('not verified',result['failure'])
                self.assertIn('report unverified',result['summary'])

    def test_unknown_aggregate_cannot_hide_inside_success_report(self):
        for field,value in [('source_mode','unknown'),('required_completion','unknown'),('required_completion','not_required')]:
            needs=healthy(); receipt=json.loads(needs['seed']['outputs']['report']); receipt['jobs'][0][field]=value
            needs['seed']['outputs']['report']=json.dumps(receipt)
            self.assertIn('not verified',execute(needs)['failure'])

    def test_untrusted_provider_strings_never_render_from_report(self):
        needs=healthy(); receipt=json.loads(needs['seed']['outputs']['report'])
        receipt['jobs'][0]['retention']['provider_url']='https://secret.invalid/private-key'
        receipt['jobs'][0]['provider_error']='sensitive exception body'
        needs['seed']['outputs']['report']=json.dumps(receipt)
        result=execute(needs)
        self.assertNotIn('secret.invalid',json.dumps(result))
        self.assertNotIn('sensitive exception body',json.dumps(result))

    def test_http_receipts_require_literal_acknowledgements_even_on_green_job(self):
        for field in ('backend','pages'):
            for value in (True,1,'True','false','',None):
                needs=healthy(); needs['revalidate']['outputs'][field]=value
                result=execute(needs)
                self.assertIn('not verified',result['failure'])


class ReviewedReportContradictionTests(unittest.TestCase):
    def test_complete_required_job_cannot_hide_errors_partial_source_or_hold(self):
        for mutation in ('errors','source','held','retention'):
            needs=healthy();r=json.loads(needs['seed']['outputs']['report']);j=r['jobs'][0]
            if mutation=='errors':j.update(status='completed_with_errors',error_count=8)
            elif mutation=='source':j['source_mode']='partial'
            elif mutation=='held':j['held_proposals']=[dict(document_id=2392,retirements=1,revisions=1,source_sha256='a'*64,candidate_sha256='b'*64,previous_sha256='c'*64)]
            else:j['retention']=dict(state='confirmed',observed=2,retained=1,missing=1,recovered=0,retry_requests=0)
            needs['seed']['outputs']['report']=json.dumps(r)
            result=execute(needs)
            self.assertIn('not verified',result['failure'])
            self.assertEqual(result['calls'][-1]['method'],'create')


if __name__ == '__main__':
    unittest.main()


class WorkflowRefreshOutcomeTests(unittest.TestCase):
    def test_five_outcomes_never_promote_missing_retention(self):
        result = execute(healthy())
        for dimension in ('Execution:', 'Stored integrity:', 'Source coverage:', 'Evidence retention:', 'Cache/page freshness:'):
            self.assertIn(dimension, result['summary'])
        self.assertIn('Evidence retention: unverified', result['summary'])


class WorkflowRefreshReviewRegressions(unittest.TestCase):
    def test_failed_page_phase_cannot_claim_pages_acknowledged(self):
        needs=healthy();needs['revalidate']['result']='failure'
        result=execute(needs)
        self.assertNotIn('pages acknowledged',result['summary'])

    def test_missing_retained_bytes_are_not_masked_by_unverified_sibling(self):
        needs=healthy();receipt=json.loads(needs['seed']['outputs']['report'])
        row=receipt['jobs'][0];row['retention']={'state':'missing_bytes','observed':1,'retained':0,'missing':1,'recovered':0,'retry_requests':0}
        other={**row,'domain':'learning_hub','job_id':32,'source_mode':'fixture','status':'completed_with_errors','error_count':1,'required_completion':'not_required','retention':{'state':'unverified'},'document_count':None,'accepted_documents':None}
        receipt['jobs'].append(other);receipt['selected_domains'].append('learning_hub')
        needs['source_plan']['outputs']['domains']=json.dumps(receipt['selected_domains'])
        needs['seed']['outputs']['report']=json.dumps(receipt)
        self.assertIn('Evidence retention: missing bytes',execute(needs)['summary'])


class WorkflowRefreshDiagnosticRegressions(unittest.TestCase):
    def test_curated_only_selection_never_claims_a_live_publisher(self):
        needs=healthy();receipt=json.loads(needs['seed']['outputs']['report'])
        receipt['selected_domains']=['learning_hub'];row=receipt['jobs'][0]
        row.update(domain='learning_hub',source_mode='fixture',status='completed_with_errors',error_count=1,required_completion='not_required',document_count=None,accepted_documents=None)
        needs['source_plan']['outputs']['domains']='["learning_hub"]';needs['seed']['outputs']['report']=json.dumps(receipt)
        self.assertIn('Source coverage: curated reference',execute(needs)['summary'])


class WorkflowRefreshObservabilityTests(unittest.TestCase):
    def test_health_verdict_names_its_reachability_scope(self):
        self.assertIn('Endpoint reachability diagnostics',execute(healthy())['summary'])

    def test_cog_last_good_age_survives_unsafe_result(self):
        needs=healthy();needs['seed']['outputs'].update(classification='unsafe',cache_eligible='false')
        needs['seed']['result']='failure'
        envelope={'version':1,'generator_sha256':'d'*64,'source_sha':'a'*40,'plan_sha256':'b'*64,
            'run_id':'41268107359','run_attempt':'1','job_floor':30,'scope':'diagnostics_only_not_source_acceptance',
            'rows':[{'domain':'county_officials','job_id':31,'validation':'valid','source_status':{
                'state':'unavailable','fixture_used':False,'stored_governors_retained':47,'dated_stored_governors':47,
                'oldest_age_seconds':86400,'newest_age_seconds':3600}}]}
        needs['source_plan']['outputs']['domains']='["county_officials"]'
        report=json.loads(needs['seed']['outputs']['report']);report.update(classification='unsafe',cache_eligible=False,selected_domains=['county_officials'],jobs=[])
        needs['seed']['outputs']['report']=json.dumps(report)
        needs['seed']['outputs']['source_diagnostics']=json.dumps(envelope)
        result=execute(needs)
        self.assertIn('CoG unavailable; retained governors=47',result['summary'])
        self.assertIn('oldest age seconds=86400',result['summary'])
        self.assertIn('Current-run report:** unverified',result['summary'])

    def test_semantic_transition_is_visible_without_duplicate_comment(self):
        needs=healthy();needs['validate']['result']='failure'
        first=execute(needs)
        body=first['calls'][-1]['args']['body']
        needs=healthy();needs['validate']['result']='failure'
        report=json.loads(needs['seed']['outputs']['report']);report['run_attempt']='2'
        needs['seed']['outputs']['report']=json.dumps(report);needs['revalidate']['outputs']['run_attempt']='2'
        second=execute(needs,attempt=2,issues=[{'number':888,'body':body}])
        self.assertIn('Actionable state: unchanged',second['summary'])
        self.assertEqual([c['method'] for c in second['calls']],['listForRepo','update'])


class WorkflowRefreshPhaseBindingTests(unittest.TestCase):
    def test_matching_outputs_do_not_override_failed_admission(self):
        needs=healthy();needs['migrate']['result']='failure'
        result=execute(needs)
        self.assertIn('Execution: unverified',result['summary'])
        self.assertIn('Cache/page freshness: unverified',result['summary'])
        self.assertNotIn('backend acknowledged',result['summary'])
