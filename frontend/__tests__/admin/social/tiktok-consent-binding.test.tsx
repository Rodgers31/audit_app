import { fireEvent, render, screen } from '@testing-library/react';
import SocialComposer from '@/components/admin/social/SocialComposer';
import type { DocumentTarget, SocialAccount, SocialDraftInput, TikTokPostOptions } from '@/lib/api/social';
import { clearChangedTikTokConfirmations } from '@/components/admin/social/tiktokConsent';
import { accounts, facebookId, post, system } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock('@/lib/hooks/useSocial', () => ({ useSocialMutation: () => ({ run: jest.fn() }), useSocialPost: () => ({}), useSocialDeliveryStatus: () => ({}) }));
jest.mock('@/components/admin/social/SocialMedia', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/admin/social/SocialPreview', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/admin/social/SocialDeliveryHistory', () => ({ __esModule: true, default: () => null }));
jest.mock('@/components/admin/social/TikTokControls', () => ({ __esModule: true, default: ({ target, onChange }: { target: DocumentTarget; onChange: (value: DocumentTarget) => void }) => <><output data-testid='consent-options'>{JSON.stringify(target.tiktok_options)}</output><button onClick={() => onChange({ ...target, tiktok_options: { ...target.tiktok_options!, is_ai_generated: true } })}>Fixture disclosure change</button><button onClick={() => onChange({ ...target, tiktok_options: { ...target.tiktok_options!, music_usage_confirmed: true } })}>Fixture music confirmation</button></> }));

const confirmed: TikTokPostOptions = { mode: 'direct', privacy_level: 'PUBLIC_TO_EVERYONE', disable_comment: true, disable_duet: true, disable_stitch: true, commercial_content: true, is_brand_organic: false, is_branded_content: true, is_ai_generated: false, upload_consent: true, music_usage_confirmed: true, branded_content_policy_confirmed: true, creator_settings_checked_at: '2026-10-16T20:00:00Z', creator_settings_hash: 'a'.repeat(64), photo_title: '' };
const creator: SocialAccount = { ...accounts[0], platform: 'tiktok', capabilities: { ...accounts[0].capabilities, supported_formats: ['video', 'image', 'carousel'] } };
function mount(overrides: DocumentTarget['overrides'] = {}, options = confirmed) {
  const source = post();
  const initial = post({ document: { ...source.document, targets: [{ account_id: facebookId, format: 'video', overrides, tiktok_options: options }] } });
  render(<SocialComposer initialPost={initial} accounts={[creator]} system={system} />);
}
function options(): TikTokPostOptions { return JSON.parse(screen.getByTestId('consent-options').textContent!); }

