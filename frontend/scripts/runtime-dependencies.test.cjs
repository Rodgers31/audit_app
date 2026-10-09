'use strict';

// These integration regressions require a real, production-only installation.
// RUNTIME_VERIFY_ROOT=/owned/pruned-install node --test scripts/runtime-dependencies.test.cjs
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

test('runtime verification rejects nested tooling and malformed manifests', async t => {
  const source = process.env.RUNTIME_VERIFY_ROOT;
  assert.ok(source, 'RUNTIME_VERIFY_ROOT must name an owned pruned installation');
  const script = path.join(__dirname, 'verify-runtime-dependencies.cjs');
  const fixture = fs.mkdtempSync(path.join(path.dirname(path.resolve(source)), 'runtime-regression-'));
  const manifest = fs.readFileSync(path.join(source, 'package.json'), 'utf8');
  try {
    fs.writeFileSync(path.join(fixture, 'package.json'), manifest);
    fs.cpSync(path.join(source, 'node_modules'), path.join(fixture, 'node_modules'), { recursive: true });
    const run = () => spawnSync(process.execPath, [script, fixture], {
      env: { PATH: process.env.PATH }, encoding: 'utf8', timeout: 30000,
    });
    await t.test('real pruned installation decodes an image', () => {
      const result = run();
      assert.equal(result.status, 0, result.stderr);
      assert.match(result.stdout, /"imageDecode":true/);
    });
    await t.test('nested reachable braces cannot produce an absence verdict', () => {
      const nested = path.join(fixture, 'node_modules/next/node_modules/braces');
      fs.mkdirSync(path.dirname(nested), { recursive: true });
      // Link the actual locked package from the full build/test installation.
      fs.symlinkSync(path.dirname(require.resolve('braces/package.json')), nested, 'dir');
      try {
        const result = run();
        assert.equal(result.status, 1, result.stdout);
        assert.match(result.stderr, /braces must be absent/);
      } finally { fs.unlinkSync(nested); }
    });
    await t.test('dependency maps cannot be arrays or null', () => {
      fs.writeFileSync(path.join(fixture, 'package.json'), JSON.stringify({
        ...JSON.parse(manifest), dependencies: [], devDependencies: null,
      }));
      try {
        const result = run();
        assert.equal(result.status, 1, result.stdout);
        assert.match(result.stderr, /dependencies must be a dependency map/);
      } finally { fs.writeFileSync(path.join(fixture, 'package.json'), manifest); }
    });
    await t.test('missing Sharp decoders cannot produce an image verdict', () => {
      // Sharp can legitimately fall back to its WASM optional package. Remove
      // all decoder packages rather than treating a working fallback as failure.
      const images = path.join(fixture, 'node_modules/@img');
      for (const name of fs.readdirSync(images)) {
        if (name.startsWith('sharp-')) fs.rmSync(path.join(images, name), { recursive: true });
      }
      const result = run();
      assert.equal(result.status, 1, result.stdout);
      assert.match(result.stderr, /Could not load the "sharp" module/);
    });
  } finally { fs.rmSync(fixture, { recursive: true, force: true }); }
});
