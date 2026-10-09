'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// These are the complete reviewed source patterns, each with one five-item
// brace group. A new source scope needs a corresponding caller review.
const approvedContent = ['pages', 'components', 'app', 'src']
  .map(directory => `./${directory}/**/*.{js,ts,jsx,tsx,mdx}`);

function verifyToolingInputs(root = path.resolve(__dirname, '..')) {
  const tailwind = require(path.join(root, 'tailwind.config.js'));
  assert.deepEqual(tailwind.content, approvedContent,
    'tooling input contract: Tailwind content must retain the reviewed bounded source patterns');
  const eslint = JSON.parse(fs.readFileSync(path.join(root, '.eslintrc.json'), 'utf8'));
  const settings = eslint.settings;
  assert.ok(settings === undefined || (settings && typeof settings === 'object' && !Array.isArray(settings)),
    'tooling input contract: ESLint settings must be an object');
  const next = settings?.next;
  assert.ok(next === undefined || (next && typeof next === 'object' && !Array.isArray(next)),
    'tooling input contract: Next lint settings must be an object');
  assert.ok(next?.rootDir === undefined,
    'tooling input contract: Next lint must use its literal default working directory, without root globs');
  return { tailwindPatterns: approvedContent, nextRoot: 'literal working directory' };
}

if (require.main === module) {
  try {
    console.log(JSON.stringify({ check: 'bounded-tooling-inputs', ...verifyToolingInputs() }));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}

module.exports = { verifyToolingInputs };
