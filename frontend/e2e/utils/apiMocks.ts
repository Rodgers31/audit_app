/**
 * Extended API mocks for the post-v1.1 feature set.
 *
 * These are additive to `mockApi.ts` — use `registerApiMocks(page)` for
 * the legacy shape and `registerAllApiMocks(page)` when you need the
 * full (post-v1.1) surface area including:
 *   - /sectors/spending
 *   - /accountability/missing-funds
 *   - /sources/summary
 *   - /counties/{id}/comprehensive, /accountability, /money-flow
 *   - /audits/fiscal-years, /audits/statistics
 *
 * Mocks deliberately return plausible but distinctive numbers so the
 * specs can assert on them without worrying about real-data drift.
 */
import type { Page, Request, Route } from '@playwright/test';
import { registerApiMocks } from './mockApi';

const SECTOR_SPENDING = {
  total_allocated: 405_099_999_999.98,
  total_spent: 167_649_251_488.17,
  counties_reporting: 47,
  sectors: [
    {
      sector: 'Health',
      allocated: 101_275_000_000.01,
      spent: 45_028_455_040.5,
      utilization_pct: 44.5,
      county_count: 47,
      top_counties: [
        { county: 'Nairobi', allocated: 5_725_981_111.38, spent: 2_061_353_200.1 },
        { county: 'Nakuru', allocated: 3_363_274_514.95, spent: 1_849_800_983.22 },
      ],
    },
    {
      sector: 'Education',
      allocated: 81_000_000_000,
      spent: 37_400_000_000,
      utilization_pct: 46.2,
      county_count: 47,
      top_counties: [
        { county: 'Nairobi', allocated: 4_380_637_042.8, spent: 1_800_000_000 },
      ],
    },
  ],
};

const MISSING_FUNDS = {
  total_amount: 250_000_000,
  total_cases: 3,
  affected_counties: 3,
  by_status: {
    active_investigation: 120_000_000,
    recovery_ongoing: 85_000_000,
    resolved: 45_000_000,
  },
  top_counties: [
    { county: 'Nairobi', cases: 1, amount: 120_000_000 },
    { county: 'Mombasa', cases: 1, amount: 85_000_000 },
    { county: 'Kisumu', cases: 1, amount: 45_000_000 },
  ],
  cases: [
    {
      case_id: 'CASE-001',
      county: 'Nairobi',
      amount: 120_000_000,
      amount_label: 'KES 120M',
      period: 'FY2023/24',
      status: 'active_investigation',
      description: 'Irregular procurement of medical supplies.',
    },
  ],
};

const SOURCES_SUMMARY = {
  sources: [
    {
      publisher: 'Controller of Budget',
      short: 'COB',
      role: 'Tracks how counties and national MDAs spend their budgets each quarter.',
      website: 'https://cob.go.ke',
      document_count: 320,
      last_fetched: '2026-04-19T00:00:00Z',
      last_seen_at: '2026-04-20T00:00:00Z',
      doc_types: { budget: 220, report: 100 },
    },
  ],
  total_documents: 2294,
};

const COUNTY_COMPREHENSIVE = (id: string) => ({
  id,
  name: id === '047' ? 'Mombasa' : id === '001' ? 'Nairobi' : 'Test County',
  slug: `${id}-county`,
  coordinates: [39.6682, -4.0435],
  demographics: { population: 1_208_333, population_year: 2019 },
  governor: 'Test Governor',
  economic_profile: { economic_base: 'trade_logistics', county_type: 'port_city' },
  budget: {
    total_allocated: 9_010_000_000,
    total_spent: 6_980_000_000,
    utilization_rate: 77.5,
    development_budget: 0,
    recurrent_budget: 9_010_000_000,
    per_capita_budget: 7_500,
    sector_breakdown: {
      'Health Services': { allocated: 2_250_000_000, spent: 1_820_000_000 },
      Education: { allocated: 1_800_000_000, spent: 1_440_000_000 },
    },
    fiscal_year: 'FY2024/25',
  },
  revenue: { own_source: 500_000_000, equitable_share: 8_510_000_000 },
  debt: {
    total_debt: 20_890_000_000,
    pending_bills: 13_080_000_000,
    breakdown: {},
    per_capita_debt: 17_289,
  },
  audit: {
    status: 'qualified',
    grade: 'C',
    health_score: 49,
    findings_count: 16,
    total_amount_involved: 129_800_000,
    by_severity: { critical: 3, warning: 8, info: 5 },
    findings: [],
  },
  health_history: [
    { fy: 'FY2022/23', score: 72, grade: 'B+' },
    { fy: 'FY2023/24', score: 75, grade: 'B+' },
    { fy: 'FY2024/25', score: 78, grade: 'B+' },
  ],
  missing_funds: { total_amount: 120_000_000, cases_count: 1, cases: [] },
  stalled_projects: {
    count: 2,
    total_contracted_value: 500_000_000,
    total_amount_paid: 300_000_000,
    projects: [],
  },
  financial_summary: {
    health_score: 78,
    grade: 'B+',
    budget_execution_rate: 77.5,
    pending_bills_ratio: 145.2,
    debt_sustainability: 'at_risk',
  },
  data_sources: {},
});

