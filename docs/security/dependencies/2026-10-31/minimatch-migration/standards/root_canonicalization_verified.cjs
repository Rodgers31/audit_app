'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), Module = require('node:module');
const base = __dirname, front = '/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app/frontend';
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const helperFile = path.join(front, 'scripts/apply-tooling-repairs.cjs');
const newSource = fs.readFileSync(helperFile, 'utf8');
let oldSource = newSource.replaceAll('  root = fs.realpathSync(root);\n', '');
const lockLine = "  const lockPath = path.join(root, 'node_modules', '.tooling-repair-lock');\n";
assert.equal(oldSource.split(lockLine).length, 2);
oldSource = oldSource.replace(lockLine, '').replace('  const { check = false } = options;\n', '  const { check = false } = options;\n' + lockLine);
assert.equal(hash(oldSource), '068a93d7f52424739f07adf3f4140ffb7daf172fcd44942e050725760f1f4b5e', 'exact previous reviewed helper');
const oldFile = path.join(base, 'apply-tooling-repairs-before-root-canonicalization.cjs.txt'); if (fs.existsSync(oldFile)) assert.equal(fs.readFileSync(oldFile, 'utf8'), oldSource); else fs.writeFileSync(oldFile, oldSource, { flag: 'wx' });
// Reuse only the already-reviewed fixture constructor; do not rerun its 52 scenarios.
const harness = fs.readFileSync(path.join(base, 'link_graph_probe.cjs'), 'utf8').split("const link = 'node_modules/eslint-plugin-import/node_modules/.bin/semver';")[0] + '\nmodule.exports={fixture};\n';
const setup = new Module(path.join(base, 'root-fixture-constructor.cjs')); setup.filename = path.join(base, 'root-fixture-constructor.cjs'); setup.paths = module.paths; setup._compile(harness, setup.filename);
const template = setup.exports.fixture(true);
console.log('Owned cold template captured; all remaining module reads use owned copies.');
const output = [];
function tree(root) {
  const entries = {};
  function walk(relative) { const absolute = path.join(root, relative), stat = fs.lstatSync(absolute); if (stat.isSymbolicLink()) entries[relative] = { link: fs.readlinkSync(absolute) }; else if (stat.isDirectory()) { entries[relative] = { directory: true, mode: stat.mode & 0o777 }; for (const name of fs.readdirSync(absolute).sort()) walk(path.join(relative, name)); } else entries[relative] = { sha256: hash(fs.readFileSync(absolute)), mode: stat.mode & 0o777 }; }
  walk(''); return entries;
}
function withCase(label, fn) {
  const owner = fs.mkdtempSync(path.join(base, 'canonical-root-case-')), root = path.join(owner, 'frontend');
  fs.cpSync(template, root, { recursive: true, verbatimSymlinks: true });
  const parentLink = path.join(owner, 'parent-alias'); fs.symlinkSync(owner, parentLink, 'dir');
  const alias = path.join(parentLink, 'frontend');
  try { return fn({ owner, root, alias, api: require(path.join(root, 'scripts/apply-tooling-repairs.cjs')) }); }
  finally { fs.rmSync(owner, { recursive: true, force: true }); }
}
function refusal(label, mutate, pattern) {
  withCase(label, state => {
    const supplied = mutate(state), before = tree(state.owner), diagnostics = [];
    for (const name of ['planRepairs', 'applyRepairs']) {
      let error; try { state.api[name](supplied); } catch (e) { error = String(e); }
      assert.ok(error, 'false green for ' + label + '/' + name); assert.match(error, pattern); diagnostics.push({ api: name, error });
      assert.deepEqual(tree(state.owner), before, 'no writes on refusal ' + label + '/' + name);
    }
    output.push({ label, refusedByBothAPIs: true, entireOwnedTreeUnchanged: true, diagnostics });
  });
}
try {
  withCase('ancestor-red-green', ({ owner, root, alias, api }) => {
    const oldFile = path.join(root, 'scripts/previous-helper.cjs'); fs.writeFileSync(oldFile, oldSource); const previous = require(oldFile);
    const before = tree(owner); const red = [];
    for (const name of ['planRepairs', 'applyRepairs']) { let error; try { previous[name](alias); } catch (e) { error = String(e); } assert.ok(error); assert.match(error, /unsafe package path/); red.push({ api: name, error }); assert.deepEqual(tree(owner), before); }
    const plan = api.planRepairs(alias); assert.equal(plan.operations.length, 25); assert.ok(plan.operations.every(operation => operation.target.startsWith(fs.realpathSync(root) + path.sep))); assert.deepEqual(tree(owner), before);
    const applied = api.applyRepairs(alias), checked = api.applyRepairs(alias, { check: true }), repeated = api.applyRepairs(root);
    assert.equal(applied.changedFiles, 25); assert.equal(applied.packages.length, 7); assert.equal(checked.changedFiles, 0); assert.equal(repeated.changedFiles, 0);
    assert.equal(fs.existsSync(path.join(root, 'node_modules/.tooling-repair-lock')), false);
    output.push({ label: 'ancestor-alias-RED-to-GREEN', previousHelperFailures: red, canonicalOperationTargets: true, applied, checked, repeated });
  });
  refusal('direct-root-symlink', ({ owner, root }) => { const direct = path.join(owner, 'direct-root'); fs.symlinkSync(root, direct, 'dir'); return direct; }, /real frontend root/);
  refusal('direct-modules-symlink-through-valid-ancestor', ({ owner, root, alias }) => { const modules = path.join(root, 'node_modules'), other = path.join(owner, 'other-modules'); fs.renameSync(modules, other); fs.symlinkSync(other, modules, 'dir'); return alias; }, /real owned node_modules/);
  for (const relative of ['node_modules/braces/lib', 'node_modules/deepmerge/index.js', 'node_modules/eslint/lib/cli-engine']) refusal('inner-link-' + relative, ({ owner, root, alias }) => { const file = path.join(root, relative), target = path.join(owner, 'owned-inner-target'); fs.renameSync(file, target); fs.symlinkSync(target, file); return alias; }, /symlink refused/);
  refusal('canonical-matcher-entry-link', ({ owner, root, alias }) => { const file = path.join(root, 'node_modules/minimatch/dist/commonjs/index.js'), target = path.join(owner, 'owned-entry.js'); fs.renameSync(file, target); fs.symlinkSync(target, file); return alias; }, /unsafe package path|unreviewed matcher executable|symlink refused/);
  withCase('omission-through-ancestor', ({ root, alias, api }) => {
    fs.rmSync(path.join(root, 'node_modules'), { recursive: true }); fs.mkdirSync(path.join(root, 'node_modules'));
    const plan = api.planRepairs(alias, { production: true }); assert.equal(plan.operations.length, 0); assert.equal(plan.absentPackages.length, 7);
    const omitted = api.applyRepairs(alias, { production: true }); assert.deepEqual(omitted.packages, []); assert.equal(omitted.absentPackages.length, 7); assert.equal(omitted.changedFiles, 0);
    assert.throws(() => api.applyRepairs(alias, { check: true }), /absent matcher caller/);
    output.push({ label: 'omission-through-ancestor', omitted, fullCheckRefused: true });
  });
  withCase('held-lock-through-ancestor', ({ root, alias, api }) => {
    const lock = path.join(root, 'node_modules/.tooling-repair-lock'); fs.mkdirSync(lock);
    assert.throws(() => api.applyRepairs(alias), /EEXIST/); assert.ok(fs.lstatSync(lock).isDirectory()); fs.rmdirSync(lock);
    assert.equal(api.applyRepairs(alias).changedFiles, 25);
    output.push({ label: 'canonical-held-lock-preserved', refusedConcurrentOwner: true, subsequentColdRepairFiles: 25 });
  });
  assert.equal(fs.readFileSync(helperFile, 'utf8'), newSource, 'source stayed frozen');
  const sourceHashes = Object.fromEntries(['package.json','package-lock.json','scripts/apply-tooling-repairs.cjs','scripts/tooling-repairs.json','scripts/tooling-repair-install.test.cjs','scripts/lint-matcher-migration.test.cjs','scripts/fixtures/lint-rules-before-matcher-migration.json'].map(file => [file, hash(fs.readFileSync(path.join(front, file)))]));
  const result = { at: new Date().toISOString(), cases: output.length, priorHelperSHA256: hash(oldSource), finalHelperSHA256: hash(newSource), sourceHashes, output };
  fs.writeFileSync(path.join(base, 'root-canonicalization-results.json'), JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify(result, null, 2));
} finally { fs.rmSync(template, { recursive: true, force: true }); }
