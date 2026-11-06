/** HMAC-SHA256 over exact raw bytes; only manifest paths may be revalidated. */
import { createHash, createHmac, timingSafeEqual } from 'crypto';
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
    const payload = jsonObject(bytes);
    const { paths } = payload;
    const nightly = ['protocol', 'context', 'nonce', 'backend_adoption_sha256'].some(key => key in payload);
    if (nightly) {
      const context = payload.context as Record<string, unknown> | undefined;
      const exactKeys = (value: object, keys: string[]) => Object.keys(value).sort().join('|') === keys.sort().join('|');
      const pattern = (value: unknown, expression: RegExp) => typeof value === 'string' && expression.test(value);
      if (!exactKeys(payload, ['protocol', 'ts', 'nonce', 'context', 'paths', 'backend_adoption_sha256']) ||
          payload.protocol !== 'nightly-refresh-v2' || !Number.isSafeInteger(payload.ts) ||
          Math.abs(Date.now() / 1000 - Number(payload.ts)) > 300 ||
          !pattern(payload.nonce, /^[a-f0-9]{32}$/) ||
          !pattern(payload.backend_adoption_sha256, /^[a-f0-9]{64}$/) ||
          !context || typeof context !== 'object' || Array.isArray(context) ||
          !exactKeys(context, ['source_sha', 'plan_sha256', 'run_id', 'run_attempt', 'schema_head']) ||
          !pattern(context.source_sha, /^[a-f0-9]{40}$/) || !pattern(context.plan_sha256, /^[a-f0-9]{64}$/) ||
          !pattern(context.run_id, /^[1-9][0-9]{0,17}$/) || !pattern(context.run_attempt, /^[1-9][0-9]{0,4}$/) ||
          context.schema_head !== 'a756b20a0001' || context.source_sha !== process.env.VERCEL_GIT_COMMIT_SHA ||
          !Array.isArray(paths) || new Set(paths).size !== paths.length || paths.some(p => !REVALIDATE_PATHS.has(p)))
        throw new RequestFailure(400, 'nightly_refresh_refused');
    }
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
    const result = { revalidated, rejected, at: new Date().toISOString() };
    if (nightly) {
      const raw = JSON.stringify({protocol:'nightly-refresh-v2', context:payload.context,
        request_sha256:createHash('sha256').update(bytes).digest('hex'), at:Math.floor(Date.now()/1000),
        result:{...result, backend_adoption_sha256:payload.backend_adoption_sha256}});
      return new NextResponse(raw, {headers:{'content-type':'application/json', 'cache-control':'no-store',
        'x-revalidate-response-signature':createHmac('sha256', secret).update(raw).digest('hex')}});
    }
    return NextResponse.json(result);
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
