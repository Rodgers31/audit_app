import { parseGenerationOutcome, parseIngestionJob } from '@/lib/admin/ingestion';

const known = { state: 'completed', execution_unverified: false, processed: 1, drafts_created: 0, baselines: 1, unchanged: 0, refused: 0 };
const stamp = '2026-10-16T12:00:00Z';
const job = { id: 1, domain: 'counties_budget', status: 'completed', dry_run: false, started_at: stamp, finished_at: stamp,
  duration_seconds: 0, items_processed: 1, items_created: 1, items_updated: 0, errors: [], error_count: 0,
  diagnostics_redacted: true, created_at: stamp, metadata: { post_commit_generation: known } };

test('operator metadata retains the safe post-commit generation outcome', () => {
  expect(parseIngestionJob(job).metadata.post_commit_generation).toEqual(known);
  expect(parseGenerationOutcome({ ...known, secret: 'PRIVATE_DIAGNOSTIC', reason: 'PRIVATE_DIAGNOSTIC' })).toEqual(known);
});

test('unknown partial effects retain null counters independently from completed ingestion', () => {
  const unknown = { state: 'failed', execution_unverified: true, processed: null, drafts_created: null, baselines: null, unchanged: null, refused: null };
  const parsed = parseIngestionJob({ ...job, metadata: { post_commit_generation: unknown } });
  expect(parsed.status).toBe('completed');
  expect(parsed.metadata.post_commit_generation).toEqual(unknown);
});

test.each([
  { processed: true }, { processed: NaN }, { processed: Infinity }, { processed: -1 }, { processed: 1001 },
  { state: 'unknown' }, { execution_unverified: 'false' }, { refused: 1 }, { baselines: 0 },
  { execution_unverified: true },
])('malformed outcomes never become completed generation: %p', change => {
  expect(() => parseGenerationOutcome({ ...known, ...change })).toThrow();
});


test('financial completion and unknown report execution remain independent', () => {
  const unknown = { state: 'failed', execution_unverified: true, processed: null, drafts_created: null, baselines: null, unchanged: null, refused: null };
  const parsed = parseIngestionJob({ ...job, metadata: { post_commit_generation: known, post_commit_report_generation: unknown } });
  expect(parsed.status).toBe('completed');
  expect(parsed.metadata.post_commit_generation).toEqual(known);
  expect(parsed.metadata.post_commit_report_generation).toEqual(unknown);
});
