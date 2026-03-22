'use client';

import { DebtTimelineEntry } from '@/lib/api/debt';
import { useDebtTimeline, useNationalDebtOverview } from '@/lib/react-query/useDebt';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { motion } from 'framer-motion';
import { Skeleton, SkeletonChart } from '@/components/ui/Skeleton';
import { AlertTriangle, Landmark, Loader2, TrendingUp } from 'lucide-react';
import { useMemo } from 'react';
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
}

function toChartData(timeline: DebtTimelineEntry[]): ChartEntry[] {
  return timeline.map((e) => ({
    year: String(e.year),
    external: e.external, // already in billions from API
    domestic: e.domestic, // already in billions from API
    total: e.total, // already in billions from API
    gdpRatio: e.gdp_ratio,
  }));
}

function fmtT(val: number): string {
  if (val >= 1000) return `${(val / 1000).toFixed(1)}T`;
  return `${val}B`;
}

function fmtKES(val: number): string {
  if (val >= 1_000_000_000_000) return `KES ${(val / 1_000_000_000_000).toFixed(1)}T`;
  if (val >= 1_000_000_000) return `KES ${(val / 1_000_000_000).toFixed(0)}B`;
  return `KES ${val.toLocaleString()}`;
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div className='rounded-xl bg-white/95 backdrop-blur-lg border border-neutral-border/40 shadow-elevated px-4 py-3 text-xs'>
      <p className='font-display text-sm text-gov-dark mb-2'>{label}</p>
      <div className='space-y-1.5'>
        <div className='flex justify-between gap-6'>
          <span className='text-neutral-muted'>Total Debt</span>
          <span className='font-bold text-gov-dark tabular-nums'>{fmtT(d.total)}</span>
        </div>
        <div className='flex justify-between gap-6'>
          <span className='flex items-center gap-1.5'>
            <span className='w-2.5 h-2.5 rounded-full bg-gov-copper/80' />
            External
          </span>
          <span className='font-semibold text-gov-dark tabular-nums'>{fmtT(d.external)}</span>
        </div>
        <div className='flex justify-between gap-6'>
          <span className='flex items-center gap-1.5'>
            <span className='w-2.5 h-2.5 rounded-full' style={{ background: '#0D7377' }} />
            Domestic
          </span>
          <span className='font-semibold text-gov-dark tabular-nums'>{fmtT(d.domestic)}</span>
        </div>
        <div className='flex justify-between gap-6 pt-1 border-t border-neutral-border/30'>
          <span className='text-neutral-muted'>Debt-to-GDP</span>
          <span className='font-bold text-gov-gold tabular-nums'>{d.gdpRatio}%</span>
        </div>
      </div>
    </div>
  );
}

