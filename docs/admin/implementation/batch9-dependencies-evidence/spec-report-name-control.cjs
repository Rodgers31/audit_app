'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'batch9-dependencies-spec-name-'));
const frontend = path.resolve(__dirname, '../../../../frontend');
const gate = path.join(frontend, 'scripts/jest-dependency-boundary.test.cjs');
const npmValidator = require.resolve('validate-npm-package-name', { paths: [frontend] });
const validate = require(npmValidator);
const { classifyControl } = require('./control_contract.cjs');
const rows = [];
const sourceBefore = require('./control_contract.cjs').sourceIdentity(__filename);
try {
  const callers = ['@jest/core', 'jest-cli', 'jest-config', 'jest-message-util']
    .map(name => ({ name, version: '30.5.2' }));
  for (const name of ['.invalid', '@scope/.invalid', 'node_modules']) {
    const stub = path.join(root, 'npm-report.cjs');
    fs.writeFileSync(stub, `process.stdout.write(${JSON.stringify(JSON.stringify([...callers, { name, version: '3.0.3' }]))});`);
    const command = [process.execPath, '--test', '--test-name-pattern=^installed Jest', gate];
    const result = spawnSync(command[0], command.slice(1), {
      cwd: frontend, encoding: 'utf8', timeout: 15000,
      env: { PATH: process.env.PATH, npm_execpath: stub },
    });
    const observed = { ...result, error: result.error?.message || null };
    const classification = classifyControl('graph-hostile-name-'+rows.length, observed, 1);
    rows.push({ name, ...classification, npmValidation: validate(name), command, gateStatus: result.status,
      stdout: result.stdout, stderr: result.stderr, signal: result.signal,
      error: result.error?.message || null });
  }
  const sourceAfter = require('./control_contract.cjs').sourceIdentity(__filename, false);
  const sourceChanged = JSON.stringify(sourceBefore) !== JSON.stringify(sourceAfter);
  console.log(JSON.stringify({ generated_by: __filename,
    generator_sha256: sourceBefore.generator_sha256, source_before: sourceBefore, source_after: sourceAfter, source_changed: sourceChanged,
    generated_at: new Date().toISOString(), gate_sha256: hash(fs.readFileSync(gate)),
    npm_validator_sha256: hash(fs.readFileSync(npmValidator)),
    runtime: { node: process.version, platform: process.platform, arch: process.arch }, rows }, null, 2));
  process.exitCode = !sourceChanged && rows.length === 3 && rows.every(row => row.matchesExpectation) ? 0 : 1;
} finally { fs.rmSync(root, { recursive: true, force: true }); }
