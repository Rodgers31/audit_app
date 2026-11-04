import api from '@/lib/api/axios';
import { useSocialMutation } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { ReactNode } from 'react';

let actor = '00000000-0000-4000-8000-000000000001';
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: actor } }) }));
const send = api.post as jest.Mock;
const body = { expected_version: 2, revision_id: '00000000-0000-4000-8000-000000000010', acknowledged_warning_codes: [] };
const path = '/posts/00000000-0000-4000-8000-000000000020/publish';
const decode = (value: unknown) => value;
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>;
}
beforeEach(() => { jest.clearAllMocks(); sessionStorage.clear(); actor = '00000000-0000-4000-8000-000000000001'; });

async function ambiguousThenRemount(decoder: (value: unknown) => unknown) {
  const first = renderHook(() => useSocialMutation(), { wrapper });
  await act(async () => { await expect(first.result.current.run(path, body, decoder)).rejects.toBeDefined(); });
  const original = send.mock.calls[0][2].headers['Idempotency-Key'];
  first.unmount();
  const next = renderHook(() => useSocialMutation(), { wrapper });
  await act(async () => { await next.result.current.run(path, body, decode); });
  expect(send.mock.calls[1][1]).toEqual(send.mock.calls[0][1]);
  expect(send.mock.calls[1][2].headers['Idempotency-Key']).toBe(original);
  next.unmount();
}

test('ambiguous publication keeps the original durable command identity after editor remount', async () => {
  send.mockRejectedValueOnce({ isAxiosError: true }).mockResolvedValueOnce({ data: {} });
  await ambiguousThenRemount(decode);
});

test('an undecodable accepted publication keeps the original identity after editor remount', async () => {
  send.mockResolvedValue({ data: {} });
  await ambiguousThenRemount(() => { throw new Error('Unconfirmed response'); });
});

test('a confirmed intent permits a deliberate new command after remount', async () => {
  send.mockResolvedValue({ data: {} });
  const first = renderHook(() => useSocialMutation(), { wrapper });
  await act(async () => { await first.result.current.run(path, body, decode); });
  first.unmount();
  const next = renderHook(() => useSocialMutation(), { wrapper });
  await act(async () => { await next.result.current.run(path, body, decode); });
  expect(send.mock.calls[1][2].headers['Idempotency-Key']).not.toBe(send.mock.calls[0][2].headers['Idempotency-Key']);
  next.unmount();
});

test('another actor cannot reuse the former actor command identity after remount', async () => {
  send.mockRejectedValueOnce({ isAxiosError: true }).mockResolvedValueOnce({ data: {} });
  const first = renderHook(() => useSocialMutation(), { wrapper });
  await act(async () => { await expect(first.result.current.run(path, body, decode)).rejects.toBeDefined(); });
  first.unmount(); actor = '00000000-0000-4000-8000-000000000099';
  const next = renderHook(() => useSocialMutation(), { wrapper });
  await act(async () => { await next.result.current.run(path, body, decode); });
  expect(send.mock.calls[1][2].headers['Idempotency-Key']).not.toBe(send.mock.calls[0][2].headers['Idempotency-Key']);
  next.unmount();
});

test.each(['read', 'write', 'silent write'])('a journal %s failure refuses a command before external submission', async mode => {
  send.mockResolvedValue({ data: {} });
  const originalGet = Storage.prototype.getItem, originalSet = Storage.prototype.setItem;
  if (mode === 'read') jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Storage denied'); });
  if (mode === 'write') jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage denied'); });
  if (mode === 'silent write') jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => undefined);
  try {
    const view = renderHook(() => useSocialMutation(), { wrapper });
    await act(async () => { await expect(view.result.current.run(path, body, decode)).rejects.toBeDefined(); });
    expect(send).not.toHaveBeenCalled(); view.unmount();
  } finally { Storage.prototype.getItem = originalGet; Storage.prototype.setItem = originalSet; }
});

test('a changed command body does not borrow the unresolved original key', async () => {
  send.mockRejectedValueOnce({ isAxiosError: true }).mockResolvedValueOnce({ data: {} });
  const first = renderHook(() => useSocialMutation(), { wrapper });
  await act(async () => { await expect(first.result.current.run(path, body, decode)).rejects.toBeDefined(); });
  first.unmount();
  const next = renderHook(() => useSocialMutation(), { wrapper });
  await act(async () => { await next.result.current.run(path, { ...body, expected_version: 3 }, decode); });
  expect(send.mock.calls[1][2].headers['Idempotency-Key']).not.toBe(send.mock.calls[0][2].headers['Idempotency-Key']);
  next.unmount();
});

test('corrupted retained recovery data refuses a command before sending', async () => {
  send.mockRejectedValueOnce({ isAxiosError: true }).mockResolvedValueOnce({ data: {} });
  const first = renderHook(() => useSocialMutation(), { wrapper });
  await act(async () => { await expect(first.result.current.run(path, body, decode)).rejects.toBeDefined(); });
  first.unmount();
  expect(sessionStorage.length).toBeGreaterThan(0);
  for (let i = 0; i < sessionStorage.length; i++) sessionStorage.setItem(sessionStorage.key(i)!, '{bad json');
  const next = renderHook(() => useSocialMutation(), { wrapper });
  await act(async () => { await expect(next.result.current.run(path, body, decode)).rejects.toBeDefined(); });
  expect(send).toHaveBeenCalledTimes(1); next.unmount();
});
