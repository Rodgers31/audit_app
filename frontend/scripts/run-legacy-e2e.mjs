import { createHash, randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { resolve } from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { cohorts, cohortEnvironment, executionPassed, listedCases, verifyPartition } from './ci-browser-cohorts.mjs';
import { legacyEnvironment } from './legacy-e2e-env.mjs';

const script = fileURLToPath(import.meta.url);
const generatorHash = createHash('sha256').update(readFileSync(script)).digest('hex');
const output = resolve('legacy-results');
const target = checked('git', ['rev-parse', 'HEAD']).trim();
const owner = randomUUID();
const container = `batch9-ci-browser-${owner}`;
const image = 'postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675';
let ownedDatabase = false;
let active;
let interrupted = false;

function checked(command, args, options = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 120000, ...options });
  if (result.error || result.status !== 0) {
    throw new Error(`${command} failed: ${result.error?.message || result.stderr || result.stdout}`);
  }
  return result.stdout;
}

function writeReceipt(name, fields) {
  const receipt = { generated_by: 'frontend/scripts/run-legacy-e2e.mjs',
    generator_sha256: generatorHash, generated_at: new Date().toISOString(),
    target_commit: target, node_version: process.version, ...fields };
  const path = resolve(output, name);
  writeFileSync(path, JSON.stringify(receipt, null, 2) + '\n');
  if (JSON.stringify(JSON.parse(readFileSync(path, 'utf8'))) !== JSON.stringify(receipt)) {
    throw new Error('Browser receipt readback failed');
  }
}

function checkFree(port) {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.once('error', () => reject(new Error(`Owned browser port ${port} is already in use`)));
    server.listen(port, '127.0.0.1', () => server.close(resolvePort));
  });
}

async function startDatabase() {
  await checkFree(55494);
  // A failed docker run can still create its named container (for example,
  // if publishing the port races). The finally block must inspect that name.
  ownedDatabase = true;
  checked('docker', ['run', '--detach', '--name', container, '--platform', 'linux/amd64',
    '--label', `audit_app.ci.owner=${owner}`, '--publish', '127.0.0.1:55494:5432',
    '--env', 'POSTGRES_USER=batch9_ci', '--env', 'POSTGRES_PASSWORD=ci-inert-local',
    '--env', 'POSTGRES_DB=batch9_ci', image]);
  let ready = false;
  for (let attempt = 0; attempt < 60; attempt++) {
    // The image's temporary initialization server accepts Unix sockets before
    // it shuts down; TCP becomes available only on the final PostgreSQL server.
    const result = spawnSync('docker', ['exec', container, 'pg_isready', '-h', '127.0.0.1', '-U', 'batch9_ci'], { encoding: 'utf8' });
    if (result.status === 0) { ready = true; break; }
    await new Promise(resolveDelay => setTimeout(resolveDelay, 500));
  }
  if (!ready) throw new Error('Owned browser PostgreSQL did not become ready');
  for (const sql of [
    "CREATE ROLE fixture LOGIN PASSWORD 'fixture'",
    'CREATE DATABASE fixture OWNER fixture',
    "CREATE ROLE batch7_coordinator LOGIN PASSWORD 'batch7-inert-coordinator-local'",
    'CREATE DATABASE batch7_coordinator OWNER batch7_coordinator',
  ]) checked('docker', ['exec', container, 'psql', '-U', 'batch9_ci', '-d', 'postgres',
    '-v', 'ON_ERROR_STOP=1', '-c', sql]);
  writeReceipt('database.json', { container, image, port: 55494, owner,
    container_identity: JSON.parse(checked('docker', ['inspect', container]))[0].Id });
}

function stopDatabase() {
  if (!ownedDatabase) return;
  const names = checked('docker', ['ps', '--all', '--filter', `name=^/${container}$`, '--format', '{{.Names}}']).trim();
  if (!names) { ownedDatabase = false; return; }
  if (names !== container) throw new Error('Unexpected database container identity');
  const label = checked('docker', ['inspect', '--format', '{{index .Config.Labels "audit_app.ci.owner"}}', container]).trim();
  if (label !== owner) throw new Error('Refusing to clean up a database owned by another run');
  checked('docker', ['rm', '--force', container]);
  ownedDatabase = false;
}

async function run(command, args, env) {
  return new Promise((resolveRun, reject) => {
    active = spawn(command, args, { env, stdio: 'inherit' });
    active.once('error', reject);
    active.once('exit', code => { active = undefined; resolveRun(code ?? 1); });
  });
}

function list(config, env) {
  return listedCases(JSON.parse(checked(process.execPath,
    ['node_modules/@playwright/test/cli.js', 'test', '--config', config,
      '--project=chromium', '--list', '--reporter=json'], { env })));
}

async function main() {
  const args = process.argv.slice(2);
  mkdirSync(output, { recursive: true });
  for (const file of ['summary.json', 'inventory.json', 'database.json']) {
    try { unlinkSync(resolve(output, file)); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  if (args.length > 1 || (args.length && args[0] !== '--list')) {
    throw new Error('The complete browser gate accepts only --list; case filtering would omit required cohorts');
  }
  const baseline = list('playwright.config.ts', legacyEnvironment());
  const inventories = cohorts.map(cohort => ({ name: cohort.name,
    cases: list('playwright.ci-cohorts.config.ts', cohortEnvironment(cohort, { ...process.env, BROWSER_TARGET_SHA: target })) }));
  const count = verifyPartition(baseline, inventories.map(cohort => cohort.cases));
  writeReceipt('inventory.json', { total: count, baseline_cases: baseline, cohorts: inventories });
  console.log(`Complete Chromium inventory: ${count} cases in ${cohorts.length} disjoint fixture cohorts`);
  if (args[0] === '--list') return 0;
  await Promise.all(cohorts.flatMap(cohort => [checkFree(cohort.api), checkFree(cohort.web)]));
  const results = {};
  try {
    await startDatabase();
    for (const cohort of cohorts) {
      if (interrupted) break;
      // Only evidence emitted by this invocation can certify its child. A
      // zero exit without a fresh report must not reuse a prior green result.
      try { unlinkSync(resolve(output, cohort.name, 'results.json')); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
      results[cohort.name] = await run(process.execPath,
        ['node_modules/@playwright/test/cli.js', 'test', '--config', 'playwright.ci-cohorts.config.ts', '--project=chromium'],
        cohortEnvironment(cohort, { ...process.env, BROWSER_TARGET_SHA: target }));
      try {
        const report = JSON.parse(readFileSync(resolve(output, cohort.name, 'results.json'), 'utf8'));
        if (!executionPassed(report, inventories.find(item => item.name === cohort.name).cases, results[cohort.name])) {
          results[cohort.name] = results[cohort.name] || 1;
        }
      } catch (error) {
        console.error(`${cohort.name} execution evidence refused: ${error.message}`);
        results[cohort.name] = results[cohort.name] || 1;
      }
    }
  } finally {
    stopDatabase();
  }
  const passed = Object.keys(results).length === cohorts.length && Object.values(results).every(code => code === 0);
  writeReceipt('summary.json', { inventory_total: count, cohort_exit_codes: results,
    verdict: passed ? 'PASSED' : 'FAILED', owned_database_removed: !ownedDatabase });
  return passed ? 0 : 1;
}

for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { interrupted = true; active?.kill(signal); });
try {
  process.exitCode = await main();
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
