'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const { createRequire } = require('node:module');
const { spawnSync } = require('node:child_process');
const base = __dirname, front = '/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app/frontend';
const manifest = JSON.parse(fs.readFileSync(path.join(front, 'scripts/tooling-repairs.json')));
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const root = fs.mkdtempSync(path.join(base, 'metadata-alias-'));
try {
  fs.mkdirSync(path.join(root, 'scripts')); fs.mkdirSync(path.join(root, 'node_modules'));
  for (const file of ['package.json', 'package-lock.json']) fs.copyFileSync(path.join(front, file), path.join(root, file));
  for (const file of ['tooling-repairs.json', 'apply-tooling-repairs.cjs']) fs.copyFileSync(path.join(front, 'scripts', file), path.join(root, 'scripts', file));
  for (const inventory of manifest.packages) for (const entry of inventory.entries) { fs.mkdirSync(path.dirname(path.join(root, entry)), { recursive: true }); fs.cpSync(path.join(front, entry), path.join(root, entry), { recursive: true, verbatimSymlinks: true }); }
  for (const name of ['eslint', '@humanwhocodes/config-array', 'flat-cache', 'minimatch', 'rimraf', 'glob']) {
    const entry = path.join(root, 'node_modules', name);
    if (['minimatch', 'rimraf', 'glob'].includes(name)) fs.cpSync(path.join(front, 'node_modules', name), entry, { recursive: true, verbatimSymlinks: true });
    else { fs.mkdirSync(entry, { recursive: true }); fs.copyFileSync(path.join(front, 'node_modules', name, 'package.json'), path.join(entry, 'package.json')); }
  }
  for (const file of ['eslint/lib/cli-engine/file-enumerator.js', 'eslint/lib/eslint/eslint-helpers.js', '@humanwhocodes/config-array/api.js', 'flat-cache/src/del.js']) { const target = path.join(root, 'node_modules', file); fs.mkdirSync(path.dirname(target), { recursive: true }); fs.copyFileSync(path.join(front, 'node_modules', file), target); }
  const api = require(path.join(root, 'scripts/apply-tooling-repairs.cjs'));
  // Separate process prevents positive resolution caches from masking the later physical mutation.
  const child = spawnSync(process.execPath, ['-e', `console.log(JSON.stringify(require(${JSON.stringify(path.join(root, 'scripts/apply-tooling-repairs.cjs'))}).applyRepairs(${JSON.stringify(root)},{check:true})))`], { encoding: 'utf8' });
  assert.equal(child.status, 0, child.stderr);
  const positive = JSON.parse(child.stdout); assert.equal(positive.packages.length, 7);
  const caller = path.join(root, 'node_modules/eslint/package.json'), req = createRequire(caller);
  const legitMetadata = path.join(root, 'node_modules/minimatch/package.json');
  const metadata = JSON.parse(fs.readFileSync(legitMetadata));
  const shadow = path.join(root, 'node_modules/eslint/node_modules/minimatch'); fs.mkdirSync(shadow, { recursive: true });
  fs.symlinkSync(path.relative(shadow, legitMetadata), path.join(shadow, 'package.json'));
  const entry = metadata.exports['.'].require.default;
  fs.mkdirSync(path.dirname(path.join(shadow, entry)), { recursive: true });
  fs.writeFileSync(path.join(path.dirname(path.join(shadow, entry)), 'package.json'), JSON.stringify({ type: 'commonjs' }));
  fs.copyFileSync(path.join(base, 'baseline/node_modules/minimatch/minimatch.js'), path.join(shadow, entry));
  for (const name of ['brace-expansion', 'balanced-match', 'concat-map']) fs.cpSync(path.join(base, 'baseline/node_modules', name), path.join(shadow, 'node_modules', name), { recursive: true, verbatimSymlinks: true });
  const metadataResolved = req.resolve('minimatch/package.json'), actualResolved = req.resolve('minimatch');
  assert.equal(metadataResolved, legitMetadata);
  assert.equal(actualResolved, path.join(shadow, entry));
  const actual = req('minimatch'); assert.equal(typeof actual.makeRe, 'function'); assert.equal(actual('x.js', '*.js'), true);
  let verdict, error;
  try { verdict = api.applyRepairs(root, { check: true }); } catch (e) { error = String(e); }
  const result = { at: new Date().toISOString(), sourceHashes: Object.fromEntries(['apply-tooling-repairs.cjs', 'tooling-repairs.json'].map(file => [file, hash(fs.readFileSync(path.join(front, 'scripts', file)))])), positive, metadataResolved: path.relative(root, metadataResolved), actualResolved: path.relative(root, actualResolved), actualOriginalMinimatchSourceSHA256: hash(fs.readFileSync(actualResolved)), legacyMakeRePresent: true, accepted: !error, verdict, error, scope: 'Owned malformed physical installation: untracked ESLint nested package uses a package.json symlink to the legitimate reviewed modern metadata but resolves the legacy executable entry.' };
  fs.writeFileSync(path.join(base, process.argv[2] || 'metadata-alias-resolution-results.json'), JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify(result, null, 2));
  if (process.argv[3] === 'must-refuse') assert.equal(result.accepted, false, 'metadata aliases must not certify a different executable entry');
} finally { fs.rmSync(root, { recursive: true, force: true }); }
