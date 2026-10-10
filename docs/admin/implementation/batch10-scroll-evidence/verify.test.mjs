import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, rmSync, unlinkSync, writeFileSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { gzipSync, gunzipSync } from 'node:zlib';
import test from 'node:test';
import { verifyPackage } from './verify.mjs';

const root = dirname(fileURLToPath(import.meta.url));
const repo = resolve(root, '../../../..');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
function fixture(t) {
  const directory = mkdtempSync(resolve(tmpdir(), 'batch10-scroll-verifier-'));
  cpSync(root, directory, { recursive: true });
  t.after(() => rmSync(directory, { recursive: true }));
  const manifest = JSON.parse(readFileSync(resolve(directory, 'manifest.json')));
  const save = () => writeFileSync(resolve(directory, 'manifest.json'), JSON.stringify(manifest));
  return { directory, manifest, save };
}
function replaceJson(f, path, change) {
  const entry = f.manifest.files.find(item => item.path === path);
  const value = JSON.parse(gunzipSync(readFileSync(resolve(f.directory, path))));
  change(value);
  const raw = Buffer.from(JSON.stringify(value));
  const encoded = gzipSync(raw);
  writeFileSync(resolve(f.directory, path), encoded);
  entry.sha256 = sha(encoded);
  entry.input_sha256 = sha(raw);
  f.save();
}

test('published archive verifies integrity while keeping the causal issue unresolved', async () => {
  const result = await verifyPackage(root, repo);
  assert.equal(result.archive_integrity, 'verified');
  assert.equal(result.issue_601, 'unresolved');
  assert.equal(result.passed, 312);
  assert.equal(result.existing_fixmes, 11);
});
for (const shape of [[], null, {}, 'garbage']) {
  test(`refuses empty or malformed file inventory: ${JSON.stringify(shape)}`, async t => {
    const f = fixture(t); f.manifest.files = shape; f.save();
    await assert.rejects(verifyPackage(f.directory, repo));
  });
}
test('refuses absent, tampered, unlisted, duplicate and symlinked archive data', async t => {
  for (const mode of ['absent', 'tampered', 'unlisted', 'duplicate', 'symlink']) {
    const f = fixture(t); const entry = f.manifest.files[0]; const path = resolve(f.directory, entry.path);
    if (mode === 'absent') unlinkSync(path);
    if (mode === 'tampered') writeFileSync(path, 'changed');
    if (mode === 'unlisted') writeFileSync(resolve(f.directory, 'data/unlisted'), 'unexpected');
    if (mode === 'duplicate') { f.manifest.files.push(entry); f.save(); }
    if (mode === 'symlink') { unlinkSync(path); symlinkSync(resolve(root, entry.path), path); }
    await assert.rejects(verifyPackage(f.directory, repo), undefined, mode);
  }
});
test('refuses a zero-test positive record even after archive hashes are updated', async t => {
  const f = fixture(t);
  replaceJson(f, f.manifest.targets[0].report, report => { report.suites = []; report.stats.expected = 0; });
  await assert.rejects(verifyPackage(f.directory, repo), /Frozen raw-input census changed/);
});
test('refuses an infrastructure failure masquerading as the native-absence assertion', async t => {
  const f = fixture(t);
  const target = f.manifest.targets.find(x => x.role === 'negative-detector');
  replaceJson(f, target.report, report => { report.suites = []; report.errors = [{message: 'missing browser'}]; });
  await assert.rejects(verifyPackage(f.directory, repo), /Frozen raw-input census changed/);
});
test('preserves the observed pagination failure without relabeling it a green replay', async t => {
  const f = fixture(t);
  const target = f.manifest.targets.find(x => x.role === 'observed-precondition-failure');
  target.role = 'positive-diagnostic'; f.save();
  await assert.rejects(verifyPackage(f.directory, repo), /Wrong targeted control identity/);
});
test('refuses source drift, wrong historical identity and a claimed resolution', async t => {
  for (const mode of ['source', 'history', 'resolved']) {
    const f = fixture(t);
    if (mode === 'source') { f.manifest.sources['frontend/e2e/smart-back.spec.ts'] = '0'.repeat(64); f.save(); }
    if (mode === 'history') replaceJson(f, f.manifest.historical_run, r => { r.headSha = '0'.repeat(40); });
    if (mode === 'resolved') { f.manifest.status = 'resolved'; f.save(); }
    await assert.rejects(verifyPackage(f.directory, repo), undefined, mode);
  }
});
test('refuses omitted cohorts and altered hostile counters in the frozen archive', async t => {
  const missing = fixture(t); missing.manifest.cohorts.pop(); missing.save();
  await assert.rejects(verifyPackage(missing.directory, repo), /Incomplete original cohort/);
  for (const value of [true, -1, null, '312']) {
    const f = fixture(t);
    replaceJson(f, f.manifest.cohorts[0].report, r => { r.stats.expected = value; });
    replaceJson(f, f.manifest.cohorts[0].receipt, r => { const d = JSON.parse(r.readback); d.stats.expected = value; r.readback = JSON.stringify(d); });
    await assert.rejects(verifyPackage(f.directory, repo));
  }
});

