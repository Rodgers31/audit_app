import React from 'react';
import { render, screen } from '@testing-library/react';
import CountyDetailClient from '@/app/counties/[id]/CountyDetailClient';
import CountyDetailLoading from '@/app/counties/[id]/loading';
import { LangProvider } from '@/lib/i18n/LangProvider';
import MERU from './fixtures/meru-comprehensive.json';

let mockLoading = true;
let mockCounty = MERU;
jest.mock('next/navigation', () => ({
  useParams: () => ({ id: '012' }),
  usePathname: () => '/counties/012',
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ back: jest.fn() }),
}));
jest.mock('@/lib/react-query/useCounties', () => ({
  useCountyComprehensive: () => ({ data: mockLoading ? undefined : mockCounty, isLoading: mockLoading }),
  useCountyFiscalYears: () => ({ data: undefined }),
  useCountyAccountability: () => ({ data: undefined }),
}));
jest.mock('next/dynamic', () => () => function Tab() { return <div>Tab body</div>; });
jest.mock('@/components/WatchButton', () => () => <button>Watch</button>);
jest.mock('@/components/PDFExportButton', () => () => <button>Export PDF</button>);

beforeEach(() => { mockLoading = true; mockCounty = JSON.parse(JSON.stringify(MERU)); });

it.each(['stream', 'client'])('%s loading keeps the same title predecessors as the loaded hero', (path) => {
  const pending = render(<LangProvider>{path === 'stream' ? <CountyDetailLoading /> : <CountyDetailClient />}</LangProvider>);
  const title = screen.getByRole('heading', { level: 1 });
  // Both loading entry points previously omit the back-link row AND eyebrow,
  // moving the title by 96.5px on the observed desktop navigation.
  const pendingHeader = title.closest('header')!;
  expect(pendingHeader.previousElementSibling).toHaveClass('backLinks');
  expect(title.previousElementSibling).toHaveTextContent('County Government');
  expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
  expect(pendingHeader.querySelectorAll('.detailMetrics > div')).toHaveLength(5);
  pending.unmount();
  mockLoading = false;
  render(<LangProvider><CountyDetailClient /></LangProvider>);
  const loadedTitle = screen.getByRole('heading', { level: 1 });
  expect(loadedTitle.closest('header')!.previousElementSibling).toHaveClass('backLinks');
  expect(loadedTitle.previousElementSibling).toHaveTextContent('County Government');
});

it('keeps the loading placeholders out of the accessible grade and financial record', () => {
  render(<LangProvider><CountyDetailLoading /></LangProvider>);
  expect(screen.queryByText(/KES|FY20/)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /grade:|score.*out of/ })).not.toBeInTheDocument();
});

it('retains an empty hidden year row when no fiscal period is sourced', () => {
  mockLoading = false;
  mockCounty = { ...mockCounty, budget: { ...mockCounty.budget, fiscal_year: null } } as typeof MERU;
  render(<LangProvider><CountyDetailClient /></LangProvider>);
  const row = screen.getByRole('heading', { level: 1 }).closest('header')!.querySelector('.detailYear');
  expect(row).not.toBeNull();
  expect(row).toBeEmptyDOMElement();
  expect(row).toHaveAttribute('aria-hidden', 'true');
  expect(screen.queryByText(/Financial data from/)).not.toBeInTheDocument();
});
