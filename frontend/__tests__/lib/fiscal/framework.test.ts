import {
  frameworkOf,
  frameworkSources,
  frameworkUses,
} from '@/lib/fiscal/framework';
import { FF_2023_24_ACTUAL, FF_2026_27 } from '@/test/fixtures/fiscalFramework';

describe('frameworkUses — one basis, one total (issue #237)', () => {
  it('splits interest out of recurrent and reconciles to the column total', () => {
    const u = frameworkUses(FF_2026_27)!;
    expect(u.total).toBe(4785.2);
    expect(u.interest).toBe(1254.2);
    // 3,538.7 - 1,254.2. The old bars subtracted debt service INCLUDING
    // principal (2,315.9), which gave 1,222.8 — 1,061.7B too small.
    expect(u.recurrentExInterest).toBeCloseTo(2284.5, 5);
    expect(u.interest + u.recurrentExInterest + u.development + u.counties + u.contingency).toBeCloseTo(
      4785.2,
      5,
    );
  });

  it('refuses a split that does not add up to its total', () => {
    expect(frameworkUses({ ...FF_2026_27, development_billion: 849.0 })).toBeNull();
  });

  it('refuses when any part is absent — absence is not zero', () => {
    expect(frameworkUses({ ...FF_2026_27, contingency_billion: null })).toBeNull();
  });

  it('only draws the basis it knows', () => {
    expect(frameworkOf({ fiscal_framework: { ...FF_2026_27, basis: 'cob_gross' } })).toBeNull();
    expect(frameworkOf({ fiscal_framework: null })).toBeNull();
    expect(frameworkOf({ fiscal_framework: FF_2026_27 })).toBe(FF_2026_27);
  });
});

describe('frameworkSources — reconciles through printed rows only', () => {
  it('budget year: revenue + A-i-A + grants + borrowing = spending', () => {
    const s = frameworkSources(FF_2026_27)!;
    expect(s.tax).toBe(2858.7);
    expect(s.nonTax).toBe(127.1);
    expect(s.cashAdjustment).toBe(0);
    expect(s.ordinaryRevenue + s.aia + s.grants + s.borrowing).toBeCloseTo(4785.1, 5);
  });

  it('settled year: the table\'s cash-basis adjustment and discrepancy close the gap', () => {
    const s = frameworkSources(FF_2023_24_ACTUAL)!;
    // 45.4 - (-16.8) = 62.2, both printed rows.
    expect(s.cashAdjustment).toBeCloseTo(62.2, 5);
  });

  it('an absent adjustment row refuses rather than counting as zero', () => {
    expect(
      frameworkSources({ ...FF_2023_24_ACTUAL, adjustment_to_cash_basis_billion: null }),
    ).toBeNull();
    expect(
      frameworkSources({ ...FF_2026_27, statistical_discrepancy_billion: undefined }),
    ).toBeNull();
  });

  it('a tax split that does not add up to ordinary revenue is dropped, the rest kept', () => {
    const s = frameworkSources({ ...FF_2026_27, non_tax_revenue_billion: 227.1 })!;
    expect(s.tax).toBeNull();
    expect(s.nonTax).toBeNull();
    expect(s.ordinaryRevenue).toBe(2985.7);
  });
});
