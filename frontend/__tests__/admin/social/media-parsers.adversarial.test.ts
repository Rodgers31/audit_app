import api from '@/lib/api/axios';
import {
  decodeMediaAsset, decodeMediaCapabilities, decodeMediaLibrary, decodeMediaPreview,
  decodeUploadGrant, putMediaFile, socialMediaApi, storageUrl, UploadGrant,
} from '@/lib/api/socialMedia';
import { SocialApiError } from '@/lib/api/social';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));

const now = Date.parse('2026-10-03T12:00:00Z');
const assetId = '00000000-0000-4000-8000-000000000101';
const otherId = '00000000-0000-4000-8000-000000000102';
const actorId = '00000000-0000-4000-8000-000000000103';
const endpoint = `https://${'a'.repeat(32)}.r2.cloudflarestorage.com`;
const pending = {
  id: assetId, version: 1, filename: 'proof.png', state: 'pending', mime_type: null,
  byte_size: null, sha256: null, width: null, height: null, duration_ms: null,
  default_alt_text: null, safe_error: null, created_at: '2026-10-03T12:00:00Z',
};
const ready = {
  ...pending, version: 2, state: 'ready', mime_type: 'image/png', byte_size: 4,
  sha256: 'b'.repeat(64), width: 2, height: 2,
};
const capabilities = {
  upload_available: true, library_available: true,
  allowed_mime_types: ['image/png'], max_image_bytes: 10 * 1024 * 1024,
  max_video_bytes: 50 * 1024 * 1024, unavailable_reason: null,
};
function signedUrl(upload = false): string {
  const path = upload ? `quarantine/${actorId}/${assetId}/source` : `ready/${assetId}/original`;
  const query = new URLSearchParams({
    'X-Amz-Algorithm': 'AWS4-HMAC-SHA256',
    'X-Amz-Credential': 'fixture-access/20261003/auto/s3/aws4_request',
    'X-Amz-Date': '20261003T120000Z', 'X-Amz-Expires': '300',
    'X-Amz-SignedHeaders': upload ? 'content-length;content-type;host;if-none-match' : 'host',
    'X-Amz-Signature': 'c'.repeat(64),
  });
  return `${endpoint}/private-media/${path}?${query}`;
}
function grant(): UploadGrant {
  return {
    asset: { ...pending, state: 'pending' }, method: 'PUT', url: signedUrl(true),
    headers: { 'Content-Type': 'image/png', 'If-None-Match': '*' },
    expires_at: '2026-10-03T12:05:00Z',
  };
}
function preview() { return { asset: ready, url: signedUrl(), expires_at: '2026-10-03T12:05:00Z' }; }
function library() { return { assets: [ready], total: 1, page: 1, page_size: 20, has_more: false }; }
function mutateUrl(upload: boolean, change: (u: URL) => void): string {
  const url = new URL(signedUrl(upload)); change(url); return url.toString();
}
const apiGet = api.get as jest.Mock;
const apiPost = api.post as jest.Mock;
const originalFetch = global.fetch;
let fetchMock: jest.Mock;
beforeEach(() => {
  jest.spyOn(Date, 'now').mockReturnValue(now);
  apiGet.mockReset(); apiPost.mockReset();
  fetchMock = jest.fn().mockResolvedValue({ ok: true, status: 200 });
  global.fetch = fetchMock;
});
afterEach(() => { jest.restoreAllMocks(); global.fetch = originalFetch; });

test('positive complete payloads and signed upload/preview baselines are alive', () => {
  expect(decodeMediaAsset(ready)).toEqual(ready);
  expect(decodeMediaCapabilities(capabilities)).toEqual(capabilities);
  expect(decodeMediaLibrary(library())).toEqual(library());
  expect(decodeUploadGrant(grant())).toEqual(grant());
  expect(decodeMediaPreview(preview())).toEqual(preview());
});

