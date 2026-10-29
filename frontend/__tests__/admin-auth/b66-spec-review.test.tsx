import React, { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AdminLayout from '@/app/admin/layout';
import Overview from '@/app/admin/page';
import Etl from '@/app/admin/etl/page';

let mockPath = '/admin';
let mockAuth: any;
const mockReplace = jest.fn();
const mockRouter = { replace: mockReplace, back: jest.fn() };
const mockGet = jest.fn();
const mockPost = jest.fn();
jest.mock('next/navigation', () => ({
  usePathname: () => mockPath,
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => mockRouter,
}));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => mockAuth }));
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: {
  get: (...args: unknown[]) => mockGet(...args), post: (...args: unknown[]) => mockPost(...args),
} }));
jest.mock('@/lib/supabase/client', () => ({ createClient: () => ({ auth: {
  onAuthStateChange: () => ({ data: { subscription: { unsubscribe() {} } } }),
} }) }));

const actorA = '00000000-0000-4000-8000-000000000001';
const actorB = '00000000-0000-4000-8000-000000000002';
const sources = ['treasury', 'cob', 'oag', 'knbs', 'opendata', 'cra'];
type Pending = { path: string; actor: string; signal: AbortSignal; resolve: (value: any) => void; reject: (error: Error) => void };
let pending: Pending[];
let client: QueryClient;
function verified(id = actorA) {
  return { user: { id, roles: ['admin'] }, authUser: { id }, isAuthenticated: true, isLoading: false };
}
function body(path: string, actor: string): unknown {
  const timestamp = new Date().toISOString();
  const marker = actor === actorA ? 'Only actor A' : 'Only actor B';
  const values: Record<string, unknown> = {
    '/admin/ingestion-jobs/stats/summary': { total_jobs: 1, completed: 0, failed: 1, running: 0, pending: 0, completed_with_errors: 0, domains: { [marker]: 1 }, total_items_processed: 8, total_items_created: 8, total_items_updated: 0 },
    '/admin/etl/schedule/summary': { timestamp, running_today: 0, skipping_today: 6, total_sources: 6, efficiency: { vs_fixed_schedule: 'review fixture' }, sources_to_run: [] },
    '/admin/etl/health': { timestamp, scheduler_status: 'unverified', plan_status: 'unavailable', worker_status: 'unverified', data_freshness: 'unverified', manual_trigger: { available: false, reason: 'review fixture' } },
    '/admin/users/stats': { total_users: 2, admin_users: 1, new_last_7_days: 0, new_last_30_days: 0 },
    '/admin/audit-log': { entries: [], total: 0, page: 1, page_size: 5, has_more: false, snapshot_id: 0, as_of: timestamp },
    '/admin/ingestion-jobs': { jobs: [{ id: 1, domain: marker, status: 'failed', created_at: timestamp, started_at: null, duration_seconds: null }], total: 1, page: 1, page_size: 5, has_more: false },
    '/admin/social/system/status': { publishing_enabled: false, worker: { state: 'unavailable', heartbeat_at: null, last_scan_at: null }, queue_counts: {} },
    '/admin/etl/schedule': { timestamp, evidence: 'calendar_plan', manual_trigger: { available: false, reason: 'review fixture' }, summary: { sources_running_today: 0, sources_skipping_today: 6, total_sources: 6, skip_percentage: 100, efficiency_vs_fixed_schedule: 'review fixture', sources_to_run: [], sources_not_running: sources }, sources: Object.fromEntries(sources.map(name => [name, { should_run: false, reason: marker, next_run: null, next_reason: '', current_period: 'review fixture' }])) },
    '/admin/etl/dispatch': { timestamp, evidence: 'worker_dispatch', available: false, reason: 'review fixture unavailable', generation: null, worker: { status: 'unavailable', last_seen_at: null, expires_at: null }, sources: Object.fromEntries(sources.map(name => [name, { available: false, reason: 'review fixture' }])) },
    '/admin/etl/commands': { entries: [], total: 0, page: 1, page_size: 20, has_more: false },
  };
  if (!(path in values)) throw new Error('Unexpected review fixture read: ' + path);
  return values[path];
}
function tree(etl: boolean) {
  return <StrictMode><QueryClientProvider client={client}><AdminLayout>{etl ? <Etl /> : <Overview />}</AdminLayout></QueryClientProvider></StrictMode>;
}
function painted(element: HTMLElement) {
  for (let current: HTMLElement | null = element; current; current = current.parentElement) {
    expect(current.style.opacity).not.toBe('0');
    expect(current.style.transform).not.toMatch(/translateY\((?!0px)/);
  }
}
async function settle(actor = actorA, rejected = false) {
  await act(async () => {
    pending.filter(item => item.actor === actor).forEach(item => rejected ? item.reject(new Error('Review fixture unavailable')) : item.resolve({ data: body(item.path, actor) }));
  });
}
beforeEach(() => {
  jest.clearAllMocks();
  pending = [];
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false } } });
  mockAuth = verified();
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  mockGet.mockImplementation((path, { signal }) => new Promise((resolve, reject) => pending.push({ path, actor: mockAuth.user.id, signal, resolve, reject })));
  mockPost.mockImplementation(() => { throw new Error('Review fixture write refused'); });
});
afterEach(() => { cleanup(); client.clear(); });

