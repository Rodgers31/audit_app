/**
 * NationalDebtChart — the recharts timeline extracted from
 * NationalDebtCard so recharts (~180KB min) loads in its own async chunk
 * via next/dynamic instead of shipping in the homepage's critical bundle.
 * Keep recharts imports out of NationalDebtCard itself, or the split is
 * defeated.
 */
'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import { useEffect, useState } from 'react';
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

export interface ChartEntry {
  year: string;
  external: number;
  domestic: number;
  total: number;
  gdpRatio: number;
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

function CustomTooltip({ active, payload, label }: any) {
  const { t } = useLang();
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div className='rounded-xl bg-white/95 backdrop-blur-lg border border-neutral-border/40 shadow-elevated px-4 py-3 text-xs'>
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
  // Lazy initializer: this component is next/dynamic'd with ssr:false,
  // so window exists on first render — reading matchMedia here avoids
  // an extra render pass that briefly drew desktop tick density on
  // phones. The matchMedia guard keeps jsdom-based tests happy.
  const [mobile, setMobile] = useState<boolean>(
    () =>
      typeof window !== 'undefined' &&
      !!window.matchMedia &&
      window.matchMedia(`(max-width: ${breakpoint}px)`).matches
  );
  useEffect(() => {
    if (!window.matchMedia) return;
    const mq = window.matchMedia(`(max-width: ${breakpoint}px)`);
    setMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setMobile(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [breakpoint]);
  return mobile;
}

export default function NationalDebtChart({ data }: { data: ChartEntry[] }) {
  const isMobile = useIsMobile();
  return (
    <ResponsiveContainer width='100%' height='100%'>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
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
          tick={{ fontSize: isMobile ? 9 : 11, fill: '#6B7280' }}
          interval={isMobile ? 1 : 0}
        />
        <YAxis
          yAxisId='debt'
          axisLine={false}
          tickLine={false}
          tick={{ fontSize: 10, fill: '#9CA3AF' }}
          tickFormatter={(v: number) => (v >= 1000 ? `${(v / 1000).toFixed(0)}T` : `${v}B`)}
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
  );
}
