'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const base = __dirname, front = '/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app/frontend';
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const manifest = JSON.parse(fs.readFileSync(path.join(front, 'scripts/tooling-repairs.json'))), output = [];
const initialSourceHashes = Object.fromEntries(['package.json','package-lock.json','scripts/apply-tooling-repairs.cjs','scripts/tooling-repairs.json'].map(file => [file, hash(fs.readFileSync(path.join(front, file)))]));
const json = (root, file) => JSON.parse(fs.readFileSync(path.join(root, file)));
const edit = (root, file, fn) => { const d = json(root, file); fn(d); fs.writeFileSync(path.join(root, file), JSON.stringify(d)); };
function fixture(cold = true) {
  const root = fs.mkdtempSync(path.join(base, 'link-graph-case-')); fs.mkdirSync(path.join(root, 'scripts')); fs.mkdirSync(path.join(root, 'node_modules'));
  for (const file of ['package.json', 'package-lock.json']) fs.copyFileSync(path.join(front, file), path.join(root, file));
  for (const file of ['tooling-repairs.json', 'apply-tooling-repairs.cjs']) fs.copyFileSync(path.join(front, 'scripts', file), path.join(root, 'scripts', file));
  for (const p of manifest.packages) for (const entry of p.entries) { fs.mkdirSync(path.dirname(path.join(root, entry)), { recursive: true }); fs.cpSync(path.join(front, entry), path.join(root, entry), { recursive: true, verbatimSymlinks: true }); }
  for (const name of ['eslint', '@humanwhocodes/config-array', 'flat-cache', 'minimatch', 'rimraf', 'glob']) {
    const entry = path.join(root, 'node_modules', name);
    if (['minimatch', 'rimraf', 'glob'].includes(name)) fs.cpSync(path.join(front, 'node_modules', name), entry, { recursive: true, verbatimSymlinks: true });
    else { fs.mkdirSync(entry, { recursive: true }); fs.copyFileSync(path.join(front, 'node_modules', name, 'package.json'), path.join(entry, 'package.json')); }
  }
  for (const file of ['eslint/lib/cli-engine/file-enumerator.js', 'eslint/lib/eslint/eslint-helpers.js', '@humanwhocodes/config-array/api.js', 'flat-cache/src/del.js']) { const target = path.join(root, 'node_modules', file); fs.mkdirSync(path.dirname(target), { recursive: true }); fs.copyFileSync(path.join(front, 'node_modules', file), target); }
  if (cold) for (const p of manifest.patches) for (const entry of manifest.packages.find(i => i.name === p.package).entries) {
    const file = path.join(root, entry, p.file);
    if (p.original_sha256 === null) fs.unlinkSync(file);
    else { let text = fs.readFileSync(file, 'utf8'); for (const e of [...p.edits].reverse()) { assert.equal(text.split(e.after).length, 2); text = text.replace(e.after, e.before); } assert.equal(hash(Buffer.from(text)), p.original_sha256); fs.writeFileSync(file, text); }
  }
  return root;
}
function snapshot(root) {
  const rows = {};
  function walk(relative) { const file = path.join(root, relative), s = fs.lstatSync(file); if (s.isSymbolicLink()) rows[relative] = { link: fs.readlinkSync(file) }; else if (s.isDirectory()) { rows[relative] = { directory: true, mode: s.mode & 0o777 }; for (const n of fs.readdirSync(file).sort()) walk(relative + '/' + n); } else rows[relative] = { hash: hash(fs.readFileSync(file)), mode: s.mode & 0o777 }; }
  walk('node_modules'); return rows;
}
function withFixture(fn, cold = true) { const root = fixture(cold); try { return fn(root); } finally { fs.rmSync(root, { recursive: true, force: true }); } }
function api(root) { return require(path.join(root, 'scripts/apply-tooling-repairs.cjs')); }
function refuse(label, mutate, diagnostic) {
  withFixture(root => {
    mutate(root); const before = snapshot(root); let error;
    try { api(root).applyRepairs(root); } catch (e) { error = String(e); }
    assert.ok(error, 'false green on ' + label); if (diagnostic) assert.match(error, diagnostic);
    assert.deepEqual(snapshot(root), before, 'no partial package writes ' + label);
    assert.equal(fs.existsSync(path.join(root, 'node_modules/.tooling-repair-lock')), false);
    output.push({ label, refused: true, packageTreeUnchanged: true, error });
  });
}
const link = 'node_modules/eslint-plugin-import/node_modules/.bin/semver';
withFixture(root => {
  const installed = api(root).applyRepairs(root), repeated = api(root).applyRepairs(root), checked = api(root).applyRepairs(root, { check: true });
  assert.equal(installed.changedFiles, 25); assert.equal(installed.packages.length, 7); assert.equal(repeated.changedFiles, 0); assert.equal(checked.changedFiles, 0);
  for (const p of manifest.packages) for (const [file, expected] of Object.entries(p.symlinks || {})) assert.equal(fs.readlinkSync(path.join(root, p.entries[0], file)), expected);
  output.push({ label: 'all-25-originals-repaired-repeat-check-with-exact-links', installed, repeated, checked });
});
for (const [label, target] of [['changed-link', '../semver/package.json'], ['absolute-link', '/owned/no-target'], ['escaping-link', '../../../../outside'], ['dangling-link', '../semver/bin/missing']]) refuse(label, root => { const file = path.join(root, link); fs.unlinkSync(file); fs.symlinkSync(target, file); }, /changed CLI link/);
refuse('missing-link', root => fs.unlinkSync(path.join(root, link)), /ENOENT/);
refuse('regular-file-instead-of-link', root => { const file = path.join(root, link); fs.unlinkSync(file); fs.writeFileSync(file, 'unexpected'); }, /CLI symlink required/);
refuse('symlink-bin-ancestor', root => { const from = path.dirname(path.join(root, link)), to = path.join(root, 'owned-bin'); fs.renameSync(from, to); fs.symlinkSync(to, from); }, /symlink refused/);
refuse('undeclared-bin-link', root => fs.symlinkSync('../semver/bin/semver.js', path.join(root, 'node_modules/eslint-plugin-import/node_modules/.bin/extra')), /symlink refused/);
refuse('undeclared-package-link', root => fs.symlinkSync('index.js', path.join(root, 'node_modules/eslint-plugin-react/extra.js')), /symlink refused/);
const target = 'node_modules/eslint-plugin-import/node_modules/semver/bin/semver.js';
refuse('missing-link-target', root => fs.unlinkSync(path.join(root, target)), /absent path/);
refuse('changed-link-target-bytes', root => fs.appendFileSync(path.join(root, target), '\n// drift'), /upstream bytes changed/);
refuse('nonexecutable-link-target', root => fs.chmodSync(path.join(root, target), 0o644), /executable mode/);
refuse('symlink-link-target', root => { const from = path.join(root, target), to = path.join(root, 'owned-cli'); fs.renameSync(from, to); fs.symlinkSync(to, from); }, /symlink refused/);
for (const value of [null, false, 0, '', [], {}, { 'node_modules/.bin/semver': '/outside' }, { 'node_modules/.bin/semver': '../../../../outside' }, { 'node_modules/.bin/new': '../semver/bin/semver.js' }]) refuse('bad-link-map-' + JSON.stringify(value), root => edit(root, 'scripts/tooling-repairs.json', d => { d.packages.find(p => p.name === 'eslint-plugin-import').symlinks = value; }), /CLI link inventory/);
refuse('link-map-on-unrelated-package', root => edit(root, 'scripts/tooling-repairs.json', d => { d.packages.find(p => p.name === 'deepmerge').symlinks = { 'node_modules/.bin/extra': '../index.js' }; }), /CLI link inventory/);
for (const [caller, dependency, version] of [['eslint','minimatch','3.1.5'],['@eslint/eslintrc','minimatch','3.1.5'],['@humanwhocodes/config-array','minimatch','3.1.5'],['eslint-plugin-import','minimatch','3.1.5'],['eslint-plugin-react','minimatch','3.1.5'],['eslint-plugin-jsx-a11y','minimatch','3.1.5'],['flat-cache','rimraf','3.0.2'],['rimraf','glob','7.2.3']]) refuse('physical-shadow-' + caller.replaceAll('/', '_'), root => { const directory = path.join(root, 'node_modules', caller, 'node_modules', dependency); fs.mkdirSync(directory, { recursive: true }); fs.writeFileSync(path.join(directory, 'package.json'), JSON.stringify({ name: dependency, version, main: 'index.js' })); fs.writeFileSync(path.join(directory, 'index.js'), 'module.exports={};'); }, /unreviewed resolved matcher/);
for (const [caller, dependency, version] of [['eslint/lib/cli-engine','minimatch','3.1.5'],['eslint/lib/eslint','minimatch','3.1.5'],['flat-cache/src','rimraf','3.0.2'],['rimraf/dist/commonjs','glob','7.2.3']]) refuse('deep-physical-shadow-' + caller.replaceAll('/', '_'), root => { const directory = path.join(root, 'node_modules', caller, 'node_modules', dependency); fs.mkdirSync(directory, { recursive: true }); fs.writeFileSync(path.join(directory, 'package.json'), JSON.stringify({ name: dependency, version, main: 'index.js' })); fs.writeFileSync(path.join(directory, 'index.js'), 'module.exports={};'); }, /unreviewed resolved matcher/);
refuse('missing-actual-requester', root => fs.unlinkSync(path.join(root, 'node_modules/eslint/lib/cli-engine/file-enumerator.js')), /absent path/);
for (const [name, version] of [['minimatch','3.1.5'],['glob','7.2.3'],['rimraf','3.0.2']]) refuse('locked-old-' + name, root => edit(root, 'package-lock.json', d => { d.packages['node_modules/unreviewed/node_modules/' + name] = { version, dev: true }; }), /incompatible matcher graph/);
refuse('missing-reviewed-matcher', root => edit(root, 'package-lock.json', d => { delete d.packages['node_modules/minimatch']; }), /missing reviewed minimatch/);
refuse('nondev-reviewed-matcher', root => edit(root, 'package-lock.json', d => { d.packages['node_modules/minimatch'].dev = false; }), /incompatible matcher graph/);
refuse('unexpected-nested-plugin-source', root => fs.writeFileSync(path.join(root, 'node_modules/eslint-plugin-react/node_modules/unreviewed.js'), 'module.exports={};'), /unexpected package file/);
refuse('changed-plugin-source', root => fs.appendFileSync(path.join(root, 'node_modules/eslint-plugin-react/lib/rules/no-danger.js'), '\n// drift'), /upstream bytes changed/);
refuse('missing-new-package-inventory', root => edit(root, 'scripts/tooling-repairs.json', d => { d.packages = d.packages.filter(p => p.name !== '@eslint/eslintrc'); }), /complete package inventory/);
for (const [dependency, file] of [['minimatch', 'dist/commonjs/index.js'], ['rimraf', 'dist/commonjs/index.js'], ['glob', 'dist/commonjs/index.min.js']]) {
  refuse('canonical-entry-bytes-' + dependency, root => fs.appendFileSync(path.join(root, 'node_modules', dependency, file), '\n// unreviewed'), /matcher executable bytes changed/);
  refuse('canonical-entry-symlink-' + dependency, root => { const from = path.join(root, 'node_modules', dependency, file), to = path.join(root, 'owned-entry.js'); fs.renameSync(from, to); fs.symlinkSync(to, from); }, /unreviewed matcher executable|symlink refused/);
}
withFixture(root => {
  fs.rmSync(path.join(root, 'node_modules'), { recursive: true }); fs.mkdirSync(path.join(root, 'node_modules'));
  const result = api(root).applyRepairs(root, { production: true }); assert.equal(result.absentPackages.length, 7); assert.equal(result.changedFiles, 0); assert.deepEqual(result.packages, []);
  assert.throws(() => api(root).applyRepairs(root, { check: true }), /absent matcher caller/);
  output.push({ label: 'production-omission-is-explicit', result, fullCheckRefused: true });
}, false);
for (const [file, digest] of Object.entries(initialSourceHashes)) assert.equal(hash(fs.readFileSync(path.join(front, file))), digest, 'frozen source bytes ' + file);
const record = { at: new Date().toISOString(), cases: output.length, sourceHashes: initialSourceHashes, output };
fs.writeFileSync(path.join(base, process.argv[2] || 'link-graph-results.json'), JSON.stringify(record, null, 2) + '\n', { flag: 'wx' });
console.log(JSON.stringify({ cases: output.length, refusedWithoutPartialWrites: output.filter(r => r.refused).length, sourceHashes: record.sourceHashes }));
