import SocialComposer from '@/components/admin/social/SocialComposer';
import api from '@/lib/api/axios';
import { SocialPost } from '@/lib/api/social';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { accounts, actorId, facebookId, instagramId, post, system, validation } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
const get = api.get as jest.Mock, send = api.post as jest.Mock, patch = api.patch as jest.Mock;
const mediaId = '00000000-0000-4000-8000-000000000101';
let saved: SocialPost, finish: (value: unknown) => void, qc: QueryClient;
const originalFetch = global.fetch;
function asset() { return { id: mediaId, version: 2, filename: 'proof.png', state: 'ready', mime_type: 'image/png', byte_size: 4, sha256: 'a'.repeat(64), width: 2, height: 2, duration_ms: null, default_alt_text: 'Evidence description', safe_error: null, created_at: new Date().toISOString() }; }
function grant() {
  const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  const url = `https://${'a'.repeat(32)}.r2.cloudflarestorage.com/media-test/quarantine/${actorId}/${mediaId}/source?${new URLSearchParams({ 'X-Amz-Algorithm': 'AWS4-HMAC-SHA256', 'X-Amz-Credential': `fake/${stamp.slice(0,8)}/auto/s3/aws4_request`, 'X-Amz-Date': stamp, 'X-Amz-Expires': '300', 'X-Amz-SignedHeaders': 'host;content-length;content-type;if-none-match', 'X-Amz-Signature': 'b'.repeat(64) })}`;
  return { asset: { ...asset(), state: 'pending', version: 1, mime_type: null, byte_size: null, sha256: null, width: null, height: null }, method: 'PUT', url, headers: { 'Content-Type': 'image/png', 'If-None-Match': '*' }, expires_at: new Date(Date.now() + 299000).toISOString() };
}
function mount(p = post()) {
  saved = p; qc.setQueryData(socialKeys.detail(actorId, p.id), p);
  render(<QueryClientProvider client={qc}><SocialComposer initialPost={p} accounts={accounts} system={system} /></QueryClientProvider>);
}
async function upload(index: number) {
  await waitFor(() => expect(screen.getAllByRole('button', { name: 'Upload media' })[index]).toBeEnabled());
  fireEvent.click(screen.getAllByRole('button', { name: 'Upload media' })[index]);
  fireEvent.change(screen.getByLabelText('Media file'), { target: { files: [new File(['data'], 'proof.png', { type: 'image/png' })] } });
  fireEvent.click(screen.getByRole('button', { name: 'Upload and inspect' }));
  await waitFor(() => expect(send.mock.calls.some(call => call[0].endsWith('/complete'))).toBe(true));
}
beforeEach(() => {
  jest.clearAllMocks(); saved = post(); qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => `00000000-0000-4000-8000-${String(Math.random()).slice(2).padEnd(12,'0').slice(0,12)}` });
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/media/capabilities') ? { upload_available: true, library_available: true, allowed_mime_types: ['image/png'], max_image_bytes: 10485760, max_video_bytes: 52428800, unavailable_reason: null } : saved }));
  send.mockImplementation((path: string) => path.endsWith('/media/uploads') ? Promise.resolve({ data: grant() }) : path.endsWith('/complete') ? new Promise(resolve => { finish = resolve; }) : Promise.resolve({ data: validation(saved) }));
  patch.mockImplementation(async (_path, body) => { saved = post({ ...body, version: saved.version + 1, revision_id: '00000000-0000-4000-8000-000000000042' }); return { data: saved }; });
  global.fetch = jest.fn().mockResolvedValue({ ok: true, status: 200 });
});
afterEach(() => { qc.clear(); global.fetch = originalFetch; });

test('pending media blocks publication commands and completion preserves current text and overrides', async () => {
  mount(); fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Publish now' })).toBeEnabled());
  await upload(0);
  expect(screen.getByRole('button', { name: 'Publish now' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Save & validate' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Duplicate as new manual draft' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Master text'), { target: { value: 'New text entered while upload was pending.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Customize text' }));
  fireEvent.change(screen.getByLabelText('Account text'), { target: { value: 'A newer Facebook override.' } });
  expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
  await act(async () => finish({ data: asset() }));
  await screen.findByLabelText('Master media 1 alt text');
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
  const document = patch.mock.calls[0][1].document;
  expect(document.master.text).toBe('New text entered while upload was pending.');
  expect(document.targets[0].overrides.text).toEqual({ mode: 'replace', value: 'A newer Facebook override.' });
  expect(document.master.media).toEqual([{ asset_id: mediaId, alt_text: 'Evidence description', caption_asset_id: null }]);
  expect(JSON.stringify(document)).not.toMatch(/X-Amz|cloudflarestorage/);
});

test('switching account while an override uploads never attaches that asset to the new account', async () => {
  const p = post({ document: { ...post().document, targets: [facebookId, instagramId].map(account_id => ({ account_id, format: 'image' as const, overrides: { media: { mode: 'replace' as const, value: [] } } })) } });
  mount(p); await upload(1);
  fireEvent.click(screen.getByRole('button', { name: 'Instagram · AuditGava test Instagram' }));
  await act(async () => finish({ data: asset() }));
  await waitFor(() => expect(screen.queryByText('Inspecting actual media bytes…')).not.toBeInTheDocument());
  expect(screen.queryByLabelText('Account media 1 alt text')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Master text'), { target: { value: 'Save the explicitly empty account overrides.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
  expect(patch.mock.calls[0][1].document.targets.map((t: { overrides: object }) => t.overrides)).toEqual([{ media: { mode: 'replace', value: [] } }, { media: { mode: 'replace', value: [] } }]);
});
