'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createRequire } = require('node:module');
const { pathToFileURL } = require('node:url');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');
const { ESLint, Linter } = require('eslint');
const baselineRules = require('./fixtures/lint-rules-before-matcher-migration.json');
const frontend = path.resolve(__dirname, '..');

test('every migrated caller resolves the modern matcher and cache traversal graph', () => {
  for (const name of ['eslint', '@eslint/eslintrc', '@humanwhocodes/config-array',
    'eslint-plugin-import', 'eslint-plugin-react', 'eslint-plugin-jsx-a11y']) {
    const caller = createRequire(require.resolve(`${name}/package.json`));
    assert.equal(caller('minimatch/package.json').version, '11.0.3', name);
    assert.equal(typeof caller('minimatch').minimatch, 'function');
  }
  const cache = createRequire(require.resolve('flat-cache/package.json'));
  assert.equal(cache('rimraf/package.json').version, '6.1.3');
  const remover = createRequire(cache.resolve('rimraf/package.json'));
  assert.equal(remover('glob/package.json').version, '14.0.3');
});

test('all 54 baseline lint rule settings survive for every supported source extension', async () => {
  const eslint = new ESLint({ cwd: frontend });
  for (const extension of ['js', 'jsx', 'ts', 'tsx', 'mjs', 'cjs']) {
    const config = await eslint.calculateConfigForFile(path.join(frontend, 'app', `__matcher_probe__.${extension}`));
    assert.deepEqual(config.rules, baselineRules, extension);
  }
  assert.equal(Object.keys(baselineRules).length, 54);
});

test('native ESM and CJS eslintrc exports retain override matching and exclusions', async () => {
  const root = path.dirname(require.resolve('@eslint/eslintrc/package.json'));
  const metadata = require('@eslint/eslintrc/package.json');
  const esm = await import(pathToFileURL(path.join(root, metadata.exports['.'].import)).href);
  for (const api of [esm, require('@eslint/eslintrc')]) {
    const matcher = api.Legacy.OverrideTester.create(['**/*.ts?(x)'], ['**/*.test.*'], frontend);
    assert.equal(matcher.test(path.join(frontend, 'app/owned.tsx')), true);
    assert.equal(matcher.test(path.join(frontend, 'app/owned.test.tsx')), false);
    assert.equal(matcher.test(path.join(frontend, 'app/owned.js')), false);
  }
});

test('actual configured rules still reject bad code and enforce suppression reasons', async () => {
  const eslint = new ESLint({ cwd: frontend });
  for (const [code, rule] of [
    ['export const value = data.total_debt ?? 0;', 'local/no-zero-fallback-on-published-figure'],
    ['// eslint-disable-next-line local/no-zero-fallback-on-published-figure\nexport const value = data.total_debt ?? 0;', 'local/require-reason-on-zero-fallback-disable'],
    ['export default function Page() { return <script src="/owned.js" />; }', '@next/next/no-sync-scripts'],
    ['export default function Page() { return <img src="/owned.png" />; }', 'jsx-a11y/alt-text'],
    ['export default function Page() { return <div>{[1].map(i => <span>{i}</span>)}</div>; }', 'react/jsx-key'],
    ['export default function Page({ ok }) { if (ok) useState(0); return null; }', 'react-hooks/rules-of-hooks'],
    ['export default {};', 'import/no-anonymous-default-export'],
  ]) {
    const [result] = await eslint.lintText(code, { filePath: path.join(frontend, 'app/__matcher_probe__.tsx') });
    assert.equal(result.fatalErrorCount, 0, JSON.stringify(result.messages));
    assert.ok(result.messages.some(message => message.ruleId === rule), `${rule} silently stopped checking`);
  }
  for (const code of [
    'export const value = data.total_debt ?? null;',
    '// eslint-disable-next-line local/no-zero-fallback-on-published-figure -- source explicitly publishes zero\nexport const value = data.total_debt ?? 0;',
  ]) {
    const [result] = await eslint.lintText(code, { filePath: path.join(frontend, 'app/__matcher_probe__.tsx') });
    assert.equal(result.fatalErrorCount, 0);
    assert.ok(!result.messages.some(message => message.ruleId?.startsWith('local/')));
  }
});

