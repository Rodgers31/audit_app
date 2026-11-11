'use strict';

const { AsyncLocalStorage } = require('node:async_hooks');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const https = require('node:https');
const { createRequire } = require('node:module');
const path = require('node:path');
const { Readable } = require('node:stream');

const [frontend, cache, certPath, keyPath] = process.argv.slice(2);
if (process.argv.length !== 6 || ![frontend, cache, certPath, keyPath].every(path.isAbsolute) ||
    !process.env.REVALIDATE_SECRET || !/^[a-f0-9]{40}$/.test(process.env.VERCEL_GIT_COMMIT_SHA || '')) {
  process.stderr.write('REFUSED invalid fixture inputs\n');
  process.exit(1);
}

globalThis.AsyncLocalStorage = AsyncLocalStorage;
const requireCached = createRequire(path.join(cache, 'package.json'));
const ts = requireCached('typescript');
const { NextRequest } = requireCached('next/server');
const { workAsyncStorage } = requireCached('next/dist/server/app-render/work-async-storage.external');

const sources = new Map();
function loadSource(file) {
  if (sources.has(file)) return sources.get(file).exports;
  const result = ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    esModuleInterop: true,
  }});
  const local = {exports: {}};
  function fixtureRequire(name) {
    if (name.startsWith('@/')) {
      return loadSource(path.join(frontend, name.slice(2) + '.ts'));
    }
    if (name === './paths.json') {
      return JSON.parse(fs.readFileSync(path.join(path.dirname(file), name), 'utf8'));
    }
    if (['crypto', 'next/server', 'next/cache'].includes(name)) return requireCached(name);
    throw new Error('Unsupported route dependency');
  }
  new Function('require', 'module', 'exports', result.outputText)(fixtureRequire, local, local.exports);
  sources.set(file, local);
  return local.exports;
}

const route = '/api/revalidate';
const { POST } = loadSource(path.join(frontend, 'app/api/revalidate/route.ts'));
const manifest = fs.readFileSync(path.join(frontend, 'lib/revalidation/paths.json'));
const manifestSha256 = createHash('sha256').update(manifest).digest('hex');
let origin;
const server = https.createServer({key: fs.readFileSync(keyPath), cert: fs.readFileSync(certPath)}, async (input, output) => {
  if (input.method !== 'POST' || input.url !== route) {
    output.writeHead(404).end();
    return;
  }
  try {
    const request = new NextRequest(origin + route, {
      method: 'POST',
      headers: input.headers,
      body: Readable.toWeb(input),
      duplex: 'half',
    });
    const work = {route, incrementalCache: {}};
    const response = await workAsyncStorage.run(work, () => POST(request));
    const body = Buffer.from(await response.arrayBuffer());
    output.writeHead(response.status, Object.fromEntries(response.headers)).end(body);
    if (response.ok) {
      process.stdout.write('CACHE ' + JSON.stringify({tags: work.pendingRevalidatedTags || [],
        pathWasRevalidated: work.pathWasRevalidated === true}) + '\n');
    }
  } catch {
    output.writeHead(500).end();
    process.stderr.write('REFUSED loopback route exception\n');
  }
});
server.on('error', () => { process.stderr.write('REFUSED loopback listener error\n'); process.exitCode = 1; });
server.listen(0, '127.0.0.1', () => {
  origin = 'https://127.0.0.1:' + server.address().port;
  process.stdout.write('READY ' + JSON.stringify({url: origin + route,
    pid: process.pid, commit: process.env.VERCEL_GIT_COMMIT_SHA, manifest_sha256: manifestSha256}) + '\n');
});
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, () => {
    server.close();
    server.closeAllConnections();
  });
}
