'use strict';

// Append-only local command recorder. Never treats a nonzero exit as a pass.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const [name, cwd, command, ...args] = process.argv.slice(2);
if (!name || !cwd || !command || !/^[a-z0-9-]+$/.test(name)) throw new Error('name cwd command [args] required');
const output = path.join(__dirname, name);
if (fs.existsSync(`${output}.json`)) throw new Error('Receipt already exists; use a new name');
const repo = path.resolve(__dirname, '../../../..');
const { sourceIdentity } = require('./control_contract.cjs');
const before = sourceIdentity(__filename);
const started = new Date().toISOString();
const result = spawnSync(command, args, { cwd, encoding: 'utf8', timeout: 1200000, maxBuffer: 64 * 1024 * 1024 });
const after = sourceIdentity(__filename, false);
const changed = JSON.stringify(before) !== JSON.stringify(after);
const verificationExit = result.status === 0 && !result.error && result.signal === null && !changed ? 0 : 1;
fs.writeFileSync(`${output}.stdout`, result.stdout || '');
fs.writeFileSync(`${output}.stderr`, result.stderr || '');
const receipt = { generated_by: 'docs/admin/implementation/batch9-dependencies-evidence/run.cjs', generator_sha256: before.generator_sha256, generated_at: new Date().toISOString(), started_at: started, target_commit: before.head, target_tree: before.tree, source_sha256: before.source_sha256, source_before: before, source_after: after, source_changed: changed, command: [command, ...args], cwd, recorder_runtime: { node: process.version, platform: process.platform, arch: process.arch }, exit: result.status, verification_exit: verificationExit, signal: result.signal, error: result.error?.message || null, stdout_sha256: hash(result.stdout || ''), stderr_sha256: hash(result.stderr || ''), verdict: verificationExit === 0 ? 'COMMAND_SUCCEEDED' : 'COMMAND_FAILED' };
fs.writeFileSync(`${output}.json`, `${JSON.stringify(receipt, null, 2)}\n`);
const readback = JSON.parse(fs.readFileSync(`${output}.json`, 'utf8'));
if (readback.generator_sha256 !== hash(fs.readFileSync(__filename)) || readback.verdict !== receipt.verdict) throw new Error('Provenance readback failed');
console.log(JSON.stringify({ name, exit: result.status, signal: result.signal, error: result.error?.message, stdout: (result.stdout || '').slice(-1200), stderr: (result.stderr || '').slice(-1200) }));
process.exitCode = verificationExit;
