import '@testing-library/jest-dom';
import { render, screen, within } from '@testing-library/react';

/**
 * Issue #237. The flow hero drew sources and uses against the COB gross
 * budget (5,485.7B) with two "residual" segments absorbing the difference
 * between bases, subtracted interest-plus-principal from a recurrent figure
 * that holds interest only, and printed two hard-coded figures ("CFS for
 * FY2025/26 is about KES 2.14T", "the ~KES 4.8T total"). Now every segment is
 * a printed line of one fiscal-framework column and both bars sum to it.
 */

import BudgetFlowHero from '@/components/budget/BudgetFlowHero';
import { FF_2023_24_ACTUAL, FF_2026_27, FY_2026_27_BILLIONS, withSyntheticFrameworkProofs } from '@/test/fixtures/fiscalFramework';

const text = (el: HTMLElement) => el.textContent ?? '';

describe('BudgetFlowHero on the fiscal framework', () => {
  it('draws both bars against the framework total, with no residual', () => {
    const { container } = render(<BudgetFlowHero data={FY_2026_27_BILLIONS} />);
    const t = text(container);
    expect(t).toMatch(/Total KES 4\.79T/);
    expect(t).toMatch(/Spending & net lending KES 4\.79T/);
    expect(t).not.toMatch(/residual/i);
    // Recurrent ex-interest = 3,538.7 - 1,254.2 = 2,284.5 -> 2.28T.
    expect(t).toMatch(/Salaries and running costsKES 2\.28T/);
    expect(t).toMatch(/Interest on debtKES 1\.25T/);
    expect(t).toMatch(/Net borrowingKES 1\.11T/);
    expect(t).toMatch(/60% comes from taxes. 23% is net new borrowing./);
    expect(t).toMatch(/Of every 100 shillings in this fiscal framework, 26 is for interest./);
    expect(t).not.toMatch(/shillings spent/);
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
    expect(t).toMatch(/How FY 2026\/27 breaks down is withheld/);
    expect(t).not.toMatch(/Where it goes/);
  });
});

it('uses the declared Actual column and interest alone for the spending takeaway', () => {
  render(<BudgetFlowHero data={{ fiscal_year: 'FY 2023/24', fiscal_framework: FF_2023_24_ACTUAL }} />);
  expect(screen.getByText('Of every 100 shillings spent, 23 went to interest.')).toBeVisible();
});

it('preserves independently qualified uses when the sources cannot be drawn', () => {
  const framework = withSyntheticFrameworkProofs({
    ...FF_2026_27,
    ordinary_revenue_billion: null,
  }, 'FY 2026/27', 'Approved');
  render(<BudgetFlowHero data={{ ...FY_2026_27_BILLIONS, fiscal_framework: framework }} />);
  expect(screen.getByText('A complete sources breakdown is withheld until the reported figures reconcile.')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Explore Where the money comes from' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Explore Where it goes' })).toBeVisible();
});

const zeroFramework = {
  ...FF_2026_27,
  total_expenditure_billion: 0,
  recurrent_billion: 0,
  interest_payments_billion: 0,
  development_billion: 0,
  county_transfers_billion: 0,
  county_equitable_share_billion: 0,
  contingency_billion: 0,
  total_revenue_incl_aia_billion: 0,
  ordinary_revenue_billion: 0,
  ministerial_aia_billion: 0,
  grants_billion: 0,
  fiscal_deficit_incl_grants_billion: 0,
  total_financing_billion: 0,
  adjustment_to_cash_basis_billion: 0,
  statistical_discrepancy_billion: 0,
  tax_revenue_billion: 0,
  non_tax_revenue_billion: 0,
};

it('retains reported zero without drawing proportions for a zero total', () => {
  render(<BudgetFlowHero data={{
    ...FY_2026_27_BILLIONS,
    fiscal_framework: withSyntheticFrameworkProofs(zeroFramework, 'FY 2026/27', 'Approved'),
  }} />);
  expect(screen.getByText('The reported total is zero. See the amounts in the table.')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Explore Where the money comes from' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Tax revenue KES 0' })).toBeVisible();
});

it('lists negative financing and reconciliation amounts without pretending they have positive bar widths', () => {
  const fiscal_framework = withSyntheticFrameworkProofs({
    ...zeroFramework,
    total_expenditure_billion: 100,
    recurrent_billion: 80,
    interest_payments_billion: 25,
    development_billion: 15,
    county_transfers_billion: 5,
    total_revenue_incl_aia_billion: 110,
    ordinary_revenue_billion: 110,
    tax_revenue_billion: 110,
    fiscal_deficit_incl_grants_billion: -10,
    total_financing_billion: -5,
    statistical_discrepancy_billion: 5,
  }, 'FY 2026/27', 'Approved');
  render(<BudgetFlowHero data={{ ...FY_2026_27_BILLIONS, fiscal_framework }} />);
  const sources = within(screen.getByRole('region', { name: 'Where the money comes from' }));
  expect(sources.queryByRole('button', { name: 'Explore Where the money comes from' })).not.toBeInTheDocument();
  expect(sources.getByText('Treasury reports net borrowing of KES −5B for this period.')).toBeVisible();
  expect(sources.getByText('The reported cash-basis adjustment less the statistical discrepancy is KES −5B.')).toBeVisible();
  const table = within(sources.getByRole('table', { hidden: true }));
  expect(table.getByText('Net borrowing').closest('tr')).toHaveTextContent('KES -5,000,000,000');
  expect(table.getByText('Cash-basis adjustment').closest('tr')).toHaveTextContent('KES -5,000,000,000');
  expect(screen.getByRole('button', { name: 'Explore Where it goes' })).toBeVisible();
});
