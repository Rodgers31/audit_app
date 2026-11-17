import MoneyFlowHero from '@/components/transparency/MoneyFlowHero';
import type { BudgetSource, MoneyFlowData } from '@/types';
import { render, screen } from '@testing-library/react';

const report = 'https://cob.go.ke/reports/example-cbirr.pdf';

function flow(allocated: number | null, spent: number | null, budget_source: BudgetSource = 'cob_cbirr'): MoneyFlowData {
  return {
    county_id: null, county_name: 'National', fiscal_year: 'FY2024/25 9M', budget_source,
    source_document_url: report, total_waste_estimate: null, efficiency_score: null,
    stages: [
      { stage: 'Allocated', label: 'Budget Allocation', amount: allocated },
      { stage: 'Spent', label: 'Actual Expenditure', amount: spent },
    ],
  };
}

const bar = () => screen.queryByTestId('national-spending-flow');

it('renders one proportional bar and its exact source for compatible reported figures', () => {
  render(<MoneyFlowHero data={flow(40e9, 31e9)} selectedYear='2024/25 9M' />);
  expect(screen.getByText('Counties · FY 2024/25 9M')).toBeVisible();
  expect(screen.getByRole('heading')).toHaveTextContent(
    'Counties spent 78% of their allocation (KES 31.00B of KES 40.00B).'
  );
  expect(bar()?.firstElementChild).toHaveStyle({ width: '77.5%' });
  expect(screen.getByText('KES 9.00B not yet spent at the time of the report.')).toBeVisible();
  const disclosure = screen.getByText('Source and method').closest('details')!;
  expect(disclosure).not.toHaveAttribute('open');
  expect(disclosure.querySelector('a')).toHaveAttribute('href', report);
  expect(disclosure).toHaveTextContent('KES 40,000,000,000');
  expect(disclosure).toHaveTextContent('KES 31,000,000,000');
});

it.each([
  { allocated: 100, spent: 0, percent: '0%', width: '0%', note: 'KES 100 not yet spent' },
  { allocated: 100, spent: 100, percent: '100%', width: '100%', note: 'KES 0 not yet spent' },
  { allocated: 100, spent: 105, percent: '105%', width: '100%', note: 'exceeded the allocation by KES 5' },
])('represents spending of $spent against $allocated', ({ allocated, spent, percent, width, note }) => {
  render(<MoneyFlowHero data={flow(allocated, spent)} />);
  expect(screen.getByRole('heading')).toHaveTextContent(`Counties spent ${percent}`);
  expect(bar()?.firstElementChild).toHaveStyle({ width });
  expect(screen.getByText(new RegExp(note))).toBeVisible();
});

it.each([
  { allocated: 0, spent: 60, amount: 'KES 0', note: 'requires a positive allocation' },
  { allocated: null, spent: 60, amount: 'KES 60', note: 'allocation is unavailable' },
  { allocated: 100, spent: null, amount: 'KES 100', note: 'spending is unavailable' },
])('preserves reported values with allocation $allocated and spending $spent', ({ allocated, spent, amount, note }) => {
  render(<MoneyFlowHero data={flow(allocated, spent)} />);
  expect(screen.getByText(amount)).toBeVisible();
  expect(screen.getByText(new RegExp(note))).toBeVisible();
  expect(bar()).not.toBeInTheDocument();
});

it.each([null, 'javascript:alert(1)'])('keeps reported figures without a traceable joint report (%s)', (url) => {
  render(<MoneyFlowHero data={{ ...flow(100, 60), source_document_url: url }} />);
  expect(screen.getByText('KES 100')).toBeVisible();
  expect(screen.getByText('KES 60')).toBeVisible();
  expect(screen.getByText(/comparison from one published report/)).toBeVisible();
  expect(bar()).not.toBeInTheDocument();
  expect(document.querySelector('a')).toBeNull();
});

it('withholds stale figures from a different period of the same fiscal year', () => {
  render(<MoneyFlowHero data={flow(100, 60)} selectedYear='2024/25' />);
  expect(screen.getByRole('heading')).toHaveTextContent('National spending figures unavailable');
  expect(screen.queryByText('KES 100')).not.toBeInTheDocument();
  expect(bar()).not.toBeInTheDocument();
});

it.each([
  { source: 'cra_model', label: 'Modelled allocation', publisher: 'equitable-share formula' },
  { source: 'mixed', label: 'Reported and modelled allocation', publisher: 'Commission on Revenue Allocation estimates' },
] as const)('labels $source provenance without a published verdict', ({ source, label, publisher }) => {
  render(<MoneyFlowHero data={flow(100, source === 'cra_model' ? null : 60, source)} />);
  expect(screen.getByText(label)).toBeVisible();
  expect(document.body.textContent).toContain(publisher);
  expect(document.querySelector('a')).toBeNull();
  expect(bar()).not.toBeInTheDocument();
});
