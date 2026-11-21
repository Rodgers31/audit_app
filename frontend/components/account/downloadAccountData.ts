import { getApiBase } from '@/lib/api/base';
import { createClient } from '@/lib/supabase/client';

export async function downloadAccountData(accountId: string, signal: AbortSignal) {
  const { data: { session }, error } = await createClient().auth.getSession();
  if (error || !session?.access_token || session.user.id !== accountId) {
    throw new Error('Account session is unavailable.');
  }
  signal.throwIfAborted();

  const version = process.env.NEXT_PUBLIC_API_VERSION || 'v1';
  const response = await fetch(`${getApiBase()}/api/${version}/user/export`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    cache: 'no-store',
    credentials: 'omit',
    signal,
  });
  if (!response.ok || !response.headers.get('content-type')?.startsWith('application/json')) {
    throw new Error('Account export is unavailable.');
  }
  const data = await response.json();
  if (data?.profile?.id !== accountId || !Array.isArray(data.watchlist) || !Array.isArray(data.alerts)) {
    throw new Error('Account export did not match the current account.');
  }
  signal.throwIfAborted();

  const file = new Blob([JSON.stringify(data, null, 2) + '\n'], { type: 'application/json' });
  const url = URL.createObjectURL(file);
  const link = document.createElement('a');
  link.href = url;
  link.download = `auditgava-data-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(link);
  try {
    link.click();
  } finally {
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
