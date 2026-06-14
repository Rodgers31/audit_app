'use client';

/**
 * AuditTab — expanded list and category breakdown of a county's audit
 * findings, powered by the OAG dataset. Each finding gets a plain-language
 * "what this means" explanation and a status chip. Split into its own
 * chunk so framer-motion's expand/collapse animations don't load for
 * users who never open this tab.
 */
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { CountyComprehensive } from '@/types';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, CheckCircle2, ChevronDown } from 'lucide-react';
import { useMemo, useState } from 'react';
import { fmtKES, SEVERITY_STYLE } from '../shared';

const CATEGORY_CONFIG: Record<
  string,
  { labelKey: TranslationKey; color: string; bg: string; icon: string }
> = {
  'Financial Irregularity': {
    labelKey: 'county.audit.cat.financial_irregularity',
    color: 'text-red-700',
    bg: 'bg-red-50 border-red-200',
    icon: '💰',
  },
  'Asset Management': {
    labelKey: 'county.audit.cat.asset_management',
    color: 'text-amber-700',
    bg: 'bg-amber-50 border-amber-200',
    icon: '🏗️',
  },
  'Missing Funds': {
    labelKey: 'county.audit.cat.missing_funds',
    color: 'text-red-800',
    bg: 'bg-red-100 border-red-300',
    icon: '🚨',
  },
  'Procurement Issues': {
    labelKey: 'county.audit.cat.procurement',
    color: 'text-orange-700',
    bg: 'bg-orange-50 border-orange-200',
    icon: '📋',
  },
  'Payroll Issues': {
    labelKey: 'county.audit.cat.payroll',
    color: 'text-purple-700',
    bg: 'bg-purple-50 border-purple-200',
    icon: '👥',
  },
  'Revenue Collection': {
    labelKey: 'county.audit.cat.revenue_collection',
    color: 'text-blue-700',
    bg: 'bg-blue-50 border-blue-200',
    icon: '🏦',
  },
  other: {
    labelKey: 'county.audit.cat.other',
    color: 'text-gray-700 dark:text-neutral-muted',
    bg: 'bg-gray-50 dark:bg-surface-elevated border-gray-200 dark:border-neutral-border',
    icon: '📄',
  },
};

const STATUS_CONFIG: Record<string, { labelKey: TranslationKey; color: string; dot: string }> = {
  'Under Review': {
    labelKey: 'county.audit.status.under_review',
    color: 'text-yellow-700 bg-yellow-50 border-yellow-200',
    dot: 'bg-yellow-500',
  },
  Escalated: {
    labelKey: 'county.audit.status.escalated',
    color: 'text-red-700 bg-red-50 border-red-200',
    dot: 'bg-red-500',
  },
  Resolved: {
    labelKey: 'county.audit.status.resolved',
    color: 'text-green-700 bg-green-50 border-green-200',
    dot: 'bg-green-500',
  },
  Pending: {
    labelKey: 'county.audit.status.pending',
    color: 'text-gray-600 dark:text-neutral-muted bg-gray-50 dark:bg-surface-elevated border-gray-200 dark:border-neutral-border',
    dot: 'bg-gray-400',
  },
  open: {
    labelKey: 'county.audit.status.open',
    color: 'text-yellow-700 bg-yellow-50 border-yellow-200',
    dot: 'bg-yellow-500',
  },
};

