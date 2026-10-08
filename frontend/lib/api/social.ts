/** Admin social contract, including batch 3 schedule controls. All requests use the existing authenticated client. */
import api from '@/lib/api/axios';
import axios from 'axios';

export const SOCIAL_PLATFORMS = ['facebook', 'instagram', 'threads', 'x', 'tiktok'] as const;
export type SocialPlatform = (typeof SOCIAL_PLATFORMS)[number];
export type SocialFormat = 'text' | 'image' | 'carousel' | 'video' | 'reel';
export type EditorialState = 'draft' | 'pending_review' | 'approved' | 'rejected' | 'archived';
export type TargetState = 'ready' | 'queued' | 'claimed' | 'dispatching' | 'processing' | 'retry_wait' | 'reconciling' | 'blocked' | 'published' | 'failed' | 'outcome_unknown' | 'cancelled';
export interface MediaReference { asset_id: string; alt_text?: string | null; caption_asset_id: string | null }
export interface SocialContent { text: string; link: string | null; hashtags: string[]; media: MediaReference[] }
export type SocialOverrides = { [K in keyof SocialContent]?: { mode: 'replace'; value: SocialContent[K] } };
export interface DocumentTarget { account_id: string; format: SocialFormat; overrides: SocialOverrides }
export interface SocialDocument { schema_version: 1; master: SocialContent; targets: DocumentTarget[] }
export interface SocialReference { url: string; label?: string | null }
export interface SocialTarget {
  id: string; account_id: string; platform: SocialPlatform; state: TargetState;
  remote_url: string | null; safe_error_message: string | null;
  next_action_at: string | null; published_at: string | null;
}
export interface SocialHistoricalTarget extends SocialTarget {
  publication_id: string; revision_id: string; approved_at: string; approved_by: string;
  scheduled_for: string | null; cancel_requested_at: string | null; revoked_at: string | null; updated_at: string;
}
export interface SocialHistory { post_id: string; targets: SocialHistoricalTarget[]; total: number; page: number; page_size: number; has_more: boolean }
export type DeliveryFilter = 'all' | 'scheduled' | 'history' | 'needs_attention';
export interface SocialSchedule {
  id: string; revision_id: string; version: number; approved_at: string; approved_by: string;
  scheduled_for: string | null; schedule_timezone: string | null;
  requested_local_time: string | null; cancel_requested_at: string | null;
}
export interface SocialSummary {
  id: string; title: string; content_type: string; origin_type: string;
  editorial_state: EditorialState; delivery_status: string; version: number;
  revision_id: string; created_at: string; created_by: string | null; updated_at: string; targets: SocialTarget[]; publication: SocialSchedule | null;
  historical_targets: SocialHistoricalTarget[]; historical_target_count: number;
}
export interface SocialPost extends SocialSummary {
  document: SocialDocument; references: SocialReference[];
  cancellation?: { in_flight_target_ids: string[]; message: string } | null;
}
export interface SocialList { posts: SocialSummary[]; total: number; page: number; page_size: number; has_more: boolean }
export interface SocialAccount {
  id: string; platform: SocialPlatform; display_name: string; handle: string | null;
  profile_url: string | null; connection_state: string; publishing_enabled: boolean;
  capabilities: SocialCapabilities;
}
export interface SocialCapabilities {
  rules_version: string; provider_api_version: string; eligible: boolean;
  supported_formats: SocialFormat[]; feature_states: Record<string, string>;
  limits: Record<string, number | null>; granted_scopes: string[]; required_scopes: string[];
  price_class: 'free' | 'paid' | 'unverified'; source_links: string[];
  verified_at: string | null; adapter_available: boolean;
}
export interface SocialIssue { code: string; field: string; message: string; account_id?: string }
export interface InspectedAsset {
  asset_id: string; sha256: string; mime_type: string; byte_size: number;
  width: number | null; height: number | null; duration_ms: number | null;
  alt_text: string | null; caption_asset_id: string | null; caption_sha256: string | null;
}
export interface ResolvedPostPayload {
  schema_version: 1; account_id: string; platform: SocialPlatform; api_product: string;
  external_account_id: string; format: SocialFormat; text: string; link: string | null;
  hashtags: string[]; assets: InspectedAsset[]; visibility: 'public'; disclosures: string[];
  capability_version: string; evidence_hash: string; content_hash: string;
}
export interface TargetValidation {
  account_id: string; platform: SocialPlatform | null; valid: boolean;
  errors: SocialIssue[]; warnings: SocialIssue[]; resolved_preview: ResolvedPostPayload | null;
}
export interface SocialValidation { valid: boolean; rules_version: string; targets: TargetValidation[]; errors: SocialIssue[]; warnings: SocialIssue[] }
export interface SocialControls {
  version: number; publishing_enabled: boolean; generation_enabled: false;
  auto_approve_enabled: false; auto_schedule_enabled: false; auto_publish_enabled: false;
}
export interface SocialSystemStatus extends Omit<SocialControls, 'version'> {
  controls_version: number; worker: { state: string; heartbeat_at: string | null; last_scan_at: string | null };
  queue_counts: Record<string, number>; adapters_available: string[]; media_upload_available: boolean;
}
export interface SocialPublication { post_id: string; publication_id: string; status: 'queued'; scheduled_for: string | null; targets: Array<{ id: string; account_id: string; platform: SocialPlatform; status: TargetState }>; status_url: string }
export interface SocialDraftInput { title: string; content_type: string; document: SocialDocument; references: SocialReference[] }
export interface VersionInput { expected_version: number }
export interface ApprovalInput extends VersionInput { revision_id: string; review_attestation?: { facts_checked: boolean; sources_checked: boolean } }
export interface PublishInput extends ApprovalInput { acknowledged_warning_codes: string[] }
export interface ScheduleEditInput extends VersionInput { publication_id: string; expected_publication_version: number; reason: string; acknowledged_warning_codes: string[] }
export interface ScheduleInput extends PublishInput { schedule: { local_time: string; timezone: string; utc_offset: string } }

