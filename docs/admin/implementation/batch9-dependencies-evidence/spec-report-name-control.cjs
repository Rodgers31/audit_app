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
const npmValidator = '/Users/roger/.nvm/versions/node/v22.19.0/lib/node_modules/npm/node_modules/validate-npm-package-name/lib/index.js';
const validate = require(npmValidator);
const rows = [];
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
    rows.push({ name, npmValidation: validate(name), command, gateStatus: result.status,
      stdout: result.stdout, stderr: result.stderr, signal: result.signal,
      error: result.error?.message || null });
  }
  console.log(JSON.stringify({ generated_by: __filename,
    generator_sha256: hash(fs.readFileSync(__filename)),
    generated_at: new Date().toISOString(), gate_sha256: hash(fs.readFileSync(gate)),
    npm_validator_sha256: hash(fs.readFileSync(npmValidator)),
    runtime: { node: process.version, platform: process.platform, arch: process.arch }, rows }, null, 2));
  process.exitCode = rows.every(row => row.gateStatus === 1) ? 0 : 1;
} finally { fs.rmSync(root, { recursive: true, force: true }); }
