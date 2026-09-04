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
    // 10.7T. Pre-fix this produced 10700000000.00T.
    // The figure and its "T" suffix render in one text node beside a
    // separate "KES" span, so match the node rather than a bare number.
    expect(screen.getByText(/^10\.70T$/)).toBeInTheDocument();
    expect(screen.queryByText(/\d{7,}\.\d\dT/)).toBeNull();
  });

  it('still scales a pre-migration billions total', () => {
    // POSITIVE CONTROL — the deploy precedes the migration.
    mockTimeline.mockReturnValue({ data: { timeline: [BILLIONS_ROW] } });
    render(<SummaryStrip />);
    expect(screen.getByText(/^10\.70T$/)).toBeInTheDocument();
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
    // Match the risk VALUE node exactly. The redesigned cell also renders a
    // Low/Moderate/High legend beneath it, so a loose /High/ matches twice.
    expect(screen.getByText(/^High Risk$/i)).toBeInTheDocument();
  });
});

/* ═══════════════════════════════════════════════════════════════════════════
   The alarm treatment is data-driven, not decorative.

   The headline turns copper only while a published figure exceeds a published
   threshold, and it names the threshold when it does. These pin both
   directions, because a warning that cannot switch off is not a warning.
   ═══════════════════════════════════════════════════════════════════════════ */

/** /api/v1/fiscal/summary → debt_anchor, as served on 2026-09-04. */
const ANCHOR_BREACHED = {
  data: { debt_anchor: { anchor_pct_gdp: 55, debt_to_gdp_pct: 69.3, above_anchor: true } },
};

const OVERVIEW_HIGH_RISK = {
  data: {
    total_outstanding: 13_552_833_964_464,
    debt_to_gdp_ratio: 69.3,
    debt_sustainability: {
      risk_level: 'High',
      assessment: 'Kenya\u2019s debt remains elevated. The IMF classifies Kenya at high risk of debt distress.',
    },
  },
};

describe('the headline states why it is alarmed', () => {
  it('names the anchor and the size of the breach', () => {
    mockFiscal.mockReturnValue(ANCHOR_BREACHED);
    mockOverview.mockReturnValue(OVERVIEW_HIGH_RISK);
    render(<SummaryStrip />);
    // 69.3 - 55 = 14.3 points. Stated, so the reader does not have to subtract.
    expect(screen.getByText(/14\.3 pts above the 55% anchor/i)).toBeInTheDocument();
  });

  it('attributes the distress rating to the IMF rather than asserting it', () => {
    mockFiscal.mockReturnValue(ANCHOR_BREACHED);
    mockOverview.mockReturnValue(OVERVIEW_HIGH_RISK);
    render(<SummaryStrip />);
    expect(screen.getByText(/high risk of debt distress · imf/i)).toBeInTheDocument();
  });

  it('colours the two debt figures only while the threshold is exceeded', () => {
    mockFiscal.mockReturnValue(ANCHOR_BREACHED);
    mockOverview.mockReturnValue(OVERVIEW_HIGH_RISK);
    const { container } = render(<SummaryStrip />);
    const figures = Array.from(container.querySelectorAll('[data-figure]'));
    expect(figures).toHaveLength(2);
    figures.forEach((f) => expect(f.className).toMatch(/text-gov-copper/));
  });

  it('drops the alarm entirely when debt is inside the anchor', () => {
    // NEGATIVE CONTROL. A warning that is always on carries no information.
    mockFiscal.mockReturnValue({
      data: { debt_anchor: { anchor_pct_gdp: 55, debt_to_gdp_pct: 41.2, above_anchor: false } },
    });
    mockOverview.mockReturnValue({
      data: {
        total_outstanding: 5_000_000_000_000,
        debt_to_gdp_ratio: 41.2,
        debt_sustainability: { risk_level: 'Low', assessment: 'Comfortable.' },
      },
    });
    const { container } = render(<SummaryStrip />);
    expect(screen.queryByText(/above the .* anchor/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/debt distress/i)).not.toBeInTheDocument();
    Array.from(container.querySelectorAll('[data-figure]')).forEach((f) =>
      expect(f.className).not.toMatch(/text-gov-copper/)
    );
  });

  it('does not raise the anchor alarm on a zero from a failed request', () => {
    // The outage shape: HTTP 200 with a 0 ratio. Neither alarm nor
    // reassurance — the strip already says "Not assessed".
    mockFiscal.mockReturnValue(ANCHOR_BREACHED);
    mockOverview.mockReturnValue({
      data: { total_outstanding: 0, debt_to_gdp_ratio: 0, debt_sustainability: null },
    });
    render(<SummaryStrip />);
    expect(screen.queryByText(/above the .* anchor/i)).not.toBeInTheDocument();
    expect(screen.getByText(/not assessed/i)).toBeInTheDocument();
  });
});
