import RevenueMix, { type RevFy, type RevSource } from '@/components/budget/RevenueMix';
import { render, screen, within } from '@testing-library/react';
import { publishedObservation, revenueDetails } from '@/tests/revenueMixTestUtils';

const report = { url: 'https://www.kra.go.ke/performance', version: 'dashboard_bundle' };
const heads: RevSource[] = [
  { revenue_type: 'PAYE', amount: 599, basis: 'published', source: report, yoy_growth_pct: 6.7 },
  { revenue_type: 'VAT', measure: 'Domestic VAT', amount: 355, basis: 'published', source: report },
  { revenue_type: 'Customs & Import Duty', measure: 'Customs departmental collections, including agency levies',
    amount: 989, basis: 'published', source: report, yoy_growth_pct: 12.5 },
  { revenue_type: 'Excise Duty', measure: 'Domestic excise', amount: 62, basis: 'published', source: report, yoy_growth_pct: -10.9 },
  { revenue_type: 'Corporation Tax', amount: 347, basis: 'published', source: report },
];

const latest: RevFy = { fiscal_year: 'FY 2025/26', sources: heads };
const rows = () => Array.from(document.querySelectorAll<HTMLElement>('[data-revenue-card]'));

it('ranks the reported measures on one scale and uses the publisher’s signed growth', () => {
  render(<RevenueMix revenueBySource={[latest]} />);
  expect(rows().map(row => row.querySelector('button span')?.textContent)).toEqual([
    'Customs (incl. agency levies)', 'PAYE', 'Domestic VAT', 'Corporation tax', 'Domestic excise',
  ]);
  expect(screen.getByText(/Customs .* is the largest amount shown, at KES 989B/)).toBeVisible();
  expect(screen.getByRole('button', { name: /^Domestic excise/ })).toHaveAccessibleDescription('KES 62,000,000,000 · -10.9% year over year, as reported');
  expect(screen.getByText(/the 16% on most goods/)).toBeVisible();
  expect(screen.getByTestId('revenue-section-source')).toHaveTextContent('Source: KRA annual performance (dashboard edition)');
});

it('keeps zero, separate publisher totals and exact qualified historical amounts', () => {
  const current = { ...latest, sources: [
    { ...heads[0], amount: 0 },
    { revenue_type: 'Other Tax Revenue', basis: 'residual', amount: 181.2, basis_note: 'Includes withholding tax' },
    { revenue_type: 'Total Agency Revenue', amount: 7.4, basis: 'published', category: 'total' },
  ] };
  render(<RevenueMix revenueBySource={[
    { fiscal_year: 'FY 2022/23', sources: [{ ...heads[0], amount: 495.235, basis: 'derived', basis_note: 'Derived from published growth.' }] },
    current,
  ]} />);
  expect(rows()).toHaveLength(1);
  expect(screen.getByRole('button', { name: /^PAYE.*KES 0B/ })).toBeVisible();
  expect(rows()[0].querySelector('span[aria-hidden]')).toBeNull();
  expect(screen.queryByRole('button', { name: /Total Agency Revenue|Other Tax Revenue/ })).toBeNull();
  const sheet = within(revenueDetails());
  expect(sheet.getByText('KES 7,400,000,000 · Publisher-stated')).toBeVisible();
  expect(publishedObservation('PAYE', 'FY 2022/23').getByText('PAYE · KES 495,235,000,000 · Derived amount')).toBeVisible();
  expect(publishedObservation('Other Tax Revenue').queryByText(/181|Includes withholding tax/)).toBeNull();
});

it('uses the actual release independently of projections and labels compatible adjacent comparisons', () => {
  render(<RevenueMix revenueBySource={[
    { fiscal_year: 'FY 2026/27', sources: [{ ...heads[1], amount: 998, basis: 'projected' }] },
    { fiscal_year: 'FY 2024/25', sources: [
      { ...heads[1], amount: 325 },
      { ...heads[2], amount: 1 },
      { ...heads[4], amount: 340, absent_reason: 'UNAVAILABLE' },
      { ...heads[3], amount: 1, measure: 'Different excise coverage', yoy_growth_pct: null },
    ] },
    latest,
  ]} />);
  expect(screen.getByText(/KRA collections, FY 2025\/26/)).toBeVisible();
  expect(screen.getByRole('button', { name: /^Domestic VAT/ })).toHaveAccessibleDescription(/\+9.2% year over year, calculated/);
  expect(screen.getByRole('button', { name: /^Customs/ })).toHaveAccessibleDescription(/\+12.5% year over year, as reported/);
  expect(screen.getByRole('button', { name: /^Corporation tax/ })).toHaveAccessibleDescription(/Year-over-year change unavailable/);
});

it('withholds lifetime-gap or incompatible growth and avoids unsupported publisher credit', () => {
  const current = { ...latest, sources: [{ ...heads[1] }, { revenue_type: 'PAYE', amount: 1, basis: null, basis_note: 'KRA Annual Performance old note' }] };
  const { rerender } = render(<RevenueMix revenueBySource={[
    { fiscal_year: 'FY 2023/24', sources: [{ ...heads[1], amount: 325 }] },
    current,
  ]} />);
  expect(screen.getByRole('button', { name: /^Domestic VAT/ })).toHaveAccessibleDescription(/Year-over-year change unavailable/);
  expect(screen.getByTestId('revenue-section-source')).not.toHaveTextContent('KRA');
  expect(rows()[1]).toHaveTextContent('income tax withheld from salaries');
  expect(rows()[1]).not.toHaveTextContent('KRA Annual Performance');

  rerender(<RevenueMix revenueBySource={[
    { fiscal_year: 'FY 2024/25', sources: [{ ...heads[1], measure: 'All VAT', amount: 325 }] },
    current,
  ]} />);
  expect(screen.getByRole('button', { name: /^Domestic VAT/ })).toHaveAccessibleDescription(/Year-over-year change unavailable/);
});
