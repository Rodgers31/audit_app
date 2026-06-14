/**
 * Supabase browser client — true cross-HMR singleton.
 *
 * Use this in Client Components (`'use client'`). Reads public env
 * vars from `.env.local`.
 *
 * Why this is a globalThis-backed singleton
 * -----------------------------------------
 * ``@supabase/ssr``'s own ``createBrowserClient`` already returns a
 * cached instance — but the cache lives in a module-scoped ``let``
 * that gets reset every time the module is re-evaluated. In Next.js
 * dev mode that happens on every HMR cycle, and the previous
 * GoTrueClient instances ARE NOT garbage-collected because their
 * ``setInterval``-based auto-refresh tick keeps a strong reference
 * to them. After a few file saves you accumulate 5-6 live
 * GoTrueClient instances all running ``_autoRefreshTokenTick``
 * concurrently, all competing for the same
 * ``lock:gotrue.<storageKey>`` Web Lock.
 *
 * That queue contention is the actual cause of the duplicate
 * ``PUT /auth/v1/user`` we'd been chasing on /reset-password —
 * confirmed by a diagnostic that captured 6 simultaneous
 * ``navigator.locks.request`` invocations at one timestamp, all
 * from ``_autoRefreshTokenTick`` (PR #93 → PR #94 thread).
 * When ``updateUser`` queues behind enough of those, its 60s
 * ``lockAcquireTimeout`` eventually fires and the SDK
 * "steal-recovers" by re-running the PUT. First call succeeds
 * (password actually changes), second hits the API with the same
 * body and returns ``code: same_password``, user sees a misleading
 * "Lock broken… should be different" error after their password
 * already updated.
 *
 * Stashing the client on ``globalThis`` survives module
 * re-evaluation, so HMR no longer multiplies instances. In
 * production this is a no-op (HMR isn't running), so the only
 * cost is one extra property on the global object.
 *
 * The 60s lockAcquireTimeout (PR #92) stays as defence-in-depth in
 * case a future code path genuinely takes long enough to need
 * recovery — but with one instance the queue will be empty and the
 * timeout shouldn't fire.
 */
import { createBrowserClient } from '@supabase/ssr';
import type { SupabaseClient } from '@supabase/supabase-js';

declare global {
  // eslint-disable-next-line no-var
  var __KPM_SUPABASE_BROWSER_CLIENT__: SupabaseClient | undefined;
}

function build(): SupabaseClient {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      // ``lockAcquireTimeout`` is documented on GoTrueClient (see
      // node_modules/@supabase/auth-js/dist/module/lib/types.d.ts)
      // but ``SupabaseClientOptions['auth']`` only re-exports a
      // subset; cast satisfies the narrower public type. The
      // runtime passes auth options straight through.
      auth: {
        lockAcquireTimeout: 60_000, // 60s (default 5s)
      } as any,
    }
  );
}

export function createClient(): SupabaseClient {
  if (typeof window === 'undefined') {
    // Server-side rendering: never cache; this path is only hit
    // during SSR of Client Components, and each request needs a
    // fresh request-scoped client anyway.
    return build();
  }
  if (!globalThis.__KPM_SUPABASE_BROWSER_CLIENT__) {
    globalThis.__KPM_SUPABASE_BROWSER_CLIENT__ = build();
  }
  return globalThis.__KPM_SUPABASE_BROWSER_CLIENT__;
}
