/** Actual isolated-PG HTTP payloads; candidate rendering, never adoption. */
import '@testing-library/jest-dom';
import { fireEvent, render, screen, within } from '@testing-library/react';
import mockPacket from '@/test/fixtures/deploymentFiscalFiveYears20261105.json';
import { frameworkOf, frameworkSources, frameworkUses } from '@/lib/fiscal/framework';

let mockFiscal: any = mockPacket.fiscal;
let mockOverview: any = mockPacket.overview;
jest.mock('@/lib/react-query', () => ({
  useBudgetOverview: () => ({ data: mockOverview, isLoading: false, isError: false }),
  useBudgetEnhanced: () => ({ data: mockPacket.enhanced }),
}));
jest.mock('@/lib/react-query/useFiscal', () => ({
  useFiscalSummary: () => ({ data: mockFiscal, isLoading: false, isError: false }),
}));
// No APDR HTTP payload was captured by this fiscal export. Its independent
// reconciliation panel keeps the ordinary absent state instead of fetching.
jest.mock('@/lib/react-query/useDebt', () => ({
  useAnnualDebtReports: () => ({ data: undefined, isLoading: false }),
}));
jest.mock('framer-motion', () => {
  const React = jest.requireActual('react');
  const components = new Map();
  return { motion: new Proxy({}, { get: (_target, tag) => {
    if (!components.has(tag)) components.set(tag,
      ({ children, initial: _i, animate: _a, whileInView: _w, viewport: _v,
         transition: _t, exit: _e, ...props }: any) => React.createElement(tag, props, children));
    return components.get(tag);
  },
  }), AnimatePresence: ({ children }: any) => <>{children}</>, useInView: () => true };
});
jest.mock('recharts', () => {
  const Pass = ({ children }: any) => <div>{children}</div>;
  return { ResponsiveContainer: Pass, PieChart: Pass, Pie: Pass, Cell: () => null,
    Sector: () => null, AreaChart: Pass, Area: () => null, LineChart: Pass, Line: () => null,
    Tooltip: () => null, XAxis: () => null, YAxis: () => null, CartesianGrid: () => null };
});
jest.mock('@/components/layout/PageShell', () => ({ __esModule: true,
  default: ({ children }: any) => <main>{children}</main> }));
