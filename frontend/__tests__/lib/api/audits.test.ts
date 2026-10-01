/**
 * Tests for lib/api/audits.ts
 *
 * Covers:
 *  getAuditReports       – list with filters
 *  getAuditReport        – single by ID
 *  getCountyAuditReports – county-specific audits
 *  getLatestCountyAudit  – latest audit for county
 *  getAuditStatistics    – aggregated stats
 */

import {
  getAuditReport,
  getAuditReports,
  getAuditStatistics,
  getCountyAuditReports,
  getLatestCountyAudit,
} from '@/lib/api/audits';
import { apiClient } from '@/lib/api/axios';

jest.mock('@/lib/api/axios', () => ({
  apiClient: {
    get: jest.fn(),
  },
}));

const mockGet = apiClient.get as jest.MockedFunction<typeof apiClient.get>;

const sampleAudit = {
  id: '1',
  countyId: '47',
  countyName: 'Nairobi',
  fiscalYear: 'FY2024',
  auditStatus: 'qualified',
  auditOpinion: 'Qualified Opinion',
  auditDate: '2024-06-15',
  findings: [],
  summary: {
    headline: 'Test',
    summary: 'Test summary',
    keyFindings: [],
    concern_level: 'medium',
  },
  financialData: {
    totalBudget: 38_000_000_000,
    budgetUtilization: 79,
    revenueCollection: 12_000_000_000,
    pendingBills: 3_000_000_000,
  },
};

describe('getAuditReports', () => {
  beforeEach(() => jest.clearAllMocks());

  it('calls /audits and returns data', async () => {
    mockGet.mockResolvedValue({ data: { data: [sampleAudit] } });

    const audits = await getAuditReports();
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(audits).toHaveLength(1);
    expect(audits[0].countyName).toBe('Nairobi');
  });

  it('applies county filter', async () => {
    mockGet.mockResolvedValue({ data: { data: [] } });

    await getAuditReports({ countyId: '47' });
    const url = mockGet.mock.calls[0][0];
    expect(url).toContain('county_id=47');
  });

  it('applies fiscal year filter', async () => {
    mockGet.mockResolvedValue({ data: { data: [] } });

    await getAuditReports({ fiscalYear: 'FY2024' });
    const url = mockGet.mock.calls[0][0];
    expect(url).toContain('fiscal_year=FY2024');
  });
});

describe('getAuditReport', () => {
  beforeEach(() => jest.clearAllMocks());

  it('fetches single audit by ID', async () => {
    mockGet.mockResolvedValue({ data: { data: sampleAudit } });

    const audit = await getAuditReport('1');
    expect(mockGet).toHaveBeenCalledWith('/audits/1');
    expect(audit.id).toBe('1');
  });
});

describe('getCountyAuditReports', () => {
  beforeEach(() => jest.clearAllMocks());

  it('fetches audits for a specific county', async () => {
    mockGet.mockResolvedValue({ data: { data: [sampleAudit] } });

    const audits = await getCountyAuditReports('47');
    const url = mockGet.mock.calls[0][0];
    expect(url).toContain('/counties/47/audits');
  });

  it('applies fiscal year filter', async () => {
    mockGet.mockResolvedValue({ data: { data: [] } });

    await getCountyAuditReports('47', 'FY2024');
    const url = mockGet.mock.calls[0][0];
    expect(url).toContain('fiscal_year=FY2024');
  });
});

describe('getLatestCountyAudit', () => {
  beforeEach(() => jest.clearAllMocks());

  it('fetches latest audit for county', async () => {
    mockGet.mockResolvedValue({ data: { data: sampleAudit } });

    const audit = await getLatestCountyAudit('47');
    expect(mockGet).toHaveBeenCalledWith('/counties/47/audits/latest');
    expect(audit.fiscalYear).toBe('FY2024');
  });
});

describe('getAuditStatistics', () => {
  beforeEach(() => jest.clearAllMocks());

  it('fetches audit statistics', async () => {
    const stats = { total_findings: 4, counties_audited: 1, total_amount_flagged: 600 };
    mockGet.mockResolvedValue({ data: stats });

    const result = await getAuditStatistics();
    expect(mockGet).toHaveBeenCalledWith('/audits/statistics');
    expect(result).toEqual(stats);
  });
});
