/**
 * The county Budget tab must not draw an aging distribution the payload cannot
 * support.
 *
 * `GET /pending-bills/counties/{id}` has no aging observation for any of the 47
 * counties. It falls back to the loans table and returns a hardcoded
 * `{"0-30d":0,"31-90d":0,"91-180d":0,"180d+": total}` — 100% of the county's
 * unpaid bills asserted to be past the 180-day mark that refers them to the
 * Pending Bills Verification Committee.
 *
 * Two things were wrong here, and they had to be fixed together:
 *
 *  1. The response type declares `aging_buckets` and `breakdown_by_type` as
 *     ARRAYS while the API sends OBJECTS, so the component's `.length > 0`
 *     guards read `undefined` and both sections silently rendered nothing.
 *     The fabricated bar was held back by a type error, not by a decision.
 *  2. Normalising the payload — the obvious fix for (1), and what
 *     DebtPageClient already does — would have put a solid red 100% bar and a
 *     "180d+: KES 9.26B (100.0%)" tooltip on all 47 county pages.
 *
 * So the assertions below run in both directions: the section now renders (it
 * did not before), AND what it renders is a statement of absence rather than a
 * distribution. Against pre-fix code the "no aging bar" cases pass vacuously —
 * nothing rendered at all — while the "says why" and "renders the type
 * breakdown when measured" cases fail.
 *
 * Payload: GET /api/v1/pending-bills/counties/3 (Kilifi), 2026-09-06
 * (production, `5ff5fa9`).
 */
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

/** Verbatim from the live response. */
const KILIFI_FALLBACK = {
  status: 'success',
  data_source: 'loans_table_fallback',
  county: 'Kilifi County',
  county_id: '3',
  total_pending: 9_255_600_000,
  breakdown_by_type: { supplier_arrears: 9_255_600_000 },
  aging_buckets: { '0-30d': 0, '31-90d': 0, '91-180d': 0, '180d+': 9_255_600_000 },
  currency: 'KES',
};

/** What a county would look like once bills carry an `aging_days`. */
const MEASURED = {
  status: 'success',
  data_source: 'pending_bills_table',
  county: 'Kilifi County',
  county_id: '3',
  total_pending: 1_000_000_000,
  breakdown_by_type: { supplier_arrears: 600_000_000, salary: 400_000_000 },
  aging_buckets: {
    '0-30d': 100_000_000,
    '31-90d': 200_000_000,
    '91-180d': 300_000_000,
    '180d+': 400_000_000,
  },
};

let pendingBills: any = KILIFI_FALLBACK;

jest.mock('@/lib/react-query/useDebt', () => ({
  useCountyPendingBills: () => ({ data: pendingBills }),
}));

jest.mock('@/components/ModelledDataNote', () => ({
  __esModule: true,
  default: () => null,
}));

import BudgetTab from '@/app/counties/[id]/tabs/BudgetTab';

/** A county carrying only the fields BudgetTab reads. */
const county = () =>
  ({
    id: 3,
    name: 'Kilifi',
    budget: {
      total_budget: 19_880_000_000,
      total_spent: 12_030_000_000,
      development_budget: 9_400_000_000,
      recurrent_budget: 10_480_000_000,
      execution_rate: 60.5,
      source: 'Controller of Budget CBIRR',
    },
    debt: { total_debt: 0, pending_bills: 9_255_600_000, breakdown: [] },
  }) as any;

beforeEach(() => {
  pendingBills = KILIFI_FALLBACK;
});

describe('county aging bar — the fabricated distribution', () => {
  it('does not draw a 180d+ bar for a county whose aging was never measured', () => {
    const { container } = render(<BudgetTab data={county()} />);
    // The bar and its legend are the only things that print a bucket name.
    expect(screen.queryByText(/180d\+/)).not.toBeInTheDocument();
    expect(container.querySelector('[title*="180d+"]')).toBeNull();
  });

  it('does not claim 100% of the bills fall in any single band', () => {
    const { container } = render(<BudgetTab data={county()} />);
    expect(container.querySelector('[title*="100.0%"]')).toBeNull();
    expect(screen.queryByText(/100\.0%/)).not.toBeInTheDocument();
  });

  it('says why there is no breakdown instead of leaving a silent gap', () => {
    render(<BudgetTab data={county()} />);
    expect(screen.getByText(/not recorded in the source they come from/i)).toBeInTheDocument();
  });

  it('keeps the total, which is real, and says the absence does not touch it', () => {
    render(<BudgetTab data={county()} />);
    expect(screen.getByText(/KES 9\.26B/)).toBeInTheDocument();
    expect(screen.getByText(/total above is unaffected/i)).toBeInTheDocument();
  });

  it('does not draw the hardcoded single-type breakdown either', () => {
    // The same fallback returns `{"supplier_arrears": total}` — one bill type
    // asserted for the whole county, from a table that records no bill type.
    render(<BudgetTab data={county()} />);
    expect(screen.queryByText(/Supplier Arrears/i)).not.toBeInTheDocument();
  });
});

describe('county aging bar — a measured distribution is still drawn', () => {
  it('draws all four bands when the payload declares the pending_bills table', () => {
    pendingBills = MEASURED;
    render(<BudgetTab data={county()} />);
    for (const bucket of ['0-30d', '31-90d', '91-180d', '180d+']) {
      expect(screen.getByText(new RegExp(bucket.replace('+', '\\+')))).toBeInTheDocument();
    }
    expect(screen.queryByText(/not recorded in the source/i)).not.toBeInTheDocument();
  });

  it('draws the type breakdown when the source records a bill type', () => {
    pendingBills = MEASURED;
    render(<BudgetTab data={county()} />);
    expect(screen.getByText(/Supplier Arrears/i)).toBeInTheDocument();
    expect(screen.getByText(/Salary/i)).toBeInTheDocument();
  });
});

describe('county aging bar — no pending-bills payload at all', () => {
  it('falls back to the county total without inventing a breakdown', () => {
    pendingBills = undefined;
    render(<BudgetTab data={county()} />);
    expect(screen.queryByText(/180d\+/)).not.toBeInTheDocument();
    // Twice: the card's own total, and the pre-existing "no breakdown yet"
    // fallback line beneath it.
    expect(screen.getAllByText(/KES 9\.26B/).length).toBeGreaterThan(0);
  });
});
