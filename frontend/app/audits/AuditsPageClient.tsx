'use client';

import DataFreshnessBadge from '@/components/DataFreshnessBadge';
import InfoSheet from '@/components/ui/InfoSheet';
import AuditRecurringFindings from './AuditRecurringFindings';
import AuditYearBars from './AuditYearBars';
import PageShell from '@/components/layout/PageShell';
import type { FindingDetailItem, FindingsFilters } from '@/lib/api/audits';
import { useLang } from '@/lib/i18n/LangProvider';
import type { Lang } from '@/lib/i18n/messages';
import { AUDITS_MESSAGES, auditSectionLabel } from '@/lib/i18n/messages/audits';
import {
  AUDIT_FINDINGS_INITIAL_FILTERS,
  useAuditDashboardSummary,
  useAuditFindings,
  useAuditTrends,
} from '@/lib/react-query';
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  FileWarning,
  Loader2,
  Search,
  Shield,
  X,
} from 'lucide-react';
import Link from 'next/link';
import { useCallback, useId, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Text,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import ResponsiveTable from '@/components/ui/ResponsiveTable';

/* ═══════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════ */

function fmtKES(val: number): string {
  if (!val || val === 0) return 'KES 0';
  const abs = Math.abs(val);
  if (abs >= 1e12) return `KES ${(val / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `KES ${(val / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `KES ${(val / 1e6).toFixed(1)}M`;
  return `KES ${val.toLocaleString()}`;
}

const TYPE_COLORS: Record<string, string> = {
  'Financial Irregularity': '#ef4444',
  'Compliance Issue': '#f59e0b',
  'Asset Management': '#8b5cf6',
  'Revenue Collection': '#3b82f6',
  'Procurement': '#ec4899',
  'Internal Controls': '#14b8a6',
  'Pending Bills': '#f97316',
  'Human Resource': '#6366f1',
  // The three OAG report sections the backend now folds headings onto.
  // Without these every bar fell through to the same grey.
  'Report on the Financial Statements': '#3b82f6',
  'Report on Lawfulness and Effectiveness in the Use of Public Resources': '#f59e0b',
  'Report on Effectiveness of Internal Controls, Risk Management and Governance':
    '#14b8a6',
};

const OPINION_COLORS: Record<string, string> = {
  Adverse: '#ef4444',
  Disclaimer: '#f59e0b',
  Qualified: '#f97316',
  Unqualified: '#22c55e',
};

function getTypeColor(type: string): string {
  return TYPE_COLORS[type] || '#94a3b8';
}

/* ═══════════════════════════════════════════════════════
   Page Component
   ═══════════════════════════════════════════════════════ */

export default function AuditFindingsPage() {
  const { lang } = useLang();
  const copy = (key: keyof typeof AUDITS_MESSAGES) => AUDITS_MESSAGES[key][lang];

  // --- Filters state ---
  // Seeded from the shared constant `app/audits/page.tsx` prefetches against,
  // so the first render reads the page the server already put in the HTML.
  const [filters, setFilters] = useState<FindingsFilters>(AUDIT_FINDINGS_INITIAL_FILTERS);

  // --- Data hooks ---
  const { data: summary, isLoading: summaryLoading } = useAuditDashboardSummary();
  const { data: trends, isLoading: trendsLoading, isError: trendsError, refetch: retryTrends } = useAuditTrends();
  const { data: findings, isLoading: findingsLoading } = useAuditFindings(filters);

  // --- Derived data ---
  const typeChartData = useMemo(() => {
    if (!summary?.findings_by_type) return [];
    return Object.entries(summary.findings_by_type)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [summary]);

  // `0` here would mean "the Auditor-General issued no adverse or disclaimer
  // opinion", which is a strong claim. Absent key -> null (renders "—");
  // present key with value 0 -> a real zero we can stand behind. Credibility
  // audit F21.
  //
  // `findings_by_opinion` is now `null` outright whenever the facet contains
  // no modified opinion at all, because the extraction records a modified
  // opinion in the finding's HEADING ("Basis for Qualified Opinion") and never
  // carries it into the opinion field — so every opinion it can show is a
  // clean one. The keys are the canonical ISA 700 names the API returns.
  const adverseCount = useMemo<number | null>(() => {
    const byOpinion = summary?.findings_by_opinion;
    if (!byOpinion) return null;
    const hasAdverse = 'Adverse Opinion' in byOpinion;
    const hasDisclaimer = 'Disclaimer of Opinion' in byOpinion;
    if (!hasAdverse && !hasDisclaimer) return null;
    return (byOpinion['Adverse Opinion'] || 0) + (byOpinion['Disclaimer of Opinion'] || 0);
  }, [summary]);

  // --- Filter options ---
  const yearOptions = useMemo(() => {
    if (!summary?.year_range?.min_year || !summary?.year_range?.max_year) return [];
    const years = [];
    for (let y = summary.year_range.max_year; y >= summary.year_range.min_year; y--) {
      years.push(y);
    }
    return years;
  }, [summary]);

  const typeOptions = useMemo(() => {
    if (!summary?.findings_by_type) return [];
    return Object.keys(summary.findings_by_type).sort();
  }, [summary]);

  const opinionOptions = useMemo(() => {
    if (!summary?.findings_by_opinion) return [];
    return Object.keys(summary.findings_by_opinion).sort();
  }, [summary]);

  // --- Filter handlers ---
  const updateFilter = useCallback((key: keyof FindingsFilters, value: any) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value || undefined,
      page: key === 'page' ? value : 1,
    }));
  }, []);

  const clearFilters = useCallback(() => {
    setFilters(AUDIT_FINDINGS_INITIAL_FILTERS);
  }, []);

  const hasActiveFilters = !!(filters.county_id || filters.year || filters.query_type || filters.severity || filters.audit_opinion || filters.status);

  const totalPages = findings ? Math.ceil(findings.total / (filters.limit || 20)) : 0;

  // --- Loading state ---
  if (summaryLoading) {
    return (
      <PageShell title={copy('audits.title')} subtitle={copy('audits.intro')}>
        <div className='flex items-center justify-center py-32'>
          <Loader2 className='w-8 h-8 animate-spin text-gov-sage' />
          <span className='ml-3 text-gov-dark/60 dark:text-white/60 font-medium'>Loading audit data...</span>
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell
      title={copy('audits.title')}
      subtitle={copy('audits.intro')}>
      <section aria-labelledby='audit-collection-heading' className='space-y-2' data-audit-headline>
        <h2 id='audit-collection-heading' className='text-sm font-semibold text-neutral-text'>{copy('audits.headline')}</h2>
        <p className='audit-figure text-audit-title text-neutral-text'>
          {summary && Number.isSafeInteger(summary.total_findings) && summary.total_findings >= 0
            ? summary.total_findings.toLocaleString(lang === 'sw' ? 'sw-KE' : 'en-KE')
            : copy('audits.count_unavailable')}
        </p>
        <div className='border-l-4 border-signal-caution-fill px-3 py-2 text-sm leading-relaxed text-signal-caution'
          style={{ backgroundColor: 'color-mix(in srgb, var(--signal-caution-fill) 10%, transparent)' }}>
          <strong className='block'>{copy('audits.loss_title')}</strong>
          <p>{copy('audits.loss_note')}</p>
        </div>
        {summary?.year_range?.min_year != null && summary?.year_range?.max_year != null && (
          <p className='text-sm text-neutral-muted'>
            {summary.year_range.min_year === summary.year_range.max_year
              ? copy('audits.recorded_year').replace('{year}', String(summary.year_range.min_year))
              : copy('audits.recorded_years').replace('{start}', String(summary.year_range.min_year)).replace('{end}', String(summary.year_range.max_year))}
          </p>
        )}
        <InfoSheet title={copy('audits.source_title')} trigger={props => (
          <button {...props} type='button' className='audit-receipt' onClick={event => {
            event.currentTarget.focus();
            props.onClick();
          }}>
            <span aria-hidden='true' className='h-2 w-2 shrink-0 bg-signal-caution' />
            {copy('audits.source')}
          </button>
        )}>
          <p>{copy('audits.source_scope')}</p>
          <p>{copy('audits.source_limits')}</p>
          <p>{summary?.withheld_findings != null && Number.isSafeInteger(summary.withheld_findings) && summary.withheld_findings >= 0
            ? copy('audits.withheld').replace('{count}', summary.withheld_findings.toLocaleString(lang === 'sw' ? 'sw-KE' : 'en-KE'))
            : copy('audits.withheld_unknown')}</p>
          <Link href='/sources' className='flex min-h-11 items-center underline underline-offset-4'>{copy('audits.view_sources')}</Link>
        </InfoSheet>
        <a href='#audit-findings-heading' className='flex min-h-11 items-center text-sm underline underline-offset-4'>{copy('audits.view_findings')}</a>
      </section>

      <div>
        <div className='max-w-xl'>
          <StatCard
            label='Adverse / Disclaimer Opinions'
            value={adverseCount != null ? adverseCount.toLocaleString() : '—'}
            icon={<Shield className='w-5 h-5' />}
            color='red'
            subtitle={
              adverseCount != null
                ? 'Entities whose accounts drew a modified opinion'
                : summary?.findings_by_opinion_reason
                  ? 'Opinion mix withheld — modified opinions are not extracted'
                  : 'Opinion type not captured for this report'
            }
          />
        </div>
      </div>

      {/* Why there is no money total here.
          The two expenditure tiles that used to sit above summed
          `amount_involved`, which the loader fills from any finding paragraph
          containing exactly one `Kshs.` figure
          (backend/seeding/domains/audits/loader.py:165). That rule has no test
          of what the figure MEANS, so the total was dominated by account
          balances quoted as context — trade-payables balances, a procurement
          value against which a 0.03% levy went unremitted, one payroll balance
          counted twice — and the largest single contributor carried the
          Auditor-General's own words "My opinion is not modified in respect of
          this matter". Publishing that sum as "Unsupported Expenditure" was
          credibility-audit finding F1. Withheld until the extraction can
          separate an amount QUESTIONED from an amount DISCUSSED. */}
      <div>
        <div className='rounded-xl border border-neutral-border/60 bg-surface-sunken/40 px-4 py-3.5'>
          <div className='flex items-start gap-2.5'>
            <FileWarning className='w-4 h-4 mt-0.5 flex-shrink-0 text-gov-forest/70 dark:text-emerald-100/70' />
            <p className='text-sm leading-relaxed text-neutral-muted'>
              <span className='font-semibold text-gov-dark dark:text-white'>
                No total money figure is shown.
              </span>{' '}
              The Auditor-General&rsquo;s report does not state a headline
              questioned amount in the machine-readable part of the document, and
              the amounts written inside individual findings are usually the
              account balance under discussion rather than a sum being queried.
              Adding them up would produce a number the report does not support,
              so none is published here.
              <span className='block mt-1.5 text-neutral-muted/80'>
                An absent total is not a finding that no public money is at
                issue. Individual findings below carry their own amounts and
                page references where the report states them.
              </span>
            </p>
          </div>
        </div>
      </div>

      {/* The "Top 10 Worst Offenders" ranking was withdrawn (credibility audit
          F1/F34). It ordered named State Departments and the Executive Office of
          the President by a "Flagged Amount" built from the same
          amount_involved extraction described above, under a heading that
          called them offenders — while the disclaimer immediately below it says
          these are queries, not proven loss. A ranking by finding COUNT is
          defensible and is what the homepage "Top Ministries Flagged" card
          shows; a ranking by an amount the report never stated is not. */}

      {/* ═══ C. FINDINGS BY TYPE + D. FINDINGS BY AUDIT YEAR ═══ */}
      <div>
        <div className='space-y-6'>
          {/* C. Findings by Type */}
          <div className='space-y-3'>
            <h2 className='font-display text-xl text-gov-dark dark:text-white'>Findings by Type</h2>
            {typeChartData.length > 0 ? (
              <div className='h-[320px] overflow-hidden'>
                <ResponsiveContainer width='100%' height='100%'>
                  <BarChart data={typeChartData} layout='vertical' margin={{ left: 0, right: 16 }}>
                    <CartesianGrid strokeDasharray='3 3' stroke='#e5e7eb' horizontal={false} />
                    <XAxis type='number' tick={{ fontSize: 12, fill: 'rgb(var(--c-neutral-muted))' }} />
                    <YAxis
                      type='category'
                      dataKey='name'
                      width={130}
                      tick={({ x, y, payload }: { x: number; y: number; payload: { value: string } }) => (
                        <Text
                          x={x}
                          y={y}
                          width={108}
                          maxLines={2}
                          textAnchor='end'
                          verticalAnchor='middle'
                          fill='rgb(var(--c-neutral-muted))'
                          style={{ fontSize: 12 }}>
                          {auditSectionLabel(payload.value, lang)}
                        </Text>
                      )}
                    />
                    <Tooltip
                      wrapperStyle={{ maxWidth: '70%' }}
                      contentStyle={{
                        backgroundColor: 'rgb(var(--c-surface-base))',
                        border: '1px solid rgb(var(--c-neutral-border))',
                        borderRadius: 4,
                        color: 'rgb(var(--c-neutral-text))',
                        fontSize: 12,
                        whiteSpace: 'normal',
                        overflowWrap: 'anywhere',
                      }}
                      itemStyle={{ color: 'rgb(var(--c-neutral-text))' }}
                      formatter={(val: number) => [val.toLocaleString(), 'Findings']}
                    />
                    <Bar dataKey='value' radius={[0, 4, 4, 0]}>
                      {typeChartData.map((entry) => (
                        <Cell key={entry.name} fill={getTypeColor(entry.name)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className='h-[320px] flex items-center justify-center text-gov-dark/40 dark:text-white/40'>
                No data available
              </div>
            )}
          </div>

          <section aria-labelledby='audit-years-heading' className='min-w-0 space-y-3'>
            <h2 id='audit-years-heading' className='font-display text-xl text-neutral-text'>{copy('audits.years_title')}</h2>
            {trendsLoading ? (
              <p role='status' className='py-8 text-sm text-neutral-muted'>{copy('audits.years_loading')}</p>
            ) : trendsError ? (
              <div className='space-y-2 text-sm'>
                <p role='alert'>{copy('audits.years_error')}</p>
                <button type='button' onClick={() => void retryTrends()} className='audit-control underline'>{copy('audits.retry')}</button>
              </div>
            ) : trends ? <AuditYearBars trends={trends} /> : (
              <p className='text-sm text-neutral-muted'>{copy('audits.years_empty')}</p>
            )}
          </section>
        </div>
      </div>

      <AuditRecurringFindings />

      {/* ═══ F. FILTER BAR ═══ */}
      <div>
        <div className='space-y-3'>
          <div className='flex items-center justify-between gap-2'>
            <h2 id='audit-findings-heading' className='scroll-mt-24 font-display text-xl text-gov-dark dark:text-white'>{copy('audits.all_findings')}</h2>
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className='flex min-h-11 items-center gap-1 text-sm text-gov-sage hover:text-gov-forest dark:text-emerald-100 transition-colors'>
                <X className='w-3 h-3' aria-hidden='true' />
                {copy('audits.clear_filters')}
              </button>
            )}
          </div>

          <div className='grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5'>
            {/* Year filter */}
            <FilterSelect
              label={copy('audits.year')}
              placeholder={copy('audits.all_years')}
              value={filters.year?.toString() || ''}
              onChange={(v) => updateFilter('year', v ? parseInt(v) : undefined)}
              options={yearOptions.map((y) => ({ value: String(y), label: String(y) }))}
            />

            {/* Type filter */}
            <FilterSelect
              label={copy('audits.section')}
              placeholder={copy('audits.all_sections')}
              value={filters.query_type || ''}
              onChange={(v) => updateFilter('query_type', v || undefined)}
              options={typeOptions.map((type) => ({ value: type, label: auditSectionLabel(type, lang) }))}
            />

            {/* Opinion filter — hidden when the facet is withheld, rather than
                rendered as a dropdown whose only option is "All". */}
            {opinionOptions.length > 0 && (
              <FilterSelect
                label={copy('audits.opinion')}
                placeholder={copy('audits.all')}
                value={filters.audit_opinion || ''}
                onChange={(v) => updateFilter('audit_opinion', v || undefined)}
                options={opinionOptions.map((o) => ({ value: o, label: o }))}
              />
            )}

            {/* Severity filter */}
            <FilterSelect
              label={copy('audits.severity')}
              placeholder={copy('audits.all')}
              value={filters.severity || ''}
              onChange={(v) => updateFilter('severity', v || undefined)}
              options={[
                { value: 'Critical', label: 'Critical' },
                { value: 'High', label: 'High' },
                { value: 'Medium', label: 'Medium' },
                { value: 'Low', label: 'Low' },
              ]}
            />

            {/* Status filter */}
            <FilterSelect
              label={copy('audits.status')}
              placeholder={copy('audits.all')}
              value={filters.status || ''}
              onChange={(v) => updateFilter('status', v || undefined)}
              options={[
                { value: 'Unresolved', label: 'Unresolved' },
                { value: 'Resolved', label: 'Resolved' },
                { value: 'Partially Resolved', label: 'Partially Resolved' },
              ]}
            />
          </div>
        </div>
      </div>

      {/* ═══ G. FINDINGS TABLE ═══ */}
      <div>
        {findingsLoading ? (
          <div className='flex items-center justify-center py-16'>
            <Loader2 className='w-6 h-6 animate-spin text-gov-sage' />
            <span className='ml-3 text-gov-dark/60 dark:text-white/60'>Loading findings...</span>
          </div>
        ) : findings && findings.items.length > 0 ? (
          <div className='space-y-4'>
            <div className='text-xs text-gov-dark/50 dark:text-white/50'>
              Showing {(findings.page - 1) * (filters.limit || 20) + 1}–
              {Math.min(findings.page * (filters.limit || 20), findings.total)} of{' '}
              {findings.total.toLocaleString()} findings
            </div>

            <ul role='list' aria-label={copy('audits.all_findings')} className='space-y-2 md:hidden'>
              {findings.items.map((finding) => (
                <MobileFindingCard key={finding.id} finding={finding} lang={lang} />
              ))}
            </ul>

            <ResponsiveTable className='hidden md:block'>
              <table className='w-full text-sm'>
                <thead>
                  <tr className='border-b border-gov-dark/10 text-left'>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70 dark:text-white/70'>Entity audited</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70 dark:text-white/70'>Year</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70 dark:text-white/70'>{copy('audits.section')}</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70 dark:text-white/70 text-right'>Amount</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70 dark:text-white/70'>Severity</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70 dark:text-white/70'>Status</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70 dark:text-white/70'>Opinion</th>
                    <th className='py-2 pr-3 font-semibold text-gov-dark/70 dark:text-white/70 text-center w-10'>Source</th>
                    <th className='py-2 font-semibold text-gov-dark/70 dark:text-white/70 text-center w-8' title='Data confidence'>DQ</th>
                  </tr>
                </thead>
                <tbody>
                  {findings.items.map((f) => (
                    <tr
                      key={f.id}
                      className='border-b border-gov-dark/5 hover:bg-gov-forest/[0.03] transition-colors'
                      title={f.finding_text}>
                      <td className='py-2.5 pr-3'>
                        <span className='block font-medium'>
                          {f.audited_entity_name ?? 'Audited institution not identified'}
                        </span>
                        {f.county_slug && f.county_name && (
                          <Link
                            href={`/counties/${encodeURIComponent(f.county_slug)}`}
                            className='text-gov-forest dark:text-emerald-100 hover:underline'>
                            {f.county_name}
                          </Link>
                        )}
                      </td>
                      <td className='py-2.5 pr-3 font-mono text-xs'>{f.audit_year || '—'}</td>
                      <td className='py-2.5 pr-3'>
                        {f.query_type ? (
                          <span className='text-xs text-neutral-muted'>{f.query_type}</span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className='py-2.5 pr-3 text-right font-mono text-red-600'>
                        {f.amount ? fmtKES(f.amount) : '—'}
                      </td>
                      <td className='py-2.5 pr-3'>
                        <SeverityBadge severity={f.severity} />
                      </td>
                      <td className='py-2.5 pr-3'>
                        <StatusBadge status={f.status} />
                      </td>
                      <td className='py-2.5 pr-3'>
                        {f.audit_opinion ? (
                          <span
                            className='text-xs font-medium'
                            style={{ color: OPINION_COLORS[f.audit_opinion] || '#6b7280' }}>
                            {f.audit_opinion}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className='py-2.5 pr-3 text-center'>
                        {f.source_document_url ? (
                          <a
                            href={f.source_document_url}
                            target='_blank'
                            rel='noopener noreferrer'
                            className='inline-flex items-center text-gov-sage hover:text-gov-forest dark:text-emerald-100 transition-colors'
                            title={f.page_ref ? `View OAG source report, ${f.page_ref}` : 'View OAG source report'}>
                            <FileText className='w-4 h-4' />
                          </a>
                        ) : (
                          <span className='text-gov-dark/20 dark:text-white/20'>—</span>
                        )}
                      </td>
                      <td className='py-2.5 text-center'>
                        <ConfidenceIndicator score={f.confidence_score} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ResponsiveTable>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className='flex items-center justify-between pt-2'>
                <button
                  onClick={() => updateFilter('page', Math.max(1, (filters.page || 1) - 1))}
                  disabled={(filters.page || 1) <= 1}
                  className='flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg bg-gov-dark/5 hover:bg-gov-dark/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors'>
                  <ChevronLeft className='w-4 h-4' />
                  Previous
                </button>
                <span className='text-xs text-gov-dark/60 dark:text-white/60'>
                  Page {filters.page || 1} of {totalPages}
                </span>
                <button
                  onClick={() => updateFilter('page', Math.min(totalPages, (filters.page || 1) + 1))}
                  disabled={(filters.page || 1) >= totalPages}
                  className='flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg bg-gov-dark/5 hover:bg-gov-dark/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors'>
                  Next
                  <ChevronRight className='w-4 h-4' />
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className='text-center py-16 text-gov-dark/40 dark:text-white/40'>
            {hasActiveFilters ? 'No findings match your filters.' : 'No findings data available.'}
          </div>
        )}
      </div>

      {/* Data freshness badge */}
      <DataFreshnessBadge sources="OAG" className="mt-6 justify-center" />
    </PageShell>
  );
}

/* ═══════════════════════════════════════════════════════
   Sub-components
   ═══════════════════════════════════════════════════════ */

function StatCard({
  label,
  value,
  icon,
  color,
  subtitle,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  color: 'red' | 'amber' | 'blue' | 'green';
  subtitle?: string;
}) {
  const colorMap = {
    red: 'bg-red-50 text-red-600 border-red-200/50',
    amber: 'bg-amber-50 text-amber-600 border-amber-200/50',
    blue: 'bg-blue-50 text-blue-600 border-blue-200/50',
    green: 'bg-emerald-50 text-emerald-600 border-emerald-200/50',
  };
  const iconBg = {
    red: 'bg-red-100 text-red-500',
    amber: 'bg-amber-100 text-amber-500',
    blue: 'bg-blue-100 text-blue-500',
    green: 'bg-emerald-100 text-emerald-500',
  };

  return (
    <div className={`rounded-xl p-4 border ${colorMap[color]} transition-shadow hover:shadow-md`}>
      <div className='flex items-start justify-between mb-2'>
        <span className='text-xs font-medium uppercase tracking-wider opacity-70'>{label}</span>
        <div className={`p-1.5 rounded-lg ${iconBg[color]}`}>{icon}</div>
      </div>
      <div className='font-display text-2xl font-bold tracking-tight'>{value}</div>
      {subtitle && <p className='text-xs mt-1 opacity-60'>{subtitle}</p>}
    </div>
  );
}

function FilterSelect({
  label,
  placeholder,
  value,
  onChange,
  options,
}: {
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  const id = useId();
  return (
    <div className='flex min-w-0 flex-col gap-1'>
      <label htmlFor={id} className='text-xs font-semibold text-neutral-muted'>
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className='min-h-11 w-full min-w-0 max-w-full rounded border border-neutral-border bg-surface-base px-3 text-sm text-neutral-text'>
        <option value=''>{placeholder}</option>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}

const MOBILE_SEVERITY: Record<string, { label: keyof typeof AUDITS_MESSAGES; tone: string }> = {
  critical: { label: 'audits.severity_critical', tone: 'text-signal-alarm' },
  warning: { label: 'audits.severity_warning', tone: 'text-signal-caution' },
  info: { label: 'audits.severity_info', tone: 'text-neutral-muted' },
};

function MobileFindingCard({ finding, lang }: { finding: FindingDetailItem; lang: Lang }) {
  const copy = (key: keyof typeof AUDITS_MESSAGES) => AUDITS_MESSAGES[key][lang];
  const severity = MOBILE_SEVERITY[finding.severity.toLowerCase()];

  return (
    <li className='min-w-0 space-y-2 rounded border border-neutral-border bg-surface-base p-3 [overflow-wrap:anywhere]'>
      <p className='flex flex-wrap items-baseline gap-x-2 text-audit-label text-neutral-muted'>
        <span className='min-w-0'>
          {finding.audited_entity_name ?? copy('audits.institution_not_identified')}
        </span>
        {finding.audit_year != null && (
          <span className='font-mono'><span aria-hidden='true'>· </span>{finding.audit_year}</span>
        )}
      </p>
      <h3 className='text-sm font-bold text-neutral-text'>
        {finding.finding_title ?? finding.finding_text}
      </h3>
      <p className='flex flex-wrap items-baseline gap-x-2 gap-y-1 text-audit-label text-neutral-muted'>
        <span className={`rounded bg-surface-sunken px-1.5 font-semibold ${severity?.tone ?? 'text-neutral-muted'}`}>
          {severity ? copy(severity.label) : finding.severity}
        </span>
        <span>
          {finding.amount == null
            ? copy('audits.amount_not_stated')
            : `${copy('audits.finding_amount')}: ${fmtKES(finding.amount)}`}
        </span>
        {finding.query_type && (
          <span>{copy('audits.section')}: {auditSectionLabel(finding.query_type, lang)}</span>
        )}
      </p>
      {finding.source_document_url && (
        <a
          href={finding.source_document_url}
          target='_blank'
          rel='noopener noreferrer'
          className='inline-flex min-h-11 min-w-11 max-w-full items-center gap-1 text-audit-label font-semibold text-signal-good underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2'>
          <span className='min-w-0'>
            {copy('audits.finding_source')}
            {finding.page_ref && <> <span className='font-mono'>{finding.page_ref}</span></>}
          </span>
          <ExternalLink className='h-3 w-3 shrink-0' aria-hidden='true' />
        </a>
      )}
    </li>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const styles: Record<string, string> = {
    Critical: 'bg-red-100 text-red-700',
    High: 'bg-orange-100 text-orange-700',
    Medium: 'bg-amber-100 text-amber-700',
    Low: 'bg-green-100 text-green-700',
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${styles[severity] || 'bg-gray-100 dark:bg-surface-elevated text-gray-600 dark:text-neutral-muted'}`}>
      {severity}
    </span>
  );
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className='text-gov-dark/30 dark:text-white/30'>—</span>;
  const styles: Record<string, string> = {
    Resolved: 'bg-emerald-100 text-emerald-700',
    Unresolved: 'bg-red-100 text-red-700',
    'Partially Resolved': 'bg-amber-100 text-amber-700',
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${styles[status] || 'bg-gray-100 dark:bg-surface-elevated text-gray-600 dark:text-neutral-muted'}`}>
      {status}
    </span>
  );
}

function ConfidenceIndicator({ score }: { score: number | null }) {
  if (score === null || score > 0.8) {
    // High confidence or unknown — no indicator needed
    return <span className='text-gov-dark/15 dark:text-white/15'>—</span>;
  }
  if (score >= 0.5) {
    return (
      <span
        className='cursor-help text-amber-500'
        title='Medium confidence — data extracted via heuristic parsing'>
        &#9888;&#65039;
      </span>
    );
  }
  return (
    <span
      className='cursor-help text-red-500'
      title='Low confidence — verify against source document'>
      &#128308;
    </span>
  );
}
