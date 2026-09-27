import { render, screen } from '@testing-library/react';
import FinancialOverview from '@/components/audit-report-card/FinancialOverview';
import OverviewTab from '@/app/counties/[id]/tabs/OverviewTab';
import { countyRevenueNotes } from '@/lib/counties/revenueNotes';
import type { County, CountyComprehensive, CountyRevenue } from '@/types';

const mockTranslate = (key: string) => ({
  'county.revenue.cash_receipts': 'Mapato ya ndani yaliyopokelewa',
  'county.revenue.summary_actual_realised': 'Jedwali la muhtasari “Actual Realised”',
  'county.revenue.amount': '{label}: {amount}',
  'county.revenue.summary_differs': 'Jedwali la muhtasari “Actual Realised”: {amount}; hutofautiana na fedha zilizopokelewa',
  'county.revenue.cash_and_opening_balance': 'Fedha zilizopokelewa na salio la mwanzo',
}[key] || key);

jest.mock('@/lib/i18n/LangProvider', () => ({
  useLang: () => ({ lang: 'sw', t: mockTranslate }),
}));
jest.mock('@/lib/data/county-officials', () => ({ getCountyOfficials: () => ({}) }));

const revenue: CountyRevenue = {
  total_revenue: 100, total_revenue_target: null,
  equitable_share: null, equitable_share_target: null, additional_allocations: null,
  local_revenue: 40, own_source_target: null,
  local_revenue_basis: 'cash_receipts',
  total_revenue_basis: 'cash_receipts_including_opening_balance',
  summary_table_own_source_revenue: 90,
  own_source_disagreement: { summary_table: 90, county_revenue_table: 40 },
  streams: [], fiscal_year: 'FY2025/26', source: 'Controller of Budget', total_revenue_absent_reason: null,
};

it('passes the selected translator through cash and disagreement notes', () => {
  // Extra JS argument is ignored by the old implementation, reproducing
  // English notes even when a caller provides the selected language.
  expect(countyRevenueNotes(revenue, String, mockTranslate)).toEqual([
    'FY2025/26',
    'Mapato ya ndani yaliyopokelewa: 40',
    'Jedwali la muhtasari “Actual Realised”: 90; hutofautiana na fedha zilizopokelewa',
  ]);
});

it('translates the report-card cash label and explanatory note', () => {
  render(<FinancialOverview county={{ revenue, revenueCollection: 40 } as County} />);
  expect(screen.getByText('Mapato ya ndani yaliyopokelewa')).toBeVisible();
  expect(screen.getByText(/hutofautiana na fedha zilizopokelewa/)).toBeVisible();
  expect(document.body.textContent).not.toContain('Own-source cash receipts');
});

it('translates the county overview cash-and-opening-balance KPI and notes', () => {
  const data = {
    id: 'example', revenue,
    budget: { utilization_rate: 0 }, debt: {},
    audit: { findings_count: 0, findings: [], by_severity: {} },
    missing_funds: { total_amount: 0, cases_count: 0, cases: [] },
    financial_summary: { debt_sustainability: 'unknown' },
    demographics: {}, economic_profile: { major_issues: [] },
  } as unknown as CountyComprehensive;
  render(<OverviewTab data={data} />);
  expect(screen.getByText('Fedha zilizopokelewa na salio la mwanzo')).toBeVisible();
  expect(screen.getByText(/hutofautiana na fedha zilizopokelewa/)).toBeVisible();
  expect(document.body.textContent).not.toContain('Cash receipts and opening balance');
});
