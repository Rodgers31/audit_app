import api from '@/lib/api/axios';
import SocialResults from '@/components/admin/social/SocialResults';
import { useSocialMutation } from '@/lib/hooks/useSocial';
import { accounts, postId, target } from '@/tests/socialFixtures';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { ReactNode } from 'react';
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
const send = api.post as jest.Mock;
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>;
}
beforeEach(() => { jest.restoreAllMocks(); jest.clearAllMocks(); sessionStorage.clear(); send.mockResolvedValue({ data: {} }); });
afterEach(() => jest.restoreAllMocks());

test('a refused journal admission populates the typed mutation error before sending', async () => {
  jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Storage denied'); });
  const view = renderHook(() => useSocialMutation(), { wrapper });
  await act(async () => { await expect(view.result.current.run('/posts', { title: 'Owned inert fixture' }, value => value)).rejects.toBeDefined(); });
  expect(send).not.toHaveBeenCalled();
  await waitFor(() => expect(view.result.current.error?.code).toBe('COMMAND_RECOVERY_UNAVAILABLE'));
});

test('a refused journal admission is visible in the actual destination retry UI', async () => {
  jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Storage denied'); });
  render(<SocialResults targets={[target('failed')]} accounts={accounts} postId={postId} />, { wrapper });
  fireEvent.change(screen.getByLabelText('Reason to retry Facebook'), { target: { value: 'Reviewed the failed fixture target' } });
  fireEvent.click(screen.getByRole('button', { name: 'Request safe retry for Facebook' }));
  const banner = await screen.findByRole('alert');
  expect(banner).toHaveTextContent(/recovery/i); expect(send).not.toHaveBeenCalled();
});

test('a journal cleanup failure after acceptance surfaces uncertainty without falsely claiming no send', async () => {
  const original = Storage.prototype.setItem; let writes = 0;
  jest.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key, value) {
    if (++writes === 2) throw new Error('Cleanup write denied');
    original.call(this, key, value);
  });
  const view = renderHook(() => useSocialMutation(), { wrapper }); let failure: unknown;
  await act(async () => { try { await view.result.current.run('/posts', { title: 'Owned inert fixture' }, value => value); } catch (error) { failure = error; } });
  expect(send).toHaveBeenCalledTimes(1); expect(failure).toBeDefined();
  expect((failure as Error).message).not.toContain('No new command was sent');
  await waitFor(() => expect(view.result.current.error?.code).toBe('COMMAND_RECOVERY_UNAVAILABLE'));
});
