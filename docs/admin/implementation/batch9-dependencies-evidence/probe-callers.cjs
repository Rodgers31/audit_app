'use strict';

const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const path = require('node:path');
const frontend = path.resolve(__dirname, '../../../../frontend');
const appRequire = createRequire(path.join(frontend, 'package.json'));
const tailwindRequire = createRequire(appRequire.resolve('tailwindcss'));
const nextLintRequire = createRequire(appRequire.resolve('@next/eslint-plugin-next'));
const nycRequire = createRequire(appRequire.resolve('@istanbuljs/load-nyc-config'));
const yamlRequire = createRequire(nycRequire.resolve('js-yaml'));
const argparseRequire = createRequire(yamlRequire.resolve('argparse'));
const pattern = '{'.repeat(4000) + 'a,b' + '}'.repeat(4000);
for (const [caller, call] of [
  ['tailwind fast-glob', () => tailwindRequire('fast-glob').generateTasks([pattern])],
  ['next lint fast-glob', () => nextLintRequire('fast-glob').generateTasks([pattern])],
  ['argparse sprintf primitive', () => argparseRequire('sprintf-js').sprintf('%.101f', 1)],
]) {
  assert.throws(call, RangeError);
  console.log(JSON.stringify({ caller, observable: 'RangeError', patternLength: pattern.length,
    limit: caller.includes('sprintf') ? '101 precision digits' : '4000 brace levels' }));
}
const yaml = nycRequire('js-yaml');
assert.deepEqual(yaml.load('include:\n  - src/**/*.ts\n'), { include: ['src/**/*.ts'] });
console.log(JSON.stringify({ caller: 'nyc js-yaml API', yamlParsing: true,
  note: 'YAML load is the actual library caller; the installed argparse CLI formatter is not invoked by YAML load.' }));
