import '@testing-library/jest-dom';
import { fireEvent, render, screen, within } from '@testing-library/react';
import AuditYearBars from '@/app/audits/AuditYearBars';
import type { AuditTrendsData } from '@/lib/api/audits';

const trends = (counts: Record<string, number>): AuditTrendsData => ({
  years: Object.keys(counts).map(Number), findings_per_year: counts,
  amount_per_year: {}, opinion_per_year: null, opinion_per_year_reason: null,
});

it('labels exact counts, exposes the same readout by focus and pointer, and clears selection', () => {
  const { container } = render(<AuditYearBars trends={trends({ '2023': 0, '2024': 15, '2025': 20 })} />);
  expect(screen.getByText('35 published findings have a recorded audit year.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '2023 · 0 Findings' })).toHaveTextContent('2023 · 0 Findings');
  expect(screen.getByText('Reports read per year unavailable')).toBeInTheDocument();
  const year = screen.getByRole('button', { name: '2024 · 15 Findings' });
  const readout = container.querySelector('[aria-live]')!;
  fireEvent.focus(year);
  expect(readout).toHaveTextContent('2024 · 15');
  fireEvent.click(year);
  expect(year).toHaveAttribute('aria-pressed', 'true');
  fireEvent.blur(year);
  expect(readout).toHaveTextContent('2024 · 15');
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(year).toHaveAttribute('aria-pressed', 'false');
  expect(readout).toBeEmptyDOMElement();
  fireEvent.click(year);
  fireEvent.click(year);
  expect(readout).toBeEmptyDOMElement();
  fireEvent.pointerEnter(year, { pointerType: 'mouse' });
  fireEvent.pointerLeave(year);
  fireEvent.click(year);
  fireEvent.pointerDown(document.body);
  expect(readout).toBeEmptyDOMElement();
  expect(year).toHaveAttribute('aria-pressed', 'false');
  const table = screen.getByRole('table', { hidden: true });
  expect(within(table).getAllByRole('row', { hidden: true })).toHaveLength(4);
});

it('keeps an absent or invalid count separate from a valid zero without fabricating years', () => {
  const input = trends({ '2023': 0, '2024': -3, '2025': Number.NaN });
  input.years = [2021, ...input.years, 2023];
  render(<AuditYearBars trends={input} />);
  expect(screen.getByRole('button', { name: '2021 · Unavailable Findings' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '2023 · 0 Findings' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '2024 · Unavailable Findings' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '2025 · Unavailable Findings' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /^2022/ })).not.toBeInTheDocument();
  expect(screen.getByText('Published findings with a recorded audit year')).toBeInTheDocument();
});

it('shows the recorded-year absence explicitly when the series is empty', () => {
  render(<AuditYearBars trends={trends({})} />);
  expect(screen.getByText('No published findings with a recorded audit year are available.')).toBeInTheDocument();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});

it('scrolls the focused region by arrow key while keeping bar keys independent', () => {
  render(<AuditYearBars trends={trends({ '2024': 15, '2025': 20 })} />);
  const region = screen.getByRole('region', { name: 'Audit year bars' });
  Object.defineProperty(region, 'clientWidth', { value: 300 });
  fireEvent.keyDown(region, { key: 'ArrowRight' });
  expect(region.scrollLeft).toBe(150);
  fireEvent.keyDown(region, { key: 'ArrowLeft' });
  expect(region.scrollLeft).toBe(0);
  fireEvent.keyDown(screen.getByRole('button', { name: '2024 · 15 Findings' }), { key: 'ArrowRight' });
  expect(region.scrollLeft).toBe(0);
});
