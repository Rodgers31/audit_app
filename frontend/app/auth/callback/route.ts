/**
 * /auth/callback – Supabase email-link handler
 *
 * When a user clicks any Supabase-generated email link (password reset,
 * magic-link, email confirmation), Supabase appends a `code` query
 * parameter. This route normally exchanges the code for a session, then
 * redirects to the intended destination.
 *
 * Special case: password recovery
 * -------------------------------
 * For the password-reset flow (``next=/reset-password``) we deliberately
 * DO NOT exchange the code here, AND we forward it under a renamed
 * query parameter so the browser SDK can't auto-exchange it either.
 * Three things conspire to make naive approaches fail, and all three
 * have to be defeated:
 *
 *   1. ``exchangeCodeForSession`` here would create a fresh session
 *      via Set-Cookie. So we skip the server exchange.
 *
 *   2. ``createBrowserClient`` runs with ``detectSessionInUrl: true``
 *      and ``flowType: 'pkce'`` (set by @supabase/ssr defaults). On
 *      every page load the SDK's ``_initialize()`` checks
 *      ``_isPKCECallback(params)`` — which returns true if there is
 *      both a ``?code=`` URL param AND a ``-code-verifier`` cookie.
 *      When it returns true the SDK fires
 *      ``_exchangeCodeForSession`` itself, from the browser, ending
 *      up exactly where we started: a fresh session created behind
 *      our back. The user reported the matching
 *      ``POST /auth/v1/token?grant_type=pkce`` showing up in their
 *      Network panel. To bypass this we forward the code under the
 *      query parameter name ``recovery`` instead of ``code``. The
 *      SDK looks for ``code`` specifically; ``recovery`` is invisible
 *      to it. The page reads ``recovery`` and POSTs it as ``code``
 *      to /api/auth/reset-password where the server-side
 *      ``createServerClient`` runs with ``detectSessionInUrl: false``
 *      and won't auto-exchange.
 *
 *   3. The user might already be signed in from an unrelated prior
 *      login on this device. ``AuthProvider``'s ``getSession()``
 *      restores that session from cookies regardless of the URL.
 *      We clear those session cookies (auth-token + chunked
 *      variants) directly here. The clear regex is tight enough to
 *      leave the ``-code-verifier`` cookie alone — it's needed by
 *      the form-submit exchange:
 *
 *          /-auth-token(\.\d+)?$/
 *
 *      Matches ``sb-<ref>-auth-token`` / ``…auth-token.0`` / ``.1``
 *      etc. but NOT ``sb-<ref>-auth-token-code-verifier``.
 *
 * Other flows (email confirmation, magic-link sign-in) keep the
 * existing exchange-and-redirect behaviour because they DO want a
 * session to be established.
 */
import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { createClient } from '@/lib/supabase/server';

// Matches ``sb-<anything>-auth-token`` and chunked variants
// ``sb-<anything>-auth-token.0`` / ``.1`` / ... but explicitly NOT
// ``sb-<anything>-auth-token-code-verifier``. See the file-level
// comment for why this distinction matters.
const SESSION_COOKIE_TAIL = /-auth-token(\.\d+)?$/;

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);

  const code = searchParams.get('code');
  const next = searchParams.get('next') ?? '/';

  // Server log so anyone running ``npm run dev`` can verify which
  // branch this handler took. The "stuck on the old behaviour"
  // reports we kept getting were almost always "the dev server is
  // serving stale code"; this log makes that immediately obvious.
  // eslint-disable-next-line no-console
  console.log(
    `[auth/callback] hit — code=${code ? 'present' : 'missing'} next=${next}`
  );

  if (code) {
    // Recovery flow: forward the code without creating a new session,
    // AND clear any pre-existing session-cookie chunks so AuthProvider
    // doesn't restore a stale session on /reset-password mount. The
    // code-verifier cookie is intentionally left alone — the
    // form-submit exchange in /api/auth/reset-password needs it.
    if (next === '/reset-password') {
      // CRITICAL: forward the code under a renamed query param.
      // ``?code=`` would be auto-exchanged by the browser SDK on
      // page mount (see file-level comment); ``?recovery=`` is
      // invisible to the SDK's PKCE-callback detection.
      const response = NextResponse.redirect(
        `${origin}/reset-password?recovery=${encodeURIComponent(code)}`
      );

      const cookieStore = await cookies();
      const cleared: string[] = [];
      cookieStore.getAll().forEach(({ name }) => {
        if (name.startsWith('sb-') && SESSION_COOKIE_TAIL.test(name)) {
          // Set with empty value + maxAge 0 to delete. Path must
          // match the path the cookie was originally set with
          // (DEFAULT_COOKIE_OPTIONS in @supabase/ssr uses '/').
          response.cookies.set(name, '', {
            maxAge: 0,
            path: '/',
            sameSite: 'lax',
          });
          cleared.push(name);
        }
      });

      // eslint-disable-next-line no-console
      console.log(
        `[auth/callback] recovery flow: forwarding code, cleared ${cleared.length} session cookie(s)${
          cleared.length ? ' [' + cleared.join(', ') + ']' : ''
        }`
      );
      return response;
    }

    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);

    if (!error) {
      // Successfully exchanged — redirect to the intended page
      return NextResponse.redirect(`${origin}${next}`);
    }
  }

  // If code is missing or exchange failed, send user to an error page
  return NextResponse.redirect(
    `${origin}/reset-password?error=${encodeURIComponent(
      'The reset link is invalid or has expired. Please request a new one.'
    )}`
  );
}
