import '@testing-library/jest-dom';
import { fireEvent, render, screen, within } from '@testing-library/react';
import PendingBillsAgingPanel from '@/app/debt/PendingBillsAgingPanel';
import { readScopedAging } from '@/lib/debt/scopedPendingBillsAging';

const measured: any = {
  version: 1, scope: 'county_executive', status: 'qualified', absent_reason: null,
  as_at: '2026-06-30', unit: 'KES', currency: 'KES', complete_total: null,
  artifact_sha256: 'a'.repeat(64), extraction_id: 12,
  source_url: 'https://cob.go.ke/report.pdf', publisher: 'Controller of Budget', table: 'Table 2.11', page: 53,
  reported_total: 10_000_000, chart_supported: true,
  coverage: { reported_counties: 46, expected_counties: 47, missing_counties: ['Nandi'], qualified_counties: ['Bomet'], complete: false },
  reader_notes: [{ code: 'reported_executive_population_only' }],
  buckets: ['Under one year', '1-2 years', '2-3 years', 'Over 3 years'].map((bucket, i) => ({ bucket, amount: (i + 1) * 1_000_000, raw_value: `${i + 1}`, absent_reason: null })),
};
const copy = () => JSON.parse(JSON.stringify(measured));

test.each(['2025-06-30', '2027-06-30', '0000-06-30'])('executive refuses an unsupported source date %s', (as_at) => {
  expect(readScopedAging({ ...measured, as_at }, 'county_executive')).toBeNull();
});

test('shows the four source bands, prints the oldest alarm, and preserves exact figures and coverage', () => {
  const { container } = render(<PendingBillsAgingPanel observations={{ county_executive: measured } as any} />);
  const chart = screen.getByRole('group', { name: 'County executive bills by age' });
  expect(within(chart).getAllByRole('button')).toHaveLength(4);
  expect(within(chart).getByRole('button', { name: 'Over 3 years 4M' })).toHaveAccessibleDescription('KES 4,000,000');
  expect(container.querySelectorAll('[data-signal=alarm]')).toHaveLength(1);
  expect(container.querySelector('[data-signal=alarm]')).toHaveAttribute('data-age-bar', 'Over 3 years');
  expect(screen.getByText(/46 of 47 counties/)).toBeInTheDocument();
  expect(screen.getByText('A complete total is unavailable.')).toBeInTheDocument();
  container.querySelector('details')!.open = true;
  expect(screen.getByRole('table')).toHaveTextContent('Under 1 year');
  expect(screen.getByRole('table')).toHaveTextContent('KES 4,000,000');
  container.querySelector('dialog')!.setAttribute('open', '');
  expect(screen.getByText('Missing: Nandi.')).toBeInTheDocument();
  expect(screen.getByText(/source qualifications or missing bands: Bomet/)).toBeInTheDocument();
});

test('has no tabular or plotted values for national or combined bills', () => {
  render(<PendingBillsAgingPanel observations={{ county_executive: measured } as any} />);
  const populations = screen.getByLabelText('Whose bills');
  for (const value of ['national', 'combined', 'county_assembly']) {
    fireEvent.change(populations, { target: { value } });
    expect(screen.getByText('Age of these bills not published')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByRole('group', { name: /bills by age/ })).not.toBeInTheDocument();
  }
});

test('an explicitly reported zero stays visible in the oldest band without an alarm', () => {
  const zero = copy();
  zero.buckets[3].amount = 0;
  zero.buckets[3].raw_value = '0';
  zero.reported_total = 6_000_000;
  const { container } = render(<PendingBillsAgingPanel observations={{ county_executive: zero } as any} />);
  expect(screen.getByRole('button', { name: 'Over 3 years 0' })).toHaveAccessibleDescription('KES 0');
  expect(container.querySelector('[data-signal=alarm]')).toBeNull();
});

test('a missing source cell is text, never a zero bar', () => {
  const missing = copy();
  missing.buckets[2].amount = null;
  missing.buckets[2].absent_reason = 'source_cell_not_reported';
  render(<PendingBillsAgingPanel observations={{ county_executive: missing } as any} />);
  expect(screen.getByRole('table')).toHaveTextContent('Not reported');
  expect(screen.queryByRole('group', { name: /bills by age/ })).not.toBeInTheDocument();
});

test.each([true, -1, NaN, Infinity, '123', {}, []])('refuses hostile money %p', (amount) => {
  const bad = copy(); bad.buckets[0].amount = amount;
  expect(readScopedAging(bad, 'county_executive')).toBeNull();
});

test('mismatched source scope, units, bands and false complete totals are refused', () => {
  for (const change of [{ scope: 'national' }, { unit: 'KES million' }, { complete_total: 10 }, { artifact_sha256: '' }, { page: true }]) {
    expect(readScopedAging({ ...measured, ...change }, 'county_executive')).toBeNull();
  }
  const bad = copy(); bad.buckets[0].bucket = '0-30d';
  expect(readScopedAging(bad, 'county_executive')).toBeNull();
});


test.each(['NaN', 'Infinity', '-Infinity', '-1', true, false, {}, []])('refuses hostile comparison operands %p before rendering', (operand) => {
  const invalid = copy();
  invalid.reader_notes = [{ code: 'known_payables_executive_sum_differs', comparison_table: 'Table 2.10', comparison_amount: operand }];
  expect(readScopedAging(invalid, 'county_executive')).toBeNull();
  render(<PendingBillsAgingPanel observations={{ county_executive: invalid } as any} />);
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  expect(screen.queryByText(/KES NaN|KES ∞/)).not.toBeInTheDocument();
});


test('loading and request errors never claim source observations are absent', () => {
  const { rerender } = render(<PendingBillsAgingPanel isLoading />);
  expect(screen.getByRole('status')).toHaveTextContent(/Loading/);
  expect(screen.queryByText(/Age of these bills not published/)).not.toBeInTheDocument();
  rerender(<PendingBillsAgingPanel observations={{ county_executive: measured } as any} isError />);
  expect(screen.getByRole('alert')).toHaveTextContent(/could not be loaded/);
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  expect(screen.queryByText(/Age of these bills not published/)).not.toBeInTheDocument();
});


test('uses the active language for aging copy and the source date', () => {
  localStorage.setItem('auditgava-lang', 'sw');
  const { LangProvider } = require('@/lib/i18n/LangProvider');
  const { unmount } = render(<LangProvider><PendingBillsAgingPanel observations={{ county_executive: measured } as any} /></LangProvider>);
  expect(screen.getByRole('heading')).toHaveTextContent('Muda ambao bili hazijalipwa');
  expect(screen.getByLabelText('Kundi la bili')).toBeInTheDocument();
  expect(screen.getByText(/30 Juni 2026/)).toBeInTheDocument();
  unmount();
  localStorage.removeItem('auditgava-lang');
});
