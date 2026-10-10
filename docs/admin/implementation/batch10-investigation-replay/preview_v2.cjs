'use strict';

// Current replay only. The historical preview.cjs and its receipts stay unchanged.
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { existsSync, lstatSync, mkdirSync, realpathSync, readdirSync } = require('node:fs');
const path = require('node:path');
const net = require('node:net');

async function main() {
  assert.ok(process.argv.length >= 6, 'FRONTEND PORT EXTERNAL_SCRATCH ABSOLUTE_NPM [browser] required');
  const root = realpathSync(process.argv[2]);
  const port = Number(process.argv[3]);
  const scratch = realpathSync(process.argv[4]);
  const npm = realpathSync(process.argv[5]);
  const mode = process.argv[6];
  assert.ok(mode === undefined || mode === 'browser', 'unknown preview mode');
  assert.ok(Number.isSafeInteger(port) && port > 1024 && port < 65536);
  assert.ok(lstatSync(root).isDirectory() && lstatSync(scratch).isDirectory());
  assert.ok(!lstatSync(process.argv[4]).isSymbolicLink(), 'scratch symlink refused');
  const repository = path.basename(root) === 'frontend' ? path.dirname(root) : root;
  const outside = path.relative(repository, scratch);
  assert.ok(outside.startsWith('..' + path.sep) || path.isAbsolute(outside), 'external scratch required');
  const inverse = path.relative(scratch, repository);
  assert.ok(inverse.startsWith('..' + path.sep) || path.isAbsolute(inverse), 'scratch cannot contain checkout');
  assert.ok(path.isAbsolute(process.argv[5]) && lstatSync(npm).isFile(), 'absolute npm executable required');
  for (const directory of new Set([repository, root])) {
    assert.ok(!readdirSync(directory).some(name => name.startsWith('.env') &&
      !['.example', '.sample', '.template'].some(suffix => name.endsWith(suffix))), 'dotenv input refused');
  }
  const runtime = path.join(scratch, 'preview-runtime');
  assert.ok(!existsSync(runtime), 'inherited runtime output refused');
  mkdirSync(runtime);
  mkdirSync(path.join(runtime, 'home'));
  mkdirSync(path.join(runtime, 'tmp'));
  const env = {
    PATH: [path.dirname(process.execPath), path.dirname(npm), '/usr/bin', '/bin'].join(path.delimiter),
    HOME: path.join(runtime, 'home'), TMPDIR: path.join(runtime, 'tmp'), LANG: 'C.UTF-8',
    NEXT_PUBLIC_API_URL: 'http://127.0.0.1:18014', INTERNAL_API_URL: 'http://127.0.0.1:18014',
    NEXT_PUBLIC_SUPABASE_URL: 'http://127.0.0.1:18014', NEXT_PUBLIC_SUPABASE_ANON_KEY: 'batch10-current-replay-inert-anon-key',
    NEXT_TELEMETRY_DISABLED: '1', PYTHON_DOTENV_DISABLED: '1', ONNXRUNTIME_NODE_INSTALL: 'skip',
    npm_config_cache: path.join(runtime, 'npm-cache'), npm_config_engine_strict: 'true',
    npm_config_userconfig: process.platform === 'win32' ? 'NUL' : '/dev/null',
    npm_config_globalconfig: process.platform === 'win32' ? 'NUL' : '/dev/null',
    NATIVE_VERIFY_CACHE_DIR: path.join(runtime, 'model-cache'),
  };
  console.log(JSON.stringify({ check: 'current-preview-environment', resolved_environment: env,
    runtime: { node: process.version, platform: process.platform, architecture: process.arch },
    classification: 'CURRENT_PREVIEW_CAPTURE', current_checkout_acceptance: false }));
  const reservation = net.createServer();
  await new Promise((resolve, reject) => {
    reservation.once('error', reject);
    reservation.listen(port, '127.0.0.1', resolve);
  });
  await new Promise(resolve => reservation.close(resolve));
  const child = spawn(npm, ['run', 'start', '--', '-H', '127.0.0.1', '-p', String(port)],
    { cwd: root, env, detached: true, stdio: ['ignore', 'pipe', 'pipe'] });
  let log = '', spawnError;
  child.on('error', error => { spawnError = error; });
  child.stdout.on('data', data => { log += data; });
  child.stderr.on('data', data => { log += data; });
  const closed = new Promise(resolve => child.once('close', resolve));
  const base = `http://127.0.0.1:${port}`;
  try {
    let response;
    for (let i = 0; i < 100; i++) {
      if (spawnError) throw spawnError;
      if (child.exitCode !== null) throw new Error(log || 'preview child exited before readiness');
      try { response = await fetch(base + '/learn', { signal: AbortSignal.timeout(1000), redirect: 'error' }); break; }
      catch { await new Promise(resolve => setTimeout(resolve, 100)); }
    }
    assert.ok(response, 'preview did not start');
    assert.equal(response.status, 200);
    const html = await response.text();
    const assets = [...html.matchAll(/href="([^\"]+\.css[^\"]*)"/g)].map(match => match[1].replace(/&amp;/g, '&'));
    assert.ok(assets.length > 0);
    for (const asset of assets) {
      const url = new URL(asset, base);
      assert.equal(url.origin, base, 'preview asset must remain on owned loopback origin');
      const result = await fetch(url, { signal: AbortSignal.timeout(1000), redirect: 'error' });
      assert.equal(result.status, 200);
      assert.match(result.headers.get('content-type'), /text\/css/);
      assert.ok((await result.text()).length > 1000);
    }
    console.log(JSON.stringify({ check: 'current-preview-css', base, learnStatus: 200, assets }));
    if (mode === 'browser') {
      const browserChild = spawn(npm, ['run', 'verify:dependency-browser'], {
        cwd: root, env: { ...env, DEPENDENCY_PREVIEW_URL: base }, detached: true, stdio: 'inherit',
      });
      let timedOut = false;
      const timeout = setTimeout(() => { timedOut = true; try { process.kill(-browserChild.pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; } }, 180000);
      const [code, signal] = await new Promise((resolve, reject) => {
        browserChild.once('error', reject);
        browserChild.once('close', (code, signal) => resolve([code, signal]));
      }).finally(() => clearTimeout(timeout));
      assert.equal(timedOut, false, 'browser child timed out');
      assert.equal(signal, null);
      assert.equal(code, 0);
    }
  } finally {
    if (child.pid) {
      try { process.kill(-child.pid, 'SIGTERM'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
    }
    const escalation = setTimeout(() => {
      if (child.pid) { try { process.kill(-child.pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; } }
    }, 10000);
    await closed.finally(() => clearTimeout(escalation));
    await assert.rejects(fetch(base + '/learn', { signal: AbortSignal.timeout(1000) }));
    console.log(JSON.stringify({ check: 'preview-owned-cleanup', port, listenerAbsent: true, log }));
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
