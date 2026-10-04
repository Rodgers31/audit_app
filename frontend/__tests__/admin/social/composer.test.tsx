import SocialComposer from '@/components/admin/social/SocialComposer';
import { SocialSystemStrip } from '@/components/admin/social/SocialWorkspace';
import api from '@/lib/api/axios';
import { SocialPost } from '@/lib/api/social';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { accounts, actorId, assetId, facebookId, instagramId, post, system, target, validation } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }) }));
const get = api.get as jest.Mock, send = api.post as jest.Mock, patch = api.patch as jest.Mock;
let savedPost: SocialPost;
function typedError(code: string, message: string, targetErrors: unknown[] = []) { return { isAxiosError: true, response: { status: 409, data: { detail: { code, message, field_errors: [], target_errors: targetErrors, retryable: false, request_id: actorId } } } }; }
function mount(p?: SocialPost, connected = accounts, publishing = system) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  if (p) qc.setQueryData(socialKeys.detail(actorId, p.id), p);
  const tree = render(<QueryClientProvider client={qc}><div><SocialComposer initialPost={p} accounts={connected} system={publishing} onSaved={jest.fn()} /></div></QueryClientProvider>);
  return { ...tree, qc };
}
beforeEach(() => {
  jest.clearAllMocks(); savedPost = post();
  Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => `00000000-0000-4000-8000-${String(Math.random()).slice(2).padEnd(12, '0').slice(0, 12)}` });
  get.mockImplementation(async () => ({ data: savedPost }));
  patch.mockImplementation(async (_path, body) => { const version = savedPost.version + 1; savedPost = post({ ...body, version, revision_id: `00000000-0000-4000-8000-${String(40 + version).padStart(12, '0')}` }); return { data: savedPost }; });
  send.mockImplementation(async (path, body) => { if (path === '/admin/social/posts') savedPost = post(body); return { data: path.endsWith('/validate') ? validation(savedPost) : savedPost }; });
});

