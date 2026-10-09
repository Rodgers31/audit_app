import { ETL_SOURCES, parseEtlHealth, parseSchedule } from '@/lib/admin/etl';
import { date, parseIngestionJob, parseIngestionList } from '@/lib/admin/ingestion';

const decision = (source: string) => ({ should_run: source === 'oag', should_run_now: source === 'oag',
  reason: `${source} synthetic plan`, next_run: null as string | null, next_reason: 'Synthetic next', current_period: 'default' });

function calendar(names = ETL_SOURCES) {
  const sources = Object.fromEntries(names.map(source => [source, decision(source)]));
  const planned = names.filter(source => sources[source].should_run);
  const skipped = names.filter(source => !sources[source].should_run);
  return { timestamp: '2026-10-08T12:00:00Z', evidence: 'calendar_plan',
    manual_trigger: { available: false, reason: 'No job was accepted.' }, sources,
    summary: { sources_running_today: planned.length, sources_skipping_today: skipped.length,
      total_sources: names.length, skip_percentage: Math.round(skipped.length / names.length * 1000) / 10,
      efficiency_vs_fixed_schedule: 'Synthetic planned checks',
      sources_to_run: planned.map(source => ({ source, reason: sources[source].reason })),
      sources_not_running: skipped } };
}

test('the complete six-source calendar is accepted', () => {
  expect(Object.keys(parseSchedule(calendar()).sources)).toEqual(ETL_SOURCES);
});

test.each(ETL_SOURCES)('a self-consistent calendar missing %s is unavailable', missing => {
  expect(() => parseSchedule(calendar(ETL_SOURCES.filter(source => source !== missing)))).toThrow();
});

test.each(ETL_SOURCES)('a self-consistent one-source %s calendar is unavailable', source => {
  expect(() => parseSchedule(calendar([source]))).toThrow();
});

test.each(['toString', 'constructor', '__proto__', 'hasOwnProperty'])('%s cannot stand in for a skipped source', source => {
  const plan = calendar();
  plan.summary.sources_not_running[0] = source;
  expect(() => parseSchedule(plan)).toThrow();
});

test.each(['toString', 'constructor', '__proto__', 'hasOwnProperty', 'unknown'])('%s cannot stand in for a planned source', source => {
  const plan = calendar();
  plan.summary.sources_to_run[0] = { source, reason: 'Synthetic planned reason' };
  expect(() => parseSchedule(plan)).toThrow();
});

test('duplicate and omitted memberships are unavailable even when counts agree', () => {
  const plan = calendar();
  plan.summary.sources_not_running[0] = plan.summary.sources_not_running[1];
  expect(() => parseSchedule(plan)).toThrow();
});

const timestamp = '2026-10-08T12:00:00Z';
const job = { id: 1, domain: 'audits', status: 'completed', dry_run: true, started_at: timestamp,
  finished_at: timestamp, duration_seconds: 0, items_processed: 3, items_created: 2, items_updated: 1,
  errors: [], error_count: 0, metadata: {}, diagnostics_redacted: true, created_at: timestamp };
const health = { timestamp, scheduler_status: 'unverified', plan_status: 'available', worker_status: 'unverified',
  data_freshness: 'unverified', manual_trigger: { available: false, reason: 'No job was accepted.' } };

test.each(['2026-02-30T00:00:00Z', '2026-02-29T00:00:00Z', '2026-10-08T24:00:00Z',
  '1900-02-29T00:00:00Z', '2100-02-29T00:00:00Z', '2026-04-31T00:00:00Z',
  '0000-01-01T00:00:00Z', '2026-10-08T00:60:00Z', '2026-10-08T00:00:60Z',
  '2026-10-08T00:00:00+24:00', '2026-10-08T00:00:00+00:60', '2026-10-08T12:00Z'])
('impossible or unsupported timestamp %s cannot certify operational evidence', timestamp => {
  expect(() => date(timestamp)).toThrow();
  expect(() => parseEtlHealth({ ...health, timestamp })).toThrow();
  expect(() => parseSchedule({ ...calendar(), timestamp })).toThrow();
  const next = calendar();
  next.sources.oag.next_run = timestamp;
  expect(() => parseSchedule(next)).toThrow();
  for (const key of ['started_at', 'finished_at', 'created_at']) {
    expect(() => parseIngestionJob({ ...job, [key]: timestamp })).toThrow();
  }
  expect(() => parseIngestionJob({ ...job, metadata: { since: timestamp } })).toThrow();
  expect(() => parseIngestionList({ jobs: [{ ...job, started_at: timestamp }], total: 1,
    page: 1, page_size: 20, has_more: false }, { page: 1, page_size: 20 })).toThrow();
});

test.each(['2024-02-29T00:00:00Z', '2000-02-29T23:59:59.999999+03:00',
  '2026-10-08T23:59:59-07:00', '2026-10-08T00:00:00+23:59', '2026-10-08T00:00:00',
  '0001-01-01T00:00:00Z'])('valid leap, bounded offset and naive timestamp %s remains supported', timestamp => {
  expect(date(timestamp)).toBe(timestamp);
  expect(parseEtlHealth({ ...health, timestamp }).timestamp).toBe(timestamp);
  expect(parseSchedule({ ...calendar(), timestamp }).timestamp).toBe(timestamp);
});
