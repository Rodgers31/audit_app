import api from '@/lib/api/axios';
import { decodeControls, decodeDocument, decodePost, decodePublication, decodeSummary, decodeSystem, decodeValidation, SocialApiError, SocialPost, SocialSummary, socialApi, toSocialError } from '@/lib/api/social';
import { socialKeys, useSocialDeliveryStatus, useSocialPost } from '@/lib/hooks/useSocial';
import { SocialSystemStrip } from '@/components/admin/social/SocialWorkspace';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { accounts, actorId, assetId, post, system, target } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
let mockActor = '00000000-0000-4000-8000-000000000001';
let mockAdmin = true;
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: mockAdmin }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: mockActor } }) }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }) }));

const get = api.get as jest.Mock;
const clients: QueryClient[] = [];
const hostileNumbers = [undefined, null, true, false, '1', {}, [], NaN, Infinity, -Infinity, -1, 1.5];
function client() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } });
  clients.push(qc); return qc;
}
function summary(p: SocialPost): SocialSummary {
  const { document: _document, references: _references, publication: _publication, ...compact } = p;
  return compact;
}
function Observer({ id }: { id: string }) {
  const full = useSocialPost(id);
  const delivery = useSocialDeliveryStatus(full.data);
  return <p>{full.data?.document.master.text ?? 'loading'} · {full.data?.targets[0]?.state ?? 'no targets'} · {delivery.error?.message ?? 'no error'}</p>;
}
function mountObserver(id: string, qc = client()) {
  return { qc, ...render(<QueryClientProvider client={qc}><Observer id={id} /></QueryClientProvider>) };
}
beforeEach(() => {
  jest.clearAllMocks(); mockActor = actorId; mockAdmin = true;
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
});
afterEach(() => { cleanup(); clients.splice(0).forEach(qc => qc.clear()); jest.useRealTimers(); });

test.each([decodeControls, decodeDocument, decodePost, decodePublication, decodeSummary, decodeSystem, decodeValidation])('%p rejects missing, null, empty, scalar and malformed DTOs', decode => {
  for (const value of [undefined, null, '', 'success', 1, true, [], {}, { success: true }]) {
    expect(() => decode(value)).toThrow(SocialApiError);
  }
});

