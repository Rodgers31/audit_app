'use client';

import DataFreshnessBadge from '@/components/DataFreshnessBadge';
import InfoSheet from '@/components/ui/InfoSheet';
import AuditFindingsDesktop from './AuditFindingsDesktop';
import AuditRecurringFindings from './AuditRecurringFindings';
import AuditSeverity from './AuditSeverity';
import AuditYearBars from './AuditYearBars';
import { FINDING_SEVERITY, formatFindingAmount } from './auditFindingPresentation';
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
  FileWarning,
  Loader2,
  Shield,
  X,
} from 'lucide-react';
import Link from 'next/link';
import { useCallback, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';

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
  const { data: summary, isLoading: summaryLoading, refetch: retrySummary } = useAuditDashboardSummary();
  const { data: trends, isLoading: trendsLoading, isError: trendsError, refetch: retryTrends } = useAuditTrends();
  const { data: findings, isLoading: findingsLoading } = useAuditFindings(filters);
  const findingsHeading = useRef<HTMLHeadingElement>(null);
  const focusFindingsAfterPaging = useRef(false);
  useLayoutEffect(() => {
    if (!findingsLoading && focusFindingsAfterPaging.current) {
      focusFindingsAfterPaging.current = false;
      findingsHeading.current?.focus();
    }
  }, [findings, findingsLoading]);

  // --- Derived data ---
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

  function changePage(page: number) {
    focusFindingsAfterPaging.current = true;
    updateFilter('page', page);
  }

  const clearFilters = useCallback(() => {
    setFilters(AUDIT_FINDINGS_INITIAL_FILTERS);
    findingsHeading.current?.focus();
  }, []);

  const hasActiveFilters = !!(filters.county_id || filters.year || filters.query_type || filters.severity || filters.audit_opinion || filters.status);

  const totalPages = findings ? Math.ceil(findings.total / (filters.limit || 20)) : 0;
  const displayNumber = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE');

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

      <AuditSeverity collectionTotal={summary?.total_findings} retryCollection={() => void retrySummary()} />

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

      <AuditRecurringFindings />

      <section aria-labelledby='audit-findings-heading' className='min-w-0 space-y-6' data-audit-findings>
        <div className='space-y-3'>
          <div className='flex items-center justify-between gap-2'>
            <h2 id='audit-findings-heading' ref={findingsHeading} tabIndex={-1} className='scroll-mt-24 font-display text-xl text-gov-dark dark:text-white'>{copy('audits.all_findings')}</h2>
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className='audit-control'>
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
              options={Object.entries(FINDING_SEVERITY).map(([severity, { label }]) => ({
                value: severity.toUpperCase(), label: copy(label),
              }))}
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

        {findingsLoading ? (
          <p role='status' className='py-8 text-sm text-neutral-muted'>{copy('audits.findings_loading')}</p>
        ) : findings && findings.items.length > 0 ? (
          <div className='space-y-4'>
            <div className='flex flex-wrap justify-between gap-x-3 text-sm text-neutral-muted'>
              <p role='status'>
                {copy('audits.findings_range')
                  .replace('{first}', displayNumber.format((findings.page - 1) * findings.limit + 1))
                  .replace('{last}', displayNumber.format(Math.min(findings.page * findings.limit, findings.total)))
                  .replace('{total}', displayNumber.format(findings.total))}
              </p>
              <p className='hidden lg:block'>{copy('audits.sort_current_page')}</p>
            </div>

            <ul role='list' aria-label={copy('audits.all_findings')} className='space-y-2 lg:hidden'>
              {findings.items.map((finding) => (
                <MobileFindingCard key={finding.id} finding={finding} lang={lang} />
              ))}
            </ul>

            <AuditFindingsDesktop key={JSON.stringify(filters)} items={findings.items} lang={lang} />

            {/* Pagination */}
            {totalPages > 1 && (
              <div className='flex items-center justify-between pt-2'>
                <button
                  onClick={() => changePage((filters.page || 1) - 1)}
                  disabled={(filters.page || 1) <= 1}
                  className='audit-control'>
                  <ChevronLeft className='w-4 h-4' aria-hidden='true' />
                  {copy('audits.findings_previous')}
                </button>
                <span className='text-sm text-neutral-muted'>
                  {copy('audits.findings_page_of')
                    .replace('{page}', displayNumber.format(findings.page))
                    .replace('{total}', displayNumber.format(totalPages))}
                </span>
                <button
                  onClick={() => changePage((filters.page || 1) + 1)}
                  disabled={(filters.page || 1) >= totalPages}
                  className='audit-control'>
                  {copy('audits.findings_next')}
                  <ChevronRight className='w-4 h-4' aria-hidden='true' />
                </button>
              </div>
            )}
          </div>
        ) : (
          <div role='status' className='py-8 text-sm text-neutral-muted'>
            {copy(hasActiveFilters ? 'audits.findings_no_match' : 'audits.findings_empty')}
          </div>
        )}
      </section>

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
      <div className='relative min-w-0'>
        <select
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className='min-h-11 w-full min-w-0 max-w-full appearance-none rounded border border-neutral-border bg-surface-base pl-3 pr-9 text-base text-neutral-text'>
          <option value=''>{placeholder}</option>
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <ChevronDown size={16} aria-hidden='true'
          className='pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-neutral-muted' />
      </div>
    </div>
  );
}

function MobileFindingCard({ finding, lang }: { finding: FindingDetailItem; lang: Lang }) {
  const copy = (key: keyof typeof AUDITS_MESSAGES) => AUDITS_MESSAGES[key][lang];
  const severity = FINDING_SEVERITY[finding.severity.toLowerCase()];

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
        <span className={`rounded bg-surface-sunken px-1.5 font-semibold ${severity?.tone ?? 'text-neutral-text'}`}>
          {severity ? copy(severity.label) : finding.severity}
        </span>
        <span>
          {finding.amount == null
            ? copy('audits.amount_not_stated')
            : `${copy('audits.finding_amount')}: ${formatFindingAmount(finding.amount)}`}
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
