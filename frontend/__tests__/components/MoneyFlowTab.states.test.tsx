import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MoneyFlowTab from '@/app/counties/[id]/tabs/MoneyFlowTab';
import { LangProvider } from '@/lib/i18n/LangProvider';
import { getCountyFiscalYears } from '@/lib/api/counties';
import { getCountyMoneyFlow } from '@/lib/api/moneyFlow';
import type { CountyFiscalYears } from '@/lib/utils';
import type { CountyComprehensive, MoneyFlowData } from '@/types';

jest.mock('@/lib/api/counties', () => ({ getCountyFiscalYears: jest.fn() }));
jest.mock('@/lib/api/moneyFlow', () => ({ getCountyMoneyFlow: jest.fn() }));
const readYears = jest.mocked(getCountyFiscalYears);
const readFlow = jest.mocked(getCountyMoneyFlow);
const years: CountyFiscalYears = {
  default: 'FY2025/26 9M',
  years: [
    { label: 'FY2025/26 9M', source: 'cob_cbirr', counties: 47 },
    { label: 'FY2024/25', source: 'cob_cbirr', counties: 47 },
  ],
};
const county = { id: '001', name: 'Nairobi County', budget: { fiscal_year: years.default } } as CountyComprehensive;
const flow: MoneyFlowData = {
  county_id: 1, county_name: 'Nairobi County', fiscal_year: years.default!,
  budget_source: 'cob_cbirr', total_waste_estimate: null, efficiency_score: 60,
  committed_amount: 1e9,
  stages: [
    { stage: 'Allocated', label: 'Budget Allocation', amount: 10e9 },
    { stage: 'Spent', label: 'Actual Expenditure', amount: 6e9 },
    { stage: 'Flagged', label: 'Auditor Flagged', amount: null, data_unavailable: true },
  ],
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
let client: QueryClient;
beforeEach(() => {
  jest.resetAllMocks(); localStorage.clear();
  client = new QueryClient({ defaultOptions: { queries: {
    retry: false, gcTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false,
  } } });
  readYears.mockResolvedValue(years); readFlow.mockResolvedValue(flow);
});
afterEach(() => client.clear());
function mount() {
  return render(<QueryClientProvider client={client}><LangProvider>
    <MoneyFlowTab data={county} />
  </LangProvider></QueryClientProvider>);
}

it('waits for fiscal-year discovery without claiming absence or starting a disabled read', async () => {
  const pending = deferred<CountyFiscalYears>(); readYears.mockReturnValue(pending.promise);
  mount();
  expect(screen.getByRole('status')).toHaveTextContent('Loading reporting periods');
  expect(screen.queryByText(/No money flow data/)).not.toBeInTheDocument();
  expect(readFlow).not.toHaveBeenCalled();
  await act(async () => pending.resolve(years));
  await waitFor(() => expect(screen.getByText('KES 10.00B')).toBeVisible());
  expect(readFlow).toHaveBeenCalledWith('001', years.default, expect.any(AbortSignal));
});

it('reports failed fiscal-year discovery and recovers only after explicit retry', async () => {
  readYears.mockRejectedValueOnce(new Error('Synthetic discovery failure'));
  mount();
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load reporting periods');
  expect(readFlow).not.toHaveBeenCalled();
  expect(screen.queryByText(/No money flow data/)).not.toBeInTheDocument();
  const pending = deferred<CountyFiscalYears>(); readYears.mockReturnValueOnce(pending.promise);
  const retry = screen.getByRole('button', { name: 'Try again' });
  fireEvent.click(retry);
  fireEvent.click(retry);
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument());
  expect(readYears).toHaveBeenCalledTimes(2);
  await act(async () => pending.resolve(years));
  await waitFor(() => expect(screen.getByText('KES 10.00B')).toBeVisible());
});

it('reports an unavailable reporting period when discovery succeeds with no selectable year', async () => {
  readYears.mockResolvedValue({ default: null, years: [] }); mount();
  expect(await screen.findByText('No reporting periods are available for money flow.')).toBeVisible();
  expect(readFlow).not.toHaveBeenCalled();
  expect(screen.queryByText(/No money flow data/)).not.toBeInTheDocument();
});

it('distinguishes a pending money-flow request from a successful empty result', async () => {
  const pending = deferred<MoneyFlowData>(); readFlow.mockReturnValue(pending.promise); mount();
  expect(await screen.findByText('Tracing the money...')).toBeVisible();
  expect(screen.queryByText(/No money flow data/)).not.toBeInTheDocument();
  await act(async () => pending.resolve({ ...flow, stages: [] }));
  expect(await screen.findByText('No money flow data available for this period.')).toBeVisible();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
});

it('distinguishes a failed read from absence and bounds retry while recovering figures and notes', async () => {
  readFlow.mockRejectedValueOnce(new Error('Synthetic endpoint failure')); mount();
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load money flow for this period');
  expect(screen.queryByText(/No money flow data/)).not.toBeInTheDocument();
  expect(screen.queryByText(/KES/)).not.toBeInTheDocument();
  const pending = deferred<MoneyFlowData>(); readFlow.mockReturnValueOnce(pending.promise);
  const retry = screen.getByRole('button', { name: 'Try again' });
  fireEvent.click(retry);
  fireEvent.click(retry);
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument());
  expect(screen.getByRole('status')).toHaveTextContent('Tracing the money');
  expect(readFlow).toHaveBeenCalledTimes(2);
  await act(async () => pending.resolve(flow));
  await waitFor(() => expect(screen.getByText('KES 10.00B')).toBeVisible());
  await waitFor(() => expect(screen.getByText('KES 6.00B')).toBeVisible());
  expect(screen.getByText(/procurement-encumbered/)).toBeVisible();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('keeps year selection available on failure and restores the selected cached period', async () => {
  mount(); await waitFor(() => expect(screen.getByText('KES 10.00B')).toBeVisible());
  readFlow.mockRejectedValueOnce(new Error('Synthetic second period failure'));
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'FY2024/25' } });
  expect(await screen.findByRole('alert')).toBeVisible();
  expect(screen.queryByText('KES 10.00B')).not.toBeInTheDocument();
  expect(screen.getByRole('combobox')).toHaveValue('FY2024/25');
  fireEvent.change(screen.getByRole('combobox'), { target: { value: years.default } });
  await waitFor(() => expect(screen.getByText('KES 10.00B')).toBeVisible());
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it.each([
  ['sw', 'Imeshindikana kupakia mtiririko wa pesa kwa kipindi hiki.', 'Jaribu tena'],
  ['plain', 'We could not load money flow for this period.', 'Try again'],
])('localizes failed reads and retry in %s', async (lang, message, retry) => {
  localStorage.setItem('auditgava-lang', lang);
  readFlow.mockRejectedValue(new Error('Synthetic failure')); mount();
  expect(await screen.findByRole('alert')).toHaveTextContent(message);
  expect(screen.getByRole('button', { name: retry })).toBeVisible();
  expect(screen.queryByText(/No money flow data/)).not.toBeInTheDocument();
});
