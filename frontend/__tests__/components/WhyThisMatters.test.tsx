import WhyThisMatters, { type CountyServiceObservation } from '@/components/WhyThisMatters';
import { render, screen, within } from '@testing-library/react';

const report: CountyServiceObservation = {
  basis: 'published-county-implementation',
  allocatedKes: 10_000_000,
  spentKes: 0,
  period: 'FY2024/25',
  countyCount: 7,
  source: { publisher: 'Synthetic publisher', url: 'https://example.org/report.pdf' },
};

it('shows the exact source, coverage and reported zero for a comparable service', () => {
  render(<WhyThisMatters observations={{ health: report }} />);
  const health = within(screen.getByRole('region', { name: 'Health' }));
  expect(health.getByText(/KES 10/)).toBeVisible();
  expect(health.getByText('0%')).toBeVisible();
  expect(health.getByText('7 of 47 counties reporting')).toBeVisible();
  expect(health.getByRole('link', { name: /Synthetic publisher.*FY2024\/25/ })).toHaveAttribute('href', report.source.url);
  expect(within(screen.getByRole('region', { name: 'Roads' })).getByText(/figures are unavailable/)).toBeVisible();
});

it('leaves an unqualified or incomplete service without a figure or source cue', () => {
  render(<WhyThisMatters observations={{
    health: { ...report, source: { ...report.source, url: 'javascript:alert(1)' } },
    education: { ...report, countyCount: 0 },
    roads: { ...report, allocatedKes: 0 },
  }} />);
  expect(screen.getAllByText(/figures are unavailable/)).toHaveLength(3);
  expect(screen.queryByText(/KES /)).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /Synthetic publisher/ })).not.toBeInTheDocument();
});
