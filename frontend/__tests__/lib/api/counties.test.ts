/**
 * Tests for lib/api/counties.ts
 *
 * Covers:
 *  getCounties        – fetches and transforms county data
 *  getCounty          – fetches a single county
 *  getCountyByCode    – fetches county by code
 *  searchCounties     – search API call
 *  getCountiesPaginated – pagination support
 */

import { apiClient } from '@/lib/api/axios';
import {
  getCounties,
  getCounty,
  getCountyByCode,
  getCountyComprehensive,
  searchCounties,
} from '@/lib/api/counties';

// Mock apiClient
jest.mock('@/lib/api/axios', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
  },
}));

const mockGet = apiClient.get as jest.MockedFunction<typeof apiClient.get>;

const sampleBackendCounty = {
  id: '1',
  name: 'Nairobi',
  code: 'NBI',
  population: 4_400_000,
  budget_2025: 38_000_000_000,
  financial_health_score: 72,
  audit_rating: 'info',
  audit_status: 'qualified',
  coordinates: [36.8219, -1.2921] as [number, number],
  total_budget: 38_000_000_000,
  total_spent: 30_000_000_000,
  budget_utilization: 79,
  money_received: 30_000_000_000,
  revenue_collection: 12_000_000_000,
  pending_bills: 3_000_000_000,
  development_budget: 15_000_000_000,
  recurrent_budget: 23_000_000_000,
  total_debt: 8_000_000_000,
  audit_issues: [],
};

describe('getCounties', () => {
  beforeEach(() => jest.clearAllMocks());

  it('fetches counties and transforms the response', async () => {
    mockGet.mockResolvedValue({ data: [sampleBackendCounty] });

    const counties = await getCounties();
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(counties).toHaveLength(1);
    expect(counties[0].name).toBe('Nairobi');
  });

  it('derives fiscal_grade from financial_health_score, never audit_rating', async () => {
    mockGet.mockResolvedValue({ data: [sampleBackendCounty] });

    const counties = await getCounties();
    // score 72 → B+ — exposed as fiscal_grade (a utilisation-derived
    // estimate), NOT as audit_rating (reserved for real OAG opinions).
    expect(counties[0].fiscal_grade).toBe('B+');
    // Backend mirrors severity ("info") into audit_rating — that's a
    // status, not a rating, so it must not surface as one.
    expect(counties[0].audit_rating).toBe('');
  });

  it('passes through a real letter-grade audit_rating unchanged', async () => {
    mockGet.mockResolvedValue({
      data: [{ ...sampleBackendCounty, audit_rating: 'A-' }],
    });

    const counties = await getCounties();
    expect(counties[0].audit_rating).toBe('A-');
  });

  it('sets auditStatus from backend data', async () => {
    mockGet.mockResolvedValue({ data: [sampleBackendCounty] });

    const counties = await getCounties();
    expect(counties[0].auditStatus).toBe('qualified');
  });

  it('applies search filter', async () => {
    mockGet.mockResolvedValue({ data: [] });

    await getCounties({ search: 'Mombasa' });
    const calledUrl = mockGet.mock.calls[0][0];
    expect(calledUrl).toContain('search=Mombasa');
  });

  it('applies budget range filter', async () => {
    mockGet.mockResolvedValue({ data: [] });

    await getCounties({ budgetRange: [1000, 5000] });
    const calledUrl = mockGet.mock.calls[0][0];
    expect(calledUrl).toContain('budget_min=1000');
    expect(calledUrl).toContain('budget_max=5000');
  });

  it('handles empty response', async () => {
    mockGet.mockResolvedValue({ data: [] });

    const counties = await getCounties();
    expect(counties).toEqual([]);
  });
});

describe('getCounty', () => {
  beforeEach(() => jest.clearAllMocks());

  it('fetches a single county by id', async () => {
    mockGet.mockResolvedValue({ data: sampleBackendCounty });

    const county = await getCounty('1');
    expect(mockGet).toHaveBeenCalledWith('/counties/1');
    expect(county.name).toBe('Nairobi');
  });
});

describe('getCountyByCode', () => {
  beforeEach(() => jest.clearAllMocks());

  it('fetches county by code', async () => {
    mockGet.mockResolvedValue({ data: { data: { id: '1', name: 'Nairobi' } } });

    const county = await getCountyByCode('NBI');
    expect(mockGet).toHaveBeenCalledWith('/counties/code/NBI');
    expect(county.name).toBe('Nairobi');
  });
});

describe('searchCounties', () => {
  beforeEach(() => jest.clearAllMocks());

  it('calls search endpoint with query param', async () => {
    mockGet.mockResolvedValue({ data: { data: [] } });

    await searchCounties('Kisumu');
    const calledUrl = mockGet.mock.calls[0][0];
    expect(calledUrl).toContain('/counties/search');
    expect(calledUrl).toContain('q=Kisumu');
  });
});

describe('getCountyComprehensive', () => {
  beforeEach(() => jest.clearAllMocks());

  it('fetches comprehensive county data', async () => {
    mockGet.mockResolvedValue({ data: { id: '5', name: 'Test' } });

    const result = await getCountyComprehensive('5');
    expect(mockGet).toHaveBeenCalledWith('/counties/5/comprehensive');
    expect(result.id).toBe('5');
  });
});
