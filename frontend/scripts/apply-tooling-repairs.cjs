'use strict';
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const patchSet = require('./tooling-repairs.json');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);

function validateRelativePath(relative) {
  assert.ok(typeof relative === 'string' && !path.isAbsolute(relative) && !relative.includes('\\') &&
    !relative.split('/').some(part => !part || part === '.' || part === '..'), 'tooling repair: unsafe package path');
}

// lstat distinguishes an omitted package from a dangling link without following it.
function inspectPath(root, relative, absent = false) {
  validateRelativePath(relative);
  let current = root;
  const parts = relative.split('/');
  for (let i = 0; i < parts.length; i++) {
    current = path.join(current, parts[i]);
    let stat;
    try { stat = fs.lstatSync(current); }
    catch (error) {
      if (error.code !== 'ENOENT') throw error;
      assert.ok(absent, `tooling repair: absent path ${relative}`);
      return { target: path.join(root, relative), stat: null };
    }
    assert.ok(!stat.isSymbolicLink(), `tooling repair: symlink refused ${relative}`);
    if (i < parts.length - 1) assert.ok(stat.isDirectory(), `tooling repair: directory required ${relative}`);
    else return { target: current, stat };
  }
}

function regularPath(root, relative) {
  const { target, stat } = inspectPath(root, relative);
  assert.ok(stat.isFile(), `tooling repair: regular file required ${relative}`);
  return target;
}

function installedFiles(root, entry) {
  const files = [];
  function walk(relative) {
    const { target, stat } = inspectPath(root, relative);
    if (stat.isDirectory()) {
      for (const name of fs.readdirSync(target).sort()) walk(`${relative}/${name}`);
    } else {
      assert.ok(stat.isFile(), `tooling repair: regular file required ${relative}`);
      files.push(relative.slice(entry.length + 1));
    }
  }
  walk(entry);
  return files;
}

function replacement(patch, bytes, relative) {
  if (patch.original_sha256 === null) {
    assert.ok(bytes === null && typeof patch.addition === 'string' && patch.edits.length === 0,
      `tooling repair: unexpected helper ${relative}`);
    bytes = Buffer.from(patch.addition);
  } else {
    assert.ok(digest(patch.original_sha256) && bytes && hash(bytes) === patch.original_sha256,
      `tooling repair: upstream bytes changed ${relative}`);
    let source = bytes.toString('utf8');
    assert.ok(Array.isArray(patch.edits) && patch.edits.length > 0 && patch.addition === null, 'tooling repair: invalid edit set');
    for (const edit of patch.edits) {
      assert.ok(typeof edit.before === 'string' && edit.before && typeof edit.after === 'string' &&
        source.split(edit.before).length === 2, `tooling repair: ambiguous edit ${relative}`);
      source = source.replace(edit.before, edit.after);
    }
    bytes = Buffer.from(source);
  }
  assert.equal(hash(bytes), patch.repaired_sha256, `tooling repair: replacement hash mismatch ${relative}`);
  return bytes;
}

