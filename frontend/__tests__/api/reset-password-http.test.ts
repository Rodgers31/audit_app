/** @jest-environment node */
import http from 'http';
import { POST } from '@/app/api/auth/reset-password/route';
import { GET } from '@/app/auth/callback/route';
const mockStore = { get: jest.fn(), getAll: jest.fn() };
jest.mock('next/headers', () => ({ cookies: async () => mockStore }));
let server: http.Server;
let base: string;
let requests: {
  method: string;
  path: string;
  body: Record<string, unknown>;
  principal?: string;
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
      let principal: string | undefined;
      if (req.headers.authorization?.startsWith('Bearer ')) {
        try { principal = JSON.parse(Buffer.from(req.headers.authorization.slice(7).split('.')[1], 'base64url').toString()).sub; } catch { /* inert invalid fixture token */ }
      }
      requests.push({ method: req.method!, path: req.url!, body, principal });
      if (stall)
        return;
      res.setHeader('content-type', 'application/json');
      if (req.url?.startsWith('/auth/v1/token')) {
        const pairs: Record<string, string> = { INERT_CODE: 'INERT_VERIFIER', INERT_ACCOUNT_A: 'INERT_VERIFIER_A', INERT_ACCOUNT_B: 'INERT_VERIFIER_B' };
        if (typeof body.auth_code !== 'string' || !pairs[body.auth_code] || body.code_verifier !== pairs[body.auth_code]) {
          res.writeHead(400);
          res.end(JSON.stringify({ error: 'invalid_grant', msg: 'Invalid PKCE verifier' }));
          return;
        }
        const user = { ...fixtureUser, id: body.auth_code === 'INERT_ACCOUNT_B' ? '00000000-0000-4000-8000-000000000002' : fixtureUser.id };
        const jwt = [Buffer.from('{}').toString('base64url'), Buffer.from(JSON.stringify({ sub: user.id, exp: Math.floor(Date.now() / 1000) + 3600 })).toString('base64url'), 'INERT_SIGNATURE'].join('.');
        res.end(JSON.stringify({ access_token: jwt, refresh_token: 'INERT_REFRESH', expires_in: 3600, token_type: 'bearer', user }));
      }
      else if (req.method === 'PUT') {
        res.writeHead(updateFails ? 400 : 200);
        res.end(JSON.stringify(updateFails ? { msg: 'INERT_ERROR', code: 'same_password' } : { ...fixtureUser, id: principal }));
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
  mockStore.get.mockReturnValue({ value: staged('INERT_CODE', 'INERT_VERIFIER/PASSWORD_RECOVERY') });
  mockStore.getAll.mockReturnValue([{ name: 'auditgava-recovery', value: 'INERT_CODE' }, { name: 'sb-127-auth-token-code-verifier', value: 'INERT_VERIFIER/PASSWORD_RECOVERY' }, { name: 'sb-127-auth-token', value: 'INERT_STALE_SESSION' }]);
});
function staged(code: string, verifier: string) {
  return JSON.stringify({ version: 1, flow: 'a'.repeat(32), code, expiresAt: Date.now() + 300000, verifier: [{ name: 'sb-127-auth-token-code-verifier', value: verifier }] });
}
function request(signal?: AbortSignal, flow = 'a'.repeat(32), password = 'InertPass123!') {
  return new Request('https://app.test/api/auth/reset-password', { method: 'POST', headers: { origin: 'https://app.test', 'content-type': 'application/json' }, body: JSON.stringify({ flow, password }), signal });
}
test('actual SSR client exchanges PKCE and updates once over owned HTTP', async () => {
  const res = await POST(request());
  expect(res.status).toBe(200);
  expect(requests.map(r => [r.method, r.path])).toEqual([['POST', '/auth/v1/token?grant_type=pkce'], ['PUT', '/auth/v1/user']]);
  expect(requests[0].body.code_verifier).toBe('INERT_VERIFIER');
  expect(requests[1].body.password).toBe('InertPass123!');
  expect(res.cookies.get('sb-127-auth-token')?.value).toBeTruthy();
  expect(res.cookies.get('sb-127-auth-token-code-verifier')).toBeUndefined();
  expect(res.cookies.get('auditgava-recovery')).toBeUndefined();
});
test('forged PKCE verifier produces no update or fresh session', async () => {
  mockStore.get.mockReturnValue({ value: staged('INERT_CODE', 'FORGED') });
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
  expect(res.cookies.getAll()).toHaveLength(0);
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
  expect(result.cookies.get('auditgava-recovery')).toBeUndefined();
  server.closeAllConnections();
  await new Promise(resolve => setTimeout(resolve, 20));
}, 20000);

