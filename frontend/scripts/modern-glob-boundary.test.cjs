'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { createRequire } = require('node:module');
const { test } = require('node:test');

// These callers use the named modern APIs. Legacy glob 7/minimatch 3 have
// different contracts and deliberately do not receive these overrides.
const core = createRequire(require.resolve('@jest/core'));
const caller = createRequire(core.resolve('jest-config'));
const { glob } = caller('glob');

test('an aborted modern glob stops recursive filesystem reads', { timeout: 4000 }, async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-glob-abort-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (let a = 0; a < 4; a++) {
    for (let b = 0; b < 4; b++) {
      const directory = path.join(root, `a${a}`, `b${b}`);
      fs.mkdirSync(directory, { recursive: true });
      fs.writeFileSync(path.join(directory, 'owned.txt'), 'fixture');
    }
  }
  const controller = new AbortController();
  let reads = 0;
  const observed = {
    ...fs,
    readdir(directory, options, callback) {
      reads++;
      fs.readdir(directory, options, (error, entries) => {
        controller.abort(new Error('owned-glob-abort'));
        callback(error, entries);
      });
    },
  };
  await assert.rejects(glob('**/*', { cwd: root, fs: observed, signal: controller.signal }), /owned-glob-abort/);
  // Allow any queued post-rejection traversal to execute before the census.
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(reads, 1, 'glob continued reading directories after abort');
});

test('modern minimatch bounds optimization expansion and retains normal matching', () => {
  const typescript = createRequire(require.resolve('@typescript-eslint/typescript-estree'));
  const { Minimatch, minimatch } = typescript('minimatch');
  // Retain the upstream regression trigger: the earlier pattern's final
  // deduplication masked intermediate amplification in an unfixed optimizer.
  const matcher = new Minimatch(Array(8).fill('**/../a/b').join('/'), { optimizationLevel: 2, braceExpandMax: 8 });
  assert.equal(matcher.set.length, 8, 'pattern amplification must stop at the configured limit');
  const small = new Minimatch('**/../a/b/**/../c/d', { optimizationLevel: 2 });
  assert.equal(small.set.length, 4);
  assert.equal(small.match('../a/b/../c/d'), true);
  assert.equal(small.match('x/a/b/y/c/d'), true);
  assert.equal(minimatch('src/.owned.ts', '**/*.{ts,tsx}', { dot: true }), true);
  assert.equal(minimatch('src/owned.js', '**/*.{ts,tsx}', { dot: true }), false);
  assert.equal(minimatch('src/owned.tsx', '**/@(owned|other).tsx'), true);
});

test('coverage include/exclude and sync/async traversal retain their callers', { timeout: 4000 }, async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-coverage-glob-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const name of ['src/main.js', 'src/nested/main.ts', 'src/.hidden.js', 'src/main.test.js', 'node_modules/pkg/main.js']) {
    const file = path.join(root, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, 'module.exports = 1;');
  }
  const babel = createRequire(caller.resolve('babel-jest'));
  const istanbul = createRequire(babel.resolve('babel-plugin-istanbul'));
  const Exclude = istanbul('test-exclude');
  const exclude = new Exclude({ cwd: root, include: ['src/**/*.{js,ts}'], exclude: ['**/*.test.js'], extension: ['.js', '.ts'] });
  const expected = ['src/.hidden.js', 'src/main.js', 'src/nested/main.ts'];
  assert.deepEqual(exclude.globSync().sort(), expected);
  assert.deepEqual((await exclude.glob()).sort(), expected);
  assert.equal(exclude.shouldInstrument(path.join(root, 'src/main.test.js')), false);
  assert.equal(exclude.shouldInstrument(path.join(root, 'node_modules/pkg/main.js')), false);
});
