'use strict';

const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const path = require('node:path');
const root = path.resolve(process.argv[2]);
const local = createRequire(path.join(root, 'package.json'));
const pattern = '{'.repeat(4000) + 'a,b' + '}'.repeat(4000);
const results = [];
for (const name of ['tailwindcss', '@next/eslint-plugin-next']) {
  const caller = createRequire(local.resolve(name));
  const glob = caller('fast-glob');
  const globRequire = createRequire(caller.resolve('fast-glob'));
  const mmRequire = createRequire(globRequire.resolve('micromatch'));
  assert.throws(() => glob.sync(pattern), RangeError);
  results.push({ caller: name, callerVersion: local(name + '/package.json').version,
    fastGlob: globRequire('./package.json').version, braces: mmRequire('braces/package.json').version,
    diagnostic: 'RangeError', patternLength: pattern.length });
}
const yaml = createRequire(local.resolve('@istanbuljs/load-nyc-config'));
const argparse = createRequire(yaml.resolve('js-yaml'));
const format = createRequire(argparse.resolve('argparse'));
assert.throws(() => format('sprintf-js').sprintf('%.101f', 1), RangeError);
results.push({ caller: 'argparse', version: argparse('argparse/package.json').version,
  sprintf: format('sprintf-js/package.json').version, input: '%.101f', diagnostic: 'RangeError' });
console.log(JSON.stringify({ check: 'current-reachable-primitives', results }, null, 2));
