'use strict';
// Actual workflow-selected script and helper; all GitHub methods are intercepted.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const root = path.resolve(__dirname, '../../..');
const yaml = require(path.join(root, 'frontend/node_modules/js-yaml'));
const workflow = yaml.load(fs.readFileSync(path.join(root, '.github/workflows/seed.yml'), 'utf8'));
const step = workflow.jobs.notify.steps.find(s => s.name === 'Create issue on seeding/validation failure');
assert.equal(step.if, 'always()');
assert.deepEqual(workflow.jobs.notify.needs, ['source_plan','healthcheck','migrate','seed','bootstrap','validate','revalidate']);
assert.equal(step.env.PIPELINE_NEEDS, '${{ toJSON(needs) }}');
assert.equal(step.env.PIPELINE_INPUTS, '${{ toJSON(github.event.inputs) }}');
assert.match(step.with.script, /await report/);
assert.match(workflow.jobs.notify.steps[0].uses, /^actions\/checkout@[a-f0-9]{40}$/);
const helper = require(path.join(root, '.github/scripts/seed_notifications.cjs'));
const keys = workflow.jobs.notify.needs;
const healthy = () => Object.fromEntries(keys.map(k => [k, {result: k === 'bootstrap' ? 'skipped' : 'success',
  outputs: k === 'source_plan' ? {bootstrap:'false'} : k === 'healthcheck' ? {has_failures:'false',unprobed:'0'} : {}}]));
