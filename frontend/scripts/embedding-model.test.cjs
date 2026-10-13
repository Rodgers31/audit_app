'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');
const { prepareModel, verifyModelBytes, configureLocalModel } = require('./embedding-model.cjs');
const manifest = require('./embedding-model.json');

function fixture(fn) {
  const root = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'batch12-dependencies-model-'));
  return Promise.resolve().then(() => fn(root)).finally(() => fs.rmSync(root, { recursive: true, force: true }));
}
const refused = { code: 'ERR_EMBEDDING_MODEL_INPUT' };

for (const [label, value] of [['null', null], ['array', []], ['boolean', true], ['number', 0], ['NaN', NaN], ['relative', 'cache']]) {
  test(`model cache refuses ${label} without fetching`, () => fixture(async root => {
    const original = global.fetch;
    let calls = 0;
    global.fetch = async () => { calls++; throw new Error('unexpected fetch'); };
    try { await assert.rejects(prepareModel(value), refused); assert.equal(calls, 0); }
    finally { global.fetch = original; }
  }));
}

for (const relative of Object.keys(manifest.files)) {
  test(`model cache refuses damaged ${relative} before any missing-file download`, () => fixture(async root => {
    const model = path.join(root, manifest.model, manifest.revision);
    const file = path.join(model, relative);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const damaged = Buffer.alloc(manifest.files[relative].bytes);
    fs.writeFileSync(file, damaged);
    const original = global.fetch;
    let calls = 0;
    global.fetch = async () => { calls++; throw new Error('unexpected fetch'); };
    try {
      await assert.rejects(prepareModel(root), refused);
      assert.equal(calls, 0);
      assert.deepEqual(fs.readFileSync(file), damaged);
    } finally { global.fetch = original; }
  }));
}

for (const kind of ['unknown-file', 'unknown-directory', 'file-link', 'directory-link', 'dangling-link', 'ancestor-link']) {
  test(`model cache refuses ${kind}`, () => fixture(async root => {
    const cache = path.join(root, 'cache');
    const model = path.join(cache, manifest.model, manifest.revision);
    fs.mkdirSync(model, { recursive: true });
    const other = path.join(root, 'other');
    fs.mkdirSync(other);
    fs.writeFileSync(path.join(other, 'config.json'), '{}');
    if (kind === 'unknown-file') fs.writeFileSync(path.join(model, 'generation_config.json'), '{}');
    if (kind === 'unknown-directory') fs.mkdirSync(path.join(model, 'unreviewed'));
    if (kind === 'file-link') fs.symlinkSync(path.join(other, 'config.json'), path.join(model, 'config.json'));
    if (kind === 'directory-link') fs.symlinkSync(other, path.join(model, 'onnx'));
    if (kind === 'dangling-link') fs.symlinkSync(path.join(other, 'absent'), path.join(model, 'config.json'));
    if (kind === 'ancestor-link') { fs.renameSync(cache, path.join(root, 'retained')); fs.symlinkSync(path.join(root, 'retained'), cache); }
    await assert.rejects(prepareModel(cache), refused);
    assert.equal(fs.readFileSync(path.join(other, 'config.json'), 'utf8'), '{}');
  }));
}

for (const [label, status, bytes] of [
  ['HTTP error', 503, Buffer.alloc(0)],
  ['empty download', 200, Buffer.alloc(0)],
  ['same-size unreviewed download', 200, Buffer.alloc(manifest.files['config.json'].bytes)],
  ['oversized download', 200, Buffer.alloc(manifest.files['config.json'].bytes + 1)],
]) {
  test(`model preparation refuses ${label} without publishing`, () => fixture(async root => {
    const original = global.fetch;
    let calls = 0;
    global.fetch = async (url, options) => {
      calls++;
      assert.equal(url, `https://huggingface.co/${manifest.model}/resolve/${manifest.revision}/config.json`);
      assert.ok(options.signal instanceof AbortSignal);
      return new Response(bytes, { status });
    };
    try {
      await assert.rejects(prepareModel(root), refused);
      assert.equal(calls, 1);
      assert.equal(fs.existsSync(path.join(root, manifest.model)), false);
    } finally { global.fetch = original; }
  }));
}

test('model byte authority cannot be bypassed with unknown files or coercible values', () => {
  for (const relative of ['../config.json', '__proto__', 'constructor', 'onnx/other.onnx']) {
    assert.throws(() => verifyModelBytes(relative, Buffer.alloc(0)), refused);
  }
  for (const bytes of [null, false, 0, '', [], new Uint8Array(650)]) {
    assert.throws(() => verifyModelBytes('config.json', bytes), refused);
  }
});

test('configured native model excludes remote and alternate caches', () => {
  const env = { allowLocalModels: false, allowRemoteModels: true, useFSCache: true, useBrowserCache: true, useCustomCache: true };
  configureLocalModel(env);
  assert.deepEqual(env, { allowLocalModels: true, allowRemoteModels: false, useFSCache: false, useBrowserCache: false, useCustomCache: false });
});
