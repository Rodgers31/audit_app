import { count, object, text, timestamp } from './audit';
export function decodeIngestion(value: unknown) {
  const o = object(value);
  const total_jobs = count(o.total_jobs), completed = count(o.completed), failed = count(o.failed), running = count(o.running), pending = count(o.pending), completed_with_errors = count(o.completed_with_errors);
  const domains = Object.fromEntries(Object.entries(object(o.domains)).map(([key, value]) => [text(key, 80), count(value)]));
  if (completed + failed + running + pending + completed_with_errors !== total_jobs || Object.values(domains).reduce((a, b) => a + b, 0) !== total_jobs) throw new Error('Invalid ingestion totals');
  return { total_jobs, completed, failed, running, pending, completed_with_errors, domains,
    total_items_processed: count(o.total_items_processed), total_items_created: count(o.total_items_created), total_items_updated: count(o.total_items_updated) };
}
export function decodeSchedule(value: unknown) {
  const o = object(value), efficiency = object(o.efficiency);
  if (!Array.isArray(o.sources_to_run) || o.sources_to_run.length > 100) throw new Error('Invalid schedule');
  const result = { timestamp: text(o.timestamp, 80), running_today: count(o.running_today), skipping_today: count(o.skipping_today), total_sources: count(o.total_sources), efficiency: { vs_fixed_schedule: text(efficiency.vs_fixed_schedule) },
    sources_to_run: o.sources_to_run.map(v => { const s = object(v); return { source: text(s.source, 80), reason: text(s.reason, 1000) }; }) };
  if (result.running_today + result.skipping_today !== result.total_sources || result.sources_to_run.length !== result.running_today) throw new Error('Invalid schedule counts');
  return result;
}
export function decodeHealth(value: unknown) {
  const o = object(value);
  const scheduler_status = text(o.scheduler_status, 1000);
  const plan_status = o.plan_status === undefined
    ? scheduler_status === 'healthy' ? 'available' : scheduler_status.startsWith('error:') ? 'unavailable' : 'unverified'
    : text(o.plan_status, 80);
  if (!['available', 'unavailable', 'unverified'].includes(plan_status)) throw new Error('Invalid calendar evidence');
  return { timestamp: text(o.timestamp, 80), scheduler_status, plan_status };
}
export function decodeUsers(value: unknown) {
  const o = object(value);
  const result = { total_users: count(o.total_users), admin_users: count(o.admin_users), new_last_7_days: count(o.new_last_7_days), new_last_30_days: count(o.new_last_30_days) };
  if (result.admin_users > result.total_users || result.new_last_7_days > result.new_last_30_days || result.new_last_30_days > result.total_users) throw new Error('Invalid profile counts');
  return result;
}
export function decodeFailures(value: unknown) {
  const o = object(value);
  if (!Array.isArray(o.jobs) || o.jobs.length > 5 || typeof o.has_more !== 'boolean') throw new Error('Invalid failure evidence');
  const total = count(o.total);
  if (o.page !== 1 || o.page_size !== 5 || o.jobs.length !== Math.min(5, total) || o.has_more !== (total > 5)) throw new Error('Invalid failure count');
  if (new Set(o.jobs.map(v => count(object(v).id))).size !== o.jobs.length) throw new Error('Invalid failure rows');
  return { total, jobs: o.jobs.map(v => {
    const j = object(v);
    if (j.status !== 'failed' || count(j.id) < 1) throw new Error('Invalid failure row');
    const duration = j.duration_seconds;
    if (duration !== null && (typeof duration !== 'number' || !Number.isFinite(duration) || duration < 0)) throw new Error('Invalid duration');
    // Error bodies may include SQL/provider credentials. Detail page owns its
    // diagnostic boundary; the overview only needs status and drill-down ID.
    return { id: count(j.id), domain: text(j.domain, 80), created_at: text(j.created_at, 80), started_at: j.started_at === null ? null : text(j.started_at, 80), duration_seconds: duration as number | null };
  }) };
}
export function decodeSocial(value: unknown) {
  const o = object(value), w = object(o.worker);
  if (typeof o.publishing_enabled !== 'boolean') throw new Error('Invalid publishing state');
  const queue_counts = Object.fromEntries(Object.entries(object(o.queue_counts)).map(([k, v]) => [text(k, 80), count(v)]));
  if (!Number.isSafeInteger(Object.values(queue_counts).reduce((a, b) => a + b, 0))) throw new Error('Invalid delivery total');
  return { publishing_enabled: o.publishing_enabled, worker: { state: text(w.state, 80), heartbeat_at: w.heartbeat_at === null ? null : text(w.heartbeat_at, 80), last_scan_at: w.last_scan_at === null ? null : text(w.last_scan_at, 80) },
    queue_counts };
}
export function socialWorkerEvidence(worker: ReturnType<typeof decodeSocial>['worker']): string {
  const heart = timestamp(worker.heartbeat_at), scan = timestamp(worker.last_scan_at);
  const limit = worker.state === 'active' ? 45_000 : 150_000;
  if (heart === null || heart > Date.now() + 5000) return 'unavailable';
  if (!['active', 'idle', 'stopped'].includes(worker.state)) return ['stale', 'unavailable'].includes(worker.state) ? worker.state : 'unavailable';
  if (Date.now() - heart > limit) return 'stale';
  if (worker.state !== 'stopped' && (scan === null || scan > Date.now() + 5000)) return 'unavailable';
  if (scan !== null && Date.now() - scan > limit) return 'stale';
  return worker.state;
}
