'use client';

import { DebtTimelineEntry } from '@/lib/api/debt';
import { useLang } from '@/lib/i18n/LangProvider';
import {
  useBroaderDebt,
  useDebtTimeline,
  useNationalDebtOverview,
} from '@/lib/react-query/useDebt';
import Link from 'next/link';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { motion } from 'framer-motion';
import { Skeleton } from '@/components/ui/Skeleton';
import { AlertTriangle, Landmark, Loader2, TrendingUp } from 'lucide-react';
import dynamic from 'next/dynamic';
import { useMemo } from 'react';
import InfoTip from '@/components/InfoTip';
import type { ChartEntry } from './NationalDebtChart';

// The recharts timeline loads as its own async chunk so ~180KB of chart
// library stays out of the homepage's hydration bundle (recharts was a
// measurable INP/FID contributor on low-end mobile). The fallback keeps
// the exact chart-box height so the swap causes no layout shift.
const NationalDebtChart = dynamic(() => import('./NationalDebtChart'), {
  ssr: false,
  loading: () => <Skeleton className='w-full h-full rounded-xl' />,
});

/* ── Transform API data to chart format ── */
function toChartData(timeline: DebtTimelineEntry[]): ChartEntry[] {
  return timeline.map((e) => ({
    year: String(e.year),
    external: e.external, // already in billions from API
    domestic: e.domestic, // already in billions from API
    total: e.total, // already in billions from API
    gdpRatio: e.gdp_ratio,
  }));
}

function fmtKES(val: number): string {
  if (val >= 1_000_000_000_000)
    return `KES ${(val / 1_000_000_000_000).toFixed(2)}T`;
  if (val >= 1_000_000_000) return `KES ${(val / 1_000_000_000).toFixed(0)}B`;
  return `KES ${val.toLocaleString()}`;
}

