import { decodeInspectedAsset, decodePublication, decodeResolvedPostPayload, decodeValidation, SocialApiError } from '@/lib/api/social';
import { assetId, facebookId, inspectedAsset, instagramId, post, postId, publicationReceipt, resolvedPayload, validation } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));

const inspected = {
  asset_id: assetId, sha256: 'a'.repeat(64), mime_type: 'image/png', byte_size: 12345,
  width: 1200, height: 630, duration_ms: null, alt_text: 'Source evidence card',
  caption_asset_id: null, caption_sha256: null,
};
const payload = {
  schema_version: 1, account_id: facebookId, platform: 'facebook', api_product: 'fixture-page',
  external_account_id: 'fixture-external-identity', format: 'image', text: 'Evidence and context.',
  link: 'https://example.org/source', hashtags: ['#Evidence'], assets: [inspected],
  visibility: 'public', disclosures: [], capability_version: 'social-v1',
  evidence_hash: 'b'.repeat(64), content_hash: 'c'.repeat(64),
};
function envelope(resolved_preview: unknown = payload, target: object = {}, top: object = {}) {
  return { valid: true, rules_version: 'social-v1', errors: [], warnings: [], targets: [{ account_id: facebookId, platform: 'facebook', valid: true, errors: [], warnings: [], resolved_preview, ...target }], ...top };
}
function publication(status_url: unknown = `/api/v1/admin/social/posts/${postId}/status`) {
  return { post_id: postId, publication_id: '00000000-0000-4000-8000-000000000060', status: 'queued', scheduled_for: null, targets: [{ id: '00000000-0000-4000-8000-000000000050', account_id: facebookId, platform: 'facebook', status: 'queued' }], status_url };
}
function rejectsAll(values: unknown[], make: (value: unknown) => unknown) {
  const accepted: unknown[] = [];
  for (const value of values) {
    try { decodeValidation(make(value)); accepted.push(value); }
    catch (error) { expect(error).toBeInstanceOf(SocialApiError); }
  }
  expect(accepted).toEqual([]);
}

