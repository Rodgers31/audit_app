/** @jest-environment node */
import { createServerClient } from '@supabase/ssr';
import { NextRequest } from 'next/server';
import { updateSession } from '@/lib/supabase/middleware';

jest.mock('@supabase/ssr', () => ({ createServerClient: jest.fn() }));
const createClient = createServerClient as jest.Mock;

beforeEach(() => {
  createClient.mockReset();
  createClient.mockReturnValue({ auth: { getUser: jest.fn().mockResolvedValue({ data: { user: null } }) } });
});

test.each([false, true])('exact standalone callback never forwards the OAuth query to a public redirect (cookie=%s)', async cookie => {
  const request = new NextRequest('https://auditgava.test/admin/social/accounts/callback?code=FAKE_CODE&state=FAKE_STATE');
  if (cookie) request.cookies.set('sb-fixture-auth-token', 'expired-fixture');
  const response = await updateSession(request);
  expect(response.headers.get('x-middleware-next')).toBe('1');
  expect(response.headers.get('location')).toBeNull();
  expect(createClient).not.toHaveBeenCalled();
});

test.each(['/admin/social/accounts', '/admin/social/accounts/callback-evil', '/admin/social/new'])('other admin paths retain authorization protection: %s', async path => {
  const response = await updateSession(new NextRequest('https://auditgava.test' + path));
  expect(createClient).toHaveBeenCalledTimes(1);
  const location = new URL(response.headers.get('location')!);
  expect(location.pathname).toBe('/');
  expect(location.searchParams.get('authRequired')).toBe('1');
});
