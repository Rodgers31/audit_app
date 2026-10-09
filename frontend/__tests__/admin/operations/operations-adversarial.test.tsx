import React, { Suspense } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import api from '@/lib/api/axios';
import Ingestion from '@/app/admin/ingestion/page';
import Detail from '@/app/admin/ingestion/[jobId]/page';
import Etl from '@/app/admin/etl/page';
import { ingestionFilters, integer, parseIngestionJob, parseIngestionList } from '@/lib/admin/ingestion';
import { ETL_SOURCES, parseEtlHealth, parseSchedule } from '@/lib/admin/etl';

let mockQuery = '';
let mockAdmin = true;
let mockLoading = false;
let mockActor: string | null = 'inert-adversarial-admin';
const mockReplace = jest.fn();
const mockPush = jest.fn();
jest.mock('next/navigation', () => ({ useRouter: () => ({ replace: mockReplace, push: mockPush }), useSearchParams: () => new URLSearchParams(mockQuery) }));
jest.mock('@/components/layout/PageShell', () => ({ __esModule: true, default: ({ title, subtitle, children }: any) => <main><h1>{title}</h1><p>{subtitle}</p>{children}</main> }));
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: mockAdmin, isLoading: mockLoading }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: mockActor ? { id: mockActor } : null }) }));
const get = api.get as jest.Mock;
const post = api.post as jest.Mock;
const timestamp = '2026-10-08T12:00:00Z';
const job = { id: 1, domain: 'audits', status: 'completed', dry_run: true, started_at: timestamp,
  finished_at: timestamp, duration_seconds: 0, items_processed: 3, items_created: 2, items_updated: 1,
  errors: [], error_count: 0, metadata: {}, diagnostics_redacted: true, created_at: timestamp };
const list = { jobs: [job], total: 1, page: 1, page_size: 20, has_more: false };
const manual = { available: false, reason: 'Dedicated dispatch unavailable. No job was accepted.' };
const plan = { timestamp, evidence: 'calendar_plan', manual_trigger: manual, summary: { sources_running_today: 1,
  sources_skipping_today: 5, total_sources: 6, skip_percentage: 83.3, efficiency_vs_fixed_schedule: '92% fewer planned checks',
  sources_to_run: [{ source: 'oag', reason: 'Synthetic plan' }], sources_not_running: ETL_SOURCES.filter(source=>source!=='oag') },
  sources: Object.fromEntries(ETL_SOURCES.map(source=>[source,{should_run:source==='oag', should_run_now:source==='oag',
    reason:source==='oag'?'Synthetic plan':`${source} deferred`, next_run:null, next_reason:'Next', current_period:'default'}])) };
const health = { timestamp, scheduler_status: 'unverified', plan_status: 'available', worker_status: 'unverified', data_freshness: 'unverified', manual_trigger: manual };

function mount(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrap = (child: React.ReactNode) => <QueryClientProvider client={qc}>{child}</QueryClientProvider>;
  const result = render(wrap(node));
  return { qc, ...result, rerenderNode: (child: React.ReactNode) => result.rerender(wrap(child)) };
}
async function mountDetail(id: string) {
  const params = Promise.resolve({ jobId: id });
  let mounted!: ReturnType<typeof mount>;
  await act(async () => { mounted = mount(<Suspense fallback={<p>Awaiting detail</p>}><Detail params={params} /></Suspense>); });
  return mounted;
}
function visibility(value: 'hidden' | 'visible') {
  Object.defineProperty(document, 'visibilityState', { configurable: true, value });
  act(() => document.dispatchEvent(new Event('visibilitychange')));
}
beforeEach(() => {
  jest.clearAllMocks(); mockQuery = ''; mockAdmin = true; mockLoading = false; mockActor = 'inert-adversarial-admin';
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
});
afterEach(() => jest.useRealTimers());

test('all numeric guards reject NaN, infinities, booleans, null, strings, negatives and unsafe integers', () => {
  const hostile = [NaN, Infinity, -Infinity, true, false, null, undefined, '', '1', -1, Number.MAX_SAFE_INTEGER + 1];
  for (const value of hostile) {
    expect(() => integer(value)).toThrow();
    for (const key of ['id', 'items_processed', 'items_created', 'items_updated', 'error_count']) expect(() => parseIngestionJob({ ...job, [key]: value })).toThrow();
    for (const key of ['total', 'page', 'page_size']) expect(() => parseIngestionList({ ...list, [key]: value }, { page: 1, page_size: 20 })).toThrow();
  }
  expect(() => parseIngestionJob({ ...job, id: 0 })).toThrow();
});

