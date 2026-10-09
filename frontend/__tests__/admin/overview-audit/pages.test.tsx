import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Overview from '@/app/admin/page';
import Audit from '@/app/admin/audit-log/page';
import Layout from '@/app/admin/layout';
import api from '@/lib/api/axios';

let mockSearch = new URLSearchParams();
let mockPath = '/admin';
const mockPush = jest.fn();
const mockReplace = jest.fn();
jest.mock('next/navigation', () => ({ usePathname: () => mockPath, useSearchParams: () => mockSearch, useRouter: () => ({ push: mockPush, replace: mockReplace }) }));
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true, isLoading: false }), AdminGuard: ({ children }: any) => <>{children}</> }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: 'inert-admin' } }) }));
jest.mock('@/components/layout/PageShell', () => ({ __esModule: true, default: ({ title, subtitle, children }: any) => <main><h1>{title}</h1><p>{subtitle}</p>{children}</main> }));
jest.mock('framer-motion', () => {
  const components: Record<string, any> = {};
  return { motion: new Proxy({}, { get: (_, tag: string) => components[tag] ??= ({ variants, initial, animate, custom, ...props }: any) => React.createElement(tag, props) }) };
});

const audit = { entries: [], total: 0, page: 1, page_size: 25, has_more: false, snapshot_id: 0, as_of: '2026-10-08T00:00:00Z' };
const responses: Record<string, any> = {
  '/admin/ingestion-jobs/stats/summary': { total_jobs: 0, completed: 0, failed: 0, running: 0, pending: 0, completed_with_errors: 0, total_items_processed: 0, total_items_created: 0, total_items_updated: 0, domains: {} },
  '/admin/etl/schedule/summary': { timestamp: '2026-10-08T00:00:00Z', running_today: 1, skipping_today: 5, total_sources: 6, efficiency: { skip_percentage: 83.3, vs_fixed_schedule: '50% reduction' }, sources_to_run: [{ source: 'cob', reason: 'calendar' }] },
  '/admin/etl/health': { timestamp: '2026-10-08T00:00:00Z', scheduler_status: 'healthy', schedule_summary: {} },
  '/admin/users/stats': { total_users: 2, admin_users: 1, new_last_7_days: 0, new_last_30_days: 1 },
  '/admin/audit-log': audit,
  '/admin/ingestion-jobs': { jobs: [], total: 0, page: 1, page_size: 5, has_more: false },
  '/admin/social/system/status': { publishing_enabled: false, worker: { state: 'unavailable', heartbeat_at: null, last_scan_at: null }, queue_counts: { pending: 0 } },
};

