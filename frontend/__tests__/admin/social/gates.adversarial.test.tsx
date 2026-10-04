import SocialComposer from '@/components/admin/social/SocialComposer';
import api from '@/lib/api/axios';
import { decodePost, SocialPost, SocialValidation, TargetState } from '@/lib/api/social';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { accounts, actorId, instagramId, post, system, target, validation } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));

const get = api.get as jest.Mock, send = api.post as jest.Mock, patch = api.patch as jest.Mock;
let serverPost: SocialPost;
let clients: QueryClient[];

function typedError(code: string, message: string) {
  return { isAxiosError: true, response: { status: 409, data: { detail: { code, message, field_errors: [], target_errors: [], retryable: false, request_id: actorId } } } };
}
function twoAccountPost() {
  const p = post();
  return post({ document: { ...p.document, targets: [p.document.targets[0], { account_id: instagramId, format: 'image', overrides: {} }] } });
}
function approved(p: SocialPost, states: TargetState[] = ['ready']) {
  return post({ ...p, editorial_state: 'approved', targets: states.map((state, i) => target(state, i ? 'instagram' : 'facebook')), publication: { id: '00000000-0000-4000-8000-000000000060', revision_id: p.revision_id, scheduled_for: null, version: 1, approved_at: '2026-10-03T12:00:00Z' } });
}
function mount(p: SocialPost, connected = accounts) {
  const decoded = decodePost(p);
  serverPost = decoded;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(qc);
  qc.setQueryData(socialKeys.detail(actorId, decoded.id), decoded);
  render(<QueryClientProvider client={qc}><SocialComposer initialPost={decoded} accounts={connected} system={system} /></QueryClientProvider>);
  return qc;
}
async function validate() {
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save & validate' })).toBeEnabled());
}
function expectClosed() {
  const publish = screen.queryByRole('button', { name: 'Publish now' });
  if (publish) expect(publish).toBeDisabled();
  const confirm = screen.queryByRole('button', { name: 'Confirm schedule' });
  if (confirm) expect(confirm).toBeDisabled();
  expect(send.mock.calls.some(call => call[0].endsWith('/publish') || call[0].endsWith('/schedule'))).toBe(false);
}
function openSchedule() {
  fireEvent.click(screen.getByRole('button', { name: 'Schedule' }));
  fireEvent.change(screen.getByLabelText('Local publish time'), { target: { value: '2027-01-05T10:00' } });
}

beforeEach(() => {
  jest.clearAllMocks(); clients = []; serverPost = post();
  Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => '00000000-0000-4000-8000-000000000099' });
  get.mockImplementation(async () => ({ data: serverPost }));
  send.mockImplementation(async path => {
    if (path.endsWith('/validate')) return { data: validation(serverPost) };
    throw typedError('NOT_FOUND', 'Unexpected command reached fixture.');
  });
});
afterEach(() => { clients.forEach(qc => qc.clear()); jest.restoreAllMocks(); });

test.each(['empty', 'missing', 'duplicate', 'null platform', 'target error', 'top-level error', 'false valid'])('malformed validation: %s stays closed', async attack => {
  const p = twoAccountPost(), result: SocialValidation = validation(p);
  if (attack === 'empty') result.targets = [];
  if (attack === 'missing') result.targets = result.targets.slice(0, 1);
  if (attack === 'duplicate') result.targets = [result.targets[0], result.targets[0]];
  if (attack === 'null platform') result.targets[0].platform = null;
  if (attack === 'target error') result.targets[0].errors = [{ code: 'ACCOUNT_UNAVAILABLE', field: 'account_id', message: 'Account disabled.' }];
  if (attack === 'top-level error') result.errors = [{ code: 'REVIEW_REQUIRED', field: 'review', message: 'Review required.' }];
  if (attack === 'false valid') result.valid = false;
  send.mockResolvedValue({ data: result }); mount(p);
  await validate(); openSchedule(); expectClosed();
});

test('empty selected destination list cannot be certified by valid=true and empty target list', async () => {
  const p = post({ document: { ...post().document, targets: [] } });
  mount(p); await validate(); openSchedule(); expectClosed();
});

test.each(['queued', 'claimed', 'blocked', 'cancelled', 'dispatching', 'processing', 'retry_wait', 'reconciling', 'published', 'failed', 'outcome_unknown'] as TargetState[])('an existing approved %s authorization cannot be sent again', async state => {
  const p = approved(post(), [state]); mount(p);
  const validateButton = screen.queryByRole('button', { name: 'Save & validate' });
  if (validateButton) await validate();
  expectClosed();
  const schedule = screen.queryByRole('button', { name: 'Schedule' });
  if (schedule) expect(schedule).toBeDisabled();
});

test('an approved authorization containing an extra ready account stays closed', async () => {
  const p = approved(post(), ['ready', 'ready']);
  mount(p); await validate(); expectClosed();
});

test('an approved authorization with missing selected account stays closed', async () => {
  const p = approved(twoAccountPost());
  mount(p); await validate(); expectClosed();
});

test('an approved authorization with a wrong revision stays closed', async () => {
  const p = approved(post()); p.publication!.revision_id = '00000000-0000-4000-8000-000000000041';
  mount(p); await validate(); expectClosed();
});

