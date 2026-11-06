/** Independent client-reader probes. Synthetic contracts, not source authority. */
import '@testing-library/jest-dom';
import { render } from '@testing-library/react';

const mockTimeline = jest.fn();
const mockOverview = jest.fn();
const mockFiscal = jest.fn();
jest.mock('@/lib/react-query/useDebt', () => ({
  useDebtTimeline: () => mockTimeline(),
  useNationalDebtOverview: () => mockOverview(),
}));
jest.mock('@/lib/react-query/useFiscal', () => ({ useFiscalSummary: () => mockFiscal() }));
jest.mock('framer-motion', () => ({
  motion: new Proxy({}, { get: () => ({ children, ...p }: any) => <div {...p}>{children}</div> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
  useReducedMotion: () => true,
}));
jest.mock('@/components/dashboard/DebtExplainerModal', () => ({ __esModule: true, default: () => <span /> }));
jest.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  ComposedChart: ({ children }: any) => <div>{children}</div>,
  Area: () => null, Line: () => null, CartesianGrid: () => null,
  Tooltip: () => null, XAxis: () => null, YAxis: () => null,
}));

import { publishedHeadlineRatio, publishedTimelineRatio } from '@/lib/debt/qualification';
import { frameworkOf, qualifiedFrameworkValue } from '@/lib/fiscal/framework';
import { SummaryStrip } from '@/components/dashboard/HeroSection';
import NationalDebtCard from '@/components/dashboard/NationalDebtCard';
import BudgetFlowHero from '@/components/budget/BudgetFlowHero';
import { FF_2026_27, FY_2026_27_BILLIONS } from '@/test/fixtures/fiscalFramework';

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value));
function timeline() {
  const identity = (measure: string, basis: string, unit = 'KES') => ({
    measure, entity_id: null, geography: 'KEN', period: '2025', unit, basis, dimensions: {},
  });
  const base = { status: 'verified', reason: 'retained_source_and_observation_matched',
    value_checked: true, document_bytes_checked: true, source_document_id: 1, receipt_id: 1, digest: 'a'.repeat(64) };
  return { year: 2025, unit: 'KES', external: 40, domestic: 60, total: 100, gdp: 200, gdp_ratio: 50,
    qualifications: {
      total: { ...base, source_kind: 'pdf', identity: identity('total', 'actual'),
        source_url: 'https://www.centralbank.go.ke/inert.pdf', locator: { page: 56, table: '4.1.3', cell: '2025-12 / total' } },
      gdp: { ...base, source_kind: 'api', identity: identity('gdp', 'current_prices'),
        source_url: 'https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN',
        locator: { json_path: '$[1][0].value', indicator: 'NY.GDP.MKTP.CN', country: 'KEN', date: '2025' } },
      gdp_ratio: { status: 'verified', reason: 'independently_matched_ratio_operands', value_checked: true,
        document_bytes_checked: true, source_document_id: 1, identity: identity('gdp_ratio', 'derived', 'percent') },
    },
    period: { stock_as_of_month: '2025-12', gdp_calendar_year: 2025, year_end_stock: true, vintage_date: null, publication_date: null },
  };
}
function cbkHeadline() {
  const observed = timeline();
  return { debt_to_gdp_ratio: 50, debt_to_gdp_year: 2025, debt_to_gdp_source: 'CBK / World Bank',
    debt_to_gdp_basis: 'Central government debt (CBK) / nominal GDP (World Bank, 2025); stock as of 2025-12',
    figure_qualifications: { derived_ratio: clone(observed.qualifications.gdp_ratio) }, debt_to_gdp_observation: observed };
}
function imfHeadline() {
  return { debt_to_gdp_ratio: 69.3, debt_to_gdp_year: 2025, debt_to_gdp_source: 'IMF World Economic Outlook',
    debt_to_gdp_basis: 'IMF General Government Gross Debt, % of GDP (GGXWDG_NGDP) — vintage-consistent',
    figure_qualifications: { derived_ratio: { status: 'qualified', reason: 'published_imf_ratio_outside_seven_table_contract' } },
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockTimeline.mockReturnValue({ data: undefined });
  mockOverview.mockReturnValue({ data: undefined });
  mockFiscal.mockReturnValue({ data: undefined });
});

