import SocialComposer from '@/components/admin/social/SocialComposer';
import { SocialSystemStrip } from '@/components/admin/social/SocialWorkspace';
import api from '@/lib/api/axios';
import { decodePost, SocialPost, TargetState } from '@/lib/api/social';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { accounts, actorId, assetId, instagramId, post, publicationReceipt, system, target, validation } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }) }));

const get = api.get as jest.Mock, send = api.post as jest.Mock, patch = api.patch as jest.Mock;
const clients: QueryClient[] = [];
const asset2 = '00000000-0000-4000-8000-000000000031';
const captionId = '00000000-0000-4000-8000-000000000032';
const freshId = '00000000-0000-4000-8000-000000000059';
function client(p?: SocialPost) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } });
  clients.push(qc); if (p) qc.setQueryData(socialKeys.detail(actorId, p.id), p); return qc;
}
function mount(raw: SocialPost) {
  const p = decodePost(raw), qc = client(p);
  get.mockResolvedValue({ data: p });
  render(<QueryClientProvider client={qc}><SocialComposer initialPost={p} accounts={accounts} system={system} /></QueryClientProvider>);
  return qc;
}
function approved(states: TargetState[] = ['ready']) {
  const p = post({ editorial_state: 'approved', targets: states.map((state, i) => target(state, i ? 'instagram' : 'facebook')) });
  if (states.length === 2) p.document.targets.push({ account_id: instagramId, format: 'image', overrides: {} });
  p.publication = { id: '00000000-0000-4000-8000-000000000060', revision_id: p.revision_id, scheduled_for: null, version: 1, approved_at: '2026-10-03T12:00:00Z', approved_by: actorId, schedule_timezone: null, requested_local_time: null, cancel_requested_at: null };
  return p;
}
function mediaPost() {
  const p = post();
  p.document.master.media = [{ asset_id: assetId, alt_text: 'First exact description', caption_asset_id: captionId }, { asset_id: asset2, alt_text: 'Second exact description', caption_asset_id: null }];
  p.document.targets = [{ account_id: instagramId, format: 'carousel', overrides: {} }];
  return p;
}
async function validate() {
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await screen.findByRole('region', { name: 'Backend validation' });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save & validate' })).toBeEnabled());
}
function authorizationExpired() {
  return { isAxiosError: true, response: { status: 409, data: { detail: { code: 'AUTHORIZATION_EXPIRED', message: 'Original authorization expired. Create a new reviewed draft.', field_errors: [], target_errors: [], retryable: false, request_id: actorId } } } };
}
beforeEach(() => {
  jest.clearAllMocks();
  let sequence = 90;
  Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => `00000000-0000-4000-8000-${String(++sequence).padStart(12, '0')}` });
});
afterEach(() => { cleanup(); clients.splice(0).forEach(qc => qc.clear()); jest.useRealTimers(); });

test.each(['wrong order', 'wrong asset', 'missing asset', 'extra asset', 'duplicate asset', 'changed explicit alt', 'changed explicit empty alt', 'wrong caption'])('complete typed preview with %s cannot enable publication', async attack => {
  const p = mediaPost();
  if (attack === 'changed explicit empty alt') p.document.master.media[0].alt_text = '';
  const result = validation(p), payload = result.targets[0].resolved_preview!;
  if (attack === 'wrong order') payload.assets.reverse();
  if (attack === 'wrong asset') payload.assets[0].asset_id = '00000000-0000-4000-8000-000000000039';
  if (attack === 'missing asset') payload.assets.pop();
  if (attack === 'extra asset') payload.assets.push({ ...payload.assets[0], asset_id: '00000000-0000-4000-8000-000000000039' });
  if (attack === 'duplicate asset') payload.assets[1] = { ...payload.assets[0] };
  if (attack === 'changed explicit alt' || attack === 'changed explicit empty alt') payload.assets[0].alt_text = 'Unexpected backend replacement';
  if (attack === 'wrong caption') payload.assets[0].caption_asset_id = '00000000-0000-4000-8000-000000000038';
  send.mockResolvedValue({ data: result }); mount(p); await validate();
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeDisabled();
  expect(send.mock.calls.some(c => c[0].endsWith('/publish'))).toBe(false);
});

test.each([null, undefined])('backend default alt enrichment for reference alt=%p remains allowed', async alt => {
  const p = mediaPost(); p.document.master.media[0].alt_text = alt;
  const result = validation(p); result.targets[0].resolved_preview!.assets[0].alt_text = 'Storage-provided accessible description';
  send.mockResolvedValue({ data: result }); mount(p); await validate();
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeEnabled();
});

