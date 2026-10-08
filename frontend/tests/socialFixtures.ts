import { InspectedAsset, ResolvedPostPayload, SocialAccount, SocialPost, SocialSchedule, SocialPublication, SocialSystemStatus, SocialTarget, SocialValidation } from '@/lib/api/social';

export const actorId = '00000000-0000-4000-8000-000000000001';
export const postId = '00000000-0000-4000-8000-000000000010';
export const facebookId = '00000000-0000-4000-8000-000000000020';
export const instagramId = '00000000-0000-4000-8000-000000000021';
export const assetId = '00000000-0000-4000-8000-000000000030';
export const accounts: SocialAccount[] = [
  { id: facebookId, platform: 'facebook', display_name: 'AuditGava test Page', handle: '@fixture-fb', profile_url: null, connection_state: 'connected', publishing_enabled: true, capabilities: { rules_version: 'social-v1', provider_api_version: 'fixture', eligible: true, supported_formats: ['text', 'image'], feature_states: { publishing: 'supported' }, limits: { max_text_length: 5000 }, granted_scopes: [], required_scopes: [], price_class: 'free', source_links: [], verified_at: null, adapter_available: true } },
  { id: instagramId, platform: 'instagram', display_name: 'AuditGava test Instagram', handle: '@fixture-ig', profile_url: null, connection_state: 'connected', publishing_enabled: true, capabilities: { rules_version: 'social-v1', provider_api_version: 'fixture', eligible: true, supported_formats: ['image', 'carousel', 'reel'], feature_states: { publishing: 'supported' }, limits: { max_text_length: 2200 }, granted_scopes: [], required_scopes: [], price_class: 'free', source_links: [], verified_at: null, adapter_available: true } },
];
export function post(overrides: Omit<Partial<SocialPost>, 'publication'> & { publication?: Partial<SocialSchedule> | null } = {}): SocialPost {
  return { id: postId, title: 'What does unsupported expenditure mean?', content_type: 'announcement', origin_type: 'manual', editorial_state: 'draft', delivery_status: 'draft', version: 1, revision_id: '00000000-0000-4000-8000-000000000040', document: { schema_version: 1, master: { text: 'Read the finding and its supporting evidence.', link: 'https://example.org/report', hashtags: ['#Evidence'], media: [] }, targets: [{ account_id: facebookId, format: 'text', overrides: {} }] }, references: [], created_at: '2026-10-03T12:00:00Z', created_by: actorId, updated_at: '2026-10-03T12:00:00Z', targets: [], ...overrides, ...(overrides.publication ? { publication: { id: '00000000-0000-4000-8000-000000000060', revision_id: '00000000-0000-4000-8000-000000000040', version: 1, approved_at: '2026-10-03T12:00:00Z', approved_by: actorId, scheduled_for: null, schedule_timezone: null, requested_local_time: null, cancel_requested_at: null, ...overrides.publication } } : { publication: null }) };
}
export function target(state: SocialTarget['state'], platform: SocialTarget['platform'] = 'facebook'): SocialTarget {
  return { id: platform === 'facebook' ? '00000000-0000-4000-8000-000000000050' : '00000000-0000-4000-8000-000000000051', account_id: platform === 'facebook' ? facebookId : instagramId, platform, state, remote_url: null, safe_error_message: null, next_action_at: null, published_at: null };
}
export const system: SocialSystemStatus = { publishing_enabled: true, controls_version: 1, worker: { state: 'unavailable', heartbeat_at: null, last_scan_at: null }, queue_counts: {}, adapters_available: [], media_upload_available: false, generation_enabled: false, auto_approve_enabled: false, auto_schedule_enabled: false, auto_publish_enabled: false };
export function inspectedAsset(overrides: Partial<InspectedAsset> = {}): InspectedAsset {
  return { asset_id: assetId, sha256: 'a'.repeat(64), mime_type: 'image/png', byte_size: 12345, width: 1200, height: 630, duration_ms: null, alt_text: 'An evidence-first explainer card', caption_asset_id: null, caption_sha256: null, ...overrides };
}
export function resolvedPayload(p: SocialPost, targetIndex = 0, overrides: Partial<ResolvedPostPayload> = {}): ResolvedPostPayload {
  const selected = p.document.targets[targetIndex];
  const account = accounts.find(a => a.id === selected.account_id);
  if (!account) throw new Error('A resolved test payload requires an explicit fixture account.');
  const master = p.document.master, fields = selected.overrides;
  const media = fields.media ? fields.media.value : master.media;
  return { schema_version: 1, account_id: selected.account_id, platform: account.platform, api_product: `fixture-${account.platform}`, external_account_id: `fixture-external-${account.id}`, format: selected.format, text: fields.text ? fields.text.value : master.text, link: fields.link ? fields.link.value : master.link, hashtags: fields.hashtags ? fields.hashtags.value : master.hashtags, assets: media.map(reference => inspectedAsset({ asset_id: reference.asset_id, alt_text: reference.alt_text ?? null, caption_asset_id: reference.caption_asset_id, caption_sha256: reference.caption_asset_id ? 'd'.repeat(64) : null, ...(selected.format === 'video' || selected.format === 'reel' ? { mime_type: 'video/mp4', duration_ms: 15000 } : {}) })), visibility: 'public', disclosures: [], capability_version: 'social-v1', evidence_hash: 'b'.repeat(64), content_hash: 'c'.repeat(64), ...overrides };
}
export function validation(p: SocialPost, valid = true): SocialValidation {
  return { valid, rules_version: 'social-v1', errors: [], warnings: [], targets: p.document.targets.map((t, index) => {
    const platform = accounts.find(a => a.id === t.account_id)?.platform ?? null;
    return { account_id: t.account_id, platform, valid: valid && platform !== null, errors: [], warnings: [], resolved_preview: valid && platform !== null ? resolvedPayload(p, index) : null };
  }) };
}
export function publicationReceipt(p: SocialPost, overrides: Partial<SocialPublication> = {}): SocialPublication {
  const targets = p.targets.length ? p.targets : p.document.targets.map(t => target('queued', accounts.find(a => a.id === t.account_id)!.platform));
  return { post_id: p.id, publication_id: p.publication?.id ?? '00000000-0000-4000-8000-000000000060', status: 'queued', scheduled_for: p.publication?.scheduled_for ?? '2026-10-03T12:00:00Z', targets: targets.map(t => ({ id: t.id, account_id: t.account_id, platform: t.platform, status: 'queued' })), status_url: `/api/v1/admin/social/posts/${p.id}/status`, ...overrides };
}
