/**
 * Issue #235: the loans API sent "0.00%" and 0 for 45 of 48 rows and the
 * homepage card showed them. These pin how an absent, modelled or published
 * figure is shown, and that the headline is the published debt service.
 */
import type { NationalLoan } from '@/lib/api/debt';
import {
  annualCostCell,
  annualDebtServiceHeadline,
  rateCell,
  sortLoans,
} from '@/lib/debt/loanInterest';
import { computeRevenueAllocation, fiscalSourceLine, ratioWorking } from '@/lib/debt/revenueAllocation';

const base: NationalLoan = {
  lender: 'X',
  lender_type: 'external_bilateral',
  principal: '1',
  outstanding: '1',
  issue_date: '2024-12-31',
  maturity_date: '',
  status: null,
  outstanding_numeric: 1,
  principal_numeric: 1,
  interest_rate: null,
  interest_rate_pct: null,
  interest_rate_basis: null,
  interest_rate_label: null,
  interest_rate_source: null,
  interest_rate_absent_reason: 'No publisher gives a rate.',
  annual_service_cost: null,
  annual_service_basis: null,
  annual_service_label: null,
  annual_service_source: null,
  annual_service_absent_reason: 'No interest figure.',
};

const bonds: NationalLoan = {
  ...base,
  lender: 'Domestic Treasury Bonds',
  outstanding_numeric: 5579e9,
  interest_rate: '13.41%',
  interest_rate_pct: 13.41,
  interest_rate_basis: 'coupon_weighted_average',
  interest_rate_label: 'Average coupon of the 56 bonds in CBK’s register',
  interest_rate_absent_reason: null,
  annual_service_cost: 748e9,
  annual_service_basis: 'modelled',
  annual_service_label: 'Modelled: balance × coupon',
  annual_service_absent_reason: null,
};

const china: NationalLoan = {
  ...base,
  lender: 'Bilateral (China)',
  outstanding_numeric: 723e9,
  annual_service_cost: 45e9,
  annual_service_basis: 'published',
  annual_service_label: 'Interest paid in 2024',
  annual_service_absent_reason: null,
};

describe('register cells', () => {
  it('an absent rate is null with its reason, never 0', () => {
    const c = rateCell(base);
    expect(c.value).toBeNull();
    expect(c.title).toBe('No publisher gives a rate.');
  });

  it('a modelled cost is tagged modelled', () => {
    expect(annualCostCell(bonds)).toMatchObject({ value: 748e9, tag: 'modelled' });
  });

  it('published interest paid is tagged with its year', () => {
    expect(annualCostCell(china)).toMatchObject({ value: 45e9, tag: 'paid 2024' });
  });

  it('a coupon average and an auction yield are told apart', () => {
    expect(rateCell(bonds).tag).toBe('avg coupon');
    expect(rateCell({ ...bonds, interest_rate_basis: 'auction_yield' }).tag).toBe('91-day yield');
  });
});

describe('sortLoans', () => {
  it('puts absent figures last instead of ranking them as zero', () => {
    const cheapest = { ...china, lender: 'cheap', interest_rate_pct: 0.5 };
    const order = sortLoans([base, bonds, cheapest], 'rate').map((l) => l.lender);
    expect(order).toEqual(['Domestic Treasury Bonds', 'cheap', 'X']);
  });

  it('by service cost, absent last', () => {
    const order = sortLoans([base, china, bonds], 'service').map((l) => l.lender);
    expect(order).toEqual(['Domestic Treasury Bonds', 'Bilateral (China)', 'X']);
  });
});

describe('annualDebtServiceHeadline', () => {
  it('is the published figure with its year and document', () => {
    const h = annualDebtServiceHeadline({
      value_kes: 2_315_900_000_000,
      fiscal_year: 'FY 2026/27',
      measure: 'Total debt service',
      source: {
        publisher: 'The National Treasury',
        title: 'Programme Based Budget FY 2026/27 (Approved)',
        url: 'https://x',
        page: 'CFS summary PDF p.1193',
      },
      absent_reason: null,
    });
    expect(h.value).toBe(2_315_900_000_000);
    expect(h.period).toBe('FY 2026/27');
    expect(h.sourceTitle).toBe('Programme Based Budget FY 2026/27 (Approved)');
    expect(h.title).toContain('CFS summary PDF p.1193');
  });

  it('is absent with the reason when nothing is published', () => {
    const h = annualDebtServiceHeadline({ value_kes: null, absent_reason: 'none sourced' });
    expect(h.value).toBeNull();
    expect(h.title).toBe('none sourced');
  });
});

describe('fiscalSourceLine', () => {
  it('names the debt-service document, not a year pinned in the code', () => {
    const line = fiscalSourceLine({
      fiscal_year: 'FY 2026/27',
      debt_service_source: {
        publisher: 'The National Treasury',
        title: 'Programme Based Budget FY 2026/27 (Approved)',
        page: 'CFS summary PDF p.1193',
      },
    });
    expect(line).toBe(
      'FY 2026/27 debt service is from The National Treasury, Programme Based Budget FY 2026/27 (Approved) (CFS summary PDF p.1193).'
    );
    expect(line).not.toMatch(/FY2025\/26|APDMR/);
  });

  it('does not borrow the budget figure’s citation', () => {
    const line = fiscalSourceLine({
      fiscal_year: 'FY 2025/26',
      budget_basis_source: { title: 'COB nine-month report' },
    });
    expect(line).toBe("The source document for FY 2025/26's debt-service figure is not recorded.");
  });
});

describe('ratioWorking', () => {
  it('prints trillions from raw KES, not raw KES with a T on it', () => {
    const a = computeRevenueAllocation({
      fiscal_year: 'FY 2026/27',
      total_revenue: 2_985_700_000_000,
      debt_service_cost: 2_315_900_000_000,
      debt_service_per_shilling: 77.6,
      recurrent_spending: 2_850_000_000_000,
      development_spending: 672_000_000_000,
      county_allocation: 420_000_000_000,
    })!;
    const w = ratioWorking(a);
    expect(w).toContain('KSh 2.316T');
    expect(w).toContain('KSh 2.986T');
    expect(w).toContain('≈ 77.6');
    expect(w).not.toMatch(/\d{6,}/);
  });
});
