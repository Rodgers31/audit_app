import { MESSAGES, type TranslationKey } from '@/lib/i18n/messages';

/** Measure-specific response contract owned by services/figure_qualification.py. */
export interface FigureQualification {
  status: 'qualified' | 'verified' | 'unavailable' | 'conflicting' | 'modelled' | 'projected';
  reason: string;
  source_kind: 'api' | 'web' | 'pdf' | 'unknown';
  identity: {
    measure: string;
    entity_id: number | null;
    geography: string;
    period: string;
    unit: string;
    basis: string;
    dimensions: Record<string, string | null>;
  };
  source_document_id: number | null;
  source_url: string | null;
  publisher: string | null;
  receipt_id: number | null;
  digest: string | null;
  locator: Record<string, unknown> | null;
  document_bytes_checked: boolean;
  value_checked: boolean;
}

export type Qualifications = Record<string, FigureQualification>;
export type QualificationRows = Record<string, Qualifications>;
export const QUALIFICATION_TABLES = ['budget_lines', 'loans', 'gdp_data', 'economic_indicators', 'poverty_indices', 'debt_timeline', 'revenue_by_source'] as const;
export type QualificationTable = typeof QUALIFICATION_TABLES[number];

/** Keep URL-bearing evidence inert unless it is an ordinary public web link. */
export function evidenceUrl(value: string | null | undefined): string | undefined {
  if (typeof value !== 'string') return undefined;
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined;
  } catch { return undefined; }
}

export function qualificationMessageKey(q: FigureQualification | undefined): TranslationKey {
  const identity = q?.identity;
  if (!q || typeof q.reason !== 'string' || !q.reason.trim() || !identity ||
      ![identity.measure, identity.geography, identity.period, identity.unit, identity.basis].every(value => typeof value === 'string' && value.trim().length > 0)) return 'evidence.status.unavailable';
  switch (q.status) {
    case 'verified':
      return q.document_bytes_checked === true && q.value_checked === true ? 'evidence.status.verified' : 'evidence.status.incomplete';
    case 'qualified': return 'evidence.status.qualified';
    case 'conflicting': return 'evidence.status.conflicting';
    case 'modelled': return 'evidence.status.modelled';
    case 'projected': return 'evidence.status.projected';
    default: return 'evidence.status.unavailable';
  }
}

/** English compatibility label for non-localized consumers. */
export function qualificationLabel(q: FigureQualification | undefined): string {
  return MESSAGES[qualificationMessageKey(q)].en;
}

/** Model origin comes from explicit backend qualification, never numeric shape. */
export function isModelledObservation(qualifications?: Qualifications): boolean {
  return qualifications?.total?.status === 'modelled';
}
