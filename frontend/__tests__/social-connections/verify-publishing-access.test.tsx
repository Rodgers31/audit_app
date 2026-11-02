import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import AccountPublishingControl from '@/components/admin/social/connections/AccountPublishingControl';
import api from '@/lib/api/axios';
import { useAuth } from '@/lib/auth/AuthProvider';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: jest.fn() }));
const id = '00000000-0000-4000-8000-000000000021';
const state = { account_id: id, publishing_enabled: false, controls_version: 1, state_token: 'a'.repeat(64), enable_available: false, enable_blockers: ['NATIVE_ADMISSION_UNAVAILABLE'], global_publishing_enabled: false, delivery_holds: ['GLOBAL_PUBLISHING_DISABLED', 'NATIVE_RUNTIME_UNAVAILABLE'] };
const verified = { ...state, controls_version: 2, state_token: 'b'.repeat(64), enable_available: true, enable_blockers: [], delivery_holds: ['GLOBAL_PUBLISHING_DISABLED'] };
const get = api.get as jest.Mock, post = api.post as jest.Mock, patch = api.patch as jest.Mock;
beforeEach(() => { jest.clearAllMocks(); (useAuth as jest.Mock).mockReturnValue({ user: { id: 'admin-a' } }); get.mockResolvedValue({ data: state }); post.mockResolvedValue({ data: verified }); });
async function mount(refresh = jest.fn()) {
  render(<AccountPublishingControl accountId={id} name='Fixture Page' refresh={refresh} canVerifyMeta />);
  fireEvent.click(screen.getByRole('button', { name: 'Refresh account publishing controls' }));
  await screen.findByRole('button', { name: 'Verify existing publishing access for Fixture Page' });
  return refresh;
}
test('verifies the saved grant before a separate explicit enable, without enabling global publishing', async () => {
  const refresh = await mount();
  fireEvent.click(screen.getByRole('button', { name: 'Verify existing publishing access for Fixture Page' }));
  await screen.findByText('Publishing access verified. Account publishing is still paused.');
  const [path, body, options] = post.mock.calls[0];
  expect(path).toBe(`/admin/social/accounts/${id}/verify-publishing-access`);
  expect(body).toEqual({ expected_controls_version: 1, expected_state: state.state_token, reason: 'Administrator requested verification of this saved Meta grant for publishing.' });
  expect(options.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/);
  expect(patch).not.toHaveBeenCalled(); expect(refresh).toHaveBeenCalledTimes(1);
  expect(screen.getByText('Global publishing is off. Enabling this account will not change it.')).toBeVisible();
  patch.mockResolvedValue({ data: { ...verified, publishing_enabled: true, controls_version: 3, state_token: 'c'.repeat(64) } });
  fireEvent.click(screen.getByRole('button', { name: 'Enable publishing for Fixture Page' }));
  await screen.findByRole('button', { name: 'Pause publishing for Fixture Page' });
  expect(patch.mock.calls[0][1]).toMatchObject({ expected_controls_version: 2, expected_state: verified.state_token, publishing_enabled: true });
});
test('ambiguous verification retains the same command body and key for explicit retry', async () => {
  post.mockRejectedValueOnce(new Error('transport lost'));
  await mount(); fireEvent.click(screen.getByRole('button', { name: 'Verify existing publishing access for Fixture Page' }));
  await screen.findByRole('alert');
  fireEvent.click(screen.getByRole('button', { name: 'Verify existing publishing access for Fixture Page' }));
  await screen.findByText('Publishing access verified. Account publishing is still paused.');
  expect(post.mock.calls[1]).toEqual(post.mock.calls[0]); expect(patch).not.toHaveBeenCalled();
});
test.each([
  { controls_version: 1 }, { controls_version: 9 }, { state_token: state.state_token },
  { publishing_enabled: true }, { account_id: '00000000-0000-4000-8000-000000000022' },
  { enable_available: false, enable_blockers: ['CREDENTIAL_UNAVAILABLE'] },
  { delivery_holds: [] },
])('refuses a verification reply that cannot establish the requested paused state: %j', async change => {
  post.mockResolvedValue({ data: { ...verified, ...change } }); const refresh = await mount();
  fireEvent.click(screen.getByRole('button', { name: 'Verify existing publishing access for Fixture Page' }));
  await screen.findByRole('alert'); expect(refresh).not.toHaveBeenCalled();
  expect(screen.queryByText('Publishing access verified. Account publishing is still paused.')).not.toBeInTheDocument();
  expect(patch).not.toHaveBeenCalled();
});
test('an enabled destination must be paused before verification and other platforms get no Meta action', async () => {
  get.mockResolvedValue({ data: { ...verified, publishing_enabled: true } });
  const view = render(<AccountPublishingControl accountId={id} name='Fixture Page' refresh={jest.fn()} canVerifyMeta />);
  fireEvent.click(screen.getByRole('button', { name: 'Refresh account publishing controls' }));
  await screen.findByRole('button', { name: 'Pause publishing for Fixture Page' });
  expect(screen.getByRole('button', { name: 'Verify existing publishing access for Fixture Page' })).toBeDisabled();
  view.rerender(<AccountPublishingControl accountId={id} name='Fixture Page' refresh={jest.fn()} />);
  expect(screen.queryByRole('button', { name: 'Verify existing publishing access for Fixture Page' })).not.toBeInTheDocument(); expect(post).not.toHaveBeenCalled();
});
test('a late verification result cannot update a successor administrator session', async () => {
  let finish!: (value: unknown) => void; post.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const refresh = jest.fn(); const view = render(<AccountPublishingControl accountId={id} name='Fixture Page' refresh={refresh} canVerifyMeta />);
  fireEvent.click(screen.getByRole('button', { name: 'Refresh account publishing controls' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Verify existing publishing access for Fixture Page' }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  (useAuth as jest.Mock).mockReturnValue({ user: { id: 'admin-b' } });
  view.rerender(<AccountPublishingControl accountId={id} name='Fixture Page' refresh={refresh} canVerifyMeta />);
  await act(async () => { finish({ data: verified }); });
  expect(refresh).not.toHaveBeenCalled(); expect(screen.queryByText('Publishing access verified. Account publishing is still paused.')).not.toBeInTheDocument();
});