export class SocialApiError extends Error {
  constructor(public code: string, message: string, public fieldErrors: SocialIssue[] = [], public targetErrors: SocialIssue[] = [], public retryable = false, public requestId?: string) {
    super(message); this.name = 'SocialApiError';
  }
}
type Obj = Record<string, unknown>;
function obj(v: unknown): Obj { if (!v || typeof v !== 'object' || Array.isArray(v)) throw contractError(); return v as Obj; }
function arr(v: unknown): unknown[] { if (!Array.isArray(v)) throw contractError(); return v; }
function str(v: unknown): string { if (typeof v !== 'string') throw contractError(); return v; }
function bool(v: unknown): boolean { if (typeof v !== 'boolean') throw contractError(); return v; }
function integer(v: unknown, min = 1): number { if (typeof v !== 'number' || !Number.isSafeInteger(v) || v < min) throw contractError(); return v; }
function nullable(v: unknown): string | null { return v === null ? null : str(v); }
function uuid(v: unknown): string { const s = str(v); if (s.length !== 36 || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s)) throw contractError(); return s.toLowerCase(); }
function hash(v: unknown): string { const s = str(v); if (s.length !== 64 || !/^[0-9a-f]{64}$/.test(s)) throw contractError(); return s; }
function nullableInteger(v: unknown): number | null { return v === null ? null : integer(v); }
function boundedText(v: unknown, max: number, min = 0): string { const s = str(v), length = Array.from(s).length; if (length < min || length > max) throw contractError(); return s; }
/** Serialized StrictModel payloads include defaults and reject unknown fields. */
function exactObject(v: unknown, fields: readonly string[]): Obj {
  const o = obj(v);
  if (Object.keys(o).some(key => !fields.includes(key)) || fields.some(key => !Object.prototype.hasOwnProperty.call(o, key))) throw contractError();
  return o;
}
function resolvedLink(v: unknown): string | null {
  if (v === null) return null;
  const s = str(v);
  if (/[\s\u0085\u001c-\u001f]/.test(s) || !/^https:\/\/[^/?#\\]+(?:[/?#]|$)/i.test(s)) throw contractError();
  try { const url = new URL(s); if (url.protocol !== 'https:' || !url.hostname || url.username || url.password) throw contractError(); }
  catch { throw contractError(); }
  return s;
}
function oneOf<T extends string>(v: unknown, choices: readonly T[]): T { const s = str(v); if (!choices.includes(s as T)) throw contractError(); return s as T; }
function contractError() { return new SocialApiError('INVALID_RESPONSE', 'The social service returned an unexpected response. Refresh or contact the administrator; no success has been assumed.'); }
const formats: SocialFormat[] = ['text', 'image', 'carousel', 'video', 'reel'];
const targetStates: TargetState[] = ['ready', 'queued', 'claimed', 'dispatching', 'processing', 'retry_wait', 'reconciling', 'blocked', 'published', 'failed', 'outcome_unknown', 'cancelled'];
const editorialStates: EditorialState[] = ['draft', 'pending_review', 'approved', 'rejected', 'archived'];
function media(v: unknown): MediaReference[] { return arr(v).map(item => { const o = obj(item); return { asset_id: str(o.asset_id), caption_asset_id: nullable(o.caption_asset_id), ...(o.alt_text === undefined ? {} : { alt_text: nullable(o.alt_text) }) }; }); }
function content(v: unknown): SocialContent { const o = obj(v); return { text: str(o.text), link: nullable(o.link), hashtags: arr(o.hashtags).map(str), media: media(o.media) }; }
export function decodeDocument(v: unknown): SocialDocument {
  const o = obj(v); if (o.schema_version !== 1) throw contractError();
  return { schema_version: 1, master: content(o.master), targets: arr(o.targets).map(item => {
    const t = obj(item), raw = obj(t.overrides), overrides: SocialOverrides = {};
    for (const key of Object.keys(raw)) {
      if (!['text', 'link', 'hashtags', 'media'].includes(key)) throw contractError();
      const field = obj(raw[key]); if (field.mode !== 'replace') throw contractError();
      if (key === 'text') overrides.text = { mode: 'replace', value: str(field.value) };
      if (key === 'link') overrides.link = { mode: 'replace', value: nullable(field.value) };
      if (key === 'hashtags') overrides.hashtags = { mode: 'replace', value: arr(field.value).map(str) };
      if (key === 'media') overrides.media = { mode: 'replace', value: media(field.value) };
    }
    return { account_id: str(t.account_id), format: oneOf(t.format, formats), overrides };
  }) };
}
function decodeTarget(v: unknown): SocialTarget {
  const o = obj(v); return { id: str(o.id), account_id: str(o.account_id), platform: oneOf(o.platform, SOCIAL_PLATFORMS), state: oneOf(o.state, targetStates), remote_url: nullable(o.remote_url), safe_error_message: nullable(o.safe_error_message), next_action_at: nullable(o.next_action_at), published_at: nullable(o.published_at) };
}
function validCivilTimestamp(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?$/.exec(value);
  if (!match) return false;
  const [, y, m, d, h, minute, second = '0'] = match;
  const year = Number(y), month = Number(m), day = Number(d);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1] && Number(h) <= 23 && Number(minute) <= 59 && Number(second) <= 59;
}
function timestamp(v: unknown): string {
  const s = str(v), match = /^(.*)(?:Z|[+-]\d{2}:\d{2})$/.exec(s);
  if (!match || !validCivilTimestamp(match[1]) || !Number.isFinite(Date.parse(s))) throw contractError();
  return s;
}
function nullableTimestamp(v: unknown): string | null { return v === null ? null : timestamp(v); }
function decodeHistoricalTarget(v: unknown): SocialHistoricalTarget {
  const o = exactObject(v, ['id', 'account_id', 'platform', 'state', 'remote_url', 'safe_error_message', 'next_action_at', 'published_at', 'publication_id', 'revision_id', 'approved_at', 'approved_by', 'scheduled_for', 'cancel_requested_at', 'revoked_at', 'updated_at']);
  return { ...decodeTarget(o), id: uuid(o.id), account_id: uuid(o.account_id),
    state: oneOf(o.state, ['published', 'failed', 'cancelled', 'outcome_unknown', 'blocked', 'reconciling']),
    publication_id: uuid(o.publication_id), revision_id: uuid(o.revision_id), approved_at: timestamp(o.approved_at), approved_by: uuid(o.approved_by),
    scheduled_for: nullableTimestamp(o.scheduled_for), cancel_requested_at: nullableTimestamp(o.cancel_requested_at), revoked_at: nullableTimestamp(o.revoked_at),
    next_action_at: nullableTimestamp(o.next_action_at), published_at: nullableTimestamp(o.published_at), updated_at: timestamp(o.updated_at) };
}
function historicalTargets(v: unknown): SocialHistoricalTarget[] {
  const targets = arr(v).map(decodeHistoricalTarget);
  if (targets.length > 20 || new Set(targets.map(t => t.id)).size !== targets.length) throw contractError();
  return targets;
}
export function decodeHistory(v: unknown): SocialHistory {
  const o = exactObject(v, ['post_id', 'targets', 'total', 'page', 'page_size', 'has_more']);
  const targets = historicalTargets(o.targets), total = integer(o.total, 0), page = integer(o.page), page_size = integer(o.page_size), has_more = bool(o.has_more);
  if (page > 2_147_483_647 || page_size > 20 || targets.length !== Math.max(0, Math.min(page_size, total - (page - 1) * page_size)) || has_more !== (page * page_size < total)) throw contractError();
  return { post_id: uuid(o.post_id), targets, total, page, page_size, has_more };
}
function decodeSchedule(v: unknown): SocialSchedule | null {
  if (v === null) return null;
  const o = exactObject(v, ['id', 'revision_id', 'version', 'approved_at', 'approved_by', 'scheduled_for', 'schedule_timezone', 'requested_local_time', 'cancel_requested_at']);
  const zone = nullable(o.schedule_timezone), local = nullable(o.requested_local_time);
  if (zone !== null) { try { new Intl.DateTimeFormat('en', { timeZone: zone }); } catch { throw contractError(); } }
  if (local !== null && !validCivilTimestamp(local)) throw contractError();
  return { id: uuid(o.id), revision_id: uuid(o.revision_id), version: integer(o.version), approved_at: timestamp(o.approved_at), approved_by: uuid(o.approved_by), scheduled_for: nullableTimestamp(o.scheduled_for), schedule_timezone: zone, requested_local_time: local, cancel_requested_at: nullableTimestamp(o.cancel_requested_at) };
}
export function decodeSummary(v: unknown): SocialSummary {
  const o = obj(v), historical_targets = historicalTargets(o.historical_targets), historical_target_count = integer(o.historical_target_count, 0);
  if (historical_targets.length !== Math.min(20, historical_target_count)) throw contractError();
  return { id: str(o.id), title: str(o.title), content_type: str(o.content_type), origin_type: str(o.origin_type), editorial_state: oneOf(o.editorial_state, editorialStates), delivery_status: str(o.delivery_status), version: integer(o.version), revision_id: str(o.revision_id), created_at: str(o.created_at), created_by: o.created_by === null ? null : uuid(o.created_by), updated_at: str(o.updated_at), targets: arr(o.targets).map(decodeTarget), publication: decodeSchedule(o.publication), historical_targets, historical_target_count };
}
export function decodePost(v: unknown): SocialPost {
  const o = obj(v);
  const cancellation = o.cancellation === undefined || o.cancellation === null ? o.cancellation : obj(o.cancellation);
  return { ...decodeSummary(o), document: decodeDocument(o.document), references: arr(o.references).map(item => { const r = obj(item); return { url: str(r.url), ...(r.label === undefined ? {} : { label: nullable(r.label) }) }; }), ...(cancellation === undefined ? {} : { cancellation: cancellation === null ? null : { in_flight_target_ids: arr(cancellation.in_flight_target_ids).map(str), message: str(cancellation.message) } }) };
}
function issues(v: unknown): SocialIssue[] { return arr(v).map(item => { const o = obj(item); return { code: str(o.code), field: str(o.field), message: str(o.message), ...(typeof o.account_id === 'string' ? { account_id: o.account_id } : {}) }; }); }
export function decodeInspectedAsset(v: unknown): InspectedAsset {
  const o = exactObject(v, ['asset_id', 'sha256', 'mime_type', 'byte_size', 'width', 'height', 'duration_ms', 'alt_text', 'caption_asset_id', 'caption_sha256']);
  return { asset_id: uuid(o.asset_id), sha256: hash(o.sha256), mime_type: str(o.mime_type), byte_size: integer(o.byte_size), width: nullableInteger(o.width), height: nullableInteger(o.height), duration_ms: nullableInteger(o.duration_ms), alt_text: nullable(o.alt_text), caption_asset_id: o.caption_asset_id === null ? null : uuid(o.caption_asset_id), caption_sha256: o.caption_sha256 === null ? null : hash(o.caption_sha256) };
}
export function decodeResolvedPostPayload(v: unknown): ResolvedPostPayload {
  const o = exactObject(v, ['schema_version', 'account_id', 'platform', 'api_product', 'external_account_id', 'format', 'text', 'link', 'hashtags', 'assets', 'visibility', 'disclosures', 'capability_version', 'evidence_hash', 'content_hash']);
  if (o.schema_version !== 1) throw contractError();
  const external_account_id = str(o.external_account_id);
  if (!external_account_id.trim()) throw contractError();
  const hashtags = arr(o.hashtags);
  if (hashtags.length > 50) throw contractError();
  return { schema_version: 1, account_id: uuid(o.account_id), platform: oneOf(o.platform, SOCIAL_PLATFORMS), api_product: str(o.api_product), external_account_id, format: oneOf(o.format, formats), text: boundedText(o.text, 20_000), link: resolvedLink(o.link), hashtags: hashtags.map(value => boundedText(value, 100, 1)), assets: arr(o.assets).map(decodeInspectedAsset), visibility: oneOf(o.visibility, ['public']), disclosures: arr(o.disclosures).map(str), capability_version: str(o.capability_version), evidence_hash: hash(o.evidence_hash), content_hash: hash(o.content_hash) };
}
export function decodeValidation(v: unknown): SocialValidation {
  const o = obj(v); return { valid: bool(o.valid), rules_version: oneOf(o.rules_version, ['social-v1']), errors: issues(o.errors), warnings: issues(o.warnings), targets: arr(o.targets).map(item => {
    const t = obj(item), account_id = uuid(t.account_id), platform = t.platform === null ? null : oneOf(t.platform, SOCIAL_PLATFORMS), valid = bool(t.valid);
    const resolved_preview = t.resolved_preview === null ? null : decodeResolvedPostPayload(t.resolved_preview);
    if ((valid && !resolved_preview) || (resolved_preview && (resolved_preview.account_id !== account_id || resolved_preview.platform !== platform))) throw contractError();
    return { account_id, platform, valid, errors: issues(t.errors), warnings: issues(t.warnings), resolved_preview };
  }) };
}
function falseFlag(v: unknown): false { if (v !== false) throw contractError(); return false; }
function disabledAutomation(o: Obj) { return { generation_enabled: falseFlag(o.generation_enabled), auto_approve_enabled: falseFlag(o.auto_approve_enabled), auto_schedule_enabled: falseFlag(o.auto_schedule_enabled), auto_publish_enabled: falseFlag(o.auto_publish_enabled) }; }
export function decodeControls(v: unknown): SocialControls { const o = obj(v); return { version: integer(o.version), publishing_enabled: bool(o.publishing_enabled), ...disabledAutomation(o) }; }
export function decodeSystem(v: unknown): SocialSystemStatus {
  const o = obj(v), worker = obj(o.worker);
  return { publishing_enabled: bool(o.publishing_enabled), controls_version: integer(o.controls_version), worker: { state: str(worker.state), heartbeat_at: nullable(worker.heartbeat_at), last_scan_at: nullable(worker.last_scan_at) }, queue_counts: Object.fromEntries(Object.entries(obj(o.queue_counts)).map(([k, count]) => [k, integer(count, 0)])), adapters_available: arr(o.adapters_available).map(str), media_upload_available: bool(o.media_upload_available), ...disabledAutomation(o) };
}
function decodeCapabilities(v: unknown): SocialCapabilities {
  const o = obj(v);
  return { rules_version: str(o.rules_version), provider_api_version: str(o.provider_api_version), eligible: bool(o.eligible), supported_formats: arr(o.supported_formats).map(f => oneOf(f, formats)), feature_states: Object.fromEntries(Object.entries(obj(o.feature_states)).map(([k, state]) => [k, str(state)])), limits: Object.fromEntries(Object.entries(obj(o.limits)).map(([k, limit]) => [k, limit === null ? null : integer(limit, 0)])), granted_scopes: arr(o.granted_scopes).map(str), required_scopes: arr(o.required_scopes).map(str), price_class: oneOf(o.price_class, ['free', 'paid', 'unverified']), source_links: arr(o.source_links).map(str), verified_at: nullable(o.verified_at), adapter_available: bool(o.adapter_available) };
}
export function decodePublication(v: unknown): SocialPublication {
  const o = obj(v), post_id = uuid(o.post_id), status_url = str(o.status_url);
  if (status_url !== `/api/v1/admin/social/posts/${post_id}/status`) throw contractError();
  return { post_id, publication_id: uuid(o.publication_id), status: oneOf(o.status, ['queued']), scheduled_for: nullable(o.scheduled_for), targets: arr(o.targets).map(item => { const t = obj(item); return { id: uuid(t.id), account_id: uuid(t.account_id), platform: oneOf(t.platform, SOCIAL_PLATFORMS), status: oneOf(t.status, targetStates) }; }), status_url };
}
export function toSocialError(error: unknown): SocialApiError {
  if (error instanceof SocialApiError) return error;
  if (axios.isAxiosError(error)) {
    const raw = error.response?.data?.detail;
    if (raw && typeof raw === 'object' && typeof raw.code === 'string' && typeof raw.message === 'string') {
      try { return new SocialApiError(raw.code, raw.message, issues(raw.field_errors), issues(raw.target_errors), raw.retryable === true, typeof raw.request_id === 'string' ? raw.request_id : undefined); } catch { return contractError(); }
    }
    if (!error.response) return new SocialApiError('NETWORK_ERROR', 'The response could not be confirmed. Retry the same command to recover its original result.', [], [], true);
    if (error.response.status === 401 || error.response.status === 403) return new SocialApiError('ACCESS_DENIED', 'Your admin session does not authorize this action. Sign in again or contact an administrator.');
  }
  return new SocialApiError('SOCIAL_UNAVAILABLE', 'The social service is unavailable. Your local edits have been preserved.');
}
async function read<T>(path: string, decode: (v: unknown) => T, signal?: AbortSignal, params?: object): Promise<T> {
  try { return decode((await api.get(`/admin/social${path}`, { signal, params })).data); } catch (e) { throw toSocialError(e); }
}
export async function sendSocialCommand<T>(path: string, body: object, key: string, decode: (v: unknown) => T, method: 'post' | 'patch' = 'post'): Promise<T> {
  try { return decode((await api[method](`/admin/social${path}`, body, { headers: { 'Idempotency-Key': key } })).data); } catch (e) { throw toSocialError(e); }
}
export const socialApi = {
  posts: (page: number, editorial_state?: EditorialState, signal?: AbortSignal, delivery_filter: DeliveryFilter = 'all') => read('/posts', v => { const o = obj(v); return { posts: arr(o.posts).map(decodeSummary), total: integer(o.total, 0), page: integer(o.page), page_size: integer(o.page_size), has_more: bool(o.has_more) }; }, signal, { page, page_size: 20, delivery_filter, ...(editorial_state ? { editorial_state } : {}) }),
  post: (id: string, signal?: AbortSignal) => read(`/posts/${encodeURIComponent(id)}`, v => { const post = decodePost(v); if (post.id !== id) throw contractError(); return post; }, signal),
  postStatus: (id: string, signal?: AbortSignal) => read(`/posts/${encodeURIComponent(id)}/status`, v => { const post = decodeSummary(v); if (post.id !== id) throw contractError(); return post; }, signal),
  history: (id: string, page: number, signal?: AbortSignal) => read(`/posts/${encodeURIComponent(id)}/history`, v => { const result = decodeHistory(v); if (result.post_id !== id || result.page !== page || result.page_size !== 20) throw contractError(); return result; }, signal, { page, page_size: 20 }),
  accounts: (signal?: AbortSignal) => read('/accounts', v => arr(obj(v).accounts).map(item => { const o = obj(item); return { id: str(o.id), platform: oneOf(o.platform, SOCIAL_PLATFORMS), display_name: str(o.display_name), handle: nullable(o.handle), profile_url: nullable(o.profile_url), connection_state: str(o.connection_state), publishing_enabled: bool(o.publishing_enabled), capabilities: decodeCapabilities(o.capabilities) }; }), signal),
  platforms: (signal?: AbortSignal) => read('/platforms', v => arr(obj(v).platforms).map(item => { const o = obj(item); return { platform: oneOf(o.platform, SOCIAL_PLATFORMS), capabilities: decodeCapabilities(o.capabilities) }; }), signal),
  status: (signal?: AbortSignal) => read('/system/status', decodeSystem, signal),
  validate: async (id: string, expected_version: number): Promise<SocialValidation> => {
    try { return decodeValidation((await api.post(`/admin/social/posts/${encodeURIComponent(id)}/validate`, { expected_version })).data); } catch (e) { throw toSocialError(e); }
  },
};
