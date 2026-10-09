'use strict';

const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createRequire } = require('node:module');
const test = require('node:test');

// Sharp declares this parser directly; do not rely on npm hoisting it.
const semver = createRequire(require.resolve('sharp'))('semver');

const frontend = path.resolve(__dirname, '..');
const jestCli = require.resolve('jest/bin/jest');

function exactVersion(value) {
  if (typeof value !== 'string') return false;
  const parsed = semver.parse(value);
  if (!parsed) return false;
  const canonical = parsed.version + (parsed.build.length ? `+${parsed.build.join('.')}` : '');
  return canonical === value && parsed.prerelease.every(identifier =>
    !/^\d+$/.test(String(identifier)) || Number.isSafeInteger(Number(identifier)));
}

function jest(args) {
  return spawnSync(process.execPath, [jestCli, ...args], {
    cwd: frontend, encoding: 'utf8', timeout: 15000,
  });
}

test('advertised Node runtime range fits installed application and Jest tooling', () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(frontend, 'package.json'), 'utf8'));
  const lock = JSON.parse(fs.readFileSync(path.join(frontend, 'package-lock.json'), 'utf8'));
  const advertised = manifest.engines.node;
  assert.ok(semver.validRange(advertised), 'Frontend must declare a valid Node runtime range');
  assert.deepEqual(lock.packages[''].engines, manifest.engines,
    'Manifest and lock root must advertise the same runtime contract');
  for (const name of ['next', 'jest', 'jest-environment-jsdom']) {
    const supported = require(`${name}/package.json`).engines.node;
    assert.ok(semver.subset(advertised, supported),
      `Frontend Node range ${advertised} advertises runtimes unsupported by ${name}: ${supported}`);
  }
  assert.ok(semver.satisfies(process.versions.node, advertised),
    `Executed Node ${process.versions.node} must meet the advertised runtime contract`);
});

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
    && exactVersion(pkg.version)), 'npm graph rows must identify packages');
  for (const caller of ['@jest/core', 'jest-cli', 'jest-config', 'jest-message-util']) {
    assert.ok(packages.some(pkg => pkg.name === caller), `npm graph must include ${caller}`);
  }
  assert.deepEqual(packages.filter(pkg => ['braces', 'micromatch'].includes(pkg.name))
    .map(pkg => `${pkg.name}@${pkg.version}`), []);
});

test('graph gate accepts exact prerelease and build versions without normalization', () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'batch9-dependencies-version-'));
  try {
    const callers = ['@jest/core', 'jest-cli', 'jest-config', 'jest-message-util']
      .map(name => ({ name, version: '30.5.2' }));
    for (const version of ['1.2.3-rc.1', '1.2.3+build.001', '1.2.3-rc.1+build.001']) {
      const npmCli = path.join(fixture, 'npm-report.cjs');
      fs.writeFileSync(npmCli, `process.stdout.write(${JSON.stringify(JSON.stringify([...callers, { name: 'ordinary-dependency', version }]))});\n`);
      const result = spawnSync(process.execPath, ['--test', '--test-name-pattern=^installed Jest', __filename], {
        cwd: frontend, encoding: 'utf8', timeout: 15000,
        env: { PATH: process.env.PATH, npm_execpath: npmCli },
      });
      assert.equal(result.status, 0, result.stdout || result.stderr || String(result.error));
    }
  } finally { fs.rmSync(fixture, { recursive: true, force: true }); }
});

test('graph gate rejects malformed rows and incomplete measurements', () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-app-jest-graph-'));
  try {
    const callers = ['@jest/core', 'jest-cli', 'jest-config', 'jest-message-util']
      .map(name => ({ name, version: '30.5.2' }));
    const core = callers[0];
    const cases = [[core], [core, {}], [core, { version: '3.0.3' }], [core, null],
      ...['not-a-version', '>=30', '30.x', '30.5', '30.5.2.1', '01.5.2',
        'v30.5.2', ' 30.5.2 ', '30.5.2-9007199254740992', '9007199254740992.0.0']
        .map(version => [...callers, { name: 'ordinary-dependency', version }])];
    for (const rows of cases) {
      const npmCli = path.join(fixture, 'npm-stub.cjs');
      fs.writeFileSync(npmCli, `process.stdout.write(${JSON.stringify(JSON.stringify(rows))});\n`);
      const result = spawnSync(process.execPath, ['--test', '--test-name-pattern=^installed Jest', __filename], {
        cwd: frontend, encoding: 'utf8', timeout: 15000,
        env: { PATH: process.env.PATH, npm_execpath: npmCli },
      });
      assert.equal(result.status, 1,
        `Malformed npm graph ${JSON.stringify(rows)} passed: ${result.stdout || result.stderr || String(result.error)}`);
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
