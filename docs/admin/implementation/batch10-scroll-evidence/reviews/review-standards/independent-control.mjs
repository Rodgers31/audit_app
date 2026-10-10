import assert from 'node:assert/strict';
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { verifyPackage } from '/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app/docs/admin/implementation/batch10-scroll-evidence/verify.mjs';

const repo = '/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app';
const original = resolve(repo, 'docs/admin/implementation/batch10-scroll-evidence');
const valid = await verifyPackage(original, repo);
assert.equal(valid.archive_integrity, 'verified');
assert.equal(valid.issue_601, 'unresolved');
console.log('Positive control: archive integrity verified; issue unresolved');
for (const kind of ['zero-count-original-control', 'negative-role-relabel', 'wrong-precondition-report']) {
  const owned = mkdtempSync(resolve(tmpdir(), 'batch10-scroll-standards-control-'));
  try {
    cpSync(original, owned, { recursive: true });
    const manifestPath = resolve(owned, 'manifest.json');
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
    if (kind === 'zero-count-original-control') manifest.targets.find(t => t.name === 'original-linux-20').count = 0;
    if (kind === 'negative-role-relabel') manifest.targets.find(t => t.name === 'probe-native-absent-negative').role = 'positive-diagnostic';
    if (kind === 'wrong-precondition-report') manifest.targets.find(t => t.name === 'original-node22-linux-100').report = 'data/original-linux-20-report.json.gz';
    writeFileSync(manifestPath, JSON.stringify(manifest));
    await assert.rejects(verifyPackage(owned, repo), /Wrong targeted control identity/);
    console.log('Malformed control rejected: ' + kind);
  } finally {
    rmSync(owned, { recursive: true });
  }
}
