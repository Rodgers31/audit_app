'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const { createRequire } = require('node:module');
const { test } = require('node:test');
const { applyRepairs } = require('./apply-tooling-repairs.cjs');
const patchSet = require('./tooling-repairs.json');
const frontend = path.resolve(__dirname, '..');
const installer = require.resolve('./apply-tooling-repairs.cjs');

function fixture() {
 const root = fs.mkdtempSync(path.join(os.tmpdir(), 'tooling-repair-'));
 fs.copyFileSync(path.join(frontend, 'package-lock.json'), path.join(root, 'package-lock.json'));
 fs.mkdirSync(path.join(root, 'node_modules'));
 for (const inventory of patchSet.packages) for (const entry of inventory.entries) {
  fs.mkdirSync(path.dirname(path.join(root, entry)), { recursive: true });
  fs.cpSync(path.join(frontend, entry), path.join(root, entry), { recursive: true });
 }
 for (const patch of patchSet.patches) {
  const target = path.join(root, patchSet.packages.find(p => p.name === patch.package).entries[0], patch.file);
  if (patch.original_sha256 === null) fs.unlinkSync(target);
  else {
   let source = fs.readFileSync(target, 'utf8');
   for (const edit of [...patch.edits].reverse()) source = source.replace(edit.after, edit.before);
   fs.writeFileSync(target, source);
  }
 }
 return root;
}
function withFixture(fn) {
 const root = fixture();
 try { return fn(root); } finally { fs.rmSync(root, { recursive: true }); }
}
function child(root, options) {
 return spawnSync(process.execPath, ['-e', `console.log(JSON.stringify(require(${JSON.stringify(installer)}).applyRepairs(${JSON.stringify(root)},${JSON.stringify(options)})))`],
  { env: { PATH: process.env.PATH }, encoding: 'utf8', timeout: 10000 });
}
function fixtureInstaller(root, mutate) {
 const scripts = path.join(root, 'scripts'); fs.mkdirSync(scripts);
 fs.copyFileSync(installer, path.join(scripts, 'apply-tooling-repairs.cjs'));
 const manifest = structuredClone(patchSet); mutate(manifest);
 fs.writeFileSync(path.join(scripts, 'tooling-repairs.json'), JSON.stringify(manifest));
 return require(path.join(scripts, 'apply-tooling-repairs.cjs'));
}
test('repair manifest cannot exempt an unpatched deepmerge resolved by a real Jest caller', () => withFixture(root => {
 applyRepairs(root);
 const entry = 'node_modules/@jest/core/node_modules/jest-config/node_modules/deepmerge';
 const nested = path.join(root, entry); fs.mkdirSync(path.dirname(nested), { recursive: true });
 fs.cpSync(path.join(root, 'node_modules/deepmerge'), nested, { recursive: true });
 for (const patch of patchSet.patches.filter(p => p.package === 'deepmerge')) {
  const file = path.join(nested, patch.file); let source = fs.readFileSync(file, 'utf8');
  for (const edit of [...patch.edits].reverse()) source = source.replace(edit.after, edit.before);
  fs.writeFileSync(file, source);
 }
 const lockPath = path.join(root, 'package-lock.json'); const lock = JSON.parse(fs.readFileSync(lockPath));
 lock.packages[entry] = { ...lock.packages['node_modules/deepmerge'] }; fs.writeFileSync(lockPath, JSON.stringify(lock));
 const core = createRequire(require.resolve('@jest/core'));
 const callerMetadata = path.join(path.dirname(nested), 'package.json');
 fs.copyFileSync(core.resolve('jest-config/package.json'), callerMetadata);
 const merge = createRequire(callerMetadata)('deepmerge');
 assert.equal(merge(Object.create(null), JSON.parse('{"__proto__":{"unpatched":true}}')).unpatched, true);
 const excluded = fixtureInstaller(root, manifest => {
  manifest.packages.find(p => p.name === 'deepmerge').otherEntries = { [entry]: '4.3.1' };
 });
 assert.throws(() => excluded.applyRepairs(root, { check: true }), /reviewed YAML4 exception/);
}));
for (const name of ['braces', 'js-yaml', 'deepmerge']) {
 test(`repair manifest rejects malformed or unapproved ${name} exclusions`, () => {
  for (const value of [false, 0, '', null, [], ['unexpected'], 17, 'unexpected', {}]) withFixture(root => {
   applyRepairs(root);
   const isolated = fixtureInstaller(root, manifest => { manifest.packages.find(p => p.name === name).otherEntries = value; });
   assert.throws(() => isolated.applyRepairs(root, { check: true }), /reviewed YAML4 exception/);
  });
 });
}
test('YAML4 exclusion is limited to its exact reviewed path and version', () => {
 for (const otherEntries of [
  { 'node_modules/js-yaml': '4.3.3' },
  { 'node_modules/unreviewed/node_modules/js-yaml': '4.3.2' },
  { 'node_modules/js-yaml': '4.3.2', 'node_modules/unreviewed/node_modules/js-yaml': '3.15.2' },
 ]) withFixture(root => {
  applyRepairs(root);
  const lockPath = path.join(root, 'package-lock.json'); const lock = JSON.parse(fs.readFileSync(lockPath));
  for (const [entry, version] of Object.entries(otherEntries)) lock.packages[entry] = { version, dev: true };
  fs.writeFileSync(lockPath, JSON.stringify(lock));
  const isolated = fixtureInstaller(root, manifest => { manifest.packages.find(p => p.name === 'js-yaml').otherEntries = otherEntries; });
  assert.throws(() => isolated.applyRepairs(root, { check: true }), /reviewed YAML4 exception/);
 });
});
test('cold upstream install applies all reviewed repaired files, reads back and repeats idempotently', () => withFixture(root => {
 assert.throws(() => applyRepairs(root, { check: true }), /unpatched/);
 assert.equal(applyRepairs(root).changedFiles, 10);
 assert.equal(applyRepairs(root).changedFiles, 0);
 assert.equal(applyRepairs(root, { check: true }).changedFiles, 0);
 assert.equal(fs.existsSync(path.join(root, 'node_modules/.tooling-repair-lock')), false);
}));
for (const [name, mutate, diagnostic] of [
 ['argparse traversal entry', root => { const p=path.join(root,'package-lock.json'); const d=JSON.parse(fs.readFileSync(p)); d.packages['../node_modules/argparse']={version:'2.0.1',dev:true}; fs.writeFileSync(p,JSON.stringify(d)); }, /unsafe package path/],
 ['unreviewed nested YAML version', root => { const p=path.join(root,'package-lock.json'); const d=JSON.parse(fs.readFileSync(p)); d.packages['node_modules/extra/node_modules/js-yaml']={version:'3.15.1',dev:true}; fs.writeFileSync(p,JSON.stringify(d)); }, /unexpected locked locations/],
 ['retired sprintf lock entry', root => { const p=path.join(root,'package-lock.json'); const d=JSON.parse(fs.readFileSync(p)); d.packages['node_modules/sprintf-js']={version:'1.0.3',dev:true}; fs.writeFileSync(p,JSON.stringify(d)); }, /retired sprintf-js/],
 ['nonexecutable YAML CLI', root => fs.chmodSync(path.join(root,'node_modules/@istanbuljs/load-nyc-config/node_modules/js-yaml/bin/js-yaml.js'),0o644), /executable mode/],
 ['changed upstream source', root => fs.appendFileSync(path.join(root, 'node_modules/braces/lib/parse.js'), '\n// drift'), /upstream bytes changed/],
 ['changed deepmerge bundle', root => fs.appendFileSync(path.join(root, 'node_modules/deepmerge/dist/cjs.js'), '\n// drift'), /upstream bytes changed/],
 ['missing deepmerge UMD bundle', root => fs.unlinkSync(path.join(root, 'node_modules/deepmerge/dist/umd.js')), /absent path/],
 ['missing deepmerge installation', root => fs.rmSync(path.join(root, 'node_modules/deepmerge'), { recursive: true }), /absent installed/],
 ['unexpected nested deepmerge', root => { const p=path.join(root,'package-lock.json'); const d=JSON.parse(fs.readFileSync(p)); d.packages['node_modules/extra/node_modules/deepmerge']={version:'4.3.1',dev:true}; fs.writeFileSync(p,JSON.stringify(d)); }, /unexpected locked locations/],
 ['symlinked deepmerge source', root => { const p=path.join(root,'node_modules/deepmerge/index.js'); const owned=path.join(root,'unrelated-deepmerge'); fs.renameSync(p,owned); fs.symlinkSync(owned,p); }, /symlink refused/],
 ['missing installed package', root => fs.rmSync(path.join(root, 'node_modules/braces'), { recursive: true }), /absent installed/],
 ['wrong package version', root => { const p = path.join(root, 'node_modules/braces/package.json'); const d = JSON.parse(fs.readFileSync(p)); d.version = '99.0.0'; fs.writeFileSync(p, JSON.stringify(d)); }, /incompatible installed/],
 ['malformed lock', root => fs.writeFileSync(path.join(root, 'package-lock.json'), '{'), /JSON/],
 ['empty lock inventory', root => fs.writeFileSync(path.join(root, 'package-lock.json'), JSON.stringify({ lockfileVersion: 3, packages: {} })), /reviewed argparse/],
 ['unsafe lock path', root => { const p = path.join(root, 'package-lock.json'); const d = JSON.parse(fs.readFileSync(p)); d.packages['../node_modules/braces'] = d.packages['node_modules/braces']; fs.writeFileSync(p, JSON.stringify(d)); }, /unsafe package path/],
 ['unreviewed locked version', root => { const p = path.join(root, 'package-lock.json'); const d = JSON.parse(fs.readFileSync(p)); d.packages['node_modules/braces'].version = '3.0.4'; fs.writeFileSync(p, JSON.stringify(d)); }, /incompatible locked/],
 ['symlinked source', root => { const p = path.join(root, 'node_modules/braces/lib/parse.js'); const owned = path.join(root, 'unrelated'); fs.renameSync(p, owned); fs.symlinkSync(owned, p); }, /symlink refused/],
 ['dangling helper symlink', root => fs.symlinkSync(path.join(root, 'missing'), path.join(root, 'node_modules/braces/lib/audit-bounds.js')), /symlink refused/],
 ['existing wrong helper', root => fs.writeFileSync(path.join(root, 'node_modules/braces/lib/audit-bounds.js'), 'unexpected'), /unexpected helper/],
]) {
 test(`installer refuses ${name} without applying any other target`, () => withFixture(root => {
  const retained = fs.readFileSync(path.join(root, 'node_modules/@istanbuljs/load-nyc-config/node_modules/js-yaml/bin/js-yaml.js'));
  mutate(root);
  const result = child(root, {});
  assert.equal(result.status, 1); assert.equal(result.signal, null); assert.match(result.stderr, diagnostic);
  assert.deepEqual(fs.readFileSync(path.join(root, 'node_modules/@istanbuljs/load-nyc-config/node_modules/js-yaml/bin/js-yaml.js')), retained);
  assert.equal(fs.existsSync(path.join(root, 'node_modules/.tooling-repair-lock')), false);
 }));
}
test('omit-dev install distinguishes absent tooling packages from applied repairs', () => withFixture(root => {
 for (const inventory of patchSet.packages) for (const entry of inventory.entries) fs.rmSync(path.join(root, entry), { recursive: true });
 const result = applyRepairs(root, { production: true });
 assert.deepEqual(result.packages, []); assert.equal(result.absentPackages.length, 3); assert.equal(result.changedFiles, 0);
 assert.throws(() => applyRepairs(root, { check: true }), /absent installed/);
}));
test('symlinked node_modules refuses before creating a lock in its target', () => withFixture(root => {
 const modules = path.join(root, 'node_modules'), other = path.join(root, 'other');
 fs.renameSync(modules, other); fs.symlinkSync(other, modules);
 assert.throws(() => applyRepairs(root), /real owned node_modules/);
 assert.equal(fs.existsSync(path.join(other, '.tooling-repair-lock')), false);
}));
test('invalid boolean modes cannot skip repair validation', () => withFixture(root => {
 for (const check of ['false', 1, null]) assert.throws(() => applyRepairs(root, { check }), /boolean modes/);
}));
test('held concurrent installer lock fails visibly and preserves the owner lock', () => withFixture(root => {
 const lock = path.join(root, 'node_modules/.tooling-repair-lock'); fs.mkdirSync(lock);
 const result = child(root, {}); assert.equal(result.status, 1); assert.match(result.stderr, /EEXIST/);
 assert.ok(fs.statSync(lock).isDirectory()); fs.rmdirSync(lock);
 assert.equal(applyRepairs(root).changedFiles, 10);
}));
test('two real installer processes cannot overlap patch publication', async () => {
 const root = fixture(); const ready = path.join(root, 'ready'), release = path.join(root, 'release');
 const script = `const fs=require('node:fs');const rename=fs.renameSync;let first=true;fs.renameSync=(...a)=>{if(first){first=false;fs.writeFileSync(${JSON.stringify(ready)},'ready');const end=Date.now()+5000;while(!fs.existsSync(${JSON.stringify(release)})){if(Date.now()>end)throw Error('gate timeout');Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,10);}}return rename(...a);};console.log(JSON.stringify(require(${JSON.stringify(installer)}).applyRepairs(${JSON.stringify(root)})));`;
 const worker = spawn(process.execPath, ['-e', script], { env: { PATH: process.env.PATH } });
 let stdout = '', stderr = ''; worker.stdout.on('data', b => { stdout += b; }); worker.stderr.on('data', b => { stderr += b; });
 const finished = new Promise(resolve => worker.on('close', (code, signal) => resolve({ code, signal })));
 try {
  const deadline = Date.now() + 5000;
  while (!fs.existsSync(ready) && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 20));
  assert.ok(fs.existsSync(ready), stderr);
  const competing = child(root, {}); assert.equal(competing.status, 1); assert.match(competing.stderr, /EEXIST/);
  fs.writeFileSync(release, 'release'); const result = await finished;
  assert.deepEqual(result, { code: 0, signal: null }); assert.equal(JSON.parse(stdout).changedFiles, 10);
  assert.equal(applyRepairs(root).changedFiles, 0);
 } finally { if (worker.exitCode === null) { worker.kill(); await finished; } fs.rmSync(root, { recursive: true }); }
});

