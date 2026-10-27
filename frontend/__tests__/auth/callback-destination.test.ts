/** @jest-environment node */
import { GET } from '@/app/auth/callback/route';

const mockExchange = jest.fn();
const mockCookieStore = { getAll: jest.fn<{ name: string; value: string }[], []>(() => []), set: jest.fn() };
jest.mock('@/lib/supabase/server', () => ({
  createClient: jest.fn(async () => ({ auth: { exchangeCodeForSession: mockExchange } })),
}));
jest.mock('next/headers', () => ({ cookies: jest.fn(async () => mockCookieStore) }));

beforeEach(() => {
  mockExchange.mockReset().mockResolvedValue({ error: null });
  mockCookieStore.getAll.mockReset().mockReturnValue([]);
});

test.each(['@elsewhere.invalid', ':443@elsewhere.invalid', '//elsewhere.invalid',
  '/\\elsewhere.invalid', 'https://elsewhere.invalid', '\n@elsewhere.invalid'])
('successful exchange keeps destination %p on the app origin', async (next) => {
  const query = new URLSearchParams({ code: 'inert-code', next });
  const response = await GET(new Request(`https://app.example.invalid/auth/callback?${query}`));
  const location = new URL(response.headers.get('location')!);
  expect(location.origin).toBe('https://app.example.invalid');
  expect(location.pathname).toBe('/');
  expect(response.headers.get('cache-control')).toBe('private, no-store');
  expect(response.headers.get('referrer-policy')).toBe('no-referrer');
});

test('normal relative destination keeps path, query and fragment', async () => {
  const query = new URLSearchParams({ code: 'inert-code', next: '/account?tab=watchlist#items' });
  const response = await GET(new Request(`https://app.example.invalid/auth/callback?${query}`));
  expect(response.headers.get('location')).toBe('https://app.example.invalid/account?tab=watchlist#items');
  expect(mockExchange).toHaveBeenCalledWith('inert-code');
});

test('recovery stages inert code and clears session without exchanging it', async () => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://fixture.supabase.invalid';
  mockCookieStore.getAll.mockReturnValue([{ name: 'sb-fixture-auth-token-code-verifier', value: 'INERT_VERIFIER' }]);
  const response = await GET(new Request('https://app.example.invalid/auth/callback?code=inert-code&next=/reset-password'));
  expect(new URL(response.headers.get('location')!).pathname).toBe('/reset-password');
  expect(new URL(response.headers.get('location')!).hash).toMatch(/^#recovery-flow=[a-f0-9]{32}$/);
  expect(mockExchange).not.toHaveBeenCalled();
  expect(response.headers.get('cache-control')).toBe('private, no-store');
  expect(response.headers.get('referrer-policy')).toBe('no-referrer');
});
