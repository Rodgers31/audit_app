/** Preserve county-detail data and navigation while its presentation changes. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import React from 'react';
import CountyDetailClient from '@/app/counties/[id]/CountyDetailClient';
import { LangProvider } from '@/lib/i18n/LangProvider';
import type { CountyComprehensive } from '@/types';
import MERU from './fixtures/meru-comprehensive.json';

let mockData: CountyComprehensive;
let mockSearch = new URLSearchParams();
const mockReplace = jest.fn((url: string, _options?: { scroll: boolean }) => {
  mockSearch = new URL(url, 'http://localhost').searchParams;
});
const mockComprehensive = jest.fn();
let mockAccountability: {
  accountability_grade: string | null;
  accountability_score: number | null;
};

jest.mock('next/navigation', () => ({
  useParams: () => ({ id: '012' }),
  usePathname: () => '/counties/012',
  useSearchParams: () => mockSearch,
  useRouter: () => ({ replace: mockReplace, back: jest.fn() }),
}));
jest.mock('@/lib/react-query/useCounties', () => ({
  useCountyComprehensive: (id: string, year: string | undefined) => {
    mockComprehensive(id, year);
    return { data: mockData, isLoading: false, error: null };
  },
  useCountyFiscalYears: () => ({
    data: {
      years: [{ label: 'FY2025/26 9M', source: 'cob_cbirr', counties: 47 }],
      default: 'FY2025/26 9M',
    },
  }),
  useCountyAccountability: () => ({ data: mockAccountability }),
}));
// The contract under test is the detail shell; each lazy tab has separate
// coverage and is exercised against the real running app as well.
jest.mock(
  'next/dynamic',
  () => () =>
    function MockLazyTab() {
      return <div>Lazy tab content</div>;
    }
);
jest.mock(
  '@/components/WatchButton',
  () =>
    function MockWatchButton() {
      return <button>Watch</button>;
    }
);
jest.mock(
  '@/components/PDFExportButton',
  () =>
    function MockPdfExport() {
      return <button>Export PDF</button>;
    }
);

function renderPage() {
  return render(
    <LangProvider>
      <CountyDetailClient />
    </LangProvider>
  );
}
function metric(label: string) {
  return screen.getByText(label, { selector: 'p' }).parentElement as HTMLElement;
}

beforeEach(() => {
  mockData = JSON.parse(JSON.stringify(MERU)) as CountyComprehensive;
  mockSearch = new URLSearchParams('fy=FY2025%2F26%209M&from=transparency');
  mockAccountability = { accountability_grade: 'B', accountability_score: 71.2 };
  mockReplace.mockClear();
  mockComprehensive.mockClear();
  Element.prototype.scrollIntoView = jest.fn();
});

it('retains all five headline figures, period, population, and governor', () => {
  renderPage();
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Meru County');
  expect(metric('Budget')).toHaveTextContent('KES 16.02B');
  expect(metric('Execution')).toHaveTextContent('68.4%');
  expect(metric('Total Debt')).toHaveTextContent('—');
  expect(metric('Pending Bills')).toHaveTextContent('KES 1.74B');
  expect(metric('Audit Issues')).toHaveTextContent('31');
  expect(screen.getByText(/1.55M residents/)).toHaveTextContent('Isaac Mutuma');
  expect(screen.getByText(/Financial data from/)).toHaveTextContent('FY2024/25');
  expect(mockComprehensive).toHaveBeenCalledWith('012', 'FY2025/26 9M');
});

it('preserves published zeroes and withholds absent figures and grades', () => {
  mockData.budget.total_allocated = 0;
  mockData.budget.utilization_rate = 0;
  mockData.debt.pending_bills = 0;
  mockData.demographics.population = null;
  mockData.audit = { ...mockData.audit, status: 'pending', findings_count: 0, findings: [] };
  mockAccountability = { accountability_grade: null, accountability_score: null };
  renderPage();
  expect(metric('Budget')).toHaveTextContent('KES 0');
  expect(metric('Execution')).toHaveTextContent('0.0%');
  expect(metric('Pending Bills')).toHaveTextContent('KES 0');
  expect(metric('Total Debt')).toHaveTextContent('—');
  expect(metric('Audit Issues')).toHaveTextContent('—');
  expect(screen.queryByText(/residents/)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /AUDIT: not yet assessed/ })).toHaveTextContent(
    'Not assessed'
  );
});

it('keeps a sourced zero audit findings count visible', () => {
  mockData.audit = { ...mockData.audit, status: 'clean', findings_count: 0, findings: [] };
  renderPage();
  expect(metric('Audit Issues')).toHaveTextContent('0');
});

it('opens all five tabs, preserving fy and origin in the URL', () => {
  renderPage();
  const cases: [string, string | null][] = [
    ['Follow the Money', 'money'],
    ['Budget & Debt', 'budget'],
    ['Audit Findings', 'audit'],
    ['Accountability', 'accountability'],
    ['Overview', null],
  ];
  for (const [label, tab] of cases) {
    const button = screen.getByRole('button', { name: label });
    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-pressed', 'true');
    const [url, options] = mockReplace.mock.calls.at(-1)!;
    const query = new URL(url, 'http://localhost').searchParams;
    expect(query.get('tab')).toBe(tab);
    expect(query.get('fy')).toBe('FY2025/26 9M');
    expect(query.get('from')).toBe('transparency');
    expect(options).toEqual({ scroll: false });
  }
});

it('restores a valid tab on first render and lets the audit grade update the URL', () => {
  mockSearch.set('tab', 'budget');
  renderPage();
  expect(screen.getByRole('button', { name: 'Budget & Debt' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  fireEvent.click(screen.getByRole('button', { name: /AUDIT grade/ }));
  expect(screen.getByRole('button', { name: 'Accountability' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  expect(mockSearch.get('tab')).toBe('accountability');
  expect(mockSearch.get('fy')).toBe('FY2025/26 9M');
  expect(mockSearch.get('from')).toBe('transparency');
});

it('falls back from unsupported tabs and stale fiscal years', () => {
  mockSearch = new URLSearchParams('fy=FY1900/01&tab=projects&from=home-map');
  renderPage();
  expect(screen.getByRole('button', { name: 'Overview' })).toHaveAttribute('aria-pressed', 'true');
  expect(mockComprehensive).toHaveBeenCalledWith('012', undefined);
  expect(screen.getByRole('link', { name: /Back to map/ })).toHaveAttribute('href', '/#home-map');
  expect(screen.getByRole('link', { name: 'All Counties' })).toHaveAttribute('href', '/counties');
});

it('retains health-methodology values and closes on Escape', async () => {
  renderPage();
  fireEvent.click(screen.getByRole('button', { name: /HEALTH grade/ }));
  const title = screen.getByRole('heading', { name: 'Financial Health Score' });
  const modal = title.parentElement!.parentElement!.parentElement!;
  await waitFor(() => expect(within(modal).getByText('68.4%')).toBeVisible());
  expect(within(modal).getByText('KES 16.02B')).toBeVisible();
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(screen.queryByRole('heading', { name: 'Financial Health Score' })).not.toBeInTheDocument();
});

it('withholds an unavailable budget execution and health grade', () => {
  Object.assign(mockData.budget, { total_allocated: null, utilization_rate: null });
  Object.assign(mockData.financial_summary, { grade: null, health_score: null });
  renderPage();
  expect(metric('Budget')).toHaveTextContent('—');
  expect(metric('Execution')).toHaveTextContent('—');
  expect(screen.getByRole('button', { name: /HEALTH: not yet assessed/ })).toHaveTextContent(
    'Not assessed'
  );
});

it('opens methodology with an unassessed health score and unavailable execution', async () => {
  Object.assign(mockData.financial_summary, { grade: null, health_score: null });
  Object.assign(mockData.budget, { utilization_rate: null });
  renderPage();
  fireEvent.click(screen.getByRole('button', { name: /HEALTH: not yet assessed/ }));
  const title = screen.getByRole('heading', { name: 'Financial Health Score' });
  const modal = title.parentElement!.parentElement!.parentElement!;
  await waitFor(() => expect(within(modal).getByText('Not assessed')).toBeVisible());
  expect(within(modal).queryByText('0.0%')).not.toBeInTheDocument();
  expect(modal.textContent).not.toMatch(/NaN|null|undefined/);
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(screen.queryByRole('heading', { name: 'Financial Health Score' })).not.toBeInTheDocument();
});

it('retains a published zero health score as assessed', () => {
  Object.assign(mockData.financial_summary, { grade: 'C', health_score: 0 });
  renderPage();
  expect(
    screen.getByRole('button', { name: 'HEALTH grade: C, score 0 out of 100' })
  ).toHaveTextContent('0');
  expect(
    screen.queryByRole('button', { name: /HEALTH: not yet assessed/ })
  ).not.toBeInTheDocument();
});
