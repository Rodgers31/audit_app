/** Metadata uses authenticated API; bytes use an isolated storage fetch. */
import api from '@/lib/api/axios';
import { SocialApiError, toSocialError } from './social';

export type MediaMime = 'image/jpeg' | 'image/png' | 'video/mp4';
export interface MediaAsset { id: string; version: number; filename: string; state: 'pending' | 'inspecting' | 'ready' | 'failed' | 'archived'; mime_type: MediaMime | null; byte_size: number | null; sha256: string | null; width: number | null; height: number | null; duration_ms: number | null; default_alt_text: string | null; safe_error: string | null; created_at: string }
export interface MediaCapabilities { upload_available: boolean; library_available: boolean; allowed_mime_types: MediaMime[]; max_image_bytes: number; max_video_bytes: number; unavailable_reason: string | null }
export interface MediaLibrary { assets: MediaAsset[]; total: number; page: number; page_size: number; has_more: boolean }
export interface MediaPreview { asset: MediaAsset; url: string; expires_at: string }
export interface UploadIntent { filename: string; declared_mime_type: MediaMime; declared_size: number; alt_text: string | null }
export interface UploadGrant extends MediaPreview { method: 'PUT'; headers: { 'Content-Type': MediaMime; 'If-None-Match': '*' } }
const mimes: MediaMime[] = ['image/jpeg', 'image/png', 'video/mp4'];
const bad = () => new SocialApiError('INVALID_MEDIA_RESPONSE', 'The media service returned an invalid response. Refresh before continuing.');
type ObjectValue = Record<string, unknown>;
function object(v: unknown, keys: string[]): ObjectValue { if (!v || typeof v !== 'object' || Array.isArray(v) || Object.keys(v).some(k => !keys.includes(k)) || keys.some(k => !(k in v))) throw bad(); return v as ObjectValue; }
function string(v: unknown, max = 2000): string { if (typeof v !== 'string' || v.length > max) throw bad(); return v; }
function number(v: unknown, min = 1, max = Number.MAX_SAFE_INTEGER): number { if (typeof v !== 'number' || !Number.isSafeInteger(v) || v < min || v > max) throw bad(); return v; }
function bool(v: unknown): boolean { if (typeof v !== 'boolean') throw bad(); return v; }
function nullableString(v: unknown): string | null { return v === null ? null : string(v); }
function nullableNumber(v: unknown, max?: number): number | null { return v === null ? null : number(v, 1, max); }
function uuid(v: unknown): string { const s = string(v, 36); if (!/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(s)) throw bad(); return s.toLowerCase(); }
function mime(v: unknown): MediaMime { if (!mimes.includes(v as MediaMime)) throw bad(); return v as MediaMime; }
function array(v: unknown, max = 50): unknown[] { if (!Array.isArray(v) || v.length > max) throw bad(); return v; }
function date(v: unknown): string { const s = string(v, 40); if (!/^\d{4}-\d\d-\d\dT.*(?:Z|\+00:00)$/.test(s) || !Number.isFinite(Date.parse(s))) throw bad(); return s; }
export function storageUrl(v: unknown): string {
  const s = string(v, 8000);
  if (/[\s\x00-\x20\x7f]/.test(s)) throw bad();
  let url: URL; try { url = new URL(s); } catch { throw bad(); }
  if (url.protocol !== 'https:' || !/^[a-f0-9]{32}\.r2\.cloudflarestorage\.com$/.test(url.hostname) || url.port || url.username || url.password || url.hash) throw bad();
  const params = url.searchParams, keys = Array.from(params.keys());
  const signed = params.get('X-Amz-Date') ?? '', ttl = params.get('X-Amz-Expires') ?? '';
  if (new Set(keys).size !== keys.length || params.get('X-Amz-Algorithm') !== 'AWS4-HMAC-SHA256' || !/^[0-9a-f]{64}$/.test(params.get('X-Amz-Signature') ?? '') || !/^.+\/[0-9]{8}\/auto\/s3\/aws4_request$/.test(params.get('X-Amz-Credential') ?? '') || !/^[0-9]{8}T[0-9]{6}Z$/.test(signed) || !/^[1-9][0-9]{0,2}$/.test(ttl) || Number(ttl) > 600 || !(params.get('X-Amz-SignedHeaders') ?? '').split(';').includes('host')) throw bad();
  const stamp = Date.parse(`${signed.slice(0, 4)}-${signed.slice(4, 6)}-${signed.slice(6, 8)}T${signed.slice(9, 11)}:${signed.slice(11, 13)}:${signed.slice(13, 15)}Z`);
  if (!Number.isFinite(stamp) || stamp > Date.now() + 30000 || stamp + Number(ttl) * 1000 <= Date.now()) throw bad();
  return s;
}
export function decodeMediaAsset(v: unknown): MediaAsset {
  const o = object(v, ['id', 'version', 'filename', 'state', 'mime_type', 'byte_size', 'sha256', 'width', 'height', 'duration_ms', 'default_alt_text', 'safe_error', 'created_at']);
  const state = string(o.state);
  if (!['pending', 'inspecting', 'ready', 'failed', 'archived'].includes(state)) throw bad();
  const sha = nullableString(o.sha256); if (sha !== null && !/^[0-9a-f]{64}$/.test(sha)) throw bad();
  const filename = string(o.filename, 200);
  if (!filename.trim() || /[/\\\x00-\x1f\x7f]/.test(filename)) throw bad();
  const asset: MediaAsset = { id: uuid(o.id), version: number(o.version), filename: string(o.filename, 200), state: state as MediaAsset['state'], mime_type: o.mime_type === null ? null : mime(o.mime_type), byte_size: nullableNumber(o.byte_size, 50 * 1024 * 1024), sha256: sha, width: nullableNumber(o.width, 10000), height: nullableNumber(o.height, 10000), duration_ms: nullableNumber(o.duration_ms, 120000), default_alt_text: nullableString(o.default_alt_text), safe_error: nullableString(o.safe_error), created_at: date(o.created_at) };
  if (state === 'ready' && (!asset.sha256 || !asset.mime_type || !asset.byte_size || !asset.width || !asset.height || asset.width * asset.height > 16000000 || (asset.mime_type === 'video/mp4') !== (asset.duration_ms !== null) || (asset.mime_type !== 'video/mp4' && asset.byte_size > 10 * 1024 * 1024))) throw bad();
  return asset;
}
export function decodeMediaCapabilities(v: unknown): MediaCapabilities {
  const o = object(v, ['upload_available', 'library_available', 'allowed_mime_types', 'max_image_bytes', 'max_video_bytes', 'unavailable_reason']);
  const allowed = array(o.allowed_mime_types, 3).map(mime), available = bool(o.upload_available);
  if (available !== (allowed.length > 0) || new Set(allowed).size !== allowed.length) throw bad();
  return { upload_available: available, library_available: bool(o.library_available), allowed_mime_types: allowed, max_image_bytes: number(o.max_image_bytes, 1, 10 * 1024 * 1024), max_video_bytes: number(o.max_video_bytes, 1, 50 * 1024 * 1024), unavailable_reason: nullableString(o.unavailable_reason) };
}
export function decodeMediaLibrary(v: unknown): MediaLibrary {
  const o = object(v, ['assets', 'total', 'page', 'page_size', 'has_more']);
  const assets = array(o.assets).map(decodeMediaAsset), total = number(o.total, 0), page = number(o.page), page_size = number(o.page_size, 1, 50), has_more = bool(o.has_more);
  if (assets.some(a => a.state !== 'ready') || new Set(assets.map(a => a.id)).size !== assets.length || assets.length > page_size || has_more !== (page * page_size < total) || assets.length !== Math.max(0, Math.min(page_size, total - (page - 1) * page_size))) throw bad();
  return { assets, total, page, page_size, has_more };
}
function expiry(v: unknown, url: string, maximum: number): string {
  const s = date(v), delta = Date.parse(s) - Date.now(), params = new URL(url).searchParams;
  const signed = params.get('X-Amz-Date')!;
  const stamp = Date.parse(`${signed.slice(0, 4)}-${signed.slice(4, 6)}-${signed.slice(6, 8)}T${signed.slice(9, 11)}:${signed.slice(11, 13)}:${signed.slice(13, 15)}Z`);
  if (delta <= 0 || delta > maximum * 1000 + 1000 || Number(params.get('X-Amz-Expires')) > maximum || Date.parse(s) > stamp + Number(params.get('X-Amz-Expires')) * 1000 + 1000) throw bad();
  return s;
}
export function decodeUploadGrant(v: unknown): UploadGrant {
  const o = object(v, ['asset', 'method', 'url', 'headers', 'expires_at']), headers = object(o.headers, ['Content-Type', 'If-None-Match']);
  const asset = decodeMediaAsset(o.asset), url = storageUrl(o.url);
  const path = new URL(url).pathname.split('/'), signed = new URL(url).searchParams.get('X-Amz-SignedHeaders')!.split(';');
  if (o.method !== 'PUT' || headers['If-None-Match'] !== '*' || asset.state !== 'pending' || asset.mime_type !== null || asset.byte_size !== null || asset.sha256 !== null || path.length !== 6 || !path[1] || path[2] !== 'quarantine' || uuid(path[3]) !== path[3] || path[4] !== asset.id || path[5] !== 'source' || !['host', 'content-length', 'content-type', 'if-none-match'].every(header => signed.includes(header))) throw bad();
  return { asset, method: 'PUT', url, headers: { 'Content-Type': mime(headers['Content-Type']), 'If-None-Match': '*' }, expires_at: expiry(o.expires_at, url, 600) };
}
export function decodeMediaPreview(v: unknown): MediaPreview {
  const o = object(v, ['asset', 'url', 'expires_at']), asset = decodeMediaAsset(o.asset), url = storageUrl(o.url);
  if (asset.state !== 'ready' || !new URL(url).pathname.endsWith(`/ready/${asset.id}/original`)) throw bad();
  return { asset, url, expires_at: expiry(o.expires_at, url, 300) };
}
async function get<T>(path: string, decode: (v: unknown) => T, signal?: AbortSignal, params?: object): Promise<T> {
  try { return decode((await api.get(`/admin/social/media${path}`, { signal, params })).data); } catch (error) { throw toSocialError(error); }
}
async function post<T>(path: string, body: object, key: string, decode: (v: unknown) => T): Promise<T> {
  try { return decode((await api.post(`/admin/social/media${path}`, body, { headers: { 'Idempotency-Key': key } })).data); } catch (error) { throw toSocialError(error); }
}
export const socialMediaApi = {
  capabilities: (signal?: AbortSignal) => get('/capabilities', decodeMediaCapabilities, signal),
  library: (page: number, q: string, kind: '' | 'image' | 'video', signal?: AbortSignal) => get('/assets', v => { const result = decodeMediaLibrary(v); if (result.page !== page || result.page_size !== 20) throw bad(); return result; }, signal, { page, page_size: 20, q, ...(kind ? { kind } : {}) }),
  preview: (id: string, signal?: AbortSignal) => get(`/assets/${encodeURIComponent(id)}/preview`, v => { const result = decodeMediaPreview(v); if (result.asset.id !== id.toLowerCase()) throw bad(); return result; }, signal),
  initiate: (body: UploadIntent, key: string) => post('/uploads', body, key, v => { const grant = decodeUploadGrant(v); if (grant.asset.filename !== body.filename || grant.headers['Content-Type'] !== body.declared_mime_type) throw bad(); return grant; }),
  complete: (id: string, version: number, key: string) => post(`/uploads/${encodeURIComponent(id)}/complete`, { expected_version: version }, key, v => { const asset = decodeMediaAsset(v); if (asset.id !== id || asset.state !== 'ready' || asset.version !== version + 1) throw bad(); return asset; }),
};
export async function putMediaFile(grant: UploadGrant, file: File): Promise<void> {
  const checked = decodeUploadGrant(grant);
  if (!(file instanceof File) || file.type !== checked.headers['Content-Type'] || !Number.isSafeInteger(file.size) || file.size <= 0 || file.size > (file.type === 'video/mp4' ? 50 : 10) * 1024 * 1024) throw bad();
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 120000);
  try {
    const response = await fetch(checked.url, { method: 'PUT', body: file, headers: checked.headers, credentials: 'omit', redirect: 'error', cache: 'no-store', mode: 'cors', signal: controller.signal });
    // A lost successful response can leave the create-only object in place.
    // Completion still inspects its actual bytes before admitting readiness.
    if (!response.ok && response.status !== 412) throw new Error('storage unavailable');
  } catch { throw new SocialApiError('MEDIA_UPLOAD_UNCONFIRMED', 'The upload could not be confirmed. Retry this file to inspect any completed upload.', [], [], true); }
  finally { clearTimeout(timeout); }
}
