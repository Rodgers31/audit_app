'use strict';

const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');
const { copyRuntimeFixture } = require('./runtime-fixture-copy.cjs');

/**
 * Hash the owned source's package and decoder bytes in stable path order.
 * @param {string} root An owned fixture containing only regular copied files.
 * @returns {{sha256:string, files:number}} Content identity and file count.
 */
function contentIdentity(root) {
  const digest = createHash('sha256');
  let files = 0;
  const walk = directory => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const file = path.join(directory, entry.name);
      if (entry.isDirectory()) walk(file);
      else {
        assert.ok(entry.isFile(), 'The owned deep copy must not retain source links');
        digest.update(path.relative(root, file) + '\0');
        digest.update(createHash('sha256').update(fs.readFileSync(file)).digest('hex') + '\n');
        files++;
      }
    }
  };
  walk(root);
  return { sha256: digest.digest('hex'), files };
}

test('destructive runtime regressions preserve a linked source installation', () => {
  const original = process.env.RUNTIME_VERIFY_ROOT;
  assert.ok(original, 'RUNTIME_VERIFY_ROOT must name the read-only pruned installation');
  const owned = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-app-runtime-isolation-'));
  const source = path.join(owned, 'disposable-source');
  const linked = path.join(owned, 'linked-fixture');
  const verifier = path.join(__dirname, 'verify-runtime-dependencies.cjs');
  try {
    fs.mkdirSync(source);
    fs.mkdirSync(linked);
    // Never expose the caller's build/runtime tree to destructive regressions.
    fs.copyFileSync(path.join(original, 'package.json'), path.join(source, 'package.json'));
    copyRuntimeFixture(path.join(original, 'node_modules'), path.join(source, 'node_modules'));
    fs.copyFileSync(path.join(source, 'package.json'), path.join(linked, 'package.json'));
    fs.symlinkSync(path.join(source, 'node_modules'), path.join(linked, 'node_modules'), 'junction');
    const before = contentIdentity(source);
    const result = spawnSync(process.execPath, ['--test', path.join(__dirname, 'runtime-dependencies.test.cjs')], {
      env: { PATH: process.env.PATH, RUNTIME_VERIFY_ROOT: linked }, encoding: 'utf8', timeout: 90000,
    });
    const after = contentIdentity(source);
    const preserved = spawnSync(process.execPath, [verifier, source], {
      env: { PATH: process.env.PATH }, encoding: 'utf8', timeout: 30000,
    });
    console.log(JSON.stringify({ check: 'runtime-regression-source-isolation',
      childControlsExit: result.status, sourceBefore: before, sourceAfter: after,
      sourceBytesPreserved: before.sha256 === after.sha256, sourceVerifierExit: preserved.status }));
    assert.equal(result.status, 0, result.stderr || result.stdout);
    assert.match(result.stdout, /^# tests 5$/m);
    assert.match(result.stdout, /^# pass 5$/m);
    assert.match(result.stdout, /^# fail 0$/m);
    assert.deepEqual(after, before, 'Destructive runtime tests changed linked source package/decoder bytes');
    assert.equal(preserved.status, 0, preserved.stderr);
    assert.match(preserved.stdout, /"imageDecode":true/);
  } finally { fs.rmSync(owned, { recursive: true, force: true }); }
});

test('runtime fixture copying resolves source links and preserves executable file permissions', () => {
  const owned = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-app-runtime-copy-'));
  try {
    const original = path.join(owned, 'original');
    const payload = path.join(owned, 'payload');
    const copy = path.join(owned, 'copy');
    fs.mkdirSync(original);
    fs.mkdirSync(payload);
    fs.writeFileSync(path.join(payload, 'decoder'), 'read-only source bytes');
    fs.chmodSync(path.join(payload, 'decoder'), 0o751);
    fs.symlinkSync(payload, path.join(original, 'package'), 'junction');
    fs.symlinkSync(path.join(payload, 'decoder'), path.join(original, 'file-link'));
    copyRuntimeFixture(original, copy);
    assert.equal(fs.lstatSync(path.join(copy, 'package')).isSymbolicLink(), false);
    assert.equal(fs.lstatSync(path.join(copy, 'file-link')).isSymbolicLink(), false);
    assert.equal(fs.readFileSync(path.join(copy, 'package/decoder'), 'utf8'), 'read-only source bytes');
    assert.equal(fs.statSync(path.join(copy, 'package/decoder')).mode & 0o777, fs.statSync(path.join(payload, 'decoder')).mode & 0o777);
    fs.rmSync(path.join(copy, 'package'), { recursive: true });
    assert.equal(fs.readFileSync(path.join(payload, 'decoder'), 'utf8'), 'read-only source bytes');
  } finally { fs.rmSync(owned, { recursive: true, force: true }); }
});

test('runtime fixture copying refuses a directory link cycle', () => {
  const owned = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-app-runtime-cycle-'));
  try {
    const original = path.join(owned, 'original');
    fs.mkdirSync(original);
    fs.writeFileSync(path.join(original, 'marker'), 'unchanged');
    fs.symlinkSync(original, path.join(original, 'cycle'), 'junction');
    assert.throws(() => copyRuntimeFixture(original, path.join(owned, 'copy')), /directory link cycle/);
    assert.equal(fs.readFileSync(path.join(original, 'marker'), 'utf8'), 'unchanged');
  } finally { fs.rmSync(owned, { recursive: true, force: true }); }
});

test('runtime fixture copying refuses an occupied destination link before writing', () => {
  const owned = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-app-runtime-destination-'));
  try {
    const original = path.join(owned, 'original');
    fs.mkdirSync(original);
    fs.writeFileSync(path.join(original, 'marker'), 'unchanged');
    const destination = path.join(owned, 'destination');
    fs.symlinkSync(original, destination, 'junction');
    assert.throws(() => copyRuntimeFixture(original, destination), /destination must be empty/);
    assert.equal(fs.readFileSync(path.join(original, 'marker'), 'utf8'), 'unchanged');
  } finally { fs.rmSync(owned, { recursive: true, force: true }); }
});
