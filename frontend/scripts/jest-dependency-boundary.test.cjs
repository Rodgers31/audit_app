'use strict';

const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const frontend = path.resolve(__dirname, '..');
const jestCli = require.resolve('jest/bin/jest');

function jest(args) {
  return spawnSync(process.execPath, [jestCli, ...args], {
    cwd: frontend, encoding: 'utf8', timeout: 15000,
  });
}

test('installed Jest dependency graph excludes the vulnerable brace compiler', () => {
  const npmCli = process.env.npm_execpath;
  assert.ok(npmCli && path.isAbsolute(npmCli) && fs.statSync(npmCli).isFile(),
    'Run through npm run test:dependency-boundaries');
  const result = spawnSync(process.execPath, [npmCli, 'query', '#jest *', '--json'], {
    cwd: frontend, encoding: 'utf8', timeout: 15000, maxBuffer: 8 * 1024 * 1024,
  });
  assert.equal(result.status, 0, result.stderr || String(result.error));
  const packages = JSON.parse(result.stdout);
  assert.ok(Array.isArray(packages) && packages.length > 0, 'Jest graph must be measured');
  assert.ok(packages.every(pkg => pkg && typeof pkg === 'object' && !Array.isArray(pkg)
    && typeof pkg.name === 'string' && pkg.name.trim()
    && typeof pkg.version === 'string' && pkg.version.trim()), 'npm graph rows must identify packages');
  for (const caller of ['@jest/core', 'jest-cli', 'jest-config', 'jest-message-util']) {
    assert.ok(packages.some(pkg => pkg.name === caller), `npm graph must include ${caller}`);
  }
  assert.deepEqual(packages.filter(pkg => ['braces', 'micromatch'].includes(pkg.name))
    .map(pkg => `${pkg.name}@${pkg.version}`), []);
});

test('graph gate rejects malformed rows and incomplete measurements', () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-app-jest-graph-'));
  try {
    const core = { name: '@jest/core', version: '30.5.2' };
    for (const rows of [[core], [core, {}], [core, { version: '3.0.3' }], [core, null]]) {
      const npmCli = path.join(fixture, 'npm-stub.cjs');
      fs.writeFileSync(npmCli, `process.stdout.write(${JSON.stringify(JSON.stringify(rows))});\n`);
      const result = spawnSync(process.execPath, ['--test', '--test-name-pattern=^installed Jest', __filename], {
        cwd: frontend, encoding: 'utf8', timeout: 15000,
        env: { PATH: process.env.PATH, npm_execpath: npmCli },
      });
      assert.equal(result.status, 1, result.stderr || String(result.error));
      assert.match(result.stdout, /npm graph (?:rows must identify packages|must include)/);
    }
  } finally { fs.rmSync(fixture, { recursive: true, force: true }); }
});

test('application discovery keeps Node fixtures out of Jest', () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-app-jest-discovery-'));
  try {
    fs.mkdirSync(path.join(fixture, '__tests__'));
    for (const name of ['jest.setup.js', 'application.test.ts', 'node.test.cjs', '__tests__/node.cjs']) {
      fs.writeFileSync(path.join(fixture, name), '');
    }
    const result = jest(['--config', path.join(frontend, 'jest.config.js'), '--rootDir', fixture,
      '--listTests', '--json', '--runInBand']);
    assert.equal(result.status, 0, result.stderr || String(result.error));
    assert.deepEqual(JSON.parse(result.stdout).map(file => path.basename(file)), ['application.test.ts']);
  } finally { fs.rmSync(fixture, { recursive: true, force: true }); }
});

test('Jest executes matching tests and reports a real assertion failure', () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-app-jest-verdict-'));
  try {
    const file = path.join(fixture, 'positive.test.js');
    const config = JSON.stringify({ rootDir: fixture, testEnvironment: 'node', transform: {},
      testMatch: ['**/{positive,negative}.test.js'] });
    fs.writeFileSync(file, "test('positive', () => expect(2 + 2).toBe(4));\n");
    const positive = jest(['--config', config, '--runInBand', '--json']);
    assert.equal(positive.status, 0, positive.stderr || String(positive.error));
    assert.equal(JSON.parse(positive.stdout).numPassedTests, 1);
    fs.writeFileSync(path.join(fixture, 'negative.test.js'), "test('negative', () => expect(2 + 2).toBe(5));\n");
    const negative = jest(['--config', config, '--runInBand', '--json']);
    assert.equal(negative.status, 1, negative.stderr || String(negative.error));
    assert.equal(JSON.parse(negative.stdout).numFailedTests, 1);
    const malformed = jest(['--config', JSON.stringify({ rootDir: fixture, testMatch: [null] }), '--listTests']);
    assert.equal(malformed.status, 1, malformed.stderr || String(malformed.error));
  } finally { fs.rmSync(fixture, { recursive: true, force: true }); }
});