export default function AuditTab({ data }: { data: CountyComprehensive }) {
  const { t } = useLang();
  const { audit, missing_funds } = data;
  const [expanded, setExpanded] = useState<number | null>(null);
  const [filterCategory, setFilterCategory] = useState<string>('all');

  // Group findings by category for the summary
  const categoryBreakdown = useMemo(() => {
    const map: Record<string, { count: number; amount: number }> = {};
    for (const f of audit.findings) {
      const cat = f.category || 'other';
      if (!map[cat]) map[cat] = { count: 0, amount: 0 };
      map[cat].count++;
      map[cat].amount += f.amount_involved || 0;
    }
    return Object.entries(map).sort((a, b) => b[1].amount - a[1].amount);
  }, [audit.findings]);

  const filteredFindings = useMemo(() => {
    if (filterCategory === 'all') return audit.findings;
    return audit.findings.filter((f) => (f.category || 'other') === filterCategory);
  }, [audit.findings, filterCategory]);

  const statusCounts = useMemo(() => {
    const map: Record<string, number> = {};
    for (const f of audit.findings) {
      const st = f.status || 'open';
      map[st] = (map[st] || 0) + 1;
    }
    return map;
  }, [audit.findings]);

  return (
    <div className='space-y-5'>
      {/* ── What this means (plain language intro) ── */}
      <div className='bg-gov-forest/5 border border-gov-forest/20 rounded-xl p-4'>
        <h3 className='text-sm font-semibold text-gov-dark dark:text-white mb-1'>
          {t('county.audit.intro_title')}
        </h3>
        <p className='text-xs text-gray-600 dark:text-neutral-muted leading-relaxed'>{t('county.audit.intro_body')}</p>
      </div>

      {/* ── Top-level stats ── */}
      <div className='grid grid-cols-2 sm:grid-cols-4 gap-3'>
        <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-4 text-center'>
          <div className='text-2xl font-bold text-gray-900 dark:text-neutral-text'>{audit.findings_count}</div>
          <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
            {t('county.audit.kpi_total_findings')}
          </div>
        </div>
        <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-4 text-center'>
          <div className='text-2xl font-bold text-red-700'>
            {audit.total_amount_involved > 0 ? fmtKES(audit.total_amount_involved) : 'KES 0'}
          </div>
          <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
            {t('county.audit.kpi_money_questioned')}
          </div>
        </div>
        <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-4 text-center'>
          <div className='flex items-center justify-center gap-1.5'>
            <div className='w-2 h-2 rounded-full bg-red-500' />
            <span className='text-2xl font-bold text-gray-900 dark:text-neutral-text'>
              {audit.by_severity.critical || 0}
            </span>
          </div>
          <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
            {t('county.audit.kpi_critical_issues')}
          </div>
        </div>
        <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-4 text-center'>
          <div className='text-2xl font-bold text-green-700'>{statusCounts['Resolved'] || 0}</div>
          <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-0.5'>{t('county.audit.kpi_resolved')}</div>
        </div>
      </div>

      {/* ── Category breakdown ── */}
      {categoryBreakdown.length > 0 && (
        <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
          <h3 className='text-sm font-semibold text-gray-800 dark:text-neutral-text mb-3'>
            {t('county.audit.findings_by_category')}
          </h3>
          <div className='space-y-2'>
            {categoryBreakdown.map(([cat, { count, amount }]) => {
              const cfg = CATEGORY_CONFIG[cat] || CATEGORY_CONFIG.other;
              const pctOfTotal =
                audit.total_amount_involved > 0 ? (amount / audit.total_amount_involved) * 100 : 0;
              return (
                <button
                  key={cat}
                  onClick={() => setFilterCategory(filterCategory === cat ? 'all' : cat)}
                  className={`w-full text-left rounded-lg border p-3 transition-all ${
                    filterCategory === cat
                      ? 'ring-2 ring-gov-forest/30 border-gov-forest/40 bg-gov-forest/5'
                      : 'hover:bg-gray-50 dark:bg-surface-elevated border-gray-100 dark:border-neutral-border'
                  }`}>
                  <div className='flex items-center justify-between mb-1'>
                    <div className='flex items-center gap-2'>
                      <span className='text-sm'>{cfg.icon}</span>
                      <span className='text-sm font-medium text-gray-800 dark:text-neutral-text'>{t(cfg.labelKey)}</span>
                      <span className='text-xs text-gray-400 dark:text-neutral-muted/80'>
                        {count}{' '}
                        {count !== 1
                          ? t('county.audit.finding_plural')
                          : t('county.audit.finding_singular')}
                      </span>
                    </div>
                    {amount > 0 && (
                      <span className={`text-sm font-semibold ${cfg.color}`}>{fmtKES(amount)}</span>
                    )}
                  </div>
                  {pctOfTotal > 0 && (
                    <div className='h-1.5 bg-gray-100 dark:bg-surface-elevated rounded-full overflow-hidden'>
                      <div
                        className='h-full bg-red-400 rounded-full transition-all'
                        style={{ width: `${Math.min(pctOfTotal, 100)}%` }}
                      />
                    </div>
                  )}
                </button>
              );
            })}
          </div>
          {filterCategory !== 'all' && (
            <button
              onClick={() => setFilterCategory('all')}
              className='mt-2 text-xs text-gov-forest dark:text-emerald-100 hover:underline'>
              {t('county.audit.show_all_categories')}
            </button>
          )}
        </div>
      )}

      {/* ── Status summary row ── */}
      <div className='flex flex-wrap gap-2'>
        {Object.entries(statusCounts).map(([status, count]) => {
          const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.open;
          return (
            <div
              key={status}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border ${cfg.color}`}>
              <div className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
              {t(cfg.labelKey)}: {count}
            </div>
          );
        })}
      </div>

      {/* ── Missing funds alert ── */}
      {(missing_funds.total_amount > 0 || missing_funds.cases_count > 0) && (
        <div className='bg-red-50 border border-red-200 rounded-xl p-4'>
          <div className='flex items-center gap-2 mb-1'>
            <AlertTriangle size={16} className='text-red-600' />
            <span className='text-sm font-semibold text-red-900'>
              {fmtKES(missing_funds.total_amount)} {t('county.audit.missing_unaccounted')}
            </span>
          </div>
          <div className='text-xs text-red-700'>
            {missing_funds.cases_count} {t('county.audit.cases_flagged')}
          </div>
        </div>
      )}

      {/* ── Findings list ── */}
      <div className='space-y-3'>
        <div className='flex items-center justify-between'>
          <h3 className='text-sm font-semibold text-gray-800 dark:text-neutral-text'>
            {filterCategory === 'all'
              ? t('county.audit.all_findings_title')
              : `${t((CATEGORY_CONFIG[filterCategory] || CATEGORY_CONFIG.other).labelKey)} ${t('county.audit.category_findings_suffix')}`}
          </h3>
          <span className='text-xs text-gray-400 dark:text-neutral-muted/80'>
            {filteredFindings.length}{' '}
            {filteredFindings.length !== 1
              ? t('county.audit.finding_plural')
              : t('county.audit.finding_singular')}
          </span>
        </div>

        {filteredFindings.slice(0, 20).map((f) => {
          const s = SEVERITY_STYLE[f.severity] || SEVERITY_STYLE.info;
          const catCfg = CATEGORY_CONFIG[f.category] || CATEGORY_CONFIG.other;
          const stCfg = STATUS_CONFIG[f.status] || STATUS_CONFIG.open;
          const open = expanded === f.id;

          // Pre-compute the "what does this mean" text
          const amountStr =
            f.amount_involved > 0 ? f.amount_involved.toLocaleString() : '';
          const undisclosedAmount = t('county.audit.explain.undisclosed_amount');
          const undisclosedValue = t('county.audit.explain.undisclosed_value');
          const amountFallback = t('county.audit.explain.amount_fallback');
          const fundsFallback = t('county.audit.explain.funds_fallback');
          const undisclosedAmounts = t('county.audit.explain.undisclosed_amounts');

          let meansText = '';
          if (f.category === 'Missing Funds') {
            meansText = t('county.audit.explain.missing_funds').replace(
              '{amount}',
              amountStr || undisclosedAmount
            );
          } else if (f.category === 'Financial Irregularity') {
            meansText = t('county.audit.explain.financial_irregularity').replace(
              '{amount}',
              amountStr || amountFallback
            );
          } else if (f.category === 'Asset Management') {
            meansText = t('county.audit.explain.asset_management').replace(
              '{amount}',
              amountStr || undisclosedValue
            );
          } else if (f.category === 'Procurement Issues') {
            meansText = t('county.audit.explain.procurement').replace(
              '{amount}',
              amountStr || fundsFallback
            );
          } else if (f.category === 'Payroll Issues') {
            meansText = t('county.audit.explain.payroll').replace(
              '{amount}',
              amountStr || undisclosedAmounts
            );
          } else {
            const amountClause =
              f.amount_involved > 0
                ? t('county.audit.explain.amount_clause').replace('{amount}', amountStr)
                : '';
            meansText = t('county.audit.explain.default').replace(
              '{amount_clause}',
              amountClause
            );
          }

          // Status explanation
          let statusExplain = '';
          if (f.status === 'Resolved') {
            statusExplain = t('county.audit.status_explain.resolved');
          } else if (f.status === 'Escalated') {
            statusExplain = t('county.audit.status_explain.escalated');
          } else if (f.status === 'Under Review') {
            statusExplain = t('county.audit.status_explain.under_review');
          } else if (f.status === 'Pending') {
            statusExplain = t('county.audit.status_explain.pending');
          } else {
            statusExplain = t('county.audit.status_explain.default');
          }

          return (
            <div
              key={f.id}
              className={`rounded-xl border border-gray-100 dark:border-neutral-border bg-white dark:bg-surface-base overflow-hidden transition-shadow ${
                open ? 'shadow-md ring-1 ring-gray-200' : 'hover:shadow-sm'
              }`}>
              <button
                onClick={() => setExpanded(open ? null : f.id)}
                className='w-full text-left px-4 py-3.5 hover:bg-gray-50/50 dark:bg-surface-elevated/70 transition-colors'>
                {/* Top row: category tag + status + amount */}
                <div className='flex items-center gap-2 flex-wrap mb-2'>
                  <span
                    className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border ${catCfg.bg} ${catCfg.color}`}>
                    {catCfg.icon} {t(catCfg.labelKey)}
                  </span>
                  <span
                    className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full border ${stCfg.color}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${stCfg.dot}`} />
                    {t(stCfg.labelKey)}
                  </span>
                  <span className={`text-[10px] font-bold uppercase tracking-wider ${s.text}`}>
                    {t(s.labelKey)}
                  </span>
                  {f.audit_year && (
                    <span className='text-[10px] text-gray-400 dark:text-neutral-muted/80 ml-auto'>
                      {t('county.audit.fy_prefix')} {f.audit_year}
                    </span>
                  )}
                </div>

                {/* Finding text */}
                <p className='text-sm text-gray-800 dark:text-neutral-text leading-relaxed mb-1.5'>{f.finding}</p>

                {/* Bottom row: amount + reference + expand arrow */}
                <div className='flex items-center gap-3'>
                  {f.amount_involved > 0 && (
                    <span className='text-sm font-bold text-red-700 tabular-nums'>
                      {fmtKES(f.amount_involved)}
                    </span>
                  )}
                  {f.reference && (
                    <span className='text-[10px] text-gray-400 dark:text-neutral-muted/80 font-mono'>
                      {t('county.audit.ref_prefix')} {f.reference}
                    </span>
                  )}
                  <ChevronDown
                    size={14}
                    className={`text-gray-400 dark:text-neutral-muted/80 ml-auto flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
                  />
                </div>
              </button>

              <AnimatePresence>
                {open && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className='overflow-hidden'>
                    <div className='px-4 pb-4 pt-0 border-t border-gray-100 dark:border-neutral-border'>
                      {/* What this means section */}
                      <div className='mt-3 mb-3 bg-blue-50 border border-blue-100 rounded-lg p-3'>
                        <h4 className='text-xs font-semibold text-blue-800 mb-1'>
                          {t('county.audit.what_means')}
                        </h4>
                        <p className='text-xs text-blue-700 leading-relaxed'>{meansText}</p>
                      </div>

                      {/* Recommendation */}
                      {f.recommendation && (
                        <div className='bg-green-50 border border-green-100 rounded-lg p-3'>
                          <h4 className='text-xs font-semibold text-green-800 mb-1'>
                            <CheckCircle2 size={12} className='inline mr-1' />
                            {t('county.audit.recommendation')}
                          </h4>
                          <p className='text-xs text-green-700 leading-relaxed'>
                            {f.recommendation}
                          </p>
                        </div>
                      )}

                      {/* Status explanation */}
                      <div className='mt-2 text-[11px] text-gray-500 dark:text-neutral-muted/80'>{statusExplain}</div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>

      {filteredFindings.length > 20 && (
        <p className='text-xs text-gray-500 dark:text-neutral-muted/80 text-center'>
          {t('county.audit.showing_of').replace('{n}', String(filteredFindings.length))}
        </p>
      )}
    </div>
  );
}