test.each([
  ['asset', () => ready, decodeMediaAsset],
  ['capabilities', () => capabilities, decodeMediaCapabilities],
  ['library', library, decodeMediaLibrary],
  ['preview', preview, decodeMediaPreview],
  ['grant', grant, decodeUploadGrant],
] as const)('%s rejects unknown fields and missing serialized fields', (_name, fixture, decoder) => {
  const body = fixture();
  expect(() => decoder({ ...body, arbitrary_secret: 'fixture' })).toThrow(SocialApiError);
  for (const field of Object.keys(body)) {
    const missing: Record<string, unknown> = { ...body }; delete missing[field];
    expect(() => decoder(missing)).toThrow(SocialApiError);
  }
});

test.each(['version', 'byte_size', 'width', 'height', 'duration_ms'])('ready asset rejects hostile %s numbers', field => {
  for (const value of [true, false, NaN, Infinity, -Infinity, '4', 0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
    expect(() => decodeMediaAsset({ ...ready, [field]: value })).toThrow(SocialApiError);
  }
});
test.each(['', '   ', '../proof.png', 'proof\n.png'])('asset filename rejects impossible initiation metadata %p', filename => {
  expect(() => decodeMediaAsset({ ...ready, filename })).toThrow(SocialApiError);
});
test('readiness cannot be inferred from incomplete or incompatible inspection metadata', () => {
  for (const patch of [
    { sha256: null }, { mime_type: null }, { byte_size: null }, { width: null }, { height: null },
    { width: 10000, height: 10000 }, { mime_type: 'video/mp4', duration_ms: null },
    { duration_ms: 1000 }, { byte_size: 10 * 1024 * 1024 + 1 },
  ]) expect(() => decodeMediaAsset({ ...ready, ...patch })).toThrow(SocialApiError);
});
test('capability limits and flags reject booleans, NaN, infinity and oversized limits', () => {
  for (const field of ['max_image_bytes', 'max_video_bytes']) {
    for (const value of [true, false, NaN, Infinity, 0, -1, 1.5, 50 * 1024 * 1024 + 1]) {
      expect(() => decodeMediaCapabilities({ ...capabilities, [field]: value })).toThrow(SocialApiError);
    }
  }
  expect(() => decodeMediaCapabilities({ ...capabilities, upload_available: 'false' })).toThrow(SocialApiError);
  expect(() => decodeMediaCapabilities({ ...capabilities, upload_available: false })).toThrow(SocialApiError);
  expect(() => decodeMediaCapabilities({ ...capabilities, allowed_mime_types: ['image/png', 'image/png'] })).toThrow(SocialApiError);
});
test('disabled uploads with a usable library remain a valid capability response', () => {
  expect(decodeMediaCapabilities({ ...capabilities, upload_available: false, allowed_mime_types: [], unavailable_reason: 'Inspectors unavailable.' })).toMatchObject({ upload_available: false, library_available: true });
});
test('library cannot certify nonready, duplicate, empty or mismatched result counts', () => {
  for (const patch of [
    { assets: [{ ...ready, state: 'pending' }] }, { assets: [ready, ready], total: 2 },
    { assets: [] }, { total: 2 }, { has_more: true }, { total: NaN }, { page: true },
  ]) expect(() => decodeMediaLibrary({ ...library(), ...patch })).toThrow(SocialApiError);
  expect(decodeMediaLibrary({ ...library(), assets: [], total: 0 })).toMatchObject({ assets: [], total: 0 });
});

test.each([
  ['http', (u: URL) => { u.protocol = 'http:'; }],
  ['foreign host', (u: URL) => { u.hostname = 'example.org'; }],
  ['userinfo', (u: URL) => { u.username = 'fixture'; u.password = 'fixture'; }],
  ['port', (u: URL) => { u.port = '8443'; }],
  ['fragment', (u: URL) => { u.hash = 'fixture'; }],
  ['no signature', (u: URL) => { u.searchParams.delete('X-Amz-Signature'); }],
] as const)('storage URL rejects %s', (_name, change) => {
  expect(() => storageUrl(mutateUrl(false, change))).toThrow(SocialApiError);
});

const signingAttacks: Array<[string, (u: URL) => void]> = [
  ['nonhex signature', u => { u.searchParams.set('X-Amz-Signature', 'not-a-signature'); }],
  ['short signature', u => { u.searchParams.set('X-Amz-Signature', 'c'); }],
  ['missing credential', u => { u.searchParams.delete('X-Amz-Credential'); }],
  ['missing algorithm', u => { u.searchParams.delete('X-Amz-Algorithm'); }],
  ['wrong algorithm', u => { u.searchParams.set('X-Amz-Algorithm', 'UNSIGNED'); }],
  ['missing signing date', u => { u.searchParams.delete('X-Amz-Date'); }],
  ['expired signature', u => { u.searchParams.set('X-Amz-Date', '20261002T120000Z'); }],
  ['missing expiry', u => { u.searchParams.delete('X-Amz-Expires'); }],
  ['zero expiry', u => { u.searchParams.set('X-Amz-Expires', '0'); }],
  ['noninteger expiry', u => { u.searchParams.set('X-Amz-Expires', 'NaN'); }],
  ['expiry over contract', u => { u.searchParams.set('X-Amz-Expires', '999999'); }],
  ['missing signed headers', u => { u.searchParams.delete('X-Amz-SignedHeaders'); }],
  ['host not signed', u => { u.searchParams.set('X-Amz-SignedHeaders', 'content-type'); }],
  ['duplicate conflicting signature', u => { u.searchParams.append('X-Amz-Signature', 'd'.repeat(64)); }],
];
describe.each([false, true])('signed %s response', upload => {
  test.each(signingAttacks)('rejects %s', (_name, change) => {
    const value = { ...(upload ? grant() : preview()), url: mutateUrl(upload, change) };
    expect(() => upload ? decodeUploadGrant(value) : decodeMediaPreview(value)).toThrow(SocialApiError);
  });
});
test.each(['host', 'content-type;host;if-none-match', 'content-length;host;if-none-match', 'content-length;content-type;host'])('upload grant rejects unsigned required headers %s', headers => {
  const url = mutateUrl(true, u => { u.searchParams.set('X-Amz-SignedHeaders', headers); });
  expect(() => decodeUploadGrant({ ...grant(), url })).toThrow(SocialApiError);
});
test.each([
  `quarantine/${actorId}/${assetId}/source-other`,
  `quarantine/${actorId}/${assetId}/source/${otherId}/source`,
])('upload grant rejects a different storage object %s', key => {
  const url = mutateUrl(true, u => { u.pathname = `/private-media/${key}`; });
  expect(() => decodeUploadGrant({ ...grant(), url })).toThrow(SocialApiError);
});
test('preview cannot claim longer validity than its signed URL', () => {
  const url = mutateUrl(false, u => { u.searchParams.set('X-Amz-Expires', '1'); });
  expect(() => decodeMediaPreview({ ...preview(), url })).toThrow(SocialApiError);
});
test('preview rejects validity beyond the backend 300 second ceiling', () => {
  const url = mutateUrl(false, u => { u.searchParams.set('X-Amz-Expires', '600'); });
  expect(() => decodeMediaPreview({ ...preview(), url, expires_at: '2026-10-03T12:10:00Z' })).toThrow(SocialApiError);
});
test.each([' '+signedUrl(), signedUrl()+'\n', signedUrl().replace('/private-media/', '/private-\tmedia/')])('raw signed URL rejects normalized whitespace', url => {
  expect(() => storageUrl(url)).toThrow(SocialApiError);
});

test('fake API preview, completion and library responses must correlate with their request', async () => {
  apiGet.mockResolvedValueOnce({ data: { ...preview(), asset: { ...ready, id: otherId }, url: signedUrl().replace(assetId, otherId) } });
  await expect(socialMediaApi.preview(assetId)).rejects.toMatchObject({ code: 'INVALID_MEDIA_RESPONSE' });
  apiGet.mockResolvedValueOnce({ data: { ...library(), page: 2, assets: [], has_more: false } });
  await expect(socialMediaApi.library(1, '', '')).rejects.toMatchObject({ code: 'INVALID_MEDIA_RESPONSE' });
  apiPost.mockResolvedValueOnce({ data: { ...ready, version: 1 } });
  await expect(socialMediaApi.complete(assetId, 1, actorId)).rejects.toMatchObject({ code: 'INVALID_MEDIA_RESPONSE' });
  apiPost.mockResolvedValueOnce({ data: { ...ready, id: otherId } });
  await expect(socialMediaApi.complete(assetId, 1, actorId)).rejects.toMatchObject({ code: 'INVALID_MEDIA_RESPONSE' });
});
test('fake API initiation binds declared filename and MIME', async () => {
  const intent = { filename: pending.filename, declared_mime_type: 'image/png' as const, declared_size: 4, alt_text: null };
  apiPost.mockResolvedValueOnce({ data: { ...grant(), asset: { ...pending, filename: 'other.png' } } });
  await expect(socialMediaApi.initiate(intent, actorId)).rejects.toMatchObject({ code: 'INVALID_MEDIA_RESPONSE' });
  apiPost.mockResolvedValueOnce({ data: { ...grant(), headers: { ...grant().headers, 'Content-Type': 'image/jpeg' } } });
  await expect(socialMediaApi.initiate(intent, actorId)).rejects.toMatchObject({ code: 'INVALID_MEDIA_RESPONSE' });
});
test('storage PUT is isolated from authenticated API headers and cookies', async () => {
  const file = new File(['data'], pending.filename, { type: 'image/png' });
  await putMediaFile(grant(), file);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledWith(grant().url, expect.objectContaining({
    method: 'PUT', body: file, headers: { 'Content-Type': 'image/png', 'If-None-Match': '*' },
    credentials: 'omit', redirect: 'error', cache: 'no-store', mode: 'cors',
  }));
  expect(apiGet).not.toHaveBeenCalled(); expect(apiPost).not.toHaveBeenCalled();
});
test.each(['Authorization', 'Cookie', 'X-Admin-Token'])('storage PUT rejects injected %s header before fetch', header => {
  const value = { ...grant(), headers: { ...grant().headers, [header]: 'fixture-secret' } };
  return expect(putMediaFile(value, new File(['data'], pending.filename, { type: 'image/png' }))).rejects.toMatchObject({ code: 'INVALID_MEDIA_RESPONSE' });
});
test.each([true, false, NaN, Infinity, -1, 0, 1.5])('PUT rejects malformed file size %p without network', async size => {
  const file = { size, type: 'image/png', name: pending.filename } as unknown as File;
  await expect(putMediaFile(grant(), file)).rejects.toMatchObject({ code: 'INVALID_MEDIA_RESPONSE' });
  expect(fetchMock).not.toHaveBeenCalled();
});
test('PUT rejects image bytes above the image ceiling even below the video ceiling', async () => {
  const file = new File([new Uint8Array(10 * 1024 * 1024 + 1)], pending.filename, { type: 'image/png' });
  await expect(putMediaFile(grant(), file)).rejects.toMatchObject({ code: 'INVALID_MEDIA_RESPONSE' });
  expect(fetchMock).not.toHaveBeenCalled();
});
test('storage rejection and transport failure remain unconfirmed and safe to retry', async () => {
  const file = new File(['data'], pending.filename, { type: 'image/png' });
  fetchMock.mockResolvedValueOnce({ ok: false, status: 403 });
  await expect(putMediaFile(grant(), file)).rejects.toMatchObject({ code: 'MEDIA_UPLOAD_UNCONFIRMED', retryable: true });
  fetchMock.mockRejectedValueOnce(new Error('fixture-private-url-and-token'));
  await expect(putMediaFile(grant(), file)).rejects.toMatchObject({ code: 'MEDIA_UPLOAD_UNCONFIRMED', message: expect.not.stringContaining('fixture-private') });
});
test('create-only 412 permits inspection of an ambiguous previously completed upload', async () => {
  fetchMock.mockResolvedValueOnce({ ok: false, status: 412 });
  await expect(putMediaFile(grant(), new File(['data'], pending.filename, { type: 'image/png' }))).resolves.toBeUndefined();
});
