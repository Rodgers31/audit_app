/** @jest-environment node */
import { createHmac } from 'crypto';
import { POST as revalidate } from '@/app/api/revalidate/route';
import { POST as reset } from '@/app/api/auth/reset-password/route';
const mockInvalidate = jest.fn();
const mockExchange = jest.fn();
const mockUpdate = jest.fn();
const mockSignOut = jest.fn();
const mockStore = { getAll: jest.fn(), get: jest.fn() };
jest.mock('next/cache', () => ({ revalidatePath: (...a: unknown[]) => mockInvalidate(...a) }));
jest.mock('next/headers', () => ({ cookies: async () => mockStore }));
jest.mock('@supabase/ssr', () => ({ createServerClient: jest.fn(() => ({ auth: { exchangeCodeForSession: mockExchange, updateUser: mockUpdate, signOut: mockSignOut } })) }));
function signed(body: string, headers: Record<string, string> = {}) {
  return new Request('https://app.test/api/revalidate', { method: 'POST', body, headers: { 'x-revalidate-signature': createHmac('sha256', 'inert-secret').update(body).digest('hex'), ...headers } }) as any;
}
function resetRequest(body: string) {
  return new Request('https://app.test/api/auth/reset-password', { method: 'POST', body, headers: { origin: 'https://app.test', 'content-type': 'application/json' } });
}
beforeEach(() => {
  jest.clearAllMocks();
  process.env.REVALIDATE_SECRET = 'inert-secret';
  mockExchange.mockResolvedValue({ data: { session: { user: { id: 'fixture' } } }, error: null });
  mockUpdate.mockResolvedValue({ error: null });
  mockSignOut.mockResolvedValue({ error: null });
  mockStore.get.mockReturnValue({ value: 'INERT_CODE' });
  mockStore.getAll.mockReturnValue([{ name: 'auditgava-recovery', value: 'INERT_CODE' }, { name: 'sb-fixture-auth-token-code-verifier', value: 'INERT_VERIFIER' }]);
});
test.each(['null', '[]', '1', '"x"', '{'])('reset rejects malformed shape %s without provider I/O', async (body) => {
  expect((await reset(resetRequest(body))).status).toBe(400);
  expect(mockExchange).not.toHaveBeenCalled();
});
test('reset refuses oversized streamed JSON before provider I/O', async () => {
  expect((await reset(resetRequest(JSON.stringify({ code: 'INERT_CODE', password: 'a'.repeat(9000) })))).status).toBe(413);
  expect(mockExchange).not.toHaveBeenCalled();
});
test('reset refuses excessive password length', async () => {
  expect((await reset(resetRequest(JSON.stringify({ code: 'INERT_CODE', password: 'a'.repeat(1025) })))).status).toBe(400);
  expect(mockExchange).not.toHaveBeenCalled();
});
test('reset requires same-origin form submission', async () => {
  const r = resetRequest(JSON.stringify({ code: 'INERT_CODE', password: 'InertPass123!' }));
  r.headers.set('origin', 'https://forged.test');
  expect((await reset(r)).status).toBe(403);
  expect(mockExchange).not.toHaveBeenCalled();
});
test('query-free recovery exchanges cookie once and updates once', async () => {
  const res = await reset(resetRequest(JSON.stringify({ password: 'InertPass123!' })));
  expect(res.status).toBe(200);
  expect(mockExchange).toHaveBeenCalledTimes(1);
  expect(mockExchange).toHaveBeenCalledWith('INERT_CODE');
  expect(mockUpdate).toHaveBeenCalledTimes(1);
  expect(res.headers.get('cache-control')).toBe('private, no-store');
  expect(res.cookies.get('auditgava-recovery')?.maxAge).toBe(0);
});
test('revalidation caps raw bytes even with a valid signature', async () => {
  expect((await revalidate(signed(JSON.stringify({ paths: ['/'], pad: 'x'.repeat(9000) })))).status).toBe(413);
  expect(mockInvalidate).not.toHaveBeenCalled();
});
test('revalidation bounds duplicate work', async () => {
  const res = await revalidate(signed(JSON.stringify({ paths: ['/', '/', '/audits', '/audits'] })));
  expect(res.status).toBe(200);
  expect(mockInvalidate).toHaveBeenCalledTimes(2);
  expect((await res.json()).revalidated).toEqual(['/', '/audits']);
});
test.each(['null', '[]', '1', '"x"', '{'])('revalidation rejects malformed shape %s', async (body) => {
  expect((await revalidate(signed(body))).status).toBe(400);
  expect(mockInvalidate).not.toHaveBeenCalled();
});
test('revalidation normal signed bytes retain allowlist', async () => {
  const r = await revalidate(signed('{ "paths" : ["/", "/forbidden"] }'));
  expect(r.status).toBe(200);
  expect((await r.json()).rejected).toEqual(['/forbidden']);
  expect(mockInvalidate).toHaveBeenCalledTimes(1);
});
test('active reset duplicate is refused without releasing the first owner', async () => {
  let finish!: () => void;
  mockExchange.mockImplementationOnce(() => new Promise(resolve => {
    finish = () => resolve({ data: { session: {} }, error: null });
  }));
  const first = reset(resetRequest(JSON.stringify({ password: 'InertPass123!' })));
  while (!finish)
    await new Promise(resolve => setTimeout(resolve, 0));
  const second = await reset(resetRequest(JSON.stringify({ password: 'InertPass123!' })));
  expect(second.status).toBe(409);
  const third = await reset(resetRequest(JSON.stringify({ password: 'InertPass123!' })));
  expect(third.status).toBe(409);
  finish();
  expect((await first).status).toBe(200);
  expect(mockExchange).toHaveBeenCalledTimes(1);
});
test('absent cookie cannot substitute a JSON body code', async () => {
  mockStore.get.mockReturnValue(undefined);
  expect((await reset(resetRequest(JSON.stringify({ code: 'INERT_CODE', password: 'InertPass123!' })))).status).toBe(400);
  expect(mockExchange).not.toHaveBeenCalled();
});
test('forged cookie without valid PKCE evidence cannot update', async () => {
  mockExchange.mockResolvedValue({ data: { session: null }, error: { message: 'INERT_PROVIDER_MESSAGE' } });
  const res = await reset(resetRequest(JSON.stringify({ password: 'InertPass123!' })));
  expect(res.status).toBe(400);
  expect(mockUpdate).not.toHaveBeenCalled();
  expect(JSON.stringify(await res.json())).not.toContain('INERT_PROVIDER_MESSAGE');
});
test('password update failure delivers no session cookies and attempts signout', async () => {
  mockUpdate.mockResolvedValue({ error: { message: 'INERT_PASSWORD_ECHO' } });
  const res = await reset(resetRequest(JSON.stringify({ password: 'InertPass123!' })));
  expect(res.status).toBe(400);
  expect(mockSignOut).toHaveBeenCalledTimes(1);
  expect(JSON.stringify(await res.json())).not.toContain('INERT_PASSWORD_ECHO');
});
test('missing signature refuses without opening body reader', async () => {
  const req = signed('x');
  req.headers.delete('x-revalidate-signature');
  const spy = jest.spyOn(req.body!, 'getReader');
  expect((await revalidate(req)).status).toBe(401);
  expect(spy).not.toHaveBeenCalled();
});
test('signed multibyte bytes and whitespace are not normalized', async () => {
  const body = ' { "paths": ["/"], "marker": "é" } ';
  const res = await revalidate(signed(body));
  expect(res.status).toBe(200);
  expect(mockInvalidate).toHaveBeenCalledTimes(1);
});
test.each([Array(65).fill('/'), ['/'.repeat(257)], [null], [{}], [1]])('signed invalid paths refuse before side effects %p', async (paths) => {
  expect((await revalidate(signed(JSON.stringify({ paths })))).status).toBe(400);
  expect(mockInvalidate).not.toHaveBeenCalled();
});
test('stream cancellation prevents revalidation', async () => {
  const controller = new AbortController();
  controller.abort();
  const req = new Request('https://app.test/api/revalidate', { method: 'POST', body: '{}', signal: controller.signal, headers: { 'x-revalidate-signature': '0'.repeat(64) } });
  expect((await revalidate(req as any)).status).toBe(408);
  expect(mockInvalidate).not.toHaveBeenCalled();
});
test('slow body deadline cancels the stream and releases admission', async () => {
  jest.useFakeTimers();
  const cancelled = jest.fn();
  const req = new Request('https://app.test/api/revalidate', { method: 'POST', body: new ReadableStream({ pull: () => new Promise(() => {
      }), cancel: cancelled }), duplex: 'half', headers: { 'x-revalidate-signature': '0'.repeat(64) } } as any);
  const response = revalidate(req as any);
  await jest.advanceTimersByTimeAsync(5001);
  expect((await response).status).toBe(504);
  expect(cancelled).toHaveBeenCalled();
  jest.useRealTimers();
  expect((await revalidate(signed('{"paths":["/"]}'))).status).toBe(200);
});
test('reset aggregate admission refuses the ninth slow request and recovers after cancellation', async () => {
  const pending: Array<{
    abort: AbortController;
    result: Promise<Response>;
  }> = [];
  for (let i = 0; i < 8; i++) {
    const abort = new AbortController();
    const req = new Request('https://app.test/api/auth/reset-password', { method: 'POST', body: new ReadableStream({ pull: () => new Promise(() => {
        }) }), duplex: 'half', signal: abort.signal, headers: { origin: 'https://app.test', 'content-type': 'application/json' } } as any);
    pending.push({ abort, result: reset(req) });
  }
  try {
    expect((await reset(resetRequest('{"password":"InertPass123!"}'))).status).toBe(503);
  }
  finally {
    pending.forEach(p => p.abort.abort());
    expect((await Promise.all(pending.map(p => p.result))).map(r => r.status)).toEqual(Array(8).fill(408));
  }
  expect((await reset(resetRequest('{"password":"InertPass123!"}'))).status).toBe(200);
});
test('reset request deadline does not free duplicate ownership before SDK settles', async () => {
  jest.useFakeTimers();
  let finish!: () => void;
  mockExchange.mockImplementationOnce(() => new Promise(resolve => {
    finish = () => resolve({ data: { session: {} }, error: null });
  }));
  const first = reset(resetRequest('{"password":"InertPass123!"}'));
  await jest.advanceTimersByTimeAsync(1);
  expect(finish).toBeDefined();
  await jest.advanceTimersByTimeAsync(15001);
  expect((await first).status).toBe(504);
  expect((await reset(resetRequest('{"password":"InertPass123!"}'))).status).toBe(409);
  finish();
  await jest.advanceTimersByTimeAsync(1);
  expect(mockUpdate).not.toHaveBeenCalled();
  jest.useRealTimers();
  expect((await reset(resetRequest('{"password":"InertPass123!"}'))).status).toBe(200);
});
test('advertised body length refuses before reading the stream', async () => {
  const req = signed('{"paths":["/"]}', { 'content-length': '8193' });
  const spy = jest.spyOn(req.body!, 'getReader');
  expect((await revalidate(req)).status).toBe(413);
  expect(spy).not.toHaveBeenCalled();
  expect(mockInvalidate).not.toHaveBeenCalled();
});
test('lying Content-Length cannot bypass streamed cap', async () => {
  const req = signed(JSON.stringify({ paths: ['/'], pad: 'x'.repeat(9000) }), { 'content-length': '1' });
  expect((await revalidate(req)).status).toBe(413);
  expect(mockInvalidate).not.toHaveBeenCalled();
});
test('overlong multibyte password is refused by byte count', async () => {
  expect((await reset(resetRequest(JSON.stringify({ password: 'é'.repeat(513) })))).status).toBe(400);
  expect(mockExchange).not.toHaveBeenCalled();
});