test('independently checked CBK pair and exact IMF contract keep their separate values', () => {
  expect(publishedTimelineRatio(timeline())).toBe(50);
  expect(publishedHeadlineRatio(cbkHeadline())).toBe(50);
  expect(publishedHeadlineRatio(imfHeadline())).toBe(69.3);
});

test.each(['imf-source', 'imf-basis', 'unavailable-derived'] as const)(
  'a valid CBK observation cannot override a contradictory headline header: %s', bad => {
    const body: any = cbkHeadline();
    if (bad === 'imf-source') body.debt_to_gdp_source = 'IMF World Economic Outlook';
    if (bad === 'imf-basis') body.debt_to_gdp_basis = imfHeadline().debt_to_gdp_basis;
    if (bad === 'unavailable-derived') body.figure_qualifications.derived_ratio = { status: 'unavailable', reason: 'stock_denominator_pair_unqualified' };
    expect(publishedHeadlineRatio(body)).toBeNull();
  },
);

test('SummaryStrip cannot label a validated CBK value as IMF through conflicting header text', () => {
  const body: any = cbkHeadline();
  body.debt_to_gdp_source = 'IMF World Economic Outlook';
  body.debt_to_gdp_basis = imfHeadline().debt_to_gdp_basis;
  mockOverview.mockReturnValue({ data: { data: body } });
  const { container } = render(<SummaryStrip />);
  expect(container.textContent).not.toMatch(/50(?:\.0)?%/);
});

test('a valid IMF headline ignores an unrelated CBK observation in its displayed basis', () => {
  const body = { ...imfHeadline(), debt_to_gdp_observation: timeline() };
  expect(publishedHeadlineRatio(body)).toBe(69.3);
  mockOverview.mockReturnValue({ data: { data: body } });
  const { container } = render(<NationalDebtCard />);
  expect(container.textContent).toMatch(/69\.3%/);
  expect(container.textContent).not.toMatch(/CBK stock at 2025-12/);
});

test('an optional equitable share needs its own proof without suppressing a qualified flow', () => {
  const ff = clone(FF_2026_27);
  ff.county_equitable_share_billion = 421;
  delete ff.measure_qualifications?.county_equitable_share_billion;
  expect(qualifiedFrameworkValue(ff, 'county_equitable_share_billion')).toBeNull();
  const { container } = render(<BudgetFlowHero data={{ ...FY_2026_27_BILLIONS, fiscal_framework: ff }} />);
  expect(container.textContent).toMatch(/Where it actually goes/);
  expect(container.textContent).not.toMatch(/421B/);
});

test('explicit unknown vintage keeps witnessed cells while an omitted vintage does not', () => {
  const ff = clone(FF_2026_27);
  delete ff.source?.column;
  Object.values(ff.measure_qualifications ?? {}).forEach(q => { q.vintage = null; delete q.source.column; });
  expect(frameworkOf({ fiscal_framework: ff })).toBe(ff);
  delete (ff.measure_qualifications!.total_expenditure_billion as any).vintage;
  expect(frameworkOf({ fiscal_framework: ff })).toBeNull();
});

test('preserves a verified Decimal half-up ratio at a binary floating-point boundary', () => {
  const row = { ...timeline(), total: 1001e8, gdp: 2000e8, gdp_ratio: 50.1 };
  expect(publishedTimelineRatio(row)).toBe(50.1);
});

test('a timeline comparison still discloses the latest stock month, annual GDP year and unknown vintage', () => {
  const current = timeline();
  const previous: any = clone(current);
  previous.year = 2024;
  previous.period.stock_as_of_month = '2024-06';
  previous.period.gdp_calendar_year = 2024;
  previous.period.year_end_stock = false;
  for (const q of Object.values(previous.qualifications) as any[]) q.identity.period = '2024';
  previous.qualifications.total.locator.cell = '2024-06 / total';
  previous.qualifications.gdp.locator.date = '2024';
  expect(publishedTimelineRatio(previous)).toBe(50);
  mockTimeline.mockReturnValue({ data: { timeline: [previous, current] } });
  const { container } = render(<NationalDebtCard />);
  expect(container.textContent).toMatch(/CBK stock at 2025-12/);
  expect(container.textContent).toMatch(/annual GDP 2025/);
  expect(container.textContent).toMatch(/source vintage unconfirmed/);
});
