import { getBudgetAllocation } from '@/lib/api/budget';
import { apiClient } from '@/lib/api/axios';
import captures from './fixtures/county-budget-http.json';

jest.mock('@/lib/api/axios', () => ({ apiClient: { get: jest.fn() } }));
const get = apiClient.get as jest.Mock;

beforeEach(() => get.mockReset());

test.each(Object.entries(captures))('returns the actual PostgreSQL HTTP %s account unchanged', async (_name, body) => {
  get.mockResolvedValueOnce({ data: body });
  const controller = new AbortController();
  const result = await getBudgetAllocation('mandera-county', '1900/01', controller.signal);
  expect(result).toEqual(body);
  expect(result?.financial_summary.fiscal_period?.label).toBe('FY2024/25');
  expect(get).toHaveBeenCalledWith('/counties/mandera-county/budget?fiscal_year=1900%2F01', { signal: controller.signal });
});

test('propagates HTTP failure and cancellation', async () => {
  const failure = new Error('HTTP 500');
  get.mockRejectedValueOnce(failure);
  await expect(getBudgetAllocation('mandera-county')).rejects.toBe(failure);
  const cancelled = new Error('cancelled');
  get.mockRejectedValueOnce(cancelled);
  const controller = new AbortController();
  controller.abort();
  await expect(getBudgetAllocation('mandera-county', undefined, controller.signal)).rejects.toBe(cancelled);
  expect(get).toHaveBeenLastCalledWith('/counties/mandera-county/budget', { signal: controller.signal });
});

test.each([undefined, {}, { data: captures.reported }, { ...captures.reported, total_budget: true }, { ...captures.reported, total_spent: -1 }, { ...captures.reported, sources: 'not-an-array' }])('rejects malformed successful response %p', async body => {
  get.mockResolvedValueOnce({ data: body });
  await expect(getBudgetAllocation('mandera-county')).rejects.toThrow('Invalid county budget response');
});

test('accepts structurally identical fiscal metadata with different key order', async () => {
  const period = captures.reported.financial_summary.fiscal_period;
  const reordered = { label: period.label, end_date: period.end_date, id: period.id, start_date: period.start_date };
  const body = { ...captures.reported, financial_summary: { ...captures.reported.financial_summary, fiscal_period: reordered } };
  get.mockResolvedValueOnce({ data: body });
  await expect(getBudgetAllocation('mandera-county')).resolves.toEqual(body);
});

const unsupportedAccount = (field: string, value: unknown) => ({
  ...captures.reported, [field]: value,
  financial_summary: { ...captures.reported.financial_summary, [field]: value },
});

test.each([
  unsupportedAccount('fiscal_period', null),
  unsupportedAccount('currency', null),
  unsupportedAccount('accounting_basis', null),
  unsupportedAccount('sources', []),
  unsupportedAccount('sources', [captures.reported.sources[0], { ...captures.reported.sources[0], id: 999 }]),
  unsupportedAccount('fiscal_period', { ...captures.reported.fiscal_period, start_date: 'bad-date' }),
  { ...captures.reported, budget_utilization: 999, budget_execution_rate: 999, financial_summary: { ...captures.reported.financial_summary, execution_rate: 999 } },
  { ...captures.reported, total_spent: null, absent_reasons: { total_spent: ' ' }, financial_summary: { ...captures.reported.financial_summary, total_spent: null, absent_reasons: { total_spent: ' ' } } },
])('rejects positive accounts with invalid provenance or accounting %p', async body => {
  get.mockResolvedValueOnce({ data: body });
  await expect(getBudgetAllocation('mandera-county')).rejects.toThrow('Invalid county budget response');
});
