import '@testing-library/jest-dom';
import { render, screen, within } from '@testing-library/react';

/**
 * Units and risk-band regression fixtures for NationalDebtCard.
 *
 * PR #136 review, finding F1 — the merge blocker. The stage1 3a migration
 * rescales debt from billions to raw KES and declares it per row with
 * `unit: "KES"`. This component still assumed billions in three places:
 *
 *   toChartData()  external/domestic/total passed through with the comment
 *                  "already in billions from API" — the chart would receive
 *                  raw KES and plot 10⁹× too high.
 *   line 77-82     `lastYear.total * 1_000_000_000` on the fallback path,
 *                  multiplying an already-raw value into 10¹⁸.
 *
 * That is not hypothetical: the migration was applied to production on
 * 2026-08-30 and rolled back within the hour for exactly this reason.
 *
 * PR #135 review, finding G3 — `risk_level || 'High'` turns an ABSENT risk
 * assessment into the worst band. Absence renders as "not assessed", never
 * as a rating.
 *
 * Both directions are covered because the deploy happens BEFORE the
 * migration: the same build must read pre-migration billions (no `unit`) and
 * post-migration raw KES (`unit: "KES"`) and be right about both.
 */

const RAW_KES_TIMELINE = [
  {
    year: 2024,
    external: 5_100_000_000_000,
    domestic: 5_600_000_000_000,
    total: 10_700_000_000_000,
    gdp: 16_224_478_000_000,
    gdp_ratio: 65.9,
    unit: 'KES' as const,
  },
];

// The same figures as a pre-migration backend serves them: bare billions,
// no unit field.
const BILLIONS_TIMELINE = [
  {
    year: 2024,
    external: 5_100,
    domestic: 5_600,
    total: 10_700,
    gdp: 16_224.478,
    gdp_ratio: 65.9,
  },
];

/**
 * `data.debt_sustainability.imf_dsa` as `backend/services/imf_dsa.py`
 * declares it (IMF Country Report No. 24/316, PDF p. 132).
 */
const IMF_DSA = {
  risk_of_external_debt_distress: 'High',
  overall_risk_of_debt_distress: 'High',
  granularity_in_the_risk_rating: 'Sustainable',
  application_of_judgment: 'No',
  source: {
    series: 'IMF Country Report No. 24/316',
    url: 'https://www.imf.org/-/media/files/publications/cr/2024/english/1kenea2024003-print-pdf.pdf',
    dsa_date: '2024-10-18',
    published: '2024-11-01',
    page: 132,
    page_label: 'PDF p. 132 (first page of the Debt Sustainability Analysis)',
  },
  latest_confirmed: { as_of: '2026-03-31', row: 27 },
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
    {
      get: () => ({ children, ...props }: any) => <div {...props}>{children}</div>,
    }
  ),
  AnimatePresence: ({ children }: any) => <>{children}</>,
  useInView: () => true,
}));

import NationalDebtCard from '@/components/dashboard/NationalDebtCard';

beforeEach(() => {
  jest.clearAllMocks();
  mockFiscal.mockReturnValue({ data: undefined });
  mockOverview.mockReturnValue({ data: undefined, isLoading: false });
  mockTimeline.mockReturnValue({ data: undefined, isLoading: false });
  mockBroader.mockReturnValue({ data: undefined, isLoading: false });
});

describe('F1 — the timeline fallback must respect the declared unit', () => {
  it('does not multiply an already-raw KES value by 1e9', () => {
    // No authoritative /debt/national value, so the component falls back to
    // the last timeline year — the path that carried `* 1_000_000_000`.
    mockTimeline.mockReturnValue({
      data: { timeline: RAW_KES_TIMELINE },
      isLoading: false,
    });
    render(<NationalDebtCard />);

    // 10.7T rendered honestly. The pre-fix code produced 10.7e21 -> "KES 10700000000.00T".
    expect(screen.getAllByText('KES 10.70T').length).toBeGreaterThan(0);
    expect(screen.queryByText(/KES \d{7,}\.\d\dT/)).toBeNull();
  });

  it('still scales a pre-migration billions value', () => {
    // POSITIVE CONTROL. The deploy precedes the migration, so the same build
    // must read bare billions correctly. Without this, "stop multiplying"
    // would look like a fix while breaking every un-migrated environment.
    mockTimeline.mockReturnValue({
      data: { timeline: BILLIONS_TIMELINE },
      isLoading: false,
    });
    render(<NationalDebtCard />);
    expect(screen.getAllByText('KES 10.70T').length).toBeGreaterThan(0);
  });
});

