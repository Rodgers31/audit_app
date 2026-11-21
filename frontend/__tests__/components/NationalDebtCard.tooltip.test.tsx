import '@testing-library/jest-dom';
import { fireEvent, render, screen, within } from '@testing-library/react';

const mockOverview = jest.fn();
const mockTimeline = jest.fn();

jest.mock('@/lib/react-query/useDebt', () => ({
  useNationalDebtOverview: () => mockOverview(),
  useDebtTimeline: () => mockTimeline(),
}));
jest.mock('@/lib/react-query/useFiscal', () => ({ useFiscalSummary: () => ({ data: undefined }) }));

import NationalDebtCard from '@/components/dashboard/NationalDebtCard';
import { syntheticDebtTimeline20261105 } from '@/test/fixtures/deploymentDebt20261105';

function observation(year: number, ratio: number) {
  const result = syntheticDebtTimeline20261105(ratio);
  result.year = year;
  for (const proof of Object.values(result.qualifications)) proof.identity.period = String(year);
  result.qualifications.total.locator.cell = `${year}-12 / total`;
  result.qualifications.gdp.locator.date = String(year);
  result.period.stock_as_of_month = `${year}-12`;
  result.period.gdp_calendar_year = year;
  return result;
}

function renderTimeline(items: unknown[]) {
  mockTimeline.mockReturnValue({ data: { timeline: items }, isLoading: false });
  const { container } = render(<NationalDebtCard />);
  return {
    nominal: container.querySelector('[data-home-debt-plot="total"]')!,
    gdp: container.querySelector<HTMLElement>('[data-home-debt-plot="gdpRatio"]')!,
    readout: within(container.querySelector<HTMLElement>('[data-home-debt-readout]')!),
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockOverview.mockReturnValue({ data: undefined, isLoading: false });
});

test('keeps a legacy ratio without an explicit matched period out of the chart and readout', () => {
  const { period, ...legacy } = observation(2025, 65.9);
  expect(period.stock_as_of_month).toBe('2025-12');
  const { nominal, gdp, readout } = renderTimeline([legacy]);
  expect(nominal.querySelector('[data-debt-point="2025"]')).toBeInTheDocument();
  expect(gdp.querySelector('[data-debt-point]')).not.toBeInTheDocument();
  expect(within(gdp).getByText(/could not be verified together/)).toBeInTheDocument();
  expect(readout.queryByText('65.9%')).not.toBeInTheDocument();
  expect(readout.getByText('Unavailable')).toBeInTheDocument();
});

test.each([0, 65.9])('retains a verified %s%% observation', ratio => {
  const { gdp, readout } = renderTimeline([observation(2025, ratio)]);
  expect(gdp.querySelector('[data-debt-point="2025"]')).toBeInTheDocument();
  expect(readout.getByText(`${ratio}%`)).toBeInTheDocument();
  expect(readout.getByText(/Central Bank debt stock as of 2025-12/)).toBeInTheDocument();
});

test.each(['KES', 'USD'])('keeps withheld %s stock and components absent', unit => {
  const { nominal, readout } = renderTimeline([{ year: 2025, unit, total: null, domestic: null,
    external: null, gdp: null, gdp_ratio: null }]);
  expect(nominal.querySelector('[data-debt-point]')).not.toBeInTheDocument();
  expect(readout.getAllByText('Unavailable')).toHaveLength(4);
  expect(screen.getByText('Total Public Debt').parentElement!.parentElement).not.toHaveTextContent('KES 0');
});

test('shows ascending aligned years and keeps separate segments across an absent year', () => {
  const { nominal, gdp, readout } = renderTimeline([observation(2025, 65.9), observation(2023, 60)]);
  for (const plot of [nominal, gdp]) {
    expect(plot.querySelectorAll('[data-debt-line-segment]')).toHaveLength(2);
    expect(Array.from(plot.querySelectorAll('[data-debt-year-mark]'), mark => mark.textContent)).toEqual(['2023', '2024', '2025']);
  }
  fireEvent.change(screen.getByLabelText('Choose a year'), { target: { value: '2024' } });
  expect(readout.getAllByText('Unavailable')).toHaveLength(4);
  expect(readout.getByText('2024')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Choose a year'), { target: { value: '2023' } });
  expect(readout.getByText('60%')).toBeInTheDocument();
  expect(readout.getByText('KES 4.80T')).toBeInTheDocument();
  expect(readout.getByText('KES 7.20T')).toBeInTheDocument();
});
