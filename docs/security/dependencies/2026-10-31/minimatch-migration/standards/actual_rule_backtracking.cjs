'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), { spawnSync } = require('node:child_process');
const base = __dirname, front = '/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app/frontend';
const output = [];
for (const [profile, plugin] of [['original', path.join(base, 'baseline/node_modules/eslint-plugin-react/lib/rules/no-danger.js')], ['installed', path.join(front, 'node_modules/eslint-plugin-react/lib/rules/no-danger.js')]]) {
  const script = `const assert=require('node:assert/strict'),{performance}=require('node:perf_hooks'),{createRequire}=require('node:module');const {Linter}=createRequire(${JSON.stringify(path.join(front, 'package.json'))})('eslint');const rule=require(${JSON.stringify(plugin)});const engine=new Linter();engine.defineRule('probe',rule);function run(pattern){return engine.verify('const x=<'+ 'A'.repeat(32) +' dangerouslySetInnerHTML={{__html:"x"}}/>;',{parserOptions:{ecmaVersion:2022,sourceType:'module',ecmaFeatures:{jsx:true}},rules:{probe:['error',{customComponentNames:[pattern]}]}},{filename:'owned.jsx'});}assert.equal(run('Other*').length,0);console.log(JSON.stringify({ordinaryControlAlive:true}));const start=performance.now();assert.equal(run('*A'.repeat(12)+'B').length,0);console.log(JSON.stringify({hostileCaseCompleted:true,elapsedMs:performance.now()-start}));`;
  const args = ['--max-old-space-size=96', '-e', script];
  const started = Date.now();
  const child = spawnSync(process.execPath, args, { encoding: 'utf8', timeout: 2500, env: { ...process.env, NODE_PATH: path.join(front, 'node_modules') } });
  const row = { profile, command: [process.execPath, ...args], timeoutMs: 2500, wallMs: Date.now() - started, exit: child.status, signal: child.signal, error: child.error ? String(child.error) : null, stdout: child.stdout, stderr: child.stderr };
  output.push(row);
  assert.match(row.stdout, /ordinaryControlAlive/);
  if (profile === 'installed') { assert.ifError(child.error); assert.equal(child.signal, null); assert.equal(child.status, 0, child.stderr); assert.match(row.stdout, /hostileCaseCompleted/); }
}
fs.writeFileSync(path.join(base, 'actual-rule-backtracking-results.json'), JSON.stringify({ at: new Date().toISOString(), case: 'Actual React no-danger custom-component matching; bounded nonmatching repeated wildcard/literal pattern, not an all-pattern complexity guarantee.', output }, null, 2) + '\n', { flag: 'wx' });
console.log(JSON.stringify(output.map(({ command, ...r }) => r), null, 2));
