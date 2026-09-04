'use client';

import { DebtTimelineEntry } from '@/lib/api/debt';
import { classifyDebtRisk, toRawKES } from '@/lib/utils';
import { useLang } from '@/lib/i18n/LangProvider';
import {
  useDebtTimeline,
  useNationalDebtOverview,
} from '@/lib/react-query/useDebt';
import Link from 'next/link';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { motion } from 'framer-motion';
import { Skeleton, SkeletonChart } from '@/components/ui/Skeleton';
import { AlertTriangle, BarChart3, Globe2, Landmark, Loader2, MapPinned, TrendingUp } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import InfoTip from '@/components/InfoTip';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

/* ── Transform API data to chart format ── */
interface ChartEntry {
  year: string;
  external: number;
  domestic: number;
  total: number;
  gdpRatio: number;
  /** True when this year's figures are round-number estimates rather than a
   *  reading off a published table. See `isRoundNumberEstimate`. */
  modelled: boolean;
}

/**
 * Is this year's debt row a round-number estimate rather than a published
 * reading?
 *
 * The 2013–2021 rows in `debt_timeline` are round hundreds of billions — 3,100
 * / 3,600 / 4,300 / 5,000 / 5,400 / 5,800 / 6,500 / 7,200 / 8,200 — across
 * external, domestic and total simultaneously. No CBK table produces that.
 * Only 2022 onward carry real precision, from the CBK Statistical Bulletin
 * figures applied by the 2026-08-29 correction. The homepage was deriving
 * "4.0× since 2013" and "From 58.4% in 2013" off the invented 2013 base
 * (credibility audit F13).
 *
 * Detected from the data rather than hardcoding a cutoff year, so a row stops
 * being flagged the moment it is re-sourced with real digits — and so nobody
 * has to remember to move a constant. Requiring ALL THREE components to land
 * exactly on 100B makes a false positive on genuine data vanishingly unlikely.
 */
export function isRoundNumberEstimate(e: {
  external: number;
  domestic: number;
  total: number;
}): boolean {
  const STEP_B = 100; // values here are billions
  const exact = (v: number) => v > 0 && Math.abs(v % STEP_B) < 1e-6;
  return exact(e.external) && exact(e.domestic) && exact(e.total);
}

/**
 * ChartEntry money fields are BILLIONS — `NationalDebtChart`'s `fmtT` divides
 * by 1000 for trillions and its tick formatter renders bare values as `${v}B`.
 *
 * The rows arriving here are not. Since the stage1 3a migration /debt/timeline
 * serves raw KES and declares it per row with `unit: "KES"`; a pre-migration
 * backend serves bare billions with no unit field. This previously passed both
 * through with the comment "already in billions from API", which was true
 * until the migration and 10⁹× wrong after it.
 *
 * So: normalise to raw KES on the DECLARED unit — never by guessing a value's
 * magnitude — then convert once to the billions the chart reads. Doing it here
 * also fixes the headline fallbacks below, which read `lastYear` and are
 * correct precisely when this function's output really is billions.
 *
 * Reported as F1 on PR #136, and confirmed the hard way: this migration was
 * applied to production on 2026-08-30 and rolled back within the hour.
 */
function toChartData(timeline: DebtTimelineEntry[]): ChartEntry[] {
  const toBillions = (v: number, unit?: string | null): number => {
    const raw = toRawKES(v, unit);
    return raw == null ? 0 : raw / 1e9;
  };
  return timeline.map((e) => {
    const row = {
      year: String(e.year),
      external: toBillions(e.external, e.unit),
      domestic: toBillions(e.domestic, e.unit),
      total: toBillions(e.total, e.unit),
      gdpRatio: e.gdp_ratio,
    };
    return { ...row, modelled: isRoundNumberEstimate(row) };
  });
}

