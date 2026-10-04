import api from '@/lib/api/axios';
import { useSocialMutation } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { ReactNode } from 'react';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));

const post = api.post as jest.Mock;
const decode = (value: unknown) => value;
const path = '/targets/00000000-0000-4000-8000-000000000050/retry';

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>;
}

beforeEach(() => jest.clearAllMocks());

test('a later deliberate retry gets a new command key after confirmed success', async () => {
  post.mockResolvedValue({ data: {} });
  const { result } = renderHook(() => useSocialMutation(), { wrapper });
  const body = { reason: 'Reviewed failed destination' };
  await act(async () => { await result.current.run(path, body, decode); });
  await act(async () => { await result.current.run(path, body, decode); });
  expect(post).toHaveBeenCalledTimes(2);
  expect(post.mock.calls[0][2].headers['Idempotency-Key']).not.toBe(post.mock.calls[1][2].headers['Idempotency-Key']);
});

test('ambiguous response recovery retains the exact original command key', async () => {
  post.mockRejectedValueOnce({ isAxiosError: true }).mockResolvedValueOnce({ data: {} });
  const { result } = renderHook(() => useSocialMutation(), { wrapper });
  const body = { reason: 'Reviewed failed destination' };
  await act(async () => { await expect(result.current.run(path, body, decode)).rejects.toBeDefined(); });
  await act(async () => { await result.current.run(path, body, decode); });
  expect(post).toHaveBeenCalledTimes(2);
  expect(post.mock.calls[0][2].headers['Idempotency-Key']).toBe(post.mock.calls[1][2].headers['Idempotency-Key']);
});
