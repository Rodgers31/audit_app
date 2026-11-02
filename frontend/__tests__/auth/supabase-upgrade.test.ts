/** @jest-environment node */
import { NextRequest } from 'next/server';
import { updateSession } from '@/lib/supabase/middleware';

const actor = '00000000-0000-4000-8000-000000000001';
const user = { id: actor, aud: 'authenticated', role: 'authenticated', email: 'fixture@example.test', app_metadata: {}, user_metadata: {}, created_at: '2026-01-01T00:00:00Z' };
function token(exp: number) {
  return [Buffer.from('{"alg":"HS256","typ":"JWT"}').toString('base64url'), Buffer.from(JSON.stringify({ sub: actor, aud: 'authenticated', exp })).toString('base64url'), 'fixture-signature'].join('.');
}

test.each(['admin', 'non-admin', 'revoked-session'])('actual upgraded SSR %s refresh preserves legacy cookies, identity and SDK cache protection', async mode => {
  const previousUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const previousKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://project.fixture.test';
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'inert-public-fixture-key';
  const requests: string[] = [];
  const fetch = jest.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url);
    requests.push(url.pathname);
    if (url.origin !== 'https://project.fixture.test') throw new Error('Unexpected fixture origin');
    if (url.pathname === '/auth/v1/token') return Response.json({ access_token: token(Math.floor(Date.now() / 1000) + 3600), refresh_token: 'rotated-fixture-refresh', expires_in: 3600, token_type: 'bearer', user });
    if (url.pathname === '/auth/v1/user') return mode === 'revoked-session'
      ? Response.json({ error_code: 'session_not_found', msg: 'Synthetic session revoked' }, { status: 401 }) : Response.json(user);
    if (url.pathname === '/rest/v1/profiles') return Response.json({ id: actor, roles: mode === 'non-admin' ? ['citizen'] : ['admin'] });
    throw new Error('Unexpected fixture path');
  });
  try {
    const session = { access_token: token(1), refresh_token: 'old-fixture-refresh', expires_at: 1, expires_in: 3600, token_type: 'bearer', user };
    const cookie = 'base64-' + Buffer.from(JSON.stringify(session)).toString('base64url');
    const response = await updateSession(new NextRequest('https://audit.example.test/admin/users', { headers: { cookie: 'sb-project-auth-token=' + cookie } }));
    expect(requests.filter(path => path === '/auth/v1/token')).toHaveLength(1);
    if (mode === 'revoked-session') expect(requests).not.toContain('/rest/v1/profiles');
    else expect(requests).toContain('/rest/v1/profiles');
    if (mode === 'admin') expect(response.headers.get('x-middleware-next')).toBe('1');
    else expect(response.headers.get('location')).toContain(mode === 'non-admin' ? 'unauthorized=1' : 'authRequired=1');
    expect(response.headers.get('cache-control')).toContain('private');
    expect(response.headers.get('cache-control')).toContain('no-store');
    expect(response.headers.get('pragma')).toBe('no-cache');
    expect(response.headers.get('expires')).toBe('0');
    expect(response.cookies.getAll().some(item => item.name.startsWith('sb-project-auth-token') && (mode === 'revoked-session' ? item.value === '' : item.value.length > 0))).toBe(true);
  } finally {
    fetch.mockRestore();
    if (previousUrl === undefined) delete process.env.NEXT_PUBLIC_SUPABASE_URL; else process.env.NEXT_PUBLIC_SUPABASE_URL = previousUrl;
    if (previousKey === undefined) delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY; else process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = previousKey;
  }
});
