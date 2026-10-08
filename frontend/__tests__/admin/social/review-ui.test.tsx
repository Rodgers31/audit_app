import SocialComposer from '@/components/admin/social/SocialComposer';
import SocialMedia from '@/components/admin/social/SocialMedia';
import SocialResults from '@/components/admin/social/SocialResults';
import { SocialSystemStrip } from '@/components/admin/social/SocialWorkspace';
import { httpsUrl, resolveContent } from '@/components/admin/social/socialDocument';
import api from '@/lib/api/axios';
import { SocialPost } from '@/lib/api/social';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { accounts, actorId, post, system, target, validation } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));

const get = api.get as jest.Mock, send = api.post as jest.Mock, patch = api.patch as jest.Mock;
let clients: QueryClient[];
function client(p?: SocialPost) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(qc);
  if (p) qc.setQueryData(socialKeys.detail(actorId, p.id), p);
  return qc;
}
function validPreview(p: SocialPost) {
  const value = validation(p);
  value.targets.forEach((row, i) => {
    const selection = p.document.targets[i], content = resolveContent(p.document.master, selection);
    row.resolved_preview = { schema_version: 1, account_id: selection.account_id, platform: row.platform!, api_product: 'fixture', external_account_id: 'fixture-account', format: selection.format, text: content.text, link: content.link, hashtags: content.hashtags, assets: [], visibility: 'public', disclosures: [], capability_version: 'social-v1', evidence_hash: 'a'.repeat(64), content_hash: 'b'.repeat(64) };
  });
  return value;
}
function receipt(p: SocialPost) {
  const queued = target('queued');
  return { post_id: p.id, publication_id: p.publication?.id ?? '00000000-0000-4000-8000-000000000060', status: 'queued', scheduled_for: '2026-10-03T12:00:00Z' as string | null, status_url: `/api/v1/admin/social/posts/${p.id}/status`, targets: [{ id: queued.id, account_id: queued.account_id, platform: queued.platform, status: 'queued' }] };
}
function approved() {
  const p = post({ editorial_state: 'approved', targets: [target('ready')] });
  p.publication = { id: '00000000-0000-4000-8000-000000000060', revision_id: p.revision_id, scheduled_for: null, version: 1, approved_at: '2026-10-03T12:00:00Z', approved_by: actorId, schedule_timezone: null, requested_local_time: null, cancel_requested_at: null };
  return p;
}
function mount(p: SocialPost) {
  get.mockResolvedValue({ data: p });
  const qc = client(p);
  render(<QueryClientProvider client={qc}><SocialComposer initialPost={p} accounts={accounts} system={system} /></QueryClientProvider>);
  return qc;
}
async function validate() {
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save & validate' })).toBeEnabled());
}
beforeEach(() => {
  jest.clearAllMocks(); clients = [];
  let sequence = 0;
  Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => `00000000-0000-4000-8000-${String(++sequence + 90).padStart(12, '0')}` });
});
afterEach(() => { clients.forEach(qc => qc.clear()); jest.useRealTimers(); jest.restoreAllMocks(); });

