import { countyRevenueNotes } from '@/lib/counties/revenueNotes';
import type { CountyRevenue } from '@/types';

const receipt: CountyRevenue = {
  total_revenue: 15790774484, total_revenue_target: null,
  equitable_share: null, equitable_share_target: null, additional_allocations: null,
  local_revenue: 6214590483, own_source_target: null,
  local_revenue_basis: 'cash_receipts',
  total_revenue_basis: 'cash_receipts_including_opening_balance',
  summary_table_own_source_revenue: 21126230000,
  own_source_disagreement: { summary_table: 21126230000, county_revenue_table: 6214590483 },
  streams: [], fiscal_year: 'FY2025/26', source: 'Controller of Budget', total_revenue_absent_reason: null,
};

test('both card consumers retain period and separately labelled cash and summary measures', () => {
  expect(countyRevenueNotes(receipt, String)).toEqual([
    'FY2025/26', 'Own-source cash receipts: 6214590483',
    'Summary table “Actual Realised”: 21126230000; differs from cash receipts',
  ]);
});

test('printed zero remains a figure; absence does not become cash', () => {
  expect(countyRevenueNotes({ ...receipt, local_revenue: 0, own_source_disagreement: null }, String)).toContain('Own-source cash receipts: 0');
  expect(countyRevenueNotes({ ...receipt, local_revenue: null, own_source_disagreement: null }, String)).toEqual(['FY2025/26']);
  expect(countyRevenueNotes({ ...receipt, local_revenue_basis: 'summary_table_actual_realised', own_source_disagreement: null }, String)[1]).toBe('Summary table “Actual Realised”: 6214590483');
});
