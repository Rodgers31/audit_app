'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const {createRequire} = require('node:module');
const {spawnSync} = require('node:child_process');
const {test} = require('node:test');

test('the NYC YAML CLI reports its package version', () => {
  const root = process.env.BATCH14_FRONTEND_ROOT;
  assert.ok(root && path.isAbsolute(root), 'set BATCH14_FRONTEND_ROOT to an installed owned frontend');
  const app = createRequire(path.join(fs.realpathSync(root), 'package.json'));
  const nyc = createRequire(app.resolve('@istanbuljs/load-nyc-config'));
  const yamlPackage = nyc.resolve('js-yaml/package.json');
  const metadata = JSON.parse(fs.readFileSync(yamlPackage, 'utf8'));
  for (const flag of ['--version', '-v']) {
    const child = spawnSync(process.execPath, [path.join(path.dirname(yamlPackage), 'bin/js-yaml.js'), flag], {encoding:'utf8',timeout:10000});
    assert.ifError(child.error);
    assert.equal(child.signal, null);
    assert.equal(child.status, 0, child.stderr);
    assert.equal(child.stdout, `${metadata.version}\n`, `${flag} must print its package version`);
  }
});
