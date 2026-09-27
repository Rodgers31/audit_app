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
 *
 * Issue #269. The risk rating and the "· IMF" chip used to come from
 * `risk_level` / `assessment`, which the backend derived from debt-to-GDP > 65
 * with a sentence attributing the result to the IMF. When those were missing,
 * the tile fell back to `classifyDebtRisk`, an uncited 40/60 banding. The
 * strip now shows a rating only when it is the joint Bank-Fund DSA's
 * (`debt_sustainability.imf_dsa`), with its date and a link to the page it is
 * printed on.
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

/**
 * `/api/v1/debt/national` → `data.debt_sustainability.imf_dsa`, as
 * `backend/services/imf_dsa.py` declares it (IMF Country Report No. 24/316,
 * PDF p. 132).
 */
const IMF_DSA = {
  framework: 'Joint World Bank-IMF Debt Sustainability Framework for Low-Income Countries',
  risk_of_external_debt_distress: 'High',
  overall_risk_of_debt_distress: 'High',
  granularity_in_the_risk_rating: 'Sustainable',
  application_of_judgment: 'No',
  source: {
    publisher: 'International Monetary Fund and International Development Association (World Bank)',
    title: 'Kenya: Seventh and Eighth Reviews Under the Extended Fund Facility and Extended Credit Facility Arrangements — Debt Sustainability Analysis',
    series: 'IMF Country Report No. 24/316',
    url: 'https://www.imf.org/-/media/files/publications/cr/2024/english/1kenea2024003-print-pdf.pdf',
    dsa_date: '2024-10-18',
    published: '2024-11-01',
    page: 132,
    page_label: 'PDF p. 132 (first page of the Debt Sustainability Analysis)',
  },
  latest_confirmed: {
    title: 'List of LIC DSAs for PRGT-Eligible Countries — As of March 31, 2026',
    url: 'https://www.imf.org/external/pubs/ft/dsa/dsalist.pdf',
    as_of: '2026-03-31',
    row: 27,
  },
};

describe('G3 — a blank risk badge is not an assessment', () => {
  it('says "not assessed" when no band can be established', () => {
    mockTimeline.mockReturnValue({
      data: { timeline: [{ ...RAW_KES_ROW, gdp_ratio: 0 }] },
    });
    render(<SummaryStrip />);
    expect(screen.getByText(/not assessed/i)).toBeInTheDocument();
  });

  it('renders the rating the IMF publishes', () => {
    mockTimeline.mockReturnValue({ data: { timeline: [RAW_KES_ROW] } });
    mockOverview.mockReturnValue({
      data: { debt_to_gdp_ratio: 69.3, debt_sustainability: { imf_dsa: IMF_DSA } },
    });
    render(<SummaryStrip />);
    // Match the risk VALUE node exactly. The cell also renders a legend
    // beneath it, so a loose /High/ matches twice.
    expect(screen.getByText(/^High Risk$/i)).toBeInTheDocument();
  });
});

describe('#269 — the risk rating is the IMF\u2019s, or it is absent', () => {
  it('does not band debt-to-GDP itself', () => {
    // RED before the fix: 65.9% fell through `classifyDebtRisk` into the
    // uncited 40/60 banding and rendered "High Risk".
    mockTimeline.mockReturnValue({ data: { timeline: [RAW_KES_ROW] } });
    render(<SummaryStrip />);
    expect(screen.queryByText(/^High Risk$/i)).toBeNull();
    expect(screen.getByText(/not assessed/i)).toBeInTheDocument();
  });

  it('does not credit the IMF with the old ratio-derived rating', () => {
    // RED before the fix: this is the payload production served on
    // 2026-09-26. `risk_level` was "High" because 69.3 > 65, and the chip
    // read "High risk of debt distress · IMF".
    mockOverview.mockReturnValue({
      data: {
        debt_to_gdp_ratio: 69.3,
        debt_sustainability: {
          risk_level: 'High',
          debt_to_gdp: 69.3,
          assessment: 'Kenya\u2019s debt remains elevated. The IMF classifies Kenya at high risk of debt distress.',
        },
      },
    });
    render(<SummaryStrip />);
    expect(screen.queryByText(/debt distress/i)).toBeNull();
    expect(screen.queryByText(/\bIMF\b/)).toBeNull();
    expect(screen.getByText(/not assessed/i)).toBeInTheDocument();
  });

  it('withholds a rating that arrives without its citation', () => {
    // A rating with no page and no date could come from anywhere.
    mockOverview.mockReturnValue({
      data: {
        debt_to_gdp_ratio: 69.3,
        debt_sustainability: {
          imf_dsa: { ...IMF_DSA, source: { ...IMF_DSA.source, url: undefined, page: undefined } },
        },
      },
    });
    render(<SummaryStrip />);
    expect(screen.queryByText(/debt distress/i)).toBeNull();
    expect(screen.getByText(/not assessed/i)).toBeInTheDocument();
  });

  it('quotes the rating and links to the page it is printed on', () => {
    mockOverview.mockReturnValue({
      data: { debt_to_gdp_ratio: 69.3, debt_sustainability: { imf_dsa: IMF_DSA } },
    });
    render(<SummaryStrip />);
    expect(screen.getByText(/Overall risk of debt distress: High/)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /IMF\u2013World Bank DSA, Oct 2024/ });
    // #page=132 opens the PDF at the DSA's first page.
    expect(link).toHaveAttribute('href', `${IMF_DSA.source.url}#page=132`);
    expect(link.getAttribute('title')).toMatch(/Country Report No\. 24\/316.*p\. 132/);
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
    debt_sustainability: { debt_to_gdp: 69.3, imf_dsa: IMF_DSA },
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
    expect(screen.getByText(/Overall risk of debt distress: High/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /IMF\u2013World Bank DSA, Oct 2024/ })).toBeInTheDocument();
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
        debt_sustainability: {
          imf_dsa: { ...IMF_DSA, overall_risk_of_debt_distress: 'Low', risk_of_external_debt_distress: 'Low' },
        },
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
