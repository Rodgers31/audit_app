/** @jest-environment node */
import { GET } from '@/app/auth/callback/route';

const exchange = jest.fn();
const cookieStore = { getAll: jest.fn(() => []), set: jest.fn() };
jest.mock('@/lib/supabase/server', () => ({
  createClient: jest.fn(async () => ({ auth: { exchangeCodeForSession: exchange } })),
}));
jest.mock('next/headers', () => ({ cookies: jest.fn(async () => cookieStore) }));

beforeEach(() => {
  exchange.mockReset().mockResolvedValue({ error: null });
  cookieStore.getAll.mockReset().mockReturnValue([]);
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
  expect(exchange).toHaveBeenCalledWith('inert-code');
});

test('recovery forwards inert code and clears session without exchanging it', async () => {
  const response = await GET(new Request('https://app.example.invalid/auth/callback?code=inert-code&next=/reset-password'));
  expect(response.headers.get('location')).toBe('https://app.example.invalid/reset-password?recovery=inert-code');
  expect(exchange).not.toHaveBeenCalled();
  expect(response.headers.get('cache-control')).toBe('private, no-store');
  expect(response.headers.get('referrer-policy')).toBe('no-referrer');
});
