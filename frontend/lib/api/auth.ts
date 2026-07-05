/**
 * User-features data access via Supabase client.
 *
 * Auth is handled by the AuthProvider (supabase.auth).
 * Watchlist, alerts, and newsletter hit Supabase Postgres directly
 * (protected by RLS policies keyed on auth.uid()).
 */
import { createClient } from '@/lib/supabase/client';

const supabase = createClient();

/* ───── Types ───── */
export interface UserProfile {
  id: string;
  email: string;
  display_name: string | null;
  roles: string[];
}

export interface WatchlistItem {
  id: number;
  user_id: string;
  item_type: 'county' | 'national_category' | 'budget_programme';
  item_id: string;
  label: string;
  notify: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface DataAlert {
  id: number;
  user_id: string;
  alert_type: string;
  title: string;
  body: string | null;
  item_type: string | null;
  item_id: string | null;
  read: boolean;
  created_at: string;
}

/* ───── Profile ───── */
export async function updateProfile(displayName: string): Promise<UserProfile> {
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error('Not authenticated');

  const { data, error } = await supabase
    .from('profiles')
    .update({ display_name: displayName })
    .eq('id', user.id)
    .select('id, email, display_name, roles')
    .single();

  if (error) throw error;
  return data as UserProfile;
}

/* ───── Watchlist ───── */
export async function getWatchlist(): Promise<WatchlistItem[]> {
  const { data, error } = await supabase
    .from('watchlist_items')
    .select('*')
    .order('created_at', { ascending: false });

  if (error) throw error;
  return (data ?? []) as WatchlistItem[];
}

export async function addWatchlistItem(payload: {
  item_type: WatchlistItem['item_type'];
  item_id: string;
  label: string;
  notify?: boolean;
}): Promise<WatchlistItem> {
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error('Not authenticated');

  const { data, error } = await supabase
    .from('watchlist_items')
    .insert({
      user_id: user.id,
      item_type: payload.item_type,
      item_id: payload.item_id,
      label: payload.label,
      notify: payload.notify ?? true,
    })
    .select()
    .single();

  if (error) {
    // Unique constraint violation → already watching
    if (error.code === '23505') {
      const existing = await supabase
        .from('watchlist_items')
        .select('*')
        .eq('user_id', user.id)
        .eq('item_type', payload.item_type)
        .eq('item_id', payload.item_id)
        .single();
      if (existing.data) return existing.data as WatchlistItem;
    }
    throw error;
  }
  return data as WatchlistItem;
}

export async function removeWatchlistItem(id: number): Promise<void> {
  const { error } = await supabase.from('watchlist_items').delete().eq('id', id);
  if (error) throw error;
}

/* ───── Alerts ───── */
export async function getAlerts(unreadOnly = false): Promise<DataAlert[]> {
  let query = supabase
    .from('data_alerts')
    .select('*')
    .order('created_at', { ascending: false })
    .limit(50);

  if (unreadOnly) {
    query = query.eq('read', false);
  }

  const { data, error } = await query;
  if (error) throw error;
  return (data ?? []) as DataAlert[];
}

export async function markAlertRead(id: number): Promise<void> {
  const { error } = await supabase.from('data_alerts').update({ read: true }).eq('id', id);
  if (error) throw error;
}

export async function markAllAlertsRead(): Promise<void> {
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error('Not authenticated');

  const { error } = await supabase
    .from('data_alerts')
    .update({ read: true })
    .eq('user_id', user.id)
    .eq('read', false);

  if (error) throw error;
}

/* ───── Newsletter ───── */
// Routed through the FastAPI backend (POST /api/v1/newsletter/*) rather than
// hitting Supabase directly. The backend runs as the postgres role, so
// newsletter_subscribers can keep RLS locked down (no anon table access) —
// see migration i9d0e1f2a3b4_lock_down_newsletter_subscribers.
export async function subscribeNewsletter(
  email: string
): Promise<{ status: 'subscribed' | 'resubscribed' | 'already_subscribed'; email: string }> {
  const { apiClient } = await import('@/lib/api/axios');
  const { data } = await apiClient.post('/newsletter/subscribe', { email });

  // Validate at runtime — a 2xx with an unexpected body (proxy/HTML page,
  // gateway error, contract drift, empty body) must not be laundered into a
  // "valid" status by a type assertion. Narrowing from `unknown` also drops
  // the unsafe `as`. Throwing routes to the caller's existing error handling.
  const status: unknown = data?.status;
  if (
    status !== 'subscribed' &&
    status !== 'resubscribed' &&
    status !== 'already_subscribed'
  ) {
    throw new Error(`Unexpected newsletter subscribe response: ${JSON.stringify(status)}`);
  }

  // Fire-and-forget welcome email for new / returning subscribers
  if (status === 'subscribed' || status === 'resubscribed') {
    _sendWelcomeEmail(email);
  }

  return { status, email };
}

/**
 * Trigger the backend to send a welcome email.
 * Best-effort — never blocks or throws on failure.
 */
async function _sendWelcomeEmail(email: string): Promise<void> {
  try {
    const { apiClient } = await import('@/lib/api/axios');
    await apiClient.post('/newsletter/send-welcome', { email });
  } catch {
    // Intentionally swallowed — welcome email is non-critical
  }
}

export async function unsubscribeNewsletter(
  email: string
): Promise<{ status: 'unsubscribed' | 'not_found' }> {
  const { apiClient } = await import('@/lib/api/axios');
  const { data } = await apiClient.post('/newsletter/unsubscribe', { email });

  // Same guard as subscribe: don't let an unexpected 2xx body masquerade as a
  // successful unsubscribe (the old `?? 'unsubscribed'` silently claimed success).
  const status: unknown = data?.status;
  if (status !== 'unsubscribed' && status !== 'not_found') {
    throw new Error(`Unexpected newsletter unsubscribe response: ${JSON.stringify(status)}`);
  }

  return { status };
}
