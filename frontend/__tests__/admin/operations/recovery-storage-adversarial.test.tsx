import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import DispatchPanel from '@/app/admin/etl/DispatchPanel';
import { clearSubmittedIntent, rememberSubmittedIntent, submittedIntent } from '@/app/admin/etl/submittedIntent';
import api from '@/lib/api/axios';
const actor = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const generation = '11111111-1111-4111-8111-111111111111';
const originalKey = '22222222-2222-4222-8222-222222222222';
const storageKey = 'auditgava.etl.submitted-intent.v1:' + actor;
const original = { source: 'oag' as const, dry_run: true, key: originalKey, generation };
const mockRelease = jest.fn(), mockController = jest.fn(() => new AbortController());
const mockAccess = { actorId: actor, authActorId: actor, lifetime: 0, enabled: true, denied: false, visible: true, current: () => true, controller: mockController, release: mockRelease, rejectAccess: jest.fn(), read: async (path: string, signal: AbortSignal, parse: (value: unknown) => unknown) => parse((await api.get(path, { signal })).data) };
jest.mock('@/app/admin/etl/useEtlAccess', () => ({ useEtlAccess: () => mockAccess }));
jest.mock('@/app/admin/etl/CommandHistory', () => ({ CommandHistory: () => null }));
jest.mock('@/app/admin/etl/useCommandReceipt', () => ({ useCommandReceipt: () => ({ isError: false, data: undefined }) }));
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
const get = api.get as jest.Mock, send = api.post as jest.Mock;
const clients: QueryClient[] = [];
function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false, gcTime: 0 } } }); clients.push(qc);
  return render(<QueryClientProvider client={qc}><DispatchPanel /></QueryClientProvider>);
}
async function ready() {
  const button = await screen.findByRole('button', { name: 'Dry Run · oag' }); await waitFor(() => expect(button).toBeEnabled()); return button;
}
beforeEach(() => {
  jest.restoreAllMocks(); jest.clearAllMocks(); sessionStorage.clear();
  HTMLDialogElement.prototype.showModal = function () { this.open = true; }; HTMLDialogElement.prototype.close = function () { this.open = false; };
  get.mockImplementation(async () => ({ data: { timestamp: new Date().toISOString(), evidence: 'worker_dispatch', available: true, reason: 'Inert bounded worker evidence', generation, worker: { status: 'ready', last_seen_at: new Date(Date.now() - 1000).toISOString(), expires_at: new Date(Date.now() + 30000).toISOString() }, sources: Object.fromEntries(['treasury', 'cob', 'oag', 'knbs', 'opendata', 'cra'].map(source => [source, { available: source === 'oag', reason: 'Inert source-specific qualification' }])) } }));
  send.mockResolvedValue({ status: 202, data: { ok: true, accepted: true, replayed: false, audit_recorded: true, command: { id: '33333333-3333-4333-8333-333333333333', source: 'oag', dry_run: true, status: 'queued', version: 1, created_at: '2026-11-04T03:00:00Z', updated_at: '2026-11-04T03:00:00Z', started_at: null, finished_at: null, job_id: null, outcome: null } } });
});
afterEach(() => { clients.splice(0).forEach(client => client.clear()); jest.restoreAllMocks(); });

test.each(['unreadable', 'corrupt'])('a %s journal visibly holds every new command without sending', async state => {
  if (state === 'unreadable') jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Read denied'); });
  else sessionStorage.setItem(storageKey, '{corrupt json');
  mount(); await screen.findByText(/Browser command recovery is unavailable/);
  expect(screen.getByRole('button', { name: 'Dry Run · oag' })).toBeDisabled();
  expect(send).not.toHaveBeenCalled(); expect(mockController).not.toHaveBeenCalled();
});

