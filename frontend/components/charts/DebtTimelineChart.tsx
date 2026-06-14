'use client';

import { motion } from 'framer-motion';
import DataIntegrityBanner from '../DataIntegrityBanner';

interface DebtTimelineChartProps {
  data?: { years: number[]; values: number[] } | null;
}

export default function DebtTimelineChart({ data }: DebtTimelineChartProps) {
  const years: number[] = data?.years ?? [];
  const values: number[] = data?.values ?? [];

  if (years.length === 0 || values.length === 0) {
    return (
      <div>
        <div className='text-sm text-gray-600 dark:text-neutral-muted mb-3'>Total debt over time (KES Billions)</div>
        <DataIntegrityBanner
          message="Historical debt timeline data is not yet available."
          severity="info"
          inline
        />
      </div>
    );
  }

  const max = Math.max(...values);

  return (
    <div>
      <div className='text-sm text-gray-600 dark:text-neutral-muted mb-3'>Total debt over time (KES Billions)</div>
      <div className='flex items-end gap-2 h-40'>
        {values.map((v, i) => (
          <motion.div
            key={i}
            initial={{ scaleY: 0 }}
            animate={{ scaleY: 1 }}
            transition={{ delay: 0.1 * i, duration: 0.4 }}
            className='bg-blue-500 rounded-t'
            style={{ width: 24, height: `${(v / max) * 100}%` }}
            title={`${years[i]}: ${v}B`}
          />
        ))}
      </div>
      <div className='flex justify-between text-xs text-gray-500 dark:text-neutral-muted/80 mt-2'>
        {years.map((y) => (
          <span key={y}>{y}</span>
        ))}
      </div>
    </div>
  );
}
