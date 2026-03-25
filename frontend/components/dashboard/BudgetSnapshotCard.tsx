'use client';

import { SkeletonCard } from '@/components/ui/Skeleton';
import { useNationalBudgetSummary } from '@/lib/react-query/useBudget';
import { motion } from 'framer-motion';
import { Banknote, TrendingUp } from 'lucide-react';
import Link from 'next/link';
import InfoTip from '@/components/InfoTip';

function fmtB(val: number): string {
  if (val >= 1_000_000_000_000) return `${(val / 1_000_000_000_000).toFixed(1)}T`;
  if (val >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(0)}B`;
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(0)}M`;
  return val.toLocaleString();
}

const SECTOR_ICONS: Record<string, string> = {
  Health: '🏥',
  Education: '🎓',
  'Roads & Infrastructure': '🛣️',
  'Public Administration': '🏛️',
  'Water & Sanitation': '💧',
  Agriculture: '🌾',
  'Trade & Industry': '📊',
  'Social Services': '👥',
  Environment: '🌍',
  'County Assembly': '🏢',
  'Lands & Planning': '🗺️',
  Other: '📋',
};

/* Map variant sector names → canonical names for consolidation */
const SECTOR_MERGE: Record<string, string> = {
  'health services': 'Health',
  health: 'Health',
  education: 'Education',
  'education & training': 'Education',
  'roads and public works': 'Roads & Infrastructure',
  'roads & transport': 'Roads & Infrastructure',
  'infrastructure & transport': 'Roads & Infrastructure',
  'public administration': 'Public Administration',
  administration: 'Public Administration',
  'governance & administration': 'Public Administration',
  'water and sanitation': 'Water & Sanitation',
  'water & sanitation': 'Water & Sanitation',
  agriculture: 'Agriculture',
  'agriculture & livestock': 'Agriculture',
  'trade and industry': 'Trade & Industry',
  'trade & enterprise': 'Trade & Industry',
  'social services': 'Social Services',
  'social protection': 'Social Protection',
  environment: 'Environment',
  'environment & natural resources': 'Environment',
  'county assembly': 'County Assembly',
  'lands & urban planning': 'Lands & Planning',
  other: 'Other',
};

/** Max visible rows — tuned so card height ≈ NationalLoansCard */
const VISIBLE_ROWS = 10;

function sectorIcon(name: string): string {
  return SECTOR_ICONS[name] || '📋';
}

