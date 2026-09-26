'use client';

/**
 * OverviewTab — the default landing tab for a county.
 *
 * Shows budget-execution hero, debt-position card, audit snapshot,
 * missing-funds banner, profile KPIs, named officials, and stalled-
 * projects summary. Pulled into its own chunk so the other five tabs
 * (which many users never open) don't bloat the initial JS payload.
 */
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { CountyComprehensive, OfficialSource } from '@/types';
import { AlertTriangle, ExternalLink, Scale, TrendingDown, TrendingUp } from 'lucide-react';
import React from 'react';
import ModelledDataNote from '@/components/ModelledDataNote';
import { ABSENT, hasIngestedAudit, fmtKES, fmtLabel, fmtPop, pct, SEVERITY_STYLE } from '../shared';
import KPI from './KPI';

/* ═══════════ Circular progress ═══════════ */
function CircleProgress({
  value,
  size = 72,
  stroke = 5,
}: {
  value: number;
  size?: number;
  stroke?: number;
}) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (Math.min(value, 100) / 100) * circ;
  const color = value >= 70 ? '#22c55e' : value >= 50 ? '#f59e0b' : '#ef4444';
  return (
    <div
      className='relative inline-flex items-center justify-center'
      style={{ width: size, height: size }}>
      <svg width={size} height={size} className='-rotate-90'>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill='none'
          stroke='#f3f4f6'
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill='none'
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap='round'
          strokeDasharray={circ}
          strokeDashoffset={offset}
          className='transition-all duration-700'
        />
      </svg>
      <span className='absolute text-sm font-bold text-gray-800 dark:text-neutral-text'>{value.toFixed(0)}%</span>
    </div>
  );
}

/* ═══════════ Officials Card — Who Runs This County ═══════════ */
/**
 * Only names a publisher supplied (#231). Both come from the Council of
 * Governors, read on every nightly seed; the API withholds a name that has
 * no source behind it.
 *
 * This card used to read party, term, deputy governor, CEC Finance, speaker
 * and website from a hand-typed `lib/data/county-officials.ts`. For Meru it
 * put the sitting governor beside his impeached predecessor's party and term,
 * and listed him again as deputy. Rows with no publisher were removed, not
 * left as "Not yet published": nothing on the nightly will ever fill them.
 */
function OfficialsCard({ data }: { data: CountyComprehensive }) {
  const { t } = useLang();
  const sources = data.officials_source;
  const rows: Array<{ role: 'governor' | 'deputy_governor'; name: string | null }> = [
    { role: 'governor', name: data.governor || null },
    { role: 'deputy_governor', name: data.deputy_governor || null },
  ];
  // One link per distinct source page; both roles usually cite the same
  // publisher but two different pages.
  const cited = rows
    .map((r) => sources?.[r.role])
    .filter((s): s is OfficialSource => !!s)
    .filter((s, i, all) => all.findIndex((o) => o.source_url === s.source_url) === i);

  return (
    <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
      <div className='mb-3'>
        <h3 className='text-sm font-semibold text-gray-800 dark:text-neutral-text'>{t('county.officials.card_title')}</h3>
        <p className='text-xs text-gray-500 dark:text-neutral-muted/80 mt-0.5'>{t('county.officials.card_subtitle')}</p>
      </div>
      <div className='grid grid-cols-1 sm:grid-cols-2 gap-3'>
        {rows.map((r) => (
          <div
            key={r.role}
            title={t(`county.officials.desc.${r.role}` as TranslationKey)}
            className='rounded-lg border border-gray-100 dark:border-neutral-border bg-gray-50/60 dark:bg-surface-elevated/70 px-3 py-2.5 hover:border-gov-sage/50 transition-colors'>
            <div className='text-[11px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold'>
              {t(`county.officials.title.${r.role}` as TranslationKey)}
            </div>
            <div
              className={`text-sm font-semibold mt-0.5 ${r.name ? 'text-gray-900 dark:text-neutral-text' : 'text-gray-400 dark:text-neutral-muted/80 italic'}`}>
              {r.name || t('county.officials.not_listed')}
            </div>
          </div>
        ))}
      </div>
      {cited.length > 0 && (
        <p className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-3'>
          {t('county.officials.source')}:{' '}
          {cited.map((s, i) => (
            <React.Fragment key={s.source_url}>
              {i > 0 && ' · '}
              <a
                href={s.source_url}
                target='_blank'
                rel='noopener noreferrer'
                className='text-gov-forest dark:text-emerald-100 hover:underline inline-flex items-center gap-1'>
                {s.publisher || new URL(s.source_url).hostname}
                <ExternalLink size={10} />
              </a>
              {s.fetched_at && (
                <span>
                  {' '}
                  ({t('county.officials.fetched')} {s.fetched_at.slice(0, 10)})
                </span>
              )}
            </React.Fragment>
          ))}
        </p>
      )}
    </div>
  );
}

