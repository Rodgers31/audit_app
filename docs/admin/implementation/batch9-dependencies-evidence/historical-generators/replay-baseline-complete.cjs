'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const repo = path.resolve(__dirname, '../../../..');
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'batch9-dependencies-red-'));
try {
  const frontend = path.join(repo, 'frontend');
  fs.cpSync(path.join(frontend, 'scripts'), path.join(root, 'scripts'), { recursive: true });
  fs.copyFileSync(path.join(frontend, 'tailwind.config.js'), path.join(root, 'tailwind.config.js'));
  fs.copyFileSync(path.join(frontend, '.eslintrc.json'), path.join(root, '.eslintrc.json'));
  fs.symlinkSync(path.join(frontend, 'node_modules'), path.join(root, 'node_modules'), 'dir');
  const old = spawnSync('git', ['show', '672c5c011ce57dc41551f5fbc642bc4e69134c43:frontend/scripts/verify-dependency-tooling.cjs'], { cwd: repo, encoding: 'utf8' });
  if (old.status !== 0) throw new Error(old.stderr);
  fs.writeFileSync(path.join(root, 'scripts/verify-dependency-tooling.cjs'), old.stdout);
  const result = spawnSync(process.execPath, ['--test', path.join(root, 'scripts/tooling-input-boundary.test.cjs')], { cwd: root, encoding: 'utf8' });
  process.stdout.write(result.stdout);
  process.stderr.write(result.stderr);
  process.exitCode = result.status;
} finally { fs.rmSync(root, { recursive: true, force: true }); }
