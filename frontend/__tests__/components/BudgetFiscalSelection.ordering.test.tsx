import { act, fireEvent, render, screen, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom';

const originalObserver = Object.getOwnPropertyDescriptor(globalThis, 'IntersectionObserver');
beforeAll(() => {
  Object.defineProperty(globalThis, 'IntersectionObserver', {
    configurable: true,
    value: class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  });
});
afterAll(() => {
  if (originalObserver) Object.defineProperty(globalThis, 'IntersectionObserver', originalObserver);
  else Reflect.deleteProperty(globalThis, 'IntersectionObserver');
});

// Hold only this page's initialization effect. Real React state and the real
// hydrated picker run normally; releasing the old effect forces the otherwise
// timing-dependent default-after-selection ordering, without sleeps/retries.
let mockCapturingPage = false;
let mockDeferDefault = true;
let mockPendingDefaults: Array<() => void> = [];
jest.mock('react', () => {
  const actual = jest.requireActual('react');
  return {
    ...actual,
    useEffect: (effect: () => void, dependencies: unknown[]) => {
      if (mockCapturingPage && mockDeferDefault) {
        actual.useEffect(() => { mockPendingDefaults.push(effect); }, dependencies);
      } else {
        actual.useEffect(effect, dependencies);
      }
    },
  };
});

const mockOld = { fiscal_year: 'FY2024/25', appropriated_budget: 150e9, unit: 'KES' };
const mockNew = { fiscal_year: 'FY2025/26', appropriated_budget: 180e9, unit: 'KES' };
let mockFiscal = { current: mockNew, history: [mockOld, mockNew] };
jest.mock('@/lib/react-query', () => ({
  useBudgetOverview: () => ({ data: {}, isLoading: false, isError: false }),
  useBudgetEnhanced: () => ({ data: {} }),
}));
jest.mock('@/lib/react-query/useFiscal', () => ({
  useFiscalSummary: () => ({ data: mockFiscal, isLoading: false, isError: false }),
}));
jest.mock('@/components/layout/PageShell', () => ({
  __esModule: true, default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));
jest.mock('@/components/budget/BudgetFlowHero', () => ({
  __esModule: true,
  default: ({ data }: { data: { fiscal_year: string; appropriated_budget: number } }) =>
    <h2>{`KES ${data.appropriated_budget}B approved for ${data.fiscal_year}`}</h2>,
}));
jest.mock('@/components/DataFreshnessBadge', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/DataIntegrityBanner', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/PDFExportButton', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/budget/BudgetSourceReconciliation', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/budget/CountyUtilizationStrip', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/budget/EconomicContextStrip', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/budget/ExecutionAuditLens', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/budget/FiscalTrendStrip', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/budget/RevenueMix', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/budget/SpendDonut', () => ({ __esModule: true, default: () => null }));

import BudgetSpendingPage from '@/app/budget/BudgetPageClient';

function Subject() {
  // Calling the actual page here bounds the effect seam to this component;
  // children (including FiscalYearPicker) retain ordinary React effects.
  mockCapturingPage = true;
  try { return BudgetSpendingPage(); }
  finally { mockCapturingPage = false; }
}

beforeEach(() => {
  mockDeferDefault = true;
  mockPendingDefaults = [];
  mockFiscal = { current: mockNew, history: [mockOld, mockNew] };
});
afterEach(() => { cleanup(); mockCapturingPage = false; });

test('a late initial default cannot overwrite an already selected historical year', () => {
  render(<Subject />);
  expect(mockPendingDefaults).toHaveLength(1);
  const lateDefault = mockPendingDefaults[0];
  const historical = screen.getByRole('button', { name: 'FY2024/25' });
  expect(historical).toBeEnabled();
  fireEvent.click(historical);
  expect(historical).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('heading', { name: 'KES 150B approved for FY2024/25' })).toBeInTheDocument();

  act(() => { lateDefault(); });
  expect(historical).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('heading', { name: 'KES 150B approved for FY2024/25' })).toBeInTheDocument();
});

test('the late default still chooses the newest year when there was no user selection', () => {
  render(<Subject />);
  act(() => { mockPendingDefaults[0](); });
  expect(screen.getByRole('button', { name: /FY2025\/26/ })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('heading', { name: 'KES 180B approved for FY2025/26' })).toBeInTheDocument();
});

test('ordinary initialization and refreshed fiscal data preserve the explicit selection', () => {
  mockDeferDefault = false;
  const view = render(<Subject />);
  fireEvent.click(screen.getByRole('button', { name: 'FY2024/25' }));
  mockFiscal = { current: { ...mockNew }, history: [{ ...mockOld }, { ...mockNew }] };
  view.rerender(<Subject />);
  expect(screen.getByRole('button', { name: 'FY2024/25' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('heading', { name: 'KES 150B approved for FY2024/25' })).toBeInTheDocument();
});
