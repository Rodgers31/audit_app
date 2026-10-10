'use strict';

// Verify immutable author receipts against their archived generators, not today's source.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const packet = process.argv[2] && process.argv[2] !== '--verify-existing'
  ? path.resolve(process.argv[2]) : __dirname;
const summary = JSON.parse(fs.readFileSync(path.join(packet, 'summary.json')));
const archive = path.join(packet, 'raw-receipts.tar.gz');
assert.equal(hash(fs.readFileSync(archive)), summary.rawArchive.sha256, 'Historical archive hash differs');
const entries = summary.rawArchive.entries;
assert.equal(Object.keys(entries).length, 308, 'Historical manifest inventory differs');
const bytes = new Map();
for (const [name, expected] of Object.entries(entries)) {
  assert.ok(/^[a-zA-Z0-9_.-]+$/.test(name) && !name.startsWith('-'), 'Unsafe archive entry');
  const value = execFileSync('tar', ['-xOf', archive, name], { maxBuffer: 32 * 1024 * 1024 });
  assert.equal(hash(value), expected, name);
  bytes.set(name, value);
}
function generator(record) {
  assert.equal(typeof record.generated_by, 'string');
  const name = path.basename(record.generated_by);
  assert.ok(bytes.has(name) && name.endsWith('.cjs'), 'Historical generator is absent');
  assert.equal(hash(bytes.get(name)), record.generator_sha256, name);
}
generator(summary);
let commands = 0;
for (const [name, value] of bytes) {
  if (!name.endsWith('.json')) continue;
  const receipt = JSON.parse(value);
  generator(receipt);
  if (!receipt.recorder_runtime) continue;
  for (const stream of ['stdout', 'stderr']) {
    const sidecar = name.slice(0, -5) + '.' + stream;
    assert.ok(bytes.has(sidecar), sidecar);
    assert.equal(hash(bytes.get(sidecar)), receipt[stream + '_sha256'], sidecar);
  }
  assert.equal(receipt.verdict, receipt.exit === 0 ? 'COMMAND_SUCCEEDED' : 'COMMAND_FAILED');
  commands++;
}
assert.equal(commands, 96);
assert.equal(summary.lockDelta.unchangedProductionRecords, 173);
console.log(JSON.stringify({ scope: 'historical author packet only; repaired source is unverified by this packet',
  archive_sha256: summary.rawArchive.sha256, original_product_commit: summary.product_commit,
  archivedFiles: bytes.size, recordedCommands: commands, generator_sha256: hash(fs.readFileSync(__filename)) }));