export default function NationalDebtCard() {
  const { t } = useLang();
  const { data: resp, isLoading } = useNationalDebtOverview();
  const { data: timelineResp, isLoading: isTimelineLoading } = useDebtTimeline();
  const { data: fiscal } = useFiscalSummary();

  // Transform API timeline → chart data (memoised)
  const debtTimeline = useMemo<ChartEntry[]>(() => {
    if (!timelineResp?.timeline?.length) return [];
    return toChartData(timelineResp.timeline);
  }, [timelineResp]);

  // Extract live values from API, fallback to latest timeline entry
  const apiData = resp?.data || resp;
  const sustainability = apiData?.debt_sustainability || {};
  const riskLevel = sustainability.risk_level || 'High';
  const debtServiceRatio =
    fiscal?.current?.debt_service_per_shilling ?? sustainability.debt_service_ratio ?? null;

  const firstYear = debtTimeline[0];
  const lastYear = debtTimeline[debtTimeline.length - 1];

  // Derive headline numbers from the authoritative /debt/national endpoint
  // (loans-table sum — same source /debt page uses) so home and the debt
  // detail page agree. Fall back to the last timeline year only if the
  // authoritative value is missing — and to NULL (not 0) when both are
  // missing: a transparency site rendering "KES 0" national debt during
  // a backend outage is misinformation, so missing values render as "—"
  // with an explicit unavailable notice instead.
  const totalDebt =
    apiData?.total_outstanding ?? apiData?.total_debt ?? (lastYear ? lastYear.total * 1_000_000_000 : null);
  const gdpRatio = apiData?.debt_to_gdp_ratio ?? lastYear?.gdpRatio ?? null;
  const externalDebt =
    apiData?.summary?.external_debt ?? (lastYear ? lastYear.external * 1_000_000_000 : null);
  const domesticDebt =
    apiData?.summary?.domestic_debt ?? (lastYear ? lastYear.domestic * 1_000_000_000 : null);
  const debtDataMissing = !isLoading && !isTimelineLoading && totalDebt == null;
  // External vs domestic split — shares of (external + domestic) so the two
  // always sum to exactly 100%. Rounding each independently off the total
  // previously produced 100.2% (51.5% + 48.7%).
  const splitBase = (externalDebt ?? 0) + (domesticDebt ?? 0);
  const externalPct = splitBase > 0 ? +((externalDebt / splitBase) * 100).toFixed(1) : 0;
  const domesticPct = splitBase > 0 ? +(100 - externalPct).toFixed(1) : 0;

  // IMF's "General Government Gross Debt" — the broader figure that
  // includes counties, SOEs, pending bills + arrears. Shown here as a
  // one-line callout so the homepage acknowledges the gap; the full
  // dual-card + explainer lives on /debt.
  const { data: broader } = useBroaderDebt();
  const imfKes = broader?.status === 'success' ? broader.latest?.value_kes ?? null : null;
  const imfPct = broader?.status === 'success' ? broader.latest?.debt_to_gdp ?? null : null;

  const growthMultiple =
    firstYear && lastYear ? (lastYear.total / firstYear.total).toFixed(1) : '—';
  const yearRange = firstYear && lastYear ? `${firstYear.year}–${lastYear.year}` : '—';
  const hasTimeline = debtTimeline.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.6, delay: 0.1 }}
      className='glass-card overflow-hidden h-full flex flex-col'>
      {/* Header */}
      <div className='bg-gradient-to-r from-gov-copper/[0.06] via-gov-sand/30 to-transparent dark:from-surface-elevated/40 dark:via-surface-base/20 dark:to-transparent px-6 sm:px-8 pt-5 pb-4 border-b border-neutral-border/20'>
        <div className='flex items-start justify-between'>
          <div>
            <h2 className='font-display text-xl sm:text-2xl text-gov-dark dark:text-white mb-1'>
              {t('home.debt.title')}
            </h2>
            <p className='text-xs text-neutral-muted'>
              {t('home.debt.source_note').replace('{range}', yearRange)}
            </p>
          </div>
          {isLoading || isTimelineLoading ? (
            <Loader2 className='w-4 h-4 animate-spin text-neutral-muted/40 mt-1' />
          ) : null}
        </div>
      </div>

      {/* Data unavailable — shown instead of misleading zeros when neither
          the national-debt endpoint nor the timeline returned data. */}
      {debtDataMissing && (
        <div className='mx-6 sm:mx-8 mt-3 flex items-start gap-2 rounded-lg border border-amber-300/50 bg-amber-50/70 dark:bg-amber-500/10 px-3 py-2'>
          <AlertTriangle className='w-3.5 h-3.5 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0' />
          <p className='text-[11px] leading-snug text-amber-800 dark:text-amber-200'>
            Live debt figures are temporarily unavailable. Values below show “—” rather than a
            misleading zero — please refresh in a moment.
          </p>
        </div>
      )}

      {/* Reconciliation divergence — surfaced on home too (audit §2.1/§4), not
          just /debt. Renders only when the two debt sources disagree materially. */}
      {apiData?.reconciliation?.status === 'divergent' && (
        <div className='mx-6 sm:mx-8 mt-3 flex items-start gap-2 rounded-lg border border-amber-300/50 bg-amber-50/70 dark:bg-amber-500/10 px-3 py-2'>
          <AlertTriangle className='w-3.5 h-3.5 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0' />
          <p className='text-[11px] leading-snug text-amber-800 dark:text-amber-200'>
            Sources differ by{' '}
            {Math.abs(Number(apiData.reconciliation.percent_diff) || 0).toFixed(1)}% —{' '}
            {apiData.reconciliation.primary_source} vs {apiData.reconciliation.secondary_source}.{' '}
            <Link href='/debt' className='font-semibold underline hover:no-underline'>
              See the audit trail
            </Link>
            .
          </p>
        </div>
      )}

      {/* Stat cards row */}
      <div className='px-6 sm:px-8 pt-5 pb-2'>
        <div className='grid grid-cols-2 sm:grid-cols-4 gap-3'>
          <StatCard
            icon={<Landmark className='w-3.5 h-3.5 text-gov-copper opacity-70' />}
            label={t('home.debt.total_public')}
            value={totalDebt != null ? fmtKES(totalDebt) : '—'}
            sub={t('home.debt.growth_sub')
              .replace('{x}', String(growthMultiple))
              .replace('{year}', String(firstYear?.year || '—'))}
            accent='copper'
          />
          <StatCard
            icon={<TrendingUp className='w-3.5 h-3.5 text-gov-gold opacity-70' />}
            label={
              <div className='flex items-center gap-1'>
                <span>{t('home.debt.tooltip_gdp')}</span>
                <InfoTip term='debt-to-gdp' size={11} />
              </div>
            }
            value={gdpRatio != null ? `${gdpRatio}%` : '—'}
            sub={t('home.debt.from_year_sub')
              .replace('{pct}', String(firstYear?.gdpRatio ?? '—'))
              .replace('{year}', String(firstYear?.year || '—'))}
            accent='gold'
          />
          <StatCard
            icon={
              <span className='text-xs' suppressHydrationWarning>
                🏦
              </span>
            }
            label={
              <div className='flex items-center gap-1'>
                <span>{t('home.debt.external_label')}</span>
                <InfoTip term='external-debt' size={11} />
              </div>
            }
            value={externalDebt != null ? fmtKES(externalDebt) : '—'}
            sub={t('home.debt.pct_of_total').replace('{pct}', String(externalPct))}
            accent='forest'
          />
          <StatCard
            icon={
              <span className='text-xs' suppressHydrationWarning>
                🇰🇪
              </span>
            }
            label={
              <div className='flex items-center gap-1'>
                <span>{t('home.debt.domestic_label')}</span>
                <InfoTip term='domestic-debt' size={11} />
              </div>
            }
            value={domesticDebt != null ? fmtKES(domesticDebt) : '—'}
            sub={t('home.debt.pct_of_total').replace('{pct}', String(domesticPct))}
            accent='sage'
          />
        </div>

        {/* Broader measure (IMF) callout — one-line, subtle, with a
            link to the full dual-card + explainer on /debt. Hidden when
            the seeder has not produced data yet so we never show a
            misleading zero. */}
        {imfKes != null && (
          <Link
            href='/debt#broader'
            className='mt-3 block rounded-lg bg-gov-gold/[0.08] border border-gov-gold/25 px-3 py-2 text-[12px] text-gov-dark/85 dark:text-white/85 hover:bg-gov-gold/[0.14] transition-colors'>
            <span className='font-semibold text-gov-dark dark:text-white'>IMF broader measure:</span>{' '}
            KES {(imfKes / 1e12).toFixed(2)}T
            {imfPct != null && ` (${imfPct.toFixed(1)}% GDP)`} — includes counties,
            SOEs, pending bills
            <span className='text-gov-forest dark:text-emerald-100 ml-1 font-medium'>→ why the gap</span>
          </Link>
        )}
      </div>

      {/* Chart */}
      <div className='px-4 sm:px-6 pt-3 pb-2 flex-1 min-h-0'>
        {isTimelineLoading ? (
          <div className='h-64 sm:h-72 flex flex-col justify-end gap-2 px-2'>
            <div className='flex items-end gap-1 h-full'>
              {[68, 45, 72, 38, 55, 82, 60, 50].map((h, i) => (
                <Skeleton
                  key={i}
                  className='flex-1 rounded-t-sm'
                  style={{ height: `${h}%` }}
                />
              ))}
            </div>
            <Skeleton className='h-2 w-full' />
          </div>
        ) : !hasTimeline ? (
          <div className='h-64 sm:h-72 flex items-center justify-center text-neutral-muted text-sm'>
            {t('home.debt.no_timeline')}
          </div>
        ) : (
          <>
            <div className='h-64 sm:h-72'>
              <NationalDebtChart data={debtTimeline} />
            </div>

            {/* Legend */}
            <div className='flex items-center justify-center gap-5 mt-2'>
              <span className='flex items-center gap-1.5 text-[10px] text-neutral-muted'>
                <span
                  className='w-3 h-2 rounded-sm'
                  style={{ background: '#0D7377', opacity: 0.5 }}
                />{' '}
                {t('home.debt.legend_domestic')}
              </span>
              <span className='flex items-center gap-1.5 text-[10px] text-neutral-muted'>
                <span className='w-3 h-2 rounded-sm bg-gov-copper/50' /> {t('home.debt.legend_external')}
              </span>
              <span className='flex items-center gap-1.5 text-[10px] text-neutral-muted'>
                <span className='w-5 h-0 border-t-2 border-dashed border-gov-gold' /> {t('home.debt.legend_gdp')}
              </span>
            </div>
          </>
        )}
      </div>

      {/* Bottom insights bar */}
      <div className='px-6 sm:px-8 py-4 mt-auto border-t border-neutral-border/30 bg-gradient-to-r from-gov-sand/20 via-transparent to-transparent'>
        <div className='grid grid-cols-1 sm:grid-cols-3 gap-4'>
          <InsightPill
            icon='🇰🇪'
            title={t('home.debt.cents_of_revenue').replace('{n}', String(debtServiceRatio ?? '—'))}
            desc={t('home.debt.insight_service')}
          />
          <InsightPill
            icon='📊'
            title={splitBase > 0 ? `${domesticPct}% / ${externalPct}%` : '— / —'}
            desc={t('home.debt.insight_split')}
          />
          <InsightPill
            icon={<AlertTriangle className='w-4 h-4 text-gov-copper' />}
            title={t('home.debt.insight_risk_label').replace('{level}', riskLevel)}
            desc={t('home.debt.insight_risk_desc')}
            highlight
          />
        </div>
      </div>
    </motion.div>
  );
}

