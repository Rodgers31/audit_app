/**
 * @jest-environment node
 *
 * The nightly's revalidation call and the route that answers it must agree on
 * which pages exist, and between them must cover every page whose HTML is
 * rendered from backend data (issue #231).
 *
 * Until #231 each side kept its own list. The workflow sent `/sectors`, which
 * is not a page, and the route put it in `rejected` with HTTP 200, so the job
 * passed. `/counties/compare` was allowed but never sent, and none of the 47
 * `/counties/[id]` pages was covered at all.
 *
 * This test does not compare two lists. It works out what the workflow step
 * would actually send, signs it, POSTs it to the real route handler, and
 * checks what the handler did with it.
 */
import { createHmac } from 'crypto';
import fs from 'fs';
import path from 'path';

const revalidatePath = jest.fn();
jest.mock('next/cache', () => ({ revalidatePath: (...args: unknown[]) => revalidatePath(...args) }));

// Imported after the mock so the route binds to it.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { POST } = require('@/app/api/revalidate/route');
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { NextRequest } = require('next/server');

const FRONTEND = path.resolve(__dirname, '..', '..');
const REPO = path.resolve(FRONTEND, '..');
const WORKFLOW = path.join(REPO, '.github', 'workflows', 'seed.yml');
const SECRET = 'test-only-revalidate-secret';

/**
 * The paths the workflow's revalidation step sends. It reads the step's own
 * text instead of keeping a copy here, and it fails closed: if the step builds
 * its body some way this function does not recognise, the test fails and
 * does not guess.
 */
function workflowPaths(): string[] {
  const yml = fs.readFileSync(WORKFLOW, 'utf8');
  const at = yml.indexOf('-X POST "$REVALIDATE_URL"');
  if (at < 0) throw new Error('seed.yml no longer calls the revalidation webhook');
  // The BODY assignment is the last one before the request to the webhook.
  const before = yml.slice(0, at);
  const literal = [...before.matchAll(/BODY='(\{"paths".*?\})'/g)].pop();
  const fromFile = [...before.matchAll(/BODY=\$\(jq -c '\{paths: \.paths\}' (\S+?)\)/g)].pop();
  const lastLiteral = literal?.index ?? -1;
  const lastFile = fromFile?.index ?? -1;
  if (lastFile > lastLiteral && fromFile) {
    const manifest = JSON.parse(fs.readFileSync(path.join(REPO, fromFile[1]), 'utf8'));
    return manifest.paths;
  }
  if (literal) return JSON.parse(literal[1]).paths;
  throw new Error('cannot tell what paths the revalidation step sends');
}

/**
 * Every route whose HTML is server-rendered from backend data: a page.tsx
 * that is not a client component and prefetches or imports an API module.
 * Such pages change only when revalidated or redeployed, so each of them
 * has to be revalidated.
 */
function serverDataRoutes(): string[] {
  const appDir = path.join(FRONTEND, 'app');
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'api') continue;
        walk(full);
      } else if (entry.name === 'page.tsx') {
        const src = fs.readFileSync(full, 'utf8');
        if (/^\s*['"]use client['"]/m.test(src.split('\n').slice(0, 12).join('\n'))) continue;
        if (!/prefetchQuery|fetchQuery|from '@\/lib\/api/.test(src)) continue;
        const rel = path.relative(appDir, path.dirname(full)).split(path.sep).join('/');
        out.push(rel ? `/${rel}` : '/');
      }
    }
  };
  walk(appDir);
  return out.sort();
}

async function postSigned(body: string) {
  const sig = createHmac('sha256', SECRET).update(body).digest('hex');
  const req = new NextRequest('http://localhost/api/revalidate', {
    method: 'POST',
    body,
    headers: { 'content-type': 'application/json', 'x-revalidate-signature': sig },
  });
  const res = await POST(req);
  return { status: res.status as number, json: await res.json() };
}

describe('revalidation paths: workflow and route agree (#231)', () => {
  const OLD_ENV = process.env.REVALIDATE_SECRET;
  beforeEach(() => {
    process.env.REVALIDATE_SECRET = SECRET;
    revalidatePath.mockClear();
  });
  afterAll(() => {
    process.env.REVALIDATE_SECRET = OLD_ENV;
  });

  it('the route accepts every path the workflow sends, and rejects none', async () => {
    const sent = workflowPaths();
    const { status, json } = await postSigned(JSON.stringify({ paths: sent }));
    expect(status).toBe(200);
    expect(json.rejected).toEqual([]);
    expect([...json.revalidated].sort()).toEqual([...sent].sort());
  });

  it('the workflow covers every server-rendered data page, including /counties/[id]', () => {
    const sent = new Set(workflowPaths());
    const routes = serverDataRoutes();
    // Guard the guard: if the scan finds nothing, it is broken, and an empty
    // list would pass any coverage check.
    expect(routes).toEqual(expect.arrayContaining(['/', '/counties/[id]', '/debt']));
    expect(routes.filter((r) => !sent.has(r))).toEqual([]);
  });

  it('revalidates a dynamic route as a page pattern, so all 47 counties refresh', async () => {
    await postSigned(JSON.stringify({ paths: workflowPaths() }));
    expect(revalidatePath).toHaveBeenCalledWith('/counties/[id]', 'page');
    // Static paths go through without a type.
    expect(revalidatePath).toHaveBeenCalledWith('/debt');
  });

  it('still rejects a path that is not in the manifest', async () => {
    const { status, json } = await postSigned(JSON.stringify({ paths: ['/sectors', '/'] }));
    expect(status).toBe(200);
    expect(json.rejected).toEqual(['/sectors']);
    expect(json.revalidated).toEqual(['/']);
  });

  it('refuses a body signed with the wrong secret', async () => {
    const body = JSON.stringify({ paths: ['/'] });
    const req = new NextRequest('http://localhost/api/revalidate', {
      method: 'POST',
      body,
      headers: { 'x-revalidate-signature': createHmac('sha256', 'wrong').update(body).digest('hex') },
    });
    const res = await POST(req);
    expect(res.status).toBe(401);
    expect(revalidatePath).not.toHaveBeenCalled();
  });
});
