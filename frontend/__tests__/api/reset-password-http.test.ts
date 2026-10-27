/** @jest-environment node */
import http from 'http';
import { POST } from '@/app/api/auth/reset-password/route';
const mockStore = { get: jest.fn(), getAll: jest.fn() };
jest.mock('next/headers', () => ({ cookies: async () => mockStore }));
let server: http.Server;
let base: string;
let requests: {
  method: string;
  path: string;
  body: Record<string, unknown>;
}[];
let updateFails = false;
let stall = false;
const fixtureUser = { id: '00000000-0000-4000-8000-000000000001', email: 'fixture@example.invalid', aud: 'authenticated', role: 'authenticated', app_metadata: {}, user_metadata: {}, created_at: '2026-01-01T00:00:00Z' };
beforeAll(async () => {
  server = http.createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', c => chunks.push(c));
    req.on('end', () => {
      const body = JSON.parse(Buffer.concat(chunks).toString() || '{}');
      requests.push({ method: req.method!, path: req.url!, body });
      if (stall)
        return;
      res.setHeader('content-type', 'application/json');
      if (req.url?.startsWith('/auth/v1/token')) {
        if (body.auth_code !== 'INERT_CODE' || body.code_verifier !== 'INERT_VERIFIER') {
          res.writeHead(400);
          res.end(JSON.stringify({ error: 'invalid_grant', msg: 'Invalid PKCE verifier' }));
          return;
        }
        const jwt = [Buffer.from('{}').toString('base64url'), Buffer.from(JSON.stringify({ sub: fixtureUser.id, exp: Math.floor(Date.now() / 1000) + 3600 })).toString('base64url'), 'INERT_SIGNATURE'].join('.');
        res.end(JSON.stringify({ access_token: jwt, refresh_token: 'INERT_REFRESH', expires_in: 3600, token_type: 'bearer', user: fixtureUser }));
      }
      else if (req.method === 'PUT') {
        res.writeHead(updateFails ? 400 : 200);
        res.end(JSON.stringify(updateFails ? { msg: 'INERT_ERROR', code: 'same_password' } : fixtureUser));
      }
      else if (req.url?.startsWith('/auth/v1/logout')) {
        res.writeHead(204);
        res.end();
      }
      else {
        res.writeHead(404);
        res.end('{}');
      }
    });
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${(server.address() as import('net').AddressInfo).port}`;
});
afterAll(async () => {
  server.closeAllConnections();
  await new Promise<void>(resolve => server.close(() => resolve()));
});
beforeEach(() => {
  requests = [];
  updateFails = false;
  stall = false;
  process.env.NEXT_PUBLIC_SUPABASE_URL = base;
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'INERT_ANON';
  mockStore.get.mockReturnValue({ value: 'INERT_CODE' });
  mockStore.getAll.mockReturnValue([{ name: 'auditgava-recovery', value: 'INERT_CODE' }, { name: 'sb-127-auth-token-code-verifier', value: 'INERT_VERIFIER/PASSWORD_RECOVERY' }, { name: 'sb-127-auth-token', value: 'INERT_STALE_SESSION' }]);
});
function request(signal?: AbortSignal) {
  return new Request('https://app.test/api/auth/reset-password', { method: 'POST', headers: { origin: 'https://app.test', 'content-type': 'application/json' }, body: JSON.stringify({ password: 'InertPass123!' }), signal });
}
test('actual SSR client exchanges PKCE and updates once over owned HTTP', async () => {
  const res = await POST(request());
  expect(res.status).toBe(200);
  expect(requests.map(r => [r.method, r.path])).toEqual([['POST', '/auth/v1/token?grant_type=pkce'], ['PUT', '/auth/v1/user']]);
  expect(requests[0].body.code_verifier).toBe('INERT_VERIFIER');
  expect(requests[1].body.password).toBe('InertPass123!');
  expect(res.cookies.get('sb-127-auth-token')?.value).toBeTruthy();
  expect(res.cookies.get('sb-127-auth-token-code-verifier')?.maxAge).toBe(0);
  expect(res.cookies.get('auditgava-recovery')?.maxAge).toBe(0);
});
test('forged PKCE verifier produces no update or fresh session', async () => {
  mockStore.getAll.mockReturnValue([{ name: 'sb-127-auth-token-code-verifier', value: 'FORGED' }]);
  const res = await POST(request());
  expect(res.status).toBe(400);
  expect(requests).toHaveLength(1);
  expect(res.cookies.get('sb-127-auth-token')).toBeUndefined();
});
test('actual update failure signs out and withholds exchanged session', async () => {
  const errors = jest.spyOn(console, 'error').mockImplementation(() => {
  });
  updateFails = true;
  const res = await POST(request());
  expect(res.status).toBe(400);
  expect(requests.map(r => r.method)).toEqual(['POST', 'PUT', 'POST']);
  expect(requests[2].path).toContain('/auth/v1/logout');
  expect(res.cookies.get('sb-127-auth-token')?.value ?? '').toBe('');
  expect(JSON.stringify(await res.json())).not.toContain('INERT_ERROR');
  expect(errors).not.toHaveBeenCalled();
  errors.mockRestore();
});
test('caller abort cancels actual stalled provider HTTP before update', async () => {
  stall = true;
  const abort = new AbortController();
  const result = POST(request(abort.signal));
  for (let i = 0; i < 100 && requests.length === 0; i++)
    await new Promise(resolve => setTimeout(resolve, 5));
  expect(requests).toHaveLength(1);
  abort.abort();
  expect((await result).status).toBe(408);
  expect(requests).toHaveLength(1);
  server.closeAllConnections();
  await new Promise(resolve => setTimeout(resolve, 20));
});
test('whole request deadline aborts actual stalled provider HTTP', async () => {
  stall = true;
  const started = Date.now();
  const result = await POST(request());
  expect(result.status).toBe(504);
  expect(Date.now() - started).toBeGreaterThanOrEqual(14900);
  expect(Date.now() - started).toBeLessThan(17500);
  expect(requests).toHaveLength(1);
  expect(requests[0].method).toBe('POST');
  expect(result.cookies.get('auditgava-recovery')?.maxAge).toBe(0);
  server.closeAllConnections();
  await new Promise(resolve => setTimeout(resolve, 20));
}, 20000);
