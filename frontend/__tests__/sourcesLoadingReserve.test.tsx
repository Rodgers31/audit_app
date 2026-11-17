import '@testing-library/jest-dom';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SourcesPage from '@/app/sources/page';

const get = jest.fn();
jest.mock('@/lib/api/axios', () => {
  const client = { get: (...args: unknown[]) => get(...args) };
  return { __esModule: true, default: client, apiClient: client };
});

jest.mock('next/navigation', () => ({
  __esModule: true,
  usePathname: () => '/sources',
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));

const SUMMARY = {
  total_documents: 2330,
  sources: [
    {
      publisher: 'Synthetic local fixture',
      document_count: 4,
      last_fetched: null,
      doc_types: { budget: 4 },
    },
    {
      publisher: 'Controller of Budget',
      website: 'https://cob.go.ke',
      document_count: 12,
      downloaded_documents: 1,
      last_fetched: '2025-06-01T00:00:00Z',
      doc_types: { report: 12 },
    },
    {
      publisher: 'Office of the Controller of Budget (OCOB)',
      website: 'https://cob.go.ke/',
      document_count: 3,
      downloaded_documents: 0,
      last_fetched: null,
      doc_types: { report: 3 },
    },
    {
      publisher: 'National Treasury & Controller of Budget',
      website: 'https://cob.go.ke/',
      document_count: 2,
      last_fetched: null,
      doc_types: { report: 2 },
    },
    {
      publisher: 'Office of the Auditor-General',
      website: 'https://www.oagkenya.go.ke',
      document_count: 2,
      last_fetched: null,
      doc_types: { audit: 2 },
    },
    {
      publisher: 'Unverified website fixture',
      website: 'https://name:credential@example.test/',
      document_count: 1,
      last_fetched: null,
      doc_types: { report: 1 },
    },
  ],
};

const FRESHNESS = {
  sources: [
    {
      source: 'COB', covers_through: 'FY2024/25', last_updated: '2025-05-12',
      last_checked: '2025-06-01', update_frequency: 'Quarterly', status: 'stale',
    },
    {
      source: 'OAG', covers_through: null, last_updated: '2099-06-01',
      last_checked: '2025-06-01', update_frequency: 'Annually', status: 'fresh',
    },
  ],
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><SourcesPage /></QueryClientProvider>);
}

function openHealth() {
  const details = screen.getByText('For researchers: data health').closest('details')!;
  details.open = true;
  fireEvent(details, new Event('toggle'));
}

beforeEach(() => get.mockReset());

it('reserves the publisher area with no count while a cold manifest read is pending', () => {
  get.mockImplementation(() => new Promise(() => {}));
  renderPage();

  const publishers = screen.getByRole('region', { name: 'Publishers' });
  expect(within(publishers).getByRole('status')).toHaveTextContent('Loading publishers…');
  expect(within(publishers).queryByText('Documents indexed')).not.toBeInTheDocument();
  expect(screen.getByText('For researchers: data health').closest('details')).not.toHaveAttribute('open');
  expect(get.mock.calls.map(([url]) => url)).not.toContain('/provenance/health');
});

it('distinguishes an empty manifest response from a missing count', async () => {
  get.mockImplementation((url: string) => Promise.resolve({ data: url === '/sources/summary'
    ? { total_documents: 0, sources: [] }
    : { sources: [] } }));
  renderPage();

  expect(await screen.findByText('No source documents indexed yet')).toBeVisible();
  expect(screen.getByText('Documents indexed').closest('p')).toHaveTextContent('Documents indexed · 0');
});

it('lists named publishers and scoped coverage without deriving dates from download checks', async () => {
  get.mockImplementation((url: string) => Promise.resolve({ data: url === '/sources/summary'
    ? SUMMARY : url === '/data/freshness' ? FRESHNESS : { tables: [] } }));
  renderPage();

  const publishers = screen.getByRole('region', { name: 'Publishers' });
  const cob = await within(publishers).findByRole('link', { name: 'Controller of Budget' });
  expect(cob).toHaveAttribute('href', 'https://cob.go.ke/');
  expect(within(publishers).getAllByRole('heading')[0]).toHaveTextContent('Controller of Budget');
  expect(within(publishers).queryByRole('heading', { name: 'Office of the Controller of Budget (OCOB)' }))
    .not.toBeInTheDocument();
  expect(within(publishers).getByRole('heading', { name: 'National Treasury & Controller of Budget' })).toBeVisible();
  expect(within(publishers).queryByRole('link', { name: 'National Treasury & Controller of Budget' })).not.toBeInTheDocument();
  expect(within(publishers).queryByRole('link', { name: 'Unverified website fixture' })).not.toBeInTheDocument();
  expect(await screen.findByText(/Budget implementation reports: quarterly/)).toBeVisible();
  expect(screen.getByText('Data in use covers through FY2024/25')).toBeVisible();
  expect(screen.getByText('Latest recorded publication date in use: 12 May 2025')).toBeVisible();
  expect(within(publishers).getAllByText(/Latest recorded publication date in use/)).toHaveLength(1);
  expect(screen.queryByText(/Jun 2025|2099/)).not.toBeInTheDocument();
  expect(screen.getByText('Documents indexed').closest('p')).toHaveTextContent('2,330');

  openHealth();
  expect(await screen.findByText('No dataset health records available.')).toBeVisible();
  expect(screen.getByText('Last verified download: 1 Jun 2025')).toBeVisible();
  expect(screen.getByText('3 registered · 0 downloaded · Extraction count unavailable')).toBeVisible();
});

it('leaves the researcher panel available when the manifest and freshness reads fail', async () => {
  get.mockImplementation((url: string) => url === '/provenance/health'
    ? Promise.resolve({ data: { tables: [] } })
    : Promise.reject(new Error('unavailable')));
  renderPage();

  expect(await screen.findByRole('alert')).toHaveTextContent('The publisher list could not be loaded.');
  expect(screen.queryByText('Documents indexed')).not.toBeInTheDocument();
  expect(screen.queryByText('No source documents indexed yet')).not.toBeInTheDocument();
  openHealth();
  expect(await screen.findByText('No dataset health records available.')).toBeVisible();
});
