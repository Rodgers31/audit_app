/** Tokens and ciphertext have no representation in this browser contract. */
import api from '@/lib/api/axios';
import axios from 'axios';
import type { SocialAccount } from './social';

export interface MetaConnectionStatus { provider: 'meta'; available: boolean; blockers: string[]; access_mode: 'unverified' | 'owned_standard' | 'advanced'; scopes: string[]; publishing_adapter_available: false }
export interface MetaStartedFlow { flow_id: string; authorize_url: string; expires_at: string }
export interface MetaAssetChoice { page_id: string; display_name: string; tasks: string[]; instagram_id: string | null; instagram_name: string | null; instagram_handle: string | null; page_eligible: boolean; instagram_eligible: boolean; missing_page_scopes: string[]; missing_instagram_scopes: string[] }
export interface MetaDiscoveredFlow { flow_id: string; expires_at: string; granted_scopes: string[]; choices: MetaAssetChoice[] }
export interface MetaAccountHealth { account_id: string; external_account_id: string; api_product: string; connection_method: 'facebook_login'; connection_state: string; credential_kind: 'facebook_page'; credential_id: string; credential_version: number; key_version: string; access_expires_at: string | null; data_access_expires_at: string | null; parent_access_expires_at: string | null; parent_data_access_expires_at: string | null; parent_grant_reconnect_required: boolean; granted_scopes: string[]; missing_scopes: string[]; checked_at: string | null; last_api_success_at: string | null; reconnect_required: boolean; publishing_enabled: boolean; renewal_strategy: 'facebook_login_reconnect'; provider_revocation_confirmed: false }
export class ConnectionError extends Error {
  constructor(public code: string, message: string, public requestId?: string) { super(message); this.name = 'ConnectionError'; }
}
function invalid(): never { throw new ConnectionError('INVALID_RESPONSE', 'The connection service returned an unexpected response. Refresh before continuing.'); }
function object(v: unknown): Record<string, unknown> { if (!v || typeof v !== 'object' || Array.isArray(v)) return invalid(); return v as Record<string, unknown>; }
function exact(v: unknown, keys: string[]) { const o = object(v); if (Object.keys(o).some(k => !keys.includes(k)) || keys.some(k => !(k in o))) invalid(); return o; }
function text(v: unknown): string { if (typeof v !== 'string') invalid(); return v as string; }
function bool(v: unknown): boolean { if (typeof v !== 'boolean') invalid(); return v as boolean; }
function list(v: unknown): string[] { if (!Array.isArray(v)) invalid(); return (v as unknown[]).map(text); }
function array(v: unknown): unknown[] { if (!Array.isArray(v)) invalid(); return v as unknown[]; }
function nullable(v: unknown) { return v === null ? null : text(v); }
function id(v: unknown) { const s = text(v); if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s)) invalid(); return s; }
function date(v: unknown) { const s = text(v); if (!Number.isFinite(Date.parse(s)) || !/(?:Z|[+-]\d{2}:\d{2})$/.test(s)) invalid(); return s; }
function nullableDate(v: unknown) { return v === null ? null : date(v); }
function external(v: unknown) { const s = text(v); if (!/^[0-9]{1,64}$/.test(s)) invalid(); return s; }
export function decodeConnectionStatus(v: unknown): MetaConnectionStatus {
  const o = exact(v, ['provider','available','blockers','access_mode','scopes','publishing_adapter_available']);
  if (o.provider !== 'meta' || o.publishing_adapter_available !== false || !['unverified','owned_standard','advanced'].includes(text(o.access_mode))) invalid();
  const available = bool(o.available), blockers = list(o.blockers);
  if (available !== (blockers.length === 0) || available && o.access_mode === 'unverified') invalid();
  return { provider: 'meta', available, blockers, access_mode: o.access_mode as MetaConnectionStatus['access_mode'], scopes: list(o.scopes), publishing_adapter_available: false };
}
export function decodeStartedFlow(v: unknown): MetaStartedFlow {
  const o = exact(v, ['flow_id','authorize_url','expires_at']);
  const url = new URL(text(o.authorize_url));
  if (url.protocol !== 'https:' || url.hostname !== 'www.facebook.com' || !/^\/v\d+\.0\/dialog\/oauth$/.test(url.pathname) || url.username || url.password || url.hash || url.searchParams.get('response_type') !== 'code' || !/^[A-Za-z0-9_-]{43}$/.test(url.searchParams.get('state') ?? '') || ['access_token','client_secret','code','refresh_token'].some(k => url.searchParams.has(k))) invalid();
  return { flow_id: id(o.flow_id), authorize_url: url.href, expires_at: date(o.expires_at) };
}
export function decodeDiscoveredFlow(v: unknown): MetaDiscoveredFlow {
  const o = exact(v, ['flow_id','expires_at','granted_scopes','choices']);
  const choices = array(o.choices).map(raw => {
    const c = exact(raw, ['page_id','display_name','tasks','instagram_id','instagram_name','instagram_handle','page_eligible','instagram_eligible','missing_page_scopes','missing_instagram_scopes']);
    const page = bool(c.page_eligible), ig = bool(c.instagram_eligible), missingPage = list(c.missing_page_scopes), missingIg = list(c.missing_instagram_scopes);
    const instagramId = c.instagram_id === null ? null : external(c.instagram_id);
    if (page && missingPage.length || ig && (!instagramId || missingIg.length)) invalid();
    return { page_id: external(c.page_id), display_name: text(c.display_name), tasks: list(c.tasks), instagram_id: instagramId, instagram_name: nullable(c.instagram_name), instagram_handle: nullable(c.instagram_handle), page_eligible: page, instagram_eligible: ig, missing_page_scopes: missingPage, missing_instagram_scopes: missingIg };
  });
  if (choices.length > 100 || new Set(choices.map(c => c.page_id)).size !== choices.length) invalid();
  return { flow_id: id(o.flow_id), expires_at: date(o.expires_at), granted_scopes: list(o.granted_scopes), choices };
}
export function decodeAccountHealth(v: unknown): MetaAccountHealth {
  const keys = ['account_id','external_account_id','api_product','connection_method','connection_state','credential_kind','credential_id','credential_version','key_version','access_expires_at','data_access_expires_at','parent_access_expires_at','parent_data_access_expires_at','parent_grant_reconnect_required','granted_scopes','missing_scopes','checked_at','last_api_success_at','reconnect_required','publishing_enabled','renewal_strategy','provider_revocation_confirmed'];
  const o = exact(v, keys);
  if (o.connection_method !== 'facebook_login' || o.credential_kind !== 'facebook_page' || o.renewal_strategy !== 'facebook_login_reconnect' || o.provider_revocation_confirmed !== false || typeof o.credential_version !== 'number' || !Number.isSafeInteger(o.credential_version) || o.credential_version < 1) invalid();
  return { account_id: id(o.account_id), external_account_id: external(o.external_account_id), api_product: text(o.api_product), connection_method: 'facebook_login', connection_state: text(o.connection_state), credential_kind: 'facebook_page', credential_id: id(o.credential_id), credential_version: o.credential_version as number, key_version: text(o.key_version), access_expires_at: nullableDate(o.access_expires_at), data_access_expires_at: nullableDate(o.data_access_expires_at), parent_access_expires_at: nullableDate(o.parent_access_expires_at), parent_data_access_expires_at: nullableDate(o.parent_data_access_expires_at), parent_grant_reconnect_required: bool(o.parent_grant_reconnect_required), granted_scopes: list(o.granted_scopes), missing_scopes: list(o.missing_scopes), checked_at: nullableDate(o.checked_at), last_api_success_at: nullableDate(o.last_api_success_at), reconnect_required: bool(o.reconnect_required), publishing_enabled: bool(o.publishing_enabled), renewal_strategy: 'facebook_login_reconnect', provider_revocation_confirmed: false };
}
async function request<T>(path: string, decode: (value: unknown) => T, body?: unknown, key?: string, signal?: AbortSignal): Promise<T> {
  try {
    const response = body === undefined ? await api.get('/admin/social' + path, { signal, headers: { 'Cache-Control': 'no-store' } }) : await api.post('/admin/social' + path, body, { timeout: 120_000, headers: { 'Idempotency-Key': key ?? crypto.randomUUID(), 'Cache-Control': 'no-store' } });
    return decode(response.data);
  } catch (error) {
    if (error instanceof ConnectionError) throw error;
    if (axios.isAxiosError(error)) {
      const detail = object(error.response?.data ?? {}).detail;
      if (detail && typeof detail === 'object') {
        const d = detail as Record<string, unknown>;
        if (typeof d.code === 'string' && typeof d.message === 'string') throw new ConnectionError(d.code, d.message, typeof d.request_id === 'string' ? d.request_id : undefined);
      }
    }
    throw new ConnectionError('CONNECTION_REQUEST_FAILED', 'The connection request failed. Refresh account status before starting a new flow.');
  }
}
export function decodeSelectedAccounts(v: unknown): { flow_id: string; accounts: SocialAccount[] } {
  const o = exact(v, ['flow_id','accounts']);
  const accounts = array(o.accounts).map(raw => {
    const a = exact(raw, ['id','platform','display_name','handle','profile_url','connection_state','publishing_enabled','capabilities']);
    if (!['facebook','instagram'].includes(text(a.platform)) || a.publishing_enabled !== false) invalid();
    const c = exact(a.capabilities, ['rules_version','provider_api_version','eligible','supported_formats','feature_states','limits','granted_scopes','required_scopes','price_class','source_links','verified_at','adapter_available']);
    if (c.adapter_available !== false || c.price_class !== 'free') invalid();
    const formats = list(c.supported_formats);
    if (formats.some(f => !['text','image','carousel','video','reel'].includes(f))) invalid();
    const features = object(c.feature_states), limits = object(c.limits);
    if (Object.values(features).some(value => !['supported','restricted','requires_review','paid','unsupported','unverified'].includes(text(value))) || Object.values(limits).some(value => value !== null && (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0))) invalid();
    const profile = nullable(a.profile_url);
    if (profile) { const u = new URL(profile); if (u.protocol !== 'https:' || u.search || u.hash || u.username || u.password || !['www.facebook.com','www.instagram.com'].includes(u.hostname)) invalid(); }
    return { id: id(a.id), platform: a.platform as 'facebook' | 'instagram', display_name: text(a.display_name), handle: nullable(a.handle), profile_url: profile, connection_state: text(a.connection_state), publishing_enabled: false, capabilities: { rules_version: text(c.rules_version), provider_api_version: text(c.provider_api_version), eligible: bool(c.eligible), supported_formats: formats as SocialAccount['capabilities']['supported_formats'], feature_states: features as Record<string,string>, limits: limits as Record<string, number | null>, granted_scopes: list(c.granted_scopes), required_scopes: list(c.required_scopes), price_class: 'free' as const, source_links: list(c.source_links), verified_at: nullableDate(c.verified_at), adapter_available: false } };
  });
  if (!accounts.length || accounts.length > 2 || new Set(accounts.map(a => a.id)).size !== accounts.length) invalid();
  return { flow_id: id(o.flow_id), accounts };
}
export const connectionApi = {
  status: (signal?: AbortSignal) => request('/connections/meta/status', decodeConnectionStatus, undefined, undefined, signal),
  start: (redirect_uri: string, reconnect_account_id?: string) => request('/connections/meta/start', decodeStartedFlow, { redirect_uri, reconnect_account_id: reconnect_account_id ?? null, reason: reconnect_account_id ? 'Administrator requested account reconnection' : 'Administrator requested owned account connection' }),
  complete: (code: string, state: string, redirect_uri: string, key: string) => request('/connections/meta/complete', decodeDiscoveredFlow, { code, state, redirect_uri }, key),
  choices: (flow: string, signal?: AbortSignal) => request('/connections/meta/flows/' + id(flow), value => { const result = decodeDiscoveredFlow(value); if (result.flow_id !== flow) invalid(); return result; }, undefined, undefined, signal),
  select: (flow: string, page_id: string, instagram_id: string | null, key: string) => request('/connections/meta/flows/' + id(flow) + '/select', value => { const result = decodeSelectedAccounts(value); if (result.flow_id !== flow) invalid(); return result; }, { page_id, instagram_id, reason: 'Administrator explicitly confirmed selected Meta identities' }, key),
  health: (account: string, signal?: AbortSignal) => request('/accounts/' + id(account) + '/health', decodeAccountHealth, undefined, undefined, signal),
  disconnect: (account: string, credential: string, version: number, key: string) => request('/accounts/' + id(account) + '/disconnect', decodeAccountHealth, { expected_credential_id: id(credential), expected_credential_version: version, reason: 'Administrator disabled the local connection' }, key),
};