// 2-decimal precision for trillion-scale values. Matches both
// ``HeroSection.tsx`` (the page-top "Total Debt as of YYYY" KPI) and
// ``DebtPageClient.tsx``'s shared formatter — pre-fix this card was
// the lone outlier at ``toFixed(1)``, so a value of 12.66T on the
// hero displayed as "12.7T" here, plus the External + Domestic
// breakdown ("6.5T + 6.2T") didn't add back up to the displayed
// "12.7T" total. 2 decimals reconciles all three.
function fmtT(val: number): string {
  if (val >= 1000) return `${(val / 1000).toFixed(2)}T`;
  return `${val}B`;
}

/** `val` is typed nullable on purpose: the values flowing in derive from an
 *  `any`-typed API response, so TypeScript cannot catch an unguarded call —
 *  and did not. The CI production build did, prerendering `/` with no backend:
 *  `Cannot read properties of null (reading 'toLocaleString')`. */
function fmtKES(val: number | null | undefined): string {
  if (val == null) return '—';
  if (val >= 1_000_000_000_000)
    return `KES ${(val / 1_000_000_000_000).toFixed(2)}T`;
  if (val >= 1_000_000_000) return `KES ${(val / 1_000_000_000).toFixed(0)}B`;
  return `KES ${val.toLocaleString()}`;
}

function CustomTooltip({ active, payload, label }: any) {
  const { t } = useLang();
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div className='rounded-sm bg-surface-elevated border border-neutral-border shadow-elevated px-4 py-3 text-xs'>
      <p className='font-display text-sm text-gov-dark dark:text-white mb-2'>{label}</p>
      <div className='space-y-1.5'>
        <div className='flex justify-between gap-6'>
          <span className='text-neutral-muted'>{t('home.debt.tooltip_total')}</span>
          <span className='font-bold text-gov-dark dark:text-white tabular-nums'>{fmtT(d.total)}</span>
        </div>
        <div className='flex justify-between gap-6'>
          <span className='flex items-center gap-1.5'>
            <span className='w-2.5 h-2.5 rounded-full bg-gov-copper/80' />
            {t('home.debt.external')}
          </span>
          <span className='font-semibold text-gov-dark dark:text-white tabular-nums'>{fmtT(d.external)}</span>
        </div>
        <div className='flex justify-between gap-6'>
          <span className='flex items-center gap-1.5'>
            <span className='w-2.5 h-2.5 rounded-full' style={{ background: '#0D7377' }} />
            {t('home.debt.domestic')}
          </span>
          <span className='font-semibold text-gov-dark dark:text-white tabular-nums'>{fmtT(d.domestic)}</span>
        </div>
        <div className='flex justify-between gap-6 pt-1 border-t border-neutral-border/30'>
          <span className='text-neutral-muted'>{t('home.debt.tooltip_gdp')}</span>
          <span className='font-bold text-gov-gold tabular-nums'>{d.gdpRatio}%</span>
        </div>
      </div>
    </div>
  );
}

