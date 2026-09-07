/**
 * The hero's source line, rendered from the real production payload.
 *
 * Companion to __tests__/lib/debt/registerScope.test.ts, which pins the
 * arithmetic. This file pins what the COMPONENT prints, so the fix cannot be
 * undone by re-wiring the label back to `loan_count` while the helper stays
 * green.
 *
 * Against pre-fix `HeroSection.tsx` the first two cases fail: the label read
 * `apiData.loan_count` and rendered
 *
 *   "Sum of our instrument register (60 rows)"
 *
 * over KES 11.86T — a figure the backend summed over 47 rows, having dropped
 * the 13 pending-bill rows with `_is_debt_loan`. The label and the figure
 * described different sets, and the name it used belongs to a different table.
 *
 * Payload: GET /api/v1/debt/national, 2026-09-06 (production, `5ff5fa9`).
 */
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

const LIVE_OVERVIEW = {
  data: {
    total_outstanding: 11_855_978_858_225.68,
    total_debt: 11_855_978_858_225.68,
    // Every national row, pending bills included — NOT what the total is over.
    loan_count: 60,
    debt_to_gdp_ratio: 69.3,
    reconciliation: { secondary_value_kes: 12_299_000_000_000 },
    summary: {
      external_debt: 5_265_016_798_890.222,
      domestic_debt: 6_590_962_059_335.458,
    },
    categories: {
      external_multilateral: { loan_count: 13, total_outstanding: 2_695_722_058_890.222 },
      external_bilateral: { loan_count: 17, total_outstanding: 1_087_508_999_335.458 },
      external_commercial: { loan_count: 12, total_outstanding: 1_014_147_800_000 },
      domestic_bonds: { loan_count: 2, total_outstanding: 5_878_982_400_000 },
      domestic_bills: { loan_count: 1, total_outstanding: 1_090_017_800_000 },
      domestic_overdraft: { loan_count: 2, total_outstanding: 89_599_800_000 },
      pending_bills: { loan_count: 13, total_outstanding: 931_300_000_000 },
    },
  },
};

let overview: any = LIVE_OVERVIEW;

jest.mock('@/lib/react-query/useDebt', () => ({
  useDebtTimeline: () => ({ data: undefined }),
  useNationalDebtOverview: () => ({ data: overview }),
}));

jest.mock('@/lib/react-query/useFiscal', () => ({
  useFiscalSummary: () => ({ data: undefined }),
}));

jest.mock('@/components/ui/KenyaFlag', () => ({
  KenyaFlag: () => <span aria-label='Kenya' />,
}));

jest.mock('@/components/dashboard/DebtExplainerModal', () => ({
  __esModule: true,
  default: () => null,
}));

import { SummaryStrip } from '@/components/dashboard/HeroSection';

beforeEach(() => {
  overview = LIVE_OVERVIEW;
});

describe('hero source line — the set the headline was summed over', () => {
  it('states 47 rows, the rows behind KES 11.86T', () => {
    render(<SummaryStrip />);
    expect(screen.getByText(/Sum of 47 loan rows/i)).toBeInTheDocument();
  });

  it('never states the 60 rows in the table', () => {
    render(<SummaryStrip />);
    expect(screen.queryByText(/60 rows/)).not.toBeInTheDocument();
  });

  it('says which rows are excluded, so 47-vs-60 is explained rather than merely correct', () => {
    render(<SummaryStrip />);
    expect(screen.getByText(/pending bills excluded/i)).toBeInTheDocument();
  });

  it('does not call the loans table "the instrument register"', () => {
    // `debt_instruments` is a different table — the maturity/coupon profile
    // behind /debt's ladder, which the seeding domain documents as covering
    // "~60% of the published bond stock, so a row here must not reach any code
    // that sums a debt total".
    render(<SummaryStrip />);
    expect(screen.queryByText(/instrument register/i)).not.toBeInTheDocument();
  });
});

describe('hero source line — when the count cannot be established', () => {
  it('states no count at all rather than an unverified one', () => {
    // Categories absent: the label must not fall back to `loan_count`.
    overview = { data: { ...LIVE_OVERVIEW.data, categories: undefined } };
    render(<SummaryStrip />);
    expect(screen.getByText(/Sum of our loans table, excluding pending bills/i)).toBeInTheDocument();
    expect(screen.queryByText(/\d+ rows/)).not.toBeInTheDocument();
  });

  it('withholds the count when the categories do not add up to the headline', () => {
    const { domestic_bonds: _dropped, ...rest } = LIVE_OVERVIEW.data.categories as Record<string, any>;
    overview = { data: { ...LIVE_OVERVIEW.data, categories: rest } };
    render(<SummaryStrip />);
    expect(screen.queryByText(/\d+ rows/)).not.toBeInTheDocument();
  });

  it('still renders the headline figure itself', () => {
    overview = { data: { ...LIVE_OVERVIEW.data, categories: undefined } };
    render(<SummaryStrip />);
    expect(screen.getByText(/11\.86T/)).toBeInTheDocument();
  });
});