test('editing the effective master content clears all exact-content confirmations', () => {
  mount();
  fireEvent.change(screen.getByLabelText('Master text'), { target: { value: 'Changed content requiring new review' } });
  expect(options()).toMatchObject({ upload_consent: false, music_usage_confirmed: false, branded_content_policy_confirmed: false });
});
test('editing a provider disclosure clears all confirmations', () => {
  mount();
  fireEvent.click(screen.getByRole('button', { name: 'Fixture disclosure change' }));
  expect(options()).toMatchObject({ is_ai_generated: true, upload_consent: false, music_usage_confirmed: false, branded_content_policy_confirmed: false });
});
test('internal metadata and checking another confirmation preserve reviewed consent', () => {
  mount({}, { ...confirmed, music_usage_confirmed: false });
  fireEvent.change(screen.getByLabelText('Internal title'), { target: { value: 'Internal title only' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add source reference' }));
  fireEvent.change(screen.getByLabelText('Source URL 1'), { target: { value: 'https://example.test/evidence' } });
  fireEvent.click(screen.getByRole('button', { name: 'Fixture music confirmation' }));
  expect(options()).toMatchObject({ upload_consent: true, music_usage_confirmed: true, branded_content_policy_confirmed: true });
});
test('an account override preserving effective content keeps consent when master text changes', () => {
  mount({ text: { mode: 'replace', value: 'Exact account-specific reviewed content' } });
  fireEvent.change(screen.getByLabelText('Master text'), { target: { value: 'Changed master has no effect for this account' } });
  expect(options()).toMatchObject({ upload_consent: true, music_usage_confirmed: true, branded_content_policy_confirmed: true });
});

function draft(): SocialDraftInput {
  return { title: 'Internal', content_type: 'announcement', references: [], document: { schema_version: 1, master: { text: 'Reviewed text', link: 'https://example.test/report', hashtags: ['Evidence'], media: [{ asset_id: 'reviewed-asset', alt_text: 'Reviewed alternative text', caption_asset_id: null }] }, targets: [{ account_id: facebookId, format: 'video', overrides: {}, tiktok_options: { ...confirmed } }] } };
}
test.each([
  { text: 'Changed text' }, { link: null }, { hashtags: ['Changed'] },
  { media: [] }, { media: [{ asset_id: 'replaced-asset', alt_text: 'Reviewed alternative text', caption_asset_id: null }] },
  { media: [{ asset_id: 'reviewed-asset', alt_text: 'Changed alternative text', caption_asset_id: null }] },
  { media: [{ asset_id: 'reviewed-asset', alt_text: 'Reviewed alternative text', caption_asset_id: 'new-captions' }] },
])('effective publication change invalidates consent: %p', changes => {
  const before = draft();
  const next = { ...before, document: { ...before.document, master: { ...before.document.master, ...changes } } };
  const result = clearChangedTikTokConfirmations(before, next);
  expect(result.document.targets[0].tiktok_options).toMatchObject({ upload_consent: false, music_usage_confirmed: false, branded_content_policy_confirmed: false });
  expect(before.document.targets[0].tiktok_options).toEqual(confirmed);
});
test.each<Partial<TikTokPostOptions>>([
  { mode: 'draft' }, { privacy_level: 'SELF_ONLY' }, { disable_comment: false }, { disable_duet: false }, { disable_stitch: false },
  { commercial_content: false }, { is_brand_organic: true }, { is_branded_content: false }, { is_ai_generated: true },
  { creator_settings_checked_at: '2026-10-16T20:01:00Z' }, { creator_settings_hash: 'b'.repeat(64) }, { photo_title: 'Changed provider title' },
])('every provider option except confirmations binds consent: %p', changes => {
  const before = draft();
  const next = { ...before, document: { ...before.document, targets: [{ ...before.document.targets[0], tiktok_options: { ...confirmed, ...changes } }] } };
  expect(clearChangedTikTokConfirmations(before, next).document.targets[0].tiktok_options).toMatchObject({ ...changes, upload_consent: false, music_usage_confirmed: false, branded_content_policy_confirmed: false });
});
test('format and account changes require fresh consent', () => {
  for (const changes of [{ format: 'image' as const }, { account_id: 'different-creator' }]) {
    const before = draft();
    const next = { ...before, document: { ...before.document, targets: [{ ...before.document.targets[0], ...changes }] } };
    expect(clearChangedTikTokConfirmations(before, next).document.targets[0].tiktok_options!.upload_consent).toBe(false);
  }
});
test('master edits invalidate only targets whose resolved publication changes', () => {
  const before = draft();
  before.document.targets[0].overrides.text = { mode: 'replace', value: 'Independent reviewed text' };
  before.document.targets.push({ ...before.document.targets[0], account_id: 'second-creator', overrides: {} });
  const next = { ...before, document: { ...before.document, master: { ...before.document.master, text: 'Changed master' } } };
  const result = clearChangedTikTokConfirmations(before, next);
  expect(result.document.targets[0]).toBe(before.document.targets[0]);
  expect(result.document.targets[0].tiktok_options!.upload_consent).toBe(true);
  expect(result.document.targets[1].tiktok_options!.upload_consent).toBe(false);
});
test('equivalent override representation and object key order preserve confirmations', () => {
  const before = draft();
  const next = draft();
  next.document.targets[0].overrides.text = { mode: 'replace', value: before.document.master.text };
  const { photo_title, ...otherOptions } = confirmed;
  next.document.targets[0].tiktok_options = { photo_title, ...otherOptions };
  expect(clearChangedTikTokConfirmations(before, next)).toBe(next);
});