test('migrated import, React and accessibility pattern options remain executable', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'lint-matcher-rules-'));
  try {
    fs.mkdirSync(path.join(root, 'node_modules/pkg/private'), { recursive: true });
    fs.writeFileSync(path.join(root, 'package.json'), '{"name":"owned-lint-fixture","version":"1.0.0"}');
    fs.writeFileSync(path.join(root, 'node_modules/pkg/package.json'), '{"name":"pkg","version":"1.0.0","main":"index.js"}');
    fs.writeFileSync(path.join(root, 'node_modules/pkg/private/secret.js'), 'module.exports = 1;');
    for (const [plugin, rule, code, options, expected] of [
      ['import', 'no-internal-modules', 'import x from "pkg/private/secret";', { forbid: ['pkg/private/**'] }, 1],
      ['import', 'no-internal-modules', 'import x from "pkg/private/secret";', { allow: ['pkg/private/**'] }, 0],
      ['react', 'jsx-pascal-case', 'const x = <BAD_COMPONENT />;', { ignore: ['BAD_*'] }, 0],
      ['react', 'jsx-pascal-case', 'const x = <BAD_COMPONENT />;', { ignore: ['OTHER_*'] }, 1],
      ['jsx-a11y', 'label-has-associated-control', 'const x = <label>Name<OwnedInput /></label>;', { controlComponents: ['Owned*'], assert: 'nesting' }, 0],
      ['jsx-a11y', 'label-has-associated-control', 'const x = <label>Name<OwnedInput /></label>;', { controlComponents: ['Other*'], assert: 'nesting' }, 1],
    ]) {
      const lint = new Linter();
      lint.defineRule('probe', require(`eslint-plugin-${plugin}`).rules[rule]);
      const messages = lint.verify(code, { parserOptions: { ecmaVersion: 2022, sourceType: 'module', ecmaFeatures: { jsx: true } },
        rules: { probe: ['error', options] } }, { filename: path.join(root, 'input.jsx') });
      assert.ok(!messages.some(message => message.fatal));
      assert.equal(messages.length, expected, `${plugin}/${rule}: ${JSON.stringify(messages)}`);
    }
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test('modern matcher handles the former legacy backtracking input in a bounded child', () => {
  const entry = require.resolve('minimatch');
  const script = `const assert=require('node:assert/strict');const {minimatch}=require(${JSON.stringify(entry)});assert.equal(minimatch('a'.repeat(32),'*a'.repeat(12)+'b'),false);`;
  const child = spawnSync(process.execPath, ['--max-old-space-size=64', '-e', script], { encoding: 'utf8', timeout: 2000 });
  assert.ifError(child.error); assert.equal(child.signal, null); assert.equal(child.status, 0, child.stderr);
});

test('existing file-entry cache still detects same-size content changes with preserved mtime', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'lint-matcher-cache-'));
  try {
    const entry = require('file-entry-cache');
    const file = path.join(root, 'owned.js');
    fs.writeFileSync(file, 'one');
    const cache = entry.create('entries', root, true);
    assert.equal(cache.getFileDescriptor(file).changed, true); cache.reconcile();
    const restored = entry.create('entries', root, true);
    assert.equal(restored.getFileDescriptor(file).changed, false);
    const stat = fs.statSync(file); fs.writeFileSync(file, 'two'); fs.utimesSync(file, stat.atime, stat.mtime);
    assert.equal(restored.getFileDescriptor(file).changed, true);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test('scoped cache remover deletes literal paths and preserves directory symlink targets', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'lint-matcher-remover-'));
  try {
    const flat = require('flat-cache');
    const literal = path.join(root, 'entry[1]'), other = path.join(root, 'entry1');
    fs.mkdirSync(path.join(literal, 'nested'), { recursive: true });
    fs.writeFileSync(path.join(literal, 'nested/owned'), 'owned'); fs.writeFileSync(other, 'retain');
    flat.clearCacheById('entry[1]', root);
    assert.equal(fs.existsSync(literal), false); assert.equal(fs.readFileSync(other, 'utf8'), 'retain');
    const target = path.join(root, 'target'); fs.mkdirSync(target); fs.writeFileSync(path.join(target, 'sentinel'), 'retain');
    const link = path.join(root, 'link'); fs.symlinkSync(target, link);
    flat.clearCacheById('link', root);
    assert.equal(fs.existsSync(link), false); assert.equal(fs.readFileSync(path.join(target, 'sentinel'), 'utf8'), 'retain');
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});
