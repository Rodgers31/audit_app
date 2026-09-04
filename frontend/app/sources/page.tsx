/**
 * Unified Data Sources page
 *
 * Every number on AuditGava traces back to a document published by a
 * Kenyan government agency. This page answers the first question every
 * critical reader asks: *where did you get this?*
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import api from '@/lib/api/axios';
import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { Activity, Clock, Database, ExternalLink, FileText, Globe, Loader2 } from 'lucide-react';

interface SourceSummary {
  publisher: string;
  short: string;
  role: string;
  website?: string | null;
  document_count: number;
  last_fetched: string | null;
  last_seen_at: string | null;
  doc_types: Record<string, number>;
}

interface SourcesResponse {
  sources: SourceSummary[];
  total_documents: number;
}

interface TableHealth {
  table: string;
  label: string;
  row_count: number;
  source: string;
  status: string; // healthy | degraded | critical | empty
  notes?: string | null;
}

interface HealthResponse {
  tables: TableHealth[];
}

const HEALTH_STYLE: Record<string, { dot: string; text: string; label: string }> = {
  healthy: { dot: 'bg-emerald-500', text: 'text-emerald-700', label: 'Healthy' },
  degraded: { dot: 'bg-amber-500', text: 'text-amber-700', label: 'Partial' },
  critical: { dot: 'bg-rose-500', text: 'text-rose-700', label: 'Critical' },
  empty: { dot: 'bg-gray-400 dark:bg-neutral-muted/60', text: 'text-gray-500 dark:text-neutral-muted/80', label: 'Empty' },
};

function fmtRelativeDate(iso: string | null): string {
  if (!iso) return 'Never';
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return 'Never';
  const diff = Date.now() - then;
  const days = Math.floor(diff / (24 * 60 * 60 * 1000));
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 30) return `${days} days ago`;
  if (days < 365) return `${Math.floor(days / 30)} months ago`;
  return `${Math.floor(days / 365)} years ago`;
}

function freshnessColor(iso: string | null): string {
  if (!iso) return 'text-gray-400 dark:text-neutral-muted/80';
  const diff = Date.now() - new Date(iso).getTime();
  const days = diff / (24 * 60 * 60 * 1000);
  if (days < 14) return 'text-emerald-600';
  if (days < 60) return 'text-amber-600';
  return 'text-rose-600';
}

function DocTypeBadge({ type, count }: { type: string; count: number }) {
  const palette: Record<string, string> = {
    budget: 'bg-blue-50 text-blue-700 border-blue-200',
    audit: 'bg-rose-50 text-rose-700 border-rose-200',
    report: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    other: 'bg-gray-50 dark:bg-surface-elevated text-gray-700 dark:text-neutral-muted border-gray-200 dark:border-neutral-border',
  };
  const cls = palette[type] || palette.other;
  return (
    <span className={`text-[11px] font-semibold uppercase px-2 py-0.5 rounded-full border ${cls}`}>
      {type} · {count.toLocaleString()}
    </span>
  );
}

export default function SourcesPage() {
  const { data, isLoading, error } = useQuery<SourcesResponse>({
    queryKey: ['sources', 'summary'],
    queryFn: async () => (await api.get<SourcesResponse>('/sources/summary')).data,
    staleTime: 10 * 60 * 1000,
  });

  const sources = data?.sources || [];
  const total = data?.total_documents || 0;

  /**
   * Distinct publishing BODIES, not distinct manifest rows.
   *
   * The manifest carries the same agency under several names — "Office of the
   * Auditor General" and "Office of the Auditor-General"; "National Treasury
   * Kenya", "National Treasury of Kenya" and "National Treasury"; "Controller
   * of Budget", "National Treasury & Controller of Budget" and "Office of the
   * Controller of Budget (OCOB)". Counting rows reported 17 agencies where
   * there are about nine (credibility audit F38).
   *
   * Normalising instead of hardcoding a number, so the count stays right as
   * the manifest changes.
   */
  const distinctAgencyCount = useMemo(() => {
    if (sources.length === 0) return null;
    const norm = (name: string) =>
      name
        .toLowerCase()
        // Any dash, ASCII or typographic, becomes a space so "Auditor-General"
        // and "Auditor General" collapse to the same body.
        .replace(/[-\u2010-\u2015]/g, ' ')
        .replace(/\(.*?\)/g, '') // drop parenthetical acronyms: "(OCOB)"
        // A row naming two bodies ("Central Bank of Kenya / National Treasury")
        // is filed under the first rather than counted as a third agency.
        .split(/[&/]/)[0]
        .replace(/\bknbs\b/g, 'national bureau statistics')
        .replace(/\b(the|of|kenya|kenyan|office|republic)\b/g, '')
        .replace(/[^a-z ]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
    return new Set(sources.map((src) => norm(src.publisher)).filter(Boolean)).size;
  }, [sources]);

  // Data-health grid — surfaces the /provenance/health endpoint (previously
  // unused by any page; audit §2.9). Shows live completeness of each dataset.
  const { data: health } = useQuery<HealthResponse>({
    queryKey: ['provenance', 'health'],
    queryFn: async () => (await api.get<HealthResponse>('/provenance/health')).data,
    staleTime: 10 * 60 * 1000,
  });
  const healthTables = health?.tables || [];

  return (
    <PageShell
      title='Where the data comes from'
      subtitle='AuditGava aggregates what Kenyan government agencies already publish. Most figures here trace to a named document; where one does not, the page carrying it says so and names the method instead. No private sources, no opinion.'>
      <div className='space-y-6'>
        {/* Hero stat strip */}
        <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border px-5 py-4 flex flex-wrap items-center gap-6'>
          <div className='flex items-center gap-3'>
            <div className='w-10 h-10 rounded-lg bg-gov-forest/10 flex items-center justify-center'>
              <Database className='text-gov-forest dark:text-emerald-100' size={20} />
            </div>
            <div>
              <div className='text-xs uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold'>
                Documents indexed
              </div>
              <div className='text-2xl font-bold text-gray-900 dark:text-neutral-text tabular-nums'>
                {total.toLocaleString()}
              </div>
            </div>
          </div>
          <div className='flex items-center gap-3'>
            <div className='w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center'>
              <Globe className='text-amber-700' size={20} />
            </div>
            <div>
              <div className='text-xs uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold'>
                Publishing agencies
              </div>
              <div className='text-2xl font-bold text-gray-900 dark:text-neutral-text tabular-nums'>
                {distinctAgencyCount ?? sources.length}
              </div>
            </div>
          </div>
          <div className='flex-1 min-w-[220px] text-sm text-gray-600 dark:text-neutral-muted leading-relaxed sm:pl-6 sm:border-l border-gray-100 dark:border-neutral-border'>
            The freshness age below shows how recently we last reached each
            agency. Several are months behind; the site does not currently update
            every source nightly, whatever a headline elsewhere may suggest.
          </div>
        </div>

        {/* Data health grid — surfaces /provenance/health */}
        {healthTables.length > 0 && (
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
            <div className='flex items-center gap-2 mb-1'>
              <Activity size={16} className='text-gov-forest dark:text-emerald-100' />
              <h2 className='text-base font-bold text-gray-900 dark:text-neutral-text'>Data health</h2>
            </div>
            <p className='text-xs text-gray-500 dark:text-neutral-muted/80 mb-4 max-w-2xl'>
              How much data each table holds. Green means the table has passed a
              minimum row count — it is a check for <em>empty</em>, not a check
              for <em>current</em> or <em>correct</em>, so a table frozen for a
              year still reads green. Use the &ldquo;last fetched&rdquo; ages below to
              judge freshness.
            </p>
            <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3'>
              {healthTables.map((tb) => {
                const s = HEALTH_STYLE[tb.status] || HEALTH_STYLE.empty;
                return (
                  <div
                    key={tb.table}
                    className='rounded-lg border border-gray-100 dark:border-neutral-border p-3'>
                    <div className='flex items-center justify-between gap-2'>
                      <span className='text-sm font-semibold text-gray-800 dark:text-neutral-text truncate'>
                        {tb.label}
                      </span>
                      <span
                        className={`inline-flex items-center gap-1 text-[11px] font-semibold flex-shrink-0 ${s.text}`}>
                        <span className={`w-2 h-2 rounded-full ${s.dot}`} />
                        {s.label}
                      </span>
                    </div>
                    <div className='mt-1 text-lg font-bold text-gray-900 dark:text-neutral-text tabular-nums'>
                      {tb.row_count.toLocaleString()}{' '}
                      <span className='text-xs font-normal text-gray-400 dark:text-neutral-muted/80'>
                        rows
                      </span>
                    </div>
                    <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 truncate'>
                      {tb.source}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Loading / Error */}
        {isLoading && (
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-8 flex items-center justify-center gap-3 text-gray-500 dark:text-neutral-muted/80'>
            <Loader2 className='animate-spin' size={18} />
            <span>Loading source manifest…</span>
          </div>
        )}
        {error && (
          <div className='bg-rose-50 border border-rose-200 rounded-xl p-4 text-rose-800 text-sm'>
            Failed to load source manifest. Please refresh.
          </div>
        )}

        {/* Empty state — manifest indexed nothing (audit §2.9: no silent "0 documents" void) */}
        {!isLoading && !error && sources.length === 0 && (
          <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-10 text-center'>
            <p className='text-sm font-semibold text-gray-700 dark:text-neutral-muted'>
              No source documents indexed yet
            </p>
            <p className='mt-1 text-xs text-gray-500 dark:text-neutral-muted/80'>
              The source manifest is empty for this environment — the ingestion pipeline has
              not recorded any documents.
            </p>
          </div>
        )}

        {/* Source list */}
        {!isLoading && !error && sources.length > 0 && (
          <div className='grid grid-cols-1 lg:grid-cols-2 gap-4'>
            {sources.map((s) => (
              <article
                key={s.publisher}
                className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5 hover:border-gov-sage/40 hover:shadow-md transition-all'>
                <div className='flex items-start justify-between gap-3 mb-3'>
                  <div className='min-w-0'>
                    <div className='flex items-center gap-2 mb-1'>
                      {s.short && (
                        <span className='text-[11px] font-bold uppercase tracking-wider bg-gov-forest/10 text-gov-forest dark:text-emerald-100 px-2 py-0.5 rounded'>
                          {s.short}
                        </span>
                      )}
                      <h2 className='text-base font-bold text-gray-900 dark:text-neutral-text truncate'>
                        {s.publisher}
                      </h2>
                    </div>
                    {s.role && (
                      <p className='text-sm text-gray-600 dark:text-neutral-muted leading-relaxed'>{s.role}</p>
                    )}
                  </div>
                  {s.website && (
                    <a
                      href={s.website}
                      target='_blank'
                      rel='noopener noreferrer'
                      className='text-xs text-gov-forest dark:text-emerald-100 hover:underline inline-flex items-center gap-1 shrink-0 whitespace-nowrap'>
                      Visit site
                      <ExternalLink size={11} />
                    </a>
                  )}
                </div>

                <div className='flex flex-wrap items-center gap-4 pt-3 border-t border-gray-100 dark:border-neutral-border'>
                  <div>
                    <div className='text-[11px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold'>
                      Documents
                    </div>
                    <div className='text-lg font-bold text-gray-900 dark:text-neutral-text tabular-nums'>
                      {s.document_count.toLocaleString()}
                    </div>
                  </div>
                  <div>
                    <div className='text-[11px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold'>
                      Last fetched
                    </div>
                    <div
                      className={`text-sm font-semibold inline-flex items-center gap-1.5 ${freshnessColor(s.last_fetched)}`}>
                      <Clock size={12} />
                      {fmtRelativeDate(s.last_fetched)}
                    </div>
                  </div>
                  {Object.keys(s.doc_types).length > 0 && (
                    <div className='flex flex-wrap gap-1.5 ml-auto'>
                      {Object.entries(s.doc_types)
                        .sort((a, b) => b[1] - a[1])
                        .map(([type, count]) => (
                          <DocTypeBadge key={type} type={type} count={count} />
                        ))}
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}

        {/* Methodology footer */}
        <div className='bg-gov-forest/5 border border-gov-forest/20 rounded-xl p-5'>
          <div className='flex items-start gap-3'>
            <FileText className='text-gov-forest dark:text-emerald-100 mt-0.5 shrink-0' size={18} />
            <div className='text-sm text-gray-700 dark:text-neutral-muted leading-relaxed'>
              <p className='font-semibold text-gray-900 dark:text-neutral-text mb-1'>How this works</p>
              {/* The old copy promised that "every extracted value retains a
                  provenance pointer … so you can trace any county's budget
                  execution number back to the original COB quarterly report".
                  GET /provenance/verify/budget_lines answers "Unknown table"
                  — the one trace the sentence promised is the one the verifier
                  cannot do (credibility audit F16). Describe the actual state. */}
              <p>
                Our ETL pipeline fetches PDFs and spreadsheets from each agency&apos;s
                official portal, extracts line-items using table-extraction tools
                and rule-based parsers, and writes them to a canonical schema.
              </p>
              <p className='mt-2'>
                Coverage of the evidence trail is uneven, and we would rather say
                so than imply otherwise. Audit findings and national debt
                instruments carry a <strong>provenance pointer</strong> — a source
                document and, for audit findings, a page reference — and can be
                checked through the verification endpoint. County budget lines and
                the historical debt timeline cannot yet: they are not wired into
                that endpoint. County figures come from two different places, and
                each page says which: the headline budget, spend and execution
                rate are read from the Controller of Budget&apos;s implementation
                review where that parse landed, while the per-sector split and any
                future-year period are modelled from the CRA equitable-share
                formula. Pages carrying modelled figures say so on the page.
              </p>
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  );
}
