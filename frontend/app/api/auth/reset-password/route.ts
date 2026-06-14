/**
 * POST /api/auth/reset-password
 *
 * Atomic password-reset endpoint. Inputs:
 *
 *   { code: string, password: string }
 *
 * where ``code`` is the PKCE recovery code Supabase forwarded to
 * /auth/callback (passed through to /reset-password as a query param
 * named ``recovery`` without being exchanged — see
 * app/auth/callback/route.ts for that decision).
 *
 * Why exchange + updateUser run server-side
 * -----------------------------------------
 * Doing both on the client (via the browser SDK) starts the
 * GoTrueClient's ``_autoRefreshTokenTick`` the moment the exchange
 * succeeds, which races with the immediately-following ``updateUser``
 * for the gotrue Web Lock — that lock-queue contention was the actual
 * source of the duplicate ``PUT /auth/v1/user`` → ``code:
 * same_password`` error we chased across PRs #87, #92, #93, #94, #95.
 * The server-side @supabase/ssr client doesn't run an auto-refresh
 * tick, so exchange + update happen sequentially with no race.
 *
 * Why we DO write session cookies on success (auto-login)
 * -------------------------------------------------------
 * The user just typed the new password; making them retype the same
 * thing on a sign-in page is friction with no security benefit (they
 * already demonstrated control of the new credential, and PKCE
 * already proved they're the browser that initiated the flow). So
 * once update succeeds we let the SDK's normal cookie writes go
 * through to the response, and the browser ends up with a fresh
 * session attached to the just-changed password. The page then
 * calls ``refreshUser()`` and redirects to home.
 *
 * Pre-existing-session cleanup happens upstream in /auth/callback,
 * which signs out any stale session before forwarding the recovery
 * code here, so we never end up with the wrong account's cookies.
 */
import { createServerClient } from '@supabase/ssr';
import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  let body: { code?: unknown; password?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON payload' }, { status: 400 });
  }

  const code = typeof body.code === 'string' ? body.code : null;
  const password = typeof body.password === 'string' ? body.password : null;

  if (!code) {
    return NextResponse.json(
      { error: 'Missing or invalid reset code. Please request a new reset link.' },
      { status: 400 }
    );
  }
  if (!password || password.length < 8) {
    return NextResponse.json(
      { error: 'Password must be at least 8 characters.' },
      { status: 400 }
    );
  }

  const cookieStore = await cookies();

  // Build the success response up-front so cookies the SDK writes
  // during exchange/updateUser are attached to *this* response. If
  // we returned a fresh ``NextResponse.json`` later we'd lose them
  // — Next.js doesn't propagate cookies set via request-scoped
  // ``cookies().set()`` onto a different response object reliably.
  const successResponse = NextResponse.json({ ok: true });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => cookieStore.getAll(),
        setAll: (cookiesToSet) => {
          // Forward every cookie the SDK wants to set onto our
          // success response. After ``exchangeCodeForSession`` this
          // includes ``sb-<ref>-auth-token`` (the new session) and
          // a cleared ``sb-<ref>-auth-token-code-verifier`` (the
          // verifier is one-shot and gets removed on use).
          cookiesToSet.forEach(({ name, value, options }) => {
            successResponse.cookies.set(name, value, options);
          });
        },
      },
    }
  );

  const { data: exchangeData, error: exchangeError } =
    await supabase.auth.exchangeCodeForSession(code);

  if (exchangeError || !exchangeData.session) {
    return NextResponse.json(
      {
        error:
          exchangeError?.message ??
          'The reset link is invalid or has expired. Please request a new one.',
      },
      { status: 400 }
    );
  }

  const { error: updateError } = await supabase.auth.updateUser({ password });

  if (updateError) {
    // We already wrote cookies on the successResponse during the
    // exchange step above, but we're returning a different response
    // for the error case — those orphaned cookie writes go nowhere,
    // so the browser ends up with no session, which matches what
    // we want when the password update failed. The just-exchanged
    // session is also signed out below to invalidate it server-side.
    await supabase.auth.signOut().catch(() => {
      /* best-effort */
    });
    return NextResponse.json(
      { error: updateError.message ?? 'Failed to update password.' },
      { status: 400 }
    );
  }

  return successResponse;
}