let cases = 0;
async function execute(needs, {inputs = null, issues = [], attempt = '1', malformed, fail} = {}) {
  const calls = []; let summary = '', failure;
  const github = {rest:{issues:Object.fromEntries(['listForRepo','create','update','createComment'].map(method => [method, async args => {
    calls.push({method,args}); if (method === fail) throw new Error('intercepted API failure');
    return {data: method === 'listForRepo' ? issues : {number:7}};
  }]))}};
  const context = {repo:{owner:'offline',repo:'fixture'}, serverUrl:'https://github.com', runId:123, eventName:'schedule'};
  const core = {summary:{addRaw(s) {summary += s; return this;}, async write(){}}, setFailed(s) {failure = s;}};
  const original = {PIPELINE_NEEDS:process.env.PIPELINE_NEEDS, PIPELINE_INPUTS:process.env.PIPELINE_INPUTS, PIPELINE_RUN_ATTEMPT:process.env.PIPELINE_RUN_ATTEMPT};
  process.env.PIPELINE_NEEDS = malformed ?? JSON.stringify(needs);
  process.env.PIPELINE_INPUTS = JSON.stringify(inputs);
  process.env.PIPELINE_RUN_ATTEMPT = attempt;
  let error;
  try {
    const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
    await new AsyncFunction('github','context','core','require',step.with.script)(github,context,core,createRequire(path.join(root,'offline.js')));
  } catch (e) { error = String(e); }
  finally { for (const [k,v] of Object.entries(original)) { if (v === undefined) delete process.env[k]; else process.env[k] = v; } }
  return {calls,summary,failure,error};
}
(async () => {
  let r = await execute(healthy()); assert.equal(r.error, undefined); assert.equal(r.calls.length,0); assert.match(r.summary,/completed as planned/); cases++;
  for (const key of keys) for (const value of ['failure','cancelled','pending','',null,[],{},42]) {
    const needs = healthy(); needs[key].result = value;
    r = await execute(needs); assert.equal(r.error,undefined); assert.ok(r.failure); assert.equal(r.calls.at(-1).method,'create'); cases++;
  }
  for (const key of keys) {
    const needs = healthy(); delete needs[key]; r = await execute(needs);
    assert.ok(r.failure); assert.equal(r.calls.at(-1).method,'create'); cases++;
  }
  for (const malformed of ['null','[]','"secret"','12','{bad']) {
    r = await execute({}, {malformed}); assert.ok(r.error); assert.equal(r.calls.length,0); assert.doesNotMatch(r.summary,/completed as planned/); cases++;
  }
  for (const bootstrap of [undefined, null, false, true, 'TRUE', {}, []]) {
    const needs = healthy(); needs.source_plan.outputs.bootstrap = bootstrap;
    r = await execute(needs); assert.ok(r.failure); assert.match(r.summary,/unverified plan/); cases++;
  }
  for (const unprobed of ['1','-1','999999','secret|<script>',null,{},[]]) {
    const needs = healthy(); needs.seed.result = 'cancelled'; needs.healthcheck.outputs.unprobed = unprobed;
    r = await execute(needs); assert.doesNotMatch(JSON.stringify(r),/secret|<script>/); assert.match(r.summary,unprobed === '1' ? /Partial/ : /Unknown/); cases++;
  }
  const early = healthy(); early.migrate.result = 'cancelled';
  for (const key of ['seed','bootstrap','validate','revalidate']) early[key].result='skipped';
  r = await execute(early); assert.match(r.summary,/Database admission/); assert.match(r.summary,/blocked by migrate/); cases++;
  const seedFailed = healthy(); seedFailed.seed.result='failure'; seedFailed.validate.result='skipped'; seedFailed.revalidate.result='skipped';
  r = await execute(seedFailed); assert.match(r.summary,/unexpectedly skipped/); cases++;
  const excluded = healthy(); excluded.validate.result=excluded.revalidate.result='skipped';
  r = await execute(excluded,{inputs:{run_validation:'false'}}); assert.equal(r.calls.length,0); cases++;
  excluded.migrate.result='failure'; r = await execute(excluded,{inputs:{run_validation:'false'}});
  assert.ok(r.failure); assert.match(r.summary,/intentional/); assert.equal(r.calls.at(-1).method,'create'); cases++;
  const first = await execute(early); const body = first.calls.at(-1).args.body;
  r = await execute(early,{issues:[{number:7,body}]}); assert.deepEqual(r.calls.map(x=>x.method),['listForRepo']); cases++;
  r = await execute(early,{issues:[{number:7,body}],attempt:'2'}); assert.deepEqual(r.calls.map(x=>x.method),['listForRepo','update']); cases++;
  for (const issues of [Array.from({length:100},(_,i)=>({number:i,body:''})), [{number:1,body},{number:2,body}], {}]) {
    r = await execute(early,{issues}); assert.ok(r.error); assert.equal(r.calls.filter(x=>x.method==='create'||x.method==='update').length,0); cases++;
  }
  for (const fail of ['listForRepo','create','update']) {
    r = await execute(early,{fail,issues:fail==='update'?[{number:7,body:'<!-- seed-pipeline-incident:v1 -->old'}]:[]});
    assert.ok(r.error); assert.ok(r.failure); assert.equal(r.calls.filter(x=>x.method==='createComment').length,0); cases++;
  }
  for (const verdict of [undefined,null,'',true,false,0,1,[],{},'TRUE','False','secret|<script>']) {
    for (const count of [undefined,null,'0','1','99999','',true,false,0,1,NaN,Infinity,-Infinity,'-1','00','01','+1','1.0','1e1',' 1','1 ','1\n','0\n','1\r','1\u2028','1\u2029','100000',[],{}]) {
      const needs=healthy(); needs.healthcheck.outputs={has_failures:verdict,unprobed:count};
      const direct=helper.healthDescription(needs); assert.match(direct,/Unknown/); assert.doesNotMatch(direct,/Partial|✅/);
      needs.seed.result='failure'; const observed=await execute(needs); assert.equal(observed.error,undefined);
      assert.match(observed.calls.at(-1).args.body,/Health Check:\*\* ❔ Unknown/);
      assert.doesNotMatch(JSON.stringify(observed),/secret\|<script>/); cases++;
    }
  }
  for (const count of [undefined,null,'',true,false,0,1,NaN,Infinity,-Infinity,'-1','00','01','+1','1.0','1e1',' 1','1 ','1\n','0\n','1\r','1\u2028','1\u2029','100000',[],{}]) {
    const needs=healthy(); needs.healthcheck.outputs={has_failures:'false',unprobed:count};
    assert.match(helper.healthDescription(needs),/Unknown/); needs.seed.result='failure';
    const observed=await execute(needs); assert.equal(observed.error,undefined); assert.match(observed.calls.at(-1).args.body,/Unknown/); cases++;
  }
  for (const count of [undefined,null,'',true,false,'0','1','99999','invalid']) {
    const needs=healthy(); needs.healthcheck.outputs={has_failures:'true',unprobed:count};
    assert.match(helper.healthDescription(needs),/Some sources were unreachable/); needs.seed.result='failure';
    assert.match((await execute(needs)).calls.at(-1).args.body,/Some sources were unreachable/); cases++;
  }
  for (const count of ['0','1','99999']) {
    const needs=healthy(); needs.healthcheck.outputs={has_failures:'false',unprobed:count};
    assert.match(helper.healthDescription(needs), count==='0' ? /✅ No critical source failures/ : /Partial/); cases++;
  }
  assert.equal(helper.assess(healthy(),{}).problems.length,0);
  console.log(JSON.stringify({status:'PASS',cases,scope:'pr885_health_review_actual_workflow_and_direct_function',external_calls:0}));
})().catch(e => {console.error(e);process.exitCode=1;});
