import { render, screen } from '@testing-library/react';
import OverviewTab from '@/app/counties/[id]/tabs/OverviewTab';
import FinancialOverview from '@/components/audit-report-card/FinancialOverview';
import { countyRevenueNotes } from '@/lib/counties/revenueNotes';
import { MESSAGES, type TranslationKey } from '@/lib/i18n/messages';
import type { County, CountyComprehensive, CountyRevenue } from '@/types';

jest.mock('@/lib/i18n/LangProvider', () => ({
  useLang: () => ({ lang: 'en', t: (key: TranslationKey) => MESSAGES[key].en }),
}));

const absent: CountyRevenue = {
  total_revenue: null, total_revenue_target: null, equitable_share: null,
  equitable_share_target: null, additional_allocations: null, local_revenue: null,
  own_source_target: null, streams: [], fiscal_year: 'FY2025/26', source: null,
  total_revenue_absent_reason: 'streams_do_not_sum_to_grand_total (out by 59,814,318.00)',
};

test.each([
  ['streams_do_not_sum_to_grand_total (out by 59,814,318.00)', 'Cash receipt streams do not reconcile to the printed total.'],
  ['a_section_has_two_subtotals', 'Cash receipt subtotals are ambiguous.'],
  ['unobserved_receipts_cell', 'A required cash receipt cell is missing.'],
  ['streams_do_not_sum_to_grand_total (out by 24,413)', 'Cash receipt streams do not reconcile to the printed total.'],
])('overview identifies the refusal %s without publishing zero', (reason, explanation) => {
  const revenue = { ...absent, total_revenue_absent_reason: reason };
  const data = {
    id: 'kwale-county', revenue, budget: { utilization_rate: 0 }, debt: {},
    audit: { findings_count: 0, findings: [], by_severity: {} },
    missing_funds: { total_amount: null, cases_count: 0, cases: [] },
    financial_summary: { debt_sustainability: 'unknown' },
    demographics: {}, economic_profile: { major_issues: [] },
  } as unknown as CountyComprehensive;
  render(<OverviewTab data={data} />);
  const label = screen.getByText('Total Revenue');
  expect(label.parentElement).toHaveTextContent('—');
  expect(label.parentElement).toHaveTextContent('Total cash receipts unavailable. ' + explanation);
  expect(label.parentElement).not.toHaveTextContent('KSh 0');
});

test('report card retains a separately labelled summary beside the cash qualification', () => {
  render(<FinancialOverview county={{ revenue: { ...absent, local_revenue: 50,
    local_revenue_basis: 'summary_table_actual_realised' }, revenueCollection: 50 } as County} />);
  expect(screen.getByText('Summary table “Actual Realised”')).toBeVisible();
  expect(screen.getByText(/Cash receipt streams do not reconcile/)).toBeVisible();
});

test.each(['en', 'sw', 'plain'] as const)('absence is localized in %s and never qualifies a measured zero', (lang) => {
  const translate = (key: TranslationKey) => MESSAGES[key][lang];
  expect(countyRevenueNotes(absent, String, translate).join(' ')).toContain(MESSAGES['county.revenue.total_unavailable'][lang]);
  expect(countyRevenueNotes({ ...absent, total_revenue: 0, total_revenue_absent_reason: null }, String, translate)).toEqual(['FY2025/26']);
});

test('the refusal note keeps the source institution and original PDF page locators', () => {
  expect(countyRevenueNotes({ ...absent, total_revenue_absence_source: {
    id: 1, url: 'https://cob.go.ke/report.pdf', pages: [385, 386, 387],
    publisher: 'Office of the Controller of Budget', title: 'Annual county report',
    basis: 'cash_receipts_including_opening_balance', unit: 'KES', artifact_sha256: null,
  } }, String, (key) => MESSAGES[key].en).join(' ').includes(
    'Office of the Controller of Budget, PDF pages 385, 386, 387')).toBe(true);
});
