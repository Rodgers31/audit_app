import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import DispatchPanel from '@/app/admin/etl/DispatchPanel';
import { CommandDetail } from '@/app/admin/etl/commands/[commandId]/CommandDetail';
import api from '@/lib/api/axios';
import { AdminGuard } from '@/lib/auth/admin';
import { commandProgress, parseCommand, parseCommandAcceptance, parseCommandList, parseDispatchCapability } from '@/lib/admin/etlDispatch';
import examples from './batch7_etl_ui_examples.json';

// Independent review fixture. Real useAdmin, useOperationsAccess, useEtlAccess,
// React Query and product components run; only auth evidence/transport are inert.
const actorA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const actorB = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
let mockAuthUser = { id: actorA };
let mockProfile: { id:string; roles:string[] } | null = { id: actorA, roles: ['admin'] };
let mockLoading = false;
let mockQuery = '';
let mockActorSequence = 0;
const mockSubscribers = new Set<() => void>();
const mockPush = jest.fn(), mockReplace = jest.fn();
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: mockPush, replace: mockReplace }), useSearchParams: () => new URLSearchParams(mockQuery) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ authUser: mockAuthUser, user: mockProfile, isLoading: mockLoading, isAuthenticated: true }) }));
jest.mock('@/lib/supabase/client', () => ({ createClient: () => ({ auth: { onAuthStateChange: (fn: () => void) => {
  mockSubscribers.add(fn); return { data: { subscription: { unsubscribe: () => mockSubscribers.delete(fn) } } };
} } }) }));
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock('@/components/layout/PageShell', () => ({ __esModule: true, default: ({ children }: {children: React.ReactNode}) => <main>{children}</main> }));
const get = api.get as jest.Mock, post = api.post as jest.Mock;
const names = ['treasury', 'cob', 'oag', 'knbs', 'opendata', 'cra'];
const emptyHistory = { entries: [], page: 1, page_size: 20, total: 0, has_more: false };
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value));
const receipt = () => ({ ...examples.accepted.command, dry_run: true });
const acceptance = () => ({ ...examples.accepted, command: receipt() });
const ready = () => ({ ...examples.capability_ready, timestamp: new Date().toISOString(), worker: {
  status: 'ready', last_seen_at: new Date(Date.now() - 1000).toISOString(), expires_at: new Date(Date.now() + 30000).toISOString(),
} });
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (error: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
function mount(node: React.ReactNode = <DispatchPanel />) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: 5 } } });
  const wrap = () => <QueryClientProvider client={qc}>{React.isValidElement(node) ? React.cloneElement(node) : node}</QueryClientProvider>;
  const view = render(wrap());
  return { ...view, qc, refresh: () => view.rerender(wrap()) };
}
function visibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: state });
  act(() => document.dispatchEvent(new Event('visibilitychange')));
}
async function button(name = 'Dry Run · oag') {
  const value = await screen.findByRole('button', { name });
  await waitFor(() => expect(value).toBeEnabled());
  return value;
}
const transitions = ['actor', 'privilege-loss', 'profile-renewal', 'sdk-renewal', 'hidden', 'unmount'] as const;
function change(kind: typeof transitions[number], view: ReturnType<typeof mount>) {
  if (kind === 'actor') { mockAuthUser = { id: actorB }; mockProfile = { id: actorB, roles: ['admin'] }; view.refresh(); }
  if (kind === 'privilege-loss') { mockProfile = { id:mockAuthUser.id, roles: ['citizen'] }; view.refresh(); }
  if (kind === 'profile-renewal') { mockLoading = true; view.refresh(); mockLoading = false; view.refresh(); }
  if (kind === 'sdk-renewal') act(() => { for (const fn of Array.from(mockSubscribers)) fn(); });
  if (kind === 'hidden') visibility('hidden');
  if (kind === 'unmount') view.unmount();
}
beforeEach(() => {
  const id = 'aaaaaaaa-aaaa-4aaa-8aaa-' + (++mockActorSequence).toString(16).padStart(12,'0');
  jest.clearAllMocks(); mockSubscribers.clear(); mockAuthUser = { id }; mockProfile = { id, roles: ['admin'] }; mockLoading = false; mockQuery = '';
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/dispatch') ? ready() : path.endsWith('/commands') ? emptyHistory : receipt() }));
  post.mockResolvedValue({ status: 202, data: acceptance() });
});
afterEach(() => jest.useRealTimers());