test('an approved authorization containing duplicated ready account must not authorize the missing account', async () => {
  jest.spyOn(console, 'error').mockImplementation(() => undefined);
  const p = approved(twoAccountPost(), ['ready', 'ready']);
  p.targets = [target('ready'), { ...target('ready'), id: '00000000-0000-4000-8000-000000000052' }];
  mount(p); await validate(); expectClosed();
});

test('a draft with duplicated selected account cannot be certified by one matching row plus an unrelated row', async () => {
  jest.spyOn(console, 'error').mockImplementation(() => undefined);
  const base = post();
  const p = post({ document: { ...base.document, targets: [base.document.targets[0], base.document.targets[0]] } });
  const result = validation(twoAccountPost());
  send.mockResolvedValue({ data: result }); mount(p);
  await validate(); openSchedule(); expectClosed();
});

test('a backend validation platform differing from the selected account must not enable publication', async () => {
  const p = post(), result = validation(p); result.targets[0].platform = 'instagram';
  send.mockResolvedValue({ data: result }); mount(p);
  await validate(); openSchedule(); expectClosed();
});

test('a saved unavailable account cannot enable publication from a contradictory valid envelope', async () => {
  const p = post(); send.mockResolvedValue({ data: validation(p) }); mount(p, []);
  await validate();
  expect(screen.getByText(/No connected accounts/)).toBeInTheDocument();
  expect(screen.getByRole('checkbox', { name: /Unavailable account/ })).toBeChecked();
  expectClosed();
});

test.each(['VERSION_CONFLICT', 'TARGET_VALIDATION_FAILED', 'PUBLISHING_PAUSED'])('server %s rejection revokes prior validation until review', async code => {
  mount(post()); await validate(); openSchedule();
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeEnabled();
  send.mockRejectedValueOnce(typedError(code, 'Authoritative publication rejection.'));
  fireEvent.click(screen.getByRole('button', { name: 'Publish now' }));
  await screen.findByText(/Authoritative publication rejection/);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save & validate' })).toBeEnabled());
  expect(screen.getByLabelText('Master text')).toHaveValue(post().document.master.text);
  expect(screen.getByRole('checkbox', { name: /Facebook · AuditGava test Page/ })).toBeChecked();
  expect(screen.queryByText(/Publication accepted/)).not.toBeInTheDocument();
  expect({
    publishDisabled: (screen.getByRole('button', { name: 'Publish now' }) as HTMLButtonElement).disabled,
    scheduleDisabled: (screen.getByRole('button', { name: 'Confirm schedule' }) as HTMLButtonElement).disabled,
  }).toEqual({ publishDisabled: true, scheduleDisabled: true });
});

test('a live newer revision blocks validated commands and preserves unsaved text', async () => {
  const p = post(), qc = mount(p); await validate();
  fireEvent.change(screen.getByLabelText('Master text'), { target: { value: 'Must preserve local text' } });
  await act(async () => qc.setQueryData(socialKeys.detail(actorId, p.id), post({ version: 2, document: { ...p.document, master: { ...p.document.master, text: 'Changed by someone else' } } })));
  await screen.findByText(/A newer revision is available/);
  expect(screen.getByLabelText('Master text')).toHaveValue('Must preserve local text');
  expect(screen.getByRole('button', { name: 'Load current revision' })).toBeDisabled();
  expectClosed();
});

test('stale save rejection preserves edits and does not retry with a newer version automatically', async () => {
  mount(post());
  fireEvent.change(screen.getByLabelText('Master text'), { target: { value: 'Never discard on a conflict' } });
  patch.mockRejectedValue(typedError('VERSION_CONFLICT', 'Save conflict fixture.'));
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await screen.findByText(/Save conflict fixture/);
  expect(screen.getByLabelText('Master text')).toHaveValue('Never discard on a conflict');
  expect(patch).toHaveBeenCalledTimes(1);
  expect(patch.mock.calls[0][1].expected_version).toBe(1);
  expect(screen.getByRole('button', { name: 'Load current revision' })).toBeDisabled();
  expectClosed();
});

test('backend review attestation rejection never claims acceptance and a checked retry sends both facts and sources', async () => {
  const p = post({ content_type: 'financial_analysis' }); mount(p); await validate();
  send.mockRejectedValueOnce(typedError('REVIEW_ATTESTATION_REQUIRED', 'Explicit sensitive review is required.'));
  fireEvent.click(screen.getByRole('button', { name: 'Publish now' }));
  await screen.findByText(/Explicit sensitive review is required/);
  expect(send.mock.calls.find(call => call[0].endsWith('/publish'))[1].review_attestation).toBeUndefined();
  expect(screen.queryByText(/Publication accepted/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('checkbox', { name: /I checked the facts and sources/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Publish now' }));
  await waitFor(() => expect(send.mock.calls.filter(call => call[0].endsWith('/publish'))).toHaveLength(2));
  expect(send.mock.calls.filter(call => call[0].endsWith('/publish'))[1][1].review_attestation).toEqual({ facts_checked: true, sources_checked: true });
});

test('editing content clears attestation and validation rather than reusing reviewed facts', async () => {
  mount(post()); await validate();
  fireEvent.click(screen.getByRole('checkbox', { name: /I checked the facts and sources/ }));
  fireEvent.change(screen.getByLabelText('Master text'), { target: { value: 'Different facts' } });
  expect(screen.getByRole('checkbox', { name: /I checked the facts and sources/ })).not.toBeChecked();
  expect(screen.getByLabelText('Master text')).toHaveValue('Different facts');
  expectClosed();
});