test('numeric version and count fields reject booleans, nonnumeric, NaN, infinity, negative and fractional values', async () => {
  for (const value of hostileNumbers) {
    expect(() => decodeSummary({ ...post(), version: value })).toThrow(SocialApiError);
    expect(() => decodeSystem({ ...system, controls_version: value })).toThrow(SocialApiError);
    expect(() => decodeSystem({ ...system, queue_counts: { queued: value } })).toThrow(SocialApiError);
    get.mockResolvedValue({ data: { posts: [], total: value, page: 1, page_size: 20, has_more: false } });
    await expect(socialApi.posts(1)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    get.mockResolvedValue({ data: { accounts: [{ ...accounts[0], capabilities: { ...accounts[0].capabilities, limits: { max_text_length: value } } }] } });
    // Null is the documented unknown capability limit; absence is malformed.
    if (value === null) await expect(socialApi.accounts()).resolves.toHaveLength(1);
    else await expect(socialApi.accounts()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  }
  expect(() => decodeSummary({ ...post(), version: 0 })).toThrow(SocialApiError);
  expect(decodeSystem({ ...system, queue_counts: { queued: 0 } }).queue_counts.queued).toBe(0);
});

test('versions do not accept integers that JavaScript cannot represent exactly', () => {
  expect(() => decodeSummary({ ...post(), version: Number.MAX_SAFE_INTEGER + 1 })).toThrow(SocialApiError);
});

test('unknown document schemas, target states, platforms and formats never become valid defaults', () => {
  for (const schema_version of [undefined, null, true, '1', 0, 2, NaN, Infinity]) {
    expect(() => decodeDocument({ ...post().document, schema_version })).toThrow(SocialApiError);
  }
  expect(() => decodeSummary({ ...post(), editorial_state: 'auto_approved' })).toThrow(SocialApiError);
  expect(() => decodeSummary({ ...post(), targets: [{ ...target('ready'), state: 'successful' }] })).toThrow(SocialApiError);
  expect(() => decodeSummary({ ...post(), targets: [{ ...target('ready'), platform: 'linkedin' }] })).toThrow(SocialApiError);
  expect(() => decodeDocument({ ...post().document, targets: [{ ...post().document.targets[0], format: 'story' }] })).toThrow(SocialApiError);
  expect(() => decodeDocument({ ...post().document, targets: [{ ...post().document.targets[0], overrides: { text: { mode: 'inherit', value: 'oops' } } }] })).toThrow(SocialApiError);
});

test('nullable API-shaped fields are accepted, while unsupported nullable content still fails', () => {
  const p = post();
  p.references = [{ url: 'https://example.org/source', label: null }];
  p.document.master.media = [{ asset_id: assetId, alt_text: null, caption_asset_id: null }];
  expect(decodePost(p).references[0].label).toBeNull();
  expect(decodePost(p).document.master.media[0].alt_text).toBeNull();
  expect(decodeValidation({ valid: false, rules_version: 'social-v1', errors: [], warnings: [], targets: [{ account_id: p.document.targets[0].account_id, platform: null, valid: false, errors: [], warnings: [], resolved_preview: null }] }).targets[0].platform).toBeNull();
  expect(() => decodeDocument({ ...p.document, master: { ...p.document.master, text: null } })).toThrow(SocialApiError);
  expect(() => decodeDocument({ ...p.document, master: { ...p.document.master, media: null } })).toThrow(SocialApiError);
});

test('real empty collections are accepted, while absent collections and failures remain errors', async () => {
  get.mockResolvedValueOnce({ data: { accounts: [] } }).mockResolvedValueOnce({ data: {} }).mockRejectedValueOnce({ isAxiosError: true, response: { status: 503, data: { detail: { code: 'SOCIAL_SCHEMA_UNAVAILABLE', message: 'Apply the migration.', field_errors: [], target_errors: [], retryable: false, request_id: actorId } } } });
  await expect(socialApi.accounts()).resolves.toEqual([]);
  await expect(socialApi.accounts()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  await expect(socialApi.accounts()).rejects.toMatchObject({ code: 'SOCIAL_SCHEMA_UNAVAILABLE' });
  get.mockResolvedValue({ data: { posts: [], total: 0, page: 1, page_size: 20, has_more: false } });
  await expect(socialApi.posts(1)).resolves.toMatchObject({ posts: [], total: 0, has_more: false });
  expect(toSocialError({ isAxiosError: true })).toMatchObject({ code: 'NETWORK_ERROR', retryable: true });
  expect(toSocialError({ isAxiosError: true, response: { status: 401, data: {} } })).toMatchObject({ code: 'ACCESS_DENIED' });
  expect(toSocialError({ success: false, message: 'failure' })).toMatchObject({ code: 'SOCIAL_UNAVAILABLE' });
});

test('compact active polling remains bounded, preserves documents, and stops on malformed responses', async () => {
  jest.useFakeTimers();
  const p = post({ targets: [target('queued')] });
  let bad = false;
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/status') ? bad ? { ...summary(p), version: false } : summary(p) : p }));
  mountObserver(p.id);
  await screen.findByText(/Read the finding.*queued/);
  await waitFor(() => expect(get.mock.calls.filter(c => c[0].endsWith('/status'))).toHaveLength(1));
  for (let i = 0; i < 3; i++) await act(async () => { jest.advanceTimersByTime(15_001); });
  expect(get.mock.calls.filter(c => c[0].endsWith('/status'))).toHaveLength(4);
  expect(get.mock.calls.filter(c => !c[0].endsWith('/status'))).toHaveLength(1);
  bad = true;
  await act(async () => { jest.advanceTimersByTime(15_001); });
  await screen.findByText(/unexpected response/);
  const afterFailure = get.mock.calls.length;
  await act(async () => { jest.advanceTimersByTime(120_000); });
  expect(get).toHaveBeenCalledTimes(afterFailure);
  expect(screen.getByText(/Read the finding.*queued/)).toBeInTheDocument();
});

test('terminal and hidden posts do not generate timer requests, and old compact versions cannot overwrite new detail', async () => {
  jest.useFakeTimers();
  const p = post({ version: 2, targets: [target('queued')] });
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/status') ? summary(post({ version: 1, targets: [target('failed')] })) : p }));
  const { qc } = mountObserver(p.id);
  await screen.findByText(/Read the finding.*queued/);
  await waitFor(() => expect(get.mock.calls.filter(c => c[0].endsWith('/status'))).toHaveLength(1));
  expect(qc.getQueryData<SocialPost>(socialKeys.detail(actorId, p.id))?.targets[0].state).toBe('queued');
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
  act(() => { document.dispatchEvent(new Event('visibilitychange')); });
  const beforeHidden = get.mock.calls.length;
  await act(async () => { jest.advanceTimersByTime(120_000); });
  expect(get).toHaveBeenCalledTimes(beforeHidden);
  cleanup(); qc.clear(); get.mockClear();
  const terminal = post({ targets: [target('outcome_unknown')] });
  get.mockResolvedValue({ data: terminal });
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  mountObserver(terminal.id);
  await screen.findByText(/outcome_unknown/);
  await act(async () => { jest.advanceTimersByTime(120_000); });
  expect(get).toHaveBeenCalledTimes(1);
});

test('a compact summary with the same version but a different revision cannot mutate authoritative detail', async () => {
  const p = post({ targets: [target('queued')] });
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/status') ? { ...summary(p), revision_id: assetId, targets: [target('published')] } : p }));
  const { qc } = mountObserver(p.id);
  await screen.findByText(/Read the finding/);
  await waitFor(() => expect(get.mock.calls.filter(c => c[0].endsWith('/status'))).toHaveLength(1));
  expect(qc.getQueryData<SocialPost>(socialKeys.detail(actorId, p.id))?.targets[0].state).toBe('queued');
});

test('admin identity changes scope reads and cached detail to the current actor', async () => {
  const first = post({ document: { ...post().document, master: { ...post().document.master, text: 'First actor document' } } });
  const second = post({ document: { ...post().document, master: { ...post().document.master, text: 'Second actor document' } } });
  get.mockImplementation(async () => ({ data: mockActor === actorId ? first : second }));
  const { qc, rerender } = mountObserver(first.id);
  await screen.findByText(/First actor document/);
  mockActor = assetId;
  rerender(<QueryClientProvider client={qc}><Observer id={first.id} /></QueryClientProvider>);
  await screen.findByText(/Second actor document/);
  expect(qc.getQueryData<SocialPost>(socialKeys.detail(actorId, first.id))?.document.master.text).toBe('First actor document');
  expect(qc.getQueryData<SocialPost>(socialKeys.detail(assetId, first.id))?.document.master.text).toBe('Second actor document');
  mockAdmin = false; get.mockClear();
  rerender(<QueryClientProvider client={qc}><Observer id={first.id} /></QueryClientProvider>);
  expect(get).not.toHaveBeenCalled();
});

test.each([null, '2026-10-03T11:00:00Z', '2026-10-03T13:00:00Z', 'not-a-time'])('absent, stale, future and malformed heartbeat %p never certify health', heartbeat_at => {
  jest.useFakeTimers({ now: new Date('2026-10-03T12:00:00Z') });
  const qc = client();
  render(<QueryClientProvider client={qc}><SocialSystemStrip status={{ ...system, worker: { state: 'healthy', heartbeat_at, last_scan_at: null } }} refresh={jest.fn()} /></QueryClientProvider>);
  expect(screen.queryByText('Worker: healthy')).not.toBeInTheDocument();
  expect(screen.getByText(/Worker (health unavailable|heartbeat stale or unavailable)/)).toBeInTheDocument();
});

test('a once-fresh heartbeat becomes stale while the page is idle', async () => {
  jest.useFakeTimers({ now: new Date('2026-10-03T12:00:00Z') });
  const qc = client();
  render(<QueryClientProvider client={qc}><SocialSystemStrip status={{ ...system, worker: { state: 'healthy', heartbeat_at: '2026-10-03T12:00:00Z', last_scan_at: null } }} refresh={jest.fn()} /></QueryClientProvider>);
  expect(screen.getByText('Worker: healthy')).toBeInTheDocument();
  await act(async () => { jest.advanceTimersByTime(195_001); });
  expect(screen.queryByText('Worker: healthy')).not.toBeInTheDocument();
  expect(screen.getByText('Worker heartbeat stale or unavailable')).toBeInTheDocument();
});
