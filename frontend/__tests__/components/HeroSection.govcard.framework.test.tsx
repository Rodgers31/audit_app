import '@testing-library/jest-dom';
import { render } from '@testing-library/react';

/**
 * Issue #237. The homepage government card's "Where the Money Goes" bar
 * divided recurrent / development / counties by the COB gross budget and
 * subtracted interest-plus-principal from recurrent. It now draws one
 * fiscal-framework column against that column's own total.
 */

const mockFiscal = jest.fn();

jest.mock('@/lib/react-query/useDebt', () => ({
  useDebtTimeline: () => ({ data: undefined }),
  useNationalDebtOverview: () => ({ data: undefined }),
}));
jest.mock('@/lib/react-query/useFiscal', () => ({
  useFiscalSummary: () => mockFiscal(),
}));
jest.mock('framer-motion', () => ({
  motion: new Proxy(
    {},
    { get: () => ({ children, ...p }: any) => <div {...p}>{children}</div> },
  ),
  AnimatePresence: ({ children }: any) => <>{children}</>,
  useReducedMotion: () => true,
}));
jest.mock('../../components/dashboard/DebtExplainerModal', () => {
  const M = () => <span />;
  M.displayName = 'DebtExplainerModalStub';
  return { __esModule: true, default: M };
});

import { KenyanGovCard } from '@/components/dashboard/HeroSection';
import { FF_2026_27 } from '@/test/fixtures/fiscalFramework';

/** The FY 2026/27 row as the API serves it: raw KES columns + the object. */
const CURRENT = {
  fiscal_year: 'FY 2026/27',
  unit: 'KES',
  appropriated_budget: 5485.7e9,
  total_revenue: 2985.7e9,
  tax_revenue: 2858.7e9,
  non_tax_revenue: 127.1e9,
  total_borrowing: 1111.8e9,
  borrowing_pct_of_budget: 23.2,
  debt_service_cost: 2315.9e9,
  debt_service_per_shilling: 77.6,
  development_spending: 749.0e9,
  recurrent_spending: 3538.7e9,
  county_allocation: 495.5e9,
  split_basis: 'treasury_fiscal_framework',
  fiscal_framework: FF_2026_27,
};

const text = (el: HTMLElement) => el.textContent ?? '';

describe('KenyanGovCard — Where the Money Goes', () => {
  it('draws interest (not interest + principal) against the framework total', () => {
    mockFiscal.mockReturnValue({ data: { current: CURRENT, history: [CURRENT] } });
    const { container } = render(<KenyanGovCard />);
    const t = text(container);
    expect(t).toMatch(/Of KES 4\.79T spending/);
    // 1,254.2 / 4,785.2 = 26%; recurrent ex-interest 2,284.5 / 4,785.2 = 48%.
    expect(t).toMatch(/Interest on Debt26%/);
    expect(t).toMatch(/Recurrent48%/);
    expect(t).not.toMatch(/Other\d/);
  });

  it('names the borrowing share for what it divides by', () => {
    mockFiscal.mockReturnValue({ data: { current: CURRENT, history: [CURRENT] } });
    const { container } = render(<KenyanGovCard />);
    expect(text(container)).toMatch(/23\.2% of spending/);
  });

  it('withholds the bar for a row with no framework, even with every column filled', () => {
    const { fiscal_framework, split_basis, ...legacy } = CURRENT;
    mockFiscal.mockReturnValue({ data: { current: legacy, history: [legacy] } });
    const { container } = render(<KenyanGovCard />);
    expect(text(container)).not.toMatch(/Where the Money Goes/i);
  });
});
