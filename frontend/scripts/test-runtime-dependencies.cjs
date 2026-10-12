'use strict';

const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

/**
 * Run installed-tree regressions in an existing owned pruned fixture or create
 * a fresh one. The build/test node_modules is never pruned or otherwise changed.
 * @returns {void} Set a failing exit code on installation or regression failure.
 */
function main() {
  const frontend = path.resolve(__dirname, '..');
  let owned;
  const root = process.env.RUNTIME_VERIFY_ROOT || (owned = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-app-runtime-boundary-')));
  try {
    if (owned) {
      for (const name of ['package.json', 'package-lock.json', 'eslint-rules']) {
        fs.cpSync(path.join(frontend, name), path.join(root, name), { recursive: true });
      }
      fs.mkdirSync(path.join(root, 'scripts'));
      for (const name of ['apply-tooling-repairs.cjs', 'tooling-repairs.json']) fs.copyFileSync(path.join(__dirname, name), path.join(root, 'scripts', name));
      const home = path.join(root, '.npm-home'); fs.mkdirSync(home);
      const userConfig = path.join(home, 'user-npmrc'), globalConfig = path.join(home, 'global-npmrc');
      fs.writeFileSync(userConfig, ''); fs.writeFileSync(globalConfig, '');
      const npmCli = process.env.npm_execpath;
      assert.ok(npmCli && path.isAbsolute(npmCli) && fs.statSync(npmCli).isFile(),
        'Run fresh installation through npm run test:dependency-boundaries');
      const install = spawnSync(process.execPath, [npmCli, 'ci', '--omit=dev', '--include=optional', '--no-audit', '--no-fund'], {
        cwd: root, stdio: 'inherit', timeout: 180000,
        env: { PATH: process.env.PATH, HOME: home, npm_config_userconfig: userConfig, npm_config_globalconfig: globalConfig, npm_config_cache: path.join(root, '.npm-cache'), npm_config_update_notifier: 'false', npm_config_engine_strict: 'true', ONNXRUNTIME_NODE_INSTALL: 'skip' },
      });
      assert.equal(install.status, 0, `Owned production install failed: ${install.error || install.signal || install.status}`);
    }
    const tests = spawnSync(process.execPath, ['--test', path.join(__dirname, 'runtime-dependencies.test.cjs'), path.join(__dirname, 'runtime-dependencies-isolation.test.cjs')], {
      cwd: frontend, stdio: 'inherit', timeout: 90000,
      env: { PATH: process.env.PATH, RUNTIME_VERIFY_ROOT: path.resolve(root) },
    });
    assert.equal(tests.status, 0, `Runtime regressions failed: ${tests.error || tests.signal || tests.status}`);
  } finally {
    if (owned) fs.rmSync(owned, { recursive: true, force: true });
  }
}

try { main(); } catch (error) { console.error(error); process.exitCode = 1; }
