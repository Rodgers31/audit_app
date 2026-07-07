/**
 * Supabase middleware helper — refreshes the auth session on every request
 * so cookies stay valid and Server Components get an up-to-date session.
 *
 * Also enforces server-side route protection:
 *   - /status, /admin/* → admin role required
 *   - /account/* → authenticated user required
 */
import { createServerClient } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';

/* ───── Routes that require specific roles ───── */
const ADMIN_ROUTES = ['/status', '/admin'];
const AUTH_ROUTES = ['/account'];

function matchesPrefix(pathname: string, prefixes: string[]): boolean {
  return prefixes.some((p) => pathname === p || pathname.startsWith(p + '/'));
}

export async function updateSession(request: NextRequest) {
  const pathname = request.nextUrl.pathname;

  /* ── Fast path: anonymous visitor on a public route ──
   * getUser() costs a network round-trip to Supabase on every request.
   * A visitor with no sb-* auth cookies has no session to refresh, and
   * on a non-protected route there is nothing to guard — skip the
   * Supabase client entirely. This was adding ~0.4–1.0s of TTFB to
   * every public page view. Protected routes still fall through so the
   * unauthenticated redirect below keeps working. */
  const hasAuthCookies = request.cookies
    .getAll()
    .some((cookie) => cookie.name.startsWith('sb-'));
  const isProtectedRoute =
    matchesPrefix(pathname, AUTH_ROUTES) || matchesPrefix(pathname, ADMIN_ROUTES);
  if (!hasAuthCookies && !isProtectedRoute) {
    return NextResponse.next({ request });
  }

  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  // Refresh the session — IMPORTANT: don't remove this
  const {
    data: { user },
  } = await supabase.auth.getUser();

  /* ── Auth-required routes: redirect unauthenticated users ── */
  if (!user && (matchesPrefix(pathname, AUTH_ROUTES) || matchesPrefix(pathname, ADMIN_ROUTES))) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = '/';
    redirectUrl.searchParams.set('authRequired', '1');
    return NextResponse.redirect(redirectUrl);
  }

  /* ── Admin-required routes: check roles in profiles table ── */
  if (user && matchesPrefix(pathname, ADMIN_ROUTES)) {
    const { data: profile } = await supabase
      .from('profiles')
      .select('roles')
      .eq('id', user.id)
      .maybeSingle();

    const isAdmin = profile?.roles?.includes('admin') ?? false;

    if (!isAdmin) {
      const redirectUrl = request.nextUrl.clone();
      redirectUrl.pathname = '/';
      redirectUrl.searchParams.set('unauthorized', '1');
      return NextResponse.redirect(redirectUrl);
    }
  }

  return supabaseResponse;
}
