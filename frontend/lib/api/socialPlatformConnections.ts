/** Explicit, session-bound platform account operations. Provider tokens never enter browser DTOs. */
import api from './axios';
import { ConnectionError } from './socialConnections';

export type ConnectionPlatform = 'threads' | 'x' | 'tiktok';
export interface PlatformStatus { provider: ConnectionPlatform; available: boolean; blockers: string[]; scopes: string[]; provider_api_version: string; publishing_enabled: false }
export interface PlatformFlow { flow_id: string; authorize_url: string; expires_at: string }
export interface PlatformChoice { flow_id: string; external_account_id: string; display_name: string; handle: string | null; granted_scopes: string[]; expires_at: string }
export interface PlatformHealth { account_id: string; platform: ConnectionPlatform; connection_state: string; credential_id: string; credential_version: number; access_expires_at: string; refresh_pending: boolean; reconnect_required: boolean; publishing_enabled: boolean }
export interface CreatorSettings { account_id: string; external_account_id: string; display_name: string; handle: string | null; settings: { privacy_level_options: Array<'PUBLIC_TO_EVERYONE' | 'MUTUAL_FOLLOW_FRIENDS' | 'FOLLOWER_OF_CREATOR' | 'SELF_ONLY'>; comment_disabled: boolean; duet_disabled: boolean; stitch_disabled: boolean; max_video_post_duration_sec: number }; checked_at: string; settings_hash: string; credential_version: number }
function invalid(): never { throw new ConnectionError('INVALID_RESPONSE','The platform connection response could not be verified. Refresh before continuing.'); }
function object(v: unknown): Record<string, unknown> { if (!v || typeof v !== 'object' || Array.isArray(v)) return invalid(); return v as Record<string, unknown>; }
function text(v: unknown): string { if (typeof v !== 'string') return invalid(); return v; }
function bool(v: unknown): boolean { if (typeof v !== 'boolean') return invalid(); return v; }
function strings(v: unknown): string[] { if (!Array.isArray(v)) return invalid(); return v.map(text); }
function uuid(v: unknown) { const s=text(v); if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s)) return invalid(); return s; }
function date(v: unknown) { const s=text(v); if (!Number.isFinite(Date.parse(s)) || !/(?:Z|[+-]\d{2}:\d{2})$/.test(s)) return invalid(); return s; }
function integer(v: unknown) { if (typeof v !== 'number' || !Number.isSafeInteger(v) || v<1) return invalid(); return v; }
export function decodePlatformStatus(v: unknown): PlatformStatus { const o=object(v); const provider=text(o.provider) as ConnectionPlatform; if (!['threads','x','tiktok'].includes(provider) || o.publishing_enabled !== false) return invalid(); const available=bool(o.available), blockers=strings(o.blockers); if (available !== !blockers.length) return invalid(); return { provider,available,blockers,scopes:strings(o.scopes),provider_api_version:text(o.provider_api_version),publishing_enabled:false }; }
export function decodePlatformFlow(v: unknown, provider: ConnectionPlatform): PlatformFlow {
  const o=object(v), url=new URL(text(o.authorize_url));
  const allowed = provider==='threads' ? url.hostname==='threads.com' && url.pathname==='/oauth/authorize' : provider==='x' ? url.hostname==='x.com' && url.pathname==='/i/oauth2/authorize' : url.hostname==='www.tiktok.com' && url.pathname==='/v2/auth/authorize';
  if (!allowed || url.protocol!=='https:' || url.username || url.password || url.port || url.hash || !/^[A-Za-z0-9_-]{43}$/.test(url.searchParams.get('state')??'') || ['access_token','refresh_token','client_secret','code'].some(k=>url.searchParams.has(k))) return invalid();
  if (provider==='x' && (url.searchParams.get('code_challenge_method')!=='S256' || !/^[A-Za-z0-9_-]{43}$/.test(url.searchParams.get('code_challenge')??''))) return invalid();
  return { flow_id:uuid(o.flow_id),authorize_url:url.href,expires_at:date(o.expires_at) };
}
export function decodePlatformChoice(v: unknown): PlatformChoice { const o=object(v); return { flow_id:uuid(o.flow_id),external_account_id:text(o.external_account_id),display_name:text(o.display_name),handle:o.handle===null?null:text(o.handle),granted_scopes:strings(o.granted_scopes),expires_at:date(o.expires_at) }; }
export function decodePlatformHealth(v: unknown): PlatformHealth { const o=object(v),platform=text(o.platform) as ConnectionPlatform; if (!['threads','x','tiktok'].includes(platform)) return invalid(); return {account_id:uuid(o.account_id),platform,connection_state:text(o.connection_state),credential_id:uuid(o.credential_id),credential_version:integer(o.credential_version),access_expires_at:date(o.access_expires_at),refresh_pending:bool(o.refresh_pending),reconnect_required:bool(o.reconnect_required),publishing_enabled:bool(o.publishing_enabled)}; }
export function decodeCreatorSettings(v: unknown): CreatorSettings { const o=object(v),s=object(o.settings); const privacy=strings(s.privacy_level_options); if (!privacy.length || new Set(privacy).size!==privacy.length || privacy.some(p=>!['PUBLIC_TO_EVERYONE','MUTUAL_FOLLOW_FRIENDS','FOLLOWER_OF_CREATOR','SELF_ONLY'].includes(p)) || !/^[0-9a-f]{64}$/.test(text(o.settings_hash))) return invalid(); return {account_id:uuid(o.account_id),external_account_id:text(o.external_account_id),display_name:text(o.display_name),handle:o.handle===null?null:text(o.handle),settings:{privacy_level_options:privacy as CreatorSettings['settings']['privacy_level_options'],comment_disabled:bool(s.comment_disabled),duet_disabled:bool(s.duet_disabled),stitch_disabled:bool(s.stitch_disabled),max_video_post_duration_sec:integer(s.max_video_post_duration_sec)},checked_at:date(o.checked_at),settings_hash:text(o.settings_hash),credential_version:integer(o.credential_version)}; }
async function request<T>(path: string, decode: (v: unknown)=>T, body?: unknown, key?: string): Promise<T> {
  try { const response=body===undefined ? await api.get('/admin/social/platform-connections'+path,{headers:{'Cache-Control':'no-store'}}) : await api.post('/admin/social/platform-connections'+path,body,{headers:{'Idempotency-Key':key??crypto.randomUUID(),'Cache-Control':'no-store'}}); return decode(response.data); }
  catch(error) { if(error instanceof ConnectionError) throw error; throw new ConnectionError('PLATFORM_CONNECTION_FAILED','The platform operation failed. Refresh its current state before retrying.'); }
}
export const platformConnectionApi={
  status:(provider:ConnectionPlatform)=>request('/'+provider+'/status',decodePlatformStatus),
  start:(provider:ConnectionPlatform,redirect_uri:string,key:string)=>request('/'+provider+'/start',v=>decodePlatformFlow(v,provider),{redirect_uri,reason:'Connect an explicitly approved owned account'},key),
  complete:(provider:ConnectionPlatform,code:string,state:string,redirect_uri:string,key:string)=>request('/'+provider+'/complete',decodePlatformChoice,{code,state,redirect_uri},key),
  choice:(provider:ConnectionPlatform,id:string)=>request('/'+provider+'/flows/'+encodeURIComponent(id),decodePlatformChoice),
  confirm:(provider:ConnectionPlatform,choice:PlatformChoice,key:string)=>request('/'+provider+'/flows/'+encodeURIComponent(choice.flow_id)+'/confirm',v=>{const o=object(v);uuid(o.flow_id);const a=object(o.account);uuid(a.id);if(a.publishing_enabled!==false)return invalid();return {account_id:uuid(a.id)};},{external_account_id:choice.external_account_id,reason:'Confirm the exact provider account'},key),
  health:(provider:ConnectionPlatform,id:string)=>request('/'+provider+'/accounts/'+encodeURIComponent(id)+'/health',decodePlatformHealth),
  accountCommand:(provider:ConnectionPlatform,id:string,action:'refresh'|'disconnect',health:PlatformHealth,key:string)=>request('/'+provider+'/accounts/'+encodeURIComponent(id)+'/'+action,decodePlatformHealth,{expected_credential_id:health.credential_id,expected_credential_version:health.credential_version,reason:action==='refresh'?'Renew the existing account grant':'Disable the local provider account'},key),
  creatorSettings:(id:string)=>request('/tiktok/accounts/'+encodeURIComponent(id)+'/creator-settings',decodeCreatorSettings),
};