test.each(['target identity', 'publication identity'])('an existing approved receipt with synthetic %s cannot certify acceptance', async attack => {
  const p = approved(), value = receipt(p);
  if (attack === 'target identity') value.targets[0].id = '00000000-0000-4000-8000-000000000059';
  else value.publication_id = '00000000-0000-4000-8000-000000000069';
  send.mockImplementation(async path => ({ data: path.endsWith('/validate') ? validPreview(p) : value }));
  mount(p); await validate();
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeEnabled();
  fireEvent.click(screen.getByRole('button', { name: 'Publish now' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save & validate' })).toBeEnabled());
  expect(send.mock.calls.some(c => c[0].endsWith('/publish'))).toBe(true);
  expect(screen.queryByText(/Publication accepted/)).not.toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent(/INVALID RESPONSE/);
});

test('direct draft publication accepts newly created target IDs without inventing preexisting IDs', async () => {
  const p = post(), value = receipt(p);
  value.targets[0].id = '00000000-0000-4000-8000-000000000059';
  send.mockImplementation(async path => ({ data: path.endsWith('/validate') ? validPreview(p) : value }));
  mount(p); await validate();
  fireEvent.click(screen.getByRole('button', { name: 'Publish now' }));
  await screen.findByText(/Publication accepted for 1 destination/);
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

test('an immediate publication accepts the actual backend UTC due timestamp', async () => {
  const p = post(), value = receipt(p);
  value.scheduled_for = '2026-10-03T12:00:00Z';
  send.mockImplementation(async path => ({ data: path.endsWith('/validate') ? validPreview(p) : value }));
  mount(p); await validate();
  fireEvent.click(screen.getByRole('button', { name: 'Publish now' }));
  await screen.findByText(/Publication accepted for 1 destination/);
});

test('a misrouted retry stays failed, preserves its intent key and cannot write another post cache', async () => {
  const p = post({ targets: [target('failed')] }), other = post({ id: '00000000-0000-4000-8000-000000000011' });
  send.mockResolvedValue({ data: other });
  const qc = client(p);
  render(<QueryClientProvider client={qc}><SocialResults postId={p.id} targets={p.targets} accounts={accounts} /></QueryClientProvider>);
  fireEvent.change(screen.getByLabelText(/Reason to retry/), { target: { value: 'Provider failure resolved' } });
  for (let attempt = 0; attempt < 2; attempt++) {
    fireEvent.click(screen.getByRole('button', { name: 'Request safe retry for Facebook' }));
    await waitFor(() => expect(send).toHaveBeenCalledTimes(attempt + 1));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Request safe retry for Facebook' })).toBeEnabled());
    expect(screen.queryByText(/Retry command accepted/)).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(/INVALID RESPONSE/);
  }
  expect(qc.getQueryData(socialKeys.detail(actorId, other.id))).toBeUndefined();
  expect(send.mock.calls[1][2].headers['Idempotency-Key']).toBe(send.mock.calls[0][2].headers['Idempotency-Key']);
});

test.each(['submit', 'approve', 'reject', 'cancel'] as const)('a wrong-post %s editorial response cannot write another post cache or replace the composer', async action => {
  const p = action === 'cancel' ? approved() : post({ editorial_state: action === 'submit' ? 'draft' : 'pending_review' });
  const other = post({ ...p, id: '00000000-0000-4000-8000-000000000011' });
  send.mockImplementation(async path => ({ data: path.endsWith('/validate') ? validPreview(p) : other }));
  const qc = mount(p);
  if (action === 'approve') await validate();
  if (action === 'reject') fireEvent.change(screen.getByLabelText('Reason to reject'), { target: { value: 'Incorrect source interpretation' } });
  const names = { submit: 'Submit for review', approve: 'Approve revision', reject: 'Reject draft', cancel: 'Cancel unsent deliveries' };
  fireEvent.click(screen.getByRole('button', { name: names[action] }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save & validate' })).toBeEnabled());
  expect(send.mock.calls.some(c => c[0].endsWith(`/${action}`))).toBe(true);
  expect(screen.getByRole('alert')).toHaveTextContent(/INVALID RESPONSE/);
  expect(qc.getQueryData(socialKeys.detail(actorId, other.id))).toBeUndefined();
});

test.each(['https://user@example.org/path', 'https://user:password@example.org', ' https://example.org', 'https://example.org/a b', 'https://example.org/a\tb', 'https://example.org/\nsecret', 'https://example.org/\u00a0secret', 'https://', 'http://example.org'])('unsafe URL %p never becomes a clickable HTTPS link', value => {
  expect(httpsUrl(value)).toBeUndefined();
});
test('ordinary absolute HTTPS links remain usable', () => expect(httpsUrl('https://example.org/report?a=1#evidence')).toBe('https://example.org/report?a=1#evidence'));

test('unsaved credential-bearing sources are not clickable', () => {
  const p = post({ references: [{ url: 'https://user:password@example.org/report', label: 'Unsafe source' }] });
  mount(p);
  expect(screen.queryByRole('link', { name: 'Open source 1' })).not.toBeInTheDocument();
});

test('each Master and Account media instance has its own valid unavailable-control description', async () => {
  get.mockResolvedValue({ data: { upload_available: false, library_available: false, allowed_mime_types: [], max_image_bytes: 10485760, max_video_bytes: 52428800, unavailable_reason: 'Private media is unavailable.' } });
  const { container } = render(<QueryClientProvider client={client()}><div>{['Master', 'Account', 'Account'].map((label, i) => <section key={i}><SocialMedia label={label} media={[]} onChange={jest.fn()} /></section>)}</div></QueryClientProvider>);
  await waitFor(() => expect(screen.getAllByText('Private media is unavailable.')).toHaveLength(3));
  const ids = Array.from(container.querySelectorAll('section')).map(section => {
    const buttons = section.querySelectorAll('button'), id = buttons[0].getAttribute('aria-describedby');
    expect(id).toBeTruthy();
    expect(buttons[1].getAttribute('aria-describedby')).toBe(id);
    expect(Array.from(section.querySelectorAll('p')).find(p => p.id === id)).toHaveTextContent('Private media is unavailable.');
    return id;
  });
  expect(new Set(ids).size).toBe(3);
});

test.each([['active', 46_000], ['idle', 151_000]] as const)('%s heartbeat expires at the backend limit, not a shared 195s threshold', (state, age) => {
  jest.useFakeTimers({ now: new Date('2026-10-03T12:00:00Z') });
  const timestamp = new Date(Date.now() - age).toISOString();
  render(<QueryClientProvider client={client()}><SocialSystemStrip status={{ ...system, worker: { state, heartbeat_at: timestamp, last_scan_at: timestamp } }} refresh={jest.fn()} /></QueryClientProvider>);
  expect(screen.queryByText(`Worker: ${state}`)).not.toBeInTheDocument();
  expect(screen.getByText('Worker heartbeat stale or unavailable')).toBeInTheDocument();
});
test.each(['active', 'idle'] as const)('%s heartbeat loses freshness locally when its deadline passes', async state => {
  jest.useFakeTimers({ now: new Date('2026-10-03T12:00:00Z') });
  const timestamp = new Date(Date.now()).toISOString();
  render(<QueryClientProvider client={client()}><SocialSystemStrip status={{ ...system, worker: { state, heartbeat_at: timestamp, last_scan_at: timestamp } }} refresh={jest.fn()} /></QueryClientProvider>);
  expect(screen.getByText(`Worker: ${state}`)).toBeInTheDocument();
  await act(async () => { jest.advanceTimersByTime((state === 'active' ? 45_000 : 150_000) + 1); });
  expect(screen.queryByText(`Worker: ${state}`)).not.toBeInTheDocument();
});
test.each([null, '2026-10-03T11:59:14Z', '2026-10-03T12:00:06Z', 'bad-time'])('active status with missing/stale/future/malformed scan %p is unavailable', last_scan_at => {
  jest.useFakeTimers({ now: new Date('2026-10-03T12:00:00Z') });
  render(<QueryClientProvider client={client()}><SocialSystemStrip status={{ ...system, worker: { state: 'active', heartbeat_at: new Date(Date.now()).toISOString(), last_scan_at } }} refresh={jest.fn()} /></QueryClientProvider>);
  expect(screen.queryByText('Worker: active')).not.toBeInTheDocument();
});

test.each(['approved', 'pending_review', 'archived'] as const)('an unchanged %s post cannot submit for review', state => {
  const p = state === 'approved' ? approved() : post({ editorial_state: state });
  mount(p);
  const button = screen.queryByRole('button', { name: 'Submit for review' });
  if (button) { expect(button).toBeDisabled(); fireEvent.click(button); }
  expect(send).not.toHaveBeenCalled();
});
test.each(['draft', 'rejected'] as const)('an unchanged %s post may submit for review', state => {
  mount(post({ editorial_state: state }));
  expect(screen.getByRole('button', { name: 'Submit for review' })).toBeEnabled();
});
test('editing a pending-review post creates a new draft before it can be submitted', async () => {
  const p = post({ editorial_state: 'pending_review' });
  patch.mockImplementation(async (_path, body) => ({ data: post({ ...body, version: 2, revision_id: '00000000-0000-4000-8000-000000000041' }) }));
  send.mockImplementation(async (_path, body) => ({ data: post({ title: 'Changed title', version: body.expected_version + 1, editorial_state: 'pending_review', revision_id: '00000000-0000-4000-8000-000000000041' }) }));
  mount(p);
  fireEvent.change(screen.getByLabelText('Internal title'), { target: { value: 'Changed title' } });
  expect(screen.getByRole('button', { name: 'Submit for review' })).toBeEnabled();
  fireEvent.click(screen.getByRole('button', { name: 'Submit for review' }));
  await screen.findByText('Draft submitted for human review.');
  expect(patch).toHaveBeenCalledTimes(1);
  expect(send).toHaveBeenCalledWith(`/admin/social/posts/${p.id}/submit`, { expected_version: 2 }, expect.any(Object));
});

test('an unchanged approved draft cannot be saved into a new revision and revoke its authorization', () => {
  mount(approved());
  const button = screen.getByRole('button', { name: 'Save draft' });
  expect(button).toBeDisabled(); fireEvent.click(button);
  expect(patch).not.toHaveBeenCalled();
});
test('reverting local changes to the saved content clears edits without creating a new revision', async () => {
  const p = approved(); mount(p);
  const title = screen.getByLabelText('Internal title');
  fireEvent.change(title, { target: { value: 'Temporary edit' } });
  fireEvent.change(title, { target: { value: p.title } });
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(screen.queryByText('Unsaved edits')).not.toBeInTheDocument());
  expect(patch).not.toHaveBeenCalled();
  expect(screen.getByText(/approved · revision 1/)).toBeInTheDocument();
});

test.each(['text', 'link', 'hashtags', 'format'] as const)('a valid preview with changed %s cannot authorize the saved selection', async field => {
  const p = post(), result = validPreview(p);
  const preview = result.targets[0].resolved_preview!;
  if (field === 'text') preview.text = 'A different message';
  if (field === 'link') preview.link = 'https://example.org/different';
  if (field === 'hashtags') preview.hashtags = ['#Different'];
  if (field === 'format') preview.format = 'image';
  send.mockResolvedValue({ data: result }); mount(p); await validate();
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeDisabled();
});

test('resume uses its own reasoned command and preserves the cancelled publication and target identity', async () => {
  const p = approved(); p.targets = [target('cancelled')];
  const value = receipt(p);
  send.mockImplementation(async path => ({ data: path.endsWith('/validate') ? validPreview(p) : value }));
  mount(p); await validate();
  const button = screen.getByRole('button', { name: 'Resume unsent deliveries' });
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Reason to resume'), { target: { value: 'Reviewed the pause; send unchanged destinations' } });
  expect(button).toBeEnabled(); fireEvent.click(button);
  await screen.findByText(/Resume accepted for 1 destination/);
  expect(send).toHaveBeenCalledWith(`/admin/social/posts/${p.id}/resume`, expect.objectContaining({ expected_version: p.version, revision_id: p.revision_id, acknowledged_warning_codes: [], reason: 'Reviewed the pause; send unchanged destinations' }), expect.any(Object));
  expect(send.mock.calls.some(c => c[0].endsWith('/publish'))).toBe(false);
});

test.each(['past', 'future'] as const)('resume retains a %s original schedule according to the backend due-time rule', async when => {
  jest.spyOn(Date, 'now').mockReturnValue(new Date('2026-10-03T12:00:00Z').getTime());
  const p = approved(); p.targets = [target('cancelled')];
  p.publication!.scheduled_for = when === 'past' ? '2026-10-03T11:59:00Z' : '2026-10-03T12:30:00Z';
  const value = receipt(p);
  value.scheduled_for = when === 'past' ? '2026-10-03T12:00:00Z' : p.publication!.scheduled_for;
  send.mockImplementation(async path => ({ data: path.endsWith('/validate') ? validPreview(p) : value }));
  mount(p); await validate();
  fireEvent.change(screen.getByLabelText('Reason to resume'), { target: { value: 'Resume this unchanged authorization' } });
  fireEvent.click(screen.getByRole('button', { name: 'Resume unsent deliveries' }));
  await screen.findByText(/Resume accepted for 1 destination/);
  expect(value.publication_id).toBe(p.publication!.id);
  expect(value.targets[0].id).toBe(p.targets[0].id);
});

test('an overdue resume may retain its original schedule while the backend queues target work due now', async () => {
  jest.spyOn(Date, 'now').mockReturnValue(new Date('2026-10-03T12:00:00Z').getTime());
  const p = approved(); p.targets = [target('cancelled')]; p.publication!.scheduled_for = '2026-10-03T11:59:00Z';
  const value = receipt(p); value.scheduled_for = p.publication!.scheduled_for;
  send.mockImplementation(async path => ({ data: path.endsWith('/validate') ? validPreview(p) : value }));
  mount(p); await validate();
  fireEvent.change(screen.getByLabelText('Reason to resume'), { target: { value: 'Resume this unchanged authorization' } });
  fireEvent.click(screen.getByRole('button', { name: 'Resume unsent deliveries' }));
  await screen.findByText(/Resume accepted for 1 destination/);
});

test.each(['2026-10-03T11:58:00Z', '2026-10-03T12:30:00Z'])('resume cannot move a future original schedule to %s', async changed => {
  jest.spyOn(Date, 'now').mockReturnValue(new Date('2026-10-03T12:00:00Z').getTime());
  const p = approved(); p.targets = [target('cancelled')]; p.publication!.scheduled_for = '2026-10-03T12:15:00Z';
  const value = receipt(p); value.scheduled_for = changed;
  send.mockImplementation(async path => ({ data: path.endsWith('/validate') ? validPreview(p) : value }));
  mount(p); await validate();
  fireEvent.change(screen.getByLabelText('Reason to resume'), { target: { value: 'Resume this unchanged authorization' } });
  fireEvent.click(screen.getByRole('button', { name: 'Resume unsent deliveries' }));
  await screen.findByRole('alert');
  expect(screen.queryByText(/Resume accepted/)).not.toBeInTheDocument();
});

test.each(['2026-10-03T11:58:00Z', '2026-10-03T12:30:00Z'])('an overdue resume cannot report an unrelated due timestamp %s', async changed => {
  jest.spyOn(Date, 'now').mockReturnValue(new Date('2026-10-03T12:00:00Z').getTime());
  const p = approved(); p.targets = [target('cancelled')]; p.publication!.scheduled_for = '2026-10-03T11:59:00Z';
  const value = receipt(p); value.scheduled_for = changed;
  send.mockImplementation(async path => ({ data: path.endsWith('/validate') ? validPreview(p) : value }));
  mount(p); await validate();
  fireEvent.change(screen.getByLabelText('Reason to resume'), { target: { value: 'Resume this unchanged authorization' } });
  fireEvent.click(screen.getByRole('button', { name: 'Resume unsent deliveries' }));
  await screen.findByRole('alert');
  expect(screen.queryByText(/Resume accepted/)).not.toBeInTheDocument();
});

test('a future schedule that becomes overdue during the resume command is accepted due now', async () => {
  let now = new Date('2026-10-03T12:00:00Z').getTime();
  jest.spyOn(Date, 'now').mockImplementation(() => now);
  const p = approved(); p.targets = [target('cancelled')]; p.publication!.scheduled_for = '2026-10-03T12:00:01Z';
  const value = receipt(p); value.scheduled_for = '2026-10-03T12:00:02Z';
  send.mockImplementation(async path => {
    if (path.endsWith('/validate')) return { data: validPreview(p) };
    now += 2_000; return { data: value };
  });
  mount(p); await validate();
  fireEvent.change(screen.getByLabelText('Reason to resume'), { target: { value: 'Resume this unchanged authorization' } });
  fireEvent.click(screen.getByRole('button', { name: 'Resume unsent deliveries' }));
  await screen.findByText(/Resume accepted for 1 destination/);
});