beforeEach(() => {
  mockSearch = new URLSearchParams(); mockPath = '/admin'; mockPush.mockReset(); mockReplace.mockReset();
  (api.get as jest.Mock).mockClear();
  (api.get as jest.Mock).mockImplementation(async (path: string) => ({ data: responses[path] }));
});
function mount(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

test('overview does not certify a running worker from scheduler calculation', async () => {
  mount(<Overview />);
  expect(await screen.findByText(/Worker execution unverified/)).toBeVisible();
  expect(screen.queryByText('Healthy')).not.toBeInTheDocument();
  expect(screen.getByText(/Auth identities/)).toBeVisible();
  expect(screen.getByRole('link', { name: /Social publishing/ })).toHaveAttribute('href', '/admin/social');
});

test('available calendar plan with unverified worker does not invent an ETL alert', async () => {
  (api.get as jest.Mock).mockImplementation(async (path: string) => ({ data: path === '/admin/etl/health' ? {
    timestamp: '2026-10-08T00:00:00Z', scheduler_status: 'unverified', plan_status: 'available', worker_status: 'unverified', data_freshness: 'unverified',
  } : responses[path] }));
  mount(<Overview />);
  expect(await screen.findByText('Schedule calculated')).toBeVisible();
  expect(screen.getByText('Worker execution unverified')).toBeVisible();
  expect(screen.queryByText('Calculation unavailable')).not.toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

test('unavailable calendar plan remains actionable with unverified worker', async () => {
  (api.get as jest.Mock).mockImplementation(async (path: string) => ({ data: path === '/admin/etl/health' ? {
    timestamp: '2026-10-08T00:00:00Z', scheduler_status: 'unverified', plan_status: 'unavailable', worker_status: 'unverified', data_freshness: 'unverified',
  } : responses[path] }));
  mount(<Overview />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Calculation unavailable');
  expect(screen.getByText('Worker execution unverified')).toBeVisible();
});

test('overview explicitly reports unavailable audit and failure evidence', async () => {
  (api.get as jest.Mock).mockImplementation(async (path: string) => {
    if (path === '/admin/audit-log' || path === '/admin/ingestion-jobs') throw Error('inert failure');
    return { data: responses[path] };
  });
  mount(<Overview />);
  expect(await screen.findByText(/Audit evidence unavailable/)).toBeVisible();
  expect(screen.getByText(/Failure evidence unavailable/)).toBeVisible();
});

test('overview rejects malformed numeric counts instead of showing a value', async () => {
  (api.get as jest.Mock).mockImplementation(async (path: string) => ({ data: path === '/admin/users/stats' ? { total_users: -1 } : responses[path] }));
  mount(<Overview />);
  const card = await screen.findByRole('link', { name: /Users/ });
  await waitFor(() => expect(within(card).getByText('Could not load')).toBeVisible());
  expect(within(card).queryByText('-1')).not.toBeInTheDocument();
});

test('audit filters are labelled and submitted together into browser history', async () => {
  mount(<Audit />);
  fireEvent.change(screen.getByLabelText('Action'), { target: { value: 'etl.trigger' } });
  fireEvent.change(screen.getByLabelText('Target id'), { target: { value: 'cob' } });
  fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }));
  expect(mockPush).toHaveBeenCalledWith(expect.stringContaining('target_id=cob'), expect.anything());
});

test('empty out-of-range audit page retains a previous-page control', async () => {
  mockSearch = new URLSearchParams('page=2');
  (api.get as jest.Mock).mockResolvedValue({ data: { ...audit, page: 2, total: 1, snapshot_id: 1 } });
  mount(<Audit />);
  expect(await screen.findByRole('button', { name: 'Prev' })).toBeEnabled();
  expect(screen.getByText(/No entries on this page/)).toBeVisible();
});

test('audit rejects malformed successful data as unavailable evidence', async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: { ...audit, has_more: 'false' } });
  mount(<Audit />);
  expect(await screen.findByText(/Could not load audit log/)).toBeVisible();
  expect(screen.queryByText('No actions match these filters.')).not.toBeInTheDocument();
});

test.each(['NaN', '2147483648'])('Refresh clears malformed snapshot URL with ID %s', async value => {
  mockSearch = new URLSearchParams(`snapshot_id=${value}&as_of=2026-10-08T00%3A00%3A00Z&visibility_snapshot=3%3A9%3A`);
  (api.get as jest.Mock).mockResolvedValue({ data: audit });
  mount(<Audit />);
  await screen.findByText('No actions match these filters.');
  fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  expect(mockPush).toHaveBeenCalledWith('/admin/audit-log?days=30&page=1', { scroll: false });
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
});

test('admin navigation exposes current subsection and named keyboard navigation', () => {
  mockPath = '/admin/social/accounts';
  mount(<Layout><p>inert</p></Layout>);
  const nav = screen.getByRole('navigation', { name: 'Admin navigation' });
  expect(within(nav).getByRole('link', { name: 'Social accounts' })).toHaveAttribute('aria-current', 'page');
  expect(within(nav).getByRole('link', { name: 'Social Media' })).not.toHaveAttribute('aria-current');
});
