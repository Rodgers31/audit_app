import api from './axios';
import { generationReasons } from '@/lib/socialGenerationReasons';
import { DocumentTarget, decodeDocument, SocialApiError } from './social';

export const sourceTypes = ['treasury', 'cob', 'oag', 'knbs', 'cra', 'kra'] as const;
export interface DraftControls { version: number; drafts_enabled: boolean; shadow_enabled: boolean; source_allowlist: string[]; targets: DocumentTarget[] }
export interface ShadowRule { id: string; version: number; definition: { name: string; mode: 'disabled' | 'shadow'; categories: string[]; source_allowlist: string[]; account_allowlist: string[]; max_per_day: number; min_interval_minutes: number; freshness_hours: number; reason: string }; definition_hash: string; created_at: string }
export interface ShadowDecision { id: string; post_id: string; revision_id: string; content_hash: string; outcome: 'would_allow' | 'human_review'; reasons: string[]; rule_version_id: string; rule_hash: string; created_at: string }
export interface EvidenceFact { fact_id: string; entity: string; metric: string; period: string; comparison_basis: string; value: string; unit: string; scale: string; classification: string; document_url: string; locator: string; document_checksum: string; publisher: string; published_on: string; retrieved_at: string; verified_at: string }
interface EvidenceReportBase { source_record_id: number; authority_fingerprint: string; entity_id: number; entity: string; period: string; period_start: string; period_end: string; source_document_id: number; document_url: string; document_checksum: string; publisher: string; retrieved_at: string; verified_at: string; canonical_url: string; locator: string; publication_extraction_id: number; qualification_extraction_id: number }
type EvidenceReportDates = { published_on: string; evidence_kind?: never; catalogued_on?: never; catalogue_url?: never } | { published_on: null; evidence_kind: 'publisher_catalogue'; catalogued_on: string; catalogue_url: string };
export type EvidenceReport = EvidenceReportBase & EvidenceReportDates;
export interface PostEvidence { post_id: string; revision_id: string; source_event_id: string | null; evidence: { evidence_version?: number; source?: { facts: EvidenceFact[]; report?: EvidenceReport; source_type: string; source_key: string; ingestion_id: string } }; generator_metadata: { template_version?: string } | null }
export interface Page<T> { total: number; page: number; page_size: number; has_more: boolean; items: T[] }
function fail(): never { throw new SocialApiError('INVALID_RESPONSE', 'The generation service returned an invalid response. Refresh before continuing.'); }
function obj(v: unknown): Record<string, unknown> { if (!v || typeof v !== 'object' || Array.isArray(v)) fail(); return v as Record<string, unknown>; }
function text(v: unknown): string { if (typeof v !== 'string') fail(); return v; }
function number(v: unknown): number { if (typeof v !== 'number' || !Number.isSafeInteger(v) || v < 0) fail(); return v; }
function boolean(v: unknown): boolean { if (typeof v !== 'boolean') fail(); return v; }
function list(v: unknown): unknown[] { if (!Array.isArray(v)) fail(); return v; }
function strings(v: unknown): string[] { return list(v).map(text); }
export function decodeDraftControls(v: unknown): DraftControls { const o = obj(v); return { version: number(o.version), drafts_enabled: boolean(o.drafts_enabled), shadow_enabled: boolean(o.shadow_enabled), source_allowlist: strings(o.source_allowlist), targets: decodeDocument({ schema_version: 1, master: { text: '', link: null, hashtags: [], media: [] }, targets: o.targets }).targets }; }
export function decodeRule(v: unknown): ShadowRule { const o = obj(v), d = obj(o.definition); if (d.mode !== 'shadow' && d.mode !== 'disabled') fail(); return { id: text(o.id), version: number(o.version), definition_hash: text(o.definition_hash), created_at: text(o.created_at), definition: { name: text(d.name), mode: d.mode, categories: strings(d.categories), source_allowlist: strings(d.source_allowlist), account_allowlist: strings(d.account_allowlist), max_per_day: number(d.max_per_day), min_interval_minutes: number(d.min_interval_minutes), freshness_hours: number(d.freshness_hours), reason: text(d.reason) } }; }
export function decodeDecision(v: unknown): ShadowDecision { const o = obj(v); if (o.outcome !== 'would_allow' && o.outcome !== 'human_review') fail(); return { id: text(o.id), post_id: text(o.post_id), revision_id: text(o.revision_id), content_hash: text(o.content_hash), outcome: o.outcome, reasons: strings(o.reasons), rule_version_id: text(o.rule_version_id), rule_hash: text(obj(o.inputs).rule_hash), created_at: text(o.created_at) }; }
function page<T>(v: unknown, key: string, decode: (v: unknown) => T): Page<T> { const o = obj(v); return { total: number(o.total), page: number(o.page), page_size: number(o.page_size), has_more: boolean(o.has_more), items: list(o[key]).map(decode) }; }
function decodeReport(v: unknown): EvidenceReport {
  const o = obj(v);
  const positive = (v: unknown) => { const result = number(v); if (result < 1) fail(); return result; };
  if (typeof o.authority_fingerprint !== 'string' || !/^[a-f0-9]{64}$/.test(o.authority_fingerprint)) fail();
  let dates: EvidenceReportDates;
  if (o.evidence_kind === 'publisher_catalogue') {
    if (o.published_on !== null || o.native_domain !== 'revenue_by_source' || o.publisher !== 'Kenya Revenue Authority'
        || o.catalogue_url !== 'https://www.kra.go.ke/component/search/?searchphrase=all&searchword=KRA+performance'
        || typeof o.catalogued_on !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(o.catalogued_on)) fail();
    dates = { published_on: null, evidence_kind: 'publisher_catalogue', catalogued_on: text(o.catalogued_on), catalogue_url: text(o.catalogue_url) };
  } else {
    if (o.evidence_kind !== undefined || o.catalogued_on !== undefined || o.catalogue_url !== undefined) fail();
    dates = { published_on: text(o.published_on) };
  }
  return { source_record_id: positive(o.source_record_id), authority_fingerprint: text(o.authority_fingerprint), entity_id: positive(o.entity_id), entity: text(o.entity), period: text(o.period),
    period_start: text(o.period_start), period_end: text(o.period_end), source_document_id: positive(o.source_document_id),
    document_url: text(o.document_url), document_checksum: text(o.document_checksum), publisher: text(o.publisher),
    ...dates, retrieved_at: text(o.retrieved_at), verified_at: text(o.verified_at),
    canonical_url: text(o.canonical_url), locator: text(o.locator), publication_extraction_id: positive(o.publication_extraction_id),
    qualification_extraction_id: positive(o.qualification_extraction_id) };
}
export function decodeEvidence(v: unknown): PostEvidence { const o = obj(v), evidence = obj(o.evidence), source = evidence.source === undefined ? undefined : obj(evidence.source); if (source?.report != null && list(source.facts).length) fail(); return { post_id: text(o.post_id), revision_id: text(o.revision_id), source_event_id: o.source_event_id === null ? null : text(o.source_event_id), generator_metadata: o.generator_metadata === null ? null : { template_version: text(obj(o.generator_metadata).template_version) }, evidence: { ...(evidence.evidence_version === undefined ? {} : { evidence_version: number(evidence.evidence_version) }), ...(source ? { source: { source_type: text(source.source_type), source_key: text(source.source_key), ingestion_id: text(source.ingestion_id), ...(source.report == null ? {} : { report: decodeReport(source.report) }), facts: list(source.facts).map(raw => { const f = obj(raw); const fields = ['fact_id', 'entity', 'metric', 'period', 'comparison_basis', 'value', 'unit', 'scale', 'classification', 'document_url', 'locator', 'document_checksum', 'publisher', 'published_on', 'retrieved_at', 'verified_at'] as const; const fact = {} as EvidenceFact; for (const field of fields) fact[field] = text(f[field]); return fact; }) } } : {}) } }; }
const base = '/admin/social';
export const generationApi = {
  capabilities: async (signal?: AbortSignal) => decodeCapabilities((await api.get(`${base}/generation/capabilities`, { signal })).data),
  preview: async (body: { domain: string; record_ids: number[]; ingestion_id: number; reports: boolean; backfill: boolean }) => { const result = decodePreview((await api.post(`${base}/generation/preview`, body)).data); if (result.results.length !== body.record_ids.length || result.results.some((r, i) => r.record_id !== body.record_ids[i])) fail(); return result; },
  controls: async (signal?: AbortSignal) => decodeDraftControls((await api.get(`${base}/generation/controls`, { signal })).data),
  rules: async (p = 1, signal?: AbortSignal) => page((await api.get(`${base}/automation/rules`, { params: { page: p }, signal })).data, 'rules', decodeRule),
  decisions: async (p = 1, post_id?: string, signal?: AbortSignal) => page((await api.get(`${base}/automation/decisions`, { params: { page: p, post_id }, signal })).data, 'decisions', decodeDecision),
  evidence: async (id: string, revision: string, signal?: AbortSignal) => { const result = decodeEvidence((await api.get(`${base}/posts/${encodeURIComponent(id)}/evidence`, { signal })).data); if (result.post_id !== id || result.revision_id !== revision) fail(); return result; },
};
export function decodeDetection(v: unknown) { return list(obj(v).results).map(raw => { const r = obj(raw); if (!['baseline', 'unchanged', 'draft_created'].includes(text(r.status))) fail(); return { status: text(r.status), post_id: r.post_id === null ? null : text(r.post_id), sequence: number(r.sequence) }; }); }