test.each(['denied', 'silently dropped'])('a journal write that is %s releases the controller and shows a held command', async state => {
  mount(); const button = await ready();
  jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { if (state === 'denied') throw new Error('Write denied'); });
  fireEvent.click(button); await screen.findByText(/Browser command recovery is unavailable/);
  await waitFor(() => expect(mockRelease).toHaveBeenCalledTimes(1));
  expect(mockController).toHaveBeenCalledTimes(1); expect(mockRelease.mock.calls[0][0]).toBe(mockController.mock.results[0].value);
  expect(send).not.toHaveBeenCalled(); expect(screen.queryByText('Requesting durable acceptance…')).toBeNull();
  expect(screen.getByRole('button', { name: 'Refresh worker evidence' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Recover same intent' })).toBeDisabled();
});

test.each(['denied', 'silently dropped'])('accepted work plus a %s journal clear keeps its accepted receipt without a second command', async state => {
  mount(); const button = await ready();
  jest.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { if (state === 'denied') throw new Error('Clear denied'); });
  fireEvent.click(button); await screen.findByText(/Browser recovery cleanup could not be confirmed/);
  await waitFor(() => expect(mockRelease).toHaveBeenCalledTimes(1));
  expect(send).toHaveBeenCalledTimes(1); expect(submittedIntent(actor)).not.toBeNull();
  expect(screen.getByText('Command accepted. Queued acceptance is not completed work.')).toBeVisible();
  const recover = screen.queryByRole('button', { name: 'Recover same intent' }); if (recover) expect(recover).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Dry Run · oag' })); expect(send).toHaveBeenCalledTimes(1);
});

test('a definite HTTP refusal plus failed clear preserves the original identity and releases resources', async () => {
  mount(); const button = await ready();
  send.mockRejectedValue({ isAxiosError: true, response: { status: 409 } });
  jest.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('Clear denied'); });
  fireEvent.click(button); await screen.findByText(/Browser command recovery is unavailable/);
  await waitFor(() => expect(mockRelease).toHaveBeenCalledTimes(1)); expect(send).toHaveBeenCalledTimes(1);
  expect(submittedIntent(actor)?.key).toBe(send.mock.calls[0][2].headers['Idempotency-Key']);
});

test('the ordinary accepted flow clears recovery, reports queue semantics and releases the exact controller', async () => {
  mount(); fireEvent.click(await ready()); await screen.findByText('Command accepted. Queued acceptance is not completed work.');
  expect(submittedIntent(actor)).toBeNull(); expect(mockRelease).toHaveBeenCalledTimes(1);
  expect(mockRelease.mock.calls[0][0]).toBe(mockController.mock.results[0].value);
  expect(screen.queryByText(/completed work successfully/i)).toBeNull();
});

test.each([
  { source: 'unregistered' }, { dry_run: 1 }, { key: [originalKey] }, { generation: [generation] },
  { generation: '' }, { key: null }, { dry_run: null },
])('malformed retained intent %# refuses without replacing its original bytes', patch => {
  const raw = JSON.stringify({ version: 1, actorId: actor, intents: [{ ...original, ...patch }] }); sessionStorage.setItem(storageKey, raw);
  expect(() => submittedIntent(actor)).toThrow(); expect(sessionStorage.getItem(storageKey)).toBe(raw);
});

test.each([{ version: true }, { version: 2 }, { actorId: generation }, { intents: {} }, { extra: true }])('malformed journal envelope %# refuses without loss', patch => {
  const raw = JSON.stringify({ version: 1, actorId: actor, intents: [original], ...patch }); sessionStorage.setItem(storageKey, raw);
  expect(() => submittedIntent(actor)).toThrow(); expect(sessionStorage.getItem(storageKey)).toBe(raw);
});

test('different semantic intents preserve siblings while a changed key cannot replace an unresolved original', () => {
  rememberSubmittedIntent(actor, original); const raw = sessionStorage.getItem(storageKey);
  expect(() => rememberSubmittedIntent(actor, { ...original, key: generation })).toThrow();
  expect(sessionStorage.getItem(storageKey)).toBe(raw);
  const sibling = { ...original, source: 'treasury' as const, key: generation };
  rememberSubmittedIntent(actor, sibling);
  expect(submittedIntent(actor, { source: 'oag', dry_run: true })).toEqual(original);
  expect(submittedIntent(actor, { source: 'treasury', dry_run: true })).toEqual(sibling);
  clearSubmittedIntent(actor, originalKey);
  expect(submittedIntent(actor, { source: 'oag', dry_run: true })).toBeNull();
  expect(submittedIntent(actor)).toEqual(sibling); expect(submittedIntent(generation)).toBeNull();
});

test('a committed journal clear with failed readback retains the already decoded acceptance in the UI', async () => {
  mount(); const button = await ready();
  const getItem = Storage.prototype.getItem, removeItem = Storage.prototype.removeItem; let denyReadback = false;
  jest.spyOn(Storage.prototype, 'removeItem').mockImplementation(function (this: Storage, key) { removeItem.call(this, key); denyReadback = true; });
  jest.spyOn(Storage.prototype, 'getItem').mockImplementation(function (this: Storage, key) {
    if (denyReadback) { denyReadback = false; throw new Error('Readback unavailable after successful clear'); }
    return getItem.call(this, key);
  });
  fireEvent.click(button); await screen.findByText(/Browser recovery cleanup could not be confirmed/);
  await waitFor(() => expect(mockRelease).toHaveBeenCalledTimes(1));
  expect(send).toHaveBeenCalledTimes(1); expect(submittedIntent(actor)).toBeNull();
  expect(screen.getByText('Command accepted. Queued acceptance is not completed work.')).toBeVisible();
  expect(screen.getByRole('link', { name: 'View accepted command' })).toHaveAttribute('href', '/admin/etl/commands/33333333-3333-4333-8333-333333333333');
});
