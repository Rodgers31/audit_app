import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import StatusPage from '@/app/status/page';
import api from '@/lib/api/axios';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ AdminGuard: ({ children }: any) => children }));
jest.mock('next/navigation', () => ({ usePathname: () => '/status', useRouter: () => ({ back: jest.fn() }) }));
jest.mock('@/components/layout/PageShell', () => ({ __esModule: true, default: ({ children }: any) => children }));

const snapshot = (source: object = {}) => ({
  schema_version: 2, status: 'unknown', checked_at: new Date().toISOString(),
  auto_seeder: { is_running: false }, database: {}, modules: {}, etl_jobs: [],
  alerts: [], summary: { errors: 0, warnings: 0, total_alerts: 0 },
  source_checks_in_progress: false,
  execution: { owner: 'dedicated seeding runner', status: 'not_observed', evidence_url: '/admin/etl' },
  sources: { knbs: { key: 'knbs', name: 'KNBS', url: 'https://www.knbs.or.ke',
    freshness: 'unknown', outcome: 'not_observed', reachable: null, observed_at: null, ...source } },
});

function show(data: object) {
  (api.get as jest.Mock).mockResolvedValue({ data });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><StatusPage /></QueryClientProvider>);
}

beforeEach(() => jest.clearAllMocks());

test('uses the prompt versioned snapshot and never calls unknown sources down', async () => {
  show(snapshot());
  expect(await screen.findByText('Not yet observed')).toBeVisible();
  expect(screen.queryByText('Down')).not.toBeInTheDocument();
  expect(api.get).toHaveBeenCalledWith('/system/pipeline-health/v2', expect.any(Object));
  expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0);
});

test('certificate and timeout observations have different labels', async () => {
  show(snapshot({ freshness: 'fresh', outcome: 'certificate_error', reachable: false,
    observed_at: new Date().toISOString(), error: '[SSL: CERTIFICATE_VERIFY_FAILED]' }));
  expect(await screen.findByText('Certificate error')).toBeVisible();
  expect(screen.queryByText('Timeout')).not.toBeInTheDocument();
  expect(screen.getByText(/Dedicated worker execution is not checked here/)).toBeVisible();
  expect(screen.queryByText(/APScheduler runs jobs automatically/)).not.toBeInTheDocument();
});

test('stale last-known success cannot look like a fresh OK', async () => {
  show(snapshot({ freshness: 'stale', outcome: 'http_response', reachable: true,
    status_code: 200, observed_at: '2026-01-01T00:00:00Z' }));
  expect(await screen.findByText('Stale · HTTP 200')).toBeVisible();
  expect(screen.queryByText('OK (200)')).not.toBeInTheDocument();
});
