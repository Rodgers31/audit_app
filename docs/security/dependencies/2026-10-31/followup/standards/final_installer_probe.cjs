'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { createRequire } = require('node:module');
const base = __dirname;
const front = '/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app/frontend';
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const manifest = JSON.parse(fs.readFileSync(path.join(front, 'scripts/tooling-repairs.json')));
const output = [];
function record(label, data) { output.push({ label, ...data }); console.log(JSON.stringify({ label, ...data })); }
function readJSON(root, file) { return JSON.parse(fs.readFileSync(path.join(root, file))); }
function writeJSON(root, file, data) { fs.writeFileSync(path.join(root, file), JSON.stringify(data)); }
function editManifest(root, fn) { const d = readJSON(root, 'scripts/tooling-repairs.json'); fn(d); writeJSON(root, 'scripts/tooling-repairs.json', d); }
function editLock(root, fn) { const d = readJSON(root, 'package-lock.json'); fn(d); writeJSON(root, 'package-lock.json', d); }
function fixture(label, cold = false) {
  const root = fs.mkdtempSync(path.join(base, 'final-fixture-' + label + '-'));
  fs.mkdirSync(path.join(root, 'scripts'));
  fs.mkdirSync(path.join(root, 'node_modules'));
  for (const file of ['apply-tooling-repairs.cjs', 'tooling-repairs.json']) fs.copyFileSync(path.join(front, 'scripts', file), path.join(root, 'scripts', file));
  fs.copyFileSync(path.join(front, 'package-lock.json'), path.join(root, 'package-lock.json'));
  for (const inventory of manifest.packages) for (const entry of inventory.entries) {
    fs.mkdirSync(path.dirname(path.join(root, entry)), { recursive: true });
    fs.cpSync(path.join(front, entry), path.join(root, entry), { recursive: true });
  }
  if (cold) for (const patch of manifest.patches) {
    const inventory = manifest.packages.find(p => p.name === patch.package);
    for (const entry of inventory.entries) {
      const file = path.join(root, entry, patch.file);
      if (patch.original_sha256 === null) fs.unlinkSync(file);
      else {
        let source = fs.readFileSync(file, 'utf8');
        for (const edit of [...patch.edits].reverse()) {
          assert.equal(source.split(edit.after).length, 2, 'unambiguous reversal ' + file);
          source = source.replace(edit.after, edit.before);
        }
        assert.equal(hash(Buffer.from(source)), patch.original_sha256, 'cold original digest ' + file);
        fs.writeFileSync(file, source);
      }
    }
  }
  return root;
}
function installer(root, file = 'apply-tooling-repairs.cjs') { return require(path.join(root, 'scripts', file)); }
function snapshot(root) {
  const entries = {};
  function walk(relative) {
    const file = path.join(root, relative), stat = fs.lstatSync(file);
    if (stat.isSymbolicLink()) entries[relative] = { link: fs.readlinkSync(file) };
    else if (stat.isDirectory()) { entries[relative] = { directory: true, mode: stat.mode & 0o777 }; for (const name of fs.readdirSync(file).sort()) walk(relative + '/' + name); }
    else entries[relative] = { sha256: hash(fs.readFileSync(file)), mode: stat.mode & 0o777 };
  }
  walk('node_modules'); return entries;
}
function owned(label, fn, cold = false) {
  const root = fixture(label, cold);
  try { return fn(root); } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
function reject(label, mutate, diagnostic, options = {}, cold = true) {
  owned(label, root => {
    mutate(root);
    const before = snapshot(root);
    let error;
    try { installer(root).applyRepairs(root, options); } catch (e) { error = e; }
    assert.ok(error, 'expected refusal for ' + label);
    if (diagnostic) assert.match(String(error), diagnostic);
    assert.deepEqual(snapshot(root), before, 'no partial package writes on preflight refusal ' + label);
    assert.equal(fs.existsSync(path.join(root, 'node_modules/.tooling-repair-lock')), false);
    record(label, { refused: true, diagnostic: String(error), packageTreeUnchanged: true });
  }, cold);
}
owned('repaired-positive', root => {
  // This physically copies the intended independent YAML4 CLI too, not just its lock metadata.
  fs.cpSync(path.join(front, 'node_modules/js-yaml'), path.join(root, 'node_modules/js-yaml'), { recursive: true });
  assert.equal(readJSON(root, 'node_modules/js-yaml/package.json').version, '4.3.2');
  const before = snapshot(root), api = installer(root);
  const checked = api.applyRepairs(root, { check: true }), repeated = api.applyRepairs(root);
  assert.equal(checked.packages.length, 3); assert.equal(checked.changedFiles, 0); assert.equal(repeated.changedFiles, 0);
  assert.deepEqual(snapshot(root), before);
  record('intended-exact-YAML4-positive', { checked, repeated, packageTreeUnchanged: true });
});
owned('cold-positive', root => {
  const api = installer(root), first = api.applyRepairs(root), repeated = api.applyRepairs(root), checked = api.applyRepairs(root, { check: true });
  assert.equal(first.changedFiles, 10); assert.equal(repeated.changedFiles, 0); assert.equal(checked.changedFiles, 0);
  assert.equal(first.packages.length, 3);
  record('cold-original-repair-idempotence', { first, repeated, checked });
}, true);
// Reproduce the pre-fix false green on original bytes and rerun the SAME metadata against the fixed helper.
owned('nested-exemption', root => {
  const nested = 'node_modules/@jest/core/node_modules/jest-config/node_modules/deepmerge';
  editManifest(root, d => { d.packages.find(p => p.name === 'deepmerge').otherEntries = { [nested]: '4.3.1' }; });
  editLock(root, d => { d.packages[nested] = { ...d.packages['node_modules/deepmerge'] }; });
  const dm = manifest.packages.find(p => p.name === 'deepmerge');
  for (const file of Object.keys(dm.files)) {
    const to = path.join(root, nested, file); fs.mkdirSync(path.dirname(to), { recursive: true });
    fs.copyFileSync(path.join(base, 'original/package', file), to);
  }
  const app = createRequire(path.join(front, 'package.json'));
  const caller = path.join(path.dirname(path.join(root, nested)), 'package.json');
  fs.copyFileSync(createRequire(app.resolve('@jest/core')).resolve('jest-config/package.json'), caller);
  const oldFile = 'pre-fix-helper.cjs';
  fs.copyFileSync(path.join(base, 'apply-tooling-repairs-before-exception.cjs.txt'), path.join(root, 'scripts', oldFile));
  const baseline = installer(root, oldFile).applyRepairs(root, { check: true });
  const req = createRequire(caller), merge = req('deepmerge');
  const poisoned = merge(Object.create(null), JSON.parse('{"__proto__":{"review_unpatched":true}}'));
  assert.equal(poisoned.review_unpatched, true);
  assert.equal(hash(fs.readFileSync(req.resolve('deepmerge'))), dm.files['dist/cjs.js'].original_sha256);
  const before = snapshot(root);
  assert.throws(() => installer(root).applyRepairs(root), /reviewed YAML4 exception/);
  assert.deepEqual(snapshot(root), before);
  assert.equal(fs.existsSync(path.join(root, 'node_modules/.tooling-repair-lock')), false);
  record('pre-fix-red-final-green-real-Jest-resolution', { baseline, resolvedSuffix: req.resolve('deepmerge').slice(root.length), inheritedMarker: poisoned.review_unpatched, originalCJSsha256: hash(fs.readFileSync(req.resolve('deepmerge'))), finalRefused: true, packageTreeUnchanged: true });
});
for (const name of ['braces', 'js-yaml', 'deepmerge']) for (const value of [false, 0, '', null, true, [], {}, 17, 'unexpected']) {
  reject('otherEntries-' + name + '-' + JSON.stringify(value), root => editManifest(root, d => { d.packages.find(p => p.name === name).otherEntries = value; }), /reviewed YAML4 exception/);
}
for (const [label, otherEntries] of [
  ['YAML-wrong-version', { 'node_modules/js-yaml': '4.3.3' }],
  ['YAML-wrong-path', { 'node_modules/extra/node_modules/js-yaml': '4.3.2' }],
  ['YAML-extra-copy', { 'node_modules/js-yaml': '4.3.2', 'node_modules/extra/node_modules/js-yaml': '3.15.2' }],
]) reject(label, root => {
  editManifest(root, d => { d.packages.find(p => p.name === 'js-yaml').otherEntries = otherEntries; });
  editLock(root, d => { for (const [entry, version] of Object.entries(otherEntries)) d.packages[entry] = { version, dev: true }; });
}, /reviewed YAML4 exception/);
reject('YAML-missing-exception', root => editManifest(root, d => { delete d.packages.find(p => p.name === 'js-yaml').otherEntries; }), /reviewed YAML4 exception/);
reject('YAML-mismatched-lock-version', root => editLock(root, d => { d.packages['node_modules/js-yaml'].version = '4.3.3'; }), /incompatible locked/);
reject('YAML-non-dev-exception', root => editLock(root, d => { d.packages['node_modules/js-yaml'].dev = false; }), /incompatible locked/);
reject('missing-third-inventory', root => editManifest(root, d => { d.packages = d.packages.filter(p => p.name !== 'deepmerge'); }), /complete package inventory/);
reject('missing-lock-file', root => fs.unlinkSync(path.join(root, 'package-lock.json')), /absent path/);
reject('malformed-lock', root => fs.writeFileSync(path.join(root, 'package-lock.json'), '{'), /JSON/);
reject('empty-lock', root => writeJSON(root, 'package-lock.json', { lockfileVersion: 3, packages: {} }), /reviewed argparse/);
reject('bad-lock-schema', root => editLock(root, d => { d.lockfileVersion = true; }), /lock package inventory/);
for (const file of ['index.js', 'dist/cjs.js', 'dist/umd.js']) reject('missing-deepmerge-' + file.replaceAll('/', '-'), root => fs.unlinkSync(path.join(root, 'node_modules/deepmerge', file)), /absent path/);
reject('changed-deepmerge-cjs', root => fs.appendFileSync(path.join(root, 'node_modules/deepmerge/dist/cjs.js'), '\n// unreviewed'), /upstream bytes changed/);
reject('changed-deepmerge-main', root => { const p = 'node_modules/deepmerge/package.json'; const d = readJSON(root, p); d.main = 'index.js'; writeJSON(root, p, d); }, /upstream bytes changed/);
reject('unexpected-deepmerge-file', root => fs.writeFileSync(path.join(root, 'node_modules/deepmerge/extra.js'), 'module.exports = {};'), /unexpected package file/);
reject('unreviewed-deepmerge-nested-lock', root => editLock(root, d => { d.packages['node_modules/extra/node_modules/deepmerge'] = { version: '4.3.1', dev: true }; }), /unexpected locked locations/);
reject('wrong-deepmerge-lock-version', root => editLock(root, d => { d.packages['node_modules/deepmerge'].version = '4.3.2'; }), /incompatible locked/);
reject('nondev-deepmerge-lock', root => editLock(root, d => { d.packages['node_modules/deepmerge'].dev = false; }), /incompatible locked/);
reject('unsafe-deepmerge-lock-path', root => editLock(root, d => { d.packages['../node_modules/deepmerge'] = { version: '4.3.1', dev: true }; }), /unsafe package path/);
reject('symlink-deepmerge-source', root => { const file = path.join(root, 'node_modules/deepmerge/index.js'), other = path.join(root, 'owned-source'); fs.renameSync(file, other); fs.symlinkSync(other, file); }, /symlink refused/);
reject('missing-deepmerge-full', root => fs.rmSync(path.join(root, 'node_modules/deepmerge'), { recursive: true }), /absent installed/);
for (const options of [{ check: 'false' }, { production: 'false' }, { check: 1 }, { production: null }]) reject('invalid-modes-' + JSON.stringify(options), () => {}, /boolean modes/, options);
owned('production-omission', root => {
  for (const p of manifest.packages) for (const entry of p.entries) fs.rmSync(path.join(root, entry), { recursive: true });
  const api = installer(root), omitted = api.applyRepairs(root, { production: true });
  assert.deepEqual(omitted.packages, []); assert.equal(omitted.absentPackages.length, 3); assert.equal(omitted.changedFiles, 0);
  assert.throws(() => api.applyRepairs(root, { check: true }), /absent installed/);
  record('production-omission-distinguished', { omitted, fullCheckRefused: true });
});
owned('present-production', root => {
  const result = installer(root).applyRepairs(root, { production: true });
  assert.equal(result.changedFiles, 10); assert.equal(result.absentPackages.length, 0);
  record('present-production-still-repairs', { result });
}, true);
const sourceHashes = Object.fromEntries(['package.json', 'package-lock.json', 'scripts/apply-tooling-repairs.cjs', 'scripts/tooling-repairs.json', 'scripts/deepmerge-boundary.test.cjs', 'scripts/tooling-repair-install.test.cjs'].map(file => [file, hash(fs.readFileSync(path.join(front, file)))]));
fs.writeFileSync(path.join(base, 'final-installer-probe-results.json'), JSON.stringify({ observedAt: new Date().toISOString(), sourceHashes, cases: output.length, output }, null, 2) + '\n', { flag: 'wx' });
console.log(JSON.stringify({ cases: output.length, success: true, sourceHashes }));
