'use client';

/**
 * EconomicContextStrip
 *
 * Minimal row of macro-economic ratios that contextualise the budget
 * against the wider economy: GDP, budget-to-GDP, revenue-to-GDP, inflation,
 * per-capita budget.
 *
 * Stays compact — three cards + a one-sentence interpretive footnote —
 * because this is supporting context, not the main story.
 */

import { motion } from 'framer-motion';
import { Activity, Building2, Gauge, TrendingUp, Users } from 'lucide-react';

export interface EconomicContext {
  fiscal_year?: string;
  gdp_billion_kes?: number;
  gdp_growth_pct?: number;
  budget_to_gdp_pct?: number;
  revenue_to_gdp_pct?: number;
  inflation_pct?: number;
  inflation_as_of?: string;
  inflation_source?: string;
  unemployment_pct?: number;
  per_capita_budget_kes?: number;
  per_capita_revenue_kes?: number;
  total_population?: number;
}

interface Props {
  ctx: EconomicContext | null | undefined;
}

function fmtT(billionKES?: number): string {
  if (billionKES == null || billionKES <= 0) return '—';
  if (billionKES >= 1000) return `${(billionKES / 1000).toFixed(2)}T`;
  return `${billionKES.toFixed(0)}B`;
}

function pct(v?: number): string {
  if (v == null) return '—';
  return `${v.toFixed(1)}%`;
}

export default function EconomicContextStrip({ ctx }: Props) {
  if (!ctx || !ctx.gdp_billion_kes) return null;

  // Inflation provenance — KNBS (not CBK), shown with its real as-of date so a
  // stale figure reads as dated rather than current (audit §3.10).
  const inflationSource = ctx.inflation_source || 'KNBS Consumer Price Index';
  const inflationAsOf =
    ctx.inflation_as_of && !Number.isNaN(Date.parse(ctx.inflation_as_of))
      ? new Date(ctx.inflation_as_of).toLocaleDateString('en-GB', {
          month: 'short',
          year: 'numeric',
        })
      : null;
  const inflationSub = inflationAsOf
    ? `${inflationSource} · as of ${inflationAsOf}`
    : inflationSource;

  const cards = [
    {
      icon: TrendingUp,
      label: 'GDP',
      value: `KES ${fmtT(ctx.gdp_billion_kes)}`,
      sub: `Growth ${pct(ctx.gdp_growth_pct)}`,
      accent: '#1B3A2A',
    },
    {
      icon: Gauge,
      label: 'Budget / GDP',
      value: pct(ctx.budget_to_gdp_pct),
      sub: `Revenue / GDP ${pct(ctx.revenue_to_gdp_pct)}`,
      accent: '#3E6B84',
    },
    {
      icon: Activity,
      label: 'Inflation',
      value: pct(ctx.inflation_pct),
      sub: inflationSub,
      accent:
        (ctx.inflation_pct ?? 0) > 7
          ? '#9E3030'
          : (ctx.inflation_pct ?? 0) > 5
            ? '#A6781F'
            : '#2F6343',
    },
  ];

  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.5 }}
      className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-5 sm:p-6'>
      <div className='flex items-baseline justify-between gap-3 mb-4'>
        <div>
          <div className='text-[11px] font-semibold uppercase tracking-[0.18em] text-gov-forest/80 dark:text-emerald-100/80'>
            Economic context
          </div>
          <h3 className='font-display text-lg sm:text-[20px] text-gov-dark dark:text-white leading-tight mt-0.5'>
            How the budget sits against the wider economy
          </h3>
        </div>
        <div className='text-[10.5px] text-neutral-muted'>
          {ctx.fiscal_year ?? ''}
        </div>
      </div>

      <div className='grid grid-cols-1 sm:grid-cols-3 gap-2.5'>
        {cards.map(({ icon: Icon, label, value, sub, accent }) => (
          <div
            key={label}
            className='rounded-xl border border-neutral-border/30 bg-white dark:bg-surface-base p-4 flex items-start gap-3'>
            <div
              className='w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0'
              style={{ backgroundColor: `${accent}14` }}>
              <Icon size={18} style={{ color: accent }} />
            </div>
            <div className='min-w-0'>
              <div className='text-[10.5px] uppercase tracking-wider font-semibold text-neutral-muted'>
                {label}
              </div>
              <div className='font-display text-xl text-gov-dark dark:text-white tabular-nums leading-tight mt-0.5'>
                {value}
              </div>
              <div className='text-[10.5px] text-neutral-muted leading-tight mt-0.5'>
                {sub}
              </div>
            </div>
          </div>
        ))}
      </div>
    </motion.section>
  );
}
