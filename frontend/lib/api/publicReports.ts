import api from './axios';

export const reportDomains = ['national_budget', 'revenue_by_source', 'audits', 'pending_bills', 'counties_budget'] as const;
export type ReportDomain = typeof reportDomains[number];
export interface ReportSelector { domain: ReportDomain; documentId: string; view: 'report' | 'financial'; snapshot: string; entity?: string; record?: string }
export interface PublicFigure { entity: string; metric: string; period: string; value: string; display_value: string; unit: string; scale: string; classification: 'actual' | 'modelled' | 'projected'; comparison_basis: string; locator: string }
export interface PublicReport {
  schema_version: 1; domain: ReportDomain; view: 'report' | 'financial'; snapshot: string;
  title: string; entity: string; period: string; period_start: string | null; period_end: string | null;
  publisher: string; published_on: string | null; catalogued_on: string | null;
  availability: 'published' | 'catalogued'; figures: PublicFigure[];
  sources: { url: string; publisher: string; locator: string }[];
}
const invalid = () => new Error('The exact report response is unavailable.');
const object = (v: unknown): Record<string, unknown> => { if (!v || typeof v !== 'object' || Array.isArray(v)) throw invalid(); return v as Record<string, unknown>; };
const text = (v: unknown, max = 2000): string => { if (typeof v !== 'string' || !v.trim() || v.length > max) throw invalid(); return v; };
const id = (v: string | null) => typeof v === 'string' && /^[1-9]\d{0,9}$/.test(v) && Number(v) <= 2147483647;
function date(v: unknown): string | null {
  if (v === null) return null;
  const value = text(v, 10);
  if (!/^\d{4}-\d\d-\d\d$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value) throw invalid();
  return value;
}
export function reportSelector(domain: string, documentId: string, query: URLSearchParams): ReportSelector | undefined {
  if (!reportDomains.includes(domain as ReportDomain) || !id(documentId)) return;
  const view = query.get('view'), snapshot = query.get('snapshot'), entity = query.get('entity'), record = query.get('record');
  if ((view !== 'report' && view !== 'financial') || !snapshot || !/^[a-f0-9]{64}$/.test(snapshot)) return;
  if (Array.from(query.keys()).some(key => !['view', 'snapshot', 'entity', 'record'].includes(key)) || Array.from(new Set(Array.from(query.keys()))).some(key => query.getAll(key).length !== 1)) return;
  if (view === 'financial' ? (!id(record) || entity !== null) : (!id(entity) || (domain === 'counties_budget' ? !id(record) : record !== null))) return;
  return { domain: domain as ReportDomain, documentId, view, snapshot, ...(entity ? { entity } : {}), ...(record ? { record } : {}) };
}
export function decodePublicReport(raw: unknown, selector: ReportSelector): PublicReport {
  const value = object(raw);
  if (value.schema_version !== 1 || value.domain !== selector.domain || value.view !== selector.view || value.snapshot !== selector.snapshot) throw invalid();
  if (value.availability !== 'published' && value.availability !== 'catalogued') throw invalid();
  const period_start = date(value.period_start), period_end = date(value.period_end), published_on = date(value.published_on), catalogued_on = date(value.catalogued_on);
  if ((period_start === null) !== (period_end === null) || (period_start && period_end && period_start > period_end)) throw invalid();
  if (value.availability === 'catalogued' ? (published_on !== null || catalogued_on === null) : published_on === null) throw invalid();
  if (!Array.isArray(value.figures) || value.figures.length > 10 || !Array.isArray(value.sources) || !value.sources.length || value.sources.length > 10) throw invalid();
  const entity = text(value.entity), period = text(value.period);
  const figures = value.figures.map(item => {
    const f = object(item), amount = text(f.value, 30);
    if (f.entity !== entity || f.period !== period) throw invalid();
    if (!/^-?(?:0|[1-9]\d{0,17})(?:\.\d{1,8})?$/.test(amount) || !['actual', 'modelled', 'projected'].includes(f.classification as string) || !['units','thousands','millions','billions'].includes(f.scale as string)) throw invalid();
    return { entity: text(f.entity), metric: text(f.metric), period: text(f.period), value: amount, display_value: text(f.display_value), unit: text(f.unit), scale: text(f.scale), classification: f.classification as PublicFigure['classification'], comparison_basis: text(f.comparison_basis), locator: text(f.locator) };
  });
  if (selector.view === 'financial' ? !figures.length : !!figures.length) throw invalid();
  const sources = value.sources.map(item => {
    const source = object(item), url = text(source.url, 2048);
    let parsed: URL; try { parsed = new URL(url); } catch { throw invalid(); }
    if (parsed.protocol !== 'https:' || !parsed.hostname || parsed.username || parsed.password || (parsed.port && parsed.port !== '443') || /[\s\\]/.test(url)) throw invalid();
    return { url, publisher: text(source.publisher), locator: text(source.locator) };
  });
  return { schema_version: 1, domain: selector.domain, view: selector.view, snapshot: selector.snapshot, title: text(value.title), entity, period, period_start, period_end, publisher: text(value.publisher), published_on, catalogued_on, availability: value.availability, figures, sources };
}
export async function getPublicReport(selector: ReportSelector, signal?: AbortSignal): Promise<PublicReport> {
  const { domain, documentId, ...params } = selector;
  return decodePublicReport((await api.get(`/reports/${domain}/${documentId}`, { params, signal })).data, selector);
}
