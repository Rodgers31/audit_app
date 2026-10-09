'use strict';
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { classifyControl, npmCli } = require('../../docs/admin/implementation/batch9-dependencies-evidence/control_contract.cjs');

test('a missing graph test or syntax error cannot count as an intended rejection', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'batch9-evidence-control-'));
  try {
    const syntax = path.join(root, 'syntax.cjs');
    fs.writeFileSync(syntax, 'const = ;');
    for (const file of [path.join(root, 'absent.cjs'), syntax]) {
      const result = spawnSync(process.execPath, ['--test', file], {
        encoding: 'utf8', env: { PATH: process.env.PATH },
      });
      assert.equal(result.status, 1);
      assert.deepEqual(classifyControl('graph-hostile-name-0', result, 1), {
        matchesExpectation: false, classification: 'SETUP_OR_CONTRACT_FAILURE',
      });
    }
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test('the actual malformed configuration reaches the guard contract', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'batch9-evidence-guard-'));
  try {
    fs.writeFileSync(path.join(root, 'tailwind.config.js'), 'module.exports = null;');
    const result = spawnSync(process.execPath, ['-e',
      '(async()=>console.log({...await require(process.argv[1]).verifyToolingInputs(process.argv[2])}))().catch(e=>{console.error(e);process.exitCode=1;});',
      path.join(__dirname, 'verify-tooling-inputs.cjs'), root], { encoding: 'utf8' });
    assert.equal(result.status, 1);
    assert.deepEqual(classifyControl('guard-invalid-tailwind', result, 1), {
      matchesExpectation: true, classification: 'VALID_REJECTION',
    });
    assert.equal(classifyControl('unknown-control', result, 1).matchesExpectation, false);
    assert.equal(classifyControl('guard-invalid-tailwind', { ...result, signal: 'SIGTERM' }, 1).matchesExpectation, false);
    assert.equal(classifyControl('guard-invalid-tailwind', { ...result, error: new Error('spawn failed') }, 1).matchesExpectation, false);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test('npm CLI resolution uses the installed runtime', () => {
  const result = spawnSync(process.execPath, [npmCli(), '--version'], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /^\d+\.\d+\.\d+/);
});

for (const change of ['stable', 'source', 'delete', 'head', 'generator', 'child-failure']) {
  test(`actual command recorder binds pre-execution source for ${change}`, () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'batch9-recorder-control-'));
    const relative = 'docs/admin/implementation/batch9-dependencies-evidence';
    const packet = path.join(root, relative);
    try {
      fs.mkdirSync(packet, { recursive: true });
      fs.mkdirSync(path.join(root, 'frontend'));
      fs.writeFileSync(path.join(root, 'frontend/package.json'), '{"name":"owned-fixture"}\n');
      for (const name of ['run.cjs', 'control_contract.cjs'])
        fs.copyFileSync(path.resolve(__dirname, '../../', relative, name), path.join(packet, name));
      for (const args of [['init', '-q'], ['add', '.'], ['-c', 'user.name=Fixture', '-c',
        'user.email=fixture@example.invalid', 'commit', '-qm', 'owned source']]) {
        const result = spawnSync('git', args, { cwd: root, encoding: 'utf8' });
        assert.equal(result.status, 0, result.stderr);
      }
      const commands = {
        stable: '', source: 'require("node:fs").appendFileSync("frontend/package.json"," ");',
        delete: 'require("node:fs").unlinkSync("frontend/package.json");',
        generator: `require("node:fs").appendFileSync(${JSON.stringify(relative + '/run.cjs')},"\\n// mutation\\n");`,
        head: 'require("node:child_process").execFileSync("git",["-c","user.name=Fixture","-c","user.email=fixture@example.invalid","commit","--allow-empty","-qm","advance"]);',
        'child-failure': 'process.exit(7);',
      };
      const result = spawnSync(process.execPath, [path.join(packet, 'run.cjs'), 'receipt', root,
        process.execPath, '-e', commands[change]], { cwd: root, encoding: 'utf8', timeout: 15000 });
      const receipt = JSON.parse(fs.readFileSync(path.join(packet, 'receipt.json')));
      assert.equal(receipt.source_changed, !['stable', 'child-failure'].includes(change));
      assert.equal(receipt.verification_exit, change === 'stable' ? 0 : 1);
      assert.equal(result.status, receipt.verification_exit, result.stderr);
      assert.equal(receipt.exit, change === 'child-failure' ? 7 : 0);
      assert.equal(receipt.verdict, change === 'stable' ? 'COMMAND_SUCCEEDED' : 'COMMAND_FAILED');
      assert.ok(receipt.source_before.source_sha256['frontend/package.json']);
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  });
}
