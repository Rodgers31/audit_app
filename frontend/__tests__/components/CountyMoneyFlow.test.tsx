import { fireEvent, render, screen, within } from '@testing-library/react';
import FollowTheMoney from '@/components/FollowTheMoney';
import { countyMoneyAmounts, countySpendShare } from '@/components/county/countyMoneyFlow';
import type { MoneyFlowData } from '@/types';

function flow(allocated: number | null, spent: number | null): MoneyFlowData {
  return {
    county_id: 1, county_name: 'Test County', fiscal_year: 'FY2025/26 9M',
    total_waste_estimate: null, efficiency_score: null, committed_amount: 8e9,
    source_document_title: 'Synthetic nine-month publication', source_document_url: 'https://example.invalid/9m.pdf',
    stages: [
      { stage: 'Allocated', label: 'Budget Allocation', amount: allocated },
      { stage: 'Spent', label: 'Actual Expenditure', amount: spent },
      { stage: 'Flagged', label: 'Auditor Flagged', amount: null, data_unavailable: true },
    ],
    audit_amount_coverage: {
      status: 'unavailable', reason: 'no_findings', total_findings: 0, findings_with_amount: 0,
      findings_without_amount: 0, findings_with_invalid_amount: 0, withheld_findings: 0,
    },
  };
}

it.each([
  [10, 6, 4, null, 60],
  [10, 12, null, 2, 120],
  [0, 0, 0, null, null],
  [null, 6, null, null, null],
  [10, null, null, null, null],
])('keeps paid and unspent values distinct for allocation %s and spend %s', (a, s, unspent, overspent, ratio) => {
  expect(countyMoneyAmounts(flow(a, s))).toMatchObject({ allocated: a, spent: s, unspent, overspent, ratio });
});

it('respects withheld stages and preserves signed amounts without drawing an unsupported share', () => {
  const data = flow(10, 6);
  data.stages[0].data_unavailable = true;
  expect(countyMoneyAmounts(data)).toMatchObject({ allocated: null, ratio: null, chartable: false });
  expect(countyMoneyAmounts(flow(-10, 6))).toMatchObject({ allocated: -10, ratio: null, unspent: null, overspent: null, chartable: false });
  expect(countyMoneyAmounts(flow(10, -2))).toMatchObject({ spent: -2, ratio: null, unspent: null, overspent: null, chartable: false });
  expect(countyMoneyAmounts(flow(-10, -2))).toMatchObject({ ratio: null, unspent: null, overspent: null, chartable: false });
  expect(countySpendShare(0.2)).toBe('0.2');
  expect(countySpendShare(99.8)).toBe('99.8');
});

it('keeps commitment out of the spent bar and names selected and aggregate finding scopes separately', () => {
  const openAudit = jest.fn();
  render(<FollowTheMoney data={flow(10e9, 6e9)} findingsCount={196} onOpenAudit={openAudit} />);
  expect(screen.getByText(/spent 60% of its allocation in FY2025\/26 9M/)).toBeVisible();
  expect(screen.getByText(/Reported procurement commitments KES 8.00B. Accounting scope is unconfirmed./)).toBeVisible();
  expect(screen.getAllByText('No audit findings are recorded for FY2025/26 9M in this dataset.')[0]).toBeVisible();
  expect(screen.getByText(/Audit tab lists 196 findings across its recorded periods/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'See Audit' }));
  expect(openAudit).toHaveBeenCalledTimes(1);
  expect(screen.queryByText(/No audit covers|2021–2025/)).toBeNull();
});

it('shows overspending in words and exact data while preserving keyboard and outside reset', () => {
  render(<FollowTheMoney data={flow(10e9, 12e9)} />);
  expect(screen.getByText('Reported spending exceeds the allocation by KES 2.00B in FY2025/26 9M.')).toBeVisible();
  const allocated = screen.getByRole('button', { name: 'Allocated KES 10.00B' });
  const spending = screen.getByRole('button', { name: /^Spent KES/ });
  fireEvent.focus(allocated);
  expect(screen.getByText('Allocated · KES 10,000,000,000')).toBeVisible();
  fireEvent.click(allocated);
  expect(allocated).toHaveAttribute('aria-pressed', 'true');
  fireEvent.keyDown(allocated, { key: 'Escape' });
  expect(allocated).toHaveAttribute('aria-pressed', 'false');
  fireEvent.focus(spending);
  fireEvent.keyDown(spending, { key: 'End' });
  expect(screen.getByText('Spent · KES 12,000,000,000')).toBeVisible();
  fireEvent.click(spending, { detail: 0 });
  expect(spending).toHaveAttribute('aria-pressed', 'true');
  fireEvent.pointerDown(document.body);
  expect(spending).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(screen.getByText('Read chart data'));
  expect(screen.getByRole('row', { name: 'Spending above allocation KES 2,000,000,000' })).toBeVisible();
});

it.each([[-10, 6], [10, -2], [-10, -2]])('keeps signed inputs %s and %s exact while derived spending populations stay unavailable', (allocated, spent) => {
  render(<FollowTheMoney data={flow(allocated, spent)} />);
  expect(screen.getByText(/Signed amounts are shown as reported in the table/)).toBeVisible();
  expect(screen.queryByRole('button', { name: /^Spent KES/ })).toBeNull();
  fireEvent.click(screen.getByText('Read chart data'));
  expect(screen.getByRole('row', { name: `Allocated KES ${allocated}` })).toBeVisible();
  expect(screen.getByRole('row', { name: `Spent KES ${spent}` })).toBeVisible();
  expect(screen.getByRole('row', { name: 'Unspent Not published' })).toBeVisible();
  expect(screen.queryByText(/^Spending above allocation/)).toBeNull();
});

it('preserves each stage source and audit coverage details in the source sheet', () => {
  const data = flow(10, 6);
  data.stages[0].source = 'Synthetic allocation account';
  data.stages[0].source_doc = 'https://example.invalid/allocation.pdf';
  data.stages[2].amount_coverage = {
    status: 'partial', reason: 'incomplete_amount_coverage', total_findings: 3,
    findings_with_amount: 1, findings_without_amount: 1, findings_with_invalid_amount: 1, withheld_findings: 2,
  };
  render(<FollowTheMoney data={data} />);
  const dialog = document.querySelector('dialog')!;
  dialog.open = true;
  dialog.querySelector('details')!.open = true;
  const source = within(dialog);
  expect(source.getByText('Synthetic allocation account')).toBeVisible();
  expect(source.getByRole('link', { name: 'Open source document' })).toHaveAttribute('href', data.stages[0].source_doc);
  expect(source.getByText(/1 of 3 cited findings/)).toHaveTextContent('1 missing and 1 invalid amounts');
  expect(source.getByText('incomplete amount coverage')).toBeVisible();
  expect(source.getByText('2 findings are withheld from the amount calculation.')).toBeVisible();
});