function useIsMobile(breakpoint = 640) {
  const [mobile, setMobile] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${breakpoint}px)`);
    setMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setMobile(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [breakpoint]);
  return mobile;
}

export default function NationalDebtCard() {
  const { t } = useLang();
  const isMobile = useIsMobile();
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
  const debtServiceRatio =
    fiscal?.current?.debt_service_per_shilling ?? sustainability.debt_service_ratio ?? null;

  const firstYear = debtTimeline[0];
  const lastYear = debtTimeline[debtTimeline.length - 1];

  // Derive headline numbers from the authoritative /debt/national endpoint
  // (loans-table sum — same source /debt page uses) so home and the debt
  // detail page agree. Fall back to the last timeline year only if the
  // authoritative value is missing.
  const totalDebt =
    apiData?.total_outstanding ?? apiData?.total_debt ?? (lastYear ? lastYear.total * 1_000_000_000 : null);
  const gdpRatio = apiData?.debt_to_gdp_ratio ?? lastYear?.gdpRatio ?? null;

  // Absence is not a risk band. This was `|| 'High'`, so an API that reported
  // no assessment rendered the WORST rating — a claim about the public
  // finances manufactured from a missing field. Reported as G3 on PR #135,
  // alongside the same defect in `classifyDebtRisk`, which now returns null
  // rather than a default so callers must handle absence explicitly.
  //
  // Order: the publisher's own assessment, else one derived from the
  // debt-to-GDP ratio, else nothing.
  const riskLevel: 'Low' | 'Moderate' | 'High' | null =
    sustainability.risk_level ?? classifyDebtRisk(gdpRatio);
  const externalDebt =
    apiData?.summary?.external_debt ?? (lastYear ? lastYear.external * 1_000_000_000 : null);
  const domesticDebt =
    apiData?.summary?.domestic_debt ?? (lastYear ? lastYear.domestic * 1_000_000_000 : null);
  // External vs domestic split — shares of (external + domestic) so the two
  // always sum to exactly 100%. Rounding each independently off the total
  // previously produced 100.2% (51.5% + 48.7%).
  //
  // The split only exists when BOTH sides are known. With one side missing it
  // used to fall back to 0, which rendered "0% of total" and a "0% / 0%"
  // split beside an em-dash value — a fabricated statistic presented with the
  // same confidence as a real one. Absent inputs now yield null and every
  // consumer renders "—".
  const splitAvailable =
    externalDebt != null && domesticDebt != null && externalDebt + domesticDebt > 0;
  const splitBase = (externalDebt ?? 0) + (domesticDebt ?? 0);
  const externalPct = splitAvailable
    ? +(((externalDebt ?? 0) / splitBase) * 100).toFixed(1)
    : null;
  const domesticPct = externalPct != null ? +(100 - externalPct).toFixed(1) : null;

  // Both derived claims must start from the earliest SOURCED year, not the
  // earliest year on the chart. Anchoring "4.0× since 2013" and "From 58.4% in
  // 2013" to a round-number estimate published a growth story built on an
  // invented base — and it understated the real rise (F13).
  const firstSourced = debtTimeline.find((e) => !e.modelled) ?? null;
  const modelledYears = debtTimeline.filter((e) => e.modelled);
  const growthMultiple =
    firstSourced && lastYear && firstSourced.total > 0
      ? (lastYear.total / firstSourced.total).toFixed(1)
      : '—';
  const growthBaseYear = firstSourced?.year ?? '—';
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
      <div className='bg-surface-sunken/45 px-6 sm:px-8 pt-5 pb-4 border-b border-neutral-border'>
        <div className='flex items-start justify-between'>
          <div>
            <h2 className='font-display text-xl sm:text-2xl text-gov-dark dark:text-white mb-1'>
              {t('home.debt.title')}
            </h2>
            <p className='text-xs text-neutral-muted'>
              {t('home.debt.source_note').replace('{range}', yearRange)}
            </p>
            {/* Say which years on this chart are not readings. Derived from the
                data, so the sentence shrinks and then disappears as years get
                re-sourced. */}
            {modelledYears.length > 0 && (
              <p className='mt-1 text-[11px] leading-snug text-neutral-muted/80'>
                {modelledYears[0].year}–{modelledYears[modelledYears.length - 1].year}{' '}
                are round-number estimates, not figures read off a published
                table. {firstSourced?.year ?? 'Later years'} onward come from the
                CBK Statistical Bulletin.
              </p>
            )}
          </div>
          {isLoading || isTimelineLoading ? (
            <Loader2 className='w-4 h-4 animate-spin text-neutral-muted/40 mt-1' />
          ) : null}
        </div>
      </div>

      {/* Reconciliation divergence — surfaced on home too (audit §2.1/§4), not
          just /debt. Renders only when the two debt sources disagree materially. */}
      {apiData?.reconciliation?.status === 'divergent' && (
        <div className='mx-6 sm:mx-8 mt-3 flex items-start gap-2 rounded-sm border border-amber-400/50 bg-amber-50/70 dark:bg-amber-500/10 px-3 py-2'>
          <AlertTriangle className='w-3.5 h-3.5 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0' />
          {/* `primary_source` / `secondary_source` are internal table names
              (`loans_table`, `debt_timeline_table`). They were being printed to
              the public. The divergence is worth telling the reader about; the
              schema is not. */}
          <p className='text-[11px] leading-snug text-amber-800 dark:text-amber-200'>
            Two official figures for this total differ by{' '}
            {Math.abs(Number(apiData.reconciliation.percent_diff) || 0).toFixed(1)}%
            and we cannot yet say which is right.{' '}
            <Link href='/debt' className='font-semibold underline hover:no-underline'>
              See both figures
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
              .replace('{year}', String(growthBaseYear))}
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
            value={`${gdpRatio}%`}
            sub={t('home.debt.from_year_sub')
              .replace('{pct}', String(firstSourced?.gdpRatio ?? '—'))
              .replace('{year}', String(growthBaseYear))}
            accent='gold'
          />
          <StatCard
            icon={<Globe2 className='w-3.5 h-3.5 text-gov-forest dark:text-emerald-100' />}
            label={
              <div className='flex items-center gap-1'>
                <span>{t('home.debt.external_label')}</span>
                <InfoTip term='external-debt' size={11} />
              </div>
            }
            value={externalDebt != null ? fmtKES(externalDebt) : '—'}
            sub={
              externalPct != null
                ? t('home.debt.pct_of_total').replace('{pct}', String(externalPct))
                : '—'
            }
            accent='forest'
          />
          <StatCard
            icon={<MapPinned className='w-3.5 h-3.5 text-gov-sage' />}
            label={
              <div className='flex items-center gap-1'>
                <span>{t('home.debt.domestic_label')}</span>
                <InfoTip term='domestic-debt' size={11} />
              </div>
            }
            value={domesticDebt != null ? fmtKES(domesticDebt) : '—'}
            sub={
              domesticPct != null
                ? t('home.debt.pct_of_total').replace('{pct}', String(domesticPct))
                : '\u2014'
            }
            accent='sage'
          />
        </div>

        {/* The "IMF broader measure … includes counties, SOEs, pending bills"
            callout was withdrawn (credibility audit F8). It described the IMF
            General-Government figure as BROADER than the headline while
            rendering it 1.26T SMALLER — a claim that refutes itself in the
            same sentence. The IMF series is still ingested and is a legitimate
            second measure; it needs a presentation that states which is larger
            and why, not one that asserts a composition the numbers contradict. */}
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
              <ResponsiveContainer width='100%' height='100%'>
                <ComposedChart
                  data={debtTimeline}
                  margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
                  <CartesianGrid strokeDasharray='3 3' stroke='#E2DDD5' vertical={false} />
                  <XAxis
                    dataKey='year'
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 11, fill: '#6B7280' }}
                    interval={isMobile ? 1 : 0}
                  />
                  <YAxis
                    yAxisId='debt'
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 11, fill: '#9CA3AF' }}
                    tickFormatter={(v: number) =>
                      v >= 1000 ? `${(v / 1000).toFixed(0)}T` : `${v}B`
                    }
                    width={40}
                  />
                  <YAxis
                    yAxisId='ratio'
                    orientation='right'
                    domain={[30, 85]}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 11, fill: '#D9A441' }}
                    tickFormatter={(v: number) => `${v}%`}
                    width={36}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  {/* Stacked areas: domestic on bottom, external on top */}
                  <Area
                    yAxisId='debt'
                    type='monotone'
                    dataKey='domestic'
                    stackId='stack'
                    stroke='#0D7377'
                    strokeWidth={1.5}
                    fill='#176B49'
                    fillOpacity={0.14}
                    name='Domestic'
                  />
                  <Area
                    yAxisId='debt'
                    type='monotone'
                    dataKey='external'
                    stackId='stack'
                    stroke='#C94A4A'
                    strokeWidth={1.5}
                    fill='#C9473D'
                    fillOpacity={0.12}
                    name='External'
                  />
                  {/* GDP ratio dashed line on right axis */}
                  <Line
                    yAxisId='ratio'
                    type='monotone'
                    dataKey='gdpRatio'
                    stroke='#D9A441'
                    strokeWidth={2.5}
                    strokeDasharray='6 3'
                    dot={{ r: 3.5, fill: '#D9A441', stroke: '#fff', strokeWidth: 2 }}
                    activeDot={{ r: 5, fill: '#D9A441', stroke: '#fff', strokeWidth: 2 }}
                    name='Debt-to-GDP'
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {/* Legend */}
            <div className='flex items-center justify-center gap-5 mt-2'>
              <span className='flex items-center gap-1.5 text-[11px] text-neutral-muted'>
                <span
                  className='w-3 h-2 rounded-sm'
                  style={{ background: '#0D7377', opacity: 0.5 }}
                />{' '}
                {t('home.debt.legend_domestic')}
              </span>
              <span className='flex items-center gap-1.5 text-[11px] text-neutral-muted'>
                <span className='w-3 h-2 rounded-sm bg-gov-copper/50' /> {t('home.debt.legend_external')}
              </span>
              <span className='flex items-center gap-1.5 text-[11px] text-neutral-muted'>
                <span className='w-5 h-0 border-t-2 border-dashed border-gov-gold' /> {t('home.debt.legend_gdp')}
              </span>
            </div>
          </>
        )}
      </div>

      {/* Bottom insights bar */}
      <div className='px-6 sm:px-8 py-4 mt-auto border-t border-neutral-border bg-surface-sunken/30'>
        <div className='grid grid-cols-1 sm:grid-cols-3 gap-4'>
          <InsightPill
            icon={<Landmark className='w-4 h-4 text-gov-sage' />}
            title={t('home.debt.cents_of_revenue').replace('{n}', String(debtServiceRatio ?? '\u2014'))}
            desc={t('home.debt.insight_service')}
          />
          <InsightPill
            icon={<BarChart3 className='w-4 h-4 text-gov-gold' />}
            title={
              domesticPct != null && externalPct != null
                ? `${domesticPct}% / ${externalPct}%`
                : '—'
            }
            desc={t('home.debt.insight_split')}
          />
          {/* A null band renders "not assessed" in neutral styling, and drops
              the `highlight` emphasis — the alarm treatment is for a stated
              risk, not for a missing reading. */}
          <InsightPill
            icon={
              <AlertTriangle
                className={`w-4 h-4 ${
                  riskLevel ? 'text-gov-copper' : 'text-neutral-muted'
                }`}
              />
            }
            title={
              riskLevel
                ? t('home.debt.insight_risk_label').replace('{level}', riskLevel)
                : t('home.debt.insight_risk_unassessed')
            }
            desc={
              riskLevel
                ? t('home.debt.insight_risk_desc')
                : t('home.debt.insight_risk_unassessed_desc')
            }
            highlight={riskLevel != null}
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
      className={`rounded-sm ${bgMap[accent] || bgMap.copper} border border-neutral-border/30 px-3 py-2.5`}>
      <div className='flex items-center gap-1.5 mb-1'>
        {icon}
        <span className='text-[11px] text-neutral-muted font-medium uppercase tracking-wider leading-none'>
          {label}
        </span>
      </div>
      <span
        className={`text-sm font-bold ${textMap[accent] || textMap.copper} tabular-nums leading-none block`}>
        {value}
      </span>
      <span className='text-[11px] text-neutral-muted mt-0.5 block'>{sub}</span>
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
      className={`flex items-start gap-2.5 ${highlight ? 'bg-gov-copper/[0.04] rounded-sm px-2.5 py-1.5 -mx-1' : ''}`}>
      <span className='text-base mt-0.5 flex-shrink-0' suppressHydrationWarning>
        {typeof icon === 'string' ? icon : icon}
      </span>
      <div>
        <span
          className={`text-xs font-semibold block ${highlight ? 'text-gov-copper' : 'text-gov-dark dark:text-white'}`}>
          {title}
        </span>
        <span className='text-[11px] text-neutral-muted leading-tight'>{desc}</span>
      </div>
    </div>
  );
}
