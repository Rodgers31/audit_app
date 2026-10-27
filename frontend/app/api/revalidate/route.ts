/** HMAC-SHA256 over exact raw bytes; only manifest paths may be revalidated. */
import { createHmac, timingSafeEqual } from 'crypto';
import { revalidatePath } from 'next/cache';
import { NextRequest, NextResponse } from 'next/server';
import { REVALIDATE_PATHS, revalidateType } from '@/lib/revalidation/paths';
import { createAdmission, jsonObject, readRequestBytes, RequestBudget, RequestFailure } from '@/lib/security/request-budget';
export const runtime = 'nodejs';
export const maxDuration = 10;
const admit = createAdmission(4);
export async function POST(req: NextRequest) {
  const secret = process.env.REVALIDATE_SECRET;
  if (!secret)
    return NextResponse.json({ error: 'revalidation_not_configured' }, { status: 503 });
  const signature = req.headers.get('x-revalidate-signature') ?? '';
  if (!/^[a-f0-9]{64}$/.test(signature))
    return NextResponse.json({ error: 'invalid_signature' }, { status: 401 });
  let release: (() => void) | undefined;
  const budget = new RequestBudget(req, 5000);
  try {
    release = admit();
    const bytes = await readRequestBytes(req, budget, 8192);
    const expected = createHmac('sha256', secret).update(bytes).digest('hex');
    if (!timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) {
      return NextResponse.json({ error: 'invalid_signature' }, { status: 401 });
    }
    const { paths } = jsonObject(bytes);
    if (!Array.isArray(paths) || paths.length === 0)
      throw new RequestFailure(400, 'no_paths');
    if (paths.length > 64 || paths.some(p => typeof p !== 'string' || p.length > 256)) {
      throw new RequestFailure(400, 'invalid_paths');
    }
    const revalidated: string[] = [];
    const rejected: string[] = [];
    for (const p of Array.from(new Set<string>(paths))) {
      budget.check();
      if (REVALIDATE_PATHS.has(p)) {
        const type = revalidateType(p);
        if (type)
          revalidatePath(p, type);
        else
          revalidatePath(p);
        revalidated.push(p);
      }
      else {
        rejected.push(p);
      }
    }
    budget.check();
    return NextResponse.json({ revalidated, rejected, at: new Date().toISOString() });
  }
  catch (error) {
    if (!(error instanceof RequestFailure))
      throw error;
    return NextResponse.json({ error: error.message }, { status: error.status });
  }
  finally {
    budget.dispose();
    release?.();
  }
}