const COUNTY_ACCOUNTABILITY = {
  county_id: '001',
  county_name: 'Test County',
  audit_opinion_history: [
    { year: 2023, opinion: 'qualified' },
    { year: 2024, opinion: 'qualified' },
  ],
  audit_severity_history: [
    { year: 2023, score: 65, info: 5, warning: 8, critical: 3 },
  ],
  total_flagged_amount: 129_800_000,
  total_findings: 16,
  critical_findings: 3,
  warning_findings: 8,
  recurring_findings_count: 2,
  unresolved_findings_count: 10,
  absorption_rate: 0.775,
  flagged_pct_of_budget: 1.44,
  accountability_grade: 'C',
  accountability_score: 61,
  grade_factors: [],
  peer_comparison: {
    region: 'Coast',
    region_avg_flagged_amount: 80_000_000,
    region_avg_grade: 'C',
    population_bracket: '1M-2M',
    population_bracket_avg: 100_000_000,
  },
};

const MONEY_FLOW = {
  county_id: 3,
  county_name: 'Nairobi County',
  fiscal_year: 'FY2024/25',
  stages: [
    {
      stage: 'Allocated',
      label: 'Budget Allocation',
      amount: 21_903_185_214,
      source: 'CRA Allocation + Conditional Grants',
      source_doc: 'https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/',
    },
    {
      stage: 'Spent',
      label: 'Actual Expenditure',
      amount: 18_116_124_490.51,
      gap_from_prev: 3_787_060_723.49,
      gap_label: 'Unspent Funds',
    },
    {
      stage: 'Flagged',
      label: 'Auditor Flagged',
      amount: 92_937_910,
      gap_label: 'Irregular/Unsupported Expenditure',
    },
  ],
  total_waste_estimate: 92_937_910,
  efficiency_score: 82.71,
  source_document_title: 'CoB County Budget Implementation Review Report FY2024/25 H1',
  source_document_url: 'https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/',
  committed_amount: 4_148_463_279.52,
};

const FISCAL_YEARS = {
  status: 'success',
  data: ['FY2025/26', 'FY2024/25', 'FY2023/24', 'FY2022/23'],
};

function json(body: unknown, status = 200) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  };
}

export async function registerAllApiMocks(page: Page): Promise<void> {
  // Layer the legacy fixtures first so `/counties`, `/debt/*` still mock.
  await registerApiMocks(page);

  await page.route('**/api/v1/**', async (route: Route, request: Request) => {
    const url = request.url();

    if (url.includes('/sectors/spending')) return route.fulfill(json(SECTOR_SPENDING));
    if (url.includes('/accountability/missing-funds'))
      return route.fulfill(json(MISSING_FUNDS));
    if (url.includes('/sources/summary')) return route.fulfill(json(SOURCES_SUMMARY));
    if (url.includes('/audits/fiscal-years')) return route.fulfill(json(FISCAL_YEARS));
    if (/\/counties\/[^/]+\/comprehensive/.test(url)) {
      const id = url.match(/\/counties\/([^/?]+)\/comprehensive/)?.[1] ?? '001';
      return route.fulfill(json(COUNTY_COMPREHENSIVE(id)));
    }
    if (/\/counties\/[^/]+\/accountability/.test(url))
      return route.fulfill(json(COUNTY_ACCOUNTABILITY));
    if (/\/counties\/[^/]+\/money-flow/.test(url)) return route.fulfill(json(MONEY_FLOW));

    return route.continue();
  });
}

/** Register mocks that deliberately fail, for error-state tests. */
export async function registerFailingApiMocks(page: Page): Promise<void> {
  await page.route('**/api/v1/**', async (route: Route) => {
    return route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'mock-induced 500' }),
    });
  });
}
