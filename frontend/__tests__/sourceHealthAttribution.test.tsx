import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SourcesPage from '@/app/sources/page';

const get = jest.fn();
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: (...args: unknown[]) => get(...args) } }));
jest.mock('@/components/layout/PageShell', () => ({ __esModule: true, default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));

const publishers = [
  { source_id: 'worldbank', name: 'World Bank Open Data', row_count: 1 },
  { source_id: 'knbs', name: 'Kenya National Bureau of Statistics (KNBS)', row_count: 1 },
];

function renderHealth(fields: Record<string, unknown>) {
  get.mockImplementation((url: string) => Promise.resolve({ data: url === '/sources/summary'
    ? { total_documents: 0, sources: [] }
    : { tables: [{ table: 'gdp_data', label: 'GDP Data', row_count: 2, source: null, status: 'degraded', document_bytes_checked: false, attribution_basis: 'coherent_observation_identity', represented_publishers: [], unresolved_source_rows: 0, ...fields }] } }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><SourcesPage /></QueryClientProvider>);
}

it('renders mixed stored lineage with both publishers and no verification claim', async () => {
  renderHealth({ attribution_status: 'mixed_publishers', represented_publishers: publishers });
  expect(await screen.findByText('Mixed stored lineage')).toBeInTheDocument();
  expect(screen.getByText(/World Bank Open Data · 1 row/)).toBeInTheDocument();
  expect(screen.getByText(/Kenya National Bureau of Statistics \(KNBS\) · 1 row/)).toBeInTheDocument();
  expect(screen.getByText(/does not validate document bytes or cross-check figures/)).toBeInTheDocument();
});

it('makes partial lineage explicit instead of crediting the whole table to one publisher', async () => {
  renderHealth({ attribution_status: 'partial', represented_publishers: publishers.slice(0, 1), unresolved_source_rows: 1 });
  expect(await screen.findByText('Partial stored lineage')).toBeInTheDocument();
  expect(screen.getByText('1 row without resolved lineage')).toBeInTheDocument();
});

it('renders an explicit absence for unresolved attribution', async () => {
  renderHealth({ attribution_status: 'unresolved', unresolved_source_rows: 2 });
  expect(await screen.findByText('Stored lineage unresolved')).toBeInTheDocument();
  expect(screen.getByText('2 rows without resolved lineage')).toBeInTheDocument();
});

it('describes other tables as document links without claiming observation verification', async () => {
  renderHealth({ attribution_status: 'single_publisher', attribution_basis: 'stored_document_links', source: 'World Bank Open Data', represented_publishers: publishers.slice(0, 1) });
  expect(await screen.findByText('Linked document publisher')).toBeInTheDocument();
  expect(screen.getByText('Linked documents only; observation evidence not assessed')).toBeInTheDocument();
});

it('distinguishes an empty cohort from unresolved rows', async () => {
  renderHealth({ row_count: 0, attribution_status: 'empty' });
  expect(await screen.findByText('No stored rows to attribute')).toBeInTheDocument();
  expect(screen.queryByText(/without resolved lineage/)).not.toBeInTheDocument();
});

it('renders captured full-main PostgreSQL HTTP cohort responses', async () => {
  const capture = require('./fixtures/sourceHealthAttribution.json');
  get.mockImplementation((url: string) => Promise.resolve({ data: url === '/sources/summary'
    ? { total_documents: 0, sources: [] }
    : capture.metadata_only_population }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><SourcesPage /></QueryClientProvider>);
  expect(await screen.findByText('Partial stored lineage')).toBeInTheDocument();
  expect(screen.getByText('Stored observation lineage')).toBeInTheDocument();
  expect(screen.getByText('1 row without resolved lineage')).toBeInTheDocument();
  expect(screen.getByText(/Kenya National Bureau of Statistics \(KNBS\) · 1 row/)).toBeInTheDocument();
  expect(screen.getAllByText(/World Bank Open Data · 1 row/)).toHaveLength(2);
});
