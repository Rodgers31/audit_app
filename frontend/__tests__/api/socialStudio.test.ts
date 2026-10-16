import { decodeAnalytics, decodeJob } from '@/lib/api/socialStudio';

const id = '00000000-0000-4000-8000-000000000001';
const sha = 'a'.repeat(64);
const composition = { schema_version: 1, template: 'new_report', template_version: 1, kind: 'video', revision_id: id, title: 'Reviewed report', facts: ['report', 'publisher', 'publication_date'].map(id => ({ id, text: 'Verified report fact', source_url: 'https://example.org/report' })), scenes: ['report', 'publisher', 'publication_date'].map(fact_id => ({ fact_id, seconds: 5 })) };
const job = { id, revision_id: id, state: 'ready', version: 3, composition, input_hash: sha, runtime_hash: sha, sha256: sha, inspection: { sha256: sha, mime_type: 'video/mp4', byte_size: 12345, width: 720, height: 1280, duration_ms: 15000 }, approved_sha256: null, safe_error: null, cancel_requested: false, attempt: 1, retry_of_id: null };
const metric = { name: 'provider_views', api_version: 'fixture-v1', unit: 'count', period: 'day', window_start: '2020-01-01T00:00:00Z', window_end: '2020-01-02T00:00:00Z', collected_at: '2020-01-03T00:00:00Z', available_until: '2020-01-04T00:00:00Z', status: 'available', value: 0, reason: null, freshness: 'fresh' };
const analytics = { target_id: id, platform: 'facebook', availability: 'observed', reason: null, collections: [{ id, state: 'collected', reason: null, remote_id: 'fixture-post', created_at: metric.collected_at, metrics: [metric] }], page: 1, has_more: false };

test('actual ready derivative requires coherent inspection and composition', () => {
  expect(decodeJob(job).sha256).toBe(sha);
  for (const value of [{ ...job, inspection: true }, { ...job, composition: { ...composition, template: 'unknown' } }, { ...job, composition: { ...composition, title: '' } }, { ...job, composition: { ...composition, scenes: [{ fact_id: 'report', seconds: 3 }] } }, { ...job, inspection: { ...job.inspection, sha256: 'b'.repeat(64) } }, { ...job, approved_sha256: 'b'.repeat(64) }]) expect(() => decodeJob(value)).toThrow();
});

test('provider zero stays zero and expired observations become stale', () => {
  const actual = decodeAnalytics(analytics).collections[0].metrics[0];
  expect(actual.value).toBe(0);
  expect(actual.status).toBe('available');
  expect(actual.freshness).toBe('stale');
  const unavailable = decodeAnalytics({ ...analytics, collections: [{ ...analytics.collections[0], metrics: [{ ...metric, status: 'unavailable', value: null, reason: 'permission_missing' }] }] }).collections[0].metrics[0];
  expect(unavailable.value).toBeNull();
  expect(unavailable.reason).toBe('permission_missing');
});

test.each([true, NaN, Infinity, -1, null, '0'])('hostile available metric value %s refuses', value => {
  expect(() => decodeAnalytics({ ...analytics, collections: [{ ...analytics.collections[0], metrics: [{ ...metric, value }] }] })).toThrow();
});
