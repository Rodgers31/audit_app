'use strict';

if (process.argv.includes('--verify-existing')) {
  require('./verify-historical.cjs');
} else {

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const repo = path.resolve(__dirname, '../../../..');
const hash = data => crypto.createHash('sha256').update(data).digest('hex');
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const names = fs.readdirSync(__dirname).filter(name => /\.(json|stdout|stderr)$/.test(name) && name !== 'summary.json').sort();
assert.ok(names.length > 0);
assert.ok(!fs.existsSync(path.join(__dirname, 'summary.json')), 'Summary is append-only');
const commands = [];
for (const name of names.filter(name => name.endsWith('.json'))) {
  const receipt = JSON.parse(fs.readFileSync(path.join(__dirname, name), 'utf8'));
  assert.equal(typeof receipt.generated_by, 'string', name);
  assert.equal(hash(fs.readFileSync(path.resolve(repo, receipt.generated_by))), receipt.generator_sha256, name);
  if (receipt.recorder_runtime) {
    const stem = name.slice(0, -5);
    for (const stream of ['stdout', 'stderr']) assert.equal(hash(fs.readFileSync(path.join(__dirname, `${stem}.${stream}`))), receipt[`${stream}_sha256`], name);
    assert.equal(receipt.verdict, receipt.exit === 0 ? 'COMMAND_SUCCEEDED' : 'COMMAND_FAILED');
    commands.push({ receipt: name, command: receipt.command, cwd: receipt.cwd, exit: receipt.exit, source_commit: receipt.target_commit });
  }
}

function audit(name) {
  const data = JSON.parse(fs.readFileSync(path.join(__dirname, `${name}.stdout`), 'utf8'));
  assert.equal(data.auditReportVersion, 2);
  assert.ok(object(data.vulnerabilities) && object(data.metadata?.vulnerabilities));
  assert.ok(Number.isSafeInteger(data.metadata.dependencies.total) && data.metadata.dependencies.total > 0);
  const entries = Object.keys(data.vulnerabilities);
  const severities = ['info', 'low', 'moderate', 'high', 'critical'];
  for (const severity of severities) assert.ok(Number.isSafeInteger(data.metadata.vulnerabilities[severity]) && data.metadata.vulnerabilities[severity] >= 0);
  assert.equal(severities.reduce((sum, severity) => sum + data.metadata.vulnerabilities[severity], 0), entries.length);
  assert.equal(data.metadata.vulnerabilities.total, entries.length);
  for (const key of entries) {
    const entry = data.vulnerabilities[key];
    assert.ok(object(entry) && entry.name === key && Array.isArray(entry.via) && entry.via.length > 0);
    assert.ok(Array.isArray(entry.nodes) && entry.nodes.length > 0 && entry.nodes.every(node => typeof node === 'string' && node.startsWith('node_modules/')));
    assert.ok(severities.includes(entry.severity));
    for (const via of entry.via) assert.ok(typeof via === 'string' ? data.vulnerabilities[via] : object(via) && typeof via.url === 'string' && via.url.startsWith('https://github.com/advisories/'));
  }
  function roots(key, visited = new Set()) {
    if (visited.has(key)) return [];
    const branch = new Set(visited).add(key);
    return data.vulnerabilities[key].via.flatMap(via => typeof via === 'string' ? roots(via, branch) : [via.url]);
  }
  const groups = {};
  for (const key of entries) for (const root of new Set(roots(key))) (groups[root] ||= []).push(key);
  const receipt = JSON.parse(fs.readFileSync(path.join(__dirname, `${name}.json`), 'utf8'));
  assert.equal(receipt.exit, entries.length ? 1 : 0);
  return { receipt: `${name}.json`, verdict: entries.length ? 'ADVISORIES_PRESENT' : 'NO_ADVISORIES_REPORTED', affectedPackageEntries: entries.length, affectedInstalledNodes: new Set(entries.flatMap(key => data.vulnerabilities[key].nodes)).size, severities: data.metadata.vulnerabilities, advisoryRoots: groups };
}
const baseline = JSON.parse(execFileSync('git', ['show', '672c5c011ce57dc41551f5fbc642bc4e69134c43:frontend/package-lock.json'], { cwd: repo }));
const candidate = JSON.parse(fs.readFileSync(path.join(repo, 'frontend/package-lock.json'), 'utf8'));
const existing = Object.keys(baseline.packages).filter(key => key !== '');
for (const key of existing) assert.deepEqual(candidate.packages[key], baseline.packages[key], key);
const production = existing.filter(key => !baseline.packages[key].dev);
assert.equal(production.length, 173);
assert.deepEqual(Object.keys(candidate.packages).filter(key => !(key in baseline.packages)), ['node_modules/validate-npm-package-name']);
assert.equal(candidate.packages['node_modules/validate-npm-package-name'].dev, true);
const list = name => JSON.parse(fs.readFileSync(path.join(__dirname, `${name}.stdout`), 'utf8').slice(fs.readFileSync(path.join(__dirname, `${name}.stdout`), 'utf8').indexOf('['))).sort();
const discovery = list('baseline-discovery');
assert.equal(discovery.length, 147);
assert.deepEqual(list('mac-final-discovery'), discovery);
const productFiles = execFileSync('git', ['diff', '--name-only', '672c5c011ce57dc41551f5fbc642bc4e69134c43', 'HEAD', '--', 'frontend'], { cwd: repo, encoding: 'utf8' }).trim().split('\n');
const sourceHashes = Object.fromEntries(productFiles.map(file => [file, hash(fs.readFileSync(path.join(repo, file)))]));
const payload = names.concat(fs.readdirSync(__dirname).filter(name => name.endsWith('.cjs'))).sort();
const archive = path.join(__dirname, 'raw-receipts.tar.gz');
assert.ok(!fs.existsSync(archive), 'Archive is append-only');
execFileSync('tar', ['-czf', archive, ...payload], { cwd: __dirname });
const summary = { generated_by: 'docs/admin/implementation/batch9-dependencies-evidence/build-evidence.cjs', generator_sha256: hash(fs.readFileSync(__filename)), generated_at: new Date().toISOString(), baseline_commit: '672c5c011ce57dc41551f5fbc642bc4e69134c43', product_commit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repo, encoding: 'utf8' }).trim(), source_sha256: sourceHashes, lockDelta: { unchangedExistingPackageRecords: existing.length, unchangedProductionRecords: production.length, added: ['node_modules/validate-npm-package-name'], modified: ['root devDependency declaration'] }, discovery: { identicalSuitePaths: discovery.length }, audits: Object.fromEntries(['baseline-full-audit', 'baseline-production-audit', 'final-mac-audit', 'final-mac-prod-audit', 'final-linux-audit', 'final-linux-prod-audit'].map(name => [name, audit(name)])), commands, rawArchive: { path: 'raw-receipts.tar.gz', sha256: hash(fs.readFileSync(archive)), entries: Object.fromEntries(payload.map(name => [name, hash(fs.readFileSync(path.join(__dirname, name)))])) } };
const output = path.join(__dirname, 'summary.json');
fs.writeFileSync(output, `${JSON.stringify(summary, null, 2)}\n`);
const readback = JSON.parse(fs.readFileSync(output, 'utf8'));
assert.equal(readback.generator_sha256, hash(fs.readFileSync(__filename)));
assert.equal(readback.rawArchive.sha256, hash(fs.readFileSync(archive)));
assert.equal(readback.lockDelta.unchangedProductionRecords, 173);
console.log(JSON.stringify({ recordedCommands: commands.length, archivedFiles: payload.length, archiveBytes: fs.statSync(archive).size, lockDelta: summary.lockDelta, auditCounts: Object.fromEntries(Object.entries(summary.audits).map(([name, data]) => [name, { entries: data.affectedPackageEntries, roots: Object.keys(data.advisoryRoots).length }])) }));
}
