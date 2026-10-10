'use strict';

const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const path = require('node:path');
const net = require('node:net');

async function main() {
  const root = path.resolve(process.argv[2]);
  const port = Number(process.argv[3]);
  assert.ok(Number.isSafeInteger(port) && port > 1024 && port < 65536);
  const reservation = net.createServer();
  await new Promise((resolve, reject) => {
    reservation.once('error', reject);
    reservation.listen(port, '127.0.0.1', resolve);
  });
  await new Promise(resolve => reservation.close(resolve));
  const child = spawn('npm', ['run', 'start', '--', '-H', '127.0.0.1', '-p', String(port)],
    { cwd: root, env: process.env, detached: true, stdio: ['ignore', 'pipe', 'pipe'] });
  let log = '';
  child.stdout.on('data', data => { log += data; });
  child.stderr.on('data', data => { log += data; });
  const closed = new Promise(resolve => child.once('close', resolve));
  const base = `http://127.0.0.1:${port}`;
  try {
    let response;
    for (let i = 0; i < 100; i++) {
      if (child.exitCode !== null) throw new Error(log);
      try { response = await fetch(base + '/learn', { signal: AbortSignal.timeout(1000) }); break; }
      catch { await new Promise(resolve => setTimeout(resolve, 100)); }
    }
    assert.ok(response, 'Preview did not start');
    assert.equal(response.status, 200);
    const html = await response.text();
    const assets = [...html.matchAll(/href="([^\"]+\.css[^\"]*)"/g)].map(match => match[1].replace(/&amp;/g, '&'));
    assert.ok(assets.length > 0);
    for (const asset of assets) {
      const result = await fetch(new URL(asset, base));
      assert.equal(result.status, 200);
      assert.match(result.headers.get('content-type'), /text\/css/);
      assert.ok((await result.text()).length > 1000);
    }
    console.log(JSON.stringify({ check: 'actual-production-preview-css', base, learnStatus: 200, assets }));
    if (process.argv[4] === 'browser') {
      const browserChild = spawn('npm', ['run', 'verify:dependency-browser'], {
        cwd: root, env: { ...process.env, DEPENDENCY_PREVIEW_URL: base }, stdio: 'inherit',
      });
      const timeout = setTimeout(() => browserChild.kill('SIGTERM'), 180000);
      const [code, signal] = await new Promise(resolve => browserChild.once('close', (code, signal) => resolve([code, signal])));
      clearTimeout(timeout);
      assert.equal(signal, null);
      assert.equal(code, 0);
    }
  } finally {
    try { process.kill(-child.pid, 'SIGTERM'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
    await Promise.race([closed, new Promise((_, reject) => setTimeout(() => reject(new Error('Preview cleanup deadline exceeded')), 10000).unref())]);
    await assert.rejects(fetch(base + '/learn', { signal: AbortSignal.timeout(1000) }));
    console.log(JSON.stringify({ check: 'preview-owned-cleanup', port, listenerAbsent: true, log }));
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
