'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const Module = require('node:module');
const crypto = require('node:crypto');
const base = __dirname;
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const fromBaseline = Module.createRequire(path.join(base, 'baseline', 'anchor.cjs'));
function sourceModule(file, mapped) {
  const ownModule = { exports: {} };
  vm.runInThisContext(Module.wrap(fs.readFileSync(file, 'utf8')), { filename: file })(ownModule.exports, id => Object.hasOwn(mapped, id) ? mapped[id] : fromBaseline(id), ownModule, file, path.dirname(file));
  return ownModule.exports;
}
const wrapperFile = path.join(base, 'baseline-eslint-lint-result-cache.js');
const hashing = sourceModule(path.join(base, 'baseline-eslint-hash.js'), {});
const variants = [];
for (const [label, flat3] of [['flat3-rimraf6', true], ['flat4', false]]) {
  const root = path.join(base, 'cache-modern', label, 'node_modules');
  fs.mkdirSync(root, { recursive: true });
  fs.cpSync(path.join(base, 'baseline/node_modules/file-entry-cache'), path.join(root, 'file-entry-cache'), { recursive: true, errorOnExist: true });
  if (flat3) fs.cpSync(path.join(base, 'baseline/node_modules/flat-cache'), path.join(root, 'flat-cache'), { recursive: true, errorOnExist: true });
  variants.push({ label, req: Module.createRequire(path.join(root, 'file-entry-cache/package.json')) });
}
variants.unshift({ label: 'baseline-flat3-rimraf3', req: fromBaseline });
const outputs = [];
const caseFunctions = [
  ['metadata-roundtrip-and-mutation', (fec, root) => {
    const file = path.join(root, 'input.txt'); fs.writeFileSync(file, 'alpha');
    let cache = fec.create('cache-meta', root, false);
    assert.equal(cache.getFileDescriptor(file).changed, true); cache.reconcile();
    cache = fec.create('cache-meta', root, false);
    assert.equal(cache.getFileDescriptor(file).changed, false);
    fs.writeFileSync(file, 'changed-longer');
    assert.equal(cache.getFileDescriptor(file).changed, true); cache.reconcile();
    fs.unlinkSync(file);
    assert.equal(cache.getFileDescriptor(file).notFound, true); cache.reconcile();
    cache.destroy(); assert.equal(fs.existsSync(path.join(root, 'cache-meta')), false);
  }],
  ['checksum-detects-same-size-content-with-restored-mtime', (fec, root) => {
    const file = path.join(root, 'input.txt'); fs.writeFileSync(file, 'alpha');
    const stat = fs.statSync(file);
    let cache = fec.create('cache-content', root, true);
    assert.equal(cache.getFileDescriptor(file).changed, true); cache.reconcile();
    cache = fec.create('cache-content', root, true);
    assert.equal(cache.getFileDescriptor(file).changed, false);
    fs.writeFileSync(file, 'omega'); fs.utimesSync(file, stat.atime, stat.mtime);
    assert.equal(cache.getFileDescriptor(file).changed, true); cache.reconcile(); cache.destroy();
  }],
  ['literal-metachar-cache-filename', (fec, root) => {
    const file = path.join(root, 'input.txt'), cacheFile = path.join(root, 'cache[*]?.json');
    fs.writeFileSync(file, 'source'); fs.writeFileSync(path.join(root, 'cache1.json'), 'sentinel');
    const cache = fec.createFromFile(cacheFile, true); cache.getFileDescriptor(file); cache.reconcile();
    assert.equal(fs.existsSync(cacheFile), true); cache.destroy();
    assert.equal(fs.existsSync(cacheFile), false); assert.equal(fs.readFileSync(path.join(root, 'cache1.json'), 'utf8'), 'sentinel');
  }],
  ['malformed-cache-forces-recompute', (fec, root) => {
    const file = path.join(root, 'input.txt'); fs.writeFileSync(file, 'source'); fs.writeFileSync(path.join(root, 'corrupt-cache'), '{');
    const cache = fec.create('corrupt-cache', root, true);
    assert.equal(cache.getFileDescriptor(file).changed, true); cache.reconcile(); cache.destroy();
  }],
  ['actual-ESLint-cache-wrapper-metadata', (fec, root) => wrapperCase(fec, root, 'metadata')],
  ['actual-ESLint-cache-wrapper-content', (fec, root) => wrapperCase(fec, root, 'content')],
];
function wrapperCase(fec, root, strategy) {
  const Cache = sourceModule(wrapperFile, { 'file-entry-cache': fec, './hash': hashing, '../../package.json': JSON.parse(fs.readFileSync(path.join(base, 'baseline-eslint-package.json'))) });
  const file = path.join(root, 'input.js'), cacheFile = path.join(root, 'lint-cache'); fs.writeFileSync(file, 'let a = 1;\n');
  const config = { rules: { semi: [2] } }, result = { filePath: file, messages: [{ ruleId: 'semi', message: 'marker' }], source: 'let a = 1;\n', errorCount: 1, warningCount: 0 };
  let cache = new Cache(cacheFile, strategy); assert.equal(cache.getCachedLintResults(file, config), null);
  cache.setCachedLintResults(file, config, result); cache.reconcile();
  cache = new Cache(cacheFile, strategy);
  assert.deepEqual(cache.getCachedLintResults(file, config), result);
  assert.equal(cache.getCachedLintResults(file, { rules: { semi: [0] } }), null);
  fs.writeFileSync(file, 'let a = 123;\n'); assert.equal(cache.getCachedLintResults(file, config), null);
  const fixedFile = path.join(root, 'fixed.js'); fs.writeFileSync(fixedFile, 'let b=1;');
  cache.setCachedLintResults(fixedFile, config, { ...result, filePath: fixedFile, output: 'let b=2;' });
  cache.reconcile();
  const again = new Cache(cacheFile, strategy); assert.equal(again.getCachedLintResults(fixedFile, config), null);
  fs.unlinkSync(file); assert.throws(() => again.getCachedLintResults(file, config), /hashOfConfig/); again.reconcile();
}
for (const variant of variants) {
  const fec = variant.req('file-entry-cache');
  const flatReq = Module.createRequire(variant.req.resolve('flat-cache/package.json'));
  const delExport = flatReq('./src/del.js'), del = typeof delExport === 'function' ? delExport : delExport.del;
  const identity = { fileEntryCache: variant.req('file-entry-cache/package.json').version, flatCache: variant.req('flat-cache/package.json').version };
  if (variant.label !== 'flat4') {
    const rimrafReq = Module.createRequire(flatReq.resolve('rimraf/package.json'));
    const globReq = Module.createRequire(rimrafReq.resolve('glob/package.json'));
    Object.assign(identity, { rimraf: rimrafReq('./package.json').version, glob: globReq('./package.json').version, minimatch: globReq('minimatch/package.json').version });
  }
  const cases = [...caseFunctions,
    ['delete-literal-file-no-glob', (_, root) => {
      const file = path.join(root, 'cache[*].json'); fs.writeFileSync(file, 'literal'); fs.writeFileSync(path.join(root, 'cache1.json'), 'sentinel');
      assert.equal(del(file), true); assert.equal(del(file), false); assert.equal(fs.readFileSync(path.join(root, 'cache1.json'), 'utf8'), 'sentinel');
    }],
    ['delete-nested-directory', (_, root) => {
      const directory = path.join(root, 'cache-dir'); fs.mkdirSync(path.join(directory, 'nested'), { recursive: true }); fs.writeFileSync(path.join(directory, 'nested/file'), 'cache');
      assert.equal(del(directory), true); assert.equal(fs.existsSync(directory), false);
    }],
    ['delete-directory-symlink-preserves-target', (_, root) => {
      const target = path.join(root, 'owned-target'), link = path.join(root, 'cache-link'); fs.mkdirSync(target); fs.writeFileSync(path.join(target, 'sentinel'), 'retained'); fs.symlinkSync(target, link);
      const removed = del(link); assert.equal(fs.readFileSync(path.join(target, 'sentinel'), 'utf8'), 'retained'); assert.equal(removed, true); assert.equal(fs.existsSync(link), false);
    }],
  ];
  for (const [label, run] of cases) {
    const root = fs.mkdtempSync(path.join(base, 'cache-case-'));
    try { run(fec, root); outputs.push({ variant: variant.label, identity, case: label, pass: true }); }
    catch (error) { outputs.push({ variant: variant.label, identity, case: label, pass: false, error: String(error) }); }
    finally { fs.rmSync(root, { recursive: true, force: true }); }
  }
}
const bad = outputs.filter(row => !row.pass && row.variant !== 'flat4');
const result = { at: new Date().toISOString(), wrapperSHA256: hash(fs.readFileSync(wrapperFile)), variants: 3, casesPerVariant: 9, outputs, failuresInBaselineOrRimraf6Candidate: bad.length, recommendation: 'Scoped flat-cache3.2.0 -> rimraf6.1.3 preserves tested cache and deletion behavior on Node24 and avoids glob7/minimatch3. Flat-cache4.0.1 changes deletion behavior for nested directories and directory symlinks; avoid that alternative without broader qualification.' };
fs.writeFileSync(path.join(base, 'cache-compatibility-final-results.json'), JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
console.log(JSON.stringify(result, null, 2));
assert.equal(bad.length, 0);
assert.equal(outputs.filter(row => row.variant === 'flat4' && !row.pass).length, 2);
