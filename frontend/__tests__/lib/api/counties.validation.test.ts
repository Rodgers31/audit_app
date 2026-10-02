import { QueryClient, dehydrate } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/axios';
import { getCounties, getCounty, getCountyComprehensive, transformCountyData } from '@/lib/api/counties';

jest.mock('@/lib/api/axios', () => ({ apiClient: { get: jest.fn() } }));
const mockGet = apiClient.get as jest.Mock;

// The public list/detail identity is a legacy route, independent of official
// county-code metadata. Financial absences and published zero are valid data.
const county = {
  id: '001', name: 'Nairobi', code: '001', population: null,
  budget_2025: 0, financial_summary: { total_allocation: 0 },
  audit_rating: '', audit_status: 'pending', financial_health_score: null,
  total_debt: null, debt: 123, money_received: null, pending_bills: 0,
};

const invalidFields = [
  ['absent', undefined], ['null', null], ['number', 7], ['boolean', false],
  ['object', {}], ['array', []], ['empty', ''], ['whitespace', ' \t\n '],
] as const;
const invalidContainers = [null, undefined, {}, 'garbage', 42, false];

beforeEach(() => mockGet.mockReset());

for (const field of ['id', 'name'] as const) {
  describe(`county response with invalid ${field}`, () => {
    it.each(invalidFields)('rejects %s across list, legacy detail and comprehensive detail', async (_label, value) => {
      const invalid = { ...county, [field]: value };
      if (value === undefined) delete invalid[field];
      expect(() => transformCountyData(invalid as never)).toThrow(/Invalid county response/);
      mockGet.mockResolvedValue({ data: [county, invalid] });
      await expect(getCounties()).rejects.toThrow(/Invalid county response/);
      mockGet.mockResolvedValue({ data: invalid });
      await expect(getCounty('001')).rejects.toThrow(/Invalid county response/);
      await expect(getCountyComprehensive('001')).rejects.toThrow(/Invalid county response/);
    });
  });
}

it.each(invalidContainers)('rejects malformed list/container %p deliberately', async (data) => {
  mockGet.mockResolvedValue({ data });
  await expect(getCounties()).rejects.toThrow(/Invalid county response/);
});

it.each([...invalidContainers, []])('rejects malformed county record %p deliberately', async (data) => {
  mockGet.mockResolvedValue({ data: [county, data] });
  await expect(getCounties()).rejects.toThrow(/Invalid county response/);
  mockGet.mockResolvedValue({ data });
  await expect(getCounty('001')).rejects.toThrow(/Invalid county response/);
  await expect(getCountyComprehensive('001')).rejects.toThrow(/Invalid county response/);
});

it('keeps the whole valid list, reported zero, withheld amounts and route identities', async () => {
  const rows = Array.from({ length: 47 }, (_, i) => ({ ...county, id: String(i + 1).padStart(3, '0'), name: `Synthetic ${i}` }));
  rows[0] = { ...county };
  rows[46] = { ...county, id: '047', name: 'Mombasa', code: '047' };
  mockGet.mockResolvedValue({ data: rows });
  const result = await getCounties();
  expect(result).toHaveLength(47);
  expect(result[0]).toMatchObject({ id: '001', name: 'Nairobi', budget: 0, totalBudget: 0, population: null, pendingBills: 0 });
  expect(result[0].debt).toBeUndefined();
  expect(result[0].moneyReceived).toBeUndefined();
  expect(result[0].fiscal_grade).toBeUndefined();
  expect(result[46]).toMatchObject({ id: '047', name: 'Mombasa' });
  const comprehensive = { ...county, metadata: { county_code: '047' } };
  mockGet.mockResolvedValue({ data: comprehensive });
  expect(await getCountyComprehensive('001')).toBe(comprehensive);
  expect(comprehensive).toMatchObject({ id: '001', name: 'Nairobi', metadata: { county_code: '047' } });
  mockGet.mockResolvedValue({ data: [] });
  expect(await getCounties()).toEqual([]);
});

it('never dehydrates malformed list or detail as successful SSR data', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  try {
    mockGet.mockResolvedValue({ data: [{ ...county, name: null }] });
    await client.prefetchQuery({ queryKey: ['counties', 'filtered'], queryFn: () => getCounties() });
    mockGet.mockResolvedValue({ data: { ...county, name: null } });
    await client.prefetchQuery({ queryKey: ['counties', '001', 'comprehensive', null], queryFn: () => getCountyComprehensive('001') });
    expect(client.getQueryState(['counties', 'filtered'])?.status).toBe('error');
    expect(client.getQueryState(['counties', '001', 'comprehensive', null])?.status).toBe('error');
    expect(dehydrate(client).queries).toEqual([]);
  } finally {
    client.clear();
  }
});
