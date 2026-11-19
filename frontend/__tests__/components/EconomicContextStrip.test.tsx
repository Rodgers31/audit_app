import { render, screen } from '@testing-library/react';
import EconomicContextStrip from '@/components/budget/EconomicContextStrip';
import type { FigureQualification } from '@/lib/evidence/qualification';
import { headlineInflationReceipt, nominalGdpReceipt, syntheticEconomicContext } from '../../test/fixtures/budgetEconomicContext';

const targetLink = /CBK Monetary Policy (Committee Report|Statement)/;

it('keeps independent annual GDP value and real growth and withholds both legacy fiscal ratios', () => {
  render(<EconomicContextStrip ctx={syntheticEconomicContext} />);
  expect(screen.getAllByRole('heading', { level: 3 }).map(heading => heading.textContent)).toEqual([
    'GDP', 'Budget / GDP', 'Inflation',
  ]);
  expect(screen.getByText('KES 12.35T')).toBeInTheDocument();
  expect(screen.getByText('At current prices in calendar year 2025.')).toBeInTheDocument();
  expect(screen.getByText('Real GDP growth in 2024: -0.4%.')).toBeInTheDocument();
  expect(screen.getByText('GDP at current prices was KES 12,345,678,000,000 in calendar year 2025.')).toBeInTheDocument();
  expect(screen.getByText('Not published yet')).toBeInTheDocument();
  expect(screen.queryByText(/32\.1%|15\.2%/)).toBeNull();
});

it('withholds nominal GDP when its qualification belongs to a different year', () => {
  render(<EconomicContextStrip ctx={{ ...syntheticEconomicContext, gdp_as_of: '2024-12-31' }} />);
  expect(screen.queryByText('KES 12.35T')).toBeNull();
  expect(screen.getByText('Real GDP growth in 2024: -0.4%.')).toBeInTheDocument();
});

it('preserves zero in a matched nominal GDP observation', () => {
  render(<EconomicContextStrip ctx={{ gdp_billion_kes: 0, gdp_as_of: '2025-12-31', qualifications: { gdp: { total_national_gdp: nominalGdpReceipt } } }} />);
  expect(screen.getByText('KES 0B')).toBeInTheDocument();
});

it.each([
  [2.49, 'Below target'],
  [2.5, null],
  [7.32, null],
  [7.5, null],
  [7.51, 'Above target'],
])('checks rate %s against the inclusive policy band', (rate, verdict) => {
  render(<EconomicContextStrip ctx={{ ...syntheticEconomicContext, inflation_pct: rate }} />);
  const card = screen.getByRole('heading', { name: /^Inflation$/ }).parentElement;
  expect(card).toHaveTextContent('CBK target range: 2.5–7.5%.');
  expect(screen.getByRole('link', { name: targetLink })).toHaveAttribute('href', expect.stringContaining('#page=25'));
  if (verdict) expect(screen.getByText(verdict, { exact: true })).toHaveClass('text-signal-caution');
  else expect(screen.queryByText(/^(Above|Below) target$/)).toBeNull();
});

it.each([
  ['2024-06-30', false, null],
  ['2024-07-31', true, '20'],
  ['2026-06-30', true, '20'],
  ['2026-07-31', true, '25'],
  ['2027-06-30', true, '25'],
  ['2027-07-31', false, null],
  ['2026-02-31', false, null],
])('only cites an effective published policy for a valid observation on %s', (day, comparable, page) => {
  render(<EconomicContextStrip ctx={{
    ...syntheticEconomicContext, inflation_as_of: day,
    qualifications: { inflation: { inflation_rate_12m: headlineInflationReceipt(day.slice(0, 7)) } },
  }} />);
  expect(screen.getByText('7.51%')).toBeInTheDocument();
  if (comparable) {
    expect(screen.getByText('Above target')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: targetLink })).toHaveAttribute('href', expect.stringContaining(`#page=${page}`));
  } else {
    expect(screen.queryByText('Above target')).toBeNull();
    expect(screen.queryByRole('link', { name: targetLink })).toBeNull();
  }
});

it.each([
  ['unverified', { ...headlineInflationReceipt('2026-10'), value_checked: false }],
  ['different month', headlineInflationReceipt('2026-09')],
  ['different publisher', { ...headlineInflationReceipt('2026-10'), publisher: 'World Bank' }],
  ['unknown source', { ...headlineInflationReceipt('2026-10'), source_url: null }],
  ['projected', { ...headlineInflationReceipt('2026-10'), status: 'projected' }],
] satisfies [string, FigureQualification][])('keeps %s headline data neutral without a band comparison', (_type, receipt) => {
  render(<EconomicContextStrip ctx={{ ...syntheticEconomicContext, qualifications: { inflation: { inflation_rate_12m: receipt } } }} />);
  expect(screen.getByText('7.51%')).toBeInTheDocument();
  expect(screen.queryByText('Above target')).toBeNull();
  expect(screen.queryByRole('link', { name: targetLink })).toBeNull();
});

it('labels annual-average inflation and leaves missing observations absent', () => {
  const { rerender } = render(<EconomicContextStrip ctx={{
    inflation_pct: 8.3, inflation_measure: 'CPI inflation, annual average', inflation_as_of: '2025-12-31',
  }} />);
  expect(screen.getByText('Annual average CPI inflation · 2025')).toBeInTheDocument();
  expect(screen.getByText('8.3%')).toBeInTheDocument();
  expect(screen.queryByText('Above target')).toBeNull();
  expect(screen.queryByRole('link', { name: targetLink })).toBeNull();
  rerender(<EconomicContextStrip ctx={{ inflation_pct: null }} />);
  expect(screen.queryByText('8.3%')).toBeNull();
  expect(screen.getAllByText('Not published yet')).toHaveLength(3);
});
