'use strict';

const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const frontend = path.resolve(__dirname, '..');
const deepPattern = '{'.repeat(4000) + 'a,b' + '}'.repeat(4000);

for (const [name, content, settings] of [
  ['deep Tailwind brace glob', [deepPattern], undefined],
  ['unreviewed Tailwind source scope', ['../**/*.{js,ts}'], undefined],
  ['deep Next lint root glob', undefined, { next: { rootDir: deepPattern } }],
]) {
  test(`tooling verification refuses ${name} before its CSS success verdict`, () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'batch9-dependencies-input-'));
    try {
      fs.cpSync(__dirname, path.join(root, 'scripts'), { recursive: true });
      fs.symlinkSync(path.join(frontend, 'node_modules'), path.join(root, 'node_modules'), 'dir');
      const config = require('../tailwind.config.js');
      fs.writeFileSync(path.join(root, 'tailwind.config.js'),
        `const config = require(${JSON.stringify(path.join(frontend, 'tailwind.config.js'))});\nmodule.exports = { ...config, content: ${JSON.stringify(content || config.content)} };\n`);
      const eslint = JSON.parse(fs.readFileSync(path.join(frontend, '.eslintrc.json'), 'utf8'));
      if (settings) eslint.settings = settings;
      fs.writeFileSync(path.join(root, '.eslintrc.json'), JSON.stringify(eslint));
      const result = spawnSync(process.execPath, [path.join(root, 'scripts/verify-dependency-tooling.cjs')], {
        cwd: root, encoding: 'utf8', timeout: 15000,
      });
      assert.equal(result.status, 1, `Unsafe tooling inputs produced success: ${result.stdout}\n${result.stderr}`);
      assert.match(result.stderr, /tooling input contract/);
      assert.doesNotMatch(result.stdout, /Dependency tooling checks passed/);
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  });
}
