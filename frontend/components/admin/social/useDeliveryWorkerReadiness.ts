'use client';
import type { SocialSystemStatus } from '@/lib/api/social';
import { useEffect, useState } from 'react';

/** Immediate delivery needs a current worker report; future scheduling does not. */
export default function useDeliveryWorkerReadiness(worker?: SocialSystemStatus['worker']) {
  const [now, setNow] = useState(() => Date.now());
  const state = worker?.state, heartbeat = worker?.heartbeat_at, scan = worker?.last_scan_at;
  const limit = state === 'active' ? 45_000 : 150_000;
  useEffect(() => {
    const update = () => setNow(Date.now());
    update();
    const expiry = Math.min(...[heartbeat, scan].map(value => value ? Date.parse(value) : NaN)) + limit + 1 - Date.now();
    const timer = Number.isFinite(expiry) && expiry > 0 ? window.setTimeout(update, expiry) : undefined;
    document.addEventListener('visibilitychange', update);
    return () => { if (timer !== undefined) window.clearTimeout(timer); document.removeEventListener('visibilitychange', update); };
  }, [heartbeat, scan, limit]);
  const recent = (value?: string | null) => {
    const age = value ? now - Date.parse(value) : NaN;
    return Number.isFinite(age) && age >= -5_000 && age <= limit;
  };
  if (state === 'stale' || ['active', 'idle'].includes(state ?? '') && (!recent(heartbeat) || !recent(scan))) return 'Delivery worker status is stale or incomplete. Refresh status before immediate publication.';
  if (!['active', 'idle'].includes(state ?? '')) return `Delivery worker is ${state === 'stopped' ? 'stopped' : 'unavailable'}. Immediate publication is unavailable; draft saving and review remain available.`;
  return undefined;
}
