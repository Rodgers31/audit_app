import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

/**
 * Units and risk-band regression fixtures for HeroSection.
 *
 * PR #136 finding F1 (the merge blocker) — `HeroSection.tsx:89` read
 * `latest.total * 1_000_000_000` from a /debt/timeline row. Since the stage1
 * 3a migration those rows are raw KES and say so with `unit: "KES"`, so the
 * multiplication produced a headline 10⁹× too large. Unlike NationalDebtCard,
 * `latest` here is the RAW API row rather than one already normalised for the
 * chart, so it needs `toRawKES` directly.
 *
 * PR #135 finding G3 — when no risk band could be established, `{riskLevel}`
 * interpolated `null`, rendering a badge reading just " Risk" in the gold
 * (non-high) styling: an outage presented as a reassuring rating.
 *
 * Both unit directions are covered because the deploy precedes the migration.
 */

const RAW_KES_ROW = {
  year: 2024,
  external: 5_100_000_000_000,
  domestic: 5_600_000_000_000,
  total: 10_700_000_000_000,
  gdp: 16_224_478_000_000,
  gdp_ratio: 65.9,
  unit: 'KES' as const,
};

const BILLIONS_ROW = {
  year: 2024,
  external: 5_100,
  domestic: 5_600,
  total: 10_700,
  gdp: 16_224.478,
  gdp_ratio: 65.9,
};

const mockTimeline = jest.fn();
const mockOverview = jest.fn();
const mockFiscal = jest.fn();

jest.mock('@/lib/react-query/useDebt', () => ({
  useDebtTimeline: () => mockTimeline(),
  useNationalDebtOverview: () => mockOverview(),
}));
jest.mock('@/lib/react-query/useFiscal', () => ({
  useFiscalSummary: () => mockFiscal(),
}));
jest.mock('framer-motion', () => ({
  motion: new Proxy(
    {},
    { get: () => ({ children, ...p }: any) => <div {...p}>{children}</div> }
  ),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
jest.mock('../../components/dashboard/DebtExplainerModal', () => {
  const M = () => <span />;
  M.displayName = 'DebtExplainerModalStub';
  return { __esModule: true, default: M };
});

import { SummaryStrip } from '@/components/dashboard/HeroSection';

beforeEach(() => {
  jest.clearAllMocks();
  mockFiscal.mockReturnValue({ data: undefined });
  mockOverview.mockReturnValue({ data: undefined });
  mockTimeline.mockReturnValue({ data: undefined });
});

describe('F1 — the headline must respect the declared unit', () => {
  it('does not multiply an already-raw KES total by 1e9', () => {
    mockTimeline.mockReturnValue({ data: { timeline: [RAW_KES_ROW] } });
    render(<SummaryStrip />);
    // 10.7T. Pre-fix this produced 10700000000.00.
    expect(screen.getByText('10.70')).toBeInTheDocument();
  });

  it('still scales a pre-migration billions total', () => {
    // POSITIVE CONTROL — the deploy precedes the migration.
    mockTimeline.mockReturnValue({ data: { timeline: [BILLIONS_ROW] } });
    render(<SummaryStrip />);
    expect(screen.getByText('10.70')).toBeInTheDocument();
  });
});

describe('G3 — a blank risk badge is not an assessment', () => {
  it('says "not assessed" when no band can be established', () => {
    mockTimeline.mockReturnValue({
      data: { timeline: [{ ...RAW_KES_ROW, gdp_ratio: 0 }] },
    });
    render(<SummaryStrip />);
    expect(screen.getByText(/not assessed/i)).toBeInTheDocument();
  });

  it('still renders a band that can be established', () => {
    mockTimeline.mockReturnValue({ data: { timeline: [RAW_KES_ROW] } });
    render(<SummaryStrip />);
    expect(screen.getByText(/High/)).toBeInTheDocument();
  });
});