test('intentional empty alt is permitted when the resolved payload preserves it exactly', async () => {
  const p = mediaPost(); p.document.master.media[0].alt_text = '';
  send.mockResolvedValue({ data: validation(p) }); mount(p); await validate();
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeEnabled();
});

test('master assets cannot replace explicitly overridden account assets in a complete preview', async () => {
  const p = mediaPost(); p.document.targets[0].overrides.media = { mode: 'replace', value: [{ asset_id: asset2, alt_text: 'Account-only description', caption_asset_id: null }] };
  const result = validation(p); result.targets[0].resolved_preview!.assets[0].asset_id = assetId;
  send.mockResolvedValue({ data: result }); mount(p); await validate();
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeDisabled();
});

test.each(['swapped existing IDs', 'new existing ID', 'new publication ID'])('ready authorization rejects a receipt with %s and retains its command key', async attack => {
  const p = approved(['ready', 'ready']), receipt = publicationReceipt(p);
  if (attack === 'swapped existing IDs') [receipt.targets[0].id, receipt.targets[1].id] = [receipt.targets[1].id, receipt.targets[0].id];
  if (attack === 'new existing ID') receipt.targets[0].id = freshId;
  if (attack === 'new publication ID') receipt.publication_id = '00000000-0000-4000-8000-000000000069';
  send.mockImplementation(async path => ({ data: path.endsWith('/validate') ? validation(p) : receipt }));
  const qc = mount(p);
  for (let attempt = 0; attempt < 2; attempt++) {
    await validate(); fireEvent.click(screen.getByRole('button', { name: 'Publish now' }));
    await screen.findByRole('alert');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save & validate' })).toBeEnabled());
    expect(screen.queryByText(/Publication accepted/)).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('INVALID RESPONSE');
    expect(qc.getQueryData<SocialPost>(socialKeys.detail(actorId, p.id))?.publication?.id).toBe(p.publication!.id);
  }
  const requests = send.mock.calls.filter(c => c[0].endsWith('/publish'));
  expect(requests).toHaveLength(2); expect(requests[0]).toEqual(requests[1]);
});

