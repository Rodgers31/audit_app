/** Exchange PKCE and update once on the server, avoiding browser auto-refresh/WebLock races. */
import { createHash } from 'crypto';
import { createServerClient } from '@supabase/ssr';
import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import { MAX_PASSWORD_BYTES, privateResponse, readRecovery, RECOVERY_COOKIE } from '@/lib/auth/recovery';
import { createAdmission, jsonObject, readBoundedBytes, readRequestBytes, RequestBudget, RequestFailure } from '@/lib/security/request-budget';
export const runtime = 'nodejs';
export const maxDuration = 20;
const admit = createAdmission(8);
// Only active hashes; never passwords/codes or an unbounded replay registry.
// PKCE one-use exchange remains the cross-instance replay boundary.
const activeCodes = new Set<string>();
export async function POST(request: Request) {
  const respond = (error: string, status: number) => privateResponse(NextResponse.json({ error }, { status }));
  if (request.headers.get('origin') !== new URL(request.url).origin)
    return respond('Invalid request origin.', 403);
  if (request.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json') {
    return respond('Expected JSON payload.', 415);
  }
  const budget = new RequestBudget(request, 15000);
  let release: (() => void) | undefined;
  let codeHash: string | undefined;
  try {
    release = admit();
    const body = jsonObject(await readRequestBytes(request, budget, 8192));
    const password = body.password;
    if (typeof password !== 'string' || password.length < 8 || password.length > MAX_PASSWORD_BYTES ||
      new TextEncoder().encode(password).byteLength > MAX_PASSWORD_BYTES) {
      return respond('Password must be between 8 characters and 1024 UTF-8 bytes.', 400);
    }
    const cookieStore = await budget.wait(cookies());
    const staged = readRecovery(cookieStore.get(RECOVERY_COOKIE)?.value);
    if (!staged)
      return respond('Missing or invalid reset code. Please request a new reset link.', 400);
    if (typeof body.flow !== 'string' || body.flow !== staged.flow)
      return respond('This reset form has been replaced or expired. Please reopen your latest reset link.', 409);
    const code = staged.code;
    const candidateHash = createHash('sha256').update(code).digest('hex');
    if (activeCodes.has(candidateHash))
      throw new RequestFailure(409, 'reset_already_in_progress');
    activeCodes.add(candidateHash);
    codeHash = candidateHash;
    const success = privateResponse(NextResponse.json({ ok: true }));
    // Do not let a stale unrelated session refresh or authorize updateUser.
    // Freeze the verifier paired with this exact callback, not a later tab's cookie.
    const incoming = staged.verifier;
    const supabase = createServerClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, {
      global: {
        fetch: async (input, init) => {
          budget.check();
          const signal = init?.signal ? AbortSignal.any([budget.signal, init.signal]) : budget.signal;
          const response = await budget.wait(fetch(input, { ...init, signal }));
          const bytes = await readBoundedBytes(response.body, response.headers, budget, 131072);
          return new Response([204, 205, 304].includes(response.status) ? null : new Uint8Array(bytes).buffer, { status: response.status, statusText: response.statusText, headers: response.headers });
        },
      },
      cookies: {
        getAll: () => incoming,
        // A delayed exchange must never delete a newer tab's shared verifier.
        setAll: (values) => values.forEach(({ name, value, options }) => {
          if (!/-auth-token-code-verifier(\.\d+)?$/.test(name))
            success.cookies.set(name, value, options);
        }),
      },
    });
    const failure = (message: string) => {
      // No incoming session was admitted. A failed operation has no browser
      // cookie authority and must not clear a newer tab's session or verifier.
      return respond(message, 400);
    };
    const operation = (async () => {
      budget.check();
      const { data, error } = await supabase.auth.exchangeCodeForSession(code);
      budget.check();
      if (error || !data.session)
        return failure('The reset link is invalid or has expired. Please request a new one.');
      const { error: updateError } = await supabase.auth.updateUser({ password });
      budget.check();
      if (updateError) {
        try {
          const { error: signOutError } = await supabase.auth.signOut();
          if (signOutError)
            console.warn('[reset-password] session cleanup failed');
        }
        catch {
          console.warn('[reset-password] session cleanup failed');
        }
        return failure('Failed to update password. Please request a new reset link.');
      }
      return success;
    })();
    // Keep admission and duplicate ownership until the actual SDK work settles,
    // even if a dependency disregards AbortSignal and the response times out.
    const finish = release;
    const hash = codeHash;
    void operation.finally(() => {
      activeCodes.delete(hash);
      finish();
    }).catch(() => {
    });
    release = undefined;
    codeHash = undefined;
    // Do not delete the shared staged cookie: another callback may have
    // replaced it while this operation was in flight. Its fixed TTL remains.
    return await budget.wait(operation);
  }
  catch (error) {
    const response = error instanceof RequestFailure ? respond(error.message, error.status) : respond('Password reset unavailable. Please request a new reset link.', 502);
    return response;
  }
  finally {
    // The active operation owns its hash; duplicate rejections do not delete it.
    if (codeHash && release)
      activeCodes.delete(codeHash);
    release?.();
    budget.dispose();
  }
}