test('complete API-shaped resolved previews preserve every payload and inspected asset field', () => {
  expect(decodeValidation(envelope()).targets[0].resolved_preview).toEqual(payload);
});
test.each([null, {}, [], '', 1, true, { text: 'Incomplete preview' }])('valid target cannot be certified by incomplete preview %p', preview => {
  expect(() => decodeValidation(envelope(preview))).toThrow(SocialApiError);
});
test.each(Object.keys(payload))('resolved preview requires serialized field %s', field => {
  const missing: Record<string, unknown> = { ...payload }; delete missing[field];
  expect(() => decodeValidation(envelope(missing))).toThrow(SocialApiError);
});
test.each(Object.keys(inspected))('inspected asset requires serialized field %s', field => {
  const missing: Record<string, unknown> = { ...inspected }; delete missing[field];
  expect(() => decodeValidation(envelope({ ...payload, assets: [missing] }))).toThrow(SocialApiError);
});
test('invalid or unavailable targets retain the declared nullable preview and platform', () => {
  expect(decodeValidation(envelope(null, { platform: null, valid: false }, { valid: false })).targets[0]).toMatchObject({ platform: null, valid: false, resolved_preview: null });
  expect(decodeValidation(envelope(payload, { valid: false }, { valid: false })).targets[0].resolved_preview).toEqual(payload);
});
test('valid target preview identities must correlate with their validation row', () => {
  rejectsAll([instagramId, ''], value => envelope({ ...payload, account_id: value }));
  rejectsAll(['instagram', null], value => envelope({ ...payload, platform: value }));
  expect(() => decodeValidation(envelope(payload, { platform: null }))).toThrow(SocialApiError);
});
test('unknown preview schemas and rule versions cannot certify a valid target', () => {
  rejectsAll([undefined, null, true, '1', 0, 2, NaN, Infinity], schema_version => envelope({ ...payload, schema_version }));
  expect(() => decodeValidation(envelope(payload, {}, { rules_version: 'social-v99' }))).toThrow(SocialApiError);
});
test('resolved payload and inspected assets reject unknown fields instead of preserving arbitrary objects', () => {
  expect(() => decodeValidation(envelope({ ...payload, credential_bundle: { secret: 'fixture' } }))).toThrow(SocialApiError);
  expect(() => decodeValidation(envelope({ ...payload, assets: [{ ...inspected, signed_url: 'https://example.org/secret' }] }))).toThrow(SocialApiError);
});
test.each(['byte_size', 'width', 'height', 'duration_ms'])('inspected %s rejects hostile numeric values', field => {
  rejectsAll([undefined, true, false, '1', {}, [], NaN, Infinity, -Infinity, -1, 0, 1.5, Number.MAX_SAFE_INTEGER + 1], value => envelope({ ...payload, assets: [{ ...inspected, [field]: value }] }));
});
test('nullable asset dimensions, captions and alt text preserve null and safe integer metadata', () => {
  const nullableAsset = { ...inspected, width: null, height: null, duration_ms: null, alt_text: null };
  expect(decodeValidation(envelope({ ...payload, assets: [nullableAsset] })).targets[0].resolved_preview).toMatchObject({ assets: [nullableAsset] });
  expect(decodeValidation(envelope({ ...payload, assets: [{ ...nullableAsset, byte_size: Number.MAX_SAFE_INTEGER }] })).targets[0].resolved_preview).toMatchObject({ assets: [{ byte_size: Number.MAX_SAFE_INTEGER }] });
});
test.each(['evidence_hash', 'content_hash', 'sha256', 'caption_sha256'])('resolved %s must be an exact lowercase SHA256', field => {
  rejectsAll([undefined, '', true, NaN, 'f'.repeat(63), 'f'.repeat(65), 'A'.repeat(64), 'g'.repeat(64), `${'a'.repeat(64)}\n`], value => envelope(field === 'evidence_hash' || field === 'content_hash' ? { ...payload, [field]: value } : { ...payload, assets: [{ ...inspected, [field]: value }] }));
});
test.each(['account_id', 'asset_id', 'caption_asset_id'])('resolved %s rejects malformed UUID identities', field => {
  rejectsAll(['', 'fake-account', '00000000-0000-4000-8000', '00000000-0000-4000-8000-00000000000z'], value => envelope(field === 'account_id' ? { ...payload, account_id: value } : { ...payload, assets: [{ ...inspected, [field]: value }] }));
});
test('nonblank external identity, known format/platform and public visibility are required', () => {
  rejectsAll(['', '   ', '\n\t', true, null], value => envelope({ ...payload, external_account_id: value }));
  expect(() => decodeValidation(envelope({ ...payload, format: 'story' }))).toThrow(SocialApiError);
  expect(() => decodeValidation(envelope({ ...payload, platform: 'linkedin' }))).toThrow(SocialApiError);
  expect(() => decodeValidation(envelope({ ...payload, visibility: 'private' }))).toThrow(SocialApiError);
});
test('bounded text, hashtags, disclosures and typed asset lists match the backend contract', () => {
  expect(() => decodeValidation(envelope({ ...payload, text: 'x'.repeat(20_001) }))).toThrow(SocialApiError);
  expect(() => decodeValidation(envelope({ ...payload, hashtags: Array(51).fill('#Evidence') }))).toThrow(SocialApiError);
  rejectsAll([[''], ['x'.repeat(101)], [true], null, {}], hashtags => envelope({ ...payload, hashtags }));
  rejectsAll([[true], null, {}], disclosures => envelope({ ...payload, disclosures }));
  rejectsAll([null, {}, [null], ['asset']], assets => envelope({ ...payload, assets }));
  expect(decodeValidation(envelope({ ...payload, text: '😀'.repeat(20_000), hashtags: [], disclosures: [], assets: [] })).targets[0].resolved_preview).toMatchObject({ hashtags: [], disclosures: [], assets: [] });
});
test('resolved links use absolute HTTPS without credentials or whitespace', () => {
  rejectsAll(['http://example.org', '/relative', 'javascript:alert(1)', ' https://example.org', 'https://example.org/path with space', 'https://user:pass@example.org', 'https:///example.org', 'https:\\example.org'], link => envelope({ ...payload, link }));
  expect(decodeValidation(envelope({ ...payload, link: null })).targets[0].resolved_preview).toMatchObject({ link: null });
});
test('publication receipt retains the required compact status URL', () => {
  expect(decodePublication(publication())).toHaveProperty('status_url', `/api/v1/admin/social/posts/${postId}/status`);
});
test.each([undefined, null, '', true, 1, `/api/v1/admin/social/posts/${postId}`, `/api/v1/admin/social/posts/${instagramId}/status`, `https://example.org/api/v1/admin/social/posts/${postId}/status`, `/api/v1/admin/social/posts/${postId}/status?token=fixture`, `/api/v1/admin/social/posts/${postId}/status#detail`])('publication rejects absent or mismatched status URL %p', status_url => {
  const receipt = publication(status_url);
  if (status_url === undefined) delete (receipt as { status_url?: unknown }).status_url;
  expect(() => decodePublication(receipt)).toThrow(SocialApiError);
});
test('direct resolved-payload and asset decoders retain their guards without the validation wrapper', () => {
  for (const value of [undefined, null, true, [], {}, { success: true }]) {
    expect(() => decodeResolvedPostPayload(value)).toThrow(SocialApiError);
    expect(() => decodeInspectedAsset(value)).toThrow(SocialApiError);
  }
  expect(decodeResolvedPostPayload(payload)).toEqual(payload);
  expect(decodeInspectedAsset(inspected)).toEqual(inspected);
});
test('malformed target collections cannot become successful publication or validation defaults', () => {
  for (const targets of [undefined, null, {}, true, [null], [true], [{}]]) {
    expect(() => decodePublication({ ...publication(), targets })).toThrow(SocialApiError);
    expect(() => decodeValidation({ ...envelope(), targets })).toThrow(SocialApiError);
  }
  for (const bad of [{ id: '' }, { id: 'synthetic' }, { account_id: null }, { platform: 'linkedin' }, { status: true }, { status: 'successful' }]) {
    expect(() => decodePublication({ ...publication(), targets: [{ ...publication().targets[0], ...bad }] })).toThrow(SocialApiError);
  }
});
test('centralized full preview, asset and compact publication fixtures decode as the real DTOs', () => {
  const p = post();
  expect(decodeValidation(validation(p))).toEqual(validation(p));
  expect(decodeResolvedPostPayload(resolvedPayload(p))).toEqual(resolvedPayload(p));
  expect(decodeInspectedAsset(inspectedAsset())).toEqual(inspectedAsset());
  expect(decodePublication(publicationReceipt(p))).toEqual(publicationReceipt(p));
  expect(publicationReceipt(p).scheduled_for).toBe('2026-10-03T12:00:00Z');
});
test('contradictory aggregate and duplicate-target DTOs preserve evidence for the separate composer gates', () => {
  // The backend DTO types impose no aggregate/uniqueness validator. Decoding
  // never supplies omitted rows or erases errors; the composer checks selection.
  const row = envelope().targets[0];
  expect(decodeValidation({ ...envelope(), targets: [] }).targets).toEqual([]);
  expect(decodeValidation({ ...envelope(), targets: [row, row] }).targets).toHaveLength(2);
  expect(decodeValidation(envelope(payload, { valid: false, errors: [{ code: 'ACCOUNT_UNAVAILABLE', field: 'account_id', message: 'Fixture hold.' }] })).targets[0]).toMatchObject({ valid: false, errors: [{ code: 'ACCOUNT_UNAVAILABLE' }] });
  expect(decodePublication({ ...publication(), targets: [] }).targets).toEqual([]);
  const accepted = publication().targets[0];
  expect(decodePublication({ ...publication(), targets: [accepted, accepted] }).targets).toHaveLength(2);
});
