import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Overview from '@/app/admin/page';
import Audit from '@/app/admin/audit-log/page';
import Layout from '@/app/admin/layout';
import api from '@/lib/api/axios';
import { decodeHealth, decodeSchedule } from '@/lib/admin/overview';

let mockActor = 'actor-A';
let mockIsAdmin = true;
jest.mock('next/navigation', () => ({ usePathname: () => '/admin', useSearchParams: () => new URLSearchParams(), useRouter: () => ({ push: jest.fn(), replace: jest.fn() }) }));
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: mockIsAdmin, isLoading: false }), AdminGuard: ({ children }: any) => <>{children}</> }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: mockActor } }) }));
jest.mock('@/components/layout/PageShell', () => ({ __esModule: true, default: ({ title, children }: any) => <main><h1>{title}</h1>{children}</main> }));
jest.mock('framer-motion', () => {
  const components: Record<string, any> = {};
  return { motion: new Proxy({}, { get: (_, tag: string) => components[tag] ??= ({ variants, initial, animate, custom, ...props }: any) => React.createElement(tag, props) }) };
});

const sources = ['treasury', 'cob', 'oag', 'knbs', 'opendata', 'cra'];
const schedule = { timestamp: '2026-10-08T00:00:00Z', running_today: 1, skipping_today: 5, total_sources: 6,
  efficiency: { vs_fixed_schedule: 'Calendar checks' }, sources_to_run: [{ source: 'oag', reason: 'Calendar due' }] };
const health = { timestamp: '2026-10-08T00:00:00Z', scheduler_status: 'unverified', plan_status: 'available' };
const stats = (total: number) => ({ total_users: total, admin_users: 1, new_last_7_days: 0, new_last_30_days: 0 });
const audit = (actor: string) => ({ entries: [{ id: 1, actor_id: actor, actor_email: `${actor}@example.invalid`, action: 'users.send_reset', target_type: 'user', target_id: 'target', payload: {}, created_at: '2026-10-08T00:00:00Z' }], total: 1, page: 1, page_size: 25, has_more: false, snapshot_id: 1, as_of: '2026-10-08T00:00:00Z' });

beforeEach(() => { mockActor = 'actor-A'; mockIsAdmin = true; (api.get as jest.Mock).mockReset(); });
function mount(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const wrap = (child: React.ReactNode) => <QueryClientProvider client={qc}>{child}</QueryClientProvider>;
  return { ...render(wrap(node)), qc, update: (child: React.ReactNode) => wrap(child) };
}

test('overview counts Auth identities including the unprofiled identity', async () => {
  // The producer fixture has two Auth identities, only one linked profile.
  (api.get as jest.Mock).mockImplementation(async (path: string) => {
    if (path === '/admin/users/stats') return { data: stats(2) };
    throw Error('Unrelated fixture evidence unavailable');
  });
  mount(<Overview />);
  const card = await screen.findByRole('link', { name: /Users/ });
  await waitFor(() => expect(within(card).getByText('2')).toBeVisible());
  expect(within(card).getByText('Auth identities')).toBeVisible();
  expect(within(card).queryByText('Profile records')).not.toBeInTheDocument();
  expect(within(card).queryByText(/without profiles are outside this count/)).not.toBeInTheDocument();
});

test.each([1, 5])('partial calendar with %s total sources cannot certify completeness', total => {
  expect(() => decodeSchedule({ ...schedule, total_sources: total, skipping_today: total - 1 })).toThrow();
});
test.each(['unknown', 'OAG', ''])('unknown calendar source %s is rejected', source => {
  expect(() => decodeSchedule({ ...schedule, sources_to_run: [{ source, reason: 'Calendar due' }] })).toThrow();
});
test('duplicate sources cannot certify independent calendar decisions', () => {
  expect(() => decodeSchedule({ ...schedule, running_today: 2, skipping_today: 4, sources_to_run: [schedule.sources_to_run[0], schedule.sources_to_run[0]] })).toThrow();
});
test.each(['garbage', '2026-02-30T00:00:00Z', '2026-02-29T00:00:00Z', '2026-10-08T24:00:00Z', '9999-01-01T00:00:00Z'])('invalid calendar timestamp %s is rejected by both overview contracts', timestamp => {
  expect(() => decodeSchedule({ ...schedule, timestamp })).toThrow();
  expect(() => decodeHealth({ ...health, timestamp })).toThrow();
});
test('complete supported calendar and healthy/unverified legacy contracts remain readable', () => {
  expect(decodeSchedule({ ...schedule, running_today: 6, skipping_today: 0, sources_to_run: sources.map(source => ({ source, reason: 'Calendar due' })) }).total_sources).toBe(6);
  expect(decodeHealth({ ...health, scheduler_status: 'healthy', plan_status: undefined }).plan_status).toBe('available');
  expect(decodeHealth(health).plan_status).toBe('available');
});

test('overview rereads for a different administrator instead of showing cached actor data', async () => {
  (api.get as jest.Mock).mockImplementation(async (path: string) => {
    if (path === '/admin/users/stats') return { data: stats(mockActor === 'actor-A' ? 11 : 22) };
    throw Error('Unrelated fixture evidence unavailable');
  });
  const view = mount(<Overview />);
  const card = await screen.findByRole('link', { name: /Users/ });
  await waitFor(() => expect(within(card).getByText('11')).toBeVisible());
  mockActor = 'actor-B'; view.rerender(view.update(<Overview />));
  await waitFor(() => expect(within(card).getByText('22')).toBeVisible());
  expect(within(card).queryByText('11')).not.toBeInTheDocument();
});
test('audit rereads for the next administrator with no prior actor row', async () => {
  (api.get as jest.Mock).mockImplementation(async () => ({ data: audit(mockActor) }));
  const view = mount(<Audit />);
  expect(await screen.findByText('actor-A')).toBeVisible();
  mockActor = 'actor-B'; view.rerender(view.update(<Audit />));
  expect(await screen.findByText('actor-B')).toBeVisible();
  expect(screen.queryByText('actor-A')).not.toBeInTheDocument();
});
test('layout cancels the departing actor without aborting the next actor request', async () => {
  let priorSignal: AbortSignal | undefined;
  let finishPrior: (value: unknown) => void = () => {};
  (api.get as jest.Mock).mockImplementation((path: string, options: { signal: AbortSignal }) => {
    if (path !== '/admin/users/stats') return Promise.reject(Error('Unrelated fixture evidence unavailable'));
    if (mockActor === 'actor-B') return Promise.resolve({ data: stats(22) });
    priorSignal = options.signal;
    return new Promise(resolve => { finishPrior = resolve; });
  });
  const view = mount(<Layout><Overview /></Layout>);
  await waitFor(() => expect(priorSignal).toBeDefined());
  mockActor = 'actor-B'; view.rerender(view.update(<Layout><Overview /></Layout>));
  await waitFor(() => expect(priorSignal!.aborted).toBe(true));
  expect(view.qc.getQueryCache().getAll().some(q => q.queryKey[2] === 'actor-A')).toBe(false);
  expect(await screen.findByText('22')).toBeVisible();
  finishPrior({ data: stats(11) });
  await waitFor(() => expect(screen.queryByText('11')).not.toBeInTheDocument());
});
test.each([Overview, Audit])('inactive access cannot manually refresh private queries', async Page => {
  mockIsAdmin = false;
  mount(<Page />);
  const refresh = screen.getByRole('button', { name: /Refresh/ });
  expect(refresh).toBeDisabled();
  fireEvent.click(refresh);
  expect(api.get).not.toHaveBeenCalled();
});
