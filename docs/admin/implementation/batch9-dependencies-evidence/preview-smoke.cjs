'use strict';

const assert = require('node:assert/strict');
const net = require('node:net');
const path = require('node:path');
const { spawn } = require('node:child_process');

async function main() {
  const root = path.resolve(__dirname, '../../../../frontend');
  const reservation = net.createServer();
  await new Promise(resolve => reservation.listen(0, '127.0.0.1', resolve));
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));
  const child = spawn('npm', ['run', 'start', '--', '-H', '127.0.0.1', '-p', String(port)], {
    cwd: root, detached: true,
    env: { ...process.env, NEXT_TELEMETRY_DISABLED: '1', NEXT_PUBLIC_API_URL: 'http://127.0.0.1:43994' },
  });
  let log = '';
  child.stdout.on('data', data => { log += data; });
  child.stderr.on('data', data => { log += data; });
  const closed = new Promise(resolve => child.once('close', resolve));
  try {
    const base = `http://127.0.0.1:${port}`;
    let response;
    for (let attempt = 0; attempt < 100; attempt++) {
      if (child.exitCode !== null) throw new Error(`Preview exited: ${log}`);
      try { response = await fetch(`${base}/learn`, { signal: AbortSignal.timeout(2000) }); break; } catch {
        await new Promise(resolve => setTimeout(resolve, 100));
      }
    }
    assert.ok(response, `Preview failed to start: ${log}`);
    assert.equal(response.status, 200);
    const html = await response.text();
    const css = html.match(/href="([^\"]+\.css[^\"]*)"/);
    assert.ok(css, 'Learn page must include built CSS');
    const asset = await fetch(new URL(css[1].replace(/&amp;/g, '&'), base));
    assert.equal(asset.status, 200);
    assert.match(asset.headers.get('content-type'), /text\/css/);
    assert.ok((await asset.text()).length > 1000);
    console.log(JSON.stringify({ check: 'owned-preview', port, learnStatus: response.status, cssStatus: asset.status }));
  } finally {
    try { process.kill(-child.pid, 'SIGTERM'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
    await closed;
    await assert.rejects(fetch(`http://127.0.0.1:${port}/learn`, { signal: AbortSignal.timeout(1000) }));
    console.log(JSON.stringify({ check: 'preview-cleanup', port, listenerAbsent: true }));
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