test.each(transitions)('adversarial late acceptance after %s cannot show success or retain old cache', async kind => {
  const pending = deferred<unknown>(); post.mockReturnValueOnce(pending.promise);
  const view = mount(); fireEvent.click(await button());
  const originatingActor = mockAuthUser.id;
  expect(post).toHaveBeenCalledTimes(1);
  const signal = post.mock.calls[0][2].signal as AbortSignal;
  change(kind, view); expect(signal.aborted).toBe(true);
  await act(async () => pending.resolve({ status: 202, data: acceptance() }));
  expect(screen.queryByText('Command accepted. Queued acceptance is not completed work.')).not.toBeInTheDocument();
  expect(view.qc.getQueriesData({ queryKey: ['admin', 'etl-command', originatingActor, 0] }).every(([,value]) => value === undefined)).toBe(true);
  expect(post).toHaveBeenCalledTimes(1);
});
test.each(transitions)('adversarial deferred real-run confirmation after %s sends no POST', async kind => {
  const view = mount(); fireEvent.click(await button('Run Now · oag'));
  const confirm = within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirm Run Now' });
  change(kind, view); fireEvent.click(confirm);
  await act(async () => {});
  expect(post).not.toHaveBeenCalled();
});
test.each(transitions)('adversarial late receipt GET after %s cannot show old completed observation', async kind => {
  const pending = deferred<unknown>(); get.mockReturnValueOnce(pending.promise);
  const view = mount(<CommandDetail commandId={examples.detail.id} />);
  await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
  const signal = get.mock.calls[0][1].signal as AbortSignal;
  change(kind, view); expect(signal.aborted).toBe(true);
  await act(async () => pending.resolve({ data: examples.detail }));
  expect(screen.queryByRole('link', { name: 'View ingestion observation #1' })).not.toBeInTheDocument();
  expect(screen.queryByText('Completed — recorded ingestion observation.')).not.toBeInTheDocument();
});
test.each(transitions)('adversarial late history GET after %s cannot show old actor receipt', async kind => {
  const pending = deferred<unknown>(); let gated = false;
  get.mockImplementation(async (path:string) => {
    if(path.endsWith('/commands') && !gated) { gated = true; return pending.promise; }
    return { data: path.endsWith('/dispatch') ? ready() : emptyHistory };
  });
  const view = mount(); await waitFor(() => expect(get.mock.calls.some(([path]) => path.endsWith('/commands'))).toBe(true));
  const call = get.mock.calls.find(([path]) => path.endsWith('/commands'));
  const signal = call![1].signal as AbortSignal;
  change(kind, view); expect(signal.aborted).toBe(true);
  await act(async () => pending.resolve({data:examples.list}));
  expect(screen.queryByRole('link',{ name:'View command '+examples.detail.id })).not.toBeInTheDocument();
  expect(screen.queryByText('Completed — recorded ingestion observation.')).not.toBeInTheDocument();
});
test.each([401, 403])('adversarial current GET %s clears success while old-lifetime denial cannot deny a new session', async status => {
  const view = mount(<CommandDetail commandId={examples.detail.id} />);
  await screen.findByText('Queued — accepted, awaiting execution.');
  const old = deferred<unknown>(); get.mockReturnValueOnce(old.promise);
  fireEvent.click(screen.getByRole('button', { name: 'Refresh receipt' }));
  await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  act(() => { for (const fn of Array.from(mockSubscribers)) fn(); });
  await screen.findByText('Queued — accepted, awaiting execution.');
  await act(async () => old.reject({ response: { status, data: { detail: 'REVIEW_PRIVATE_DIAGNOSTIC' } } }));
  expect(screen.queryByText('Administrator access expired. Renew your session to verify access.')).not.toBeInTheDocument();
  get.mockRejectedValueOnce({ response: { status, data: { detail: 'REVIEW_PRIVATE_DIAGNOSTIC' } } });
  fireEvent.click(screen.getByRole('button', { name: 'Refresh receipt' }));
  await screen.findByText('Administrator access expired. Renew your session to verify access.');
  expect(screen.queryByText('Queued — accepted, awaiting execution.')).not.toBeInTheDocument();
  expect(screen.queryByText('REVIEW_PRIVATE_DIAGNOSTIC')).not.toBeInTheDocument();
  expect(view.qc.getQueriesData({ queryKey: ['admin', 'etl-command'] }).every(([,value]) => value === undefined)).toBe(true);
});
test('adversarial lost response has no automatic POST retry, retains same key across renewal, rotates changed mode', async () => {
  post.mockRejectedValueOnce(new Error('lost response after durable commit'));
  mount(); fireEvent.click(await button()); await screen.findByRole('button', { name: 'Recover same intent' });
  const original = post.mock.calls[0][2].headers['Idempotency-Key'];
  await act(async () => {}); expect(post).toHaveBeenCalledTimes(1);
  act(() => { for (const fn of Array.from(mockSubscribers)) fn(); });
  const recover = await screen.findByRole('button', { name: 'Recover same intent' });
  fireEvent.click(recover); await screen.findByText('Command accepted. Queued acceptance is not completed work.');
  expect(post.mock.calls[1][2].headers['Idempotency-Key']).toBe(original);
  post.mockResolvedValueOnce({ status: 202, data: { ...acceptance(), command: { ...receipt(), dry_run: false } } });
  fireEvent.click(await button('Run Now · oag'));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirm Run Now' }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
  expect(post.mock.calls[2][2].headers['Idempotency-Key']).not.toBe(original);
});
test.each([401, 403])('review regression definite POST %s retires its key before same-actor guard renewal', async status => {
  post.mockRejectedValueOnce({response:{status,data:{detail:'REVIEW_PRIVATE_DIAGNOSTIC'}}});
  const view = mount(<AdminGuard><DispatchPanel /></AdminGuard>);
  fireEvent.click(await button());
  const rejectedKey = post.mock.calls[0][2].headers['Idempotency-Key'];
  await screen.findByText('Administrator access expired. Renew your session to verify access.');
  expect(screen.getByRole('button',{name:'Dry Run · oag'})).toBeDisabled();
  expect(screen.queryByText('REVIEW_PRIVATE_DIAGNOSTIC')).not.toBeInTheDocument();
  mockProfile = null; mockLoading = true; view.refresh();
  await screen.findByText('Verifying access…');
  mockAuthUser = {...mockAuthUser};
  mockProfile = {id:mockAuthUser.id,roles:['admin']}; mockLoading = false; view.refresh();
  await button();
  expect(screen.queryByRole('button',{name:'Recover same intent'})).not.toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(1);
  fireEvent.click(await button());
  await screen.findByText('Command accepted. Queued acceptance is not completed work.');
  expect(post.mock.calls[1][2].headers['Idempotency-Key']).not.toBe(rejectedKey);
});
test.each([401, 403])('review control refused recovery POST %s preserves original uncertainty across renewal', async status => {
  post.mockRejectedValueOnce(new Error('lost response after durable commit'));
  const view = mount(<AdminGuard><DispatchPanel /></AdminGuard>);
  fireEvent.click(await button());
  const originalKey = post.mock.calls[0][2].headers['Idempotency-Key'];
  await screen.findByRole('button',{name:'Recover same intent'});
  post.mockRejectedValueOnce({response:{status}});
  fireEvent.click(screen.getByRole('button',{name:'Recover same intent'}));
  await screen.findByText('Administrator access expired. Renew your session to verify access.');
  mockProfile = null; mockLoading = true; view.refresh();
  await screen.findByText('Verifying access…');
  mockAuthUser = {...mockAuthUser};
  mockProfile = {id:mockAuthUser.id,roles:['admin']}; mockLoading = false; view.refresh();
  await button();
  const recover = await screen.findByRole('button',{name:'Recover same intent'});
  expect(post).toHaveBeenCalledTimes(2);
  post.mockResolvedValueOnce({status:202,data:{...acceptance(),replayed:true}});
  fireEvent.click(recover);
  await screen.findByText('Original receipt recovered. No second command was accepted.');
  expect(post.mock.calls[1][2].headers['Idempotency-Key']).toBe(originalKey);
  expect(post.mock.calls[2][2].headers['Idempotency-Key']).toBe(originalKey);
});
test.each([400, 404, 409, 422])('review control definite POST %s never becomes ambiguous after same-actor renewal', async status => {
  post.mockRejectedValueOnce({response:{status}});
  const view = mount(); fireEvent.click(await button());
  const rejectedKey = post.mock.calls[0][2].headers['Idempotency-Key'];
  await screen.findByText('Command was not acknowledged. Refresh worker evidence before a new intent.');
  mockAuthUser = {...mockAuthUser}; view.refresh();
  await button();
  expect(screen.queryByRole('button',{name:'Recover same intent'})).not.toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(1);
  fireEvent.click(await button());
  await screen.findByText('Command accepted. Queued acceptance is not completed work.');
  expect(post.mock.calls[1][2].headers['Idempotency-Key']).not.toBe(rejectedKey);
});
test.each(['network', '500', '503', 'malformed-202'])('review control %s preserves explicit same-key recovery across guard renewal', async kind => {
  if(kind==='network') post.mockRejectedValueOnce(new Error('lost response after durable commit'));
  else if(kind==='malformed-202') post.mockResolvedValueOnce({status:202,data:{ok:true,accepted:true}});
  else post.mockRejectedValueOnce({response:{status:Number(kind)}});
  const view = mount(<AdminGuard><DispatchPanel /></AdminGuard>);
  fireEvent.click(await button());
  const original = post.mock.calls[0][2].headers['Idempotency-Key'];
  await screen.findByRole('button',{name:'Recover same intent'});
  mockProfile = null; mockLoading = true; view.refresh();
  await screen.findByText('Verifying access…');
  mockAuthUser = {...mockAuthUser};
  mockProfile = {id:mockAuthUser.id,roles:['admin']}; mockLoading = false; view.refresh();
  const recover = await screen.findByRole('button',{name:'Recover same intent'});
  expect(post).toHaveBeenCalledTimes(1);
  fireEvent.click(recover);
  await screen.findByText('Command accepted. Queued acceptance is not completed work.');
  expect(post.mock.calls[1][2].headers['Idempotency-Key']).toBe(original);
});
test('adversarial actual AdminGuard revalidation unmount retains an uncertain same-actor UUID without automatic POST', async () => {
  const old = deferred<unknown>(); post.mockReturnValueOnce(old.promise);
  const view = mount(<AdminGuard><DispatchPanel /></AdminGuard>);
  fireEvent.click(await button()); const key = post.mock.calls[0][2].headers['Idempotency-Key'];
  const signal = post.mock.calls[0][2].signal as AbortSignal;
  mockProfile = null; mockLoading = true; view.refresh();
  expect(signal.aborted).toBe(true);
  await screen.findByText('Verifying access…');
  await act(async () => old.resolve({status:202,data:acceptance()}));
  mockProfile = {id:mockAuthUser.id,roles:['admin']}; mockLoading = false; view.refresh();
  const recover = await screen.findByRole('button',{name:'Recover same intent'});
  expect(post).toHaveBeenCalledTimes(1);
  fireEvent.click(recover); await screen.findByText('Command accepted. Queued acceptance is not completed work.');
  expect(post).toHaveBeenCalledTimes(2); expect(post.mock.calls[1][2].headers['Idempotency-Key']).toBe(key);
});
test('adversarial unresolved guarded intent is hidden from a new actor and recoverable only by the originating actor', async () => {
  post.mockRejectedValueOnce(new Error('lost response'));
  const originalActor = mockAuthUser.id;
  const view = mount(<AdminGuard><DispatchPanel /></AdminGuard>);
  fireEvent.click(await button()); await screen.findByRole('button',{name:'Recover same intent'});
  const key = post.mock.calls[0][2].headers['Idempotency-Key'];
  mockProfile = null; mockLoading = true; view.refresh();
  mockAuthUser = {id:actorB}; mockProfile = {id:actorB,roles:['admin']}; mockLoading = false; view.refresh();
  await button(); expect(screen.queryByRole('button',{name:'Recover same intent'})).not.toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(1);
  mockProfile = null; mockLoading = true; view.refresh();
  mockAuthUser = {id:originalActor}; mockProfile = {id:originalActor,roles:['admin']}; mockLoading = false; view.refresh();
  fireEvent.click(await screen.findByRole('button',{name:'Recover same intent'}));
  await screen.findByText('Command accepted. Queued acceptance is not completed work.');
  expect(post).toHaveBeenCalledTimes(2); expect(post.mock.calls[1][2].headers['Idempotency-Key']).toBe(key);
});
test('adversarial initial hidden mount requests no private transport', async () => {
  visibility('hidden'); mount(); await act(async () => {}); expect(get).not.toHaveBeenCalled(); expect(post).not.toHaveBeenCalled();
  visibility('visible'); await button();
});
test.each(['malformed','expired','transport-error'])('adversarial %s worker refresh disables controls and hides prior panel success', async mode => {
  mount(); fireEvent.click(await button());
  await screen.findByText('Command accepted. Queued acceptance is not completed work.');
  get.mockImplementation(async (path:string) => {
    if(path.endsWith('/dispatch')) {
      if(mode==='transport-error') throw {response:{status:503,data:{detail:'REVIEW_PRIVATE_DIAGNOSTIC'}}};
      const capability = ready();
      return {data:mode==='malformed'?{...capability,available:'true'}:{...capability,worker:{...capability.worker,expires_at:new Date(Date.now()-1).toISOString()}}};
    }
    return {data:path.endsWith('/commands')?emptyHistory:receipt()};
  });
  fireEvent.click(screen.getByRole('button',{name:'Refresh worker evidence'}));
  await screen.findByText('Worker evidence unavailable or malformed. Controls are disabled.');
  expect(screen.queryByText('Command accepted. Queued acceptance is not completed work.')).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Run Now · oag'})).toBeDisabled();
  expect(screen.queryByText('REVIEW_PRIVATE_DIAGNOSTIC')).not.toBeInTheDocument();
});
test('adversarial expiry while a real-run dialog is deferred prevents publication intent', async () => {
  jest.useFakeTimers(); mount(); fireEvent.click(await button('Run Now · oag'));
  const confirm = within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirm Run Now' });
  await act(async () => { jest.advanceTimersByTime(31000); });
  fireEvent.click(confirm); expect(post).not.toHaveBeenCalled();
});

