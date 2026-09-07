/**
 * The home card's External / Domestic tiles, rendered from the real payload.
 *
 * Companion to __tests__/lib/debt/externalDomesticSplit.test.ts, which pins the
 * reconciliation. This file pins what the COMPONENT prints.
 *
 * Against pre-fix `NationalDebtCard.tsx` these fail. It read
 * `apiData.summary.external_debt` straight through and rendered
 *
 *   EXTERNAL DEBT   KES 5.27T   44.4% of total
 *
 * That figure is not the sum of any creditors this site publishes: the backend
 * computes the register's own external total (4.80T), then overwrites it with
 * the register TOTAL re-split by a proportion from the DebtTimeline table. The
 * parts still sum to the headline, so nothing looked wrong — but /debt's
 * creditor cards, drawn from the same response's `categories`, add to 4.80T.
 * The two figures a reader is invited to connect were 467.7Bn apart, with
 * nothing on either page saying so.
 *
 * Payload: GET /api/v1/debt/national, 2026-09-06 (production, `5ff5fa9`).
 */
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

const LIVE_CATEGORIES = {
  external_multilateral: { loan_count: 13, total_principal: 2_695_722_058_890.222 },
  external_bilateral: { loan_count: 17, total_principal: 1_087_508_999_335.458 },
  external_commercial: { loan_count: 12, total_principal: 1_014_147_800_000 },
  domestic_bonds: { loan_count: 2, total_principal: 5_878_982_400_000 },
  domestic_bills: { loan_count: 1, total_principal: 1_090_017_800_000 },
  domestic_overdraft: { loan_count: 2, total_principal: 89_599_800_000 },
  pending_bills: { loan_count: 13, total_principal: 931_300_000_000 },
};

/** The re-split the backend serves — 467.7Bn away from the categories. */
const LIVE_SUMMARY = {
  external_debt: 5_265_016_798_890.222,
  domestic_debt: 6_590_962_059_335.458,
  external_percentage: 44.4,
  domestic_percentage: 55.6,
};

const LIVE_OVERVIEW = {
  data: {
    total_outstanding: 11_855_978_858_225.68,
    loan_count: 60,
    debt_to_gdp_ratio: 69.3,
    summary: LIVE_SUMMARY,
    categories: LIVE_CATEGORIES,
  },
};

const mockOverview = jest.fn();
const mockTimeline = jest.fn();
const mockFiscal = jest.fn();
const mockBroader = jest.fn();

jest.mock('@/lib/react-query/useDebt', () => ({
  useNationalDebtOverview: () => mockOverview(),
  useDebtTimeline: () => mockTimeline(),
  useBroaderDebt: () => mockBroader(),
}));
jest.mock('@/lib/react-query/useFiscal', () => ({
  useFiscalSummary: () => mockFiscal(),
}));

jest.mock('framer-motion', () => ({
  motion: new Proxy(
    {},
    { get: () => ({ children, ...props }: any) => <div {...props}>{children}</div> },
  ),
  AnimatePresence: ({ children }: any) => <>{children}</>,
  useInView: () => true,
}));

jest.mock('recharts', () => {
  const Pass = ({ children }: any) => <div>{children}</div>;
  return {
    __esModule: true,
    ResponsiveContainer: Pass,
    ComposedChart: (props: any) => <div>{props.children}</div>,
    CartesianGrid: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    Legend: () => null,
    Area: () => null,
    Line: () => null,
    Bar: () => null,
    ReferenceLine: () => null,
  };
});

import NationalDebtCard from '@/components/dashboard/NationalDebtCard';

beforeEach(() => {
  jest.clearAllMocks();
  mockFiscal.mockReturnValue({ data: undefined });
  mockTimeline.mockReturnValue({ data: undefined, isLoading: false });
  mockBroader.mockReturnValue({ data: undefined, isLoading: false });
  mockOverview.mockReturnValue({ data: LIVE_OVERVIEW, isLoading: false });
});

describe('external/domestic tiles — while the two sources disagree', () => {
  it('shows the register sum the creditor cards add up to, not the re-split', () => {
    render(<NationalDebtCard />);
    expect(screen.getByText('KES 4.80T')).toBeInTheDocument();
    expect(screen.queryByText('KES 5.27T')).not.toBeInTheDocument();
  });

  it('shows the domestic side on the same basis', () => {
    render(<NationalDebtCard />);
    expect(screen.getByText('KES 7.06T')).toBeInTheDocument();
    expect(screen.queryByText('KES 6.59T')).not.toBeInTheDocument();
  });

  it('does not publish the API share of 44.4% against cards that make 40.5%', () => {
    render(<NationalDebtCard />);
    expect(screen.queryByText(/44\.4%/)).not.toBeInTheDocument();
    expect(screen.queryByText(/55\.6%/)).not.toBeInTheDocument();
  });

  it('makes the disagreement visible, with its size', () => {
    render(<NationalDebtCard />);
    // The card's own formatter rounds billions to whole units, as it does for
    // every other figure on it.
    expect(screen.getByText(/Two sources disagree by KES 468B/i)).toBeInTheDocument();
  });

  it('says which of the two the tiles are, and where the rows can be seen', () => {
    render(<NationalDebtCard />);
    expect(screen.getByText(/our own creditor rows added up/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '/debt' })).toBeInTheDocument();
  });

  it('keeps the two tiles summing to the headline total', () => {
    render(<NationalDebtCard />);
    // 4.80T + 7.06T = 11.86T, the figure at the top of the same card.
    expect(screen.getByText('KES 11.86T')).toBeInTheDocument();
  });
});

describe('external/domestic tiles — once the backend fix lands', () => {
  it('reverts to the API figures and drops the disclosure with no further change here', () => {
    mockOverview.mockReturnValue({
      data: {
        data: {
          ...LIVE_OVERVIEW.data,
          summary: {
            external_debt: 4_797_378_858_225.68,
            domestic_debt: 7_058_600_000_000,
          },
        },
      },
      isLoading: false,
    });
    render(<NationalDebtCard />);
    expect(screen.getByText('KES 4.80T')).toBeInTheDocument();
    expect(screen.queryByText(/Two sources disagree/i)).not.toBeInTheDocument();
  });
});

describe('external/domestic tiles — absent inputs', () => {
  it('renders em dashes rather than a fabricated split when the summary is empty', () => {
    mockOverview.mockReturnValue({
      data: { data: { total_outstanding: 11_855_978_858_225.68, summary: {}, categories: {} } },
      isLoading: false,
    });
    render(<NationalDebtCard />);
    expect(screen.queryByText(/Two sources disagree/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/% of total/)).not.toBeInTheDocument();
  });
});