function planRepairs(root, { check = false, production = false } = {}) {
  assert.ok(typeof check === 'boolean' && typeof production === 'boolean', 'tooling repair: boolean modes required');
  assert.ok(fs.lstatSync(root).isDirectory(), 'tooling repair: real frontend root required');
  assert.ok(fs.lstatSync(path.join(root, 'node_modules')).isDirectory(), 'tooling repair: real owned node_modules required');
  assert.equal(patchSet.schema, 2, 'tooling repair: unsupported patch schema');
  assert.ok(Array.isArray(patchSet.packages) && patchSet.packages.length === 2 &&
    new Set(patchSet.packages.map(p => p.name)).size === 2, 'tooling repair: complete package inventory required');
  assert.ok(Array.isArray(patchSet.patches) && patchSet.patches.length > 0, 'tooling repair: nonempty patches required');
  const lock = JSON.parse(fs.readFileSync(regularPath(root, 'package-lock.json')));
  assert.ok(lock && lock.lockfileVersion === 3 && lock.packages && !Array.isArray(lock.packages), 'tooling repair: lock package inventory required');
  const operations = [], packages = [], absentPackages = [], usedPatches = new Set();
  for (const inventory of patchSet.packages) {
    assert.ok(['braces', 'sprintf-js'].includes(inventory.name) && typeof inventory.version === 'string' &&
      inventory.files && !Array.isArray(inventory.files) && Object.keys(inventory.files).length > 0,
    'tooling repair: invalid package inventory');
    const patches = new Map();
    for (const patch of patchSet.patches.filter(p => p.package === inventory.name)) {
      validateRelativePath(patch.file);
      assert.ok(patch.version === inventory.version && digest(patch.repaired_sha256) && !patches.has(patch.file),
        'tooling repair: invalid or duplicate patch identity');
      const identity = inventory.files[patch.file];
      assert.ok(identity && identity.original_sha256 === patch.original_sha256 && identity.repaired_sha256 === patch.repaired_sha256,
        'tooling repair: patch inventory mismatch');
      patches.set(patch.file, patch); usedPatches.add(patch);
    }
    const entries = Object.entries(lock.packages).filter(([name]) =>
      name.endsWith(`/node_modules/${inventory.name}`) || name === `node_modules/${inventory.name}`);
    assert.ok(entries.length > 0, `tooling repair: missing locked ${inventory.name}`);
    for (const [entry, record] of entries) {
      validateRelativePath(entry);
      assert.ok(entry.startsWith('node_modules/'), 'tooling repair: unsafe package path');
      assert.ok(record.version === inventory.version && record.dev === true, `tooling repair: incompatible locked ${entry}`);
      const installed = inspectPath(root, entry, true);
      if (!installed.stat) {
        assert.ok(production, `tooling repair: absent installed ${entry}`);
        absentPackages.push(entry); continue;
      }
      assert.ok(installed.stat.isDirectory(), `tooling repair: directory required ${entry}`);
      const metadata = JSON.parse(fs.readFileSync(regularPath(root, `${entry}/package.json`)));
      assert.ok(metadata.name === inventory.name && metadata.version === inventory.version, `tooling repair: incompatible installed ${entry}`);
      for (const file of installedFiles(root, entry)) {
        assert.ok(Object.hasOwn(inventory.files, file), `tooling repair: unexpected package file ${entry}/${file}`);
      }
      for (const [file, identity] of Object.entries(inventory.files)) {
        validateRelativePath(file);
        const patch = patches.get(file), relative = `${entry}/${file}`;
        assert.ok(digest(identity.repaired_sha256) && (identity.original_sha256 === null || digest(identity.original_sha256)),
          'tooling repair: invalid source digest');
        const { target, stat } = inspectPath(root, relative, Boolean(patch && patch.original_sha256 === null));
        assert.ok(stat === null || stat.isFile(), `tooling repair: regular file required ${relative}`);
        const bytes = stat ? fs.readFileSync(target) : null;
        if (bytes && hash(bytes) === identity.repaired_sha256) continue;
        if (!patch) {
          assert.ok(bytes && identity.original_sha256 === identity.repaired_sha256,
            `tooling repair: invalid unchanged inventory ${relative}`);
          assert.fail(`tooling repair: upstream bytes changed ${relative}`);
        }
        // Unknown bytes fail even in check mode; only the reviewed original can be repaired.
        if (check && bytes && hash(bytes) === patch.original_sha256) {
          assert.fail(`tooling repair: unpatched ${relative}; run npm ci with scripts enabled`);
        }
        const repaired = replacement(patch, bytes, relative);
        assert.ok(!check, `tooling repair: unpatched ${relative}; run npm ci with scripts enabled`);
        operations.push({ target, bytes: repaired });
      }
      packages.push(entry);
    }
  }
  assert.equal(usedPatches.size, patchSet.patches.length, 'tooling repair: unknown patch package');
  return { operations, packages, absentPackages };
}

function applyRepairs(root = path.resolve(__dirname, '..'), options = {}) {
  const { check = false } = options;
  const lockPath = path.join(root, 'node_modules', '.tooling-repair-lock');
  // Concurrent installs fail visibly; never delete an unknown/stale owner lock.
  assert.ok(fs.lstatSync(root).isDirectory(), 'tooling repair: real frontend root required');
  assert.ok(fs.lstatSync(path.join(root, 'node_modules')).isDirectory(), 'tooling repair: real owned node_modules required');
  if (!check) fs.mkdirSync(lockPath);
  try {
    const plan = planRepairs(root, options);
    for (const { target, bytes } of plan.operations) {
      const temporary = `${target}.repair-${process.pid}`;
      let created = false;
      try {
        fs.writeFileSync(temporary, bytes, { flag: 'wx' }); created = true;
        fs.renameSync(temporary, target); created = false;
      } finally {
        if (created) fs.unlinkSync(temporary);
      }
      assert.equal(hash(fs.readFileSync(target)), hash(bytes), 'tooling repair: write readback failed');
    }
    const verified = planRepairs(root, { ...options, check: true });
    return { check: 'source-bound-tooling-repairs', packages: verified.packages, absentPackages: verified.absentPackages, changedFiles: plan.operations.length };
  } finally {
    if (!check) fs.rmdirSync(lockPath);
  }
}
if (require.main === module) {
  try {
    assert.ok(process.argv.slice(2).every(x => x === '--check'), 'tooling repair: unknown argument');
    console.log(JSON.stringify(applyRepairs(undefined, { check: process.argv.includes('--check'), production: (process.env.npm_config_omit || '').split(/[ ,]+/).includes('dev') })));
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
module.exports = { applyRepairs, planRepairs };
