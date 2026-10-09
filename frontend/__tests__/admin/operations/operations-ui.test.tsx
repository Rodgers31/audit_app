import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/lib/api/axios';
import Ingestion from '@/app/admin/ingestion/page';
import Etl from '@/app/admin/etl/page';
import { ETL_SOURCES } from '@/lib/admin/etl';

let query = '';
const replace = jest.fn();
const push = jest.fn();
jest.mock('next/navigation', () => ({ useRouter: () => ({ replace, push }), useSearchParams: () => new URLSearchParams(query) }));
jest.mock('@/components/layout/PageShell', () => ({ __esModule: true, default: ({ title, subtitle, children }: any) => <main><h1>{title}</h1><p>{subtitle}</p>{children}</main> }));
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true, isLoading: false }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: 'inert-operations-admin' } }) }));
const get = api.get as jest.Mock;
const post = api.post as jest.Mock;
const timestamp = '2026-10-08T12:00:00Z';
export const job = { id:1, domain:'audits', status:'completed', dry_run:true, started_at:timestamp,
  finished_at:timestamp, duration_seconds:0, items_processed:3, items_created:2, items_updated:1,
  errors:[], error_count:0, metadata:{}, diagnostics_redacted:true, created_at:timestamp };
const list = { jobs:[job], total:1, page:1, page_size:20, has_more:false };
const manual = { available:false, reason:'No dedicated worker dispatch is connected. No job was accepted.' };
export const plan = { timestamp, evidence:'calendar_plan', manual_trigger:manual, summary:{ sources_running_today:1,
  sources_skipping_today:5, total_sources:6, skip_percentage:83.3, efficiency_vs_fixed_schedule:'92% fewer planned checks than fixed schedule',
  sources_to_run:[{source:'oag',reason:'Synthetic plan'}], sources_not_running:ETL_SOURCES.filter(source=>source!=='oag') },
  sources:Object.fromEntries(ETL_SOURCES.map(source=>[source,{should_run:source==='oag', should_run_now:source==='oag',
    reason:source==='oag'?'Synthetic plan':`${source} deferred`, next_run:null, next_reason:'Synthetic next', current_period:'default'}])) };
export const health = {timestamp, scheduler_status:'unverified', plan_status:'available', worker_status:'unverified',
  data_freshness:'unverified', schedule_summary:null, manual_trigger:manual};

function mount(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions:{queries:{retry:false}, mutations:{retry:false}} });
  return {qc, ...render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>)};
}
beforeEach(() => {
  jest.clearAllMocks(); query='';
  Object.defineProperty(document, 'visibilityState', { configurable:true, value:'visible' });
});
afterEach(() => jest.useRealTimers());

test('hostile URL parameters never reach the API and are replaced with bounded defaults', async () => {
  query='days=NaN&page=-12&domain='+ 'x'.repeat(101)+'&status=unrecognized';
  get.mockResolvedValue({ data:list });
  mount(<Ingestion />);
  await screen.findAllByText('audits');
  expect(get.mock.calls[0][1].params).toEqual({page:1,page_size:20,days:7});
  expect(replace).toHaveBeenCalledWith('/admin/ingestion');
});

test('filter labels are usable and filter changes use navigable history', async () => {
  query='page=3'; get.mockResolvedValue({data:{...list,jobs:[],page:3,total:41}});
  mount(<Ingestion />);
  fireEvent.change(await screen.findByLabelText('Status'), { target:{value:'failed'} });
  expect(push).toHaveBeenCalledWith('/admin/ingestion?status=failed');
});

test('an empty later page retains a way back to earlier jobs', async () => {
  query='page=4'; get.mockResolvedValue({ data:{...list,jobs:[],page:4,total:41} });
  mount(<Ingestion />);
  await screen.findByText(/No jobs/);
  fireEvent.click(screen.getByRole('button', {name:'Prev'}));
  expect(push).toHaveBeenCalledWith('/admin/ingestion?page=3');
});

