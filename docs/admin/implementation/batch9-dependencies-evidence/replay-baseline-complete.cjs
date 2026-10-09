'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const crypto = require('node:crypto');
const repo = path.resolve(__dirname, '../../../..');
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'batch9-dependencies-red-'));
try {
  const frontend = path.join(repo, 'frontend');
  fs.cpSync(path.join(frontend, 'scripts'), path.join(root, 'scripts'), { recursive: true });
  fs.copyFileSync(path.join(frontend, 'tailwind.config.js'), path.join(root, 'tailwind.config.js'));
  fs.copyFileSync(path.join(frontend, '.eslintrc.json'), path.join(root, '.eslintrc.json'));
  fs.copyFileSync(path.join(frontend, 'package.json'), path.join(root, 'package.json'));
  fs.symlinkSync(path.join(frontend, 'node_modules'), path.join(root, 'node_modules'), 'dir');
  const old = fs.readFileSync(path.join(__dirname, 'historical-generators/baseline-672c5c0-verify-dependency-tooling.cjs'));
  if (crypto.createHash('sha256').update(old).digest('hex') !== 'dd00157cf8255ee809c7bd273d0ad67fa332fdaab06a39aa648fdb2310c755a0')
    throw new Error('Historical baseline producer hash differs');
  fs.writeFileSync(path.join(root, 'scripts/verify-dependency-tooling.cjs'), old);
  const env = { ...process.env, npm_execpath: require('./control_contract.cjs').npmCli() };
  delete env.NODE_TEST_CONTEXT;
  const result = spawnSync(process.execPath, ['--test', path.join(root, 'scripts/tooling-input-boundary.test.cjs')], { cwd: root, encoding: 'utf8', env });
  process.stdout.write(result.stdout);
  process.stderr.write(result.stderr);
  process.exitCode = result.status;
} finally { fs.rmSync(root, { recursive: true, force: true }); }