export default function BudgetSnapshotCard() {
  const { data: resp, isLoading, error } = useNationalBudgetSummary();

  if (isLoading) {
    return <SkeletonCard className='min-h-[340px]' />;
  }

  if (error || !resp) {
    return (
      <div className='glass-card p-8 flex flex-col items-center justify-center min-h-[340px] gap-2'>
        <Banknote className='w-6 h-6 text-neutral-muted/25' />
        <p className='text-xs text-neutral-muted'>Budget data unavailable</p>
      </div>
    );
  }

  const budget = resp?.data || resp;
  const total = budget.total || 0;
  const spent = budget.total_spent || 0;
  const executionRate = budget.execution_rate || 0;

  // Consolidate duplicate/variant sector names into canonical buckets
  const merged = new Map<
    string,
    { sector: string; amount: number; percentage: number; utilization: number }
  >();
  for (const a of budget.allocations || []) {
    if (!a.sector || a.sector === 'Total Budget') continue;
    const canonical = SECTOR_MERGE[a.sector.toLowerCase()] || a.sector;
    const existing = merged.get(canonical);
    if (existing) {
      existing.amount += a.amount || 0;
      existing.percentage += a.percentage || 0;
      if (!existing.utilization && a.utilization) existing.utilization = a.utilization;
    } else {
      merged.set(canonical, {
        sector: canonical,
        amount: a.amount || 0,
        percentage: a.percentage || 0,
        utilization: a.utilization || 0,
      });
    }
  }
  const allSectors = Array.from(merged.values()).sort((a, b) => b.amount - a.amount);
  const sectors = allSectors.slice(0, VISIBLE_ROWS);

  const maxAmt = sectors.length > 0 ? sectors[0].amount : 1;

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.6, delay: 0.1 }}
      className='glass-card overflow-hidden flex flex-col'>
      {/* Header */}
      <div className='bg-gradient-to-r from-gov-sand/60 via-gov-cream/40 to-transparent px-6 sm:px-8 pt-5 pb-4 border-b border-neutral-border/20'>
        <h3 className='font-display text-lg text-gov-dark mb-0.5'>Where Your Taxes Go</h3>
        <p className='text-xs text-neutral-muted'>
          National budget allocation by sector
          {budget?.fiscal_year ? ` — ${budget.fiscal_year}` : ''}
        </p>
      </div>

      <div className='px-6 sm:px-8 py-5 flex flex-col flex-1'>
        {/* Headline metrics */}
        <div className='flex gap-4 sm:gap-6 mb-4'>
          <div className='flex-1 rounded-xl bg-gov-forest/[0.04] border border-neutral-border/30 px-4 py-3'>
            <div className='flex items-center gap-1.5 mb-1'>
              <Banknote className='w-3.5 h-3.5 text-gov-forest opacity-70' />
              <span className='text-[10px] text-neutral-muted font-medium uppercase tracking-wider'>
                Total Budget
              </span>
            </div>
            <span className='text-lg font-bold text-gov-forest tabular-nums leading-none'>
              KES {fmtB(total)}
            </span>
          </div>
          <div className='flex-1 rounded-xl bg-gov-gold/[0.05] border border-neutral-border/30 px-4 py-3'>
            <div className='flex items-center gap-1.5 mb-1'>
              <TrendingUp className='w-3.5 h-3.5 text-gov-gold opacity-70' />
              <span className='text-[10px] text-neutral-muted font-medium uppercase tracking-wider'>
                Budget Execution
              </span>
              <InfoTip term='budget-execution' size={11} />
            </div>
            <span className='text-lg font-bold text-gov-gold tabular-nums leading-none'>
              {executionRate}%
            </span>
          </div>
        </div>

        {/* Sector bars */}
        <div className='space-y-2'>
          {sectors.map((s: any, i: number) => {
            const pct = maxAmt > 0 ? (s.amount / maxAmt) * 100 : 0;
            const utilization = s.utilization || 0;
            return (
              <div key={s.sector}>
                <div className='flex items-center justify-between mb-1'>
                  <div className='flex items-center gap-2 min-w-0'>
                    <span className='text-sm leading-none'>{sectorIcon(s.sector)}</span>
                    <span className='text-xs text-gov-dark font-medium truncate'>{s.sector}</span>
                    {(s.sector === 'Development' || s.sector === 'Recurrent') && (
                      <InfoTip
                        term={s.sector === 'Development' ? 'development-spending' : 'recurrent-spending'}
                        size={11}
                      />
                    )}
                  </div>
                  <div className='flex items-center gap-2 flex-shrink-0'>
                    <span className='text-xs font-bold text-gov-dark tabular-nums'>
                      {fmtB(s.amount)}
                    </span>
                    <span className='text-[10px] text-neutral-muted tabular-nums w-8 text-right'>
                      {Math.round(s.percentage * 10) / 10}%
                    </span>
                  </div>
                </div>
                <div className='h-1.5 rounded-full bg-neutral-border/25 overflow-hidden'>
                  <motion.div
                    initial={{ width: 0 }}
                    whileInView={{ width: `${pct}%` }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.7, delay: 0.15 + i * 0.05 }}
                    className='h-full rounded-full bg-gradient-to-r from-gov-forest to-gov-sage'
                  />
                </div>
                {utilization > 0 && (
                  <div className='flex justify-end mt-0.5'>
                    <span
                      className={`text-[10px] tabular-nums ${
                        utilization >= 70
                          ? 'text-gov-sage'
                          : utilization >= 40
                            ? 'text-gov-gold'
                            : 'text-gov-copper'
                      }`}>
                      {utilization}% spent
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {allSectors.length > VISIBLE_ROWS && (
          <p className='text-[10px] text-neutral-muted text-center pt-2'>
            +{allSectors.length - VISIBLE_ROWS} more sectors
          </p>
        )}

        <Link
          href='/budget'
          className='group mt-auto pt-4 flex items-center justify-center gap-1.5 w-full rounded-lg bg-white/60 border border-neutral-border/40 hover:border-gov-sage/40 hover:bg-gov-sage/[0.04] px-4 py-2.5 transition-all text-xs font-medium text-gov-dark'>
          View Full Budget Breakdown →
        </Link>
      </div>
    </motion.div>
  );
}
