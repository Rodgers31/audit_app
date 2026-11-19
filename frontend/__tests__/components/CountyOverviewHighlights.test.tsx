import { fireEvent, render, screen } from '@testing-library/react';
import OverviewHighlights from '@/app/counties/[id]/tabs/OverviewHighlights';
import { countyOverviewFacts } from '@/app/counties/[id]/tabs/overviewFacts';
import type { CountyComprehensive } from '@/types';

const source = { title: 'Synthetic county budget report', publisher: 'Controller of Budget', url: 'https://example.test/budget.pdf' };
const fullYear = { label: 'FY2025/26', start_date: '2025-07-01', end_date: '2026-06-30' };
const base = {
  budget: { total_allocated: 10e9, total_spent: 7.6e9, utilization_rate: 76,
    fiscal_year: fullYear.label, fiscal_period: fullYear, sources: [source], accounting_basis: 'reported_total' },
  debt: { pending_bills: 860e6, pending_bills_as_at: '2026-06-30',
    pending_bills_source: { ...source, table: 'Table 2.10' } },
  financial_summary: { pending_bills_ratio: 8.6 },
  audit: {
    findings_count: 2, by_severity: { critical: 1, warning: 1, info: 0 },
    findings: [
      { id: 1, severity: 'critical', source_url: 'https://example.test/audit.pdf#page=3', page_ref: 'p. 3' },
      { id: 2, severity: 'warning', source_url: 'https://example.test/audit.pdf#page=4', page_ref: 'p. 4' },
    ],
  },
};
const data = (patch: object = {}) => ({ ...base, ...patch }) as unknown as CountyComprehensive;

it('renders the three approved cards in order with exact source facts and tab actions', () => {
  const onOpenTab = jest.fn();
  render(<OverviewHighlights data={data()} onOpenTab={onOpenTab} />);
  expect(screen.getAllByRole('heading').map(heading => heading.textContent)).toEqual([
    '3 things to know', 'Share of budget spent', 'Unpaid bills', 'Serious audit findings',
  ]);
  expect(screen.getByText('76%')).toBeVisible();
  expect(screen.getByText('On track')).toBeVisible();
  expect(screen.getByText('8.6% of the FY2025/26 budget, owed to suppliers.')).toBeVisible();
  expect(screen.getByText('Of 2 published county audit findings.')).toBeVisible();
  expect(screen.queryByText(/recorded audit years/)).toBeNull();
  for (const label of ['See Money', 'See Budget', 'See Audit']) fireEvent.click(screen.getByRole('button', { name: label }));
  expect(onOpenTab.mock.calls).toEqual([['money'], ['budget'], ['audit']]);
});

it('keeps the sourced partial-period spending and year-end payables separate', () => {
  const label = 'FY2025/26 9M';
  const budget = { ...base.budget, fiscal_year: label, fiscal_period: { ...fullYear, label, end_date: '2026-03-31' } };
  render(<OverviewHighlights data={data({ budget })} />);
  expect(screen.getByText(/KES 7.60B of KES 10.00B allocated · FY2025\/26 9M/)).toBeVisible();
  expect(screen.getByText('Part-year result')).toBeVisible();
  expect(screen.queryByText(/annual spending target/)).toBeNull();
  expect(screen.getByText('KES 860.0M')).toBeVisible();
  expect(screen.getByText('Trade payables reported as at 30 June 2026.')).toBeVisible();
  expect(screen.getByText('A comparable annual budget share is unavailable.')).toBeVisible();
});

it('uses only the published compatible bills ratio and safe report links', () => {
  expect(countyOverviewFacts(data({ financial_summary: { pending_bills_ratio: null } })).pendingShare).toBeNull();
  expect(countyOverviewFacts(data({ financial_summary: { pending_bills_ratio: 8.4 } })).pendingShare).toBeNull();
  expect(countyOverviewFacts(data({ debt: { ...base.debt, pending_bills_as_at: '2025-06-30' } })).pendingShare).toBeNull();
  expect(countyOverviewFacts(data({ budget: { ...base.budget, sources: [{ url: 'javascript:alert(1)' }] } })).spending).toBeNull();
});

it('requires the bound public account even when a report URL and arithmetic are present', () => {
  for (const patch of [{ source: 'mixed' }, { source: 'cra_model' }, { accounting_basis: undefined },
    { accounting_basis: 'unknown' }, { fiscal_period: { label: fullYear.label } }]) {
    const facts = countyOverviewFacts(data({ budget: { ...base.budget, ...patch } }));
    expect(facts.spending).toBeNull();
    expect(facts.pendingShare).toBeNull();
    expect(facts.pending?.amount).toBe(860e6);
  }
  const budget = { ...base.budget, source: null, accounting_basis: 'recurrent_plus_development' };
  expect(countyOverviewFacts(data({ budget })).spending?.rate).toBe(76);
});

it('retains a verified zero and refuses truncated, unsupported and absent audit evidence', () => {
  const findings = base.audit.findings.map(finding => ({ ...finding, severity: 'warning' }));
  const zero = { ...base.audit, findings, by_severity: { critical: 0, warning: 2 } };
  expect(countyOverviewFacts(data({ audit: zero })).findingCounts?.serious).toBe(0);
  expect(countyOverviewFacts(data({ audit: { ...zero, by_severity: { warning: 2 } } })).findingCounts?.serious).toBe(0);
  expect(countyOverviewFacts(data({ audit: { ...zero, findings_count: 30 } })).findingCounts).toBeNull();
  expect(countyOverviewFacts(data({ audit: { ...zero, by_severity: { critical: 1, warning: 1 } } })).findingCounts).toBeNull();
  expect(countyOverviewFacts(data({ audit: { ...zero, by_severity: { warning: 2 },
    findings: [findings[0], { ...findings[1], page_ref: null }] } })).findingCounts).toBeNull();
  expect(countyOverviewFacts(data({ audit: { ...zero, findings_count: 0, findings: [] } })).findingCounts).toBeNull();
  expect(countyOverviewFacts(data({ debt: { ...base.debt, pending_bills: 0 },
    financial_summary: { pending_bills_ratio: 0 } })).pendingShare?.rate).toBe(0);
});
