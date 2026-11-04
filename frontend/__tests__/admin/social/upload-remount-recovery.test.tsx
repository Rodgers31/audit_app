import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MediaUpload from '@/components/admin/social/media/MediaUpload';
import { putMediaFile, socialMediaApi, MediaAsset, MediaCapabilities, UploadGrant } from '@/lib/api/socialMedia';
import { SocialApiError } from '@/lib/api/social';

jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: actor } }) }));
jest.mock('@/lib/api/socialMedia', () => ({ socialMediaApi: { initiate: jest.fn(), complete: jest.fn() }, putMediaFile: jest.fn() }));
let actor = '00000000-0000-4000-8000-000000000001';
const initiate = socialMediaApi.initiate as jest.Mock;
const complete = socialMediaApi.complete as jest.Mock;
const put = putMediaFile as jest.Mock;
const caps: MediaCapabilities = { upload_available: true, library_available: true, allowed_mime_types: ['image/png'], max_image_bytes: 10485760, max_video_bytes: 52428800, unavailable_reason: null };
const pending: MediaAsset = { id: '00000000-0000-4000-8000-000000000101', version: 1, filename: 'proof.png', state: 'pending', mime_type: null, byte_size: null, sha256: null, width: null, height: null, duration_ms: null, default_alt_text: 'Fixture proof', safe_error: null, created_at: '2026-11-04T00:00:00Z' };
const ready: MediaAsset = { ...pending, version: 2, state: 'ready', mime_type: 'image/png', byte_size: 4, sha256: 'a'.repeat(64), width: 2, height: 2 };
const grant: UploadGrant = { asset: pending, method: 'PUT', url: 'https://fixture.invalid/no-network', headers: { 'Content-Type': 'image/png', 'If-None-Match': '*' }, expires_at: '2027-01-01T00:00:00Z' };
const failed = () => new SocialApiError('MEDIA_UPLOAD_UNCONFIRMED', 'Ambiguous inert upload response', [], [], true);
function mount(contextKey = 'owned-composer') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const select = jest.fn();
  const mounted = render(<QueryClientProvider client={client}><MediaUpload capabilities={caps} contextKey={contextKey} onSelect={select} onClose={jest.fn()} onBusy={jest.fn()} /></QueryClientProvider>);
  return { ...mounted, select };
}
function chooseAndUpload(contents = 'data') {
  fireEvent.change(screen.getByLabelText('Media file'), { target: { files: [new File([contents], 'proof.png', { type: 'image/png', lastModified: 1 })] } });
  fireEvent.change(screen.getByLabelText('Default media alt text'), { target: { value: 'Fixture proof' } });
  fireEvent.click(screen.getByRole('button', { name: 'Upload and inspect' }));
}
beforeEach(() => { actor = '00000000-0000-4000-8000-000000000001'; jest.clearAllMocks(); sessionStorage.clear(); initiate.mockResolvedValue(grant); complete.mockResolvedValue(ready); put.mockResolvedValue(undefined); });

test('ambiguous upload initiation keeps its original identity after the upload panel remounts', async () => {
  initiate.mockRejectedValueOnce(failed());
  const first = mount(); chooseAndUpload();
  await screen.findByRole('alert'); const key = initiate.mock.calls[0][1];
  first.unmount(); const second = mount(); chooseAndUpload();
  await waitFor(() => expect(second.select).toHaveBeenCalledWith(ready));
  expect(initiate.mock.calls[1][0]).toEqual(initiate.mock.calls[0][0]);
  expect(initiate.mock.calls[1][1]).toBe(key);
});

test('ambiguous completion preserves both original command identities after the upload panel remounts', async () => {
  complete.mockRejectedValueOnce(failed());
  const first = mount(); chooseAndUpload();
  await screen.findByRole('alert'); const initiateKey = initiate.mock.calls[0][1], completeKey = complete.mock.calls[0][2];
  first.unmount(); const second = mount(); chooseAndUpload();
  await waitFor(() => expect(second.select).toHaveBeenCalledWith(ready));
  if (initiate.mock.calls.length > 1) expect(initiate.mock.calls[1][1]).toBe(initiateKey);
  else expect(initiate).toHaveBeenCalledTimes(1);
  expect(complete.mock.calls[1][2]).toBe(completeKey);
});

test('the same mounted panel retries uncertain completion with the original identity and without repeating PUT', async () => {
  complete.mockRejectedValueOnce(failed());
  const view = mount(); chooseAndUpload();
  await screen.findByRole('alert'); const key = complete.mock.calls[0][2];
  fireEvent.click(screen.getByRole('button', { name: 'Retry this upload' }));
  await waitFor(() => expect(view.select).toHaveBeenCalledWith(ready));
  expect(initiate).toHaveBeenCalledTimes(1); expect(put).toHaveBeenCalledTimes(1);
  expect(complete.mock.calls[1][2]).toBe(key);
});

test('different original bytes with identical file metadata never reuse an uncertain upload identity', async () => {
  initiate.mockRejectedValueOnce(failed());
  const first = mount(); chooseAndUpload('data');
  await screen.findByRole('alert'); const key = initiate.mock.calls[0][1];
  first.unmount(); const second = mount(); chooseAndUpload('evil');
  await waitFor(() => expect(second.select).toHaveBeenCalledWith(ready));
  expect(initiate.mock.calls[1][0]).toEqual(initiate.mock.calls[0][0]);
  expect(initiate.mock.calls[1][1]).not.toBe(key);
});

test.each(['actor', 'context'])('a different %s never borrows the interrupted upload command', async changed => {
  initiate.mockRejectedValueOnce(failed());
  const first = mount(); chooseAndUpload();
  await screen.findByRole('alert'); const key = initiate.mock.calls[0][1];
  first.unmount();
  if (changed === 'actor') actor = '00000000-0000-4000-8000-000000000099';
  const second = mount(changed === 'context' ? 'another-composer' : 'owned-composer'); chooseAndUpload();
  await waitFor(() => expect(second.select).toHaveBeenCalledWith(ready));
  expect(initiate.mock.calls[1][1]).not.toBe(key);
});

test.each(['write denied', 'write silently dropped'])('upload journal %s refuses before initiating or putting bytes', async mode => {
  const original = Storage.prototype.setItem;
  jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { if (mode === 'write denied') throw new Error('Storage denied'); });
  try {
    mount(); chooseAndUpload();
    await screen.findByRole('alert');
    expect(initiate).not.toHaveBeenCalled(); expect(put).not.toHaveBeenCalled(); expect(complete).not.toHaveBeenCalled();
  } finally { Storage.prototype.setItem = original; }
});
import '../../../tests/socialRecoveryCrypto';
