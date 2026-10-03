import { SocialAccount, SocialPost, SocialSystemStatus, SocialTarget, SocialValidation } from '@/lib/api/social';

export const actorId = '00000000-0000-4000-8000-000000000001';
export const postId = '00000000-0000-4000-8000-000000000010';
export const facebookId = '00000000-0000-4000-8000-000000000020';
export const instagramId = '00000000-0000-4000-8000-000000000021';
export const assetId = '00000000-0000-4000-8000-000000000030';
export const accounts: SocialAccount[] = [
  { id: facebookId, platform: 'facebook', display_name: 'AuditGava test Page', handle: '@fixture-fb', profile_url: null, connection_state: 'connected', publishing_enabled: true, capabilities: { rules_version: 'social-v1', provider_api_version: 'fixture', eligible: true, supported_formats: ['text', 'image'], feature_states: { publishing: 'supported' }, limits: { max_text_length: 5000 }, granted_scopes: [], required_scopes: [], price_class: 'free', source_links: [], verified_at: null, adapter_available: true } },
  { id: instagramId, platform: 'instagram', display_name: 'AuditGava test Instagram', handle: '@fixture-ig', profile_url: null, connection_state: 'connected', publishing_enabled: true, capabilities: { rules_version: 'social-v1', provider_api_version: 'fixture', eligible: true, supported_formats: ['image', 'carousel', 'reel'], feature_states: { publishing: 'supported' }, limits: { max_text_length: 2200 }, granted_scopes: [], required_scopes: [], price_class: 'free', source_links: [], verified_at: null, adapter_available: true } },
];
export function post(overrides: Partial<SocialPost> = {}): SocialPost {
  return { id: postId, title: 'What does unsupported expenditure mean?', content_type: 'announcement', origin_type: 'manual', editorial_state: 'draft', delivery_status: 'draft', version: 1, revision_id: '00000000-0000-4000-8000-000000000040', document: { schema_version: 1, master: { text: 'Read the finding and its supporting evidence.', link: 'https://example.org/report', hashtags: ['#Evidence'], media: [] }, targets: [{ account_id: facebookId, format: 'text', overrides: {} }] }, references: [], created_at: '2026-10-03T12:00:00Z', updated_at: '2026-10-03T12:00:00Z', publication: null, targets: [], ...overrides };
}
export function target(state: SocialTarget['state'], platform: SocialTarget['platform'] = 'facebook'): SocialTarget {
  return { id: platform === 'facebook' ? '00000000-0000-4000-8000-000000000050' : '00000000-0000-4000-8000-000000000051', account_id: platform === 'facebook' ? facebookId : instagramId, platform, state, remote_url: null, safe_error_message: null, next_action_at: null, published_at: null };
}
export const system: SocialSystemStatus = { publishing_enabled: true, controls_version: 1, worker: { state: 'unavailable', heartbeat_at: null, last_scan_at: null }, queue_counts: {}, adapters_available: [], media_upload_available: false, generation_enabled: false, auto_approve_enabled: false, auto_schedule_enabled: false, auto_publish_enabled: false };
export function validation(p: SocialPost, valid = true): SocialValidation {
  return { valid, rules_version: 'social-v1', errors: [], warnings: [], targets: p.document.targets.map(t => ({ account_id: t.account_id, platform: accounts.find(a => a.id === t.account_id)?.platform ?? null, valid, errors: [], warnings: [], resolved_preview: null })) };
}
