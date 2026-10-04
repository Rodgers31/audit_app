import { resolveCivilTime, resolveContent } from '@/components/admin/social/socialDocument';
import { decodeDocument, decodePost, decodeSystem, decodeValidation, SocialApiError, socialApi } from '@/lib/api/social';
import api from '@/lib/api/axios';
import { assetId, post, system } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
beforeEach(() => jest.clearAllMocks());

test('API-shaped nullable fields preserve exact replacement and inheritance semantics', () => {
  const p = post(); p.references = [{ url: 'https://example.org/source', label: null }];
  p.document.master.media = [{ asset_id: assetId, alt_text: null, caption_asset_id: null }];
  p.document.targets[0].overrides = { text: { mode: 'replace', value: '' }, link: { mode: 'replace', value: null }, hashtags: { mode: 'replace', value: [] }, media: { mode: 'replace', value: [] } };
  const decoded = decodePost(p);
  expect(decoded.references[0].label).toBeNull(); expect(decoded.document.master.media[0].alt_text).toBeNull();
  expect(resolveContent(decoded.document.master, decoded.document.targets[0])).toEqual({ text: '', link: null, hashtags: [], media: [] });
  expect(decodeValidation({ valid: false, rules_version: 'social-v1', errors: [], warnings: [], targets: [{ account_id: p.document.targets[0].account_id, platform: null, valid: false, errors: [], warnings: [], resolved_preview: null }] }).targets[0].platform).toBeNull();
});
test('malformed response versions and null overrides fail instead of claiming success', () => {
  expect(() => decodePost({ ...post(), version: true })).toThrow(SocialApiError);
  expect(() => decodeDocument({ ...post().document, targets: [{ ...post().document.targets[0], overrides: { text: null } }] })).toThrow(SocialApiError);
  expect(() => decodePost({})).toThrow(SocialApiError);
});
test('real empty accounts are distinct from unavailable/invalid account responses', async () => {
  (api.get as jest.Mock).mockResolvedValueOnce({ data: { accounts: [] } }).mockResolvedValueOnce({ data: {} }).mockRejectedValueOnce({ isAxiosError: true, response: { status: 503, data: { detail: { code: 'SOCIAL_SCHEMA_UNAVAILABLE', message: 'Apply the social schema migration.', field_errors: [], target_errors: [], retryable: false, request_id: post().id } } } });
  await expect(socialApi.accounts()).resolves.toEqual([]);
  await expect(socialApi.accounts()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  await expect(socialApi.accounts()).rejects.toMatchObject({ code: 'SOCIAL_SCHEMA_UNAVAILABLE' });
});
test('typed system DTO accepts a missing worker heartbeat without manufacturing health', () => {
  expect(decodeSystem(system).worker).toEqual({ state: 'unavailable', heartbeat_at: null, last_scan_at: null });
  expect(() => decodeSystem({ ...system, worker: {} })).toThrow(SocialApiError);
  expect(() => decodeSystem({ ...system, auto_publish_enabled: true })).toThrow(SocialApiError);
  expect(decodeSystem({ ...system, media_upload_available: true }).media_upload_available).toBe(true);
  expect(() => decodeSystem({ ...system, media_upload_available: 'true' })).toThrow(SocialApiError);
});
test('future schedule uses its selected zone and rejects DST gaps or invalid dates', () => {
  expect(resolveCivilTime('2027-01-05T10:00', 'Africa/Nairobi').candidates).toEqual([{ utc: '2027-01-05T07:00:00.000Z', offset: '+03:00' }]);
  expect(resolveCivilTime('2027-03-14T02:30', 'America/Chicago').error).toMatch(/does not exist/);
  expect(resolveCivilTime('2027-11-07T01:30', 'America/Chicago').candidates).toEqual([{ utc: '2027-11-07T07:30:00.000Z', offset: '-06:00' }, { utc: '2027-11-07T06:30:00.000Z', offset: '-05:00' }]);
  expect(resolveCivilTime('2027-02-30T10:00', 'Africa/Nairobi').error).toBeDefined();
  expect(resolveCivilTime('2027-01-05T10:00', 'Not/AZone').error).toMatch(/IANA/);
});
