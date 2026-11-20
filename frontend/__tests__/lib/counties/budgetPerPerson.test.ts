import { apiClient } from '@/lib/api/axios';
import { loadCountyCensus, publishedBudgetPerPerson } from '@/lib/counties/budgetPerPerson';

jest.mock('@/lib/api/axios', () => ({ apiClient: { get: jest.fn() } }));
const get = jest.mocked(apiClient.get);

const countyRow = {
  entity_id: 12,
  entity_name: 'Mandera County',
  entity_type: 'county',
  year: 2019,
  total_population: 400_000,
  source_document_id: 741,
};
const document = {
  id: 741,
  title: '2019 Kenya Population and Housing Census Volume I: Population by County and Sub-County',
  publisher: 'Kenya National Bureau of Statistics',
  url: 'https://www.knbs.or.ke/census-volume-one.pdf',
  meta: { dataset_id: 'knbs_census_2019' },
};

beforeEach(() => get.mockReset());

function mockCensus(population: unknown = [countyRow], source: unknown = document) {
  get.mockResolvedValueOnce({ data: population }).mockResolvedValueOnce({ data: source });
}

it('loads one explicit census edition, excluding national and invalid rows', async () => {
  mockCensus([
    { ...countyRow, entity_id: null, entity_name: null, entity_type: 'national' },
    { ...countyRow, entity_id: 93, entity_name: 'Lamu County', year: 2026 },
    { ...countyRow, entity_id: 22, entity_name: 'Baringo County', total_population: 0 },
    { ...countyRow, entity_id: 24, entity_name: 'Nairobi County', source_document_id: null },
    { ...countyRow, entity_id: 32, entity_name: 'Kajiado County', total_population: '50' },
    { ...countyRow, entity_id: 96, entity_name: 'Unknown County' },
    null,
    countyRow,
  ]);
  const { signal } = new AbortController();
  const census = await loadCountyCensus(signal);

  expect(get.mock.calls).toEqual([
    ['/economic/population?year=2019&limit=100', { signal }],
    ['/source-documents/741', { signal }],
  ]);
  const { meta: _meta, ...source } = document;
  expect(census).toEqual({
    year: 2019,
    source,
    counts: new Map([[12, { countyKey: 'mandera', population: 400_000 }]]),
  });
});

it.each([
  ['missing rows', null],
  ['wrong container', { rows: [countyRow] }],
  ['oversized rows', Array(101).fill(countyRow)],
  ['conflicting document IDs', [
    countyRow,
    { ...countyRow, entity_id: 93, entity_name: 'Lamu County', source_document_id: 555 },
  ]],
  ['duplicate entity IDs', [countyRow, { ...countyRow, entity_name: 'Lamu County' }]],
  ['duplicate county names', [countyRow, { ...countyRow, entity_id: 99, total_population: null }]],
] as const)('does not resolve a source for %s', async (_shape, population) => {
  mockCensus(population);
  await expect(loadCountyCensus()).resolves.toBeUndefined();
  expect(get.mock.calls).toEqual([['/economic/population?year=2019&limit=100']]);
});

it.each([
  ['wrong source ID', { id: 999 }],
  ['wrong publisher', { publisher: 'World Bank' }],
  ['wrong edition', { title: document.title.replace('Volume I:', 'Volume II:') }],
  ['wrong dataset', { meta: { dataset_id: 'knbs_census_2009' } }],
  ['lookalike hostname', { url: 'https://knbs.or.ke.example.com/report.pdf' }],
  ['plain HTTP', { url: 'http://www.knbs.or.ke/report.pdf' }],
  ['URL credentials', { url: 'https://user:password@www.knbs.or.ke/report.pdf' }],
] as const)('rejects a document with %s', async (_shape, overrides) => {
  mockCensus([countyRow], { ...document, ...overrides });
  await expect(loadCountyCensus()).resolves.toBeUndefined();
  expect(get).toHaveBeenCalledTimes(2);
});

it('accepts the official KNBS repository after a source URL update', async () => {
  const url = 'https://repository.knbs.or.ke/server/api/core/bitstreams/volume-one/content';
  mockCensus([countyRow], { ...document, url });
  await expect(loadCountyCensus()).resolves.toMatchObject({ source: { url } });
});

it('skips the source lookup when the population request has been aborted', async () => {
  const controller = new AbortController();
  get.mockImplementationOnce(async () => {
    controller.abort();
    return { data: [countyRow] };
  });
  await expect(loadCountyCensus(controller.signal)).rejects.toHaveProperty('name', 'AbortError');
  expect(get).toHaveBeenCalledTimes(1);
});