/* ── Sub-components ── */

function StatCard({
  icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: React.ReactNode;
  label: React.ReactNode;
  value: string;
  sub: string;
  accent: string;
}) {
  const bgMap: Record<string, string> = {
    copper: 'bg-gov-copper/[0.04]',
    gold: 'bg-gov-gold/[0.05]',
    forest: 'bg-gov-forest/[0.04]',
    sage: 'bg-gov-sage/[0.06]',
  };
  const textMap: Record<string, string> = {
    copper: 'text-gov-copper',
    gold: 'text-gov-gold',
    forest: 'text-gov-forest dark:text-emerald-100',
    sage: 'text-gov-sage',
  };
  return (
    <div
      className={`rounded-xl ${bgMap[accent] || bgMap.copper} border border-neutral-border/30 px-3 py-2.5`}>
      <div className='flex items-center gap-1.5 mb-1'>
        {icon}
        <span className='text-[9px] text-neutral-muted font-medium uppercase tracking-wider leading-none'>
          {label}
        </span>
      </div>
      <span
        className={`text-sm font-bold ${textMap[accent] || textMap.copper} tabular-nums leading-none block`}>
        {value}
      </span>
      <span className='text-[10px] text-neutral-muted mt-0.5 block'>{sub}</span>
    </div>
  );
}

function InsightPill({
  icon,
  title,
  desc,
  highlight,
}: {
  icon: React.ReactNode;
  title: string;
  desc: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`flex items-start gap-2.5 ${highlight ? 'bg-gov-copper/[0.04] rounded-lg px-2.5 py-1.5 -mx-1' : ''}`}>
      <span className='text-base mt-0.5 flex-shrink-0' suppressHydrationWarning>
        {typeof icon === 'string' ? icon : icon}
      </span>
      <div>
        <span
          className={`text-xs font-semibold block ${highlight ? 'text-gov-copper' : 'text-gov-dark dark:text-white'}`}>
          {title}
        </span>
        <span className='text-[10px] text-neutral-muted leading-tight'>{desc}</span>
      </div>
    </div>
  );
}
