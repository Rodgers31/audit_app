import { render, screen, within } from '@testing-library/react';
import DebtServiceObservations from '@/components/debt/DebtServiceObservations';
import { buildDebtServiceSeries, FiscalYearRow } from '@/lib/debt/debtServiceSeries';

function observations(years: FiscalYearRow[]) {
  const { container } = render(<DebtServiceObservations points={buildDebtServiceSeries(years)} />);
  container.querySelector('details')!.open = true;
  return screen.getByRole('table', { name: 'Debt cost observations by fiscal year' });
}

describe('readable debt cost observations', () => {
  it('retains supplied fiscal order, exact KES values and a valid zero service share', () => {
    const table = observations([
      { fiscal_year: 'FY 2024/25', debt_service_cost: 1_234_567_890.25, debt_service_per_shilling: 50, total_revenue: 2_469_135_780.5 },
      { fiscal_year: 'FY 2025/26', debt_service_cost: 0, debt_service_per_shilling: 0, total_revenue: 100_000_000_000 },
    ]);
    expect(within(table).getAllByRole('rowheader').map(row => row.textContent)).toEqual(['FY 2024/25', 'FY 2025/26']);
    expect(within(table).getAllByRole('cell').map(cell => cell.textContent)).toEqual([
      '1,234,567,890.25', '2,469,135,780.5', '50.0%', '0', '100,000,000,000', '0.0%',
    ]);
  });

  it('keeps published service beside missing revenue and explains the withheld share', () => {
    const table = observations([
      { fiscal_year: 'FY 2026/27', debt_service_cost: 2_315_900_000_000, total_revenue: null },
      { fiscal_year: 'FY 2027/28', debt_service_cost: 123 },
    ]);
    expect(within(table).getAllByRole('cell').map(cell => cell.textContent)).toEqual([
      '2,315,900,000,000', 'Not published', 'Withheld: revenue not published',
      '123', 'Not published', 'Withheld: revenue not published',
    ]);
  });

  it('distinguishes missing service, zero revenue and absence of both inputs', () => {
    const table = observations([
      { fiscal_year: 'FY 2024/25', debt_service_cost: null, total_revenue: 400 },
      { fiscal_year: 'FY 2025/26', debt_service_cost: 50, total_revenue: 0 },
      { fiscal_year: 'FY 2026/27', debt_service_cost: null, total_revenue: null },
    ]);
    expect(within(table).getAllByRole('cell').map(cell => cell.textContent)).toEqual([
      'Not published', '400', 'Withheld: debt service not published',
      '50', '0', 'Withheld: revenue must be greater than zero',
      'Not published', 'Not published', 'Withheld: debt service not published; revenue not published',
    ]);
  });

  it('does not display non-finite observations as numbers or a missing year as a real year', () => {
    const table = observations([
      { debt_service_cost: NaN, total_revenue: Infinity },
      { fiscal_year: 'FY 2028/29', debt_service_cost: 200, total_revenue: -Infinity },
    ]);
    expect(within(table).getAllByRole('rowheader')[0]).toHaveTextContent('Fiscal year not published');
    expect(within(table).getAllByRole('cell').map(cell => cell.textContent)).toEqual([
      'Not published', 'Not published', 'Withheld: debt service not published; revenue not published',
      '200', 'Not published', 'Withheld: revenue not published',
    ]);
  });

  it('does not invent observations for an empty series', () => {
    const table = observations([]);
    expect(within(table).queryAllByRole('cell')).toHaveLength(0);
  });
});


it('carries each measure source, vintage and printed precision into readable history', () => {
  const source = { title: 'Inert source fixture', url: 'https://www.treasury.go.ke/fixture.pdf', page: 'Table 4, PDF p.37', sha256: 'a'.repeat(64) };
  const proof = { value_kes: 1201033000000, fiscal_year: 'FY 2022/23', basis: 'total_debt_service_interest_and_principal', vintage: 'Preliminary', precision_kes: 1000000, source };
  const table = observations([
    { fiscal_year: 'FY 2022/23', debt_service_cost: 1201033000000, total_revenue: 2041119000000, debt_service_per_shilling: 58.8,
      measure_qualifications: { debt_service_cost: proof, total_revenue: { ...proof, value_kes: 2041119000000, basis: 'ordinary_revenue_excl_aia' } } },
    { fiscal_year: 'FY 2026/27', debt_service_cost: 2315900000000, total_revenue: 2985700000000,
      measure_qualifications: { debt_service_cost: { ...proof, fiscal_year: 'FY 2026/27', vintage: 'Approved', precision_kes: 100000000 } } },
  ]);
  expect(within(table).getAllByText(/Preliminary; printed precision KES 1,000,000/)).toHaveLength(2);
  expect(within(table).getByText(/Approved; printed precision KES 100,000,000/)).toBeInTheDocument();
  expect(within(table).getAllByRole('link')).toHaveLength(3);
  expect(within(table).getAllByRole('link')[0]).toHaveAttribute('href', source.url);
  expect(within(table).getByText('Withheld: compatible source evidence unconfirmed')).toBeInTheDocument();
});
