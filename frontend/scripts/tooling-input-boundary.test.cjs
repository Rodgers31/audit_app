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

for (const mode of ['override', 'extends', 'alternate', 'descendant', 'array', 'string']) {
  test(`standard lint refuses unsafe effective ${mode} configuration before Next runs`, () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'batch9-dependencies-eslint-'));
    try {
      fs.cpSync(__dirname, path.join(root, 'scripts'), { recursive: true });
      fs.symlinkSync(path.join(frontend, 'node_modules'), path.join(root, 'node_modules'), 'dir');
      fs.copyFileSync(path.join(frontend, 'tailwind.config.js'), path.join(root, 'tailwind.config.js'));
      fs.copyFileSync(path.join(frontend, 'package.json'), path.join(root, 'package.json'));
      fs.mkdirSync(path.join(root, 'app'));
      fs.writeFileSync(path.join(root, 'app/page.js'), 'export default function Page() { return <div>Fixture</div>; }');
      const config = { extends: 'next/core-web-vitals' };
      const unsafe = { settings: { next: { rootDir: deepPattern } } };
      if (mode === 'override') config.overrides = [{ files: ['*.js'], ...unsafe }];
      if (mode === 'extends') {
        config.extends = ['next/core-web-vitals', './inherited.json'];
        fs.writeFileSync(path.join(root, 'inherited.json'), JSON.stringify(unsafe));
      }
      if (mode === 'alternate') fs.writeFileSync(path.join(root, '.eslintrc.cjs'), `module.exports = ${JSON.stringify({ ...config, ...unsafe })};`);
      if (mode === 'descendant') fs.writeFileSync(path.join(root, 'app/.eslintrc.json'), JSON.stringify(unsafe));
      fs.writeFileSync(path.join(root, '.eslintrc.json'), JSON.stringify(mode === 'array' ? [] : mode === 'string' ? 'invalid' : config));
      assert.ok(process.env.npm_execpath, 'Run the suite through npm');
      const result = spawnSync(process.execPath, [process.env.npm_execpath, 'run', 'lint', '--', '--file', 'app/page.js'], {
        cwd: root, encoding: 'utf8', timeout: 15000,
        env: { PATH: process.env.PATH, NEXT_TELEMETRY_DISABLED: '1' },
      });
      assert.equal(result.status, 1, result.stdout || result.stderr || String(result.error));
      assert.match(result.stderr, /tooling input contract/);
      assert.doesNotMatch(result.stdout, /bounded-tooling-inputs|> next lint/);
      assert.doesNotMatch(result.stderr, /Maximum call stack size exceeded/);
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  });
}
