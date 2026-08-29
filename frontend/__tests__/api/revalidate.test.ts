/**
 * The revalidation webhook (Layer 8): HMAC-gated, allowlisted, loud.
 */
import { createHmac } from 'crypto';

const mockRevalidatePath = jest.fn();
jest.mock('next/cache', () => ({
  revalidatePath: (...args: unknown[]) => mockRevalidatePath(...args),
}));
jest.mock('next/server', () => ({
  NextRequest: class {},
  NextResponse: {
    json: (body: unknown, init?: { status?: number }) => ({
      status: init?.status ?? 200,
      json: async () => body,
    }),
  },
}));

import { POST } from '@/app/api/revalidate/route';

const SECRET = 'test-secret';

function makeRequest(body: string, signature?: string) {
  return {
    text: async () => body,
    headers: {
      get: (name: string) =>
        name === 'x-revalidate-signature' ? (signature ?? null) : null,
    },
  } as any;
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