const decisionReasons: Record<string, string> = {
  RULE_DISABLED: 'This rule version is disabled.',
  EDITORIAL_REVIEW_REQUIRED: 'The post was rejected or archived and needs editorial review.',
  GENERATED_SOURCE_REQUIRED: 'A generated post with an immutable source event is required.',
  SOURCE_REVIEW_REQUIRED: 'The current report source authority changed. Review its evidence again.',
  CATALOGUE_HUMAN_REVIEW_REQUIRED: 'Only the catalogue entry date is known. Human review is required; automatic approval is unavailable.',
  SOURCE_SUPERSEDED: 'A newer source event superseded this evidence.',
  SOURCE_CATEGORY_NOT_ALLOWLISTED: 'This source or content category is outside the rule allowlist.',
  GENERATED_COPY_EDITED: 'The factual template was edited and requires human review.',
  CORRECTION_REQUIRES_REVIEW: 'A correction is pending and requires human review.',
  EVIDENCE_STALE: 'The evidence verification is outside the rule freshness window.',
  EVIDENCE_INTEGRITY_FAILED: 'The evidence does not match its immutable source event.',
  REVISION_INTEGRITY_FAILED: 'The revision hash does not match the saved content.',
  CUSTOMIZATION_REQUIRES_REVIEW: 'A destination was customized and requires human review.',
  ACCOUNT_NOT_ALLOWLISTED: 'Choose destinations included in the account allowlist.',
  TARGET_VALIDATION_FAILED: 'A selected destination failed validation; inspect its account and content.',
  BUDGET_OR_AUTOMATION_ACCESS_UNVERIFIED: 'Platform budget or unattended access has not been verified.',
  DAILY_CADENCE_LIMIT: 'The account reached its suggestion limit for the last 24 hours.',
  MINIMUM_INTERVAL: 'The account needs more time between suggestions.',
  CADENCE_HISTORY_LIMIT: 'The bounded history limit was reached; inspect cadence manually.',
  ALL_SHADOW_GATES_PASSED_HUMAN_APPROVAL_REQUIRED: 'All shadow gates passed. Human approval is still required.',
};
export function describeShadowReason(code: string): string { return decisionReasons[code] ?? `Unrecognized decision reason: ${code}`; }


