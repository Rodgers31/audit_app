import api from '@/lib/api/axios';
import { SocialPost } from '@/lib/api/social';
import { socialKeys, useSocialDeliveryStatus, useSocialPost } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import { actorId, post, target } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
const get = api.get as jest.Mock;
function Observer({ id }: { id: string }) {
  const full = useSocialPost(id); useSocialDeliveryStatus(full.data);
  return <p>{full.data?.document.master.text ?? 'loading'} · {full.data?.targets[0]?.state}</p>;
}
beforeEach(() => { jest.clearAllMocks(); Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' }); });
afterEach(() => jest.useRealTimers());
test('active timer polls compact summaries, retains the document, and stops hidden or terminal', async () => {
  jest.useFakeTimers();
  const p = post({ targets: [target('queued')] }); let compact = { ...p, document: undefined, references: undefined };
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/status') ? compact : p }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><Observer id={p.id} /></QueryClientProvider>);
  await screen.findByText(/Read the finding.*queued/);
  await waitFor(() => expect(get.mock.calls.filter(c => c[0].endsWith('/status'))).toHaveLength(1));
  await act(async () => { jest.advanceTimersByTime(15_001); });
  expect(get.mock.calls.filter(c => c[0].endsWith('/status'))).toHaveLength(2);
  expect(get.mock.calls.filter(c => !c[0].endsWith('/status'))).toHaveLength(1);
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
  act(() => { document.dispatchEvent(new Event('visibilitychange')); });
  await act(async () => { jest.advanceTimersByTime(60_000); });
  expect(get.mock.calls.filter(c => c[0].endsWith('/status'))).toHaveLength(2);
  compact = { ...compact, targets: [target('published')] };
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  await act(async () => { document.dispatchEvent(new Event('visibilitychange')); });
  await act(async () => { jest.advanceTimersByTime(100); });
  expect(qc.getQueryData<SocialPost>(socialKeys.detail(actorId, p.id))!.targets[0].state).toBe('published');
  const calls = get.mock.calls.length;
  await act(async () => { jest.advanceTimersByTime(60_000); });
  expect(get).toHaveBeenCalledTimes(calls);
  expect(get.mock.calls.filter(c => !c[0].endsWith('/status'))).toHaveLength(1);
});
test('a new compact version refreshes detail once without merging a new version onto the old document', async () => {
  const p = post({ targets: [target('queued')] });
  const next = post({ version: 2, targets: [target('queued')], document: { ...p.document, master: { ...p.document.master, text: 'Authoritative new revision' } } });
  let detailReads = 0;
  get.mockImplementation(async (path: string) => {
    if (path.endsWith('/status')) return { data: { ...next, document: undefined, references: undefined } };
    detailReads++; return { data: detailReads === 1 ? p : next };
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><Observer id={p.id} /></QueryClientProvider>);
  await screen.findByText(/Authoritative new revision/);
  expect(detailReads).toBe(2);
  jest.useFakeTimers();
  await act(async () => { jest.advanceTimersByTime(30_000); });
  expect(detailReads).toBe(2);
  const cached = qc.getQueryData<SocialPost>(socialKeys.detail(actorId, p.id));
  expect(cached?.version).toBe(2); expect(cached?.document.master.text).toBe('Authoritative new revision');
});
