/**
 * POST /api/revalidate — the freshness loop's entry point (Layer 8).
 *
 * The nightly seed job calls this after data lands and validates, so a new
 * OAG/COB publication reaches the prerendered pages without a deploy.
 *
 * Auth: HMAC-SHA256 of the raw request body with the shared
 * REVALIDATE_SECRET, sent as `x-revalidate-signature` (hex). Unsigned or
 * mis-signed requests are rejected; an unconfigured secret disables the
 * endpoint loudly (503) rather than open (no-silent-fallbacks).
 *
 * Body: {"paths": ["/", "/audits", ...]} — only known app routes are
 * accepted; anything else is reported back as rejected, never silently
 * dropped.
 */
import { createHmac, timingSafeEqual } from 'crypto';
import { revalidatePath } from 'next/cache';
import { NextRequest, NextResponse } from 'next/server';

const ALLOWED_PATHS = new Set([
  '/',
  '/audits',
  '/budget',
  '/counties',
  '/counties/compare',
  '/debt',
  '/sectors',
  '/transparency',
  '/accountability/missing-funds',
  '/sources',
]);

export async function POST(req: NextRequest) {
  const secret = process.env.REVALIDATE_SECRET;
  if (!secret) {
    return NextResponse.json(
      { error: 'revalidation_not_configured' },
      { status: 503 }
    );
  }

  const body = await req.text();
  const signature = req.headers.get('x-revalidate-signature') ?? '';
  const expected = createHmac('sha256', secret).update(body).digest('hex');
  const sigBuf = Buffer.from(signature, 'utf8');
  const expBuf = Buffer.from(expected, 'utf8');
  if (sigBuf.length !== expBuf.length || !timingSafeEqual(sigBuf, expBuf)) {
    return NextResponse.json({ error: 'invalid_signature' }, { status: 401 });
  }

  let paths: unknown;
  try {
    paths = JSON.parse(body).paths;
  } catch {
    return NextResponse.json({ error: 'malformed_body' }, { status: 400 });
  }
  if (!Array.isArray(paths) || paths.length === 0) {
    return NextResponse.json({ error: 'no_paths' }, { status: 400 });
  }

  const revalidated: string[] = [];
  const rejected: string[] = [];
  for (const p of paths) {
    if (typeof p === 'string' && ALLOWED_PATHS.has(p)) {
      revalidatePath(p);
      revalidated.push(p);
    } else {
      rejected.push(String(p));
    }
  }
  return NextResponse.json({
    revalidated,
    rejected,
    at: new Date().toISOString(),
  });
}