test('two account callbacks cannot send the older form password to the newer account', async () => {
  const verifierName = 'sb-127-auth-token-code-verifier';
  async function callback(code: string, verifier: string) {
    mockStore.getAll.mockReturnValue([{ name: verifierName, value: verifier + '/PASSWORD_RECOVERY' }]);
    return GET(new Request('https://app.test/auth/callback?' + new URLSearchParams({ code, next: '/reset-password' })));
  }
  const a = await callback('INERT_ACCOUNT_A', 'INERT_VERIFIER_A');
  const b = await callback('INERT_ACCOUNT_B', 'INERT_VERIFIER_B');
  const flow = (r: Awaited<ReturnType<typeof GET>>) => new URLSearchParams(new URL(r.headers.get('location')!).hash.slice(1)).get('recovery-flow')!;
  mockStore.get.mockReturnValue({ value: b.cookies.get('auditgava-recovery')!.value });
  mockStore.getAll.mockReturnValue([{ name: verifierName, value: 'INERT_VERIFIER_B/PASSWORD_RECOVERY' }]);
  const stale = await POST(request(undefined, flow(a), 'InertAPass123!'));
  expect(requests.filter(r => r.method === 'PUT').map(r => ({ principal: r.principal, password: r.body.password }))).toEqual([]);
  expect(stale.status).toBe(409);
  expect(requests).toHaveLength(0);
  expect(stale.cookies.getAll()).toHaveLength(0);
  mockStore.getAll.mockReturnValue([{ name: verifierName, value: 'INERT_VERIFIER_C/PASSWORD_RECOVERY' }]);
  const current = await POST(request(undefined, flow(b), 'InertBPass123!'));
  expect(current.status).toBe(200);
  expect(requests).toHaveLength(2);
  expect(requests[0].body).toEqual({ auth_code: 'INERT_ACCOUNT_B', code_verifier: 'INERT_VERIFIER_B' });
  expect(requests[1].principal).toBe('00000000-0000-4000-8000-000000000002');
  expect(requests[1].body.password).toBe('InertBPass123!');
  expect(current.cookies.get('sb-127-auth-token-code-verifier')).toBeUndefined();
  expect(current.cookies.get('auditgava-recovery')).toBeUndefined();
});

test('actual SSR client reassembles the frozen contiguous PKCE verifier chunks', async () => {
  const state = JSON.parse(staged('INERT_CODE', 'INERT_VERIFIER/PASSWORD_RECOVERY'));
  state.verifier = [
    { name: 'sb-127-auth-token-code-verifier.1', value: 'VERIFIER/PASSWORD_RECOVERY' },
    { name: 'sb-127-auth-token-code-verifier.0', value: 'INERT_' },
  ];
  mockStore.get.mockReturnValue({ value: JSON.stringify(state) });
  mockStore.getAll.mockReturnValue([{ name: 'sb-127-auth-token-code-verifier', value: 'INERT_OTHER' }]);
  const response = await POST(request());
  expect(response.status).toBe(200);
  expect(requests.map(r => r.method)).toEqual(['POST', 'PUT']);
  expect(requests[0].body.code_verifier).toBe('INERT_VERIFIER');
  expect(requests[1].principal).toBe(fixtureUser.id);
});
