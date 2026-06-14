'use client';

import { useNationalBudgetSummary } from '@/lib/react-query';
import { motion } from 'framer-motion';

function formatKES(value: number | null | undefined): string {
  if (value == null) return '—';
  if (value >= 1000) return `KES ${(value / 1000).toFixed(1)}T`;
  return `KES ${value.toFixed(1)}B`;
}

/**
 * Zone 5 supplement: Explore County Finances card
 * Contains Kenya map preview, summary budget stats.
 * Data sourced from GET /budget/national.
 */
export default function CountyFinancesCard() {
  const { data, isLoading } = useNationalBudgetSummary();

  const totalBudget = data?.total_budget ?? data?.totalBudget ?? null;
  const totalAllocations = data?.total_allocations ?? data?.totalAllocations ?? null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.6, delay: 0.1 }}
      className='glass-card p-6 sm:p-8'>
      <h3 className='font-display text-xl text-gov-dark dark:text-white mb-5'>Explore County Finances</h3>

      {/* Map legend strip */}
      <div className='flex items-center gap-4 mb-4'>
        <div className='flex items-center gap-1.5'>
          <div className='w-3 h-3 rounded-sm bg-gov-sage' />
          <span className='text-xs text-neutral-muted'>Good</span>
        </div>
        <div className='flex items-center gap-1.5'>
          <div className='w-3 h-3 rounded-sm bg-gov-gold' />
          <span className='text-xs text-neutral-muted'>Average</span>
        </div>
      </div>

      {/* Mini Kenya map silhouette placeholder */}
      <div className='relative w-full h-52 rounded-xl overflow-hidden bg-gradient-to-br from-gov-sage/5 to-gov-gold/5 border border-neutral-border/30 mb-5'>
        <svg viewBox='0 0 200 220' className='w-full h-full'>
          {/* Simplified Kenya outline with county fills */}
          <path
            d='M80 10 L120 8 L150 22 L165 50 L158 75 L140 95 L120 110 L95 108 L70 95 L52 72 L48 50 L60 28 Z'
            fill='#4A7C5C'
            opacity='0.15'
            stroke='#4A7C5C'
            strokeWidth='0.8'
          />
          <path d='M60 28 L80 10 L95 15 L85 40 L70 42 Z' fill='#4A7C5C' opacity='0.3' />
          <path d='M95 15 L120 8 L130 30 L110 45 L85 40 Z' fill='#4A7C5C' opacity='0.4' />
          <path
            d='M130 30 L150 22 L160 40 L145 55 L120 50 L110 45 Z'
            fill='#D9A441'
            opacity='0.3'
          />
          <path d='M85 40 L110 45 L105 65 L80 70 L70 55 Z' fill='#4A7C5C' opacity='0.25' />
          <path d='M110 45 L120 50 L125 70 L105 75 L105 65 Z' fill='#C94A4A' opacity='0.2' />
          <path d='M70 55 L80 70 L75 90 L55 80 L52 72 Z' fill='#4A7C5C' opacity='0.35' />
          <path d='M80 70 L105 75 L100 95 L85 100 L75 90 Z' fill='#D9A441' opacity='0.25' />
          {/* County dots */}
          <circle cx='100' cy='50' r='2' fill='#C94A4A' opacity='0.7' />
          <circle cx='80' cy='60' r='1.5' fill='#4A7C5C' />
          <circle cx='120' cy='40' r='1.5' fill='#D9A441' />
        </svg>
      </div>

      {/* Bottom summary metrics */}
      <div className='grid grid-cols-2 gap-4'>
        <div>
          <div className='flex items-center gap-1.5 mb-0.5'>
            <span className='text-sm'>🇰🇪</span>
            {isLoading ? (
              <div className='h-6 w-24 bg-neutral-200 rounded animate-pulse' />
            ) : (
              <span className='text-lg font-bold text-gov-dark dark:text-white tabular-nums'>
                {formatKES(totalBudget)}
              </span>
            )}
          </div>
          <p className='text-xs text-neutral-muted leading-tight'>Total county budget</p>
        </div>
        <div>
          <div className='flex items-center gap-1.5 mb-0.5'>
            <span className='text-sm'>🇰🇪</span>
            {isLoading ? (
              <div className='h-6 w-24 bg-neutral-200 rounded animate-pulse' />
            ) : (
              <span className='text-lg font-bold text-gov-dark dark:text-white tabular-nums'>
                {formatKES(totalAllocations)}
              </span>
            )}
          </div>
          <p className='text-xs text-neutral-muted leading-tight'>
            Total budget allocations across all counties
          </p>
        </div>
      </div>

      <button className='btn-secondary w-full mt-5 text-sm'>View Detailed Report</button>
    </motion.div>
  );
}
