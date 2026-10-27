/** @jest-environment node */
import { GET } from '@/app/auth/callback/route';
import { NextRequest } from 'next/server';
import { updateSession } from '@/lib/supabase/middleware';
const mockExchange = jest.fn();
const mockServer = jest.fn();
const mockCookies = { getAll: () => [{ name: 'sb-fixture-auth-token', value: 'STALE' }, { name: 'sb-fixture-auth-token.0', value: 'STALE_CHUNK' }, { name: 'sb-fixture-auth-token-code-verifier', value: 'INERT_VERIFIER' }] };
jest.mock('next/headers', () => ({ cookies: async () => mockCookies }));
jest.mock('@/lib/supabase/server', () => ({ createClient: async () => ({ auth: { exchangeCodeForSession: mockExchange } }) }));
jest.mock('@supabase/ssr', () => ({ createServerClient: (...a: unknown[]) => mockServer(...a) }));
beforeEach(() => {
  jest.clearAllMocks();
  mockExchange.mockResolvedValue({ error: null });
  mockServer.mockReturnValue({ auth: { getUser: async () => ({ data: { user: null } }) } });
});
test('recovery never forwards code into the rendered page URL', async () => {
  const r = await GET(new Request('https://app.test/auth/callback?code=INERT_CODE&next=/reset-password'));
  expect(r.headers.get('location')).toBe('https://app.test/reset-password');
  const c = r.cookies.get('auditgava-recovery');
  expect(c?.value).toBe('INERT_CODE');
  expect(c?.httpOnly).toBe(true);
  expect(c?.secure).toBe(true);
  expect(c?.path).toBe('/api/auth/reset-password');
  expect(c?.maxAge).toBe(300);
  expect(r.cookies.get('sb-fixture-auth-token')?.maxAge).toBe(0);
  expect(r.cookies.get('sb-fixture-auth-token.0')?.maxAge).toBe(0);
  expect(r.cookies.get('sb-fixture-auth-token-code-verifier')).toBeUndefined();
  expect(mockExchange).not.toHaveBeenCalled();
});
test.each(['/auth/callback?code=INERT_CODE&next=/reset-password', '/api/auth/reset-password', '/reset-password'])('recovery ingress %s bypasses stale-session network refresh', async (path) => {
  const req = new NextRequest('https://app.test' + path);
  req.cookies.set('sb-fixture-auth-token', 'STALE');
  await updateSession(req);
  expect(mockServer).not.toHaveBeenCalled();
});
test('legacy recovery query is staged before any page render', async () => {
  const r = await updateSession(new NextRequest('https://app.test/reset-password?recovery=INERT_CODE&other=INERT_MARKER'));
  expect(r.headers.get('location')).toBe('https://app.test/reset-password');
  expect(r.cookies.get('auditgava-recovery')?.value).toBe('INERT_CODE');
  expect(mockServer).not.toHaveBeenCalled();
});
test.each(['code=a&code=b', 'code=' + 'x'.repeat(1025), 'code=a&next=/reset-password&next=/'])('ambiguous/overlong callback refuses %s', async (query) => {
  const r = await GET(new Request('https://app.test/auth/callback?' + query));
  expect(mockExchange).not.toHaveBeenCalled();
  expect(r.cookies.get('auditgava-recovery')?.value).not.toBe('a');
  expect(r.headers.get('location')).not.toContain('code=');
});