test('empty accounts preserve first-class manual draft creation and disabled media controls', async () => {
  mount(undefined, []);
  expect(screen.getByText(/No connected accounts/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Upload media' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Choose from library' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Internal title'), { target: { value: 'Manual announcement' } });
  fireEvent.change(screen.getByLabelText('Master text'), { target: { value: 'A manual draft without destinations.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await screen.findByText('Draft saved. Nothing has been queued for publication.');
  expect(send).toHaveBeenCalledWith('/admin/social/posts', expect.objectContaining({ document: expect.objectContaining({ targets: [] }) }), expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }));
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeDisabled();
});

test('account overrides isolate changes, preserve intentional empty values, and reset to master', async () => {
  const p = post({ document: { ...post().document, targets: [{ account_id: facebookId, format: 'text', overrides: {} }, { account_id: instagramId, format: 'image', overrides: {} }] } });
  savedPost = p; mount(p);
  fireEvent.click(screen.getByRole('button', { name: 'Customize text' }));
  fireEvent.change(screen.getByLabelText('Account text'), { target: { value: 'Facebook only wording' } });
  expect(screen.getByLabelText('Master text')).toHaveValue(p.document.master.text);
  fireEvent.click(screen.getByRole('button', { name: 'Instagram · AuditGava test Instagram' }));
  expect(screen.queryByLabelText('Account text')).not.toBeInTheDocument();
  expect(within(screen.getByRole('region', { name: 'Resolved post preview' })).getByText(p.document.master.text)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Facebook · AuditGava test Page' }));
  expect(screen.getByLabelText('Account text')).toHaveValue('Facebook only wording');
  fireEvent.click(screen.getByRole('button', { name: 'Customize link' }));
  fireEvent.change(screen.getByLabelText(/Account URL/), { target: { value: '' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(patch).toHaveBeenCalled());
  expect(patch.mock.calls[0][1].document.targets[0].overrides.link).toEqual({ mode: 'replace', value: null });
  expect(patch.mock.calls[0][1].document.targets[1].overrides).toEqual({});
  fireEvent.click(screen.getByRole('button', { name: 'Reset text to master' }));
  fireEvent.click(screen.getByRole('button', { name: 'Reset link to master' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(patch).toHaveBeenCalledTimes(2));
  expect(patch.mock.calls[1][1].document.targets[0].overrides).toEqual({});
});

test('typing hashtag separators preserves the input and isolates account hashtags', async () => {
  mount(post());
  fireEvent.change(screen.getByLabelText(/Master hashtags/), { target: { value: '#Evidence ' } });
  expect(screen.getByLabelText(/Master hashtags/)).toHaveValue('#Evidence ');
  fireEvent.change(screen.getByLabelText(/Master hashtags/), { target: { value: '#Evidence #Sources' } });
  fireEvent.click(screen.getByRole('button', { name: 'Customize hashtags' }));
  fireEvent.change(screen.getByLabelText(/Account hashtags/), { target: { value: '#Account ' } });
  expect(screen.getByLabelText(/Account hashtags/)).toHaveValue('#Account ');
  fireEvent.change(screen.getByLabelText(/Account hashtags/), { target: { value: '#Account #Context' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await screen.findByText('Draft saved. Nothing has been queued for publication.');
  expect(patch.mock.calls[0][1].document.master.hashtags).toEqual(['#Evidence', '#Sources']);
  expect(patch.mock.calls[0][1].document.targets[0].overrides.hashtags).toEqual({ mode: 'replace', value: ['#Account', '#Context'] });
});

test('invalid selected subset blocks all publication and never silently drops destinations', async () => {
  const p = post({ document: { ...post().document, targets: [{ account_id: facebookId, format: 'text', overrides: {} }, { account_id: instagramId, format: 'text', overrides: {} }] } });
  const result = validation(p); result.valid = false; result.targets[1].valid = false; result.targets[1].errors = [{ code: 'UNSUPPORTED_FORMAT', field: 'format', message: 'Instagram needs ready media.' }];
  send.mockResolvedValue({ data: result }); mount(p);
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await screen.findByText('Instagram needs ready media.');
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeDisabled();
  expect(screen.getByRole('checkbox', { name: /Instagram · AuditGava test Instagram/ })).toBeChecked();
  expect(patch).not.toHaveBeenCalled();
  expect(send.mock.calls.every(c => c[0].endsWith('/validate'))).toBe(true);
});

test('a malformed valid envelope cannot omit a selected destination', async () => {
  const p = post(); const result = validation(p); result.targets = [];
  send.mockResolvedValue({ data: result }); mount(p);
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await screen.findByRole('region', { name: 'Backend validation' });
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeDisabled();
});

test('global pause gates valid posts while draft saving remains available', async () => {
  mount(post(), accounts, { ...system, publishing_enabled: false });
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await screen.findByText(/All selected destinations passed/);
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Internal title'), { target: { value: 'An edited draft during the publishing pause' } });
  expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled();
  expect(screen.getByText(/Publishing is paused/)).toBeInTheDocument();
});

test('stale save preserves local text and expected version until explicit conflict resolution', async () => {
  const p = post(); mount(p);
  fireEvent.change(screen.getByLabelText('Master text'), { target: { value: 'Preserve my local edit' } });
  patch.mockRejectedValueOnce(typedError('VERSION_CONFLICT', 'Another admin edited this post.'));
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await screen.findByText(/Another admin edited this post/);
  expect(screen.getByLabelText('Master text')).toHaveValue('Preserve my local edit');
  expect(patch.mock.calls[0][1].expected_version).toBe(1);
  expect(screen.getByRole('button', { name: 'Load current revision' })).toBeDisabled();
  savedPost = post({ version: 2, document: { ...p.document, master: { ...p.document.master, text: 'New server content' } } });
  fireEvent.click(screen.getByRole('checkbox', { name: /Discard my local edits/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Load current revision' }));
  await screen.findByText('Current revision loaded. Review it before saving or publishing.');
  expect(screen.getByLabelText('Master text')).toHaveValue('New server content');
});

test('ambiguous draft save retry reuses the exact command body and Idempotency-Key', async () => {
  mount();
  fireEvent.change(screen.getByLabelText('Internal title'), { target: { value: 'Recover this save' } });
  send.mockRejectedValueOnce({ isAxiosError: true });
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await screen.findByText(/response could not be confirmed/);
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await screen.findByText('Draft saved. Nothing has been queued for publication.');
  expect(send.mock.calls[0]).toEqual(send.mock.calls[1]);
});

test.each(['publish', 'schedule'])('approve then validate then %s uses the approved ready publication', async action => {
  const p = post({ editorial_state: 'pending_review' }); savedPost = p;
  send.mockImplementation(async (path, body) => {
    if (path.endsWith('/validate')) return { data: validation(savedPost) };
    if (path.endsWith('/approve')) {
      savedPost = post({ editorial_state: 'approved', version: 2, targets: [target('ready')], publication: { id: '00000000-0000-4000-8000-000000000060', revision_id: p.revision_id, scheduled_for: null, version: 1, approved_at: '2026-10-03T12:00:00Z' } });
      return { data: savedPost };
    }
    return { data: { post_id: p.id, publication_id: savedPost.publication!.id, status: 'queued', scheduled_for: action === 'schedule' ? '2027-01-05T07:00:00Z' : '2026-10-03T12:00:00Z', status_url: `/api/v1/admin/social/posts/${p.id}/status`, targets: [{ id: target('queued').id, account_id: facebookId, platform: 'facebook', status: 'queued' }] } };
  });
  mount(p);
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Approve revision' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Approve revision' }));
  await screen.findByText('This exact revision is approved. Publication is a separate command.');
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Publish now' })).toBeEnabled());
  if (action === 'schedule') {
    fireEvent.click(screen.getByRole('button', { name: 'Schedule' }));
    fireEvent.change(screen.getByLabelText('Local publish time'), { target: { value: '2027-01-05T10:00' } });
    expect(screen.getByText(/UTC preview: 2027-01-05T07:00:00.000Z/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm schedule' }));
  } else fireEvent.click(screen.getByRole('button', { name: 'Publish now' }));
  await screen.findByText(/accepted for 1 destination/);
  const command = send.mock.calls.find(c => c[0].endsWith(`/${action}`));
  expect(command[1]).toEqual(expect.objectContaining({ expected_version: 2, revision_id: p.revision_id, acknowledged_warning_codes: [] }));
  if (action === 'schedule') expect(command[1].schedule).toEqual({ local_time: '2027-01-05T10:00:00', timezone: 'Africa/Nairobi', utc_offset: '+03:00' });
});

test('warnings require acknowledgement and backend target rejection preserves all selected accounts', async () => {
  const p = post(); const result = validation(p); result.warnings = [{ code: 'LINK_WARNING', field: 'link', message: 'Check the link presentation.' }];
  send.mockImplementation(async path => {
    if (path.endsWith('/validate')) return { data: result };
    throw typedError('TARGET_VALIDATION_FAILED', 'Account validation changed.', [{ account_id: facebookId, code: 'ACCOUNT_UNAVAILABLE', field: 'account_id', message: 'Reconnect this account.' }]);
  }); mount(p);
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await screen.findByText(/Acknowledge LINK_WARNING/);
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox', { name: /Acknowledge LINK_WARNING/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Publish now' }));
  await screen.findByText(/Reconnect this account/);
  expect(screen.getByRole('checkbox', { name: /Facebook · AuditGava test Page/ })).toBeChecked();
  expect(send.mock.calls.find(c => c[0].endsWith('/publish'))[1].acknowledged_warning_codes).toEqual(['LINK_WARNING']);
});

test('partial results retain confirmed links and retry only the explicitly failed target', async () => {
  const success = { ...target('published'), remote_url: 'https://example.org/confirmed-post', published_at: '2026-10-03T12:10:00Z' };
  const failure = { ...target('failed', 'instagram'), safe_error_message: 'The provider rejected this media.' };
  const p = post({ targets: [success, failure], delivery_status: 'partially_published' }); savedPost = p; mount(p);
  expect(screen.getByRole('link', { name: 'View Facebook post' })).toHaveAttribute('href', success.remote_url);
  expect(screen.getByLabelText('Master text')).toBeDisabled();
  expect(screen.queryByRole('button', { name: /retry for Facebook/ })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Reason to retry Instagram'), { target: { value: 'Provider issue resolved after inspection' } });
  fireEvent.click(screen.getByRole('button', { name: 'Request safe retry for Instagram' }));
  await screen.findByText(/Retry command accepted/);
  expect(send).toHaveBeenCalledWith(`/admin/social/targets/${failure.id}/retry`, { reason: 'Provider issue resolved after inspection' }, expect.any(Object));
  expect(screen.getByRole('link', { name: 'View Facebook post' })).toBeInTheDocument();
});

test('unknown remote outcome and unsafe links never offer a blind retry', () => {
  mount(post({ targets: [{ ...target('published'), remote_url: 'javascript:alert(1)' }, target('outcome_unknown', 'instagram')] }));
  expect(screen.queryByRole('link', { name: 'View Facebook post' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Request safe retry/ })).not.toBeInTheDocument();
  expect(screen.getByText(/platform may have accepted/)).toBeInTheDocument();
});

test('nullable source/media payloads and missing account platform decode and remain editable', async () => {
  const p = post({ references: [{ url: 'https://example.org/source', label: null }], document: { ...post().document, master: { ...post().document.master, media: [{ asset_id: assetId, alt_text: null, caption_asset_id: null }] } } });
  const result = validation(p, false); result.targets[0].platform = null; result.targets[0].errors = [{ code: 'ACCOUNT_UNAVAILABLE', field: 'account_id', message: 'Selected account no longer exists.' }];
  send.mockResolvedValue({ data: result }); savedPost = p;
  const { qc } = mount(p); qc.removeQueries({ queryKey: socialKeys.detail(actorId, p.id) });
  fireEvent.click(screen.getByRole('button', { name: 'Refresh revision & results' }));
  await waitFor(() => expect(get).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await screen.findByText(/Unknown platform/);
  expect(screen.getByLabelText('Source label 1')).toHaveValue('');
  expect(screen.getByLabelText('Master media 1 alt text')).toHaveValue('');
  expect(screen.queryByText(/INVALID RESPONSE/)).not.toBeInTheDocument();
});

test('system status never fabricates worker health and uses versioned pause commands', async () => {
  const qc = new QueryClient(); patch.mockResolvedValue({ data: { ...system, version: 2, publishing_enabled: false } });
  render(<QueryClientProvider client={qc}><div><SocialSystemStrip status={system} refresh={jest.fn()} /></div></QueryClientProvider>);
  expect(screen.getByText('Worker health unavailable')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Pause publishing' }));
  fireEvent.change(screen.getByLabelText('Reason for control change'), { target: { value: 'Editorial hold' } });
  fireEvent.click(screen.getByRole('button', { name: 'Confirm pause' }));
  await waitFor(() => expect(patch).toHaveBeenCalledWith('/admin/social/controls', { expected_version: 1, publishing_enabled: false, reason: 'Editorial hold' }, expect.any(Object)));
});
