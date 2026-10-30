import { fireEvent, render, screen } from '@testing-library/react';
import BudgetTab from '@/app/counties/[id]/tabs/BudgetTab';
import type { CountyComprehensive } from '@/types';
import { LangProvider } from '@/lib/i18n/LangProvider';
let mockDate = '2026-06-30';
let mockResult: any;
const mockRead = jest.fn();
jest.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams({as_at: mockDate}) }));
jest.mock('@/lib/react-query/useDebt', () => ({ useCountyPendingBills: (...args: unknown[]) => { mockRead(...args); return mockResult; } }));
jest.mock('@/components/ModelledDataNote', () => ({ __esModule: true, default: () => null }));
const data = {id: 71, name: 'Nairobi', budget: {total_allocated: 100, total_spent: 50, utilization_rate: 50}, debt: {pending_bills: 999000000, total_debt: null, breakdown: []}} as unknown as CountyComprehensive;
beforeEach(() => {
  jest.clearAllMocks(); mockDate = '2026-06-30'; mockResult = {data: {total_pending: 86899380000, pending_bills_as_at: mockDate, pending_bills_source: {publisher: 'Controller of Budget', url: 'https://cob.go.ke/report'}, pending_bills_notes: [{code: 'assembly_not_printed', table: 'Table 2.10'}]}, isPending: false, refetch: jest.fn()};
  window.history.replaceState({}, '', '/counties/nairobi-county?tab=budget&as_at=2026-06-30#pending-bills');
});
afterEach(() => window.history.replaceState({}, '', '/'));
test('date-specific pending-bills states follow the selected public language', () => {
  localStorage.setItem('auditgava-lang', 'sw');
  mockResult = { data: undefined, isPending: true, refetch: jest.fn() };
  try {
    render(<LangProvider><BudgetTab data={data} /></LangProvider>);
    expect(screen.getByRole('status')).toHaveTextContent('Inapakia kipindi hiki cha ripoti');
    expect(screen.getByText(/Ankara zilizokwama zilizoripotiwa kufikia 2026-06-30/)).toBeInTheDocument();
  } finally { localStorage.removeItem('auditgava-lang'); }
});
test('the linked date is passed to the reader and lazy-mounted section receives the focus', () => {
  render(<BudgetTab data={data} />);
  expect(mockRead).toHaveBeenCalledWith('71', {enabled: true}, '2026-06-30');
  expect(screen.getByText(/Reported pending bills as at 2026-06-30/)).toBeInTheDocument();
  expect(document.activeElement).toHaveAttribute('id', 'pending-bills');
  expect(screen.getByRole('link', {name: 'Read the original report'})).toHaveAttribute('href', 'https://cob.go.ke/report');
  expect(screen.getByText(/County Executive only: the report prints no County Assembly figure/)).toBeInTheDocument();
});
test.each(['loading', 'absent', 'error', 'invalid'])('a %s historical link never substitutes the comprehensive latest amount', state => {
  mockResult = {data: undefined, isPending: state === 'loading', error: state === 'error' ? Error('offline') : undefined, refetch: jest.fn()};
  if (state === 'absent') mockResult.data = {total_pending: null};
  if (state === 'invalid') mockDate = '2026-02-30';
  render(<BudgetTab data={data} />);
  expect(screen.queryByText(/999/)).not.toBeInTheDocument();
  if (state === 'loading') expect(screen.getByRole('status')).toHaveTextContent('Loading this reporting period');
  if (state === 'absent') expect(screen.getByRole('status')).toHaveTextContent('No published pending-bills figure');
  if (state === 'invalid') { expect(screen.getByRole('alert')).toHaveTextContent('invalid reporting date'); expect(mockRead).toHaveBeenCalledWith('71', {enabled: false}, mockDate); }
  if (state === 'error') { fireEvent.click(screen.getByRole('button', {name: 'Try again'})); expect(mockResult.refetch).toHaveBeenCalled(); }
});
