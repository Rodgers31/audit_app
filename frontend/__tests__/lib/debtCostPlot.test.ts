import { chartFiscalYears, ratioPath, serviceTicks } from '@/app/debt/debtCostPlot';
import { buildDebtServiceSeries } from '@/lib/debt/debtServiceSeries';

it('shares calendar positions, including an omitted year, without adding a financial observation', () => {
  const points = buildDebtServiceSeries([
    { fiscal_year: 'FY 2024/25', debt_service_cost: 250e9, total_revenue: 100e9 },
    { fiscal_year: '2026/27', debt_service_cost: 300e9, total_revenue: 600e9, debt_service_per_shilling: 50 },
    { fiscal_year: 'FY 2022/23', debt_service_cost: 180e9, total_revenue: 600e9, debt_service_per_shilling: 30 },
    { fiscal_year: 'FY 2025/29', debt_service_cost: 1e9 },
  ]);
  const years = chartFiscalYears(points);
  expect(years.map(year => year.shortYear)).toEqual(['FY22/23', 'FY23/24', 'FY24/25', 'FY25/26', 'FY26/27']);
  expect(years.map(year => year.point?.service ?? null)).toEqual([180e9, null, 250e9, null, 300e9]);
  expect(ratioPath(years.map(year => year.point?.ratio ?? null), 100)).toBe('M0.5,70 M4.5,50');
});

it('breaks the line at a withheld year without discarding a source-supported zero', () => {
  expect(ratioPath([0, 20, null, 100, 0], 100)).toBe('M0.5,100 L1.5,80 M3.5,0 L4.5,100');
  expect(ratioPath([null, null], 100)).toBe('');
});

it('uses at most four repayment ticks from zero through the plotted maximum', () => {
  expect(serviceTicks([0, null, 2.3159e12])).toEqual([0, 1e12, 2e12, 3e12]);
  expect(serviceTicks([null, 50e9])).toEqual([0, 20e9, 40e9, 60e9]);
});