it('does not relabel a request failure as source absence', async () => {
  const error = new Error('Census request failed');
  get.mockRejectedValueOnce(error);
  await expect(loadCountyCensus()).rejects.toBe(error);
});

const allocationSource = {
  id: 57,
  title: 'Controller of Budget County BIRR FY2025/26 9M',
  publisher: 'Controller of Budget',
  url: 'https://cob.go.ke/download/example-cbirr/?wpdmdl=1',
};
const financialSummary = {
  total_allocation: 8_000_000_000,
  currency: 'KES',
  accounting_basis: 'reported_total',
  fiscal_period: { label: 'FY2025/26 9M' },
  sources: [allocationSource],
};
const allocated = {
  source_document_id: 57,
  publisher: 'Controller of Budget',
  source_url: allocationSource.url,
  status: 'qualified',
  reason: 'historical_source_not_value_checked',
  identity: {
    measure: 'allocated_amount',
    geography: 'Mandera County',
    period: 'FY2025/26 9M',
    unit: 'KES',
    basis: 'actual',
    entity_id: 12,
    dimensions: { category: 'Total', subcategory: null },
  },
};

async function validInput() {
  mockCensus();
  return {
    census: await loadCountyCensus(),
    countyName: 'Mandera',
    fiscalYear: 'FY 2025/26 9M',
    budgetSource: null,
    financialSummary,
    budgetLines: { '195': { allocated_amount: allocated } },
  };
}

it('derives the rate from actual allocation and the bound census entity', async () => {
  expect(publishedBudgetPerPerson(await validInput())).toEqual({
    value: 20_000,
    allocation: 8_000_000_000,
    fiscalPeriod: 'FY2025/26 9M',
    budget: allocationSource,
    population: 400_000,
    censusYear: 2019,
    censusSource: {
      id: document.id, title: document.title, publisher: document.publisher, url: document.url,
    },
  });
});

it('matches the Nairobi City census alias without relying on a route ID', async () => {
  mockCensus([{ ...countyRow, entity_id: 48, entity_name: 'Nairobi City County' }]);
  const census = await loadCountyCensus();
  const identity = { ...allocated.identity, geography: 'Nairobi County', entity_id: 48 };
  expect(publishedBudgetPerPerson({
    census,
    countyName: 'Nairobi',
    fiscalYear: 'FY2025/26 9M',
    financialSummary,
    budgetLines: { '195': { allocated_amount: { ...allocated, identity } } },
  })?.value).toBe(20_000);
});

it('preserves a qualified reported allocation of zero', async () => {
  const input = await validInput();
  expect(publishedBudgetPerPerson({
    ...input, financialSummary: { ...financialSummary, total_allocation: 0 },
  })?.value).toBe(0);
});

it.each([
  ['missing census', { census: undefined }],
  ['fiscal period mismatch', { fiscalYear: 'FY2025/26' }],
  ['CRA model', { budgetSource: 'cra_model' }],
  ['mixed budget', { budgetSource: 'mixed' }],
  ['missing financial summary', { financialSummary: null }],
  ['missing published allocation', { financialSummary: { ...financialSummary, total_allocation: null } }],
  ['wrong allocation currency', { financialSummary: { ...financialSummary, currency: 'USD' } }],
  ['budget classification without a reported total', {
    financialSummary: { ...financialSummary, accounting_basis: 'recurrent_plus_development' },
  }],
  ['missing allocation receipt', { budgetLines: [] }],
  ['conflicting allocation receipt', {
    budgetLines: { '195': { allocated_amount: { ...allocated, status: 'conflicting' } } },
  }],
  ['unverified bytes on a receipt claiming verification', {
    budgetLines: { '195': { allocated_amount: { ...allocated, status: 'verified', value_checked: true } } },
  }],
  ['another allocation document', {
    budgetLines: { '195': { allocated_amount: { ...allocated, source_document_id: 99 } } },
  }],
  ['different population entity', {
    budgetLines: { '195': { allocated_amount: {
      ...allocated, identity: { ...allocated.identity, entity_id: 24 },
    } } },
  }],
  ['multiple matching total receipts', {
    budgetLines: { '195': { allocated_amount: allocated }, '196': { allocated_amount: allocated } },
  }],
] as const)('withholds budget per person for %s', async (_shape, overrides) => {
  expect(publishedBudgetPerPerson({ ...await validInput(), ...overrides })).toBeUndefined();
});