jest.mock('@/components/DataFreshnessBadge', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/PDFExportButton', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/budget/CountyUtilizationStrip', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/budget/EconomicContextStrip', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/budget/ExecutionAuditLens', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/budget/RevenueMix', () => ({ __esModule: true, default: () => null }));

import BudgetPage from '@/app/budget/BudgetPageClient';

const expected = [
  { year: 'FY 2022/23', vintage: 'Approved', expenditure: 3342.8, recurrent: 2255,
    development: 676.7, counties: 407, financing: 862.5, display: '3.34T',
    ordinary: 2041.119, frameworkOrdinary: 2141.6, debtServiceRatio: 58.8 },
  { year: 'FY 2023/24', vintage: 'Actual', expenditure: 3605.2, recurrent: 2678.4,
    development: 546.4, counties: 380.4, financing: 818.3, display: '3.61T',
    ordinary: 2288.9, frameworkOrdinary: 2288.9, debtServiceRatio: null },
  { year: 'FY 2024/25', vintage: 'Preliminary', expenditure: 3975.9, recurrent: 2948.4,
    development: 582.9, counties: 444.6, financing: 1034.2, display: '3.98T',
    ordinary: 2420.2, frameworkOrdinary: 2420.2, debtServiceRatio: null },
  { year: 'FY 2025/26', vintage: 'Supplementary I', expenditure: 4638.4, recurrent: 3393.2,
    development: 758.4, counties: 484.8, financing: 1199.4, display: '4.64T',
    ordinary: 2784.4, frameworkOrdinary: 2784.4, debtServiceRatio: null },
  { year: 'FY 2026/27', vintage: 'Approved', expenditure: 4785.2, recurrent: 3538.7,
    development: 749, counties: 495.5, financing: 1111.8, display: '4.79T',
    ordinary: 2985.7, frameworkOrdinary: 2985.7, debtServiceRatio: null },
] as const;

beforeAll(() => {
  globalThis.IntersectionObserver = class {
    observe() {} unobserve() {} disconnect() {} takeRecords() { return []; }
  } as unknown as typeof IntersectionObserver;
});
beforeEach(() => { mockFiscal = mockPacket.fiscal; mockOverview = mockPacket.overview; });

test.each(expected)('real budget picker renders $year with its own source column and quantities', e => {
  const row: any = mockPacket.fiscal.history.find(r => r.fiscal_year === e.year);
  const ff = frameworkOf(row);
  expect(ff).not.toBeNull();
  expect(ff!.total_expenditure_billion).toBe(e.expenditure);
  expect(ff!.recurrent_billion).toBe(e.recurrent);
  expect(ff!.development_billion).toBe(e.development);
  expect(ff!.county_transfers_billion).toBe(e.counties);
  expect(frameworkUses(ff)!.total).toBe(e.expenditure);
  expect(frameworkSources(ff)!.borrowing).toBe(e.financing);
  expect(frameworkSources(ff)!.ordinaryRevenue).toBe(e.frameworkOrdinary);
  expect(row.total_revenue).toBe(e.ordinary * 1e9);
  expect(row.debt_service_per_shilling).toBe(e.debtServiceRatio);
  expect(row.appropriated_budget).toBeNull();
  const budget = mockPacket.overview.fiscal_history.find(r => r.fiscal_year === e.year)!;
  expect(budget.total_revenue).toBe(e.ordinary);
  expect(mockPacket.outturns.series.find(r => r.period === e.year)!.expenditure).toBe(e.expenditure);

  render(<BudgetPage />);
  const button = screen.getByRole('button', { name: new RegExp(`FY${e.year.slice(3)}`) });
  expect(button).toBeEnabled();
  fireEvent.click(button);
  expect(button).toHaveAttribute('aria-pressed', 'true');
  const heading = screen.getByRole('heading', { name: `Approved budget for ${e.year} withheld` });
  const hero = heading.closest('section')!;
  expect(hero).toHaveTextContent(`Fiscal framework: ${e.vintage}`);
  expect(hero).toHaveTextContent(e.display);
  expect(within(hero).getByText('Where the money comes from')).toBeInTheDocument();
  expect(within(hero).getByText('Where it actually goes')).toBeInTheDocument();
  expect(hero).toHaveTextContent(ff!.source!.edition!);
  expect(hero).toHaveTextContent(String(ff!.source!.page));
  if (e.year === 'FY 2022/23') {
    expect(hero).toHaveTextContent('KES 58.8');
    expect(hero).toHaveTextContent('Separate BROP preliminary observation');
    expect(hero.querySelector('a[href*="Annual-Public-Debt-Report-2022-2023"]')).not.toBeNull();
    expect(row.tax_revenue).toBeNull();
    expect(row.non_tax_revenue).toBeNull();
    expect(frameworkSources(ff)!.tax).toBeNull();
  } else {
    expect(within(hero).queryByText(/^KES \d+(?:\.\d+)?$/)).not.toBeInTheDocument();
  }
});

test('the conservative public-only mirror withdraws five unproven years without inventing zero or publication dates', () => {
  mockFiscal = mockPacket.code_only_fiscal;
  mockOverview = mockPacket.code_only_overview;
  expect(mockFiscal.history).toHaveLength(0);
  expect(mockOverview.fiscal_history_withheld).toHaveLength(5);
  render(<BudgetPage />);
  expect(screen.queryByRole('button', { name: /FY2022\/23/ })).not.toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Approved budget for FY 2026/27 withheld' })).toBeInTheDocument();
  expect(screen.getByText(/How FY 2026\/27 breaks down is withheld/)).toBeInTheDocument();
  expect(screen.queryByText('Where the money comes from')).not.toBeInTheDocument();
  expect(screen.queryByText('KES 0 approved for FY 2026/27')).not.toBeInTheDocument();
});