describe('G3 — an absent risk assessment is not a risk band', () => {
  it('renders "not assessed" when neither a risk level nor a ratio exists', () => {
    // RED before the fix: `risk_level || 'High'` rendered the WORST band from
    // a missing field — "Risk: High" with the copper alarm styling.
    mockTimeline.mockReturnValue({
      data: { timeline: [{ ...RAW_KES_TIMELINE[0], gdp_ratio: 0 }] },
      isLoading: false,
    });
    mockOverview.mockReturnValue({
      data: { data: { debt_sustainability: {} } },
      isLoading: false,
    });
    render(<NationalDebtCard />);

    expect(screen.getByText(/not assessed/i)).toBeInTheDocument();
    expect(screen.queryByText(/Risk: High/)).toBeNull();
  });

  it('does not band debt-to-GDP itself when no rating is published', () => {
    // #269. RED before the fix: 65.9% went through `classifyDebtRisk`, an
    // uncited 40/60 banding, and rendered "Risk: High" under the caption
    // "IMF debt distress classification". The IMF does not rate countries by
    // nominal debt-to-GDP, and that banding cites no one.
    mockTimeline.mockReturnValue({
      data: { timeline: RAW_KES_TIMELINE },  // gdp_ratio 65.9
      isLoading: false,
    });
    mockOverview.mockReturnValue({
      data: { data: { debt_sustainability: {} } },
      isLoading: false,
    });
    render(<NationalDebtCard />);
    expect(screen.queryByText(/Risk: High/)).toBeNull();
    expect(screen.getByText(/not assessed/i)).toBeInTheDocument();
  });

  it('does not credit the IMF with the old ratio-derived rating', () => {
    // #269. RED before the fix: `risk_level: 'High'` was set by the backend
    // because debt-to-GDP > 65. The card captioned it "IMF debt distress
    // classification".
    mockTimeline.mockReturnValue({
      data: { timeline: RAW_KES_TIMELINE },
      isLoading: false,
    });
    mockOverview.mockReturnValue({
      data: { data: { debt_sustainability: { risk_level: 'High', debt_to_gdp: 69.3 } } },
      isLoading: false,
    });
    render(<NationalDebtCard />);
    expect(screen.queryByText(/Risk: High/)).toBeNull();
    // The card names the IMF elsewhere, correctly, as the basis of its GDP
    // ratio. What must not appear is a distress rating credited to anyone.
    expect(screen.queryByText(/debt distress|classification|\bDSA\b/i)).toBeNull();
  });

  it('renders the rating the IMF publishes, with its date', () => {
    // POSITIVE CONTROL — "never say High" is not the fix.
    mockTimeline.mockReturnValue({
      data: { timeline: RAW_KES_TIMELINE },
      isLoading: false,
    });
    mockOverview.mockReturnValue({
      data: { data: { debt_sustainability: { imf_dsa: IMF_DSA } } },
      isLoading: false,
    });
    render(<NationalDebtCard />);
    expect(screen.getByText(/Risk: High/)).toBeInTheDocument();
    expect(screen.getByText(/IMF\u2013World Bank DSA, Oct 2024/)).toBeInTheDocument();
  });
});


describe('F1 — the chart and yearly readout use the declared unit', () => {
  it.each([RAW_KES_TIMELINE, BILLIONS_TIMELINE])('shows the same admitted values on both payload shapes', row => {
    mockTimeline.mockReturnValue({ data: { timeline: [row] }, isLoading: false });
    const { container } = render(<NationalDebtCard />);
    const readout = within(container.querySelector<HTMLElement>('[data-home-debt-readout]')!);
    expect(readout.getByText('KES 10.70T')).toBeInTheDocument();
    expect(readout.getByText('KES 5.10T')).toBeInTheDocument();
    expect(readout.getByText('KES 5.60T')).toBeInTheDocument();
  });
});
