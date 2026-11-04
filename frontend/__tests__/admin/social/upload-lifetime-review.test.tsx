import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MediaUpload from '@/components/admin/social/media/MediaUpload';
import { putMediaFile, socialMediaApi, MediaAsset, MediaCapabilities, UploadGrant } from '@/lib/api/socialMedia';
import '../../../tests/socialRecoveryCrypto';

let actor = '00000000-0000-4000-8000-000000000001', allowed = true;
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: allowed }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: actor } }) }));
jest.mock('@/lib/api/socialMedia', () => ({ socialMediaApi: { initiate: jest.fn(), complete: jest.fn() }, putMediaFile: jest.fn() }));
const initiate = socialMediaApi.initiate as jest.Mock, complete = socialMediaApi.complete as jest.Mock, put = putMediaFile as jest.Mock;
const caps: MediaCapabilities = { upload_available: true, library_available: true, allowed_mime_types: ['image/png'], max_image_bytes: 10485760, max_video_bytes: 52428800, unavailable_reason: null };
const pending: MediaAsset = { id: '00000000-0000-4000-8000-000000000101', version: 1, filename: 'proof.png', state: 'pending', mime_type: null, byte_size: null, sha256: null, width: null, height: null, duration_ms: null, default_alt_text: 'Fixture proof', safe_error: null, created_at: '2026-11-04T00:00:00Z' };
const ready: MediaAsset = { ...pending, version: 2, state: 'ready', mime_type: 'image/png', byte_size: 4, sha256: 'a'.repeat(64), width: 2, height: 2 };
const grant: UploadGrant = { asset: pending, method: 'PUT', url: 'https://fixture.invalid/no-network', headers: { 'Content-Type': 'image/png', 'If-None-Match': '*' }, expires_at: '2027-01-01T00:00:00Z' };
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; }
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }), select = jest.fn();
  const tree = (contextKey: string) => <QueryClientProvider client={client}><MediaUpload capabilities={caps} contextKey={contextKey} onSelect={select} onClose={jest.fn()} onBusy={jest.fn()} /></QueryClientProvider>;
  const view = render(tree('original'));
  return { ...view, select, change: (context = 'original') => view.rerender(tree(context)) };
}
function begin() {
  fireEvent.change(screen.getByLabelText('Media file'), { target: { files: [new File(['data'], 'proof.png', { type: 'image/png', lastModified: 1 })] } });
  fireEvent.click(screen.getByRole('button', { name: 'Upload and inspect' }));
}
beforeEach(() => { actor = '00000000-0000-4000-8000-000000000001'; allowed = true; jest.clearAllMocks(); sessionStorage.clear(); initiate.mockResolvedValue(grant); put.mockResolvedValue(undefined); complete.mockResolvedValue(ready); });

test.each(['actor', 'context', 'permission', 'unmount'])('%s invalidation during initiation prevents PUT and completion', async kind => {
  const gate = deferred<UploadGrant>(); initiate.mockReturnValue(gate.promise);
  const view = mount(); begin(); await waitFor(() => expect(initiate).toHaveBeenCalledTimes(1));
  if (kind === 'actor') actor = '00000000-0000-4000-8000-000000000099';
  if (kind === 'permission') allowed = false;
  if (kind === 'unmount') view.unmount(); else view.change(kind === 'context' ? 'different' : 'original');
  await act(async () => { gate.resolve(grant); });
  expect(put).not.toHaveBeenCalled(); expect(complete).not.toHaveBeenCalled(); expect(view.select).not.toHaveBeenCalled();
  const journal = JSON.parse(sessionStorage.getItem('auditgava.social.uploads.v1:00000000-0000-4000-8000-000000000001')!);
  expect(journal.entries).toHaveLength(1);
});