const invalidValues: unknown[] = [undefined, null, '', false, true, NaN, Infinity, -Infinity, 0, -1, {}, []];
test('adversarial required capability and command fields reject hostile primitive/empty shapes', () => {
  const now = Date.parse(examples.capability_ready.timestamp);
  for (const value of invalidValues) {
    expect(() => parseDispatchCapability(value, now)).toThrow(); expect(() => parseCommand(value)).toThrow();
    for (const key of ['id','source','dry_run','status','version','created_at','updated_at'] as const) {
      if (key === 'dry_run' && typeof value === 'boolean') continue;
      expect(() => parseCommand({ ...examples.detail, [key]: value })).toThrow();
    }
    for (const key of ['timestamp','evidence','reason','generation','worker','sources'] as const) {
      expect(() => parseDispatchCapability({ ...examples.capability_ready, [key]: value }, now)).toThrow();
    }
  }
  for (const name of names) {
    const raw = clone(examples.capability_ready) as {sources: Record<string, unknown>}; delete raw.sources[name];
    expect(() => parseDispatchCapability(raw, now)).toThrow();
  }
});
test('adversarial acceptance and history enforce actual boolean, UUID, status, intent and bounds', () => {
  for (const value of invalidValues.filter(v => v !== true)) {
    for (const key of ['ok','accepted','audit_recorded']) expect(() => parseCommandAcceptance({ ...examples.accepted, [key]: value }, { source:'oag', dry_run:true }, 202)).toThrow();
  }
  for (const value of invalidValues.filter(v => typeof v !== 'boolean')) {
    expect(() => parseCommandAcceptance({ ...examples.accepted, replayed: value }, {source:'oag',dry_run:true},202)).toThrow();
  }
  for (const id of ['../../oag','22222222-2222-4222-8222-222222222222 ','AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA']) expect(() => parseCommand({ ...examples.detail, id })).toThrow();
  for (const page of [0,-1,true,NaN,Infinity,10001,'1']) expect(() => parseCommandList(examples.list,{ page:page as number,page_size:20,source:'',status:'' })).toThrow();
  for (const page_size of [0,-1,true,NaN,Infinity,51,'20']) expect(() => parseCommandList(examples.list,{ page:1,page_size:page_size as number,source:'',status:'' })).toThrow();
  expect(() => parseCommandAcceptance(examples.accepted,{source:'cra',dry_run:true},202)).toThrow();
  expect(() => parseCommandAcceptance(examples.accepted,{source:'oag',dry_run:false},202)).toThrow();
});
test('adversarial submillisecond chronology rejects a receipt updated before it was created', () => {
  expect(() => parseCommand({ ...examples.accepted.command, created_at:'2026-10-09T12:00:00.000002Z', updated_at:'2026-10-09T12:00:00.000001Z' })).toThrow();
});
test('adversarial submillisecond worker heartbeat cannot lie after the server evidence timestamp', () => {
  expect(() => parseDispatchCapability({ ...examples.capability_ready, timestamp:'2026-10-09T12:00:00.000001Z', worker:{ ...examples.capability_ready.worker,last_seen_at:'2026-10-09T12:00:00.000002Z' } },Date.parse(examples.capability_ready.timestamp))).toThrow();
});
test('adversarial submillisecond equal-millisecond history still enforces actual descending creation order', () => {
  const earlier = { ...examples.detail,id:'33333333-3333-4333-8333-333333333333',created_at:'2026-10-09T12:00:00.000001Z' };
  const later = { ...examples.detail,id:'11111111-1111-4111-8111-111111111111',created_at:'2026-10-09T12:00:00.000002Z' };
  expect(() => parseCommandList({ ...examples.list,total:2,entries:[earlier,later] },{page:1,page_size:20,source:'',status:''})).toThrow();
});
test('adversarial terminal receipt cannot rewrite its recorded finished timestamp', () => {
  const previous = parseCommand(examples.detail);
  const rewritten = parseCommand({ ...examples.detail,version:4,finished_at:'2026-10-09T12:00:04Z',updated_at:'2026-10-09T12:00:04Z' });
  expect(() => commandProgress(rewritten,previous)).toThrow();
});
test('adversarial rendered completed receipt with reversed microsecond chronology exposes no observation link', async () => {
  get.mockResolvedValueOnce({ data: { ...examples.detail,
    created_at:'2026-10-09T12:00:00.000002Z',updated_at:'2026-10-09T12:00:00.000001Z',
    started_at:'2026-10-09T12:00:00.000002Z',finished_at:'2026-10-09T12:00:00.000001Z',
  } });
  mount(<CommandDetail commandId={examples.detail.id} />);
  await screen.findByText('Could not verify this command receipt. Refresh to retry.');
  expect(screen.queryByRole('link', { name: 'View ingestion observation #1' })).not.toBeInTheDocument();
});
test('adversarial rendered terminal refresh hides success after a rewritten finished timestamp', async () => {
  get.mockResolvedValueOnce({ data: examples.detail });
  mount(<CommandDetail commandId={examples.detail.id} />);
  await screen.findByText('Completed — recorded ingestion observation.');
  get.mockResolvedValueOnce({ data: { ...examples.detail, version:4,finished_at:'2026-10-09T12:00:04Z',updated_at:'2026-10-09T12:00:04Z' } });
  fireEvent.click(screen.getByRole('button', { name:'Refresh receipt' }));
  await screen.findByText('Could not verify this command receipt. Refresh to retry.');
  expect(screen.queryByText('Completed — recorded ingestion observation.')).not.toBeInTheDocument();
});
test('adversarial rapid history filters merge while intermediate router navigation is unfinished', async () => {
  get.mockImplementation(async (path:string,config:{params?:{page:number;page_size:number}}) => ({data:path.endsWith('/dispatch')?ready():path.endsWith('/commands')?{...emptyHistory,page:config.params!.page,page_size:config.params!.page_size}:receipt()}));
  const view = mount(); await screen.findByText('No commands match this page.');
  fireEvent.change(screen.getByRole('combobox',{name:'Command source'}),{target:{value:'oag'}});
  fireEvent.change(screen.getByRole('combobox',{name:'Command status'}),{target:{value:'completed'}});
  fireEvent.change(screen.getByRole('combobox',{name:'Commands per page'}),{target:{value:'50'}});
  expect(mockPush).toHaveBeenLastCalledWith('/admin/etl?source=oag&status=completed&page_size=50');
  // First navigation completes after subsequent filter intents have been sent.
  mockQuery='source=oag';view.refresh();
  fireEvent.change(screen.getByRole('combobox',{name:'Command status'}),{target:{value:'failed'}});
  expect(mockPush).toHaveBeenLastCalledWith('/admin/etl?source=oag&status=failed&page_size=50');
  mockQuery='source=oag&status=failed&page_size=50';view.refresh();
  await waitFor(()=>expect(get.mock.calls.some(([path,config])=>path.endsWith('/commands')&&config.params.source==='oag'&&config.params.status==='failed'&&config.params.page_size===50)).toBe(true));
  fireEvent.change(screen.getByRole('combobox',{name:'Command source'}),{target:{value:'cra'}});
  expect(mockPush).toHaveBeenLastCalledWith('/admin/etl?source=cra&status=failed&page_size=50');
});
test('adversarial clear and browser back remove unfinished history filter intents before the next edit', async () => {
  get.mockImplementation(async (path:string,config:{params?:{page:number;page_size:number}}) => ({data:path.endsWith('/dispatch')?ready():path.endsWith('/commands')?{...emptyHistory,page:config.params!.page,page_size:config.params!.page_size}:receipt()}));
  mockQuery='source=oag&status=failed&page=2';
  const view = mount(); await screen.findByText('No commands match this page.');
  fireEvent.change(screen.getByRole('combobox',{name:'Command status'}),{target:{value:'completed'}});
  fireEvent.click(screen.getByRole('button',{name:'Clear command filters'}));
  expect(mockPush).toHaveBeenLastCalledWith('/admin/etl');
  fireEvent.change(screen.getByRole('combobox',{name:'Command source'}),{target:{value:'cra'}});
  expect(mockPush).toHaveBeenLastCalledWith('/admin/etl?source=cra');
  mockQuery='source=cra';view.refresh();
  fireEvent.change(screen.getByRole('combobox',{name:'Command status'}),{target:{value:'running'}});
  expect(mockPush).toHaveBeenLastCalledWith('/admin/etl?source=cra&status=running');
  mockQuery='source=knbs&page_size=50';act(()=>window.dispatchEvent(new PopStateEvent('popstate')));view.refresh();
  fireEvent.change(screen.getByRole('combobox',{name:'Command status'}),{target:{value:'failed'}});
  expect(mockPush).toHaveBeenLastCalledWith('/admin/etl?source=knbs&status=failed&page_size=50');
});
