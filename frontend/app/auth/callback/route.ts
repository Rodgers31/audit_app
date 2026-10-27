/** Email-link callback. Recovery defers PKCE exchange until password submission. */
import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import { isResetPasswordPath, privateResponse, recoveryRedirect, validRecoveryCode } from '@/lib/auth/recovery';
import { createClient } from '@/lib/supabase/server';

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const suppliedNext = searchParams.get('next') ?? '/';
  const next = suppliedNext.startsWith('/') && !suppliedNext.startsWith('//') &&
    !/[\\\u0000-\u0020\u007f]/.test(suppliedNext) ? suppliedNext : '/';
  const code = searchParams.get('code');
  if (searchParams.getAll('code').length !== 1 || searchParams.getAll('next').length > 1 || !validRecoveryCode(code)) {
    return recoveryRedirect(request.url, null, []);
  }
  if (isResetPasswordPath(new URL(next, origin).pathname)) {
    const cookieStore = await cookies();
    // HttpOnly, host-only, five minutes, API path only. No session is created;
    // clear stale session chunks but keep the browser's PKCE verifier intact.
    return recoveryRedirect(request.url, code, cookieStore.getAll());
  }
  const supabase = await createClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (!error) return privateResponse(NextResponse.redirect(`${origin}${next}`));
  return recoveryRedirect(request.url, null, []);
}
