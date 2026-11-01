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
        result = execute(needs)
        self.assertEqual(result['calls'][-1]['method'], 'create')
        self.assertIn('Bootstrap', result['calls'][-1]['args']['body'])

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
        for outputs,expected in [({'has_failures':'true','unprobed':'0'},'Some sources were unreachable'),
                                 ({'has_failures':'false','unprobed':'3'},'3 source(s) not probed'),
                                 ({'has_failures':'','unprobed':'0'},'missing or malformed'),
                                 ({'has_failures':'false','unprobed':'0'},'No critical source failures')]:
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
        cases = [({'has_failures': 'true', 'unprobed': count}, 'Some sources were unreachable')
                 for count in ('0', '3', '', None, 'invalid')]
        cases += [({'has_failures': 'false', 'unprobed': '0'}, '✅ No critical source failures'),
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


if __name__ == '__main__':
    unittest.main()
