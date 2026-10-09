import assert from 'node:assert/strict';
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const scripts = fileURLToPath(new URL('.', import.meta.url));
const names = ['public', 'users', 'operations', 'overview-audit', 'etl-ui', 'coordinator'];

// Import substitutions execute the real copied CLI without Docker, network
// listeners, browsers, shared results, or changes to the calling environment.
const childStub = `
import { EventEmitter } from 'node:events';
import { appendFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
const names = ${JSON.stringify(names)};
const mode = process.env.CI_LIFECYCLE_TEST_MODE;
let owner, container, present = false;
const log = (command, args) => appendFileSync('commands.jsonl', JSON.stringify({ command, args }) + '\\n');
function report(selected = names) {
  return { config: { rootDir: resolve('e2e') }, errors: [],
    suites: [{ specs: selected.map(name => ({ file: name + '.spec.ts', line: 1, column: 1, title: name,
      tests: [{ projectName: 'chromium', expectedStatus: 'passed', status: 'expected',
        results: [{ status: 'passed', duration: 1 }] }] })) }],
    stats: { expected: selected.length, unexpected: 0, flaky: 0, skipped: 0 } };
}
export function spawnSync(command, args, options = {}) {
  log(command, args);
  const okay = stdout => ({ status: 0, stdout, stderr: '' });
  if (command === 'git') return okay('a'.repeat(40) + '\\n');
  if (args.includes('--list')) return okay(JSON.stringify(report(options.env?.BROWSER_TEST_COHORT
    ? [options.env.BROWSER_TEST_COHORT] : names)));
  if (command !== 'docker') throw new Error('Unexpected fake command');
  if (args[0] === 'run') {
    owner = args[args.indexOf('--label') + 1].split('=')[1];
    container = args[args.indexOf('--name') + 1];
    present = mode !== 'failed-no-container';
    return ['failed-partial-container', 'failed-no-container'].includes(mode)
      ? { status: 1, stdout: '', stderr: 'simulated partial start' } : okay('owned-id\\n');
  }
  if (args[0] === 'ps') return okay(present ? container + '\\n' : '');
  if (args[0] === 'inspect' && args.includes('--format')) return okay(mode === 'wrong-owner'
    ? 'unrelated-run\\n' : owner + '\\n');
  if (args[0] === 'inspect') return okay(JSON.stringify([{ Id: 'owned-id' }]));
  if (args[0] === 'rm') { present = false; return okay('removed\\n'); }
  if (args[0] === 'exec' && args.includes('pg_isready')) {
    if (!args.includes('-h') || args[args.indexOf('-h') + 1] !== '127.0.0.1') {
      throw new Error('Readiness used the temporary initialization Unix socket');
    }
    return okay('ready');
  }
  if (args[0] === 'exec' && args.includes('psql')) return okay('CREATE');
  throw new Error('Unexpected fake Docker command');
}
export function spawn(command, args, options) {
  log(command, args);
  const child = new EventEmitter();
  child.kill = signal => { queueMicrotask(() => child.emit('exit', null, signal)); return true; };
  const cohort = options.env.BROWSER_TEST_COHORT;
  if (mode === 'interrupted') { queueMicrotask(() => process.emit('SIGTERM')); return child; }
  if (!['stale-results', 'absent-results'].includes(mode)) {
    const folder = resolve('legacy-results', cohort);
    mkdirSync(folder, { recursive: true });
    const data = report([cohort]);
    if (mode === 'failed-case' && cohort === 'users') {
      data.suites[0].specs[0].tests[0].status = 'unexpected';
      data.suites[0].specs[0].tests[0].results[0].status = 'failed';
      data.stats.expected = 0; data.stats.unexpected = 1;
    }
    writeFileSync(resolve(folder, 'results.json'), JSON.stringify(data));
  }
  queueMicrotask(() => child.emit('exit', 0));
  return child;
}
`;

