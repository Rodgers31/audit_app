import api from './axios';
import { decodePost, SocialApiError, toSocialError } from './social';

export interface Composition { schema_version: 1; template: string; template_version: 1; kind: 'graphic' | 'video'; revision_id: string; title: string; facts: { id: string; text: string; source_url: string }[]; scenes: { fact_id: string; seconds: number }[] }
export interface RenderJob { id: string; revision_id: string; state: 'queued' | 'running' | 'ready' | 'failed' | 'cancelled'; version: number; composition: Composition; sha256: string | null; approved_sha256: string | null; safe_error: string | null; cancel_requested: boolean; attempt: number; retry_of_id: string | null }
export interface StudioCapabilities { rendering_available: boolean; unavailable_reason: string | null; templates: string[]; template_version: number; analytics_collection_available: boolean; analytics_reason: string; uploads_enabled: false }
export interface CalendarItem { publication_id: string; post_id: string; title: string; revision_id: string; scheduled_for: string; timezone: string | null; cancel_requested: boolean; revoked: boolean }
export interface ProviderMetric { name: string; api_version: string; unit: string; period: string; window_start: string; window_end: string; collected_at: string; available_until: string; status: 'available' | 'unavailable'; value: number | null; reason: string | null; freshness: 'fresh' | 'stale' }
export interface Analytics { target_id: string; platform: string; availability: 'observed' | 'unavailable'; reason: string | null; collections: { id: string; state: string; reason: string | null; remote_id: string; created_at: string; metrics: ProviderMetric[] }[]; page: number; has_more: boolean }
const invalid = () => new SocialApiError('INVALID_STUDIO_RESPONSE', 'The studio response is invalid. Refresh before continuing.');
export const templateRoles: Record<string, readonly string[]> = { debt_update: ['metric', 'period', 'value'], audit_finding: ['entity', 'finding', 'period'], budget_update: ['entity', 'period', 'value'], new_report: ['report', 'publisher', 'publication_date'], did_you_know: ['fact', 'context'], educational: ['term', 'definition'] };
function object(v: unknown): Record<string, unknown> { if (!v || typeof v !== 'object' || Array.isArray(v)) throw invalid(); return v as Record<string, unknown>; }
function text(v: unknown, max = 2048): string { if (typeof v !== 'string' || v.length > max) throw invalid(); return v; }
function nullable(v: unknown): string | null { return v === null ? null : text(v); }
function integer(v: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): number { if (typeof v !== 'number' || !Number.isSafeInteger(v) || v < min || v > max) throw invalid(); return v; }
function bool(v: unknown): boolean { if (typeof v !== 'boolean') throw invalid(); return v; }
function array(v: unknown, max: number): unknown[] { if (!Array.isArray(v) || v.length > max) throw invalid(); return v; }
function uuid(v: unknown): string { const s = text(v, 36); if (!/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(s)) throw invalid(); return s; }
function hash(v: unknown): string | null { const s = nullable(v); if (s !== null && !/^[0-9a-f]{64}$/.test(s)) throw invalid(); return s; }
function date(v: unknown): string { const s = text(v, 40); if (!/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(s) || !Number.isFinite(Date.parse(s))) throw invalid(); return s; }
function one<T extends string>(v: unknown, options: readonly T[]): T { if (!options.includes(v as T)) throw invalid(); return v as T; }
function printable(v: unknown, max: number): string { const s = text(v, max); if (!s.trim() || !/^[\x20-\x7e]+$/.test(s) || /\{|\}|\[[a-zA-Z_][^]]*\]|<[^>]+>/.test(s)) throw invalid(); return s; }
function source(v: unknown): string { const s = text(v); let u: URL; try { u = new URL(s); } catch { throw invalid(); } if (u.protocol !== 'https:' || !u.hostname || u.username || u.password || /\s/.test(s)) throw invalid(); return s; }
export function decodeJob(v: unknown): RenderJob {
  const o = object(v), c = object(o.composition);
  const facts = array(c.facts, 6).map(v => { const f = object(v); return { id: text(f.id, 80), text: printable(f.text, 180), source_url: source(f.source_url) }; });
  const scenes = array(c.scenes, 6).map(v => { const s = object(v); return { fact_id: text(s.fact_id, 80), seconds: integer(s.seconds, 3, 15) }; });
  if (c.schema_version !== 1 || c.template_version !== 1 || !facts.length || !scenes.length || new Set(facts.map(f => f.id)).size !== facts.length || scenes.some(s => !facts.some(f => f.id === s.fact_id))) throw invalid();
  const template = one(c.template, Object.keys(templateRoles)), kind = one(c.kind, ['graphic', 'video']);
  const required = templateRoles[template];
  if (facts.length !== required.length || required.some(role => !facts.some(f => f.id === role)) || kind === 'graphic' && scenes.length !== 1 || kind === 'video' && (required.some(role => !scenes.some(s => s.fact_id === role)) || scenes.reduce((n, s) => n + s.seconds, 0) < 15 || scenes.reduce((n, s) => n + s.seconds, 0) > 45)) throw invalid();
  const composition: Composition = { schema_version: 1, template, template_version: 1, kind, revision_id: uuid(c.revision_id), title: printable(c.title, 70), facts, scenes };
  const job: RenderJob = { id: uuid(o.id), revision_id: uuid(o.revision_id), state: one(o.state, ['queued', 'running', 'ready', 'failed', 'cancelled']), version: integer(o.version, 1), composition, sha256: hash(o.sha256), approved_sha256: hash(o.approved_sha256), safe_error: nullable(o.safe_error), cancel_requested: bool(o.cancel_requested), attempt: integer(o.attempt, 1, 2), retry_of_id: o.retry_of_id === null ? null : uuid(o.retry_of_id) };
  if (job.revision_id !== composition.revision_id || job.state === 'ready' && (!job.sha256 || !o.inspection) || job.approved_sha256 !== null && (job.state !== 'ready' || job.approved_sha256 !== job.sha256)) throw invalid();
  if ((job.attempt === 1) !== (job.retry_of_id === null) || !hash(o.input_hash)) throw invalid();
  if (job.state === 'ready') {
    const inspection = object(o.inspection);
    const duration = scenes.reduce((n, s) => n + s.seconds, 0) * 1000;
    if (hash(inspection.sha256) !== job.sha256 || !hash(o.runtime_hash) || integer(inspection.width) !== 720 || integer(inspection.height) !== 1280 || integer(inspection.byte_size, 1, 50 * 1024 * 1024) < 1 || inspection.mime_type !== (kind === 'video' ? 'video/mp4' : 'image/png') || (kind === 'video' ? Math.abs(integer(inspection.duration_ms, 1, 45000) - duration) > 100 : inspection.duration_ms !== null)) throw invalid();
  } else if (o.inspection !== null || job.sha256 !== null || o.runtime_hash !== null) throw invalid();
  return job;
}
export function decodeCapabilities(v: unknown): StudioCapabilities {
  const o = object(v);
  if (o.uploads_enabled !== false || o.template_version !== 1) throw invalid();
  return { rendering_available: bool(o.rendering_available), unavailable_reason: nullable(o.unavailable_reason), templates: array(o.templates, 6).map(v => text(v, 80)), template_version: 1, analytics_collection_available: bool(o.analytics_collection_available), analytics_reason: text(o.analytics_reason), uploads_enabled: false };
}
export function decodeCalendar(v: unknown) {
  const o = object(v);
  return { items: array(o.items, 50).map(v => { const r = object(v); return { publication_id: uuid(r.publication_id), post_id: uuid(r.post_id), title: text(r.title, 300), revision_id: uuid(r.revision_id), scheduled_for: date(r.scheduled_for), timezone: nullable(r.timezone), cancel_requested: bool(r.cancel_requested), revoked: bool(r.revoked) }; }), page: integer(o.page, 1), has_more: bool(o.has_more) };
}
export function decodeAnalytics(v: unknown): Analytics {
  const o = object(v);
  const collections = array(o.collections, 10).map(v => {
    const c = object(v);
    return { id: uuid(c.id), state: one(c.state, ['reserved', 'collected', 'unavailable', 'failed']), reason: nullable(c.reason), remote_id: text(c.remote_id, 512), created_at: date(c.created_at), metrics: array(c.metrics, 20).map(v => {
      const m = object(v), status = one(m.status, ['available', 'unavailable']), value = m.value === null ? null : integer(m.value);
      const metric: ProviderMetric = { name: text(m.name, 80), api_version: text(m.api_version, 80), unit: text(m.unit, 80), period: text(m.period, 80), window_start: date(m.window_start), window_end: date(m.window_end), collected_at: date(m.collected_at), available_until: date(m.available_until), status, value, reason: nullable(m.reason), freshness: one(m.freshness, ['fresh', 'stale']) };
      if ((status === 'available') !== (value !== null) || (status === 'unavailable') !== (metric.reason !== null) || !(Date.parse(metric.window_start) < Date.parse(metric.window_end) && Date.parse(metric.window_end) <= Date.parse(metric.collected_at) && Date.parse(metric.collected_at) < Date.parse(metric.available_until))) throw invalid();
      if (Date.parse(metric.available_until) - Date.parse(metric.collected_at) > 86400000) throw invalid();
      if (Date.parse(metric.available_until) <= Date.now()) metric.freshness = 'stale';
      return metric;
    }) };
  });
  return { target_id: uuid(o.target_id), platform: one(o.platform, ['facebook', 'instagram', 'threads', 'x', 'tiktok']), availability: one(o.availability, ['observed', 'unavailable']), reason: nullable(o.reason), collections, page: integer(o.page, 1), has_more: bool(o.has_more) };
}
const base = '/admin/social/studio';
async function get<T>(path: string, decode: (v: unknown) => T, params?: object): Promise<T> { try { return decode((await api.get(base + path, { params })).data); } catch (e) { throw toSocialError(e); } }
async function post<T>(path: string, body: object, key: string, decode: (v: unknown) => T): Promise<T> { try { return decode((await api.post(base + path, body, { headers: { 'Idempotency-Key': key } })).data); } catch (e) { throw toSocialError(e); } }
export const studioApi = {
  capabilities: () => get('/capabilities', decodeCapabilities),
  jobs: (page: number) => get('/jobs', v => { const o = object(v); return { jobs: array(o.jobs, 10).map(decodeJob), page: integer(o.page, 1), has_more: bool(o.has_more) }; }, { page }),
  create: (composition: Composition, key: string) => post('/jobs', composition, key, decodeJob),
  cancel: (job: RenderJob, key: string) => post(`/jobs/${job.id}/cancel`, { expected_version: job.version }, key, decodeJob),
  retry: (job: RenderJob, key: string) => post(`/jobs/${job.id}/retry`, { expected_version: job.version }, key, decodeJob),
  approve: (job: RenderJob, key: string) => post(`/jobs/${job.id}/approve`, { expected_version: job.version, sha256: job.sha256, review_attestation: { facts_checked: true, sources_checked: true } }, key, decodeJob),
  attach: (job: RenderJob, assetId: string, postVersion: number, key: string) => post(`/jobs/${job.id}/attach`, { expected_version: postVersion, asset_id: assetId }, key, decodePost),
  calendar: (start: string, end: string, page: number) => get('/calendar', decodeCalendar, { start, end, page }),
  analytics: (targetId: string, page: number) => get(`/analytics/${encodeURIComponent(targetId)}`, decodeAnalytics, { page }),
  async media(job: RenderJob): Promise<string> {
    try {
      const response = await api.get(`${base}/jobs/${job.id}/preview`, { responseType: 'arraybuffer' });
      if (!(response.data instanceof ArrayBuffer) || response.data.byteLength > 50 * 1024 * 1024) throw invalid();
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', response.data))).map(b => b.toString(16).padStart(2, '0')).join('');
      if (!job.sha256 || digest !== job.sha256 || response.headers['x-content-sha256'] !== job.sha256) throw invalid();
      return URL.createObjectURL(new Blob([response.data], { type: job.composition.kind === 'video' ? 'video/mp4' : 'image/png' }));
    } catch (e) { throw toSocialError(e); }
  },
  async subtitles(job: RenderJob): Promise<string> {
    try { const response = await api.get(`${base}/jobs/${job.id}/transcript`, { params: { format: 'srt' }, responseType: 'text' }); if (response.headers['x-content-sha256'] !== job.sha256 || typeof response.data !== 'string' || response.data.length > 10000) throw invalid(); return URL.createObjectURL(new Blob([response.data], { type: 'application/x-subrip' })); } catch (e) { throw toSocialError(e); }
  },
};
