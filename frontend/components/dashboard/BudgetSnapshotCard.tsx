'use client';

import InfoTip from '@/components/InfoTip';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { useLang } from '@/lib/i18n/LangProvider';
import { useNationalBudgetSummary } from '@/lib/react-query/useBudget';
import { fmtKES } from '@/lib/utils';
import { motion } from 'framer-motion';
import { Banknote, TrendingUp } from 'lucide-react';
import Link from 'next/link';

// fmtKES imported from @/lib/utils — expects raw KES input (BudgetLine data)

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
  const { t } = useLang();
  const { data: resp, isLoading, error } = useNationalBudgetSummary();

  if (isLoading) {
    return <SkeletonCard className='min-h-[340px]' />;
  }

  if (error || !resp) {
    return (
      <div className='glass-card p-8 flex flex-col items-center justify-center min-h-[340px] gap-2'>
        <Banknote className='w-6 h-6 text-neutral-muted/25' />
        <p className='text-xs text-neutral-muted'>{t('home.budget.unavailable')}</p>
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
      <div className='bg-gradient-to-r from-gov-sand/60 via-gov-cream/40 to-transparent dark:from-surface-elevated/40 dark:via-surface-base/20 dark:to-transparent px-6 sm:px-8 pt-5 pb-4 border-b border-neutral-border/20'>
        <h3 className='font-display text-lg text-gov-dark dark:text-white mb-0.5'>{t('home.budget.where_taxes_go')}</h3>
        <p className='text-xs text-neutral-muted'>
          {t('home.budget.allocation_by_sector')}
          {budget?.fiscal_year ? ` — ${budget.fiscal_year}` : ''}
        </p>
      </div>

      <div className='px-6 sm:px-8 py-5 flex flex-col flex-1'>
        {/* Headline metrics */}
        <div className='flex gap-4 sm:gap-6 mb-4'>
          <div className='flex-1 rounded-xl bg-gov-forest/[0.04] border border-neutral-border/30 px-4 py-3'>
            <div className='flex items-start gap-1.5 mb-1'>
              <Banknote className='w-3.5 h-3.5 mt-px flex-shrink-0 text-gov-forest dark:text-emerald-100 opacity-70' />
              <span className='text-[11px] text-neutral-muted font-medium leading-tight'>
                {budget.total_label || t('home.budget.total_label')}
              </span>
            </div>
            <span className='text-lg font-bold text-gov-forest dark:text-emerald-100 tabular-nums leading-none'>
              {fmtKES(total)}
            </span>
            {budget.scope_detail && (
              <p className='mt-1.5 text-[11px] leading-snug text-neutral-muted/75'>
                {budget.scope_detail}
              </p>
            )}
          </div>
          <div className='flex-1 rounded-xl bg-gov-gold/[0.05] border border-neutral-border/30 px-4 py-3'>
            <div className='flex items-center gap-1.5 mb-1'>
              <TrendingUp className='w-3.5 h-3.5 text-gov-gold opacity-70' />
              <span className='text-[11px] text-neutral-muted font-medium uppercase tracking-wider'>
                {t('home.budget.execution_label')}
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
                    <span className='text-xs text-gov-dark dark:text-white font-medium truncate'>{s.sector}</span>
                    {(s.sector === 'Development' || s.sector === 'Recurrent') && (
                      <InfoTip
                        term={
                          s.sector === 'Development' ? 'development-spending' : 'recurrent-spending'
                        }
                        size={11}
                      />
                    )}
                  </div>
                  <div className='flex items-center gap-2 flex-shrink-0'>
                    <span className='text-xs font-bold text-gov-dark dark:text-white tabular-nums'>
                      {fmtKES(s.amount)}
                    </span>
                    <span className='text-[11px] text-neutral-muted tabular-nums w-8 text-right'>
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
                      className={`text-[11px] tabular-nums ${
                        utilization >= 70
                          ? 'text-gov-sage'
                          : utilization >= 40
                            ? 'text-gov-gold'
                            : 'text-gov-copper'
                      }`}>
                      {t('home.budget.pct_spent').replace('{pct}', String(utilization))}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {allSectors.length > VISIBLE_ROWS && (
          <p className='text-[11px] text-neutral-muted text-center pt-2'>
            {t('home.budget.more_sectors').replace('{n}', String(allSectors.length - VISIBLE_ROWS))}
          </p>
        )}

        <Link
          href='/budget'
          className='group mt-auto pt-4 flex items-center justify-center gap-1.5 w-full rounded-lg bg-white/60 dark:bg-surface-elevated border border-neutral-border/40 hover:border-gov-sage/40 hover:bg-gov-sage/[0.04] px-4 py-2.5 transition-all text-xs font-medium text-gov-dark dark:text-white'>
          {t('home.budget.view_full')}
        </Link>
      </div>
    </motion.div>
  );
}