test.each(['actor', 'context', 'permission', 'unmount'])('%s invalidation aborts the in-flight PUT and prevents completion', async kind => {
  const gate = deferred<void>(); put.mockReturnValue(gate.promise);
  const view = mount(); begin(); await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
  const signal = put.mock.calls[0][2] as AbortSignal | undefined;
  if (kind === 'actor') actor = '00000000-0000-4000-8000-000000000099';
  if (kind === 'permission') allowed = false;
  if (kind === 'unmount') view.unmount(); else view.change(kind === 'context' ? 'different' : 'original');
  expect(signal?.aborted).toBe(true);
  await act(async () => { gate.resolve(); });
  expect(complete).not.toHaveBeenCalled(); expect(view.select).not.toHaveBeenCalled();
});

test('a transient progress-write failure after initiation can retry in the same panel with its original command', async () => {
  const original = Storage.prototype.setItem; let failed = false;
  jest.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key, value) {
    if (!failed && key.startsWith('auditgava.social.uploads.') && JSON.parse(value).entries?.[0]?.assetId) { failed = true; throw new Error('one transient write refusal'); }
    return original.call(this, key, value);
  });
  try {
    const view = mount(); begin(); await screen.findByRole('alert');
    const key = initiate.mock.calls[0][1];
    fireEvent.click(screen.getByRole('button', { name: 'Retry this upload' }));
    await waitFor(() => expect(view.select).toHaveBeenCalledWith(ready));
    expect(initiate).toHaveBeenCalledTimes(1); expect(initiate.mock.calls[0][1]).toBe(key); expect(put).toHaveBeenCalledTimes(1);
  } finally { Storage.prototype.setItem = original; }
});

test('a transient stored-progress failure retries completion without repeating PUT', async () => {
  const original = Storage.prototype.setItem; let failed = false;
  jest.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key, value) {
    if (!failed && key.startsWith('auditgava.social.uploads.') && JSON.parse(value).entries?.[0]?.stored) { failed = true; throw new Error('one transient write refusal'); }
    return original.call(this, key, value);
  });
  try {
    const view = mount(); begin(); await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Retry this upload' }));
    await waitFor(() => expect(view.select).toHaveBeenCalledWith(ready));
    expect(put).toHaveBeenCalledTimes(1); expect(complete).toHaveBeenCalledTimes(1);
  } finally { Storage.prototype.setItem = original; }
});

test('an old actor cannot resume after an A-to-B-to-A session transition', async () => {
  const gate = deferred<UploadGrant>(); initiate.mockReturnValue(gate.promise);
  const view = mount(); begin(); await waitFor(() => expect(initiate).toHaveBeenCalledTimes(1));
  actor = '00000000-0000-4000-8000-000000000099'; view.change();
  actor = '00000000-0000-4000-8000-000000000001'; view.change();
  await act(async () => { gate.resolve(grant); });
  expect(put).not.toHaveBeenCalled(); expect(complete).not.toHaveBeenCalled();
});

test.each(['actor', 'context', 'permission', 'unmount'])('%s invalidation during inspection retains the original completion identity without selecting media', async kind => {
  const gate=deferred<MediaAsset>(); complete.mockReturnValue(gate.promise);
  const view=mount(); begin(); await waitFor(()=>expect(complete).toHaveBeenCalledTimes(1));
  const signal=complete.mock.calls[0][3] as AbortSignal;
  if(kind==='actor')actor='00000000-0000-4000-8000-000000000002';if(kind==='permission')allowed=false;
  if(kind==='unmount')view.unmount();else view.change(kind==='context'?'different':'original');
  expect(signal.aborted).toBe(true); await act(async()=>gate.resolve(ready));
  expect(view.select).not.toHaveBeenCalled();
  const journal=JSON.parse(sessionStorage.getItem('auditgava.social.uploads.v1:00000000-0000-4000-8000-000000000001')!);
  expect(journal.entries[0].completeKey).toBe(complete.mock.calls[0][2]); expect(journal.entries[0].stored).toBe(true);
});
