import SocialComposer from '@/components/admin/social/SocialComposer';
import api from '@/lib/api/axios';
import { SocialSystemStatus } from '@/lib/api/social';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { accounts, actorId, post, publicationReceipt, system, validation } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
const get = api.get as jest.Mock, send = api.post as jest.Mock;
function mount(status: SocialSystemStatus = system, connected = accounts) {
  const p = post(), qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  qc.setQueryData(socialKeys.detail(actorId, p.id), p);
  const tree = render(<QueryClientProvider client={qc}><SocialComposer initialPost={p} accounts={connected} system={status} /></QueryClientProvider>);
  return { ...tree, qc };
}
function healthy() { return { ...system, worker: { state: 'idle', heartbeat_at: new Date().toISOString(), last_scan_at: new Date().toISOString() } }; }
beforeEach(() => {
  jest.clearAllMocks(); window.history.replaceState({}, '', '/admin/social');
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/media/capabilities') ? { upload_available: false, library_available: true, allowed_mime_types: [], max_image_bytes: 10485760, max_video_bytes: 52428800, unavailable_reason: 'Private uploads are paused for launch acceptance.' } : post() }));
  send.mockImplementation(async (path: string) => ({ data: path.endsWith('/validate') ? validation(post()) : publicationReceipt(post()) }));
});

test('manual media and publication are visible without expanding secondary controls', async () => {
  mount();
  expect(screen.getByRole('button', { name: 'Choose from library' })).toBeVisible();
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeVisible();
  expect(await screen.findByText('Private uploads are paused for launch acceptance.')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Upload media' })).toBeDisabled();
});

test('publication readiness explains system, account, worker and saved-validation holds', async () => {
  mount({ ...system, publishing_enabled: false }, [{ ...accounts[0], publishing_enabled: false, connection_state: 'disconnected' }]);
  const reasons = screen.getByRole('region', { name: 'Publication readiness' });
  expect(within(reasons).getByText(/Publishing is paused at the system level/)).toBeVisible();
  expect(within(reasons).getByText(/AuditGava test Page: account publishing is disabled/)).toBeVisible();
  expect(within(reasons).getByText(/AuditGava test Page: connection is disconnected/)).toBeVisible();
  expect(within(reasons).getByText(/Delivery worker is unavailable/)).toBeVisible();
  expect(within(reasons).getByText(/Save & validate this revision/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Publish now' })).toHaveAccessibleDescription(/Publishing is paused at the system level/);
  expect(send).not.toHaveBeenCalled();
});

test.each(['stale', 'stopped', 'unavailable'])('%s worker blocks immediate delivery but permits a valid future schedule', async state => {
  mount({ ...healthy(), worker: { ...healthy().worker, state } });
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await screen.findByText(/All selected destinations passed/);
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Schedule' }));
  fireEvent.change(screen.getByLabelText('Local publish time'), { target: { value: '2099-01-05T10:00' } });
  expect(screen.getByRole('button', { name: 'Confirm schedule' })).toBeEnabled();
  expect(send.mock.calls.every(([path]) => path.endsWith('/validate'))).toBe(true);
});

test('worker freshness expires while the composer stays open', async () => {
  jest.useFakeTimers();
  try {
    mount({ ...healthy(), worker: { state: 'active', heartbeat_at: new Date().toISOString(), last_scan_at: new Date().toISOString() } });
    fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
    await act(async () => {});
    expect(screen.getByRole('button', { name: 'Publish now' })).toBeEnabled();
    act(() => { jest.advanceTimersByTime(45_001); });
    expect(screen.getByRole('button', { name: 'Publish now' })).toBeDisabled();
    expect(screen.getByText(/Delivery worker status is stale/)).toBeVisible();
  } finally { jest.useRealTimers(); }
});

test('human publication accepts queued receipt without claiming remote publication', async () => {
  mount(healthy());
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Publish now' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Publish now' }));
  await screen.findByText(/Publication accepted for 1 destination/);
  expect(send.mock.calls.find(([path]) => path.endsWith('/publish'))?.[1]).toMatchObject({ expected_version: 1, revision_id: post().revision_id });
  expect(screen.queryByRole('link', { name: /View Facebook post/ })).not.toBeInTheDocument();
});


test('media availability never offers uploads when only the inspected library is available', async () => {
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/media/capabilities') ? { upload_available: false, library_available: true, allowed_mime_types: [], max_image_bytes: 10485760, max_video_bytes: 52428800, unavailable_reason: null } : post() }));
  mount();
  expect(await screen.findByText('Media uploads are unavailable. You can still choose inspected assets from the library.')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Upload media' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Choose from library' })).toBeEnabled();
});


test('server review-attestation refusal explains the missing human review before retry', async () => {
  send.mockImplementation(async (path: string) => {
    if (path.endsWith('/validate')) return { data: validation(post()) };
    throw { isAxiosError: true, response: { status: 422, data: { detail: { code: 'REVIEW_ATTESTATION_REQUIRED', message: 'Review facts and sources before publishing.', request_id: actorId, retryable: false, field_errors: [], target_errors: [] } } } };
  });
  mount(healthy());
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Publish now' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Publish now' }));
  await screen.findByText(/Review facts and sources before publishing/);
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeDisabled();
  expect(within(screen.getByRole('region', { name: 'Publication readiness' })).getByText(/The server requires a facts-and-sources review attestation/)).toBeVisible();
  fireEvent.click(screen.getByRole('checkbox', { name: /I checked the facts and sources/ }));
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeEnabled();
});
