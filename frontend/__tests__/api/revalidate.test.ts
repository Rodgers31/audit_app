/** @jest-environment node */
/**
 * The revalidation webhook (Layer 8): HMAC-gated, allowlisted, loud.
 */
import { createHmac } from 'crypto';

const mockRevalidatePath = jest.fn();
jest.mock('next/cache', () => ({
  revalidatePath: (...args: unknown[]) => mockRevalidatePath(...args),
}));
import { POST } from '@/app/api/revalidate/route';

const SECRET = 'test-secret';

function makeRequest(body: string, signature?: string) {
  return new Request('https://app.test/api/revalidate', {
    method: 'POST', body,
    headers: signature ? { 'x-revalidate-signature': signature } : {},
  }) as any;
}

function sign(body: string, secret = SECRET) {
  return createHmac('sha256', secret).update(body).digest('hex');
}

describe('POST /api/revalidate', () => {
  beforeEach(() => {
    mockRevalidatePath.mockClear();
    process.env.REVALIDATE_SECRET = SECRET;
  });
  afterAll(() => {
    delete process.env.REVALIDATE_SECRET;
  });

  it('revalidates allowlisted paths with a valid signature', async () => {
    const body = JSON.stringify({ paths: ['/', '/audits'] });
    const res = await POST(makeRequest(body, sign(body)));
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.revalidated).toEqual(['/', '/audits']);
    expect(mockRevalidatePath).toHaveBeenCalledWith('/');
    expect(mockRevalidatePath).toHaveBeenCalledWith('/audits');
  });

  it('rejects a bad signature and revalidates nothing', async () => {
    const body = JSON.stringify({ paths: ['/'] });
    const res = await POST(makeRequest(body, sign(body, 'wrong-secret')));
    expect(res.status).toBe(401);
    expect(mockRevalidatePath).not.toHaveBeenCalled();
  });

  it('rejects a missing signature', async () => {
    const body = JSON.stringify({ paths: ['/'] });
    const res = await POST(makeRequest(body));
    expect(res.status).toBe(401);
    expect(mockRevalidatePath).not.toHaveBeenCalled();
  });

  it('fails closed (503) when the secret is not configured', async () => {
    delete process.env.REVALIDATE_SECRET;
    const body = JSON.stringify({ paths: ['/'] });
    const res = await POST(makeRequest(body, sign(body)));
    expect(res.status).toBe(503);
    expect(mockRevalidatePath).not.toHaveBeenCalled();
  });

  it('reports non-allowlisted paths as rejected, never silently drops', async () => {
    const body = JSON.stringify({ paths: ['/', '/etc/passwd'] });
    const res = await POST(makeRequest(body, sign(body)));
    const data = await res.json();
    expect(data.revalidated).toEqual(['/']);
    expect(data.rejected).toEqual(['/etc/passwd']);
    expect(mockRevalidatePath).toHaveBeenCalledTimes(1);
  });

  it('rejects malformed bodies', async () => {
    const body = 'not json';
    const res = await POST(makeRequest(body, sign(body)));
    expect(res.status).toBe(400);
  });
});

it('binds nightly page acknowledgments to the signed invocation', async () => {
  process.env.REVALIDATE_SECRET = SECRET;
  process.env.VERCEL_GIT_COMMIT_SHA = 'a'.repeat(40);
  const context = { source_sha: 'a'.repeat(40), plan_sha256: 'b'.repeat(64), run_id: '1234', run_attempt: '1', schema_head: 'a756b20a0001' };
  const body = JSON.stringify({protocol:'nightly-refresh-v2', ts:Math.floor(Date.now()/1000), nonce:'c'.repeat(32), context, paths:['/'], backend_adoption_sha256:'d'.repeat(64)});
  const response = await POST(makeRequest(body, sign(body)));
  const raw = await response.text();
  expect(response.status).toBe(200);
  expect(response.headers.get('x-revalidate-response-signature')).toBe(sign(raw));
  expect(JSON.parse(raw).context).toEqual(context);
  expect(JSON.parse(raw).result.backend_adoption_sha256).toBe('d'.repeat(64));
});

it.each(['stale', 'unknown', 'duplicate'])('refuses %s nightly requests before page mutation', async (kind) => {
  process.env.REVALIDATE_SECRET = SECRET;
  mockRevalidatePath.mockClear();
  process.env.VERCEL_GIT_COMMIT_SHA = 'a'.repeat(40);
  const body = JSON.stringify({protocol:kind==='unknown'?'future-v900':'nightly-refresh-v2', ts:Math.floor(Date.now()/1000)-(kind==='stale'?600:0), nonce:'c'.repeat(32), context:{source_sha:'a'.repeat(40),plan_sha256:'b'.repeat(64),run_id:'1234',run_attempt:'1',schema_head:'a756b20a0001'}, paths:kind==='duplicate'?['/','/']:['/'],backend_adoption_sha256:'d'.repeat(64)});
  const response = await POST(makeRequest(body, sign(body)));
  expect(response.status).toBe(400);
  expect(mockRevalidatePath).not.toHaveBeenCalled();
});
