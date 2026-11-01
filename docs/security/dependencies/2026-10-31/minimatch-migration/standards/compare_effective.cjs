'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const { createRequire } = require('node:module');
const front = '/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app/frontend';
const { ESLint } = createRequire(path.join(front, 'package.json'))('eslint');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const before = JSON.parse(fs.readFileSync(path.join(__dirname, 'baseline-effective-configs.json')));
(async () => {
  const engine = new ESLint({ cwd: front }), differences = [], after = {};
  for (const [relative, expected] of Object.entries(before.paths)) {
    const file = path.join(front, relative);
    assert.equal(await engine.isPathIgnored(file), false, relative);
    const config = JSON.parse(JSON.stringify(await engine.calculateConfigForFile(file)).split(front).join('<frontend>'));
    const actual = hash(JSON.stringify(config)); after[relative] = actual;
    if (actual !== expected) differences.push({ relative, expected, actual, config });
  }
  for (const [relative, expected] of Object.entries(before.sourceInputs)) if (relative === '.eslintrc.json' || relative.startsWith('eslint-rules/')) assert.equal(hash(fs.readFileSync(path.join(front, relative))), expected, 'local policy bytes ' + relative);
  const result = { at: new Date().toISOString(), filesCompared: Object.keys(after).length, differences, configAndLocalRuleBytesUnchanged: true, paths: after };
  fs.writeFileSync(path.join(__dirname, 'effective-config-comparison.json'), JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify({ filesCompared: result.filesCompared, differences: differences.length, configAndLocalRuleBytesUnchanged: true }));
  assert.deepEqual(differences, []);
})().catch(error => { console.error(error); process.exitCode = 1; });
