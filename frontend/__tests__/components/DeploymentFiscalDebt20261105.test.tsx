import '@testing-library/jest-dom';
import { fireEvent, render } from '@testing-library/react';
import { frameworkOf, frameworkSources, frameworkUses } from '@/lib/fiscal/framework';
import { FF_2026_27, FY_2026_27_BILLIONS, withSyntheticFrameworkProofs } from '@/test/fixtures/fiscalFramework';

const mockTimeline = jest.fn();
const mockOverview = jest.fn(() => ({ data: undefined }));
jest.mock('@/lib/react-query/useDebt', () => ({
  useDebtTimeline: () => mockTimeline(), useNationalDebtOverview: () => mockOverview(),
}));
jest.mock('@/lib/react-query/useFiscal', () => ({ useFiscalSummary: () => ({ data: undefined }) }));
jest.mock('framer-motion', () => ({
  motion: new Proxy({}, { get: () => ({ children, initial, animate, whileInView, viewport, transition, ...p }: any) => <div {...p}>{children}</div> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
jest.mock('../../components/dashboard/DebtExplainerModal', () => ({ __esModule: true, default: () => <span /> }));

import { SummaryStrip } from '@/components/dashboard/HeroSection';
import BudgetFlowHero from '@/components/budget/BudgetFlowHero';

beforeEach(() => { mockTimeline.mockReturnValue({ data: undefined }); mockOverview.mockReturnValue({ data: undefined }); });

it('withholds a legacy nested framework that has only a document citation', () => {
  const legacy = { ...FF_2026_27, measure_qualifications: undefined };
  expect(frameworkOf({ fiscal_framework: legacy })).toBeNull();
  expect(frameworkUses(legacy)).toBeNull();
  expect(frameworkSources(legacy)).toBeNull();
  const { container } = render(<BudgetFlowHero data={{ ...FY_2026_27_BILLIONS, fiscal_framework: legacy }} />);
  expect(container.textContent).toMatch(/How FY 2026\/27 breaks down is withheld/);
  expect(container.textContent).not.toMatch(/Spending & net lending KES 4\.79T/);
});

it('does not render a stored timeline ratio without compatible operand qualification', () => {
  mockTimeline.mockReturnValue({ data: { timeline: [{ year: 2025, external: 400e9, domestic: 600e9,
    total: 1000e9, gdp: 2000e9, gdp_ratio: 50, unit: 'KES' }] } });
  const { container } = render(<SummaryStrip />);
  expect(container.textContent).not.toMatch(/50(?:\.0)?%/);
});

it('withholds an overview ratio that lacks an accepted observation or explicit IMF qualification', () => {
  mockOverview.mockReturnValue({ data: { debt_to_gdp_ratio: 50, debt_to_gdp_year: 2025, debt_to_gdp_source: 'computed register',
    figure_qualifications: { derived_ratio: { status: 'qualified', reason: 'aggregate_operands' } } } } as any);
  const { container } = render(<SummaryStrip />);
  expect(container.textContent).not.toMatch(/50(?:\.0)?%/);
});

it.each(['-1', 'unconfirmed1'])('requires an actual page locator rather than %s', (page) => {
  const ff = JSON.parse(JSON.stringify(FF_2026_27));
  ff.source.page = page;
  Object.values(ff.measure_qualifications).forEach((q: any) => { q.source.page = page; });
  expect(frameworkOf({ fiscal_framework: ff })).toBeNull();
});

it('refuses a matching negative interest cell and proof', () => {
  const ff = withSyntheticFrameworkProofs({ ...FF_2026_27, interest_payments_billion: -1 }, 'FY 2026/27', 'Approved');
  expect(frameworkUses(ff)).toBeNull();
});

it('uses the backend rounding bounds for independently witnessed expenditure and revenue parts', () => {
  const uses = withSyntheticFrameworkProofs({ ...FF_2026_27, development_billion: 749.4 }, 'FY 2026/27', 'Approved');
  expect(frameworkUses(uses)).toBeNull();
  const sources = withSyntheticFrameworkProofs({ ...FF_2026_27, ordinary_revenue_billion: 2986.1 }, 'FY 2026/27', 'Approved');
  expect(frameworkSources(sources)).toBeNull();
});

it.each(['unproved', 'exceeds transfers'])('withholds equitable share when %s in the rendered county tooltip', (mode) => {
  const ff = withSyntheticFrameworkProofs({ ...FF_2026_27, county_equitable_share_billion: mode === 'unproved' ? 420 : 700 }, 'FY 2026/27', 'Approved');
  if (mode === 'unproved') delete ff.measure_qualifications!.county_equitable_share_billion;
  const view = render(<BudgetFlowHero data={{ ...FY_2026_27_BILLIONS, fiscal_framework: ff }} />);
  fireEvent.mouseEnter(view.getByRole('button', { name: /Counties/ }));
  expect(view.container.textContent).not.toMatch(/equitable share \(KES (420|700)/);
  expect(view.container.textContent).toMatch(/Spending & net lending KES 4\.79T/);
});

it('preserves an explicitly unknown vintage but refuses a missing vintage witness', () => {
  const ff = JSON.parse(JSON.stringify(FF_2026_27));
  delete ff.source.column;
  Object.values(ff.measure_qualifications).forEach((q: any) => { q.vintage = null; delete q.source.column; });
  expect(frameworkOf({ fiscal_framework: ff })).toBe(ff);
  delete ff.measure_qualifications.total_expenditure_billion.vintage;
  expect(frameworkOf({ fiscal_framework: ff })).toBeNull();
});

it('refuses a core witness that adds digits below the printed one-decimal-billion quantum', () => {
  const ff = withSyntheticFrameworkProofs({ ...FF_2026_27, total_expenditure_billion: 4785.200001 }, 'FY 2026/27', 'Approved');
  expect(frameworkOf({ fiscal_framework: ff })).toBeNull();
});
