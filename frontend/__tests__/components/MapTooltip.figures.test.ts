/**
 * Derived figures on the map tooltip must withhold, not fabricate.
 *
 * Both helpers here exist because the tooltip cannot fix the problem at the
 * point of render: it used to compute
 *
 *   const debtRatio  = county.budget ? ((county.debt || 0) / county.budget) * 100 : 0;
 *   const fundingGap = (county.budget || 0) - (county.moneyReceived || 0);
 *
 * so a county whose debt or transfers the API never published got a confident
 * "0.0%" debt ratio, and — worse — a "Funding gap" alert for its ENTIRE budget,
 * because subtracting an absent `moneyReceived` as 0 turns "we don't know what
 * this county received" into "this county received nothing".
 *
 * Neither is a rendering bug, so neither is fixable in the JSX. The rule is
 * that a derived claim is only made when every input it rests on was actually
 * published.
 */
import { countyDebtRatio, countyFundingGap, getFinancialTrend } from '@/components/map/MapUtilities';
import { County } from '@/types';

/** A county carrying only the fields these helpers read. */
const county = (over: Partial<County> = {}): County =>
  ({
    id: 'baringo',
    name: 'Baringo',
    population: 666_763,
    budget_2025: 9_542_030_000,
    financial_health_score: 42.9,
    audit_rating: '',
    fiscal_grade: 'B-',
    ...over,
  }) as County;

describe('countyDebtRatio', () => {
  it('computes the ratio when both figures were published', () => {
    const r = countyDebtRatio(county({ budget: 9_542_030_000, debt: 450_065_025 }));
    expect(r).toBeCloseTo(4.7167, 4);
  });

  it('withholds when debt was not published', () => {
    expect(countyDebtRatio(county({ budget: 9_542_030_000 }))).toBeNull();
  });

  it('withholds when budget was not published', () => {
    expect(countyDebtRatio(county({ debt: 450_065_025 }))).toBeNull();
  });

  it('withholds rather than dividing by zero', () => {
    expect(countyDebtRatio(county({ budget: 0, debt: 450_065_025 }))).toBeNull();
  });

  it('reports a genuine zero debt against a published budget as 0%', () => {
    // Distinct from absence: the caller passed a real 0, not `undefined`.
    expect(countyDebtRatio(county({ budget: 9_542_030_000, debt: 0 }))).toBe(0);
  });
});

describe('countyFundingGap', () => {
  it('computes the gap when both figures were published', () => {
    const g = countyFundingGap(county({ budget: 9_542_030_000, moneyReceived: 4_093_530_870 }));
    expect(g).toBe(5_448_499_130);
  });

  it('withholds when the API never published what the county received', () => {
    // The defect this test exists for: an absent `moneyReceived` used to
    // produce a funding-gap alert for the county's entire budget.
    expect(countyFundingGap(county({ budget: 9_542_030_000 }))).toBeNull();
  });

  it('withholds when the budget was not published', () => {
    expect(countyFundingGap(county({ moneyReceived: 4_093_530_870 }))).toBeNull();
  });

  it('returns a non-positive gap unchanged so the caller decides', () => {
    expect(countyFundingGap(county({ budget: 9_542_030_000, moneyReceived: 9_542_030_000 }))).toBe(
      0
    );
  });
});

describe('getFinancialTrend', () => {
  it('withholds a trend when the county reported no execution', () => {
    // Previously this county landed in the lowest ("poor") colour bucket,
    // which reads as a judgement on a county that simply did not report.
    expect(getFinancialTrend(county({ budget: 9_542_030_000, debt: 450_065_025 }))).toBe('unknown');
  });

  it('still grades a county that did report', () => {
    expect(
      getFinancialTrend(
        county({ budgetUtilization: 95, budget: 9_542_030_000, debt: 450_065_025 })
      )
    ).toBe('excellent');
  });

  it('does not treat absent debt as a debt-free county', () => {
    // 95% execution with no debt figure must not be graded "excellent" on the
    // strength of a debt ratio computed from a zero nobody published.
    expect(getFinancialTrend(county({ budgetUtilization: 95, budget: 9_542_030_000 }))).toBe(
      'unknown'
    );
  });
});
