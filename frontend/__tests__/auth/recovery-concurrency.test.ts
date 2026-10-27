/** @jest-environment node */
import { GET } from '@/app/auth/callback/route';
import { POST } from '@/app/api/auth/reset-password/route';
import { NextRequest } from 'next/server';
import { updateSession } from '@/lib/supabase/middleware';
const mockStore = { getAll: jest.fn(), get: jest.fn() };
const mockExchange = jest.fn();
const mockUpdate = jest.fn();
const mockServer = jest.fn();
jest.mock('next/headers', () => ({ cookies: async () => mockStore }));
jest.mock('@supabase/ssr', () => ({ createServerClient: (...args: unknown[]) => mockServer(...args) }));
jest.mock('@/lib/supabase/server', () => ({ createClient: async () => ({ auth: { exchangeCodeForSession: mockExchange } }) }));
const key = 'sb-fixture-auth-token-code-verifier';
beforeEach(() => {
  jest.clearAllMocks();
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://fixture.supabase.invalid';
  mockExchange.mockImplementation(async (code: string) => ({ data: { session: { user: { id: code } } }, error: null }));
  mockUpdate.mockResolvedValue({ error: null });
  mockServer.mockReturnValue({ auth: { exchangeCodeForSession: mockExchange, updateUser: mockUpdate, signOut: jest.fn(), getUser: async () => ({ data: { user: null } }) } });
});
async function stage(code: string, verifier: string, next = '/reset-password') {
  mockStore.getAll.mockReturnValue([{ name: key, value: verifier }]);
  return GET(new Request(`https://app.test/auth/callback?${new URLSearchParams({ code, next })}`));
}
function selector(response: Awaited<ReturnType<typeof GET>>, fallback: string) {
  return new URLSearchParams(new URL(response.headers.get('location')!).hash.slice(1)).get('recovery-flow') ?? fallback;
}
function request(flow?: string) {
  return new Request('https://app.test/api/auth/reset-password', { method: 'POST', headers: { origin: 'https://app.test', 'content-type': 'application/json' }, body: JSON.stringify({ password: 'InertPass123!', ...(flow ? { flow } : {}) }) });
}
test('older tab cannot exchange the code staged by a newer account callback', async () => {
  const a = await stage('INERT_ACCOUNT_A', 'INERT_VERIFIER_A');
  const b = await stage('INERT_ACCOUNT_B', 'INERT_VERIFIER_B');
  const stagedB = b.cookies.get('auditgava-recovery')!.value;
  mockStore.get.mockReturnValue({ value: stagedB });
  mockStore.getAll.mockReturnValue([{ name: 'auditgava-recovery', value: stagedB }, { name: key, value: 'INERT_VERIFIER_B' }]);
  const stale = await POST(request(selector(a, 'flow_A')));
  expect(stale.status).toBe(409);
  expect(mockExchange).not.toHaveBeenCalled();
  expect(mockUpdate).not.toHaveBeenCalled();
  expect(stale.cookies.get('auditgava-recovery')).toBeUndefined();
  const current = await POST(request(selector(b, 'flow_B')));
  expect(current.status).toBe(200);
  expect(mockExchange).toHaveBeenCalledWith('INERT_ACCOUNT_B');
});
test('latest flow uses its snapshotted verifier, never a later browser verifier', async () => {
  const b = await stage('INERT_ACCOUNT_B', 'INERT_VERIFIER_B');
  const cookie = b.cookies.get('auditgava-recovery')!.value;
  mockStore.get.mockReturnValue({ value: cookie });
  mockStore.getAll.mockReturnValue([{ name: 'auditgava-recovery', value: cookie }, { name: key, value: 'INERT_VERIFIER_C' }]);
  expect((await POST(request(selector(b, 'flow_B')))).status).toBe(200);
  const options = mockServer.mock.calls[0][2];
  expect(options.cookies.getAll()).toContainEqual({ name: key, value: 'INERT_VERIFIER_B' });
  expect(options.cookies.getAll()).not.toContainEqual({ name: key, value: 'INERT_VERIFIER_C' });
});
test('missing flow selector refuses without consuming staged recovery', async () => {
  const r = await stage('INERT_ACCOUNT_B', 'INERT_VERIFIER_B');
  mockStore.get.mockReturnValue({ value: r.cookies.get('auditgava-recovery')!.value });
  const response = await POST(request());
  expect(response.status).toBe(409);
  expect(mockExchange).not.toHaveBeenCalled();
  expect(response.cookies.get('auditgava-recovery')).toBeUndefined();
});
test.each(['/reset-password/', '/reset-password///'])('legacy %s removes query before page render', async (path) => {
  const req = new NextRequest(`https://app.test${path}?recovery=INERT_CODE`);
  req.cookies.set(key, 'INERT_VERIFIER');
  const r = await updateSession(req);
  expect(new URL(r.headers.get('location')!).pathname).toBe('/reset-password');
  expect(new URL(r.headers.get('location')!).search).toBe('');
  expect(r.cookies.get('auditgava-recovery')?.httpOnly).toBe(true);
});
test.each(['/reset-password/', '/reset-password/?old=INERT', '/reset-password///'])('callback destination %s defers exchange', async (next) => {
  const r = await stage('INERT_CODE', 'INERT_VERIFIER', next);
  expect(mockExchange).not.toHaveBeenCalled();
  expect(new URL(r.headers.get('location')!).pathname).toBe('/reset-password');
  expect(new URL(r.headers.get('location')!).search).toBe('');
  expect(r.cookies.get('auditgava-recovery')?.httpOnly).toBe(true);
});

