import { BUDGET_GUIDE_STEPS, budgetGuideHref, findBudgetGuideStep, readBudgetGuideFigure } from '@/app/learn/budget-guide/budgetGuideData';
import type { FiscalSummaryResponse } from '@/lib/api/fiscal';
import type { FrameworkMeasureProof } from '@/lib/fiscal/framework';

const currentYear = 'FY 2026/27';
const duringYear = new Date('2026-11-19T12:00:00Z');

function approvedFixture() {
  const source = {
    sha256: 'a'.repeat(64), title: 'Synthetic budget fixture', publisher: 'Synthetic Treasury fixture',
    url: 'https://www.treasury.go.ke/synthetic-budget-guide.pdf', page: 'Annex Table 2a, PDF p.7',
    table: 'Annex Table 2a', edition: 'Synthetic approved budget test', column: 'Approved',
  };
  const entries = {
    total_expenditure_billion: [120.5, 'Expenditure and Net Lending'],
    total_revenue_incl_aia_billion: [85, 'Total Revenue including A-i-A'],
    grants_billion: [5.5, 'Grants'],
    fiscal_deficit_incl_grants_billion: [30, 'Fiscal Balance including Grants (sign reversed)'],
    total_financing_billion: [30, 'Total Financing'],
    adjustment_to_cash_basis_billion: [0, 'Adjustment to Cash Basis'],
    statistical_discrepancy_billion: [0, 'Statistical Discrepancy'],
    county_transfers_billion: [12.5, 'County Transfers'],
  } as const;
  const qualifications: Record<string, FrameworkMeasureProof> = {};
  for (const [key, [value, cell]] of Object.entries(entries)) {
    qualifications[key] = {
      value_kes: value * 1e9, fiscal_year: currentYear,
      basis: key === 'total_revenue_incl_aia_billion' ? 'revenue_including_aia' : 'treasury_fiscal_framework',
      vintage: 'Approved', precision_kes: 100_000_000, source: { ...source, cell },
    };
  }
  const fiscalFramework = {
    ...Object.fromEntries(Object.entries(entries).map(([key, [value]]) => [key, value])),
    basis: 'treasury_fiscal_framework', fiscal_year: currentYear, measure_contract_version: 'fiscal-measures-v1',
    precision_kes: 100_000_000, source, measure_qualifications: qualifications,
  };
  const response = { current: { fiscal_year: currentYear, fiscal_framework: fiscalFramework } } as FiscalSummaryResponse;
  return { response, source, fiscalFramework, qualifications };
}

it('links each ordered step to its live context and exact guide URL', () => {
  expect(BUDGET_GUIDE_STEPS.map(step => step.destination)).toEqual([
    '/budget', '/learn/glossary#term-revenue', '/debt', '/transparency',
  ]);
  expect(budgetGuideHref(findBudgetGuideStep('financing'))).toBe('/learn/budget-guide?step=financing');
  expect(findBudgetGuideStep().key).toBe('spending');
  expect(findBudgetGuideStep('5').key).toBe('spending');
  expect(findBudgetGuideStep(['counties', 'revenue']).key).toBe('spending');
});

it('reveals each individually qualified amount with the same approved fiscal period and exact PDF page', () => {
  const { response } = approvedFixture();
  const figures = BUDGET_GUIDE_STEPS.map(step => readBudgetGuideFigure(response, step, duringYear));
  expect(figures).toEqual([120.5, 85, 30, 12.5].map(amountBillion => ({
    state: 'available', fiscalYear: currentYear, amountBillion,
    sourceLabel: 'Synthetic Treasury fixture · Synthetic approved budget test · Annex Table 2a, PDF p.7',
    sourceUrl: 'https://www.treasury.go.ke/synthetic-budget-guide.pdf#page=7',
  })));
});

it('rolls over to the new fiscal year at midnight in Nairobi', () => {
  const { response } = approvedFixture();
  const step = findBudgetGuideStep();
  expect(readBudgetGuideFigure(response, step, new Date('2026-06-30T20:59:59Z'))).toEqual({
    state: 'yearUnavailable', fiscalYear: 'FY 2025/26',
  });
  expect(readBudgetGuideFigure(response, step, new Date('2026-06-30T21:00:00Z')).state).toBe('available');
  expect(readBudgetGuideFigure(response, step, new Date('2027-06-30T21:00:00Z'))).toEqual({
    state: 'yearUnavailable', fiscalYear: 'FY 2027/28',
  });
});

it('withholds a legacy raw value without the measure qualification contract', () => {
  const { response } = approvedFixture();
  const framework = response.current.fiscal_framework!;
  delete framework.measure_contract_version;
  delete framework.measure_qualifications;
  expect(framework.total_expenditure_billion).toBe(120.5);
  expect(readBudgetGuideFigure(response, findBudgetGuideStep(), duringYear)).toEqual({
    state: 'figureUnavailable', fiscalYear: currentYear,
  });
});

it('withholds only the county cell when its qualification is missing from an otherwise reconciled column', () => {
  const { response, qualifications } = approvedFixture();
  delete qualifications.county_transfers_billion;
  expect(readBudgetGuideFigure(response, findBudgetGuideStep('counties'), duringYear).state).toBe('figureUnavailable');
  expect(readBudgetGuideFigure(response, findBudgetGuideStep(), duringYear).state).toBe('available');
});

it('requires matching source, period and Approved column', () => {
  const { response, source, fiscalFramework, qualifications } = approvedFixture();
  const step = findBudgetGuideStep();
  qualifications[step.measure].source.page = '8';
  expect(readBudgetGuideFigure(response, step, duringYear).state).toBe('figureUnavailable');
  qualifications[step.measure].source.page = source.page;
  fiscalFramework.fiscal_year = 'FY 2025/26';
  expect(readBudgetGuideFigure(response, step, duringYear).state).toBe('figureUnavailable');
  fiscalFramework.fiscal_year = currentYear;
  source.column = 'Preliminary';
  for (const proof of Object.values(qualifications)) {
    proof.vintage = 'Preliminary';
    proof.source.column = 'Preliminary';
  }
  expect(readBudgetGuideFigure(response, step, duringYear).state).toBe('figureUnavailable');
});

it('preserves a bare PDF page accepted by the fiscal source contract', () => {
  const { response, source, qualifications } = approvedFixture();
  source.page = 'p. 7';
  for (const proof of Object.values(qualifications)) proof.source.page = source.page;
  expect(readBudgetGuideFigure(response, findBudgetGuideStep(), duringYear)).toMatchObject({
    state: 'available', sourceUrl: 'https://www.treasury.go.ke/synthetic-budget-guide.pdf#page=7',
  });
});

it('sets a single page fragment and keeps rejecting sources with a populated fragment', () => {
  const { response, source, qualifications } = approvedFixture();
  const step = findBudgetGuideStep();
  const original = source.url;
  source.url = original + '#';
  for (const proof of Object.values(qualifications)) proof.source.url = source.url;
  expect(readBudgetGuideFigure(response, step, duringYear)).toMatchObject({
    state: 'available', sourceUrl: original + '#page=7',
  });
  source.url = original + '#other-section';
  for (const proof of Object.values(qualifications)) proof.source.url = source.url;
  expect(readBudgetGuideFigure(response, step, duringYear).state).toBe('figureUnavailable');
});