/* ═══════════ Tab: Overview ═══════════ */
export default function OverviewTab({ data }: { data: CountyComprehensive }) {
  const { t } = useLang();
  const {
    demographics,
    economic_profile,
    budget,
    debt,
    audit,
    financial_summary,
    missing_funds,
    revenue,
  } = data;

  // Provenance comes from the API, which knows whether this period's headline
  // was read from a CoB BIRR table or modelled from the CRA formula. The
  // static string this replaced asserted "modelled" for every county and every
  // period, which denied the provenance of figures that ARE published.
  // Falls back to the translated string only when the API omits it.
  const budgetSourceLabel =
    data.data_sources?.budget || t('county.overview.source_cob');

  const sustainLabel: Record<
    string,
    { textKey: TranslationKey; color: string; Icon: React.ElementType }
  > = {
    sustainable: {
      textKey: 'county.overview.sustain.sustainable',
      color: 'text-emerald-700',
      Icon: TrendingUp,
    },
    moderate: {
      textKey: 'county.overview.sustain.moderate',
      color: 'text-amber-700',
      Icon: Scale,
    },
    at_risk: {
      textKey: 'county.overview.sustain.at_risk',
      color: 'text-red-700',
      Icon: TrendingDown,
    },
    unknown: {
      textKey: 'county.overview.sustain.unknown',
      color: 'text-gray-500',
      Icon: AlertTriangle,
    },
  };
  // `?? moderate` labelled a county nobody has measured. The API now returns
  // null where no source published a debt figure — 43 of the 47 — and an
  // absent assessment has to read as absent, not as the middle of three
  // verdicts.
  const sust =
    sustainLabel[financial_summary.debt_sustainability as string] ?? sustainLabel.unknown;

  return (
    <div className='space-y-6'>
      <ModelledDataNote budgetSource={budget.source} />
      {/* Hero row: Budget execution as a magazine-style feature */}
      <div className='grid grid-cols-1 lg:grid-cols-5 gap-5'>
        {/* Budget execution — large, editorial */}
        <div className='lg:col-span-3 rounded-2xl bg-gradient-to-br from-white via-white to-gov-sage/5 dark:from-surface-elevated dark:via-surface-base dark:to-surface-elevated border border-gray-100 dark:border-neutral-border p-6 shadow-sm'>
          <div className='flex items-start gap-6'>
            <CircleProgress value={budget.utilization_rate} />
            <div className='min-w-0 flex-1'>
              <div className='text-[11px] uppercase tracking-widest font-semibold text-gray-400 dark:text-neutral-muted/80 mb-1'>
                {t('county.overview.budget_execution')}
              </div>
              <div className='text-2xl font-bold text-gray-900 dark:text-neutral-text mb-2'>
                {pct(budget.utilization_rate)}
                <span className='text-sm font-normal text-gray-500 dark:text-neutral-muted/80 ml-2'>
                  {t('county.overview.utilized_suffix')}
                </span>
              </div>
              <div className='text-sm text-gray-600 dark:text-neutral-muted leading-relaxed'>
                <span className='font-semibold tabular-nums'>
                  {fmtKES(budget.total_spent)}
                </span>{' '}
                {t('county.overview.spent_of')}{' '}
                <span className='font-semibold tabular-nums'>
                  {fmtKES(budget.total_allocated)}
                </span>{' '}
                {t('county.overview.allocated_suffix')}
              </div>
              {budget.fiscal_year && (
                <div className='mt-2 text-[11px] text-gray-400 dark:text-neutral-muted/80'>
                  {budgetSourceLabel} · {budget.fiscal_year}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Debt sustainability — minimal, gradient tinted */}
        <div
          className={`lg:col-span-2 rounded-2xl border p-6 shadow-sm ${
            financial_summary.debt_sustainability === 'sustainable'
              ? 'bg-gradient-to-br from-emerald-50/70 to-white border-emerald-100'
              : financial_summary.debt_sustainability === 'at_risk'
                ? 'bg-gradient-to-br from-rose-50/70 to-white border-rose-100'
                : financial_summary.debt_sustainability === 'moderate'
                  ? 'bg-gradient-to-br from-amber-50/70 to-white border-amber-100'
                  : 'bg-white border-gray-200'
          }`}>
          <div className='flex items-center gap-2 mb-3'>
            <sust.Icon size={18} className={sust.color} />
            <span className={`text-sm font-semibold ${sust.color}`}>{t(sust.textKey)}</span>
          </div>
          <div className='text-[11px] uppercase tracking-widest font-semibold text-gray-400 dark:text-neutral-muted/80 mb-2'>
            {t('county.overview.debt_position')}
          </div>
          <div className='space-y-1.5 text-sm'>
            <div className='flex justify-between'>
              <span className='text-gray-500 dark:text-neutral-muted/80'>{t('county.overview.debt_total')}</span>
              <span className='font-semibold text-gray-800 dark:text-neutral-text tabular-nums'>
                {fmtKES(debt.total_debt)}
              </span>
            </div>
            <div className='flex justify-between'>
              <span className='text-gray-500 dark:text-neutral-muted/80'>{t('county.overview.debt_to_budget')}</span>
              <span className='font-semibold text-gray-800 dark:text-neutral-text tabular-nums'>
                {pct(debt.debt_to_budget_ratio)}
              </span>
            </div>
            <div className='flex justify-between'>
              <span className='text-gray-500 dark:text-neutral-muted/80'>{t('county.overview.debt_pending')}</span>
              <span className='font-semibold text-gray-800 dark:text-neutral-text tabular-nums'>
                {fmtKES(debt.pending_bills)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Audit snapshot — wide banner */}
      <div className='relative rounded-2xl bg-white dark:bg-surface-base border border-gray-100 dark:border-neutral-border p-5 overflow-hidden'>
        <div
          aria-hidden
          className={`absolute inset-y-0 left-0 w-1 ${
            // Green for "0 findings" told the reader this county came back
            // clean. Absent is grey, not green (credibility audit F23).
            !hasIngestedAudit(audit)
              ? 'bg-neutral-border'
              : audit.findings_count === 0
                ? 'bg-emerald-400'
                : (audit.by_severity.critical || 0) > 0
                  ? 'bg-rose-500'
                  : 'bg-amber-400'
          }`}
        />
        <div className='flex flex-col sm:flex-row sm:items-center justify-between gap-3 pl-2'>
          <div>
            <div className='text-[11px] uppercase tracking-widest font-semibold text-gray-400 dark:text-neutral-muted/80 mb-1'>
              {t('county.overview.audit_snapshot')}
            </div>
            <div className='flex items-center gap-4 flex-wrap'>
              {(['critical', 'warning', 'info'] as const).map((sev) => {
                const count = hasIngestedAudit(audit)
                  ? audit.by_severity[sev] || 0
                  : null;
                const s = SEVERITY_STYLE[sev];
                return (
                  <div key={sev} className='flex items-center gap-1.5'>
                    <div className={`w-2 h-2 rounded-full ${s.dot}`} />
                    <span className='text-sm text-gray-700 dark:text-neutral-muted'>
                      <span className='font-semibold tabular-nums'>{count ?? '—'}</span>{' '}
                      {t(s.lowerKey)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
          {audit.total_amount_involved != null && audit.total_amount_involved > 0 && (
            <div className='text-right'>
              <div className='text-xs text-gray-500 dark:text-neutral-muted/80'>
                {t('county.overview.total_amount_involved')}
              </div>
              <div className='text-base font-bold text-rose-700 tabular-nums'>
                {fmtKES(audit.total_amount_involved)}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Missing funds banner */}
      {(missing_funds.total_amount > 0 || missing_funds.cases_count > 0) && (
        <div className='bg-red-50 border border-red-200 rounded-xl p-4 flex items-center gap-4'>
          <div className='w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0'>
            <AlertTriangle size={20} className='text-red-600' />
          </div>
          <div>
            <div className='text-sm font-semibold text-red-900'>
              {fmtKES(missing_funds.total_amount)} {t('county.overview.missing_unaccounted')}
            </div>
            <div className='text-xs text-red-700'>
              {missing_funds.cases_count} {t('county.overview.cases_oag')}
            </div>
          </div>
        </div>
      )}

      {/* About this county */}
      <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
        <h3 className='text-sm font-semibold text-gray-800 dark:text-neutral-text mb-3'>{t('county.profile.title')}</h3>
        <div className='grid grid-cols-2 sm:grid-cols-4 gap-y-4 gap-x-6'>
          <KPI
            label={t('county.profile.population')}
            value={fmtPop(demographics.population)}
            sub={
              demographics.population_year
                ? `${t('county.overview.kpi.census')} ${demographics.population_year}`
                : undefined
            }
            accent='text-blue-700'
          />
          <KPI
            label={t('county.profile.governor')}
            value={data.governor || t('county.overview.kpi.na')}
            accent='text-purple-700'
          />
          <KPI
            label={t('county.profile.economic_base')}
            value={
              economic_profile.economic_base
                ? fmtLabel(economic_profile.economic_base)
                : ABSENT
            }
            accent='text-emerald-700'
          />
          <KPI
            label={t('county.overview.kpi.total_revenue')}
            value={fmtKES(revenue.total_revenue)}
            sub={
              revenue.local_revenue > 0
                ? `${t('county.overview.kpi.local_prefix')} ${fmtKES(revenue.local_revenue)}`
                : undefined
            }
            accent='text-green-700'
          />
        </div>

        {economic_profile.major_issues.length > 0 && (
          <div className='mt-4 pt-4 border-t border-gray-100 dark:border-neutral-border'>
            <div className='text-xs font-semibold text-gray-500 dark:text-neutral-muted/80 uppercase tracking-wider mb-2'>
              {t('county.overview.key_challenges')}
            </div>
            <div className='flex flex-wrap gap-2'>
              {economic_profile.major_issues.map((issue, i) => (
                <span
                  key={i}
                  className='text-xs bg-amber-50 text-amber-800 border border-amber-200 rounded-full px-2.5 py-1'>
                  {issue}
                </span>
              ))}
            </div>
            <p className='mt-2 text-[11px] text-gray-400 dark:text-neutral-muted/80 italic'>
              {economic_profile.major_issues_source
                ? t('county.overview.challenges_oag_note')
                : t('county.overview.challenges_generic_note')}
            </p>
          </div>
        )}
      </div>

      {/* Who Runs This County — named officials */}
      <OfficialsCard data={data} />

      {/* The stalled-projects summary card was withdrawn along with the
          Projects tab (credibility audit F6) — it summarised a hand-written
          fixture whose Auditor-General case references were never read from any
          OAG report. See the note on TABS in CountyDetailClient.tsx. */}
    </div>
  );
}
