/**
 * "The cost of debt over time" must not draw a share it cannot compute.
 *
 * Live data on 2026-09-04, from /api/v1/fiscal/summary:
 *
 *   FY 2022/23   service 1.162T   revenue 2.042T   -> 56.9%
 *   FY 2023/24   service 1.640T   revenue 2.406T   -> 68.2%
 *   FY 2024/25   service 1.854T   revenue 2.917T   -> 63.6%
 *   FY 2025/26   service 1.900T   revenue 2.910T   -> 65.3%
 *   FY 2026/27   service 2.316T   revenue NULL     -> withheld
 *
 * The old `: 0` fallback plotted that last row as 0%, so the gold line dived
 * from 65% to zero in the year debt service is at its largest — stating that
 * debt service will consume none of revenue. It is the year Treasury's
 * revenue estimate is not in our data, which is a different claim entirely.
 */
import { buildDebtServiceSeries, yearMissingRevenue } from '@/lib/debt/debtServiceSeries';

const T = 1_000_000_000_000;

const LIVE = [
  { fiscal_year: 'FY 2022/23', debt_service_cost: 1.162 * T, total_revenue: 2.042 * T },
  { fiscal_year: 'FY 2023/24', debt_service_cost: 1.64 * T, total_revenue: 2.406 * T },
  { fiscal_year: 'FY 2024/25', debt_service_cost: 1.854 * T, total_revenue: 2.917 * T },
  { fiscal_year: 'FY 2025/26', debt_service_cost: 1.9 * T, total_revenue: 2.91 * T },
  { fiscal_year: 'FY 2026/27', debt_service_cost: 2.3159 * T, total_revenue: null },
];

describe('buildDebtServiceSeries', () => {
  it('computes the share for every year that published both figures', () => {
    const s = buildDebtServiceSeries(LIVE);
    expect(s[0].ratio).toBeCloseTo(56.9, 1);
    expect(s[1].ratio).toBeCloseTo(68.2, 1);
    expect(s[2].ratio).toBeCloseTo(63.6, 1);
    expect(s[3].ratio).toBeCloseTo(65.3, 1);
  });

  it('withholds the share for the year with no published revenue', () => {
    // The regression: this was 0, drawn as a plunge to the axis.
    const s = buildDebtServiceSeries(LIVE);
    expect(s[4].ratio).toBeNull();
    expect(s[4].ratio).not.toBe(0);
  });

  it('still plots the debt service that WAS published for that year', () => {
    // Withholding the ratio must not withhold the figure beside it.
    const s = buildDebtServiceSeries(LIVE);
    expect(s[4].service).toBeCloseTo(2.3159 * T, 0);
    expect(s[4].year).toBe('FY 2026/27');
  });

  it('withholds the share when debt service is absent instead', () => {
    const s = buildDebtServiceSeries([
      { fiscal_year: 'FY 2027/28', debt_service_cost: null, total_revenue: 3 * T },
    ]);
    expect(s[0].service).toBeNull();
    expect(s[0].ratio).toBeNull();
  });

  it('refuses to divide by a zero revenue', () => {
    const s = buildDebtServiceSeries([
      { fiscal_year: 'FY 2027/28', debt_service_cost: 2 * T, total_revenue: 0 },
    ]);
    expect(s[0].ratio).toBeNull();
  });

  it('rejects non-finite figures rather than plotting NaN', () => {
    const s = buildDebtServiceSeries([
      { fiscal_year: 'FY 2027/28', debt_service_cost: Number.NaN, total_revenue: 3 * T },
      { fiscal_year: 'FY 2028/29', debt_service_cost: 2 * T, total_revenue: Number.POSITIVE_INFINITY },
    ]);
    expect(s[0].service).toBeNull();
    expect(s[1].ratio).toBeNull();
  });

  it('survives an empty or absent series', () => {
    expect(buildDebtServiceSeries([])).toEqual([]);
    expect(buildDebtServiceSeries(undefined as never)).toEqual([]);
  });
});

describe('yearMissingRevenue', () => {
  it('names the year whose revenue has not been published', () => {
    expect(yearMissingRevenue(LIVE)).toBe('FY 2026/27');
  });

  it('is null when every year with debt service also has revenue', () => {
    expect(yearMissingRevenue(LIVE.slice(0, 4))).toBeNull();
  });

  it('ignores a year that has neither figure', () => {
    // Nothing to explain: the chart never had a point to draw there.
    expect(
      yearMissingRevenue([{ fiscal_year: 'FY 2027/28', debt_service_cost: null, total_revenue: null }])
    ).toBeNull();
  });
});