test('executes the original parser on valid results and hostile counters', () => {
  const manifest = JSON.parse(readFileSync(resolve(root, 'manifest.json')));
  const report = JSON.parse(gunzipSync(readFileSync(resolve(root, manifest.cohorts[0].report))));
  const inventory = JSON.parse(gunzipSync(readFileSync(resolve(root, manifest.inventory))));
  report.config.rootDir = resolve(repo, 'frontend/e2e');
  const parser = resolve(repo, 'frontend/scripts/ci-browser-cohorts.mjs');
  const code = `import {executionPassed} from ${JSON.stringify(pathToFileURL(parser).href)};let input='';for await(const chunk of process.stdin)input+=chunk;const {report,cases}=JSON.parse(input);if(!executionPassed(report,cases,0))throw Error('Valid control failed');let rejected=0;for(const value of [true,-1,null,'258',NaN,Infinity]){const changed=structuredClone(report);changed.stats.expected=value;try{if(executionPassed(changed,cases,0))throw Error('False success');}catch(e){if(e.message==='False success')throw e;rejected++;}}if(rejected!==6)throw Error('Missing rejection');console.log('Valid execution and six hostile counters verified');`;
  const output = execFileSync(process.execPath, ['--input-type=module', '-e', code], {cwd: resolve(repo, 'frontend'), input: JSON.stringify({report, cases: inventory.cohorts[0].cases}), encoding: 'utf8', timeout: 15000});
  assert.equal(output.trim(), 'Valid execution and six hostile counters verified');
});

test('seals command, measurement, prerequisite and diagnostic bytes', async t => {
  for (const kind of ['command', 'measurement', 'prerequisite', 'diagnostic']) await t.test(kind, async c => {
    const f = fixture(c);
    if (kind === 'command') replaceJson(f, f.manifest.targets[0].receipt, r => { r.command = []; });
    if (kind === 'measurement') {
      const entry = f.manifest.files.find(e => e.path === 'data/probe-hooks.ts.gz');
      const raw = Buffer.from('unrelated instrumentation'); const encoded = gzipSync(raw);
      writeFileSync(resolve(f.directory, entry.path), encoded); entry.sha256 = sha(encoded); entry.input_sha256 = sha(raw); f.save();
    }
    if (kind === 'prerequisite') {
      const entry = f.manifest.files.find(e => e.path === 'data/launch.json.gz');
      unlinkSync(resolve(f.directory, entry.path)); f.manifest.files = f.manifest.files.filter(e => e !== entry); f.save();
    }
    if (kind === 'diagnostic') replaceJson(f, f.manifest.cohorts[0].report, r => { r.suites[0].suites[0].specs[0].ok = false; });
    await assert.rejects(verifyPackage(f.directory, repo), /Frozen raw-input census changed/);
  });
});

test('rejects independently reproduced false-integrity paths', async t => {
  const mutations = [
    ['negative control replaced with positive', f => { Object.assign(f.manifest.targets[3], f.manifest.targets[0], {name: 'probe-native-absent-negative'}); f.save(); }],
    ['unrelated targeted case', f => replaceJson(f, f.manifest.targets[0].report, r => { const visit = s => { for (const p of s.specs) { p.file = 'absent.spec.ts'; p.title = 'unrelated'; p.line = 999; } (s.suites ?? []).forEach(visit); }; r.suites.forEach(visit); })],
    ['wrong targeted source hash', f => replaceJson(f, f.manifest.targets[0].receipt, r => { r.source_hashes['frontend/e2e/smart-back.spec.ts'] = '0'.repeat(64); })],
    ['wrong targeted commit', f => replaceJson(f, f.manifest.targets[0].receipt, r => { r.target_commit = '0'.repeat(40); })],
    ['wrong targeted log', f => replaceJson(f, f.manifest.targets[0].receipt, r => { r.log_sha256 = '0'.repeat(64); })],
    ['wrong manifest commit', f => { f.manifest.target_commit = '0'.repeat(40); f.save(); }],
    ['omitted scroll source census', f => { f.manifest.sources = Object.fromEntries(Object.entries(f.manifest.sources).slice(0, 8)); f.save(); }],
    ['failed full parent', f => replaceJson(f, 'data/full-original-chromium.json.gz', r => { r.child_exit = 1; r.verification_exit = 1; r.timeout = true; })],
    ['wrong full parent generator', f => replaceJson(f, 'data/full-original-chromium.json.gz', r => { r.generator_sha256 = '0'.repeat(64); })],
    ['full cohort infrastructure error', f => replaceJson(f, f.manifest.cohorts[0].receipt, r => { r.error = 'infrastructure failed'; r.readback = ''; })],
    ['full cohort retried', f => replaceJson(f, f.manifest.cohorts[0].report, r => { const visit = s => { for (const p of s.specs) for (const x of p.tests) x.results[0].retry = 100; (s.suites ?? []).forEach(visit); }; r.suites.forEach(visit); })],
    ['altered inventory metadata', f => replaceJson(f, f.manifest.inventory, r => { r.generator_sha256 = '0'.repeat(64); })],
    ['substituted inventory case', f => {
      let oldCase, newCase;
      replaceJson(f, f.manifest.cohorts[0].report, r => {
        const p = r.suites[0].suites[0].specs[0];
        oldCase = JSON.stringify({file: p.file, line: p.line, column: p.column, title: p.title});
        p.title = 'never executed'; p.line = 100000;
        newCase = JSON.stringify({file: p.file, line: p.line, column: p.column, title: p.title});
      });
      replaceJson(f, f.manifest.inventory, r => {
        for (const cases of [r.baseline_cases, ...r.cohorts.map(c => c.cases)]) {
          const i = cases.indexOf(oldCase); if (i >= 0) cases[i] = newCase;
        }
      });
    }],
    ['unknown compression', f => { const entry = f.manifest.files.find(e => e.path === 'data/python-runtime.txt.gz'); entry.compression = 'unknown'; entry.input_sha256 = entry.sha256; f.save(); }],
  ];
  for (const [name, mutate] of mutations) await t.test(name, async c => {
    const f = fixture(c); mutate(f);
    await assert.rejects(verifyPackage(f.directory, repo));
  });
});