test('an older in-flight reset response cannot delete a newer staged flow', async () => {
  const a = await stage('INERT_ACCOUNT_A', 'INERT_VERIFIER_A');
  mockStore.get.mockReturnValue({ value: a.cookies.get('auditgava-recovery')!.value });
  mockStore.getAll.mockReturnValue([{ name: key, value: 'INERT_VERIFIER_A' }]);
  let finish!: () => void;
  mockExchange.mockImplementationOnce(() => new Promise(resolve => {
    finish = () => resolve({ data: { session: { user: { id: 'INERT_ACCOUNT_A' } } }, error: null });
  }));
  const pending = POST(request(selector(a, 'flow_A')));
  for (let i = 0; i < 100 && !finish; i++) await Promise.resolve();
  expect(finish).toBeDefined();
  const b = await stage('INERT_ACCOUNT_B', 'INERT_VERIFIER_B');
  expect(b.cookies.get('auditgava-recovery')?.maxAge).toBe(300);
  // The old SDK work completes after B was staged and requests deletion of
  // its shared verifier; that mutation must not escape into the browser.
  mockServer.mock.calls[0][2].cookies.setAll([{ name: key, value: '', options: { maxAge: 0 } }]);
  finish();
  const response = await pending;
  expect(response.status).toBe(200);
  expect(response.cookies.get('auditgava-recovery')).toBeUndefined();
  expect(response.cookies.get(key)).toBeUndefined();
});
test('malformed callback leaves newer staged recovery and verifier untouched', async () => {
  const response = await GET(new Request('https://app.test/auth/callback?code=a&code=b&next=/reset-password'));
  expect(response.cookies.getAll()).toHaveLength(0);
  expect(mockExchange).not.toHaveBeenCalled();
});
test.each(['expired', 'malformed', 'oversized', 'wrong-project', 'extra-project', 'mixed-chunks', 'chunk-gap', 'duplicate-verifier', 'future-expiry', 'boolean-expiry'])('refused %s staged state does not mutate a newer browser flow', async (kind) => {
  const response = await stage('INERT_ACCOUNT_A', 'INERT_VERIFIER_A');
  const cookie = JSON.parse(response.cookies.get('auditgava-recovery')!.value);
  if (kind === 'expired') cookie.expiresAt = Date.now() - 1;
  if (kind === 'wrong-project') cookie.verifier = [{ name: 'sb-unrelated-auth-token-code-verifier', value: 'INERT_OTHER' }];
  if (kind === 'extra-project') cookie.verifier.push({ name: 'sb-unrelated-auth-token-code-verifier', value: 'INERT_OTHER' });
  if (kind === 'mixed-chunks') cookie.verifier.push({ name: key + '.0', value: 'INERT_OTHER' });
  if (kind === 'chunk-gap') cookie.verifier = [{ name: key + '.1', value: 'INERT_OTHER' }];
  if (kind === 'duplicate-verifier') cookie.verifier.push({ ...cookie.verifier[0] });
  if (kind === 'future-expiry') cookie.expiresAt = Date.now() + 3600000;
  if (kind === 'boolean-expiry') cookie.expiresAt = true;
  const value = kind === 'malformed' ? '{' : kind === 'oversized' ? 'x'.repeat(3801) : JSON.stringify(cookie);
  mockStore.get.mockReturnValue({ value });
  const result = await POST(request(selector(response, 'flow_A')));
  expect(result.status).toBe(400);
  expect(result.cookies.getAll()).toHaveLength(0);
  expect(mockExchange).not.toHaveBeenCalled();
});
test('oversized staged cookie refuses without retaining an envelope or code URL', async () => {
  const response = await stage('%'.repeat(1024), '%'.repeat(1024));
  expect(response.cookies.getAll()).toHaveLength(0);
  expect(response.headers.get('location')).not.toContain('%25%25');
  expect(new URL(response.headers.get('location')!).searchParams.has('error')).toBe(true);
});
