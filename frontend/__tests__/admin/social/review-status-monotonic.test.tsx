import { SocialErrorBanner } from '@/components/admin/social/SocialNotice';
import api from '@/lib/api/axios';
import { decodePublication, SocialPost, SocialSummary } from '@/lib/api/social';
import { socialKeys, useSocialDeliveryStatus, useSocialMutation, useSocialPost } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { actorId, assetId, post, target } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
let mockActor = '00000000-0000-4000-8000-000000000001';
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: mockActor } }) }));

const get = api.get as jest.Mock;
const clients: QueryClient[] = [];
const nextRevision = '00000000-0000-4000-8000-000000000041';
function summary(p: SocialPost): SocialSummary {
  const { document: _document, references: _references, ...compact } = p;
  return compact;
}
function client() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  clients.push(qc); return qc;
}
function Observer({ id }: { id: string }) {
  const full = useSocialPost(id);
  const status = useSocialDeliveryStatus(full.data);
  return <div><p>{full.data?.document.master.text ?? 'Loading'} · {full.data?.targets[0]?.state}</p>
    {status.error && <SocialErrorBanner error={status.error} />}
    <button onClick={() => void status.refetch()}>Retry status</button></div>;
}
function mount(p: SocialPost, qc = client()) {
  qc.setQueryData(socialKeys.detail(mockActor, p.id), p);
  return { qc, ...render(<QueryClientProvider client={qc}><Observer id={p.id} /></QueryClientProvider>) };
}
function statusReads() { return get.mock.calls.filter(c => c[0].endsWith('/status')).length; }
function detailReads() { return get.mock.calls.filter(c => !c[0].endsWith('/status')).length; }
async function advance(ms = 15_001) { await act(async () => { jest.advanceTimersByTime(ms); }); }

beforeEach(() => {
  jest.clearAllMocks(); mockActor = actorId; jest.useFakeTimers();
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
});
afterEach(() => { cleanup(); clients.splice(0).forEach(qc => qc.clear()); jest.useRealTimers(); });

test.each(['queued', 'failed'] as const)('compact version older than full detail is a visible error even with %s targets, and stops polling', async state => {
  const full = post({ version: 2, revision_id: nextRevision, targets: [target('processing')] });
  const old = post({ version: 1, targets: [target(state)] });
  get.mockResolvedValue({ data: summary(old) });
  const { qc } = mount(full);
  await waitFor(() => expect(statusReads()).toBe(1));
  await screen.findByRole('alert');
  expect(screen.getByRole('alert')).toHaveTextContent('INVALID RESPONSE');
  expect(qc.getQueryData(socialKeys.detail(actorId, full.id))).toEqual(full);
  await advance(90_000);
  expect(statusReads()).toBe(1); expect(detailReads()).toBe(0);
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
  act(() => { document.dispatchEvent(new Event('visibilitychange')); });
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  act(() => { document.dispatchEvent(new Event('visibilitychange')); });
  await advance(90_000);
  expect(statusReads()).toBe(1);
});

test('compact version 2 then version 1 is rejected while the version-2 full refresh is pending', async () => {
  const original = post({ targets: [target('queued')] });
  const next = post({ version: 2, revision_id: nextRevision, targets: [target('processing')], document: { ...original.document, master: { ...original.document.master, text: 'Full version two content' } } });
  let resolveFull!: (value: { data: SocialPost }) => void;
  const fullRefresh = new Promise<{ data: SocialPost }>(resolve => { resolveFull = resolve; });
  let reads = 0;
  get.mockImplementation(async path => {
    if (path.endsWith('/status')) return { data: summary(++reads === 1 ? next : post({ targets: [target('failed')] })) };
    return fullRefresh;
  });
  const { qc } = mount(original);
  await waitFor(() => expect(detailReads()).toBe(1));
  expect(qc.getQueryData(socialKeys.detail(actorId, original.id))).toEqual(original);
  await advance();
  await screen.findByRole('alert');
  expect(qc.getQueryData(socialKeys.detail(actorId, original.id))).toEqual(original);
  expect(qc.getQueryData<SocialSummary>(socialKeys.status(actorId, original.id))?.version).toBe(2);
  await advance(90_000);
  expect(statusReads()).toBe(2); expect(detailReads()).toBe(1);
  await act(async () => { resolveFull({ data: next }); });
  await screen.findByText(/Full version two content.*processing/);
  expect(screen.getByRole('alert')).toHaveTextContent('INVALID RESPONSE');
  expect(qc.getQueryData(socialKeys.detail(actorId, original.id))).toEqual(next);
  await advance(60_000); expect(statusReads()).toBe(2);
});