export default function NationalDebtCard() {
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
    fiscal?.current?.debt_service_per_shilling ?? sustainability.debt_service_ratio ?? 0;

  const firstYear = debtTimeline[0];
  const lastYear = debtTimeline[debtTimeline.length - 1];

  // Derive headline numbers from the latest timeline year (single source of truth)
  const totalDebt = lastYear ? lastYear.total * 1_000_000_000 : apiData?.total_debt || 0;
  const gdpRatio = lastYear?.gdpRatio ?? apiData?.debt_to_gdp_ratio ?? 0;
  const externalDebt = lastYear
    ? lastYear.external * 1_000_000_000
    : apiData?.summary?.external_debt || 0;
  const domesticDebt = lastYear
    ? lastYear.domestic * 1_000_000_000
    : apiData?.summary?.domestic_debt || 0;
  const externalPct = totalDebt > 0 ? +((externalDebt / totalDebt) * 100).toFixed(1) : 0;
  const domesticPct = totalDebt > 0 ? +((domesticDebt / totalDebt) * 100).toFixed(1) : 0;

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
      <div className='bg-gradient-to-r from-gov-copper/[0.06] via-gov-sand/30 to-transparent px-6 sm:px-8 pt-5 pb-4 border-b border-neutral-border/20'>
        <div className='flex items-start justify-between'>
          <div>
            <h2 className='font-display text-xl sm:text-2xl text-gov-dark mb-1'>
              Kenya&apos;s National Debt
            </h2>
            <p className='text-xs text-neutral-muted'>
              {yearRange} · Source: Central Bank of Kenya &amp; National Treasury
            </p>
          </div>
          {isLoading || isTimelineLoading ? (
            <Loader2 className='w-4 h-4 animate-spin text-neutral-muted/40 mt-1' />
          ) : null}
        </div>
      </div>

      {/* Stat cards row */}
      <div className='px-6 sm:px-8 pt-5 pb-2'>
        <div className='grid grid-cols-2 sm:grid-cols-4 gap-3'>
          <StatCard
            icon={<Landmark className='w-3.5 h-3.5 text-gov-copper opacity-70' />}
            label='Total Public Debt'
            value={fmtKES(totalDebt)}
            sub={`${growthMultiple}× since ${firstYear?.year || '—'}`}
            accent='copper'
          />
          <StatCard
            icon={<TrendingUp className='w-3.5 h-3.5 text-gov-gold opacity-70' />}
            label='Debt-to-GDP'
            value={`${gdpRatio}%`}
            sub={`From ${firstYear?.gdpRatio ?? '—'}% in ${firstYear?.year || '—'}`}
            accent='gold'
          />
          <StatCard
            icon={
              <span className='text-xs' suppressHydrationWarning>
                🏦
              </span>
            }
            label='External Debt'
            value={fmtKES(externalDebt)}
            sub={`${externalPct}% of total`}
            accent='forest'
          />
          <StatCard
            icon={
              <span className='text-xs' suppressHydrationWarning>
                🇰🇪
              </span>
            }
            label='Domestic Debt'
            value={fmtKES(domesticDebt)}
            sub={`${domesticPct}% of total`}
            accent='sage'
          />
        </div>
      </div>

      {/* Chart */}
      <div className='px-4 sm:px-6 pt-3 pb-2 flex-1 min-h-0'>
        {isTimelineLoading ? (
          <div className='h-64 sm:h-72 flex flex-col justify-end gap-2 px-2'>
            <div className='flex items-end gap-1 h-full'>
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton
                  key={i}
                  className='flex-1 rounded-t-sm'
                  style={{ height: `${30 + Math.random() * 60}%` }}
                />
              ))}
            </div>
            <Skeleton className='h-2 w-full' />
          </div>
        ) : !hasTimeline ? (
          <div className='h-64 sm:h-72 flex items-center justify-center text-neutral-muted text-sm'>
            No timeline data available
          </div>
        ) : (
          <>
            <div className='h-64 sm:h-72'>
              <ResponsiveContainer width='100%' height='100%'>
                <ComposedChart
                  data={debtTimeline}
                  margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
                  <defs>
                    <linearGradient id='extGrad' x1='0' y1='0' x2='0' y2='1'>
                      <stop offset='0%' stopColor='#C94A4A' stopOpacity={0.35} />
                      <stop offset='100%' stopColor='#C94A4A' stopOpacity={0.04} />
                    </linearGradient>
                    <linearGradient id='domGrad' x1='0' y1='0' x2='0' y2='1'>
                      <stop offset='0%' stopColor='#0D7377' stopOpacity={0.32} />
                      <stop offset='100%' stopColor='#0D7377' stopOpacity={0.04} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray='3 3' stroke='#E2DDD5' vertical={false} />
                  <XAxis
                    dataKey='year'
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 11, fill: '#6B7280' }}
                    interval={0}
                  />
                  <YAxis
                    yAxisId='debt'
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 10, fill: '#9CA3AF' }}
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
                    tick={{ fontSize: 10, fill: '#D9A441' }}
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
                    fill='url(#domGrad)'
                    name='Domestic'
                  />
                  <Area
                    yAxisId='debt'
                    type='monotone'
                    dataKey='external'
                    stackId='stack'
                    stroke='#C94A4A'
                    strokeWidth={1.5}
                    fill='url(#extGrad)'
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
              <span className='flex items-center gap-1.5 text-[10px] text-neutral-muted'>
                <span
                  className='w-3 h-2 rounded-sm'
                  style={{ background: '#0D7377', opacity: 0.5 }}
                />{' '}
                Domestic Debt
              </span>
              <span className='flex items-center gap-1.5 text-[10px] text-neutral-muted'>
                <span className='w-3 h-2 rounded-sm bg-gov-copper/50' /> External Debt
              </span>
              <span className='flex items-center gap-1.5 text-[10px] text-neutral-muted'>
                <span className='w-5 h-0 border-t-2 border-dashed border-gov-gold' /> Debt-to-GDP %
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
            title={`KES ${debtServiceRatio} cents`}
            desc='of every tax shilling goes to debt service'
          />
          <InsightPill
            icon='📊'
            title={`${domesticPct}% / ${externalPct}%`}
            desc='Domestic vs External debt split'
          />
          <InsightPill
            icon={<AlertTriangle className='w-4 h-4 text-gov-copper' />}
            title={`Risk: ${riskLevel}`}
            desc='IMF debt distress classification'
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
  label: string;
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
    forest: 'text-gov-forest',
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
          className={`text-xs font-semibold block ${highlight ? 'text-gov-copper' : 'text-gov-dark'}`}>
          {title}
        </span>
        <span className='text-[10px] text-neutral-muted leading-tight'>{desc}</span>
      </div>
    </div>
  );
}
