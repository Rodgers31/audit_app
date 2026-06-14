'use client';

/**
 * AccountabilityTab — editorial presentation of the county's
 * accountability grade, how it was computed (per-factor breakdown),
 * key metrics, historical audit opinions, and peer comparisons.
 *
 * Split off because it pulls in its own queryset (useCountyAccountability)
 * and lookup tables (ACCT_GRADE_STYLE, OPINION_COLOR) that aren't needed
 * by the other tabs.
 */
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { useCountyAccountability } from '@/lib/react-query/useCounties';
import { CountyComprehensive } from '@/types';
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Clock,
  FileWarning,
  Info,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react';
import { fmtKES } from '../shared';

const ACCT_GRADE_STYLE: Record<
  string,
  { bg: string; text: string; border: string; labelKey: TranslationKey; glow: string }
> = {
  A: {
    bg: 'bg-emerald-500',
    text: 'text-white',
    border: 'border-emerald-600',
    labelKey: 'county.acct.grade_excellent',
    glow: 'bg-emerald-300',
  },
  B: {
    bg: 'bg-teal-500',
    text: 'text-white',
    border: 'border-teal-600',
    labelKey: 'county.acct.grade_good',
    glow: 'bg-teal-300',
  },
  C: {
    bg: 'bg-yellow-400',
    text: 'text-yellow-900',
    border: 'border-yellow-500',
    labelKey: 'county.acct.grade_fair',
    glow: 'bg-yellow-300',
  },
  D: {
    bg: 'bg-orange-500',
    text: 'text-white',
    border: 'border-orange-600',
    labelKey: 'county.acct.grade_needs_improvement',
    glow: 'bg-orange-300',
  },
  F: {
    bg: 'bg-red-600',
    text: 'text-white',
    border: 'border-red-700',
    labelKey: 'county.acct.grade_poor',
    glow: 'bg-rose-300',
  },
};

const IMPACT_STYLE: Record<string, { chip: string; dot: string; labelKey: TranslationKey }> = {
  positive: {
    chip: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    dot: 'bg-emerald-500',
    labelKey: 'county.acct.impact_positive',
  },
  minor: {
    chip: 'bg-yellow-50 text-yellow-700 border-yellow-200',
    dot: 'bg-yellow-500',
    labelKey: 'county.acct.impact_minor',
  },
  moderate: {
    chip: 'bg-orange-50 text-orange-700 border-orange-200',
    dot: 'bg-orange-500',
    labelKey: 'county.acct.impact_moderate',
  },
  major: {
    chip: 'bg-rose-50 text-rose-700 border-rose-200',
    dot: 'bg-rose-500',
    labelKey: 'county.acct.impact_major',
  },
};

const OPINION_COLOR: Record<string, string> = {
  Unqualified: 'bg-emerald-500 text-white',
  Qualified: 'bg-yellow-400 text-yellow-900',
  Adverse: 'bg-red-500 text-white',
  Disclaimer: 'bg-red-700 text-white',
};

const OPINION_KEY: Record<string, TranslationKey> = {
  Unqualified: 'county.acct.opinion.unqualified',
  Qualified: 'county.acct.opinion.qualified',
  Adverse: 'county.acct.opinion.adverse',
  Disclaimer: 'county.acct.opinion.disclaimer',
};

