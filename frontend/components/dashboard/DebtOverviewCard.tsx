'use client';

import { useDebtTimeline } from '@/lib/react-query';
import { motion } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

/**
 * Zone 6 LEFT: National Debt Overview — chart + risk emphasis.
 * Asymmetric panel, taller than audit card.
 * Data sourced from GET /debt/timeline.
 */
export default function DebtOverviewCard() {
  const { data, isLoading } = useDebtTimeline();

  const chartData =
    data?.timeline?.map((entry) => ({
      year: String(entry.year),
      debt: entry.total,
    })) ?? [];

  const latestEntry = data?.timeline?.[data.timeline.length - 1];
  const totalDebt = latestEntry?.total ?? 0;
  const debtToGdp = latestEntry?.gdp_ratio ?? 0;
  const latestYear = latestEntry?.year ?? '';

  const debtLabel =
    totalDebt >= 1000
      ? `KES ${(totalDebt / 1000).toFixed(2)} Trillion`
      : `KES ${totalDebt.toFixed(0)}B`;

  const riskLevel = debtToGdp >= 55 ? 'High Risk' : debtToGdp >= 30 ? 'Moderate' : 'Low Risk';

  if (isLoading) {
    return (
      <div className='glass-card p-6 sm:p-8 animate-pulse'>
        <div className='h-6 bg-neutral-200 rounded w-48 mb-4' />
        <div className='h-48 bg-neutral-100 rounded mb-5' />
        <div className='h-16 bg-neutral-100 rounded' />
      </div>
    );
  }

  if (!data?.timeline?.length) {
    return (
      <div className='glass-card p-6 sm:p-8'>
        <h3 className='font-display text-xl text-gov-dark dark:text-white mb-1'>National Debt Overview</h3>
        <p className='text-sm text-neutral-muted mt-4'>Debt timeline data unavailable.</p>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.6, delay: 0.15 }}
      className='glass-card p-6 sm:p-8'>
      <h3 className='font-display text-xl text-gov-dark dark:text-white mb-1'>National Debt Overview</h3>

      {/* Chart */}
      <div className='h-48 mt-4 mb-5'>
        <ResponsiveContainer width='100%' height='100%'>
          <ComposedChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
            <CartesianGrid strokeDasharray='3 3' stroke='#E2DDD5' vertical={false} />
            <XAxis
              dataKey='year'
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 11, fill: '#6B7280' }}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 10, fill: '#6B7280' }}
              tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}T`}
            />
            <Tooltip
              contentStyle={{
                background: 'rgba(255,255,255,0.85)',
                backdropFilter: 'blur(8px)',
                border: '1px solid #E2DDD5',
                borderRadius: '12px',
                fontSize: '12px',
              }}
            />
            <Bar
              dataKey='debt'
              fill='#4A7C5C'
              radius={[4, 4, 0, 0]}
              barSize={28}
              opacity={0.7}
              name='Debt (B KES)'
            />
            <Line
              type='monotone'
              dataKey='debt'
              stroke='#1B3A2A'
              strokeWidth={2}
              dot={{ r: 3, fill: '#1B3A2A' }}
              name='Trend'
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Headline risk metric */}
      <div className='flex items-center gap-5 pt-4 border-t border-neutral-border/40'>
        <div>
          <div className='flex items-center gap-2 mb-0.5'>
            <span className='text-xl'>🇰🇪</span>
            <span className='metric-medium text-gov-dark dark:text-white'>{debtLabel}</span>
          </div>
          <p className='text-xs text-neutral-muted'>Total Debt as of {latestYear}</p>
        </div>
        <div className='ml-auto text-right'>
          <div className='flex items-center gap-2 justify-end'>
            <AlertTriangle className='w-4 h-4 text-gov-copper' />
            <span className='text-2xl font-bold text-gov-copper'>{Math.round(debtToGdp)}%</span>
          </div>
          <p className='text-xs text-neutral-muted'>{riskLevel}</p>
          <p className='text-[10px] text-neutral-muted/60'>Debt Level</p>
        </div>
      </div>

      <button className='btn-secondary w-full mt-5 text-sm'>View Detailed Report</button>
    </motion.div>
  );
}
