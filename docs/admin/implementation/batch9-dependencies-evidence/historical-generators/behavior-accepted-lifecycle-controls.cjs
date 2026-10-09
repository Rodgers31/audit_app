'use strict';
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const repo = path.resolve(__dirname, '../../../..');
const frontend = path.join(repo, 'frontend');
const npmCli = '/Users/roger/.nvm/versions/node/v22.19.0/lib/node_modules/npm/bin/npm-cli.js';
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const roots = [];
const results = [];
const failures = [];
function run(label, command, args, cwd) {
  const output = spawnSync(command, args, { cwd, encoding: 'utf8', timeout: 20000, maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, NEXT_TELEMETRY_DISABLED: '1' } });
  const result = { label, command: [command, ...args], cwd, status: output.status, signal: output.signal,
    error: output.error?.message || null, stdout: output.stdout || '', stderr: output.stderr || '' };
  result.expected = 1;
  result.matchesExpectation = result.status === 1 && !result.error && result.signal === null && /tooling input contract/.test(result.stderr) && !/bounded-tooling-inputs|> next (?:dev|build|lint)|Dependency tooling checks passed|Maximum call stack size exceeded/.test(result.stdout + result.stderr);
  if (!result.matchesExpectation) failures.push(label);
  results.push(result);
  console.log(JSON.stringify({label,status:result.status,signal:result.signal,error:result.error,
    toolStarted: /> next (?:dev|build|lint)/.test(result.stdout), compatibilitySuccess: /Dependency tooling checks passed/.test(result.stdout)}));
}
try {
  for (const lifecycle of ['dev', 'build', 'lint']) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'batch9-dependencies-behavior-lifecycle-'));
    roots.push(root);
    fs.symlinkSync(path.join(frontend, 'node_modules'), path.join(root, 'node_modules'), 'dir');
    fs.mkdirSync(path.join(root, 'scripts'));
    fs.copyFileSync(path.join(frontend, 'scripts/verify-tooling-inputs.cjs'), path.join(root, 'scripts/verify-tooling-inputs.cjs'));
    fs.copyFileSync(path.join(frontend, 'package.json'), path.join(root, 'package.json'));
    fs.writeFileSync(path.join(root, 'tailwind.config.js'), `module.exports = { content: [${JSON.stringify('{'.repeat(4000) + 'a,b' + '}'.repeat(4000))}] };\n`);
    fs.writeFileSync(path.join(root, '.eslintrc.json'), '{}');
    run(`reject-before-${lifecycle}`, process.execPath, [npmCli, 'run', lifecycle], root);
  }
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'batch9-dependencies-behavior-compatibility-'));
  roots.push(root);
  fs.symlinkSync(path.join(frontend, 'node_modules'), path.join(root, 'node_modules'), 'dir');
  fs.mkdirSync(path.join(root, 'scripts'));
  for (const name of ['verify-tooling-inputs.cjs', 'verify-dependency-tooling.cjs'])
    fs.copyFileSync(path.join(frontend, 'scripts', name), path.join(root, 'scripts', name));
  fs.copyFileSync(path.join(frontend, 'tailwind.config.js'), path.join(root, 'tailwind.config.js'));
  fs.writeFileSync(path.join(root, '.eslintrc.json'), JSON.stringify({extends:'next/core-web-vitals',
    overrides:[{files:['*.js'],settings:{next:{rootDir:'{'.repeat(4000)+'a,b'+'}'.repeat(4000)}}}]}));
  run('css-verdict-with-unsafe-eslint-override', process.execPath, [path.join(root, 'scripts/verify-dependency-tooling.cjs')], root);
} finally {
  fs.writeFileSync(path.join(__dirname, 'behavior-accepted-lifecycle-results.json'), JSON.stringify({generated_by:__filename,
    generator_sha256:hash(fs.readFileSync(__filename)), generated_at:new Date().toISOString(),
    head:spawnSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8'}).stdout.trim(),
    runtime:{node:process.version,platform:process.platform,arch:process.arch},results,expectationFailures:failures},null,2)+'\n');
  for (const root of roots) fs.rmSync(root,{recursive:true,force:true});
}

console.log(JSON.stringify({controlRunnerCompleted:true, expectationFailures:failures}));
if (failures.length) process.exitCode = 1;
