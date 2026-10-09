'use strict';

// Drive the built Learn page with real WASM inference. Only public model/runtime
// downloads are fulfilled from an owned cache; all external transport is denied.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { createRequire } = require('node:module');
const { chromium } = require('@playwright/test');
const { selectFixture } = require('../scripts/dependency-browser-fixtures.cjs');

/**
 * Drive two isolated Learn contexts: BM25 fallback and actual WASM inference.
 * Model and runtime resources come from the owned pinned fixture; all other
 * external requests fail. Ranking assertions catch a silently unavailable model.
 * @returns {Promise<void>} Reject missing fixtures or incompatible search results.
 */
async function main() {
  const base = process.env.DEPENDENCY_PREVIEW_URL;
  const cache = process.env.NATIVE_VERIFY_CACHE_DIR;
  assert.ok(base && /^http:\/\/127\.0\.0\.1:\d+$/.test(base));
  assert.ok(cache, 'An owned public-model cache is required');
  const revision = '751bff37182d3f1213fa05d7196b954e230abad9';
  const transformersRequire = createRequire(require.resolve('@huggingface/transformers'));
  const wasmDir = path.dirname(transformersRequire.resolve('onnxruntime-web'));
  const runtimeVersion = require(path.join(wasmDir, '../package.json')).version;
  const browser = await chromium.launch({ headless: true });
  const results = [];
  try {
    for (const allowModel of [false, true]) {
      const context = await browser.newContext();
      const unexpected = [];
      const errors = [];
      const fixtures = [];
      const fixtureUrls = [];
      await context.addInitScript(() => {
        window.__dependencyWasmCalls = 0;
        for (const method of ['instantiate', 'instantiateStreaming']) {
          const original = WebAssembly[method];
          WebAssembly[method] = function (...args) {
            window.__dependencyWasmCalls++;
            return original.apply(this, args);
          };
        }
      });
      await context.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.origin === base) return route.continue();
        const fixture = selectFixture(url.href, runtimeVersion);
        if (fixture?.kind === 'model') {
          if (!allowModel) return route.abort();
          const { relative, contentType } = fixture;
          fixtures.push(relative);
          fixtureUrls.push(url.href);
          return route.fulfill({ body: await fs.readFile(path.join(cache, 'Xenova/all-MiniLM-L6-v2', revision, relative)),
            contentType });
        }
        if (fixture?.kind === 'runtime') {
          fixtures.push(fixture.relative);
          fixtureUrls.push(url.href);
          return route.fulfill({ body: await fs.readFile(path.join(wasmDir, fixture.relative)), contentType: fixture.contentType });
        }
        unexpected.push(url.href);
        return route.abort();
      });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`${base}/learn`, { waitUntil: 'networkidle' });
      const input = page.getByRole('searchbox', { name: 'Search civic topics or the Constitution' });
      if (allowModel) {
        await page.waitForFunction(() => window.__dependencyWasmCalls > 0, { timeout: 60000 });
      }
      const rankings = [];
      for (const query of ['how many terms can a president serve?', 'right to health care']) {
        await input.fill('');
        await page.getByText('Matching articles', { exact: true }).waitFor({ state: 'hidden' });
        await input.fill(query);
        const list = page.getByText('Matching articles', { exact: true }).locator('..').locator('ul');
        await list.waitFor();
        // The UI debounces search and awaits real model inference.
        await page.getByRole('button', { name: 'Clear search', exact: true }).waitFor();
        const text = await list.innerText();
        assert.ok(text.trim());
        rankings.push({ query, text });
      }
      const wasmCalls = await page.evaluate(() => window.__dependencyWasmCalls);
      assert.equal(errors.length, 0, JSON.stringify(errors));
      assert.equal(unexpected.length, 0, JSON.stringify(unexpected));
      assert.equal(wasmCalls > 0, allowModel);
      results.push({ allowModel, wasmCalls, fixtures, fixtureUrls, rankings, errors, unexpected });
      await context.close();
    }
    assert.notEqual(results[0].rankings[0].text, results[1].rankings[0].text, 'Semantic search must change the fallback ranking');
    assert.match(results[1].rankings[0].text.split('\n')[0], /142/);
    assert.match(results[1].rankings[1].text.split('\n')[0], /43/);
    console.log(JSON.stringify({ check: 'actual-packaged-browser-search', revision, runtimeVersion, results }, null, 2));
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
