/** Real standalone render/proxy smoke; no browser, auth service or PostgreSQL. */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, rm } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setTimeout } from 'node:timers/promises';
import test from 'node:test';

test('standalone harness renders with inert auth and restricts its local transport', { timeout: 60000 }, async () => {
  const calls = [];
  const backend = createServer((req, res) => {
    calls.push({ method: req.method, path: req.url, headers: req.headers });
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end('[]');
  });
  backend.listen(0, '127.0.0.1');
  await once(backend, 'listening');
  const reservation = createServer();
  reservation.listen(0, '127.0.0.1');
  await once(reservation, 'listening');
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));
  const output = await mkdtemp(join(tmpdir(), 'b86-harness-smoke-'));
  const child = spawn(process.execPath, [new URL('./serve.mjs', import.meta.url).pathname], {
    env: { PATH: process.env.PATH, B86_GENERATION_BROWSER_OUTPUT: output,
      B86_GENERATION_FIXTURE_API: `http://127.0.0.1:${backend.address().port}`, B86_GENERATION_BROWSER_PORT: String(port) },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let logs = '';
  child.stdout.on('data', data => { logs += data; });
  child.stderr.on('data', data => { logs += data; });
  try {
    const origin = `http://127.0.0.1:${port}`;
    const deadline = Date.now() + 45000;
    let page;
    while (!page && Date.now() < deadline) {
      assert.equal(child.exitCode, null, logs);
      try { page = await fetch(origin, { signal: AbortSignal.timeout(1000) }); } catch { await setTimeout(100); }
    }
    assert.ok(page, logs);
    assert.equal(page.status, 200, logs);
    assert.match(await page.text(), /Owned local native report fixture/);
    const prefix = `${origin}/api/v1/admin/social`;
    const result = await fetch(`${prefix}/generation/capabilities`, { headers: { Authorization: 'Bearer inert-test', Cookie: 'inert-test' } });
    assert.equal(result.status, 200);
    assert.deepEqual(await result.json(), []);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].headers.authorization, undefined);
    assert.equal(calls[0].headers.cookie, undefined);
    for (const path of ['/generation/controls', '/media/uploads', '/posts/fixture/publish']) {
      assert.equal((await fetch(prefix + path, { method: 'POST', body: '{}' })).status, 403);
    }
    assert.equal(calls.length, 1, 'Forbidden commands reached the fixture API');
  } finally {
    if (child.exitCode === null && child.signalCode === null) {
      const exited = once(child, 'exit');
      child.kill('SIGTERM');
      await exited;
    }
    await new Promise(resolve => backend.close(resolve));
    await rm(output, { recursive: true, force: true });
  }
});