test('absent, primitive, empty, unknown or contradictory job and page shapes fail closed', () => {
  for (const raw of [null, undefined, [], {}, true, '', 1]) {
    expect(() => parseIngestionJob(raw)).toThrow();
    expect(() => parseIngestionList(raw, { page: 1, page_size: 20 })).toThrow();
    expect(() => parseSchedule(raw)).toThrow();
    expect(() => parseEtlHealth(raw)).toThrow();
  }
  for (const mutation of [ { status: 'queued' }, { status: 'healthy' }, { dry_run: 1 }, { diagnostics_redacted: false },
    { diagnostics_redacted: 'true' }, { duration_seconds: NaN }, { duration_seconds: Infinity }, { duration_seconds: -1 },
    { errors: {} }, { errors: [false] }, { errors: ['secret'], error_count: 0 }, { errors: [], error_count: 1 },
    { metadata: [] }, { domain: '../../private' }, { finished_at: false }, { started_at: '' } ]) {
    expect(() => parseIngestionJob({ ...job, ...mutation })).toThrow();
  }
  for (const mutation of [ { page: 2 }, { page_size: 10 }, { has_more: true }, { has_more: 'false' },
    { jobs: [] }, { jobs: [job, job], total: 2 }, { total: 0 }, { jobs: {} } ]) {
    expect(() => parseIngestionList({ ...list, ...mutation }, { page: 1, page_size: 20 })).toThrow();
  }
});

test('redaction never transfers attacker strings or arbitrary metadata into the parsed job', () => {
  const raw = { ...job, status: 'failed', error_count: 7, errors: ['PRIVATE_ERROR'], metadata: {
    token: 'PRIVATE_TOKEN', nested: { credentials: 'PRIVATE' }, source_mode: 'fixture', manual_trigger: true,
    dropped_by_global_budget: false, dry_run: true, since: timestamp,
  } };
  const parsed = parseIngestionJob(raw);
  expect(JSON.stringify(parsed)).not.toMatch(/PRIVATE/);
  expect(parsed.error_count).toBe(7);
  expect(parsed.errors).toHaveLength(1);
  expect(parsed.metadata).toEqual({ source_mode: 'fixture', manual_trigger: true, dropped_by_global_budget: false, dry_run: true, since: timestamp });
});

test('hostile and duplicated URL parameters become canonical bounded values', () => {
  for (const raw of ['NaN', 'Infinity', '-Infinity', 'true', '-1', '0', '1.2', '999999999999999999999']) {
    expect(ingestionFilters(new URLSearchParams(`page=${raw}&days=${raw}`))).toMatchObject({ page: 1, days: 7 });
  }
  expect(ingestionFilters(new URLSearchParams('page=2&page=999&days=0009&status=FAILED&domain=audits'))).toMatchObject({ page: 2, days: 9, status: 'failed', domain: 'audits' });
});

test('calendar summaries reject false execution evidence, hostile counts and contradictory identities', () => {
  for (const value of [NaN, Infinity, -Infinity, true, false, -1, null, '1']) {
    for (const key of ['sources_running_today', 'sources_skipping_today', 'total_sources', 'skip_percentage']) expect(() => parseSchedule({ ...plan, summary: { ...plan.summary, [key]: value } })).toThrow();
  }
  expect(() => parseSchedule({ ...plan, evidence: 'running' })).toThrow();
  expect(() => parseSchedule({ ...plan, sources: {} })).toThrow();
  expect(() => parseSchedule({ ...plan, sources: { unknown: plan.sources.oag } })).toThrow();
  expect(() => parseSchedule({ ...plan, sources: { oag: { ...plan.sources.oag, should_run_now: false } } })).toThrow();
  expect(() => parseSchedule({ ...plan, summary: { ...plan.summary, sources_to_run: [{ source: 'cob', reason: 'Synthetic plan' }] } })).toThrow();
  for (const key of ['scheduler_status', 'worker_status', 'data_freshness']) expect(() => parseEtlHealth({ ...health, [key]: 'healthy' })).toThrow();
});

test('health rejects array and object plan statuses instead of coercing their identities', () => {
  for (const plan_status of [['available'], ['unavailable'], { toString: () => 'available' }]) {
    expect(() => parseEtlHealth({ ...health, plan_status })).toThrow();
  }
});

test('nonadmins and auth-loading observers make no operational reads', async () => {
  mockAdmin = false; mockLoading = true; get.mockResolvedValue({ data: list });
  const mounted = mount(<Ingestion />);
  expect(screen.getByText('Verifying access…')).toBeInTheDocument();
  await act(async () => {});
  expect(get).not.toHaveBeenCalled();
  mockLoading = false; mounted.rerenderNode(<Ingestion />);
  expect(screen.getByText('Admin access required.')).toBeInTheDocument();
  expect(get).not.toHaveBeenCalled();
});