test('same-version wrong revision is visible, cannot overwrite results, and stops requests', async () => {
  const full = post({ targets: [target('processing')] });
  get.mockResolvedValue({ data: { ...summary(full), revision_id: nextRevision, targets: [target('published')] } });
  const { qc } = mount(full);
  await screen.findByRole('alert');
  expect(qc.getQueryData(socialKeys.detail(actorId, full.id))).toEqual(full);
  await advance(90_000); expect(statusReads()).toBe(1); expect(detailReads()).toBe(0);
});

test('a status request started at version 1 must respect a newer full version when its response arrives', async () => {
  const original = post({ targets: [target('queued')] });
  const current = post({ version: 2, revision_id: nextRevision, targets: [target('processing')] });
  let resolveStatus!: (value: { data: SocialSummary }) => void;
  get.mockImplementation(() => new Promise<{ data: SocialSummary }>(resolve => { resolveStatus = resolve; }));
  const { qc } = mount(original);
  await waitFor(() => expect(statusReads()).toBe(1));
  await act(async () => { qc.setQueryData(socialKeys.detail(actorId, original.id), current); });
  await act(async () => { resolveStatus({ data: summary(post({ targets: [target('failed')] })) }); });
  await screen.findByRole('alert');
  expect(qc.getQueryData(socialKeys.detail(actorId, original.id))).toEqual(current);
  await advance(90_000); expect(statusReads()).toBe(1);
});

test('a second compact version 2 with a different revision cannot replace the first accepted version 2', async () => {
  const original = post({ targets: [target('queued')] });
  const next = post({ version: 2, revision_id: nextRevision, targets: [target('processing')] });
  let reads = 0;
  get.mockImplementation(async path => path.endsWith('/status') ? { data: { ...summary(next), ...(++reads === 1 ? {} : { revision_id: assetId, targets: [target('failed')] }) } } : new Promise(() => undefined));
  const { qc } = mount(original);
  await waitFor(() => expect(detailReads()).toBe(1));
  await advance();
  await screen.findByRole('alert');
  expect(qc.getQueryData<SocialSummary>(socialKeys.status(actorId, original.id))?.revision_id).toBe(nextRevision);
  expect(qc.getQueryData(socialKeys.detail(actorId, original.id))).toEqual(original);
  await advance(90_000); expect(statusReads()).toBe(2);
});

