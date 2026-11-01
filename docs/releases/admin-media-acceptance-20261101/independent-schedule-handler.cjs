'use strict';
// Execute the real component and real readiness hook; invoke even disabled
// buttons' handler callbacks to verify the mutation guard independently.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../..');
const ts = require(path.join(root, 'frontend/node_modules/typescript'));
const compile = relative => ts.transpileModule(fs.readFileSync(path.join(root, relative), 'utf8'), {
  compilerOptions: {target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX},
}).outputText;
const hook = compile('frontend/components/admin/social/useDeliveryWorkerReadiness.ts');
const component = compile('frontend/components/admin/social/SocialScheduleControls.tsx');
const now = Date.parse('2026-11-01T18:00:00Z'), future = '2099-01-05T07:00:00.000Z';
const iso = offset => new Date(now + offset).toISOString();
const healthy = {state:'active',heartbeat_at:iso(0),last_scan_at:iso(0)};
const post = {id:'inert-post',version:3,editorial_state:'approved',targets:[{state:'queued'}],
  publication:{id:'inert-publication',version:2,requested_local_time:'2099-01-05T10:00:00',schedule_timezone:'Africa/Nairobi'}};
let cases = 0;
async function probe(worker, blocked) {
  let stateIndex = 0;
  const calls = [];
  const react = {useState(initial) {const index = stateIndex++; return [index === 1 ? 'Explicit inert review' : typeof initial === 'function' ? initial() : initial, () => {}];},
    useEffect() {},useMemo(fn) {return fn();},useRef(current) {return {current};},useId() {return 'inert-description';}};
  const jsx = (type, props) => ({type, props});
  const module = {exports:{}};
  class Clock extends Date {static now() {return now;}}
  const globals = {Date:Clock,window:{},document:{}};
  vm.runInNewContext(hook,{...globals,module,exports:module.exports,require(name) {assert.equal(name,'react');return react;}});
  const actualHook = module.exports.default;
  const view = {exports:{}};
  vm.runInNewContext(component,{...globals,module:view,exports:view.exports,require(name) {
    if(name === 'react') return react;
    if(name === 'react/jsx-runtime') return {jsx,jsxs:jsx};
    if(name === './useDeliveryWorkerReadiness') return {__esModule:true,default:actualHook};
    if(name === '@/lib/hooks/useSocial') return {useSocialMutation:() => ({isPending:false,run:async (...args) => {calls.push(args);throw new Error('Intercepted inert mutation');}})};
    if(name === './socialDocument') return {resolveCivilTime:() => ({candidates:[{utc:future,offset:'+03:00'}]})};
    if(name === '@/lib/api/social') return {decodePost:x=>x,SocialApiError:Error};
    if(name === './SocialNotice') return {SocialErrorBanner:() => null};
    if(name === './social.module.css') return {__esModule:true,default:{}};
    throw new Error('Unexpected import '+name);
  }});
  const tree = view.exports.default({post,system:{publishing_enabled:true,worker},disabled:false,onUpdated() {throw new Error('Unexpected accepted mutation');}});
  function nodes(node) {if(!node||typeof node!=='object')return [];return [node,...[node.props?.children].flat(Infinity).flatMap(nodes)];}
  const all = nodes(tree), buttons = all.filter(x=>x.type==='button');
  const immediate = buttons.find(x=>x.props.children==='Publish unsent now');
  const scheduled = buttons.find(x=>x.props.children==='Confirm reschedule');
  assert.equal(Boolean(immediate.props.disabled),blocked);
  if(blocked) {
    assert.equal(immediate.props['aria-describedby'],'inert-description');
    assert.ok(all.some(x=>x.props?.id==='inert-description'));
  }
  await immediate.props.onClick();
  assert.equal(calls.length,blocked?0:1,'Direct handler must honor worker readiness');
  if(!blocked) {assert.match(calls[0][0],/publish-now$/);assert.equal(calls[0][1].schedule,undefined);}
  assert.equal(Boolean(scheduled.props.disabled),false,'Worker readiness must preserve future rescheduling');
  await scheduled.props.onClick();
  assert.equal(calls.length,blocked?1:2);assert.match(calls.at(-1)[0],/reschedule$/);
  assert.equal(calls.at(-1)[1].expected_version,3);assert.equal(calls.at(-1)[1].expected_publication_version,2);
  cases++;
}
(async()=>{
  await probe(healthy,false);await probe({...healthy,state:'idle'},false);
  await probe(undefined,true);await probe(null,true);
  for(const state of ['stale','stopped','unavailable','unknown']) await probe({...healthy,state},true);
  for(const field of ['heartbeat_at','last_scan_at']) for(const value of [null,'invalid',iso(5001),iso(-45001)]) await probe({...healthy,[field]:value},true);
  console.log(JSON.stringify({status:'PASS',cases,scope:'actual_schedule_component_and_hook_direct_handlers',external_calls:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
