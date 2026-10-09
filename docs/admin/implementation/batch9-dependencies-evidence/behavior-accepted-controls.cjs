'use strict';

// Independent accepted-source recheck. Await async guard; preserve both prior review rounds.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const repo = path.resolve(__dirname, '../../../..');
const frontend = path.join(repo, 'frontend');
const npmCli = require('./control_contract.cjs').npmCli();
const guard = path.join(frontend, 'scripts/verify-tooling-inputs.cjs');
const graph = path.join(frontend, 'scripts/jest-dependency-boundary.test.cjs');
const patterns = ['pages', 'components', 'app', 'src'].map(dir => `./${dir}/**/*.{js,ts,jsx,tsx,mdx}`);
const deepPattern = '{'.repeat(4000) + 'a,b' + '}'.repeat(4000);
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const results = [];
const failures = [];
const sourceBefore = require('./control_contract.cjs').sourceIdentity(__filename);
const positiveLabels = new Set(['guard-valid-default', 'standard-lint-valid-default', 'graph-valid-control', 'graph-version-13', 'graph-version-14', 'graph-valid-builtin-name']);
function run(label, command, args, options = {}) {
  const output = spawnSync(command, args, { encoding: 'utf8', timeout: 20000, maxBuffer: 16 * 1024 * 1024, ...options });
  const result = { label, command: [command, ...args], cwd: options.cwd || process.cwd(), status: output.status,
    signal: output.signal, error: output.error?.message || null, stdout: output.stdout || '', stderr: output.stderr || '' };
  const expected = positiveLabels.has(label) ? 0 : 1;
  result.expected = expected;
  Object.assign(result, require('./control_contract.cjs').classifyControl(label, result, expected));
  if (!result.matchesExpectation) failures.push(label);
  if (label.startsWith('standard-lint') && expected === 1 && /bounded-tooling-inputs|> next lint|Maximum call stack size exceeded/.test(result.stdout + result.stderr)) failures.push(label + '-not-blocked-before-next');
  results.push(result);
  console.log(JSON.stringify({ label, status: result.status, signal: result.signal, error: result.error,
    successVerdict: /bounded-tooling-inputs/.test(result.stdout), braceCrash: /Maximum call stack size exceeded/.test(result.stderr),
    assertion: (result.stdout.match(/error: '(.*?)'/) || [])[1] }));
  return result;
}
function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'batch9-dependencies-behavior-'));
  fs.mkdirSync(path.join(root, 'scripts'));
  fs.mkdirSync(path.join(root, 'app'));
  fs.symlinkSync(path.join(frontend, 'node_modules'), path.join(root, 'node_modules'), 'dir');
  fs.copyFileSync(guard, path.join(root, 'scripts/verify-tooling-inputs.cjs'));
  fs.writeFileSync(path.join(root, 'tailwind.config.js'), `module.exports = { content: ${JSON.stringify(patterns)} };\n`);
  fs.writeFileSync(path.join(root, '.eslintrc.json'), JSON.stringify({ extends: 'next/core-web-vitals' }));
  fs.writeFileSync(path.join(root, 'app/page.js'), 'export default function Page() { return <div>Fixture</div>; }\n');
  const sourceManifest = JSON.parse(fs.readFileSync(path.join(frontend, 'package.json'), 'utf8'));
  fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify({ ...sourceManifest, name: 'batch9-dependencies-behavior' }));
  return root;
}
function guardCall(label, root) {
  return run(label, process.execPath, ['-e', '(async () => { const fn = require(process.argv[1]).verifyToolingInputs; console.log(JSON.stringify({check:"bounded-tooling-inputs", ...await fn(process.argv[2])})); })().catch(error => { console.error(error); process.exitCode = 1; });', guard, root], { cwd: root });
}
const roots = [];
try {
  for (const [name, change, actualLint] of [
    ['valid-default', () => {}, true],
    ['missing-tailwind', root => fs.unlinkSync(path.join(root, 'tailwind.config.js')), false],
    ['empty-tailwind', root => fs.writeFileSync(path.join(root, 'tailwind.config.js'), ''), false],
    ['invalid-tailwind', root => fs.writeFileSync(path.join(root, 'tailwind.config.js'), 'module.exports = null;'), false],
    ['deep-tailwind', root => fs.writeFileSync(path.join(root, 'tailwind.config.js'), `module.exports = {content:[${JSON.stringify(deepPattern)}]};`), false],
    ['missing-eslint', root => fs.unlinkSync(path.join(root, '.eslintrc.json')), false],
    ['empty-eslint', root => fs.writeFileSync(path.join(root, '.eslintrc.json'), ''), false],
    ['invalid-eslint-json', root => fs.writeFileSync(path.join(root, '.eslintrc.json'), '{'), false],
    ['eslint-array', root => fs.writeFileSync(path.join(root, '.eslintrc.json'), '[]'), true],
    ['eslint-string', root => fs.writeFileSync(path.join(root, '.eslintrc.json'), '"invalid"'), true],
    ['eslint-null', root => fs.writeFileSync(path.join(root, '.eslintrc.json'), 'null'), false],
    ['eslint-direct-deep', root => fs.writeFileSync(path.join(root, '.eslintrc.json'), JSON.stringify({ extends: 'next/core-web-vitals', settings: { next: {rootDir: deepPattern} } })), true],
    ['eslint-override-deep', root => fs.writeFileSync(path.join(root, '.eslintrc.json'), JSON.stringify({ extends: 'next/core-web-vitals', overrides: [{ files: ['*.js'], settings: { next: {rootDir: deepPattern} } }] })), true],
    ['eslint-extends-deep', root => {
      fs.writeFileSync(path.join(root, '.eslintrc.json'), JSON.stringify({ extends: ['next/core-web-vitals', './inherited.json'] }));
      fs.writeFileSync(path.join(root, 'inherited.json'), JSON.stringify({ settings: { next: {rootDir: deepPattern} } }));
    }, true],
    ['eslint-alternative-cjs-deep', root => fs.writeFileSync(path.join(root, '.eslintrc.cjs'), `module.exports = ${JSON.stringify({ extends: 'next/core-web-vitals', settings: { next: {rootDir: deepPattern} } })};\n`), true],
    ['eslint-descendant-deep', root => fs.writeFileSync(path.join(root, 'app/.eslintrc.json'), JSON.stringify({ settings: { next: {rootDir: deepPattern} } })), true],
  ]) {
    const root = fixture();
    roots.push(root);
    change(root);
    guardCall(`guard-${name}`, root);
    if (actualLint) run(`standard-lint-${name}`, process.execPath, [npmCli, 'run', 'lint', '--', '--file', 'app/page.js'], { cwd: root, env: { ...process.env, NEXT_TELEMETRY_DISABLED: '1' } });
  }
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'batch9-dependencies-behavior-graph-'));
  roots.push(root);
  const callers = ['@jest/core', 'jest-cli', 'jest-config', 'jest-message-util'].map(name => ({ name, version: '30.5.2' }));
  const reports = [
    ['valid-control', JSON.stringify(callers)],
    ['absent-output', ''], ['invalid-json', '['], ['empty-array', '[]'], ['null', 'null'], ['object', '{}'],
    ['missing-caller', JSON.stringify(callers.slice(1))],
    ...[null, true, 0, {}, [], { name: 'dependency' }, { name: 1, version: '1.2.3' }, { name: '   ', version: '1.2.3' }].map((row, index) => [`invalid-row-${index}`, JSON.stringify([...callers, row])]),
    ...['01.2.3', '1.2.03', 'v1.2.3', '=1.2.3', ' 1.2.3', '1.2.3 ', '1.2.3-01', '1.2.3-9007199254740992', '1.2.3-9007199254740993', '9007199254740992.1.1', '1.2.9007199254740992', '1.2.3\u0000', '1.2.3\n', '1.2.3+build.001', '1.2.3-rc.1+build.001'].map((version,index) => [`version-${index}`, JSON.stringify([...callers, { name: 'dependency', version }])]),
    ...['braces', 'micromatch'].map(name => [`excluded-${name}`, JSON.stringify([...callers, { name, version: '3.0.3' }])]),
    ['valid-builtin-name', JSON.stringify([...callers, {name:'fs',version:'3.0.3'}])],
    ...['.invalid','@scope/.invalid','@scope/bad%20name','@scope/node_modules/invalid','braces\t'].map((name,index) => [`additional-hostile-name-${index}`, JSON.stringify([...callers,{name,version:'3.0.3'}])]),
    ['whitespace-excluded-braces', JSON.stringify([...callers, { name: 'braces ', version: '3.0.3' }])],
    ...['braces\n', 'braces\r', 'braces\u2028', 'braces\u2029', 'braces\r\n', '@scope/bad name', 'bra ces', '', '@scope/', '.braces', '_braces', 'node_modules', 'favicon.ico'].map((name,index) => [`hostile-name-${index}`, JSON.stringify([...callers, {name,version:'3.0.3'}])]),
  ];
  for (const [label, report] of reports) {
    const npmReport = path.join(root, 'report.cjs');
    fs.writeFileSync(npmReport, `process.stdout.write(${JSON.stringify(report)});\n`);
    run(`graph-${label}`, process.execPath, ['--test', '--test-name-pattern=^installed Jest', graph], { cwd: frontend,
      env: { PATH: process.env.PATH, npm_execpath: npmReport } });
  }
} finally {
  const sourceAfter = require('./control_contract.cjs').sourceIdentity(__filename, false);
  if (JSON.stringify(sourceBefore) !== JSON.stringify(sourceAfter)) failures.push('source-changed-during-execution');
  const record = { generated_by: __filename, generator_sha256: sourceBefore.generator_sha256, generated_at: new Date().toISOString(),
    source_before: sourceBefore, source_after: sourceAfter,
    source: { head: spawnSync('git', ['rev-parse', 'HEAD'], {cwd: repo, encoding: 'utf8'}).stdout.trim(),
      guard_sha256: hash(fs.readFileSync(guard)), graph_sha256: hash(fs.readFileSync(graph)),
      package_sha256: hash(fs.readFileSync(path.join(frontend, 'package.json'))), lock_sha256: hash(fs.readFileSync(path.join(frontend, 'package-lock.json'))) },
    runtime: {node: process.version, platform: process.platform, arch: process.arch}, fixture_roots: roots, results, expectationFailures:failures };
  fs.writeFileSync(path.join(__dirname, 'behavior-accepted-control-results-review-'+Date.now()+'.json'), JSON.stringify(record, null, 2) + '\n');
  for (const root of roots) fs.rmSync(root, { recursive: true, force: true });
}

console.log(JSON.stringify({controlRunnerCompleted:true, expectationFailures:failures}));
if (failures.length) process.exitCode = 1;
