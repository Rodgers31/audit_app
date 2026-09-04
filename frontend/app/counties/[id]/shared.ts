/**
 * Shared formatters, tab metadata, and styling lookups for the
 * county-detail page. Extracted so each tab file can import these
 * without pulling in the entire CountyDetailClient bundle.
 */
import type { TranslationKey } from '@/lib/i18n/messages';

/* ═══════════ Formatters ═══════════ */
export function fmtKES(n: number): string {
  if (n >= 1e9) return `KES ${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `KES ${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `KES ${(n / 1e3).toFixed(0)}K`;
  return `KES ${n.toLocaleString()}`;
}

export function fmtPop(n: number): string {
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return String(n);
}

/** Convert snake_case to Title Case (e.g. "financial_services" → "Financial Services") */
export function fmtLabel(s: string): string {
  return s
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

export function pct(n: number): string {
  return `${n.toFixed(1)}%`;
}

/* ═══════════ Shared constants ═══════════ */
export const PALETTE = [
  '#3b82f6',
  '#ef4444',
  '#22c55e',
  '#f59e0b',
  '#8b5cf6',
  '#06b6d4',
  '#ec4899',
  '#14b8a6',
  '#f97316',
  '#6366f1',
  '#a855f7',
  '#84cc16',
  '#0ea5e9',
  '#e11d48',
  '#94a3b8',
];

export type Tab = 'overview' | 'budget' | 'audit' | 'accountability' | 'money';

export const SEVERITY_STYLE: Record<
  string,
  { labelKey: TranslationKey; lowerKey: TranslationKey; dot: string; bg: string; text: string }
> = {
  critical: {
    labelKey: 'county.audit.critical',
    lowerKey: 'county.overview.sev_critical_lower',
    dot: 'bg-red-500',
    bg: 'bg-red-50',
    text: 'text-red-800',
  },
  warning: {
    labelKey: 'county.audit.warning',
    lowerKey: 'county.overview.sev_warning_lower',
    dot: 'bg-amber-500',
    bg: 'bg-amber-50',
    text: 'text-amber-800',
  },
  info: {
    labelKey: 'county.audit.info',
    lowerKey: 'county.overview.sev_info_lower',
    dot: 'bg-blue-500',
    bg: 'bg-blue-50',
    text: 'text-blue-800',
  },
};

/* ═══════════ Grade badge palettes ═══════════ */
export const HEALTH_GRADE_BG: Record<string, string> = {
  A: 'from-emerald-500 to-emerald-600',
  'B+': 'from-green-500 to-green-600',
  B: 'from-amber-500 to-amber-600',
  'B-': 'from-orange-500 to-orange-600',
  C: 'from-red-500 to-red-600',
};

export const ACCT_GRADE_BG: Record<string, string> = {
  A: 'from-emerald-500 to-emerald-600',
  B: 'from-teal-500 to-teal-600',
  C: 'from-yellow-500 to-amber-500',
  D: 'from-orange-500 to-orange-600',
  F: 'from-rose-500 to-red-600',
};


/**
 * Has ANY Auditor-General finding been ingested for this county?
 *
 * `findings_count: 0` does not mean the county was found clean — it means no
 * OAG report for it has been read into this site yet. The Accountability tab
 * already says exactly that ("An absent grade is not a low grade… This is not
 * a finding that the county is clean"), while the hero KPI, the health modal
 * and the Audit Findings tab rendered the same null as a bold "0" beside a
 * green bar (credibility audit F23). Same data, opposite messages, one click
 * apart.
 *
 * `status: "pending"` with no findings is the shape the API returns when
 * nothing has been ingested; a real audit that found nothing would carry a
 * status and an opinion.
 */
export function hasIngestedAudit(audit: {
  findings_count?: number | null;
  status?: string | null;
  findings?: unknown[] | null;
}): boolean {
  if (audit?.findings_count && audit.findings_count > 0) return true;
  if (audit?.findings && audit.findings.length > 0) return true;
  // An explicit non-pending status means the report was read and reported
  // nothing — a real zero we can stand behind.
  const status = (audit?.status || '').toLowerCase();
  return status !== '' && status !== 'pending' && status !== 'unknown';
}
