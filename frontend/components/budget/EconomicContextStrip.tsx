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

import FigureEvidence from '@/components/evidence/FigureEvidence';
import { motion } from 'framer-motion';
import { Activity, Building2, Gauge, TrendingUp, Users } from 'lucide-react';

import type { Qualifications } from '@/lib/evidence/qualification';

export interface EconomicContext {
  qualifications?: Record<string, Qualifications>;
  fiscal_year?: string;
  gdp_billion_kes?: number;
  gdp_as_of?: string | null;
  gdp_source?: string | null;
  gdp_growth_pct?: number | null;
  gdp_growth_as_of?: string | null;
  gdp_growth_source?: string | null;
  budget_to_gdp_pct?: number;
  revenue_to_gdp_pct?: number;
  inflation_pct?: number | null;
  inflation_as_of?: string | null;
  inflation_source?: string | null;
  inflation_measure?: string | null;
  unemployment_pct?: number | null;
  per_capita_budget_kes?: number;
  per_capita_revenue_kes?: number;
  total_population?: number;
}

interface Props {
  ctx: EconomicContext | null | undefined;
}

function fmtT(billionKES?: number): string {
  if (billionKES == null || !Number.isFinite(billionKES)) return '—';
  if (billionKES >= 1000) return `${(billionKES / 1000).toFixed(2)}T`;
  return `${billionKES.toFixed(0)}B`;
}

function pct(v?: number | null): string {
  if (v == null) return '—';
  return `${v.toFixed(1)}%`;
}

function asOf(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions): string | null {
  if (!iso || Number.isNaN(Date.parse(iso))) return null;
  return new Date(iso).toLocaleDateString('en-GB', { timeZone: 'UTC', ...opts });
}

/** Caption parts that exist, joined. An absent source is left out, never guessed. */
function caption(...parts: (string | null | undefined)[]): string {
  return parts.filter(Boolean).join(' · ');
}

export default function EconomicContextStrip({ ctx }: Props) {
  if (!ctx) return null;

  // Every caption is the row's own declared provenance (issue #232). The
  // inflation caption used to fall back to the literal "KNBS Consumer Price
  // Index", which is how a World Bank annual average came to be credited to
  // KNBS. No source from the API now means no source on the page.
  const inflationSub = caption(
    ctx.inflation_measure,
    asOf(ctx.inflation_as_of, { month: 'short', year: 'numeric' }),
  );
  const growthYear = asOf(ctx.gdp_growth_as_of, { year: 'numeric' });
  const gdpSub = caption(
    `Growth ${pct(ctx.gdp_growth_pct)}${growthYear && ctx.gdp_growth_pct != null ? ` (${growthYear})` : ''}`,
    ctx.gdp_growth_source !== ctx.gdp_source ? ctx.gdp_growth_source : null,
  );
  const gdpNote = caption(asOf(ctx.gdp_as_of, { year: 'numeric' }), ctx.gdp_source);

  const cards = [
    {
      icon: TrendingUp,
      label: 'GDP',
      labelKey: 'evidence.label.gdp' as const,
      qualifications: { ...ctx.qualifications?.gdp, ...ctx.qualifications?.gdp_growth },
      value: `KES ${fmtT(ctx.gdp_billion_kes)}`,
      sub: gdpSub,
      note: gdpNote,
      accent: '#1B3A2A',
    },
    {
      icon: Gauge,
      label: 'Budget / GDP',
      labelKey: 'evidence.label.budget_gdp' as const,
      qualifications: undefined,
      value: pct(ctx.budget_to_gdp_pct),
      sub: `Revenue / GDP ${pct(ctx.revenue_to_gdp_pct)}`,
      note: '',
      accent: '#3E6B84',
    },
    {
      icon: Activity,
      label: 'Inflation',
      labelKey: 'evidence.label.inflation' as const,
      qualifications: ctx.qualifications?.inflation,
      value: pct(ctx.inflation_pct),
      sub: inflationSub,
      note: ctx.inflation_source ?? '',
      accent:
        // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- colour band threshold only — the figure itself renders from ctx.inflation_pct and shows an em dash when absent
        (ctx.inflation_pct ?? 0) > 7
          ? '#9E3030'
          // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- colour band threshold only
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
        <div className='text-[11px] text-neutral-muted'>
          {ctx.fiscal_year ?? ''}
        </div>
      </div>

      <div className='grid grid-cols-1 sm:grid-cols-3 gap-2.5'>
        {cards.map(({ icon: Icon, label, value, sub, note, accent, qualifications, labelKey }) => (
          <div
            key={label}
            className='rounded-xl border border-neutral-border/30 bg-white dark:bg-surface-base p-4 flex items-start gap-3'>
            <div
              className='w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0'
              style={{ backgroundColor: `${accent}14` }}>
              <Icon size={18} style={{ color: accent }} />
            </div>
            <div className='min-w-0'>
              <div className='text-[11px] uppercase tracking-wider font-semibold text-neutral-muted'>
                {label}
              </div>
              <div className='font-display text-xl text-gov-dark dark:text-white tabular-nums leading-tight mt-0.5'>
                {value}
              </div>
              <div className='text-[11px] text-neutral-muted leading-tight mt-0.5'>
                {sub}
              </div>
              <FigureEvidence label={label} labelKey={labelKey} qualifications={qualifications} />
              {note ? (
                <div className='text-[10px] text-neutral-muted/80 leading-tight mt-1'>
                  {note}
                </div>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </motion.section>
  );
}
