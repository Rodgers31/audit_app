import { auditFilters, decodeAudit, safePayload, timeAgo, timestamp } from '@/lib/admin/audit';
import { decodeFailures, decodeIngestion, decodeSocial, decodeUsers, socialWorkerEvidence } from '@/lib/admin/overview';
const audit = { entries: [], total: 0, page: 1, page_size: 25, has_more: false, snapshot_id: 0, as_of: '2026-10-08T00:00:00Z' };

test('impossible calendar dates never certify fresh worker evidence', () => {
  jest.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-03-02T00:00:00Z'));
  try {
    expect(timestamp('2026-02-30T00:00:00Z')).toBeNull();
    expect(socialWorkerEvidence({ state: 'active', heartbeat_at: '2026-02-30T00:00:00Z', last_scan_at: '2026-02-30T00:00:00Z' })).toBe('unavailable');
  } finally { jest.restoreAllMocks(); }
});

test('missing rows cannot certify empty evidence with nonzero totals', () => {
  expect(() => decodeAudit({ ...audit, total: 25, snapshot_id: 25 })).toThrow();
  expect(() => decodeFailures({ jobs: [], total: 25, has_more: false, page: 1, page_size: 5 })).toThrow();
});

test('frontend snapshot bounds match API and reject future capture time', () => {
  expect(() => decodeAudit({ ...audit, snapshot_id: 2147483648 })).toThrow();
  expect(() => decodeAudit({ ...audit, as_of: '9999-01-01T00:00:00Z' })).toThrow();
});

test.each(['3:2:', '2:4:', '3:4294967296:', '3:9:8,4', '3:9:4,4', '3:9:2', '3:9:9'])('visibility snapshot schema agrees with API: %s', value => {
  expect(() => decodeAudit({ ...audit, visibility_snapshot: value })).toThrow();
});

test.each(['NaN', '2147483648'])('invalid snapshot ID %s cannot send orphan visibility evidence', value => {
  expect(auditFilters(new URLSearchParams(`snapshot_id=${value}&as_of=2026-10-08T00%3A00%3A00Z&visibility_snapshot=3%3A9%3A`))).toMatchObject({
    snapshot_id: undefined, as_of: undefined, visibility_snapshot: undefined,
  });
});

test.each([null, true, false, -1, NaN, Infinity, '1', {}, []])('hostile user/ingestion counts are rejected: %s', value => {
  expect(() => decodeUsers({ total_users: value, admin_users: 0, new_last_7_days: 0, new_last_30_days: 0 })).toThrow();
  expect(() => decodeIngestion({ total_jobs: value })).toThrow();
});

test('time, URL and payload boundaries are bounded and inert', () => {
  expect(timeAgo('garbage')).toBe('Timestamp unavailable');
  expect(timeAgo('9999-01-01T00:00:00Z')).toBe('Timestamp is in the future');
  expect(auditFilters(new URLSearchParams('page=NaN&days=-1&action=' + 'x'.repeat(100)))).toMatchObject({ page: 1, days: 30, action: 'x'.repeat(80) });
  expect(JSON.stringify(safePayload('users.send_reset', { email: 'inert@example.invalid', redirect_to: 'https://example.invalid/INERT_SECRET', nested: { token: 'INERT_SECRET' } }))).not.toContain('INERT_SECRET');
  expect(safePayload('unknown.action', { anything: 'INERT_SECRET' })).toEqual({ _redacted: 'Unsupported fields omitted' });
});

test('social worker statuses require present fresh heartbeat and scan', () => {
  const now = new Date().toISOString(), old = new Date(Date.now() - 300_000).toISOString();
  expect(socialWorkerEvidence({ state: 'active', heartbeat_at: now, last_scan_at: now })).toBe('active');
  expect(socialWorkerEvidence({ state: 'active', heartbeat_at: now, last_scan_at: null })).toBe('unavailable');
  expect(socialWorkerEvidence({ state: 'idle', heartbeat_at: old, last_scan_at: old })).toBe('stale');
  expect(() => decodeSocial({ publishing_enabled: 'false', worker: {} })).toThrow();
});
