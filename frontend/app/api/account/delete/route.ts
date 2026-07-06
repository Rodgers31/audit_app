/**
 * DELETE /api/account/delete
 *
 * Permanently deletes the authenticated user's account.
 * Uses the Supabase service-role key (server-side only) to call
 * auth.admin.deleteUser(), which cascades to remove
 * the profiles row, watchlist entries, and alerts via FK constraints.
 */
import { createServerClient } from '@supabase/ssr';
import { createClient } from '@supabase/supabase-js';
import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

export async function DELETE() {
  /* ── 1. Authenticate the caller via their session cookie ── */
  const cookieStore = await cookies();

  const supabaseUser = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => cookieStore.getAll(),
        setAll: (c) => {
          try {
            c.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
          } catch {
            /* ignore in Server Component context */
          }
        },
      },
    }
  );

  const {
    data: { user },
  } = await supabaseUser.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }

  /* ── 2. Delete user-owned data first (profiles, watchlist, alerts) ── */
  // FK CASCADE should handle most of it, but be explicit for safety
  const admin = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { autoRefreshToken: false, persistSession: false } }
  );

  // Best-effort explicit cleanup (defense-in-depth). supabase-js returns
  // { error } instead of throwing, so capture it. deleteUser() below is the
  // authoritative step and cascades via ON DELETE CASCADE FKs, so we log any
  // failures here but do NOT abort — a transient cleanup error must not block
  // the user's deletion request.
  const cleanup = await Promise.all([
    admin.from('watchlist_items').delete().eq('user_id', user.id),
    admin.from('data_alerts').delete().eq('user_id', user.id),
    admin.from('profiles').delete().eq('id', user.id),
  ]);
  for (const { error: cleanupError } of cleanup) {
    if (cleanupError) console.warn('[delete-account] cleanup:', cleanupError.message);
  }

  /* ── 3. Delete the auth user (authoritative; cascades to dependent rows) ── */
  const { error } = await admin.auth.admin.deleteUser(user.id);

  if (error) {
    console.error('[delete-account]', error.message);
    return NextResponse.json({ error: 'Failed to delete account' }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
}