test.each([null, {}, {...list,total:-1}, {...list,jobs:[{...job,status:'mystery'}]}, {...list,jobs:[{...job,items_processed:true}]}])('malformed lists are an error state, never no jobs or a table', async raw => {
  get.mockResolvedValue({data:raw}); mount(<Ingestion />);
  await screen.findByText('Could not load jobs.');
  expect(screen.queryByText('No jobs match these filters.')).not.toBeInTheDocument();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

test('desktop jobs have keyboard-accessible detail links and dry-run remains visible', async () => {
  get.mockResolvedValue({data:list}); mount(<Ingestion />);
  const link = await screen.findByRole('link', {name:'View job #1'});
  expect(link).toHaveAttribute('href','/admin/ingestion/1');
  expect(screen.getAllByText('dry-run')).toHaveLength(2);
});

test('a failed refresh stops showing old successful counts', async () => {
  get.mockResolvedValueOnce({data:list}).mockRejectedValue({ response:{status:403,data:{detail:'PRIVATE_ERROR'}} });
  mount(<Ingestion />); await screen.findAllByText('audits');
  fireEvent.click(screen.getByRole('button', {name:'Refresh'}));
  await screen.findByText('Could not load jobs.');
  expect(screen.queryByText(/1 job in the last/)).not.toBeInTheDocument();
  expect(screen.queryByText(/PRIVATE_ERROR/)).not.toBeInTheDocument();
});

test('running jobs poll while visible, pause hidden and stop at completion', async () => {
  jest.useFakeTimers(); let state = {...job,status:'running',finished_at:null,duration_seconds:null};
  get.mockImplementation(async () => ({data:{...list,jobs:[state]}}));
  mount(<Ingestion />); await screen.findAllByText('running');
  await act(async () => { jest.advanceTimersByTime(15_001); });
  expect(get).toHaveBeenCalledTimes(2);
  Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  await act(async () => {jest.advanceTimersByTime(60_000);});
  expect(get).toHaveBeenCalledTimes(2);
  state={...state,status:'completed'};
  Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});
  await act(async () => document.dispatchEvent(new Event('visibilitychange')));
  await screen.findAllByText('completed');
  const calls=get.mock.calls.length;
  await act(async () => {jest.advanceTimersByTime(60_000);});
  expect(get).toHaveBeenCalledTimes(calls);
});

test('calendar planning never renders running or healthy worker claims and unavailable controls cannot dispatch', async () => {
  get.mockImplementation(async path => ({data:path.endsWith('/health')?health:plan}));
  mount(<Etl />);
  await screen.findByText('Synthetic plan');
  expect(screen.getByText('Planned today')).toBeInTheDocument();
  expect(screen.queryByText('Running today')).not.toBeInTheDocument();
  expect(screen.queryByText('Scheduler health')).not.toBeInTheDocument();
  expect(screen.getAllByRole('button',{name:'Trigger'})).toHaveLength(6);
  expect(screen.getAllByRole('button',{name:'Dry-run'})).toHaveLength(6);
  screen.getAllByRole('button',{name:'Trigger'}).forEach(button=>expect(button).toBeDisabled());
  screen.getAllByRole('button',{name:'Dry-run'}).forEach(button=>expect(button).toBeDisabled());
  expect(screen.getByText(/No job was accepted/)).toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
});

test('malformed schedule and health are recoverable errors', async () => {
  get.mockResolvedValue({data:{timestamp,summary:{},sources:{}}}); mount(<Etl />);
  await screen.findByText('Could not load schedule.');
  expect(screen.getByText('Could not load execution evidence.')).toBeInTheDocument();
});

test.each(['ingestion', 'etl'])('an initially hidden %s page awaits its first read without claiming empty or failed results', async surface => {
  Object.defineProperty(document, 'visibilityState', { configurable:true, value:'hidden' });
  get.mockResolvedValue({data:list});
  mount(surface === 'ingestion' ? <Ingestion /> : <Etl />);
  await act(async () => {});
  expect(get).not.toHaveBeenCalled();
  expect(screen.queryByText('No jobs match these filters.')).not.toBeInTheDocument();
  expect(screen.queryByText('Could not load schedule.')).not.toBeInTheDocument();
});
