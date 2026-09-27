import '@testing-library/jest-dom';
import { render } from '@testing-library/react';

/**
 * Issue #237. The flow hero drew sources and uses against the COB gross
 * budget (5,485.7B) with two "residual" segments absorbing the difference
 * between bases, subtracted interest-plus-principal from a recurrent figure
 * that holds interest only, and printed two hard-coded figures ("CFS for
 * FY2025/26 is about KES 2.14T", "the ~KES 4.8T total"). Now every segment is
 * a printed line of one fiscal-framework column and both bars sum to it.
 */

jest.mock('framer-motion', () => ({
  motion: new Proxy(
    {},
    {
      get:
        () =>
        ({ children, initial, animate, whileInView, viewport, transition, ...p }: any) => (
          <div {...p}>{children}</div>
        ),
    },
  ),
}));

import BudgetFlowHero from '@/components/budget/BudgetFlowHero';
import { FY_2026_27_BILLIONS } from '@/test/fixtures/fiscalFramework';

const text = (el: HTMLElement) => el.textContent ?? '';

describe('BudgetFlowHero on the fiscal framework', () => {
  it('draws both bars against the framework total, with no residual', () => {
    const { container } = render(<BudgetFlowHero data={FY_2026_27_BILLIONS} />);
    const t = text(container);
    expect(t).toMatch(/Total KES 4\.79T/);
    expect(t).toMatch(/Spending & net lending KES 4\.79T/);
    expect(t).not.toMatch(/residual/i);
    // Recurrent ex-interest = 3,538.7 - 1,254.2 = 2,284.5 -> 2.28T.
    expect(t).toMatch(/Recurrent \(ex-interest\)KES 2\.28T/);
    expect(t).toMatch(/Interest on debtKES 1\.25T/);
    expect(t).toMatch(/Net borrowingKES 1\.11T/);
  });

  it('carries no hard-coded budget figures', () => {
    const { container } = render(<BudgetFlowHero data={FY_2026_27_BILLIONS} />);
    const t = text(container);
    expect(t).not.toMatch(/2\.14T/);
    expect(t).not.toMatch(/~KES 4\.8T/);
    // The reconciliation is computed from API values:
    // 5,485.7 - 1,061.6 + 420.0 = 4,844.1 -> 4.84T.
    expect(t).toMatch(/about KES 4\.84T/);
  });

  it('keeps the gross budget as the headline', () => {
    const { container } = render(<BudgetFlowHero data={FY_2026_27_BILLIONS} />);
    expect(text(container)).toMatch(/KES 5\.49T approved for FY 2026\/27/);
  });

  it('withholds the flow when no framework is published — never bars of columns', () => {
    const { fiscal_framework, ...legacy } = FY_2026_27_BILLIONS;
    const { container } = render(<BudgetFlowHero data={legacy} />);
    const t = text(container);
    expect(t).toMatch(/How FY 2026\/27 breaks down is not published yet/);
    expect(t).not.toMatch(/Where it actually goes/);
  });
});
