/** Runtime contracts for private audit evidence. No arbitrary payload text is rendered. */
export function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid admin evidence');
  return value as Record<string, unknown>;
}
export function count(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new Error('Invalid admin count');
  return value;
}
export function text(value: unknown, max = 255): string {
  if (typeof value !== 'string' || value.length > max) throw new Error('Invalid admin text');
  return value;
}
function nullable(value: unknown, max = 255): string | null { return value === null ? null : text(value, max); }
export function timestamp(value: unknown): number | null {
  if (typeof value !== 'string') return null;
  const parts = /^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)?$/.exec(value);
  if (!parts) return null;
  const [, year, month, day, hour, minute, second] = parts.map(Number);
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  if (month < 1 || month > 12 || day < 1 || day > daysInMonth || hour > 23 || minute > 59 || second > 59) return null;
  const parsed = Date.parse(/(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : value + 'Z');
  return Number.isFinite(parsed) ? parsed : null;
}
export function timeAgo(value: unknown): string {
  const parsed = timestamp(value);
  if (parsed === null) return 'Timestamp unavailable';
  const diff = Date.now() - parsed;
  if (diff < -5000) return 'Timestamp is in the future';
  const mins = Math.floor(Math.max(0, diff) / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`;
  return `${Math.floor(mins / 1440)}d ago`;
}
export function safePayload(action: string, value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return { _redacted: 'Unsupported payload' };
  const payload = value as Record<string, unknown>, result: Record<string, unknown> = {};
  if (action === 'etl.trigger') {
    if (typeof payload.job_id === 'number' && Number.isSafeInteger(payload.job_id) && payload.job_id > 0 && payload.job_id <= 2147483647) result.job_id = payload.job_id;
    if (typeof payload.dry_run === 'boolean') result.dry_run = payload.dry_run;
  } else if (action === 'users.update_roles') {
    for (const key of ['old', 'new']) {
      const roles = payload[key];
      if (Array.isArray(roles) && roles.length <= 20) result[key] = roles.map(r => r === 'admin' || r === 'citizen' ? r : '[redacted role]');
    }
  } else if (action === 'users.delete' || action === 'users.send_reset') {
    const key = action === 'users.delete' ? 'deleted_email' : 'email';
    const email = payload[key];
    if (typeof email === 'string' && email.length <= 255 && /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(email)) result[key] = email;
    if (action === 'users.delete' && typeof payload.deleted_created_at === 'string' && payload.deleted_created_at.length <= 40 && timestamp(payload.deleted_created_at) !== null) result.deleted_created_at = payload.deleted_created_at;
    if (action === 'users.send_reset' && 'redirect_to' in payload) result.redirect_to = payload.redirect_to ? '[redacted]' : null;
  }
  if (Object.keys(payload).some(k => !(k in result))) result._redacted = 'Unsupported fields omitted';
  return result;
}
export interface AuditEntry {
  id: number; actor_id: string; actor_email: string | null; action: string;
  target_type: string | null; target_id: string | null; payload: Record<string, unknown>; created_at: string;
}
export interface AuditList {
  entries: AuditEntry[]; total: number; page: number; page_size: number; has_more: boolean;
  snapshot_id: number; as_of: string; visibility_snapshot: string | null;
}
export function decodeAudit(value: unknown): AuditList {
  const o = object(value);
  if (!Array.isArray(o.entries) || o.entries.length > 100 || typeof o.has_more !== 'boolean') throw new Error('Invalid audit evidence');
  const result = {
    entries: o.entries.map(value => {
      const e = object(value), action = text(e.action, 80);
      return { id: count(e.id), actor_id: text(e.actor_id, 64), actor_email: nullable(e.actor_email), action,
        target_type: nullable(e.target_type, 40), target_id: nullable(e.target_id, 64), payload: safePayload(action, e.payload), created_at: text(e.created_at, 80) };
    }),
    total: count(o.total), page: count(o.page), page_size: count(o.page_size), has_more: o.has_more,
    snapshot_id: count(o.snapshot_id), as_of: text(o.as_of, 80),
    visibility_snapshot: o.visibility_snapshot == null ? null : text(o.visibility_snapshot, 4096),
  };
  const captured = timestamp(result.as_of);
  const expectedRows = Math.min(result.page_size, Math.max(0, result.total - (result.page - 1) * result.page_size));
  if (result.visibility_snapshot !== null && visibilitySnapshot(result.visibility_snapshot) === null) throw new Error('Invalid audit visibility snapshot');
  if (result.page < 1 || result.page > 10000 || result.page_size < 1 || result.page_size > 100 || result.entries.length !== expectedRows || result.has_more !== (result.page * result.page_size < result.total) || captured === null || captured > Date.now() + 5000 || result.snapshot_id > 2147483647 || result.total > result.snapshot_id || result.entries.some(e => e.id < 1 || e.id > result.snapshot_id) || new Set(result.entries.map(e => e.id)).size !== result.entries.length) throw new Error('Invalid audit evidence');
  return result;
}
export const DAYS = [1, 7, 30, 90, 0];
export function visibilitySnapshot(value: unknown): string | null {
  if (typeof value !== 'string' || value.length > 4096 || !/^\d{1,10}:\d{1,10}:(?:\d{1,10}(?:,\d{1,10})*)?$/.test(value)) return null;
  const [lowText, highText, active] = value.split(':');
  const low = Number(lowText), high = Number(highText), ids = active ? active.split(',').map(Number) : [];
  if (low < 3 || low > high || high >= 4294967296 || ids.some((id, index) => id < low || id >= high || (index > 0 && id <= ids[index - 1]))) return null;
  return value;
}
export function auditFilters(params: URLSearchParams) {
  const bounded = (key: string, fallback: number, max: number, min: number) => {
    const raw = params.get(key);
    return raw !== null && /^\d+$/.test(raw) && Number.isSafeInteger(Number(raw)) && Number(raw) >= min && Number(raw) <= max ? Number(raw) : fallback;
  };
  const days = bounded('days', 30, 36500, 0);
  return { actor_id: (params.get('actor_id') ?? '').slice(0, 64), action: (params.get('action') ?? '').slice(0, 80),
    target_type: (params.get('target_type') ?? '').slice(0, 40), target_id: (params.get('target_id') ?? '').slice(0, 64),
    days: DAYS.includes(days) ? days : 30, page: bounded('page', 1, 10000, 1),
    snapshot_id: params.has('snapshot_id') && /^\d+$/.test(params.get('snapshot_id')!) && Number(params.get('snapshot_id')) <= 2147483647 && timestamp(params.get('as_of')) !== null ? Number(params.get('snapshot_id')) : undefined,
    as_of: timestamp(params.get('as_of')) !== null ? params.get('as_of')! : undefined,
    visibility_snapshot: params.has('snapshot_id') && timestamp(params.get('as_of')) !== null ? visibilitySnapshot(params.get('visibility_snapshot')) ?? undefined : undefined };
}
