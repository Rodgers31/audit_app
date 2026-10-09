'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');

function sourceIdentity(generator, required = true) {
  const repo = path.resolve(__dirname, '../../../..');
  const git = args => execFileSync('git', args, { cwd: repo, encoding: 'utf8' }).trim();
  const files = git(['ls-files', 'frontend/package.json', 'frontend/package-lock.json',
    'frontend/scripts', 'frontend/jest.config.js', 'frontend/tailwind.config.js',
    'frontend/postcss.config.js', 'frontend/.eslintrc.json']).split('\n').filter(Boolean);
  if (!files.length) throw new Error('Evidence setup failed: no source inventory');
  const hash = file => fs.existsSync(file)
    ? crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex') : null;
  const source = Object.fromEntries(files.map(file => [file, hash(path.join(repo, file))]));
  if (required && Object.values(source).some(value => value === null)) throw new Error('Evidence setup failed: source file is absent');
  return { head: git(['rev-parse', 'HEAD']), tree: git(['rev-parse', 'HEAD^{tree}']),
    tracked_status: git(['status', '--porcelain', '--untracked-files=no']), source_sha256: source,
    generator_sha256: hash(generator), contract_sha256: hash(__filename) };
}

function npmCli() {
  const candidates = process.env.npm_execpath ? [process.env.npm_execpath] :
    (process.env.PATH || '').split(path.delimiter).map(dir => path.join(dir, 'npm'));
  for (const candidate of candidates) {
    if (path.isAbsolute(candidate) && fs.existsSync(candidate) && fs.statSync(candidate).isFile())
      return fs.realpathSync(candidate);
  }
  throw new Error('Evidence setup failed: npm CLI is unavailable');
}

function classifyControl(label, result, expected) {
  const stdout = result.stdout || '';
  const stderr = result.stderr || '';
  let reached = false;
  if (label.startsWith('guard-')) {
    if (expected === 0) {
      try {
        const value = JSON.parse(stdout.trim());
        reached = value.check === 'bounded-tooling-inputs' && Array.isArray(value.tailwindPatterns)
          && value.tailwindPatterns.length === 4 && Number.isSafeInteger(value.lintFilesChecked)
          && value.lintFilesChecked > 0;
      } catch { reached = false; }
    } else {
      reached = /tooling input contract:/.test(stderr)
        && !/bounded-tooling-inputs|Maximum call stack size exceeded/.test(stdout + stderr);
    }
  } else if (label.startsWith('standard-lint-')) {
    reached = expected === 0 ? /bounded-tooling-inputs/.test(stdout) && /No ESLint warnings or errors/.test(stdout)
      : /tooling input contract:/.test(stderr)
        && !/bounded-tooling-inputs|> next lint|Maximum call stack size exceeded/.test(stdout + stderr);
  } else if (label.startsWith('graph-')) {
    const named = /# Subtest: installed Jest dependency graph excludes the vulnerable brace compiler/.test(stdout);
    const count = /# tests 1(?:\r?\n|$)/.test(stdout);
    const verdict = expected === 0 ? /# pass 1(?:\r?\n|$)/.test(stdout) && /# fail 0(?:\r?\n|$)/.test(stdout)
      : /# pass 0(?:\r?\n|$)/.test(stdout) && /# fail 1(?:\r?\n|$)/.test(stdout);
    let reason = expected === 0;
    if (/^graph-(?:absent-output|invalid-json)$/.test(label))
      reason = /SyntaxError/.test(stdout) && /Unexpected end of JSON input|Unexpected token/.test(stdout);
    else if (/^graph-(?:empty-array|null|object)$/.test(label)) reason = /Jest graph must be measured/.test(stdout);
    else if (label === 'graph-missing-caller') reason = /npm graph must include @jest\/core/.test(stdout);
    else if (/^graph-excluded-(?:braces|micromatch)$/.test(label))
      reason = /Expected values to be strictly deep-equal/.test(stdout) && stdout.includes(label.slice('graph-excluded-'.length) + '@3.0.3');
    else if (expected === 1) reason = /npm graph rows must identify packages/.test(stdout);
    reached = named && count && verdict && reason;
  }
  const accepted = (expected === 0 || expected === 1) && result.status === expected
    && !result.error && result.signal === null && reached;
  return { matchesExpectation: accepted, classification: accepted
    ? (expected === 0 ? 'VALID_ACCEPTANCE' : 'VALID_REJECTION') : 'SETUP_OR_CONTRACT_FAILURE' };
}

module.exports = { npmCli, classifyControl, sourceIdentity };