export default function AccountabilityTab({ data: countyData }: { data: CountyComprehensive }) {
  const { t } = useLang();
  const { data, isLoading, error } = useCountyAccountability(countyData.id);

  if (isLoading) {
    return (
      <div className='flex items-center justify-center py-16'>
        <div className='animate-spin rounded-full h-10 w-10 border-b-2 border-gov-forest' />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className='bg-red-50 border border-red-200 rounded-xl p-6 text-center'>
        <ShieldAlert size={28} className='mx-auto text-red-400 mb-2' />
        <p className='text-sm text-red-700'>{t('county.acct.failed_load')}</p>
      </div>
    );
  }

  const gradeStyle = ACCT_GRADE_STYLE[data.accountability_grade] || ACCT_GRADE_STYLE.F;
  const peer = data.peer_comparison;
  const isBelowRegion = data.total_flagged_amount > peer.region_avg_flagged_amount;
  const isBelowBracket = data.total_flagged_amount > peer.population_bracket_avg;
  const score =
    typeof data.accountability_score === 'number' ? data.accountability_score : null;
  const factors = data.grade_factors || [];

  // Score arc — 0 to 100 maps to stroke-dashoffset on a circle
  const CIRC = 2 * Math.PI * 42; // r=42
  const scorePct = score !== null ? Math.max(0, Math.min(100, score)) : 0;
  const dashOffset = CIRC - (scorePct / 100) * CIRC;
  const arcColor =
    score === null
      ? '#9ca3af'
      : score >= 85
        ? '#10b981'
        : score >= 70
          ? '#14b8a6'
          : score >= 55
            ? '#eab308'
            : score >= 40
              ? '#f97316'
              : '#dc2626';

  return (
    <div className='space-y-6'>
      {/* A. GRADE — editorial hero with score ring */}
      <div className='relative overflow-hidden rounded-2xl bg-gradient-to-br from-white to-gov-sage/5 dark:from-surface-elevated dark:to-surface-base border border-gray-100 dark:border-neutral-border p-6'>
        <div
          aria-hidden
          className={`absolute top-0 right-0 w-40 h-40 rounded-full blur-3xl opacity-30 ${gradeStyle.glow}`}
        />
        <div className='relative flex flex-col sm:flex-row items-center sm:items-start gap-6'>
          {/* Score ring with grade letter centered */}
          <div className='relative flex-shrink-0'>
            <svg width='112' height='112' viewBox='0 0 100 100' className='-rotate-90'>
              <circle
                cx='50'
                cy='50'
                r='42'
                fill='none'
                stroke='#f1f5f9'
                strokeWidth='8'
              />
              <circle
                cx='50'
                cy='50'
                r='42'
                fill='none'
                stroke={arcColor}
                strokeWidth='8'
                strokeLinecap='round'
                strokeDasharray={CIRC}
                strokeDashoffset={dashOffset}
                style={{ transition: 'stroke-dashoffset 0.8s ease-out' }}
              />
            </svg>
            <div className='absolute inset-0 flex flex-col items-center justify-center'>
              <span
                className={`text-4xl font-black leading-none ${
                  score !== null && score >= 55 ? 'text-gray-800 dark:text-neutral-text' : 'text-gray-800 dark:text-neutral-text'
                }`}
                style={{ color: arcColor }}>
                {data.accountability_grade}
              </span>
              {score !== null && (
                <span className='text-[10px] font-semibold text-gray-500 dark:text-neutral-muted/80 tabular-nums mt-0.5'>
                  {score.toFixed(0)}/100
                </span>
              )}
            </div>
          </div>

          <div className='text-center sm:text-left flex-1'>
            <div className='text-[11px] uppercase tracking-widest font-semibold text-gray-400 dark:text-neutral-muted/80 mb-1'>
              {t('county.acct.grade_label')}
            </div>
            <h3 className='text-2xl font-bold text-gray-900 dark:text-neutral-text mb-1'>{t(gradeStyle.labelKey)}</h3>
            <p className='text-sm text-gray-600 dark:text-neutral-muted max-w-xl'>{t('county.acct.grade_description')}</p>
          </div>
        </div>
      </div>

      {/* A2. HOW THIS GRADE WAS CALCULATED */}
      {factors.length > 0 && (
        <div className='bg-white dark:bg-surface-base rounded-2xl border border-gray-100 dark:border-neutral-border overflow-hidden'>
          <div className='px-5 pt-5 pb-3 flex items-center gap-2'>
            <div className='h-5 w-1 rounded-full bg-gov-forest' />
            <h3 className='text-base font-semibold text-gray-900 dark:text-neutral-text'>
              {t('county.acct.how_calculated')}
            </h3>
          </div>
          <div className='px-5 pb-3 text-[12px] text-gray-500 dark:text-neutral-muted/80'>
            {t('county.acct.how_calc_intro')}
          </div>
          <div className='divide-y divide-gray-50'>
            {/* Score bar summary */}
            <div className='px-5 py-3'>
              <div className='flex items-center justify-between text-[11px] text-gray-500 dark:text-neutral-muted/80 mb-1.5'>
                <span className='font-semibold uppercase tracking-widest'>
                  {t('county.acct.score_label')}
                </span>
                <span className='tabular-nums font-semibold text-gray-800 dark:text-neutral-text'>
                  {score !== null ? `${score.toFixed(1)} / 100` : '—'}
                </span>
              </div>
              <div className='relative h-2 bg-gray-100 dark:bg-surface-elevated rounded-full overflow-hidden'>
                <div
                  className='absolute inset-y-0 left-0 rounded-full'
                  style={{
                    width: `${scorePct}%`,
                    backgroundColor: arcColor,
                    transition: 'width 0.8s ease-out',
                  }}
                />
                {/* Grade band markers */}
                {[40, 55, 70, 85].map((threshold) => (
                  <div
                    key={threshold}
                    className='absolute inset-y-0 w-px bg-white/80 dark:bg-surface-elevated'
                    style={{ left: `${threshold}%` }}
                  />
                ))}
              </div>
              <div className='flex justify-between text-[9px] text-gray-400 dark:text-neutral-muted/80 mt-1 tabular-nums'>
                <span>F</span>
                <span className='ml-[28%]'>D</span>
                <span className='ml-[10%]'>C</span>
                <span className='ml-[10%]'>B</span>
                <span className='ml-[10%]'>A</span>
              </div>
            </div>

            {factors.map((f, idx) => {
              const style = IMPACT_STYLE[f.impact] || IMPACT_STYLE.minor;
              const pts = typeof f.points === 'number' ? f.points : 0;
              return (
                <div
                  key={idx}
                  className='px-5 py-3 flex items-start gap-3 hover:bg-gray-50/60 dark:bg-surface-elevated/70 transition-colors'>
                  <div
                    className={`mt-1.5 h-2 w-2 rounded-full flex-shrink-0 ${style.dot}`}
                    aria-hidden
                  />
                  <div className='flex-1 min-w-0'>
                    <div className='flex items-center justify-between gap-2 mb-0.5'>
                      <span className='text-sm font-semibold text-gray-800 dark:text-neutral-text'>{f.label}</span>
                      <span
                        className={`text-xs font-bold tabular-nums px-2 py-0.5 rounded-md border ${
                          pts < 0
                            ? 'text-rose-700 bg-rose-50 border-rose-200'
                            : pts > 0
                              ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                              : 'text-gray-600 dark:text-neutral-muted bg-gray-50 dark:bg-surface-elevated border-gray-200 dark:border-neutral-border'
                        }`}>
                        {pts > 0 ? `+${pts}` : pts} {t('county.acct.pt_suffix')}
                      </span>
                    </div>
                    <div className='flex items-center gap-2'>
                      <span
                        className={`inline-block text-[10px] uppercase tracking-widest font-semibold px-1.5 py-0.5 rounded border ${style.chip}`}>
                        {t(style.labelKey)}
                      </span>
                      <span className='text-xs text-gray-500 dark:text-neutral-muted/80'>{f.detail}</span>
                    </div>
                  </div>
                </div>
              );
            })}
            {factors.length === 0 && (
              <div className='px-5 py-6 text-center text-sm text-gray-500 dark:text-neutral-muted/80'>
                {t('county.acct.no_penalties')}
              </div>
            )}
          </div>
          <div className='px-5 py-3 bg-gray-50/60 dark:bg-surface-elevated/70 border-t border-gray-100 dark:border-neutral-border text-[11px] text-gray-500 dark:text-neutral-muted/80 flex items-start gap-2'>
            <Info size={12} className='mt-0.5 flex-shrink-0 text-gray-400 dark:text-neutral-muted/80' />
            <span>{t('county.acct.calc_footnote')}</span>
          </div>
        </div>
      )}

      {/* C. KEY METRICS — stat strip with colour accent */}
      <div className='grid grid-cols-2 sm:grid-cols-4 gap-3'>
        {[
          {
            value:
              data.total_flagged_amount > 0 ? fmtKES(data.total_flagged_amount) : 'KES 0',
            label: t('county.acct.kpi.total_flagged'),
            sub:
              typeof data.flagged_pct_of_budget === 'number' && data.flagged_pct_of_budget > 0
                ? `${data.flagged_pct_of_budget.toFixed(1)}% ${t('county.acct.kpi.pct_of_budget')}`
                : undefined,
            Icon: FileWarning,
            tone: 'rose' as const,
          },
          {
            value: String(data.total_findings ?? 0),
            label: t('county.acct.kpi.audit_findings'),
            sub:
              typeof data.critical_findings === 'number' &&
              typeof data.warning_findings === 'number'
                ? `${data.critical_findings} ${t('county.acct.kpi.critical_lower')} · ${data.warning_findings} ${t('county.acct.kpi.warning_lower')}`
                : undefined,
            Icon: AlertTriangle,
            tone: 'amber' as const,
          },
          {
            value: String(data.unresolved_findings_count),
            label: t('county.acct.kpi.unresolved'),
            sub: `${data.recurring_findings_count} ${t('county.acct.kpi.recurring')}`,
            Icon: Clock,
            tone: 'orange' as const,
          },
          {
            value:
              data.absorption_rate !== null
                ? `${(data.absorption_rate * 100).toFixed(1)}%`
                : t('county.overview.kpi.na'),
            label: t('county.acct.kpi.absorption_rate'),
            sub: data.absorption_rate !== null ? t('county.acct.kpi.absorption_sub') : undefined,
            Icon: TrendingUp,
            tone: 'blue' as const,
          },
        ].map((m) => {
          const toneCls = {
            rose: 'border-l-rose-400 text-rose-700',
            amber: 'border-l-amber-400 text-amber-700',
            orange: 'border-l-orange-400 text-orange-700',
            blue: 'border-l-blue-400 text-blue-700',
          }[m.tone];
          return (
            <div
              key={m.label}
              className={`bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border border-l-4 ${toneCls} p-4`}>
              <div className='flex items-center gap-2 mb-1'>
                <m.Icon size={14} />
                <div className='text-[10px] uppercase tracking-widest font-semibold text-gray-400 dark:text-neutral-muted/80'>
                  {m.label}
                </div>
              </div>
              <div className='text-xl font-bold tabular-nums text-gray-900 dark:text-neutral-text'>{m.value}</div>
              {m.sub && <div className='text-[10px] text-gray-500 dark:text-neutral-muted/80 mt-0.5'>{m.sub}</div>}
            </div>
          );
        })}
      </div>

      {/* B. AUDIT OPINION HISTORY */}
      {data.audit_opinion_history.length > 0 && (
        <div className='bg-white dark:bg-surface-base rounded-xl border border-gray-100 dark:border-neutral-border p-5'>
          <h3 className='text-sm font-semibold text-gray-800 dark:text-neutral-text mb-4'>
            {t('county.acct.opinion_history')}
          </h3>
          <div className='overflow-x-auto'>
            <table className='w-full border-collapse'>
              <thead>
                <tr className='border-b border-gray-100 dark:border-neutral-border'>
                  <th className='text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 py-2 px-3'>
                    {t('county.acct.table.year')}
                  </th>
                  <th className='text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 py-2 px-3'>
                    {t('county.acct.table.opinion')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {[...data.audit_opinion_history]
                  .sort((a, b) => b.year - a.year)
                  .map((entry) => {
                    const opinionCls = OPINION_COLOR[entry.opinion] || 'bg-gray-200 dark:bg-surface-sunken text-gray-700 dark:text-neutral-muted';
                    const opinionKey = OPINION_KEY[entry.opinion];
                    return (
                      <tr key={entry.year} className='border-b border-gray-50 dark:border-neutral-border last:border-0'>
                        <td className='py-2.5 px-3 text-sm text-gray-700 dark:text-neutral-muted tabular-nums font-medium'>
                          {t('county.audit.fy_prefix')} {entry.year}/
                          {(entry.year + 1).toString().slice(-2)}
                        </td>
                        <td className='py-2.5 px-3'>
                          <span
                            className={`inline-block text-xs font-semibold px-2.5 py-1 rounded-full ${opinionCls}`}>
                            {opinionKey ? t(opinionKey) : entry.opinion}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* D. PEER COMPARISON — side-by-side with better visual cues */}
      <div>
        <div className='flex items-center gap-2 mb-3'>
          <div className='h-5 w-1 rounded-full bg-gov-forest' />
          <h3 className='text-base font-semibold text-gray-900 dark:text-neutral-text'>{t('county.acct.peer.title')}</h3>
        </div>
        <div className='grid grid-cols-1 sm:grid-cols-2 gap-4'>
          {/* vs Region */}
          <div
            className={`rounded-2xl border p-5 ${
              isBelowRegion
                ? 'bg-gradient-to-br from-rose-50/60 to-white border-rose-100'
                : 'bg-gradient-to-br from-emerald-50/60 to-white border-emerald-100'
            }`}>
            <div className='text-[11px] font-semibold text-gray-500 dark:text-neutral-muted/80 uppercase tracking-widest mb-3'>
              {t('county.acct.peer.vs_region').replace(
                '{region}',
                peer.region
                  ? peer.region.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
                  : t('county.acct.peer.region_fallback')
              )}
            </div>
            <div className='flex items-center gap-2 mb-3'>
              {isBelowRegion ? (
                <ArrowUp size={20} className='text-rose-500' />
              ) : (
                <ArrowDown size={20} className='text-emerald-500' />
              )}
              <span
                className={`text-lg font-bold ${isBelowRegion ? 'text-rose-700' : 'text-emerald-700'}`}>
                {isBelowRegion ? t('county.acct.peer.above') : t('county.acct.peer.below')}
              </span>
            </div>
            <div className='space-y-1 text-sm'>
              <div className='flex justify-between'>
                <span className='text-gray-500 dark:text-neutral-muted/80'>{t('county.acct.peer.this_county')}</span>
                <span className='font-semibold text-gray-800 dark:text-neutral-text tabular-nums'>
                  {fmtKES(data.total_flagged_amount)}
                </span>
              </div>
              <div className='flex justify-between'>
                <span className='text-gray-500 dark:text-neutral-muted/80'>{t('county.acct.peer.region_avg')}</span>
                <span className='font-semibold text-gray-800 dark:text-neutral-text tabular-nums'>
                  {fmtKES(peer.region_avg_flagged_amount)}
                </span>
              </div>
              {peer.region_avg_grade && (
                <div className='flex justify-between'>
                  <span className='text-gray-500 dark:text-neutral-muted/80'>{t('county.acct.peer.region_avg_grade')}</span>
                  <span className='font-semibold text-gray-800 dark:text-neutral-text'>{peer.region_avg_grade}</span>
                </div>
              )}
            </div>
          </div>

          {/* vs Population Bracket */}
          <div
            className={`rounded-2xl border p-5 ${
              isBelowBracket
                ? 'bg-gradient-to-br from-rose-50/60 to-white border-rose-100'
                : 'bg-gradient-to-br from-emerald-50/60 to-white border-emerald-100'
            }`}>
            <div className='text-[11px] font-semibold text-gray-500 dark:text-neutral-muted/80 uppercase tracking-widest mb-3'>
              {t('county.acct.peer.vs_bracket').replace(
                '{bracket}',
                peer.population_bracket || t('county.acct.peer.bracket_fallback')
              )}
            </div>
            <div className='flex items-center gap-2 mb-3'>
              {isBelowBracket ? (
                <ArrowUp size={20} className='text-rose-500' />
              ) : (
                <ArrowDown size={20} className='text-emerald-500' />
              )}
              <span
                className={`text-lg font-bold ${isBelowBracket ? 'text-rose-700' : 'text-emerald-700'}`}>
                {isBelowBracket
                  ? t('county.acct.peer.above_bracket')
                  : t('county.acct.peer.below_bracket')}
              </span>
            </div>
            <div className='space-y-1 text-sm'>
              <div className='flex justify-between'>
                <span className='text-gray-500 dark:text-neutral-muted/80'>{t('county.acct.peer.this_county')}</span>
                <span className='font-semibold text-gray-800 dark:text-neutral-text tabular-nums'>
                  {fmtKES(data.total_flagged_amount)}
                </span>
              </div>
              <div className='flex justify-between'>
                <span className='text-gray-500 dark:text-neutral-muted/80'>{t('county.acct.peer.bracket_avg')}</span>
                <span className='font-semibold text-gray-800 dark:text-neutral-text tabular-nums'>
                  {fmtKES(peer.population_bracket_avg)}
                </span>
              </div>
            </div>
          </div>
        </div>
        <p className='text-[11px] text-gray-400 dark:text-neutral-muted/80 mt-3 italic'>
          {t('county.acct.peer.footer_note')}
        </p>
      </div>
    </div>
  );
}