test('an admin revocation removes visible data and cached operational responses', async () => {
  get.mockResolvedValue({ data: list }); const mounted = mount(<Ingestion />);
  await screen.findAllByText('audits');
  expect(mounted.qc.getQueryCache().getAll()).toHaveLength(1);
  mockAdmin = false; mounted.rerenderNode(<Ingestion />);
  expect(screen.getByText('Admin access required.')).toBeInTheDocument();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  expect(mounted.qc.getQueryCache().getAll().every(query => query.state.data === undefined)).toBe(true);
});

test('actor changes abort the old read and a late old response cannot replace new actor data', async () => {
  let resolveOld!: (value: unknown) => void;
  let oldSignal!: AbortSignal;
  get.mockImplementationOnce((_path, options) => {
    oldSignal = options.signal;
    return new Promise(resolve => { resolveOld = resolve; });
  }).mockResolvedValue({ data: { ...list, jobs: [{ ...job, domain: 'new_actor_data' }] } });
  const mounted = mount(<Ingestion />);
  await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
  mockActor = 'inert-second-admin'; mounted.rerenderNode(<Ingestion />);
  await screen.findAllByText('new_actor_data');
  expect(oldSignal.aborted).toBe(true);
  await act(async () => resolveOld({ data: { ...list, jobs: [{ ...job, domain: 'OLD_ACTOR_PRIVATE' }] } }));
  expect(screen.queryByText('OLD_ACTOR_PRIVATE')).not.toBeInTheDocument();
  expect(mounted.qc.getQueriesData({ queryKey: ['admin', 'ingestion-jobs', 'inert-adversarial-admin'] })).toHaveLength(0);
});

test('visibility changes abort an in-flight read and unmount removes cached responses', async () => {
  let resolve!: (value: unknown) => void;
  let signal!: AbortSignal;
  get.mockImplementationOnce((_path, options) => { signal = options.signal; return new Promise(r => { resolve = r; }); });
  const mounted = mount(<Ingestion />);
  await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
  visibility('hidden'); expect(signal.aborted).toBe(true);
  await act(async () => resolve({ data: list }));
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  mounted.unmount(); expect(mounted.qc.getQueryCache().getAll()).toHaveLength(0);
});

test('hidden list observers cannot bypass the disabled query through Refresh', async () => {
  get.mockResolvedValue({ data: list }); mount(<Ingestion />); await screen.findAllByText('audits');
  visibility('hidden'); fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  await act(async () => {});
  expect(get).toHaveBeenCalledTimes(1);
});

test('a valid empty first page has no table and no next-page action', async () => {
  get.mockResolvedValue({ data: { ...list, jobs: [], total: 0 } }); mount(<Ingestion />);
  await screen.findByText('No jobs match these filters.');
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument();
});

