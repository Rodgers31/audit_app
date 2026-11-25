'use client';

import UnaccountedFindings from '@/components/accountability/UnaccountedFindings';
import { useLang } from '@/lib/i18n/LangProvider';
import type { CountyComprehensive } from '@/types';
import { useMemo, useState } from 'react';
import styles from '../../CountyExperience.module.css';
import { fmtKES, hasIngestedAudit } from '../shared';
import CountyAuditFindingsList, { CATEGORY_LABELS, STATUS_LABELS } from './CountyAuditFindingsList';

export default function AuditTab({ data }: { data: CountyComprehensive }) {
  const { t } = useLang();
  const { audit, missing_funds } = data;
  const [filterCategory, setFilterCategory] = useState<string>('all');

  // Group findings by category for the summary
  const categoryBreakdown = useMemo(() => {
    const map = new Map<string, { count: number; amount: number }>();
    for (const f of audit.findings) {
      const cat = f.category || 'other';
      const totals = map.get(cat) ?? { count: 0, amount: 0 };
      totals.count += 1;
      // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- accumulator seed, not a published figure
      totals.amount += f.amount_involved || 0;
      map.set(cat, totals);
    }
    return Array.from(map).sort((a, b) => b[1].amount - a[1].amount);
  }, [audit.findings]);

  const hasCategories = categoryBreakdown.length > 1;
  const activeCategory = hasCategories && categoryBreakdown.some(([category]) => category === filterCategory)
    ? filterCategory : 'all';
  const filteredFindings = activeCategory === 'all'
    ? audit.findings
    : audit.findings.filter(finding => (finding.category || 'other') === activeCategory);
  const categoryLabel = (category: string) => {
    const label = CATEGORY_LABELS.get(category);
    return label ? t(label) : category;
  };

  const ingested = hasIngestedAudit(audit);

  const statusCounts = useMemo(() => {
    const map = new Map<string, number>();
    for (const f of audit.findings) {
      const st = f.status || 'open';
      map.set(st, (map.get(st) ?? 0) + 1);
    }
    return map;
  }, [audit.findings]);

  return (
    <div className='space-y-5'>
      {/* ── What this means (plain language intro) ── */}
      <div className={styles.note}>
        <h3 className='text-sm font-semibold text-gov-dark dark:text-white mb-1'>
          {t('county.audit.intro_title')}
        </h3>
        <p className='text-xs text-gray-600 dark:text-neutral-muted leading-relaxed'>
          {t('county.audit.intro_body')}
        </p>
      </div>

      {!ingested && (
        <div className='rounded-xl border border-neutral-border/60 bg-surface-sunken/40 px-4 py-3'>
          <p className='text-[12.5px] leading-relaxed text-neutral-muted'>
            <span className='font-semibold text-gov-dark dark:text-white'>
              No Auditor-General report for this county has been ingested yet.
            </span>{' '}
            The counters below read &ldquo;—&rdquo; rather than zero because a zero would say the
            Auditor-General examined this county and questioned nothing. That is not what an absent
            report means.
          </p>
        </div>
      )}

      {/* ── Top-level stats ── */}
      <div className='grid grid-cols-2 sm:grid-cols-4 gap-3'>
        <div className={styles.tabMetric}>
          {/* "0 Total Findings" read as a clean bill of health. It means no
              OAG report for this county has been ingested (F23). */}
          <div className='text-2xl font-bold text-gray-900 dark:text-neutral-text'>
            {ingested ? audit.findings_count : '—'}
          </div>
          <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
            {t('county.audit.kpi_total_findings')}
          </div>
        </div>
        <div className={styles.tabMetric}>
          <div className='text-2xl font-bold text-red-700'>
            {audit.total_amount_involved != null && audit.total_amount_involved > 0
              ? fmtKES(audit.total_amount_involved)
              : audit.total_amount_involved === 0
                ? fmtKES(0)
                : '—'}
          </div>
          <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
            {t('county.audit.kpi_money_questioned')}
          </div>
        </div>
        <div className={styles.tabMetric}>
          <div className='flex items-center justify-center gap-1.5'>
            <div className='w-2 h-2 rounded-full bg-red-500' />
            <span className='text-2xl font-bold text-gray-900 dark:text-neutral-text'>
              {ingested ? audit.by_severity.critical || 0 : '—'}
            </span>
          </div>
          <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
            {t('county.audit.kpi_critical_issues')}
          </div>
        </div>
        <div className={styles.tabMetric}>
          <div className='text-2xl font-bold text-green-700'>
            {ingested ? statusCounts.get('Resolved') ?? 0 : '—'}
          </div>
          <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
            {t('county.audit.kpi_resolved')}
          </div>
        </div>
      </div>

      {hasCategories && (
        <div className={styles.section} role='group' aria-label={t('county.audit.findings_by_category')}>
          <h3 className='mb-3 text-sm font-semibold text-neutral-text'>
            {t('county.audit.findings_by_category')}
          </h3>
          <div className='flex flex-wrap items-center gap-2'>
            <button type='button' className='audit-control aria-pressed:border-neutral-text aria-pressed:bg-surface-sunken'
              aria-pressed={activeCategory === 'all'} onClick={() => setFilterCategory('all')}>
              {t('county.audit.show_all_categories')}
            </button>
            {categoryBreakdown.map(([category, { count, amount }]) => (
              <button key={category} type='button'
                className='audit-control min-w-0 max-w-full flex-wrap text-left [overflow-wrap:anywhere] aria-pressed:border-neutral-text aria-pressed:bg-surface-sunken'
                aria-pressed={activeCategory === category}
                onClick={() => setFilterCategory(activeCategory === category ? 'all' : category)}>
                <span>{categoryLabel(category)}</span>
                <span className='text-neutral-muted'>
                  {count} {t(count === 1 ? 'county.audit.finding_singular' : 'county.audit.finding_plural')}
                </span>
                {amount > 0 && <span>{fmtKES(amount)}</span>}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Status summary row ── */}
      <div className='flex flex-wrap gap-2'>
        {Array.from(statusCounts).map(([status, count]) => {
          const label = STATUS_LABELS.get(status.toLowerCase());
          return (
            <span key={status} className='text-sm text-neutral-muted'>
              {label ? t(label) : status} · {count}
            </span>
          );
        })}
      </div>

      {/* ── Missing funds alert ── */}
      <UnaccountedFindings cases={missing_funds.cases} />

      <CountyAuditFindingsList key={activeCategory} findings={filteredFindings} sourceCases={missing_funds.cases}
        title={activeCategory === 'all'
          ? t('county.audit.all_findings_title')
          : t('county.audit.category_findings_title').replace('{category}', () => categoryLabel(activeCategory))}
      />
    </div>
  );
}