test('production mode rejects absent traversal entries rather than reporting them omitted', () => withFixture(root => {
 const p = path.join(root, 'package-lock.json'); const d = JSON.parse(fs.readFileSync(p));
 d.packages['../node_modules/braces'] = d.packages['node_modules/braces']; fs.writeFileSync(p, JSON.stringify(d));
 const result = child(root, { production: true });
 assert.equal(result.status, 1); assert.match(result.stderr, /unsafe package path/);
}));
for (const file of ['index.js', 'lib/constants.js']) {
 test(`check refuses missing mandatory unmodified braces/${file}`, () => withFixture(root => {
  applyRepairs(root); fs.unlinkSync(path.join(root, 'node_modules/braces', file));
  const result = child(root, { check: true }); assert.equal(result.status, 1); assert.match(result.stderr, /absent path/);
 }));
}
test('check refuses changed main export even with unchanged name and version', () => withFixture(root => {
 applyRepairs(root); const p = path.join(root, 'node_modules/braces/package.json');
 const d = JSON.parse(fs.readFileSync(p)); d.main = 'lib/constants.js'; fs.writeFileSync(p, JSON.stringify(d));
 const result = child(root, { check: true }); assert.equal(result.status, 1); assert.match(result.stderr, /upstream bytes changed/);
}));
test('production mode refuses a dangling installed package link', () => withFixture(root => {
 fs.rmSync(path.join(root, 'node_modules/braces'), { recursive: true });
 fs.symlinkSync(path.join(root, 'missing'), path.join(root, 'node_modules/braces'));
 const result = child(root, { production: true }); assert.equal(result.status, 1); assert.match(result.stderr, /symlink refused/);
}));
