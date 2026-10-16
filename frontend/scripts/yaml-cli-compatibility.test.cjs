'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createRequire } = require('node:module');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');
const app = createRequire(require.resolve('../package.json'));
const nyc = createRequire(app.resolve('@istanbuljs/load-nyc-config/package.json'));
const yamlPackage = nyc.resolve('js-yaml/package.json');
const cli = path.join(path.dirname(yamlPackage), 'bin/js-yaml.js');
function run(args, input = '') {
 const child = spawnSync(process.execPath, [cli, ...args], { input, encoding: 'utf8', timeout: 5000 });
 assert.equal(child.signal, null); assert.equal(child.error, undefined);
 return child;
}
test('legacy CLI retains executable mode for direct invocation', () => {
 assert.ok(fs.statSync(cli).mode & 0o111);
 const child = spawnSync(cli, ['--version'], { encoding: 'utf8', timeout: 5000 });
 assert.equal(child.error, undefined); assert.equal(child.status, 0); assert.equal(child.stderr, '');
 assert.equal(child.stdout.trim(), JSON.parse(fs.readFileSync(yamlPackage)).version);
});
test('legacy CLI succeeds with deprecations fatal and normal success stderr empty', () => {
 const child = spawnSync(process.execPath, ['--throw-deprecation', cli], {
  input: 'all: true\n', encoding: 'utf8', timeout: 5000,
 });
 assert.equal(child.error, undefined); assert.equal(child.status, 0); assert.equal(child.stderr, '');
 assert.deepEqual(JSON.parse(child.stdout), { all: true });
 assert.equal(run([], 'all: true\n').stderr, '');
});
test('legacy argument errors retain usage on stdout and diagnostic on stderr', () => {
 const child = run(['--unknown-option']); assert.equal(child.status, 2);
 assert.match(child.stdout, /^usage: js-yaml/); assert.match(child.stderr, /^js-yaml: error:/);
});
for (const flag of ['--version', '-v']) {
 test(`NYC js-yaml CLI ${flag} prints its actual package version`, () => {
  const child = run([flag]); assert.equal(child.status, 0);
  assert.equal(child.stdout.trim(), JSON.parse(fs.readFileSync(yamlPackage)).version);
 });
}
test('NYC YAML configuration loader retains nested arrays and booleans', async () => {
 const root = fs.mkdtempSync(path.join(os.tmpdir(), 'yaml-compatibility-'));
 try {
  fs.writeFileSync(path.join(root, 'package.json'), '{}');
  fs.writeFileSync(path.join(root, '.nycrc.yml'), 'all: true\ninclude: [src/**/*.ts]\nexclude: [generated/**]\n');
  const result = await app('@istanbuljs/load-nyc-config').loadNycConfig({ cwd: root });
  assert.equal(result.all, true); assert.deepEqual(result.include, ['src/**/*.ts']);
  assert.deepEqual(result.exclude, ['generated/**']);
 } finally { fs.rmSync(root, { recursive: true }); }
});
test('NYC js-yaml CLI retains stdin, hidden JSON, JSON-to-YAML and multi-document behavior', () => {
 for (const args of [[], ['-j'], ['--to-json']]) {
  const child = run(args, 'all: true\n'); assert.equal(child.status, 0);
  assert.deepEqual(JSON.parse(child.stdout), { all: true });
 }
 const json = run([], '{"all":true}'); assert.equal(json.status, 0); assert.equal(json.stdout.trim(), 'all: true');
 const multiple = run([], '---\na: 1\n---\na: 2\n'); assert.equal(multiple.status, 0);
 assert.deepEqual(JSON.parse(multiple.stdout), [{ a: 1 }, { a: 2 }]);
});
test('NYC js-yaml CLI retains help and bounded error exits', () => {
 for (const flag of ['-h', '--help']) {
  const help = run([flag]); assert.equal(help.status, 0); assert.match(help.stdout, /js-yaml/);
  assert.match(help.stdout, /--version/); assert.doesNotMatch(help.stdout, /--to-json/);
 }
 for (const args of [[], ['--compact'], ['--trace'], ['-c'], ['-t']]) {
  const invalid = run(args, 'a: [\n'); assert.equal(invalid.status, 1); assert.match(invalid.stderr, /YAMLException/);
 }
 assert.equal(run(['--unknown-option']).status, 2);
 const missing = run([path.join(os.tmpdir(), 'yaml-missing-' + process.pid)]);
 assert.equal(missing.status, 2); assert.match(missing.stderr, /File not found/);
});
