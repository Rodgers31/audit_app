import '@testing-library/jest-dom';
import { render, screen, within } from '@testing-library/react';
import { cloneElement } from 'react';

const mockOverview = jest.fn();
const mockTimeline = jest.fn();
const mockFiscal = jest.fn();
const mockBroader = jest.fn();
const chartProps: any[] = [];
const tooltipContents: any[] = [];

jest.mock('@/lib/react-query/useDebt', () => ({
  useNationalDebtOverview: () => mockOverview(),
  useDebtTimeline: () => mockTimeline(),
  useBroaderDebt: () => mockBroader(),
}));
jest.mock('@/lib/react-query/useFiscal', () => ({
  useFiscalSummary: () => mockFiscal(),
}));
jest.mock('framer-motion', () => ({
  motion: new Proxy({}, {
    get: () => ({ children }: any) => <div>{children}</div>,
  }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
  useInView: () => true,
}));
jest.mock('recharts', () => {
  const Pass = ({ children }: any) => <div>{children}</div>;
  return {
    __esModule: true,
    ResponsiveContainer: Pass,
    ComposedChart: (props: any) => {
      chartProps.push(props);
      return <div>{props.children}</div>;
    },
    Tooltip: ({ content }: any) => {
      tooltipContents.push(content);
      return null;
    },
    CartesianGrid: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Area: () => null,
    Line: () => null,
  };
});

import NationalDebtCard from '@/components/dashboard/NationalDebtCard';
import { syntheticDebtTimeline20261105 } from '@/test/fixtures/deploymentDebt20261105';

const timelineRow = {
  year: 2025,
  external: 5_000_000_000_000,
  domestic: 6_000_000_000_000,
  total: 11_000_000_000_000,
  gdp: null,
  gdp_ratio: null as number | null,
  unit: 'KES',
};

function renderHoveredRatio(ratio: number | null) {
  mockTimeline.mockReturnValue({
    data: { timeline: [ratio === null ? timelineRow : syntheticDebtTimeline20261105(ratio)] },
    isLoading: false,
  });
  render(<NationalDebtCard />);

  // Use the row transformed by the real card and the actual tooltip element
  // passed to Recharts. A row with debt totals is hoverable even when its ratio
  // is absent; the line series simply has no point for that year.
  const row = chartProps[0].data[0];
  return render(cloneElement(tooltipContents[0], {
    active: true,
    payload: [{ payload: row }],
    label: row.year,
  })).container;
}

beforeEach(() => {
  jest.clearAllMocks();
  chartProps.length = 0;
  tooltipContents.length = 0;
  mockFiscal.mockReturnValue({ data: undefined });
  mockBroader.mockReturnValue({ data: undefined, isLoading: false });
  mockOverview.mockReturnValue({
    data: { data: { total_outstanding: timelineRow.total, debt_to_gdp_ratio: null, summary: {}, categories: {} } },
    isLoading: false,
  });
});

describe('home debt chart tooltip', () => {
  it('shows absence for a hoverable year without a ratio', () => {
    const tooltip = renderHoveredRatio(null);
    expect(within(tooltip).queryByText('null%')).not.toBeInTheDocument();
    expect(within(tooltip).queryByText('%')).not.toBeInTheDocument();
    expect(within(tooltip).getByText('—')).toBeInTheDocument();
  });

  it.each([0, 65.9])('retains a reported %s%% ratio', (ratio) => {
    const tooltip = renderHoveredRatio(ratio);
    expect(within(tooltip).getByText(`${ratio}%`)).toBeInTheDocument();
  });

  it.each(['KES', 'USD'])('keeps withheld %s stock amounts absent in headline, chart and tooltip', (unit) => {
    mockOverview.mockReturnValue({ data: undefined, isLoading: false });
    mockTimeline.mockReturnValue({ data: { timeline: [{ ...timelineRow,
      unit, total: null, external: null, domestic: null, gdp: null }] }, isLoading: false });
    render(<NationalDebtCard />);
    const row = chartProps[0].data[0];
    expect(row.total).toBeNull();
    expect(row.external).toBeNull();
    expect(row.domestic).toBeNull();
    expect(screen.getByText('Total Public Debt').parentElement!.parentElement).not.toHaveTextContent('KES 0');
    const tooltip = render(cloneElement(tooltipContents[0], {
      active: true, payload: [{ payload: row }], label: row.year,
    })).container;
    expect(within(tooltip).queryByText('0B')).not.toBeInTheDocument();
  });
});