test('a direct two-account draft permits freshly created unique receipt IDs in either account order', async () => {
  const p = post(); p.document.targets.push({ account_id: instagramId, format: 'image', overrides: {} });
  const receipt = publicationReceipt(p);
  receipt.publication_id = '00000000-0000-4000-8000-000000000069';
  receipt.targets[0].id = freshId; receipt.targets[1].id = '00000000-0000-4000-8000-000000000058'; receipt.targets.reverse();
  send.mockImplementation(async path => ({ data: path.endsWith('/validate') ? validation(p) : receipt }));
  mount(p); await validate(); fireEvent.click(screen.getByRole('button', { name: 'Publish now' }));
  await screen.findByText(/Publication accepted for 2 destination/);
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

test('a direct two-account draft rejects a receipt whose newly-created IDs are duplicated', async () => {
  const p = post(); p.document.targets.push({ account_id: instagramId, format: 'image', overrides: {} });
  const receipt = publicationReceipt(p); receipt.targets.forEach(t => { t.id = freshId; });
  send.mockImplementation(async path => ({ data: path.endsWith('/validate') ? validation(p) : receipt }));
  mount(p); await validate(); fireEvent.click(screen.getByRole('button', { name: 'Publish now' }));
  await screen.findByRole('alert'); expect(screen.queryByText(/Publication accepted/)).not.toBeInTheDocument();
});

test.each(['draft', 'pending_review', 'rejected', 'archived'] as const)('cancelled targets on an editorial %s post cannot resume', async state => {
  const p = approved(['cancelled']); p.editorial_state = state;
  send.mockResolvedValue({ data: validation(p) }); mount(p);
  if (screen.queryByRole('button', { name: 'Save & validate' })) await validate();
  expect(screen.queryByRole('button', { name: 'Resume unsent deliveries' })).not.toBeInTheDocument();
  expect(send.mock.calls.some(c => c[0].endsWith('/resume'))).toBe(false);
});

test.each(['ready', 'queued', 'claimed', 'dispatching', 'processing', 'retry_wait', 'reconciling', 'blocked', 'published', 'failed', 'outcome_unknown'] as TargetState[])('approved mixed cancelled/%s targets cannot resume', async state => {
  const p = approved(['cancelled', state]); send.mockResolvedValue({ data: validation(p) }); mount(p);
  if (screen.queryByRole('button', { name: 'Save & validate' })) await validate();
  expect(screen.queryByRole('button', { name: 'Resume unsent deliveries' })).not.toBeInTheDocument();
  expect(send.mock.calls.some(c => c[0].endsWith('/resume'))).toBe(false);
});

test('AUTHORIZATION_EXPIRED on resume preserves the reason, identity and key without claiming success', async () => {
  const p = approved(['cancelled', 'cancelled']);
  send.mockImplementation(async path => {
    if (path.endsWith('/validate')) return { data: validation(p) };
    throw authorizationExpired();
  });
  const qc = mount(p); await validate();
  const reason = '  Reviewed the unchanged original destinations  ';
  fireEvent.change(screen.getByLabelText('Reason to resume'), { target: { value: reason } });
  for (let attempt = 0; attempt < 2; attempt++) {
    const button = screen.getByRole('button', { name: 'Resume unsent deliveries' });
    if ((button as HTMLButtonElement).disabled) await validate();
    fireEvent.click(button);
    await screen.findByText(/Original authorization expired/);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save & validate' })).toBeEnabled());
    expect(screen.getByLabelText('Reason to resume')).toHaveValue(reason);
    expect(screen.queryByText(/Resume accepted/)).not.toBeInTheDocument();
    expect(qc.getQueryData<SocialPost>(socialKeys.detail(actorId, p.id))?.targets.every(t => t.state === 'cancelled')).toBe(true);
  }
  const requests = send.mock.calls.filter(c => c[0].endsWith('/resume'));
  expect(requests).toHaveLength(2); expect(requests[0]).toEqual(requests[1]);
  expect(requests[0][1]).toEqual(expect.objectContaining({ reason: reason.trim(), revision_id: p.revision_id, expected_version: p.version }));
});

test.each(['title', 'hashtags', 'override', 'source'])('an approved %s edit then semantic revert cannot enable submit or revoke authorization by no-op save', async field => {
  const p = approved(); send.mockResolvedValue({ data: validation(p) }); const qc = mount(p);
  if (field === 'title') {
    fireEvent.change(screen.getByLabelText('Internal title'), { target: { value: 'Temporary title' } });
    fireEvent.change(screen.getByLabelText('Internal title'), { target: { value: p.title } });
  }
  if (field === 'hashtags') fireEvent.change(screen.getByLabelText(/Master hashtags/), { target: { value: '#Evidence  ' } });
  if (field === 'override') { fireEvent.click(screen.getByRole('button', { name: 'Customize text' })); fireEvent.click(screen.getByRole('button', { name: 'Reset text to master' })); }
  if (field === 'source') { fireEvent.click(screen.getByRole('button', { name: 'Add source reference' })); fireEvent.click(screen.getByRole('button', { name: 'Remove source 1' })); }
  expect(screen.getByRole('button', { name: 'Submit for review' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Submit for review' }));
  expect(send).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await screen.findByText('Saved content is unchanged. The current revision and authorization were kept.');
  expect(patch).not.toHaveBeenCalled();
  expect(qc.getQueryData<SocialPost>(socialKeys.detail(actorId, p.id))?.publication?.id).toBe(p.publication!.id);
  await validate(); expect(screen.getByRole('button', { name: 'Publish now' })).toBeEnabled();
});

test.each(['healthy', 'unavailable', 'unexpected'])('unknown worker state %s cannot appear fresh with valid timestamps', state => {
  jest.useFakeTimers({ now: new Date('2026-10-03T12:00:00Z') });
  const timestamp = new Date(Date.now()).toISOString();
  render(<QueryClientProvider client={client()}><SocialSystemStrip status={{ ...system, worker: { state, heartbeat_at: timestamp, last_scan_at: timestamp } }} refresh={jest.fn()} /></QueryClientProvider>);
  expect(screen.queryByText(`Worker: ${state}`)).not.toBeInTheDocument();
});

test('fresh active heartbeat cannot mask a stale scan and a stopped worker may omit its scan', () => {
  jest.useFakeTimers({ now: new Date('2026-10-03T12:00:00Z') });
  const timestamp = new Date(Date.now()).toISOString(), qc = client();
  const { rerender } = render(<QueryClientProvider client={qc}><SocialSystemStrip status={{ ...system, worker: { state: 'active', heartbeat_at: timestamp, last_scan_at: '2026-10-03T11:59:14Z' } }} refresh={jest.fn()} /></QueryClientProvider>);
  expect(screen.queryByText('Worker: active')).not.toBeInTheDocument();
  rerender(<QueryClientProvider client={qc}><SocialSystemStrip status={{ ...system, worker: { state: 'stopped', heartbeat_at: timestamp, last_scan_at: null } }} refresh={jest.fn()} /></QueryClientProvider>);
  expect(screen.getByText('Worker: stopped')).toBeInTheDocument();
});
