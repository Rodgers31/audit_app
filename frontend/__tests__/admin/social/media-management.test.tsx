import MediaPicker from '@/components/admin/social/media/MediaPicker';
import api from '@/lib/api/axios';
import { decodeMediaUsage } from '@/lib/api/socialMedia';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
jest.mock('@/components/admin/social/media/AssetPreview', () => ({ __esModule: true, default: () => <span>Private preview</span>, assetMetadata: () => 'PNG' }));
const id = '00000000-0000-4000-8000-000000000101';
const asset = { id, version: 3, filename: 'proof.png', state: 'ready', mime_type: 'image/png', byte_size: 4, sha256: 'a'.repeat(64), width: 2, height: 2, duration_ms: null, default_alt_text: null, safe_error: null, created_at: '2026-10-18T00:00:00Z' };
function usage() { return { asset, references: [], total: 0, page: 1, page_size: 20, has_more: false, archive_eligible: true, archive_reason: 'Objects and quota remain retained.' }; }
const get = api.get as jest.Mock, post = api.post as jest.Mock;
let qc: QueryClient;
beforeEach(() => {
  jest.clearAllMocks(); qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => '00000000-0000-4000-8000-000000000099' });
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/usage') ? usage() : { assets: [asset], total: 1, page: 1, page_size: 20, has_more: false } }));
  post.mockResolvedValue({ data: { ...asset, state: 'archived', version: 4 } });
});
afterEach(() => qc.clear());
function mount(selected: string[] = []) { render(<QueryClientProvider client={qc}><MediaPicker selected={selected} onSelect={jest.fn()} onClose={jest.fn()} /></QueryClientProvider>); }

test('usage detail and explicit archive preserve the original command on ambiguous retry', async () => {
  post.mockRejectedValueOnce(new Error('lost reply'));
  mount(); fireEvent.click(await screen.findByRole('button', { name: 'View usage for proof.png' }));
  expect(await screen.findByText('Used by 0 historical revisions')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Archive unused asset' }));
  fireEvent.change(screen.getByLabelText('Archive reason'), { target: { value: 'Unused editorial asset' } });
  fireEvent.click(screen.getByRole('button', { name: 'Confirm asset archive' }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Confirm asset archive' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Confirm asset archive' }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[0][2].headers['Idempotency-Key']).toBe(post.mock.calls[1][2].headers['Idempotency-Key']);
  expect(await screen.findByText(/Asset archived. Objects, quota and history are retained/)).toBeInTheDocument();
});

test('a locally selected asset cannot be archived from the picker', async () => {
  mount([id]); fireEvent.click(await screen.findByRole('button', { name: 'View usage for proof.png' }));
  expect(await screen.findByRole('button', { name: 'Archive unused asset' })).toBeDisabled();
  expect(post).not.toHaveBeenCalled();
});

test('regressed same-asset usage cannot regain archive authority', async () => {
  let reads = 0;
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/usage') ? (++reads === 1 ? { ...usage(), asset: { ...asset, version: 4 }, archive_eligible: false } : usage()) : { assets: [asset], total: 1, page: 1, page_size: 20, has_more: false } }));
  mount(); fireEvent.click(await screen.findByRole('button', { name: 'View usage for proof.png' }));
  expect(await screen.findByRole('button', { name: 'Archive unused asset' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Refresh usage' }));
  await waitFor(() => expect(reads).toBe(2));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh usage' })).toBeEnabled());
  expect(screen.getByRole('button', { name: 'Archive unused asset' })).toBeDisabled();
});

test.each([{ ...usage(), archive_eligible: true, total: 1 }, { ...usage(), has_more: true }, { ...usage(), page_size: true }, { ...usage(), extra: 'not allowed' }])('usage parser rejects malformed or inconsistent metadata', input => {
  expect(() => decodeMediaUsage(input)).toThrow();
});
