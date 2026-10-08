const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const test = require('node:test');
const root = path.resolve(__dirname, '..');

function nextConfig(apiURL, mode = 'production') {
  const env = { PATH: process.env.PATH, NODE_ENV: mode };
  if (apiURL !== undefined) env.NEXT_PUBLIC_API_URL = apiURL;
  return spawnSync(process.execPath, ['-e', "const c=require('./next.config.js');console.log(JSON.stringify({api:c.env.NEXT_PUBLIC_API_URL}))"], { cwd: root, env, encoding: 'utf8' });
}

for (const value of [undefined, '', ' ', 'localhost:8000', 'ftp://backend.invalid', 'https://user:password@backend.invalid', 'https://backend.invalid?query=1', 'https://backend.invalid/#fragment']) {
  test(`production public API rejects ${JSON.stringify(value)}`, () => {
    const result = nextConfig(value);
    assert.notEqual(result.status, 0, 'invalid public API config must fail before compilation');
    assert.match(result.stderr, /NEXT_PUBLIC_API_URL/);
  });
}

test('explicit public API accepts an absolute HTTP URL and normalizes its trailing slash', () => {
  const result = nextConfig('http://127.0.0.1:8125/');
  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(result.stdout.trim()).api, 'http://127.0.0.1:8125');
});

test('local development keeps its explicit localhost fallback', () => {
  const result = nextConfig(undefined, 'development');
  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(result.stdout.trim()).api, 'http://localhost:8000');
});

const { validatePublicConfig } = require('../lib/config/public-config.cjs');
const { validateRuntime } = require('./container-config.cjs');
const publicValues = {
  NEXT_PUBLIC_API_URL: 'https://public-backend.invalid',
  NEXT_PUBLIC_SUPABASE_URL: 'https://public-auth.invalid',
  NEXT_PUBLIC_SUPABASE_ANON_KEY: 'synthetic-public-anon-key',
};
const baked = { version: 1, publicConfig: validatePublicConfig(publicValues) };

for (const name of Object.keys(publicValues)) {
  test(`build validation requires ${name}`, () => {
    const env = { ...publicValues }; delete env[name];
    assert.throws(() => validatePublicConfig(env), new RegExp(name));
    assert.throws(() => validatePublicConfig({ ...publicValues, [name]: ' ' }), new RegExp(name));
  });
  test(`runtime rejects a changed ${name} without echoing its value`, () => {
    const value = name.includes('KEY') ? 'changed-synthetic-value' : 'https://changed.invalid';
    assert.throws(() => validateRuntime({ ...publicValues, [name]: value }, baked), error => {
      assert.match(error.message, new RegExp(name));
      assert(!error.message.includes(value)); return true;
    });
  });
}

test('runtime validates matching public values and permits a separate internal address', () => {
  assert.deepEqual(validateRuntime({ ...publicValues, INTERNAL_API_URL: 'http://backend:8000' }, baked), baked.publicConfig);
  assert.deepEqual(validateRuntime(publicValues, baked), baked.publicConfig);
});

test('runtime rejects an invalid internal address and invalid marker', () => {
  for (const url of ['', ' ', 'backend:8000', 'https://user:pass@backend.invalid']) {
    assert.throws(() => validateRuntime({ ...publicValues, INTERNAL_API_URL: url }, baked), /INTERNAL_API_URL/);
  }
  assert.throws(() => validateRuntime(publicValues, undefined), /marker/);
  assert.throws(() => validateRuntime(publicValues, { version: 2 }), /marker/);
});

test('workflow provides the required public API URL and preflights before registry writes', () => {
  const fs = require('node:fs');
  const yaml = require(path.join(root, 'node_modules/js-yaml'));
  const workflow = yaml.load(fs.readFileSync(path.join(root, '../.github/workflows/docker-build-deploy.yml'), 'utf8'));
  assert.equal(workflow.on.workflow_dispatch.inputs.public_api_url.required, true);
  const steps = workflow.jobs['build-and-push'].steps;
  const preflight = steps.findIndex(step => step.run === 'node frontend/scripts/container-config.cjs validate');
  assert(preflight >= 0);
  assert(preflight < steps.findIndex(step => step.uses === 'docker/login-action@v3'));
  assert(preflight < steps.findIndex(step => step.name === 'Build & Push Backend'));
  assert.equal(steps[preflight].env.NEXT_PUBLIC_API_URL, '${{ inputs.public_api_url }}');
  const build = steps.find(step => step.name === 'Build & Push Frontend');
  assert.equal(workflow.env.NEXT_PUBLIC_API_URL, undefined);
  assert.match(build.with['build-args'], /NEXT_PUBLIC_API_URL=\$\{\{ inputs.public_api_url \}\}/);
  const testBuild = workflow.jobs['test-frontend'].steps.find(step => step.name === 'Build Next.js (REQUIRED)');
  assert.equal(testBuild.env.NEXT_PUBLIC_API_URL, '${{ inputs.public_api_url }}');
});