test('a new compact version fetches full detail only once and never overlays its version on the old document', async () => {
  const original = post({ targets: [target('queued')] });
  const next = post({ version: 2, revision_id: nextRevision, targets: [target('processing')], document: { ...original.document, master: { ...original.document.master, text: 'New exact full document' } } });
  let resolveFull!: (value: { data: SocialPost }) => void;
  const fullRefresh = new Promise<{ data: SocialPost }>(resolve => { resolveFull = resolve; });
  get.mockImplementation(async path => path.endsWith('/status') ? { data: summary(next) } : fullRefresh);
  const { qc } = mount(original);
  await waitFor(() => expect(detailReads()).toBe(1));
  await advance(); await advance();
  expect(detailReads()).toBe(1); expect(statusReads()).toBe(3);
  expect(qc.getQueryData(socialKeys.detail(actorId, original.id))).toEqual(original);
  await act(async () => { resolveFull({ data: next }); });
  await screen.findByText(/New exact full document.*processing/);
  await advance(); expect(detailReads()).toBe(1); expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

test('a stale-status failure stays stopped across rerenders and explicit retry can recover polling', async () => {
  const full = post({ version: 2, revision_id: nextRevision, targets: [target('processing')] });
  let compact = summary(post({ targets: [target('failed')] }));
  get.mockImplementation(async () => ({ data: compact }));
  const { qc, rerender } = mount(full);
  await screen.findByRole('alert');
  rerender(<QueryClientProvider client={qc}><Observer id={full.id} /></QueryClientProvider>);
  await advance(90_000); expect(statusReads()).toBe(1);
  compact = summary(full);
  fireEvent.click(screen.getByRole('button', { name: 'Retry status' }));
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  expect(statusReads()).toBe(2);
  await advance(); expect(statusReads()).toBe(3); expect(detailReads()).toBe(0);
});

test('a pending newer-version refresh for one actor cannot suppress the same version refresh for another actor', async () => {
  const originalA = post({ targets: [target('queued')] });
  const originalB = post({ targets: [target('processing')] });
  const nextA = post({ version: 2, revision_id: nextRevision, targets: [target('processing')] });
  const nextB = post({ ...nextA, document: { ...nextA.document, master: { ...nextA.document.master, text: 'Second actor exact revision' } } });
  let resolveA!: (value: { data: SocialPost }) => void;
  const pendingA = new Promise<{ data: SocialPost }>(resolve => { resolveA = resolve; });
  get.mockImplementation(async path => {
    if (path.endsWith('/status')) return { data: summary(mockActor === actorId ? nextA : nextB) };
    return mockActor === actorId ? pendingA : { data: nextB };
  });
  const qc = client(); qc.setQueryData(socialKeys.detail(assetId, originalB.id), originalB);
  const { rerender } = mount(originalA, qc);
  await waitFor(() => expect(detailReads()).toBe(1));
  mockActor = assetId;
  rerender(<QueryClientProvider client={qc}><Observer id={originalA.id} /></QueryClientProvider>);
  await screen.findByText(/Second actor exact revision/);
  expect(detailReads()).toBe(2);
  expect(qc.getQueryData<SocialPost>(socialKeys.detail(actorId, originalA.id))?.version).toBe(1);
  expect(qc.getQueryData<SocialPost>(socialKeys.detail(assetId, originalA.id))?.version).toBe(2);
  await act(async () => { resolveA({ data: nextA }); });
  // Removing the first actor's observer cancels its detail query. A late
  // response must neither migrate into the second scope nor undo its result.
  expect(qc.getQueryData<SocialPost>(socialKeys.detail(actorId, originalA.id))?.version).toBe(1);
  expect(qc.getQueryData<SocialPost>(socialKeys.detail(assetId, originalA.id))?.document.master.text).toBe('Second actor exact revision');
});

test('one actor stale compact error does not poison a different actor with a lower valid version', async () => {
  const first = post({ version: 2, revision_id: nextRevision, targets: [target('queued')] });
  const second = post({ targets: [target('processing')] });
  get.mockImplementation(async () => ({ data: summary(second) }));
  const qc = client(); qc.setQueryData(socialKeys.detail(assetId, second.id), second);
  const { rerender } = mount(first, qc);
  await screen.findByRole('alert');
  mockActor = assetId;
  rerender(<QueryClientProvider client={qc}><Observer id={first.id} /></QueryClientProvider>);
  await screen.findByText(/Read the finding.*processing/);
  await waitFor(() => expect(qc.getQueryData(socialKeys.status(assetId, first.id))).toBeDefined());
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  await advance(); expect(statusReads()).toBe(3);
  expect(qc.getQueryState(socialKeys.status(actorId, first.id))?.error).toMatchObject({ code: 'INVALID_RESPONSE' });
  expect(qc.getQueryState(socialKeys.status(assetId, first.id))?.error).toBeNull();
});

test('an accepted resume command refreshes the actor-scoped system and delivery caches', async () => {
  const p = post(), queued = target('queued');
  const qc = client(), invalidate = jest.spyOn(qc, 'invalidateQueries');
  Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => '00000000-0000-4000-8000-000000000099' });
  (api.post as jest.Mock).mockResolvedValue({ data: {
    post_id: p.id, publication_id: '00000000-0000-4000-8000-000000000060', status: 'queued', scheduled_for: null,
    status_url: `/api/v1/admin/social/posts/${p.id}/status`,
    targets: [{ id: queued.id, account_id: queued.account_id, platform: queued.platform, status: 'queued' }],
  } });
  function Wrapper({ children }: { children: React.ReactNode }) { return <QueryClientProvider client={qc}>{children}</QueryClientProvider>; }
  const { result } = renderHook(() => useSocialMutation(), { wrapper: Wrapper });
  await act(async () => { await result.current.run(`/posts/${p.id}/resume`, { expected_version: p.version }, decodePublication, { postId: p.id }); });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: [...socialKeys.root(actorId), 'system'], exact: true });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: socialKeys.detail(actorId, p.id), exact: true });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: socialKeys.status(actorId, p.id), exact: true });
  invalidate.mockRestore();
});
