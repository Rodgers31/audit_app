'use strict';
// Execute the actual hook with a deterministic clock and minimal React lifecycle.
// No network, browser, service or copied hook implementation is involved.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../..');
const ts = require(path.join(root, 'frontend/node_modules/typescript'));
const file = path.join(root, 'frontend/components/admin/social/useDeliveryWorkerReadiness.ts');
const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS},
}).outputText;
const start = Date.parse('2026-11-01T18:00:00Z');
let cases = 0;
function harness(worker) {
  let clock = start, state, initialized = false, currentWorker = worker;
  let dependencies, cleanup, effect, changed = false, currentResult;
  let nextTimer = 0;
  const timers = new Map(), listeners = new Map();
  class Clock extends Date { static now() { return clock; } }
  const module = {exports: {}};
  const react = {
    useState(init) {
      if (!initialized) { state = init(); initialized = true; }
      return [state, value => { if (value !== state) { state = value; changed = true; } }];
    },
    useEffect(fn, deps) {
      if (!dependencies || deps.some((d, i) => d !== dependencies[i])) {
        dependencies = deps; effect = fn;
      }
    },
  };
  vm.runInNewContext(compiled, {module, exports: module.exports, Date: Clock,
    require(name) { assert.equal(name, 'react'); return react; },
    window: {setTimeout(fn, delay) { const id = ++nextTimer; timers.set(id, {fn, at: clock + delay}); return id; },
      clearTimeout(id) { timers.delete(id); }},
    document: {addEventListener(name, fn) { listeners.set(name, fn); },
      removeEventListener(name, fn) { if (listeners.get(name) === fn) listeners.delete(name); }},
  }, {filename: file});
  function render(next = currentWorker) {
    currentWorker = next;
    for (let guard = 0; guard < 10; guard++) {
      changed = false; currentResult = module.exports.default(currentWorker);
      if (effect) { const pending = effect; effect = undefined; cleanup?.(); cleanup = pending(); }
      if (!changed) return currentResult;
    }
    throw new Error('Hook failed to settle');
  }
  render();
  return {result: () => currentResult, render,
    jump(ms) { clock += ms; },
    visible() { listeners.get('visibilitychange')?.(); render(); },
    advance(ms) {
      const end = clock + ms;
      for (;;) {
        const due = [...timers].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        clock = due[1].at; timers.delete(due[0]); due[1].fn(); render();
      }
      clock = end;
    },
    dispose() { cleanup?.(); assert.equal(timers.size, 0); assert.equal(listeners.size, 0); },
  };
}
const timestamp = delta => new Date(start + delta).toISOString();
function worker(state = 'active', heartbeat = 0, scan = 0) {
  return {state, heartbeat_at: typeof heartbeat === 'number' ? timestamp(heartbeat) : heartbeat,
    last_scan_at: typeof scan === 'number' ? timestamp(scan) : scan};
}
function check(value, blocked) {
  const h = harness(value);
  assert.equal(Boolean(h.result()), blocked, JSON.stringify(value)); h.dispose(); cases++;
}
check(undefined, true); check(null, true);
for (const state of ['stopped', 'stale', 'unavailable', 'pending', '', 'unknown']) check(worker(state), true);
for (const field of ['heartbeat_at', 'last_scan_at']) {
  for (const value of [null, undefined, '', 'not-a-time', '2099-01-01T00:00:00Z'])
    check({...worker(), [field]: value}, true);
}
for (const state of ['active', 'idle']) {
  const limit = state === 'active' ? 45_000 : 150_000;
  for (const field of ['heartbeat_at', 'last_scan_at']) {
    check({...worker(state), [field]: timestamp(-limit)}, false);
    check({...worker(state), [field]: timestamp(-limit - 1)}, true);
    check({...worker(state), [field]: timestamp(5000)}, false);
    check({...worker(state), [field]: timestamp(5001)}, true);
  }
  const h = harness(worker(state)); h.advance(limit); assert.equal(h.result(), undefined);
  h.advance(1); assert.match(h.result(), /stale/); h.dispose(); cases++;
}
const visible = harness(worker()); visible.jump(60_000); visible.visible();
assert.match(visible.result(), /stale/); visible.dispose(); cases++;
const refresh = harness(worker()); refresh.jump(60_000);
assert.equal(refresh.render(worker('active', 60_000, 60_000)), undefined);
refresh.advance(45_001); assert.match(refresh.result(), /stale/); refresh.dispose(); cases++;
console.log(JSON.stringify({status: 'PASS', cases, scope: 'actual_hook_deterministic_clock', network: 'not_used'}));
