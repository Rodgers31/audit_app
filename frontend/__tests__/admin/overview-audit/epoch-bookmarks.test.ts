import { auditFilters, visibilitySnapshot } from '@/lib/admin/audit';

const scope = '61100000-0000-4000-8000-000000000001';

test.each([
  `v2:${scope}:4294967294:4294967299:4294967295,4294967297`,
  `v2:${scope}:9007199254740993:9007199254740995:9007199254740994`,
  `v2:${scope}:18446744073709551613:18446744073709551615:18446744073709551614`,
])('durable bookmark transfers without numeric precision loss: %s', value => {
  expect(visibilitySnapshot(value)).toBe(value);
  const params = new URLSearchParams({ snapshot_id: '2', as_of: new Date().toISOString(), visibility_snapshot: value, page: '2' });
  expect(auditFilters(params).visibility_snapshot).toBe(value);
});

test.each([
  `v2:${scope}:3:18446744073709551616:`,
  `v2:${scope}:9007199254740993:9007199254740995:9007199254740994,9007199254740993`,
  `v2:${scope}:3:5:4,4`, `v2:${scope}:3:5:5`,
  `v2:${scope}:٣:٤:`, `v3:${scope}:3:5:`, 'v2:garbage:3:5:',
  `v2:${scope}:3:5:${'4,'.repeat(2100)}`, '4294967296:4294967297:',
])('malformed and unversioned wrapped bookmarks stay unavailable: %s', value => {
  expect(visibilitySnapshot(value)).toBeNull();
  const params = new URLSearchParams({ snapshot_id: '2', as_of: new Date().toISOString(), visibility_snapshot: value });
  expect(auditFilters(params).snapshot_id).toBeUndefined();
});

test('epoch-zero bookmark contract remains available', () => {
  expect(visibilitySnapshot('3:4294967295:4')).toBe('3:4294967295:4');
});
