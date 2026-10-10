'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const { ESLint } = require('eslint');
const tailwindRequire = createRequire(require.resolve('tailwindcss'));
const fastGlob = tailwindRequire('fast-glob');

// These are the complete reviewed source patterns, each with one five-item
// brace group. A new source scope needs a corresponding caller review.
const approvedContent = ['pages', 'components', 'app', 'src']
  .map(directory => `./${directory}/**/*.{js,ts,jsx,tsx,mdx}`);

function verifyNextSettings(config) {
  assert.ok(config && typeof config === 'object' && !Array.isArray(config),
    'tooling input contract: ESLint configuration must be an object');
  const settings = config.settings;
  assert.ok(settings === undefined || (settings && typeof settings === 'object' && !Array.isArray(settings)),
    'tooling input contract: ESLint settings must be an object');
  const next = settings?.next;
  assert.ok(next === undefined || (next && typeof next === 'object' && !Array.isArray(next)),
    'tooling input contract: Next lint settings must be an object');
  assert.ok(next?.rootDir === undefined,
    'tooling input contract: Next lint must use its literal default working directory, without root globs');
}

/**
 * Check the retained Tailwind patterns and ESLint's effective Next root setting.
 * @param {string} root Absolute frontend directory containing owned configuration.
 * @returns {Promise<object>} Reviewed patterns, literal Next root and checked-file count.
 * @throws {Error} Reject missing/malformed config, expanded source scope or root globs.
 */
async function verifyToolingInputs(root = path.resolve(__dirname, '..')) {
  let tailwind;
  try { tailwind = require(path.join(root, 'tailwind.config.js')); } catch {
    throw new Error('tooling input contract: Tailwind configuration cannot be loaded');
  }
  assert.ok(tailwind && typeof tailwind === 'object' && !Array.isArray(tailwind),
    'tooling input contract: Tailwind configuration must be an object');
  assert.deepEqual(tailwind.content, approvedContent,
    'tooling input contract: Tailwind content must retain the reviewed bounded source patterns');
  let eslint;
  try { eslint = JSON.parse(fs.readFileSync(path.join(root, '.eslintrc.json'), 'utf8')); } catch {
    throw new Error('tooling input contract: ESLint configuration must contain readable JSON');
  }
  verifyNextSettings(eslint);
  // These are Next lint's default directories and extensions. The scan itself
  // uses two constant, shallow brace groups, never caller-supplied patterns.
  const files = fastGlob.sync('{pages,components,lib,src,app}/**/*.{js,jsx,ts,tsx,mjs,cjs}', {
    cwd: root, absolute: true, onlyFiles: true, dot: true,
  });
  const lint = new ESLint({ cwd: root });
  const targets = [path.join(root, '__dependency_tooling_probe__.js'), ...files];
  let lintFilesChecked = 0;
  for (const file of targets) {
    if (file !== targets[0] && await lint.isPathIgnored(file)) continue;
    let effective;
    try { effective = await lint.calculateConfigForFile(file); } catch {
      throw new Error('tooling input contract: ESLint configuration cannot be resolved');
    }
    verifyNextSettings(effective);
    lintFilesChecked++;
  }
  return { tailwindPatterns: approvedContent, nextRoot: 'literal working directory', lintFilesChecked };
}

if (require.main === module) {
  verifyToolingInputs().then(result => {
    console.log(JSON.stringify({ check: 'bounded-tooling-inputs', ...result }));
  }).catch(error => {
    console.error(error.message);
    process.exitCode = 1;
  });
}

module.exports = { verifyToolingInputs };
