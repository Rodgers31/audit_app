import api from '@/lib/api/axios';
import { decodePost, SocialPost } from '@/lib/api/social';
import { socialKeys, useSocialDeliveryStatus, useSocialMutation, useSocialPost } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, render, renderHook, screen, waitFor } from '@testing-library/react';
import { actorId, assetId, post, target } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
let mockActor = '00000000-0000-4000-8000-000000000001';
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: mockActor } }) }));
const get = api.get as jest.Mock;
const send = api.post as jest.Mock;
const clients: QueryClient[] = [];
function client() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } });
  clients.push(qc); return qc;
}
function Observer({ id }: { id: string }) {
  const full = useSocialPost(id);
  const delivery = useSocialDeliveryStatus(full.data);
  return <p>{full.data?.targets[0]?.state ?? 'loading'} · {delivery.error?.message ?? 'no error'}</p>;
}
beforeEach(() => {
  jest.clearAllMocks(); mockActor = actorId;
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => '00000000-0000-4000-8000-000000000099' });
});
afterEach(() => { cleanup(); clients.splice(0).forEach(qc => qc.clear()); jest.useRealTimers(); });

test('wrong-post compact status is a visible contract error rather than silently stopping another active post', async () => {
  jest.useFakeTimers();
  const p = post({ targets: [target('queued')] });
  const wrong = { ...p, id: assetId, targets: [target('published')] };
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/status') ? wrong : p }));
  const qc = client();
  render(<QueryClientProvider client={qc}><Observer id={p.id} /></QueryClientProvider>);
  await screen.findByText(/queued/);
  await waitFor(() => expect(get.mock.calls.filter(c => c[0].endsWith('/status'))).toHaveLength(1));
  expect(qc.getQueryData<SocialPost>(socialKeys.detail(actorId, p.id))?.targets[0].state).toBe('queued');
  await act(async () => { jest.advanceTimersByTime(60_000); });
  expect(screen.queryByText(/no error/)).not.toBeInTheDocument();
});

test('in-flight mutation completion cannot populate a different actor cache after the admin identity changes', async () => {
  const qc = client();
  let resolveResponse!: (value: { data: SocialPost }) => void;
  send.mockImplementation(() => new Promise<{ data: SocialPost }>(resolve => { resolveResponse = resolve; }));
  const p = post();
  function Wrapper({ children }: { children: React.ReactNode }) { return <QueryClientProvider client={qc}>{children}</QueryClientProvider>; }
  const { result, rerender } = renderHook(() => useSocialMutation(), { wrapper: Wrapper });
  let pending!: Promise<SocialPost>;
  act(() => { pending = result.current.run('/posts', { title: p.title, content_type: p.content_type, document: p.document, references: p.references }, decodePost); });
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  mockActor = assetId;
  rerender();
  await act(async () => { resolveResponse({ data: p }); await pending; });
  expect(qc.getQueryData(socialKeys.detail(assetId, p.id))).toBeUndefined();
});
