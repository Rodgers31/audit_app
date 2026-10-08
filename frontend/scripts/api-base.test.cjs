const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');

// Load the actual API modules with only Axios/Supabase side effects replaced.
function apiModules(browser, env) {
  const cache = new Map();
  function load(file) {
    if (cache.has(file)) return cache.get(file);
    const exports = {}; cache.set(file, exports);
    const fakeAxios = { create: config => ({ defaults: config, interceptors: { request: { use() {} }, response: { use() {} } } }) };
    const context = {
      exports, URL, console, process: { env },
      require(name) {
        if (name === 'axios') return { __esModule: true, default: fakeAxios, AxiosError: class {}, CanceledError: class {} };
        if (name === '@/lib/supabase/client') return { createClient() {} };
        const target = path.resolve(path.dirname(file), name);
        if (target.endsWith('.cjs')) return require(target);
        return load(target + '.ts');
      },
    };
    if (browser) context.window = {};
    const source = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
    vm.runInNewContext(source, context);
    return exports;
  }
  return { axios: load(path.join(root, 'lib/api/axios.ts')), endpoints: load(path.join(root, 'lib/api/endpoints.ts')) };
}

const env = { NODE_ENV: 'production', NEXT_PUBLIC_API_URL: 'https://browser-backend.invalid', INTERNAL_API_URL: 'http://backend:8000' };
test('actual server Axios and endpoint helper use the internal transport', () => {
  const modules = apiModules(false, env);
  assert.equal(modules.axios.apiClient.defaults.baseURL, 'http://backend:8000/api/v1');
  assert.equal(modules.endpoints.getApiBaseUrl(), 'http://backend:8000/api/v1');
});
test('actual browser Axios and endpoint helper use the public transport', () => {
  const modules = apiModules(true, env);
  assert.equal(modules.axios.apiClient.defaults.baseURL, 'https://browser-backend.invalid/api/v1');
  assert.equal(modules.endpoints.getApiBaseUrl(), 'https://browser-backend.invalid/api/v1');
});
test('server without internal transport retains the public backend', () => {
  const { INTERNAL_API_URL, ...publicEnv } = env;
  const modules = apiModules(false, publicEnv);
  assert.equal(modules.axios.apiClient.defaults.baseURL, 'https://browser-backend.invalid/api/v1');
});
test('a supplied blank or malformed internal URL fails instead of silently switching transport', () => {
  for (const value of ['', ' ', 'backend:8000', 'https://user:pass@backend.invalid']) {
    assert.throws(() => apiModules(false, { ...env, INTERNAL_API_URL: value }), /INTERNAL_API_URL/);
  }
});

test('a supplied blank public URL fails instead of using localhost', () => {
  for (const value of ['', ' ']) {
    assert.throws(() => apiModules(true, { ...env, NEXT_PUBLIC_API_URL: value }), /NEXT_PUBLIC_API_URL/);
  }
});