export interface GenerationCapability { domain: string; financial: boolean; reports: boolean; reason: string }
export interface GenerationPreviewResult { record_id: number; status: string; reason: string; source_document_id: number | null }
export interface GenerationPreview { drafts_enabled: boolean; results: GenerationPreviewResult[] }
function reasonCode(value: unknown) { const code = text(value); if (!Object.hasOwn(generationReasons, code)) fail(); return code; }
export function decodeCapabilities(raw: unknown): GenerationCapability[] {
  const values = list(raw);
  if (values.length > 25) fail();
  const result = values.map(raw => { const v = obj(raw), domain = text(v.domain); if (!/^[a-z_]{1,100}$/.test(domain)) fail(); return { domain, financial: boolean(v.financial), reports: boolean(v.reports), reason: reasonCode(v.reason) }; });
  if (new Set(result.map(v => v.domain)).size !== result.length) fail();
  return result;
}
export function decodePreview(raw: unknown): GenerationPreview {
  const v = obj(raw), values = list(v.results);
  if (values.length < 1 || values.length > 25) fail();
  const results = values.map(raw => {
    const r = obj(raw), status = text(r.status), id = number(r.record_id), source = r.source_document_id === null ? null : number(r.source_document_id);
    if (!['baseline','unchanged','eligible_change','refused','unsupported_source'].includes(status) || id < 1 || id > 2147483647 || source !== null && (source < 1 || source > 2147483647)) fail();
    return { record_id: id, status, reason: reasonCode(r.reason), source_document_id: source };
  });
  if (new Set(results.map(r => r.record_id)).size !== results.length) fail();
  return { drafts_enabled: boolean(v.drafts_enabled), results };
}
