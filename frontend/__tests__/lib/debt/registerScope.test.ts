/**
 * The hero's row count must describe the rows the figure above it was summed
 * over.
 *
 * `GET /debt/national` returns `loan_count: 60` — every national loan row —
 * next to `total_outstanding: 11,855,978,858,225.68`, which the backend sums
 * with `_is_debt_loan` over the 47 rows that are not pending bills. The hero
 * read `loan_count` and published "Sum of our instrument register (60 rows)",
 * attributing an 11.86T figure to 13 rows that are not in it.
 *
 * Fixtures are the real payload from GET /api/v1/debt/national on 2026-09-06
 * (production, `5ff5fa9`).
 */

import {
  isDebtCategory,
  registerSourceLabel,
  summedRegisterRows,
  type RegisterCategories,
} from '@/lib/debt/registerScope';

/** GET /api/v1/debt/national → data.categories, 2026-09-06. */
const LIVE: RegisterCategories = {
  external_multilateral: {
    loan_count: 13,
    total_principal: 2_695_722_058_890.222,
    total_outstanding: 2_695_722_058_890.222,
  },
  external_bilateral: {
    loan_count: 17,
    total_principal: 1_087_508_999_335.458,
    total_outstanding: 1_087_508_999_335.458,
  },
  external_commercial: {
    loan_count: 12,
    total_principal: 1_014_147_800_000,
    total_outstanding: 1_014_147_800_000,
  },
  domestic_bonds: {
    loan_count: 2,
    total_principal: 5_878_982_400_000,
    total_outstanding: 5_878_982_400_000,
  },
  domestic_bills: {
    loan_count: 1,
    total_principal: 1_090_017_800_000,
    total_outstanding: 1_090_017_800_000,
  },
  domestic_overdraft: {
    loan_count: 2,
    total_principal: 89_599_800_000,
    total_outstanding: 89_599_800_000,
  },
  pending_bills: {
    loan_count: 13,
    total_principal: 931_300_000_000,
    total_outstanding: 931_300_000_000,
  },
};

/** data.total_outstanding for the same response. */
const LIVE_TOTAL = 11_855_978_858_225.68;
/** data.loan_count for the same response — what the label used to print. */
const LIVE_LOAN_COUNT = 60;

describe('summedRegisterRows — production payload', () => {
  it('counts the 47 rows the total was summed over, not the 60 rows in the table', () => {
    expect(summedRegisterRows(LIVE, LIVE_TOTAL)).toBe(47);
  });

  it('does not return the API loan_count', () => {
    // The defect in one line: the label read `loan_count` and printed 60.
    expect(summedRegisterRows(LIVE, LIVE_TOTAL)).not.toBe(LIVE_LOAN_COUNT);
  });

  it('excludes exactly the pending-bill rows', () => {
    expect(LIVE_LOAN_COUNT - summedRegisterRows(LIVE, LIVE_TOTAL)!).toBe(
      LIVE.pending_bills.loan_count,
    );
  });
});

describe('summedRegisterRows — withholds rather than guesses', () => {
  it('withholds when the categories do not add up to the published total', () => {
    // A category the response dropped: the count would describe a set larger
    // than the figure it labels.
    const { domestic_bills: _dropped, ...missing } = LIVE as Record<string, any>;
    expect(summedRegisterRows(missing, LIVE_TOTAL)).toBeNull();
  });

  it('withholds when a debt category carries no loan_count', () => {
    const noCount = { ...LIVE, domestic_bonds: { ...LIVE.domestic_bonds, loan_count: null } };
    expect(summedRegisterRows(noCount, LIVE_TOTAL)).toBeNull();
  });

  it('withholds when there are no categories at all', () => {
    expect(summedRegisterRows({}, LIVE_TOTAL)).toBeNull();
    expect(summedRegisterRows(null, LIVE_TOTAL)).toBeNull();
    expect(summedRegisterRows(undefined, LIVE_TOTAL)).toBeNull();
  });

  it('withholds when the published total is absent', () => {
    expect(summedRegisterRows(LIVE, null)).toBeNull();
    expect(summedRegisterRows(LIVE, undefined)).toBeNull();
  });

  it('withholds rather than dividing by a zero total', () => {
    expect(summedRegisterRows(LIVE, 0)).toBeNull();
  });

  it('counts a category that is genuinely empty rather than treating 0 as absence', () => {
    const withEmpty = {
      ...LIVE,
      county_guaranteed: { loan_count: 0, total_principal: 0, total_outstanding: 0 },
    };
    expect(summedRegisterRows(withEmpty, LIVE_TOTAL)).toBe(47);
  });

  it('reconciles on total_principal when total_outstanding is absent', () => {
    const principalOnly = Object.fromEntries(
      Object.entries(LIVE).map(([k, v]) => [k, { loan_count: v.loan_count, total_principal: v.total_principal }]),
    );
    expect(summedRegisterRows(principalOnly, LIVE_TOTAL)).toBe(47);
  });
});

describe('isDebtCategory', () => {
  it('keeps every borrowing category', () => {
    for (const key of [
      'external_multilateral',
      'external_bilateral',
      'external_commercial',
      'domestic_bonds',
      'domestic_bills',
      'domestic_overdraft',
      'county_guaranteed',
      'other',
    ]) {
      expect(isDebtCategory(key)).toBe(true);
    }
  });

  it('drops pending bills — unpaid invoices are not borrowed money', () => {
    expect(isDebtCategory('pending_bills')).toBe(false);
  });
});

describe('registerSourceLabel', () => {
  it('names the count and the exclusion that makes it differ from loan_count', () => {
    expect(registerSourceLabel(47)).toBe('Sum of 47 loan rows — pending bills excluded');
  });

  it('states no count when the count could not be established', () => {
    const label = registerSourceLabel(null);
    expect(label).toBe('Sum of our loans table, excluding pending bills');
    expect(label).not.toMatch(/\d/);
  });

  it('never calls the loans table the instrument register', () => {
    // `debt_instruments` is a DIFFERENT table — the maturity/coupon profile
    // behind /debt's ladder, covering ~60% of the bond stock and explicitly
    // barred from any debt total. Two tables cannot share one name on a page
    // whose claim is traceability.
    for (const label of [registerSourceLabel(47), registerSourceLabel(null)]) {
      expect(label.toLowerCase()).not.toContain('instrument register');
    }
  });
});
