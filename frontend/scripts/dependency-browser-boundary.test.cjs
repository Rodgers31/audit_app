'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const { test } = require('node:test');

const script = path.join(__dirname, '../tests/batch7DependencyBrowser.cjs');
const scriptRequire = createRequire(script);
const transformersRequire = createRequire(scriptRequire.resolve('@huggingface/transformers'));
const wasmDir = path.dirname(transformersRequire.resolve('onnxruntime-web'));
const runtimeVersion = scriptRequire(path.join(wasmDir, '../package.json')).version;
const runtimeName = 'ort-wasm-simd-threaded.asyncify.wasm';
const runtimeUrl = `https://cdn.jsdelivr.net/npm/onnxruntime-web@${runtimeVersion}/dist/${runtimeName}`;
const modelUrl = 'https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/config.json';

/**
 * Execute the verifier's actual registered route callback in isolated browser
 * doubles. This tests transport decisions; real browser/WASM replay is separate.
 * @param {string} requestedUrl The external request presented to both contexts.
 * @returns {Promise<object>} Main outcome and actual fulfillment/abort decisions.
 */
async function runVerifier(requestedUrl) {
  const state = { fulfilled: [], aborted: [], output: '', error: '' };
  const processDouble = { env: { DEPENDENCY_PREVIEW_URL: 'http://127.0.0.1:43193', NATIVE_VERIFY_CACHE_DIR: '/owned/inert-cache' }, exitCode: 0 };
  let settle;
  const done = new Promise(resolve => { settle = resolve; });
  let contexts = 0;
  const browser = {
    async newContext() {
      const allowModel = contexts++ === 1;
      let handleRoute;
      let query = '';
      const element = {
        async waitFor() {},
        locator() { return element; },
        async innerText() { return allowModel ? `Article ${query.includes('health') ? 43 : 142}\nSemantic result` : 'Article 1\nFallback result'; },
      };
      return {
        async addInitScript() {},
        async route(pattern, handler) { handleRoute = handler; },
        async newPage() {
          return {
            on() {},
            async goto() {
              await handleRoute({
                request: () => ({ url: () => requestedUrl }),
                async fulfill() { state.fulfilled.push(requestedUrl); },
                async abort() { state.aborted.push(requestedUrl); },
                async continue() { throw new Error('External request continued'); },
              });
            },
            getByRole(role) { return role === 'searchbox' ? { async fill(value) { query = value; } } : element; },
            getByText() { return element; },
            async waitForFunction() {},
            async evaluate() { return allowModel ? 1 : 0; },
          };
        },
        async close() {},
      };
    },
    async close() {},
  };
  const timer = setTimeout(() => settle(), 5000);
  const browserRequire = name => {
    if (name === '@playwright/test') return { chromium: { async launch() { return browser; } } };
    if (name === 'node:fs/promises') return { async readFile() { return Buffer.from('inert-fixture'); } };
    return scriptRequire(name);
  };
  browserRequire.resolve = scriptRequire.resolve;
  try {
    vm.runInNewContext(fs.readFileSync(script, 'utf8'), {
      require: browserRequire,
      process: processDouble,
      console: {
        log(value) { state.output = value; settle(); },
        error(value) { state.error = String(value); settle(); },
      },
      Buffer,
      URL,
    }, { filename: script });
    await done;
    assert.ok(state.output || state.error, 'Verifier did not complete');
    return { ...state, exitCode: processDouble.exitCode };
  } finally { clearTimeout(timer); }
}

for (const [name, url] of [
  ['unrelated runtime package', `https://cdn.jsdelivr.net/npm/unrelated@9/dist/${runtimeName}`],
  ['wrong runtime version', `https://cdn.jsdelivr.net/npm/onnxruntime-web@0.0.0/dist/${runtimeName}`],
  ['unversioned runtime', `https://unpkg.com/onnxruntime-web/dist/${runtimeName}`],
  ['runtime HTTP downgrade', runtimeUrl.replace('https:', 'http:')],
  ['runtime alternate port', runtimeUrl.replace('cdn.jsdelivr.net', 'cdn.jsdelivr.net:444')],
  ['runtime query', runtimeUrl + '?unexpected=1'],
  ['runtime credentials', runtimeUrl.replace('https://', 'https://inert-user@')],
  ['unapproved runtime basename', `https://cdn.jsdelivr.net/npm/onnxruntime-web@${runtimeVersion}/dist/ort-unexpected.wasm`],
  ['model HTTP downgrade', modelUrl.replace('https:', 'http:')],
  ['model alternate port', modelUrl.replace('huggingface.co', 'huggingface.co:444')],
  ['model query', modelUrl + '?unexpected=1'],
  ['model credentials', modelUrl.replace('https://', 'https://inert-user@')],
]) {
  test(`actual browser verifier rejects ${name}`, async () => {
    const result = await runVerifier(url);
    assert.equal(result.exitCode, 1, `Unexpected transport was certified: ${result.output}`);
    assert.equal(result.fulfilled.length, 0, JSON.stringify(result.fulfilled));
  });
}

for (const url of [runtimeUrl, runtimeUrl.replace('cdn.jsdelivr.net/npm/', 'unpkg.com/'), modelUrl]) {
  test(`actual browser verifier accepts the approved fixture ${url}`, async () => {
    const result = await runVerifier(url);
    assert.equal(result.exitCode, 0, result.error);
    assert.ok(result.fulfilled.length > 0);
  });
}
