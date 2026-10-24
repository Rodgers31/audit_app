/** @jest-environment node */
import { execFileSync, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import ts from 'typescript';

const source = resolve(__dirname, '../..');
const producer = resolve(source, 'browser-fixtures/admin-working-paint/prepare.mjs');
const hash = (bytes: Buffer) => createHash('sha256').update(bytes).digest('hex');
let owned: string;
beforeEach(() => { owned = mkdtempSync(join(tmpdir(), 'b67-paint-producer-')); });
afterEach(() => { rmSync(owned, { recursive: true, force: true }); });

function prepare(variant?: 'frozen') {
  const output = join(owned, 'fixture');
  execFileSync(process.execPath, [producer, output, ...(variant ? [variant] : [])], { cwd: source });
  const config = JSON.parse(readFileSync(join(output, 'tsconfig.json'), 'utf8'));
  const parsed = ts.parseJsonConfigFileContent(config, ts.sys, output);
  expect(parsed.errors).toEqual([]);
  return { output, config, options: parsed.options };
}

function diagnostics(api: string, options: ts.CompilerOptions) {
  // No ambient @types may silently supply the libraries the producer omitted.
  // Exercise the actual generated API module before Next normalizes tsconfig.
  const program = ts.createProgram([api], { ...options, types: [], noEmit: true, skipLibCheck: true });
  return ts.getPreEmitDiagnostics(program).map(item => ({
    code: item.code, message: ts.flattenDiagnosticMessageText(item.messageText, '\n'),
  }));
}

test.each([undefined, 'frozen'] as const)('fresh %s producer supplies modern Object and DOM types without Next rewriting config', variant => {
  const { output, config, options } = prepare(variant);
  const api = join(output, 'fixture/api.ts');
  expect(diagnostics(api, options)).toEqual([]);
  // Prove the compiler sees the intended missing-lib failure, rather than a
  // vacuous success, syntax/setup failure or silently skipped input module.
  const oldLibrary = diagnostics(api, { ...options, lib: ['lib.dom.d.ts', 'lib.es2017.d.ts'] });
  expect(oldLibrary.some(item => item.message.includes("'fromEntries'"))).toBe(true);
  expect(oldLibrary.some(item => item.message.includes("'hasOwn'"))).toBe(true);
  expect(config.compilerOptions.target).toBe('es2017');
  expect(config.compilerOptions.jsx).toBe('preserve');

  const receipt = JSON.parse(readFileSync(join(output, 'fixture-source.json'), 'utf8'));
  expect(receipt.producer['prepare.mjs']).toBe(hash(readFileSync(producer)));
  for (const path of ['app/admin/page.tsx', 'app/admin/etl/page.tsx']) {
    const selected = variant === 'frozen'
      ? execFileSync('git', ['show', `${receipt.frozenBase}:frontend/${path}`], { cwd: source })
      : readFileSync(resolve(source, path));
    expect(receipt.files[path]).toBe(hash(selected));
  }
  expect(receipt.runtime.node).toBe(process.version);
  expect(receipt.runtime.next).toBe(JSON.parse(readFileSync(resolve(source, 'node_modules/next/package.json'), 'utf8')).version);
});

test('producer refuses an existing destination without replacing retained contents', () => {
  const { output } = prepare();
  const marker = join(output, 'custody-marker.txt');
  writeFileSync(marker, 'owned fixture marker');
  const result = spawnSync(process.execPath, [producer, output], { cwd: source, encoding: 'utf8' });
  expect(result.status).not.toBe(0);
  expect(result.stderr).toContain('EEXIST');
  expect(readFileSync(marker, 'utf8')).toBe('owned fixture marker');
});