function scenario(mode, inspect) {
  const root = realpathSync(mkdtempSync(resolve(tmpdir(), 'ci-browser-lifecycle-')));
  try {
    mkdirSync(resolve(root, 'scripts'));
    mkdirSync(resolve(root, 'e2e'));
    mkdirSync(resolve(root, 'legacy-results'));
    for (const name of ['run-legacy-e2e.mjs', 'ci-browser-cohorts.mjs', 'legacy-e2e-env.mjs']) {
      copyFileSync(resolve(scripts, name), resolve(root, 'scripts', name));
    }
    for (const name of names) {
      writeFileSync(resolve(root, 'e2e', `${name}.spec.ts`), '// isolated source fixture\n');
      if (mode === 'stale-results') {
        const folder = resolve(root, 'legacy-results', name);
        mkdirSync(folder, { recursive: true });
        writeFileSync(resolve(folder, 'results.json'), JSON.stringify({
          config: { rootDir: resolve(root, 'e2e') }, errors: [],
          suites: [{ specs: [{ file: `${name}.spec.ts`, line: 1, column: 1, title: name,
            tests: [{ projectName: 'chromium', expectedStatus: 'passed', status: 'expected',
              results: [{ status: 'passed', duration: 1 }] }] }] }],
          stats: { expected: 1, unexpected: 0, flaky: 0, skipped: 0 },
        }));
      }
    }
    const summaryPath = resolve(root, 'legacy-results/summary.json');
    writeFileSync(summaryPath, '{"verdict":"PASSED","stale":true}');
    writeFileSync(resolve(root, 'commands.jsonl'), '');
    writeFileSync(resolve(root, 'child-stub.mjs'), childStub);
    writeFileSync(resolve(root, 'net-stub.mjs'), `
      export function createServer() {
        return { once() {}, listen(port, host, callback) { queueMicrotask(callback); }, close(callback) { callback(); } };
      }
    `);
    writeFileSync(resolve(root, 'loader.mjs'), `
      import { pathToFileURL } from 'node:url';
      import { resolve as pathResolve } from 'node:path';
      export async function resolve(specifier, context, nextResolve) {
        const stub = { 'node:child_process': 'child-stub.mjs', 'node:net': 'net-stub.mjs' }[specifier];
        return stub ? { url: pathToFileURL(pathResolve(stub)).href, shortCircuit: true }
          : nextResolve(specifier, context);
      }
    `);
    const env = Object.fromEntries(['PATH', 'HOME', 'TMPDIR'].filter(key => process.env[key])
      .map(key => [key, process.env[key]]));
    const result = spawnSync(process.execPath, ['--no-warnings', '--loader', resolve(root, 'loader.mjs'),
      resolve(root, 'scripts/run-legacy-e2e.mjs'), ...(mode === 'invalid-argument' ? ['--grep', 'omit'] : [])], {
      cwd: root, env: { ...env, CI_LIFECYCLE_TEST_MODE: mode }, encoding: 'utf8', timeout: 15000,
    });
    assert.equal(result.error, undefined, result.error?.message);
    const commands = readFileSync(resolve(root, 'commands.jsonl'), 'utf8').trim().split('\n')
      .filter(Boolean).map(line => JSON.parse(line));
    const summary = existsSync(summaryPath) ? JSON.parse(readFileSync(summaryPath, 'utf8')) : undefined;
    assert.notEqual(summary?.stale, true, 'a stale success summary survived this attempt');
    inspect({ result, commands, summary });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

const removed = commands => commands.filter(command => command.command === 'docker' && command.args[0] === 'rm');
function assertOwnedRemoval(commands) {
  const started = commands.find(command => command.command === 'docker' && command.args[0] === 'run');
  const name = started.args[started.args.indexOf('--name') + 1];
  assert.ok(name.startsWith('batch9-ci-browser-'), name);
  assert.deepEqual(removed(commands).map(command => command.args), [['rm', '--force', name]]);
  const ownershipChecks = commands.filter(command => command.command === 'docker' && command.args[0] === 'inspect'
    && command.args.includes('--format'));
  assert.equal(ownershipChecks.length, 1);
  assert.equal(ownershipChecks[0].args.at(-1), name);
}

test('complete CLI succeeds only with fresh reports and removes its owned database', () => {
  scenario('all-pass', ({ result, summary, commands }) => {
    assert.equal(result.status, 0, result.stderr);
    assert.equal(summary.verdict, 'PASSED');
    assert.equal(summary.inventory_total, names.length);
    assert.deepEqual(summary.cohort_exit_codes, Object.fromEntries(names.map(name => [name, 0])));
    assert.equal(summary.owned_database_removed, true);
    const started = commands.find(command => command.command === 'docker' && command.args[0] === 'run');
    assert.equal(started.args.at(-1), 'public.ecr.aws/docker/library/postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675');
    assert.equal(started.args[started.args.indexOf('--platform') + 1], 'linux/amd64');
    assertOwnedRemoval(commands);
  });
});

for (const mode of ['failed-case', 'absent-results', 'stale-results', 'interrupted']) {
  test(`complete CLI refuses ${mode} and clears stale success`, () => {
    scenario(mode, ({ result, summary, commands }) => {
      assert.equal(result.status, 1, result.stderr);
      assert.equal(summary.verdict, 'FAILED');
      assert.equal(summary.owned_database_removed, true);
      assertOwnedRemoval(commands);
      if (mode === 'interrupted') assert.deepEqual(Object.keys(summary.cohort_exit_codes), ['public']);
      else assert.deepEqual(Object.keys(summary.cohort_exit_codes), names);
    });
  });
}

for (const [mode, removeCount, message] of [
  ['failed-partial-container', 1, 'simulated partial start'],
  ['failed-no-container', 0, 'simulated partial start'],
  ['wrong-owner', 0, 'owned by another run'],
  ['invalid-argument', 0, 'accepts only --list'],
]) {
  test(`complete CLI refuses ${mode} and preserves ownership`, () => {
    scenario(mode, ({ result, summary, commands }) => {
      assert.equal(result.status, 1, result.stderr);
      assert.equal(summary, undefined);
      assert.equal(removed(commands).length, removeCount);
      if (removeCount) assertOwnedRemoval(commands);
      assert.ok(result.stderr.includes(message), result.stderr);
    });
  });
}