describe.each([false, true])('actual guarded route ETL=%s', etl => {
  beforeEach(() => { mockPath = etl ? '/admin/etl' : '/admin'; });
  test.each(['restoring', 'expired', 'citizen', 'wrong-actor', 'malformed-role'])('%s refuses private rendering and requests', state => {
    if (state === 'restoring') mockAuth = { ...verified(), isLoading: true };
    if (state === 'expired') mockAuth = { ...verified(), isAuthenticated: false };
    if (state === 'citizen') mockAuth = { ...verified(), user: { id: actorA, roles: ['citizen'] } };
    if (state === 'wrong-actor') mockAuth = { ...verified(), authUser: { id: actorB } };
    if (state === 'malformed-role') mockAuth = { ...verified(), user: { id: actorA, roles: 'admin' } };
    render(tree(etl));
    expect(screen.queryByRole('heading', { name: etl ? 'Run & recover' : 'What needs doing?' })).not.toBeInTheDocument();
    expect(mockGet).not.toHaveBeenCalled();
    expect(mockPost).not.toHaveBeenCalled();
    if (state !== 'restoring') expect(mockReplace).toHaveBeenCalledWith('/');
  });

  test('slow reads preserve immediate working content; late populated sections paint without entrances', async () => {
    render(tree(etl));
    await waitFor(() => expect(pending.length).toBeGreaterThanOrEqual(etl ? 2 : 7));
    const target = screen.getByText(etl ? 'Request a data check' : 'Check data updates');
    painted(target);
    expect(screen.getByRole('button', { name: etl ? 'Refresh' : 'Refresh overview' })).toBeDisabled();
    // Data is deliberately unresolved until all initial-state checks above run.
    await settle();
    await waitFor(() => expect(screen.getAllByText('Only actor A').length).toBeGreaterThan(0));
    screen.getAllByText('Only actor A').forEach(painted);
    if (!etl) {
      ['Your work', 'Updates needing attention', 'Recent recorded actions'].forEach(label => painted(screen.getByText(label)));
      expect(screen.getByRole('link', { name: /Only actor A.*#1/ })).toHaveAttribute('href', '/admin/ingestion/1');
    } else {
      const row = screen.getAllByText('Only actor A')[0].closest('li')!;
      expect(row.className).toContain('flex-wrap');
      screen.getAllByRole('button', { name: /^(Dry-run|Trigger|Run Now ·|Dry Run ·)/ }).forEach(button => expect(button).toBeDisabled());
    }
    expect(mockPost).not.toHaveBeenCalled();
  });

  test('failed reads retain unavailable evidence and a functional refresh', async () => {
    render(tree(etl));
    await waitFor(() => expect(pending.length).toBeGreaterThanOrEqual(etl ? 2 : 7));
    await settle(actorA, true);
    await waitFor(() => expect(screen.getByText(etl ? 'Calendar plan unavailable. Refresh to retry.' : /Recent failures could not be checked\./)).toBeInTheDocument());
    const refresh = screen.getByRole('button', { name: etl ? 'Refresh' : 'Refresh overview' });
    await waitFor(() => expect(refresh).toBeEnabled());
    const count = pending.length;
    fireEvent.click(refresh);
    await waitFor(() => expect(pending.length).toBeGreaterThan(count));
    await settle();
    await waitFor(() => expect(screen.getAllByText('Only actor A').length).toBeGreaterThan(0));
    expect(mockPost).not.toHaveBeenCalled();
  });

  test('identity transition aborts prior requests and hides their delayed replies; unmount/remount stays isolated', async () => {
    const view = render(tree(etl));
    await waitFor(() => expect(pending.length).toBeGreaterThanOrEqual(etl ? 2 : 7));
    const prior = [...pending];
    mockAuth = { ...verified(actorB), user: null, isLoading: true };
    view.rerender(tree(etl));
    expect(screen.queryByRole('heading', { name: etl ? 'Run & recover' : 'What needs doing?' })).not.toBeInTheDocument();
    expect(prior.every(item => item.signal.aborted)).toBe(true);
    await settle(); // Transport intentionally ignores abort and delivers old actor data.
    expect(screen.queryByText('Only actor A')).not.toBeInTheDocument();
    mockAuth = verified(actorB);
    view.rerender(tree(etl));
    await waitFor(() => expect(pending.some(item => item.actor === actorB)).toBe(true));
    await settle(actorB);
    await waitFor(() => expect(screen.getAllByText('Only actor B').length).toBeGreaterThan(0));
    expect(screen.queryByText('Only actor A')).not.toBeInTheDocument();
    view.unmount();
    expect(client.getQueryCache().findAll({ queryKey: ['admin'] })).toHaveLength(0);
    mockAuth = { ...verified(actorA), isAuthenticated: false };
    const reads = mockGet.mock.calls.length;
    render(tree(etl));
    expect(mockGet).toHaveBeenCalledTimes(reads);
    expect(screen.queryByText('Only actor B')).not.toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });
});