test('detail response identity conflicts fail closed and can recover through Retry', async () => {
  get.mockResolvedValueOnce({ data: { ...job, id: 2 } }).mockResolvedValue({ data: job });
  await mountDetail('1'); await screen.findByText('Could not load job.');
  expect(screen.queryByText('Ingestion job #2')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  await screen.findByText('Ingestion job #1');
});

test('invalid detail route IDs make no API calls', async () => {
  for (const id of ['NaN', '-1', '0', 'true', '2147483648', '1.1', '../1']) {
    const mounted = await mountDetail(id);
    expect(screen.getByRole('heading', { name: 'Invalid job ID' })).toBeInTheDocument();
    mounted.unmount();
  }
  expect(get).not.toHaveBeenCalled();
});

test('detail diagnostic metric preserves the real count after payload redaction', async () => {
  get.mockResolvedValue({ data: { ...job, status: 'failed', error_count: 7, errors: ['PRIVATE_ERROR'] } });
  await mountDetail('1'); await screen.findByRole('heading', { name: 'Errors (7)' });
  const metric = screen.getByText('Errors', { exact: true }).parentElement!;
  expect(within(metric).getByText('7', { exact: true })).toBeInTheDocument();
  expect(screen.queryByText('PRIVATE_ERROR')).not.toBeInTheDocument();
});

test('detail refresh failures hide old counts and raw error details', async () => {
  get.mockResolvedValueOnce({ data: job }).mockRejectedValue({ response: { status: 500, data: { detail: 'PRIVATE_ERROR' } } });
  await mountDetail('1'); await screen.findByText('Ingestion job #1');
  fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  await screen.findByText('Could not load job.');
  expect(screen.queryByText('Items processed')).not.toBeInTheDocument();
  expect(screen.queryByText('PRIVATE_ERROR')).not.toBeInTheDocument();
});

test('hidden detail observers cannot bypass the disabled query through Refresh', async () => {
  get.mockResolvedValue({ data: job }); await mountDetail('1'); await screen.findByText('Ingestion job #1');
  visibility('hidden'); fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  await act(async () => {});
  expect(get).toHaveBeenCalledTimes(1);
});

test('hidden detail error observers cannot bypass the disabled query through Retry', async () => {
  get.mockRejectedValue({ response: { status: 404, data: { detail: 'PRIVATE_ERROR' } } });
  await mountDetail('1'); await screen.findByText('Job not found.');
  expect(screen.queryByText('PRIVATE_ERROR')).not.toBeInTheDocument();
  visibility('hidden'); fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  await act(async () => {});
  expect(get).toHaveBeenCalledTimes(1);
});

test('hidden list error observers cannot bypass the disabled query through Retry', async () => {
  get.mockRejectedValue({ response: { status: 403, data: { detail: 'PRIVATE_ERROR' } } });
  mount(<Ingestion />); await screen.findByText('Could not load jobs.');
  visibility('hidden'); fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  await act(async () => {});
  expect(get).toHaveBeenCalledTimes(1);
});

test('failed active-job polling does not keep polling or display stale successful counts', async () => {
  jest.useFakeTimers();
  get.mockResolvedValueOnce({ data: { ...list, jobs: [{ ...job, status: 'running', finished_at: null, duration_seconds: null }] } })
    .mockRejectedValue({ response: { status: 401, data: { detail: 'PRIVATE_ERROR' } } });
  mount(<Ingestion />); await screen.findAllByText('running');
  await act(async () => { jest.advanceTimersByTime(15_001); });
  await screen.findByText('Could not load jobs.');
  expect(screen.queryByText(/1 job in the last/)).not.toBeInTheDocument();
  expect(screen.queryByText('PRIVATE_ERROR')).not.toBeInTheDocument();
  await act(async () => { jest.advanceTimersByTime(60_000); });
  expect(get).toHaveBeenCalledTimes(2);
});

test('pending detail polls only while visible and stops when the observed record completes', async () => {
  jest.useFakeTimers();
  let state = { ...job, status: 'pending', finished_at: null as string | null, duration_seconds: null as number | null };
  get.mockImplementation(async () => ({ data: state }));
  await mountDetail('1'); await screen.findByText('Awaiting execution');
  await act(async () => { jest.advanceTimersByTime(15_001); });
  expect(get).toHaveBeenCalledTimes(2);
  visibility('hidden');
  await act(async () => { jest.advanceTimersByTime(60_000); });
  expect(get).toHaveBeenCalledTimes(2);
  state = { ...state, status: 'completed', finished_at: timestamp, duration_seconds: 0 };
  visibility('visible'); await screen.findByText('completed');
  const calls = get.mock.calls.length;
  await act(async () => { jest.advanceTimersByTime(60_000); });
  expect(get).toHaveBeenCalledTimes(calls);
});

test('malformed calendar responses recover through the rendered Refresh action', async () => {
  let malformed = true;
  get.mockImplementation(async path => ({ data: malformed ? {} : path.endsWith('/health') ? health : plan }));
  mount(<Etl />); await screen.findByText('Could not load schedule.');
  expect(screen.getByText('Could not load execution evidence.')).toBeInTheDocument();
  malformed = false; fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  await screen.findByText('Synthetic plan');
  expect(screen.queryByText('Could not load execution evidence.')).not.toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: 'Trigger' })).toHaveLength(6);
  expect(screen.getAllByRole('button', { name: 'Dry-run' })).toHaveLength(6);
  screen.getAllByRole('button', { name: 'Trigger' }).forEach(button=>expect(button).toBeDisabled());
  screen.getAllByRole('button', { name: 'Dry-run' }).forEach(button=>expect(button).toBeDisabled());
  expect(post).not.toHaveBeenCalled();
});

test('calendar refresh failures hide old planned counts and never acknowledge execution', async () => {
  let failed = false;
  get.mockImplementation(async path => {
    if (failed) throw { response: { status: 500, data: { detail: 'PRIVATE_ERROR' } } };
    return { data: path.endsWith('/health') ? health : plan };
  });
  mount(<Etl />); await screen.findByText('Synthetic plan');
  failed = true; fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  await screen.findByText('Could not load schedule.');
  expect(screen.queryByText('Synthetic plan')).not.toBeInTheDocument();
  expect(screen.queryByText('1/6')).not.toBeInTheDocument();
  expect(screen.queryByText('PRIVATE_ERROR')).not.toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
});
