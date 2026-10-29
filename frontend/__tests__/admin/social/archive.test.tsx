import SocialComposer from '@/components/admin/social/SocialComposer';
import SocialWorkspace, { SocialEditorPage } from '@/components/admin/social/SocialWorkspace';
import api from '@/lib/api/axios';
import { decodePost, SocialPost } from '@/lib/api/social';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { actorId, post, system } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
const push = jest.fn();
jest.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
const get = api.get as jest.Mock, send = api.post as jest.Mock;
const retained = 'Archived history is retained read-only. Duplicate as a new manual draft to recover content; fresh review and authorization are required. No remote post was deleted.';
function fixture(): SocialPost { return post({ archive: { eligible: true, archived_at: null, message: 'Archive keeps all evidence. No remote post is deleted.' } }); }
function archived(p: SocialPost): SocialPost { return { ...p, version: p.version + 1, editorial_state: 'archived', archive: { eligible: false, archived_at: '2026-10-18T12:00:00Z', message: retained } }; }
function mount(p = fixture()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  qc.setQueryData(socialKeys.detail(actorId, p.id), p);
  return render(<QueryClientProvider client={qc}><SocialComposer initialPost={p} accounts={[]} system={{ ...system, publishing_enabled: false }} onSaved={push} /></QueryClientProvider>);
}
beforeEach(() => { jest.clearAllMocks(); Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => '00000000-0000-4000-8000-000000000727' }); get.mockResolvedValue({ data: fixture() }); });

test('confirmation archives without save/queue calls and preserves read-only recovery', async () => {
  const p = fixture(); send.mockResolvedValue({ data: archived(p) }); mount(p);
  fireEvent.click(screen.getByRole('button', { name: 'Archive post' })); expect(send).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Confirm archive' })); await screen.findByText(retained);
  expect(send).toHaveBeenCalledTimes(1); expect(send.mock.calls[0][0]).toBe(`/admin/social/posts/${p.id}/archive`);
  expect(send.mock.calls[0][1]).toEqual({ expected_version: 1 }); expect(api.patch).not.toHaveBeenCalled();
  expect(screen.getByLabelText('Draft title')).toBeDisabled();
  expect(screen.queryByRole('button', { name: 'Publish now' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Cancel unsent deliveries' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Duplicate as new manual draft' })).toBeEnabled();
});

test('ambiguous retry retains version/key and invalid receipt preserves original', async () => {
  const p = fixture(); send.mockRejectedValueOnce(new Error('connection lost')).mockResolvedValue({ data: { ...archived(p), revision_id: actorId } }); mount(p);
  fireEvent.click(screen.getByRole('button', { name: 'Archive post' })); fireEvent.click(screen.getByRole('button', { name: 'Confirm archive' }));
  await screen.findByRole('alert'); fireEvent.click(screen.getByRole('button', { name: 'Confirm archive' }));
  await screen.findByText(/archive receipt did not confirm/);
  expect(send).toHaveBeenCalledTimes(2); expect(send.mock.calls[0]).toEqual(send.mock.calls[1]);
  expect(screen.getByLabelText('Draft title')).toBeEnabled();
});

test('unsafe eligibility explains independent cancellation', () => {
  const p = fixture(); p.archive = { eligible: false, archived_at: null, message: 'Use independent cancellation or reconciliation before archive.' }; mount(p);
  fireEvent.click(screen.getByText('More draft actions')); expect(screen.getByRole('button', { name: 'Archive post' })).toBeDisabled(); expect(screen.getByText(/Use independent cancellation/)).toBeVisible();
});

test('local edits cannot be implicitly saved by archive', () => {
  mount(); fireEvent.change(screen.getByLabelText('Draft title'), { target: { value: 'Unsaved title' } });
  expect(screen.getByRole('button', { name: 'Archive post' })).toBeDisabled(); expect(send).not.toHaveBeenCalled();
});

test('Archived queue fetches explicit state filter', async () => {
  get.mockImplementation(async (path: string) => ({ data: path.includes('/system/') ? { ...system, publishing_enabled: false } : path.endsWith('/accounts') ? { accounts: [] } : { posts: [], total: 0, page: 1, page_size: 20, has_more: false } }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><SocialWorkspace /></QueryClientProvider>);
  fireEvent.click(screen.getByText('Filter & history')); fireEvent.change(screen.getByLabelText('View'), { target: { value: 'archived' } });
  await waitFor(() => expect(get.mock.calls.some(([path, options]) => path === '/admin/social/posts' && options.params.editorial_state === 'archived')).toBe(true));
});

test.each([null, {}, { eligible: 'true', archived_at: null, message: 'x' }, { eligible: true, archived_at: '2026-10-18T12:00:00Z', message: 'x' }])('malformed archive metadata fails closed: %p', archive => {
  expect(() => decodePost({ ...fixture(), archive })).toThrow();
});

test('pending archive disables editing and sibling commands until its receipt settles', async () => {
  const p = fixture(); let settle!: (value: { data: SocialPost }) => void;
  send.mockImplementation(() => new Promise(resolve => { settle = resolve; })); mount(p);
  fireEvent.click(screen.getByRole('button', { name: 'Archive post' })); fireEvent.click(screen.getByRole('button', { name: 'Confirm archive' }));
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  expect(screen.getByLabelText('Draft title')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Submit for review' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Duplicate as new manual draft' })).toBeDisabled();
  settle({ data: archived(p) }); await screen.findByText(retained);
});

test('legacy archived history without a timestamp remains visible and read-only', () => {
  const p = { ...fixture(), editorial_state: 'archived', archive: { eligible: false, archived_at: null, message: retained } };
  expect(decodePost(p).archive?.archived_at).toBeNull();
  mount(decodePost(p));
  expect(screen.getByLabelText('Draft title')).toBeDisabled();
  expect(screen.getByRole('heading', { name: 'Archived history' })).toBeVisible();
  expect(screen.getByRole('button', { name: 'Duplicate as new manual draft' })).toBeEnabled();
});


test('valid eligible draft metadata is accepted and remains editable', () => {
  const p = fixture(); p.archive = { eligible: true, archived_at: null, message: 'x' };
  expect(decodePost(p)).toEqual(p);
  mount(decodePost(p));
  expect(screen.getByLabelText('Draft title')).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Archive post' })).toBeEnabled();
});


test.each(['draft', 'pending_review', 'approved', 'rejected'] as const)('a timestamp cannot contradict non-archived state %s for either eligibility', editorial_state => {
  for (const eligible of [false, true]) {
    expect(() => decodePost({ ...fixture(), editorial_state, archive: { eligible, archived_at: '2026-10-18T12:00:00Z', message: 'Retained' } })).toThrow();
  }
});


test('inconsistent timestamp returned by the API cannot render an editable composer', async () => {
  const p = fixture(); p.archive = { eligible: false, archived_at: '2026-10-18T12:00:00Z', message: 'Retained' };
  get.mockImplementation(async (path: string) => ({ data: path.includes('/system/') ? { ...system, publishing_enabled: false } : path.endsWith('/accounts') ? { accounts: [] } : p }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><SocialEditorPage postId={p.id} /></QueryClientProvider>);
  await waitFor(() => expect(screen.queryByText('Loading draft…')).not.toBeInTheDocument());
  expect(screen.getByRole('alert')).toHaveTextContent('INVALID RESPONSE');
  expect(screen.queryByLabelText('Internal title')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save draft' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Archive post' })).not.toBeInTheDocument();
  expect(send).not.toHaveBeenCalled(); expect(api.patch).not.toHaveBeenCalled();
});

beforeEach(() => { window.history.replaceState({}, "", "/admin/social"); });
