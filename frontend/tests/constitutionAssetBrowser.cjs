'use strict';

// Run against the owned production preview. Model doubles are never used here.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const { chromium } = require('@playwright/test');
const { selectFixture } = require('../scripts/dependency-browser-fixtures.cjs');
const { verifyModelBytes } = require('../scripts/embedding-model.cjs');
const manifest = require('../scripts/embedding-model.json');

async function main() {
  const base = process.env.DEPENDENCY_PREVIEW_URL;
  const cache = process.env.NATIVE_VERIFY_CACHE_DIR;
  assert.equal(base, 'http://127.0.0.1:13062', 'Use the assigned inert lane preview');
  assert.ok(cache && path.isAbsolute(cache), 'An absolute approved public-model fixture is required');
  const modelFiles = {};
  for (const name of Object.keys(manifest.files)) {
    const bytes = fs.readFileSync(path.join(cache, manifest.model, manifest.revision, name));
    verifyModelBytes(name, bytes);
    modelFiles[name] = bytes;
  }
  const transformersRequire = createRequire(require.resolve('@huggingface/transformers'));
  const wasmDir = path.dirname(transformersRequire.resolve('onnxruntime-web'));
  const runtimeVersion = require(path.join(wasmDir, '../package.json')).version;
  const originalMeta = JSON.parse(fs.readFileSync(path.join(__dirname, '../public/data/constitution/embeddings-index.json'), 'utf8'));
  const originalBin = fs.readFileSync(path.join(__dirname, '../public/data/constitution/embeddings.bin'));
  const cases = [
    { name: 'network-unavailable', allowModel: false },
    { name: 'nonfinite-stored', bin: () => { const b = Buffer.from(originalBin); b.writeFloatLE(NaN, 0); return b; } },
    { name: 'short-stored', bin: () => originalBin.subarray(0, originalBin.length - 4) },
    { name: 'wrong-dimension', meta: () => ({ ...originalMeta, dim: 383 }), bin: () => originalBin.subarray(0, 264 * 383 * 4) },
    { name: 'incompatible-model', meta: () => ({ ...originalMeta, model: 'unrelated/model' }) },
    { name: 'incompatible-revision', meta: () => ({ ...originalMeta, revision: 'main' }) },
    { name: 'missing-index', absent: true },
    { name: 'malformed-index', malformed: true },
    { name: 'genuine-wasm', allowModel: true },
  ];
  const browser = await chromium.launch({ headless: true });
  const results = [];
  try {
    for (const control of cases) {
      const context = await browser.newContext();
      try {
        const unexpected = [], errors = [], fixtures = [], localAssets = [];
        await context.addInitScript(() => {
          window.__constitutionWasmCalls = 0;
          for (const method of ['instantiate', 'instantiateStreaming']) {
            const original = WebAssembly[method];
            WebAssembly[method] = function (...args) {
              window.__constitutionWasmCalls++;
              return original.apply(this, args);
            };
          }
        });
        await context.route('**/*', async route => {
          const url = new URL(route.request().url());
          if (url.origin === base) {
            if (url.pathname === '/data/constitution/embeddings-index.json') {
              localAssets.push(url.pathname);
              if (control.absent) return route.fulfill({ status: 404, body: 'unavailable' });
              if (control.malformed) return route.fulfill({ contentType: 'application/json', body: '{broken' });
              if (control.meta) return route.fulfill({ contentType: 'application/json', body: JSON.stringify(control.meta()) });
            }
            if (url.pathname === '/data/constitution/embeddings.bin') {
              localAssets.push(url.pathname);
              if (control.bin) return route.fulfill({ contentType: 'application/octet-stream', body: control.bin() });
            }
            return route.continue();
          }
          const fixture = selectFixture(url.href, runtimeVersion);
          if (fixture?.kind === 'model') {
            fixtures.push(url.href);
            if (!control.allowModel) return route.abort();
            return route.fulfill({ body: modelFiles[fixture.relative], contentType: fixture.contentType });
          }
          if (fixture?.kind === 'runtime') {
            fixtures.push(url.href);
            return route.fulfill({ body: fs.readFileSync(path.join(wasmDir, fixture.relative)), contentType: fixture.contentType });
          }
          unexpected.push(url.href);
          return route.abort();
        });
        const page = await context.newPage();
        page.on('pageerror', error => errors.push(error.message));
        const response = await page.goto(`${base}/learn`, { waitUntil: 'networkidle' });
        assert.equal(response.status(), 200);
        if (control.allowModel) await page.waitForFunction(() => window.__constitutionWasmCalls > 0, { timeout: 60000 });
        const input = page.getByRole('searchbox', { name: 'Search civic topics or the Constitution' });
        const rankings = [];
        for (const query of ['how many terms can a president serve?', 'right to health care']) {
          await input.fill('');
          await page.getByText('Matching articles', { exact: true }).waitFor({ state: 'hidden' });
          await input.fill(query);
          const list = page.getByText('Matching articles', { exact: true }).locator('..').locator('ul');
          await list.waitFor();
          const text = await list.innerText();
          assert.ok(text.trim());
          rankings.push({ query, text });
        }
        const wasmCalls = await page.evaluate(() => window.__constitutionWasmCalls);
        assert.deepEqual(errors, []);
        assert.deepEqual(unexpected, []);
        assert.equal(wasmCalls > 0, control.allowModel === true);
        assert.ok(localAssets.includes('/data/constitution/embeddings.bin'));
        assert.ok(localAssets.includes('/data/constitution/embeddings-index.json'));
        if (control.name !== 'network-unavailable' && !control.allowModel) {
          assert.deepEqual(fixtures, [], 'Invalid assets must refuse before model/runtime requests');
          assert.deepEqual(rankings, results[0].rankings, 'Invalid assets must preserve exact keyword fallback');
        }
        const result = { name: control.name, outcome: 'passed', wasmCalls, localAssets, fixtures, rankings, errors, unexpected };
        results.push(result);
        console.log(JSON.stringify(result));
      } finally { await context.close(); }
    }
    const semantic = results[results.length - 1];
    assert.notEqual(semantic.rankings[0].text, results[0].rankings[0].text);
    assert.match(semantic.rankings[0].text.split('\n')[0], /142/);
    assert.match(semantic.rankings[1].text.split('\n')[0], /43/);
    console.log(JSON.stringify({ check: 'constitution-asset-browser', revision: manifest.revision, runtimeVersion, results, skipped: 0 }));
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
