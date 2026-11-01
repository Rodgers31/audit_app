'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const { createRequire } = require('node:module');
const base = __dirname, front = '/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app/frontend';
const app = createRequire(path.join(front, 'package.json')), { Linter } = app('eslint'), espree = app('espree');
const stage = process.argv[2]; assert.ok(['raw', 'final'].includes(stage));
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const work = fs.mkdtempSync(path.join(base, 'plugin-cases-'));
const sourceFiles = JSON.parse(fs.readFileSync(path.join(base, 'legacy-caller-inventory.json'))).map(r => r.package + '/' + r.path);
const activeModules = stage === 'raw' ? path.join(base, 'cache-modern/raw-plugin/node_modules') : path.join(front, 'node_modules');
const sourceHashes = () => Object.fromEntries([...new Set(sourceFiles)].sort().map(p => [p, hash(fs.readFileSync(path.join(activeModules, p)))]));
const before = sourceHashes();
fs.mkdirSync(path.join(work, 'node_modules/pkg/private'), { recursive: true });
fs.mkdirSync(path.join(work, 'node_modules/pkg/public'), { recursive: true });
fs.writeFileSync(path.join(work, 'package.json'), JSON.stringify({ name: 'owned-rule-fixture', version: '1.0.0', devDependencies: { pkg: '1.0.0' } }));
fs.writeFileSync(path.join(work, 'node_modules/pkg/package.json'), JSON.stringify({ name: 'pkg', version: '1.0.0', main: 'index.js' }));
for (const file of ['index.js', 'private/secret.js', 'public/shared.js']) fs.writeFileSync(path.join(work, 'node_modules/pkg', file), 'module.exports=1;');
const cases = [];
function rule(plugin, name, code, options, expected) { cases.push({ kind: 'rule', plugin, name, code, options, expected }); }
const imp = 'eslint-plugin-import', react = 'eslint-plugin-react', a11y = 'eslint-plugin-jsx-a11y';
for (const [allow, expected] of [[['pkg/public/**'], 1], [['pkg/private/**'], 0]]) rule(imp, 'no-internal-modules', 'import x from "pkg/private/secret";', [{ allow }], expected);
for (const [forbid, expected] of [[['pkg/private/**'], 1], [['pkg/public/**'], 0]]) rule(imp, 'no-internal-modules', 'import x from "pkg/private/secret";', [{ forbid }], expected);
for (const [pattern, expected] of [[path.join(work, 'input.js'), 0], [path.join(work, 'elsewhere.js'), 1]]) rule(imp, 'no-import-module-exports', 'import x from "pkg"; module.exports = x;', [{ exceptions: [pattern] }], expected);
for (const [pattern, expected] of [['secret', 0], ['other', 1]]) rule(imp, 'no-namespace', 'import * as x from "pkg/private/secret";', [{ ignore: [pattern] }], expected);
for (const [pattern, expected] of [['pkg/private/**', 0], ['pkg/public/**', 1]]) rule(imp, 'no-unassigned-import', 'import "pkg/private/secret";', [{ allow: [pattern] }], expected);
for (const [pattern, expected] of [[path.join(work, 'input.js'), 0], [path.join(work, 'elsewhere.js'), 1]]) rule(imp, 'no-extraneous-dependencies', 'import x from "pkg/private/secret";', [{ devDependencies: [pattern] }], expected);
for (const [action, expected] of [['ignore', 0], ['enforce', 1]]) rule(imp, 'extensions', 'import x from "pkg/private/secret";', ['always', { ignorePackages: false, pathGroupOverrides: [{ pattern: 'pkg/**', action }] }], expected);
for (const [code, expected] of [['import x from "pkg/private/secret"; import fs from "fs";', 1], ['import fs from "fs"; import x from "pkg/private/secret";', 0]]) rule(imp, 'order', code, [{ groups: ['builtin', 'external', 'internal'], pathGroups: [{ pattern: 'pkg/**', group: 'internal', position: 'before' }], pathGroupsExcludedImportTypes: [] }], expected);
for (const [from, expected] of [['./node_modules/pkg/private/**', 1], ['./node_modules/pkg/public/**', 0]]) rule(imp, 'no-restricted-paths', 'import x from "pkg/private/secret";', [{ basePath: work, zones: [{ target: './', from }] }], expected);
for (const [pattern, expected] of [['Form*', 1], ['Other*', 0]]) rule(react, 'no-danger', 'const x = <FormInput dangerouslySetInnerHTML={{ __html: "x" }} />;', [{ customComponentNames: [pattern] }], expected);
for (const [pattern, expected] of [['BAD_*', 0], ['OTHER_*', 1]]) rule(react, 'jsx-pascal-case', 'const x = <BAD_COMPONENT />;', [{ ignore: [pattern] }], expected);
for (const [pattern, expected] of [['Form*', 0], ['Other*', 1]]) rule(react, 'jsx-handler-names', 'const x = <FormInput onClick={this.badHandler} />;', [{ ignoreComponentNames: [pattern] }], expected);
for (const [pattern, expected] of [['render*', 0], ['slot*', 1]]) rule(react, 'no-unstable-nested-components', 'function App() { return <Container renderPanel={() => <div />} />; }', [{ propNamePattern: pattern }], expected);
for (const [component, expected] of [['SafeWidget', 0], ['BadWidget', 1]]) rule(react, 'forbid-component-props', `const x = <${component} data-test="1" />;`, [{ forbid: [{ propNamePattern: 'data-*', allowedForPatterns: ['Safe*'] }] }], expected);
for (const [pattern, expected] of [['Input*', true], ['Other*', false]]) cases.push({ kind: 'utility', plugin: a11y, name: 'mayContainChildComponent', pattern, expected });
for (const [pattern, expected] of [['Input*', false], ['Other*', true]]) cases.push({ kind: 'utility', plugin: a11y, name: 'mayHaveAccessibleLabel', pattern, expected });
function normalized(messages) { if (messages === undefined) return undefined; return JSON.parse(JSON.stringify(messages).split(work).join('<fixture>')); }
function execute(profile, item) {
  const location = profile === 'baseline' ? path.join(base, 'baseline/node_modules') : activeModules;
  const file = path.join(location, item.plugin, 'lib', item.kind === 'rule' ? 'rules' : 'util', item.name + '.js');
  try {
    const implementation = require(file);
    if (item.kind === 'utility') {
      const text = item.name === 'mayContainChildComponent' ? '<label><InputControl /></label>' : '<InputControl />';
      const root = espree.parse(text, { ecmaVersion: 2022, ecmaFeatures: { jsx: true } }).body[0].expression;
      const value = item.name === 'mayContainChildComponent' ? implementation(root, item.pattern) : implementation(root, 1, [], node => node.name.name, [item.pattern]);
      assert.equal(value, item.expected);
      return { success: true, value };
    }
    const engine = new Linter(); engine.defineRule('review/' + item.name, implementation);
    const messages = engine.verify(item.code, { parserOptions: { ecmaVersion: 2022, sourceType: 'module', ecmaFeatures: { jsx: true } }, settings: { react: { version: '19.2.4' } }, rules: { ['review/' + item.name]: ['error', ...item.options] } }, { filename: path.join(work, 'input.js') });
    assert.equal(messages.length, item.expected, JSON.stringify(messages));
    assert.ok(!messages.some(m => m.fatal));
    return { success: true, messages: normalized(messages) };
  } catch (error) { return { success: false, error: String(error).split(work).join('<fixture>') }; }
}
try {
  const output = cases.map((item, index) => {
    const baseline = execute('baseline', item), installed = execute('installed', item);
    return { index, target: item.plugin + '/' + item.name, code: item.code, options: normalized(item.options), pattern: item.pattern, expected: item.expected, baseline, installed, equivalent: JSON.stringify(baseline) === JSON.stringify(installed) };
  });
  const after = sourceHashes(); assert.deepEqual(after, before, 'installed caller bytes stable during test');
  const result = { at: new Date().toISOString(), stage, activeModules, sourceHashes: before, cases: output.length, baselineFailures: output.filter(r => !r.baseline.success).length, installedFailures: output.filter(r => !r.installed.success).length, equivalents: output.filter(r => r.equivalent).length, output };
  fs.writeFileSync(path.join(base, 'plugin-callers-' + stage + '-results.json'), JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify(result, null, 2));
  assert.equal(result.baselineFailures, 0, 'every comparison baseline must be alive');
  if (stage === 'raw') assert.ok(result.installedFailures >= 20, 'raw callable/makeRe failures must be reproduced');
  else { assert.equal(result.installedFailures, 0); assert.equal(result.equivalents, result.cases); }
} finally { fs.rmSync(work, { recursive: true, force: true }); }
