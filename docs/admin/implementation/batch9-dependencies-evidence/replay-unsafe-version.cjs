'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const crypto = require('node:crypto');
const repo = path.resolve(__dirname, '../../../..');
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'batch9-dependencies-unsafe-version-'));
try {
  fs.mkdirSync(path.join(root, 'scripts'));
  fs.symlinkSync(path.join(repo, 'frontend/node_modules'), path.join(root, 'node_modules'), 'dir');
  const source = process.argv[2] === 'baseline'
    ? fs.readFileSync(path.join(__dirname, 'historical-generators/baseline-672c5c0-jest-dependency-boundary.test.cjs'), 'utf8')
    : fs.readFileSync(path.join(repo, 'frontend/scripts/jest-dependency-boundary.test.cjs'), 'utf8');
  assert.ok(source);
  if (process.argv[2] === 'baseline') assert.equal(crypto.createHash('sha256').update(source).digest('hex'),
    'a3988b46b0ba8b091c0081db9626d94e14e5e6aa93fb1e066f2861cea97eb3c7', 'Historical baseline graph hash differs');
  const target = path.join(root, 'scripts/jest-dependency-boundary.test.cjs');
  fs.writeFileSync(target, source);
  const callers = ['@jest/core', 'jest-cli', 'jest-config', 'jest-message-util'].map(name => ({ name, version: '30.5.2' }));
  const rows = [...callers, { name: 'ordinary-dependency', version: '30.5.2-9007199254740992' }];
  const report = path.join(root, 'npm-report.cjs');
  fs.writeFileSync(report, `process.stdout.write(${JSON.stringify(JSON.stringify(rows))});`);
  const result = spawnSync(process.execPath, ['--test', '--test-name-pattern=^installed Jest', target], {
    cwd: root, encoding: 'utf8', env: { PATH: process.env.PATH, npm_execpath: report }, timeout: 15000,
  });
  console.log(JSON.stringify({ mode: process.argv[2], source_sha256: crypto.createHash('sha256').update(source).digest('hex'), child_status: result.status, rows }));
  process.stdout.write(result.stdout);
  process.stderr.write(result.stderr);
  assert.equal(result.status, 1, 'Unsafe numeric prerelease must not produce an absence verdict');
  assert.match(result.stdout, /npm graph rows must identify packages/);
} finally { fs.rmSync(root, { recursive: true, force: true }); }
