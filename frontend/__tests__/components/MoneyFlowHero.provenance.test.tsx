/**
 * The Follow the Money waterfall on /transparency captioned its Allocated
 * stage "CRA equitable share + conditional grants", and its footer opened
 * "Allocations follow the Commission on Revenue Allocation formula" — both
 * fixed strings, on a page whose allocation figure is the Controller of
 * Budget's own CBIRR aggregate wherever the report has landed.
 *
 * The API now reports which rows produced that figure (`budget_source`, the
 * same vocabulary ModelledDataNote switches on — see
 * backend/tests/test_money_flow_stage_provenance.py). The hero has to follow
 * it, including the other way: a CRA equitable-share projection period is
 * still a model and must still say so.
 */
import MoneyFlowHero from '@/components/transparency/MoneyFlowHero';
import type { BudgetSource, MoneyFlowData } from '@/types';
import { render, screen } from '@testing-library/react';

jest.mock('framer-motion', () => ({
  motion: {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    section: ({ children, initial: _i, animate: _a, whileInView: _w, viewport: _v, transition: _t, ...props }: any) => (
      <section {...props}>{children}</section>
    ),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    div: ({ children, initial: _i, animate: _a, whileInView: _w, viewport: _v, transition: _t, ...props }: any) => (
      <div {...props}>{children}</div>
    ),
  },
}));

const flow = (budget_source: BudgetSource): MoneyFlowData => ({
  county_id: null,
  county_name: 'National (All Counties)',
  fiscal_year: 'FY2024/25',
  budget_source,
  stages: [
    {
      stage: 'Allocated',
      label: 'Budget Allocation',
      amount: 633_303_870_000,
    },
    {
      stage: 'Spent',
      label: 'Actual Expenditure',
      amount: 421_000_000_000,
      gap_from_prev: 212_303_870_000,
      gap_label: 'Unspent Funds',
    },
    {
      stage: 'Flagged',
      label: 'Auditor Flagged',
      amount: 12_000_000_000,
      gap_label: 'Irregular/Unsupported Expenditure',
    },
  ],
  total_waste_estimate: 12_000_000_000,
  efficiency_score: 66.5,
});

const heroText = () => document.body.textContent ?? '';

describe('MoneyFlowHero — Allocated stage provenance', () => {
  it('does not credit the CRA formula for a Controller of Budget figure', () => {
    render(<MoneyFlowHero data={flow('cob_cbirr')} />);
    const text = heroText();

    // The figure really is on screen — otherwise this asserts about nothing.
    expect(screen.getAllByText(/633\.3B/).length).toBeGreaterThan(0);

    expect(text).not.toMatch(/CRA equitable share \+ conditional grants/i);
    expect(text).not.toMatch(
      /Allocations follow the Commission on Revenue Allocation formula/i
    );
    expect(text).toMatch(/Controller of Budget/i);
  });

  it('still calls a CRA projection modelled', () => {
    // A fix that hardcodes the CBIRR wording is the same defect reversed.
    render(<MoneyFlowHero data={flow('cra_model')} />);
    const text = heroText();

    expect(text).toMatch(/CRA equitable-share model/i);
    expect(text).toMatch(/Commission on Revenue Allocation formula/i);
    expect(text).toMatch(/modelled/i);
  });

  it('names both sources for a figure pooled across both', () => {
    // A national total over a partly-ingested CBIRR is neither one source nor
    // the other; naming one is wrong about the other half of the money.
    render(<MoneyFlowHero data={flow('mixed')} />);
    const text = heroText();

    expect(text).toMatch(/CoB CBIRR where published/i);
    expect(text).toMatch(/Commission on Revenue Allocation/i);
  });

  it('claims no allocation source when the API reports none', () => {
    render(<MoneyFlowHero data={flow(null)} />);
    const text = heroText();

    expect(text).not.toMatch(/CRA equitable share \+ conditional grants/i);
    expect(text).not.toMatch(
      /Allocations follow the Commission on Revenue Allocation formula/i
    );
    expect(text).not.toMatch(/Allocations are the Controller of Budget/i);
  });
});
