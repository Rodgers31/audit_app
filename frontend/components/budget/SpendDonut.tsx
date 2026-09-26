'use client';

/**
 * SpendDonut
 *
 * Concentric donut for the Budget page, matching the Lender donut on the
 * Debt page so the two feel like sibling visualisations.
 *
 * Inner ring  — the printed lines of one fiscal-framework column:
 *                 Interest · Recurrent (ex-interest) · Development ·
 *                 Counties · Contingency — summing to that column's total
 * (The county-sector outer ring was withdrawn — F11.)
 *
 * Center readout reflects whichever slice or legend chip the user is
 * hovering. Defaults to the framework's spending total.
 */

import { motion } from 'framer-motion';
import { useMemo, useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer, Sector } from 'recharts';

import {
  frameworkCitation,
  frameworkOf,
  frameworkUses,
  type FiscalFramework,
} from '@/lib/fiscal/framework';

export interface SpendSector {
  sector: string;
  allocated: number; // KES (not billions) or KES-B, both supported
  spent?: number;
  utilization?: number;
  percentage?: number; // share of the dataset — optional, we recompute
}

export interface SpendDonutData {
  fiscal_year?: string;
  appropriated_budget?: number | null; // KES billions
  recurrent_spending?: number | null;
  debt_service_cost?: number | null;
  development_spending?: number | null;
  county_allocation?: number | null;
  /** The split and its own total, KSh billion. The ONLY input drawn. */
  fiscal_framework?: FiscalFramework | null;
  /** No longer rendered — the county-sector outer ring was withdrawn (F11). */
  sectors?: SpendSector[];
}

/* ────── Inner-ring palette — aligned with Flow hero so hover-stateful
   center text uses the same hues across the page ────── */
const INNER = {
  debtService: { base: '#9E3030', start: '#AB3A3A', end: '#6F2222' },
  recurrent: { base: '#6B7280', start: '#7B8591', end: '#4B5563' },
  development: { base: '#2F6343', start: '#3B7251', end: '#1F4A30' },
  counties: { base: '#4B8564', start: '#5B9774', end: '#295B3E' },
  other: { base: '#A6781F', start: '#B38628', end: '#7D591A' },
};

/* The per-sector palette and its outer ring were withdrawn (F11). */

function fmtBillions(kesB?: number | null): string {
  if (kesB == null || kesB <= 0) return '—';
  if (kesB >= 1000) return `${(kesB / 1000).toFixed(2)}T`;
  return `${kesB.toFixed(0)}B`;
}

/* ───────────────── active slice renderer — subtle lift ───────────────── */

function renderActiveShape(props: any) {
  const { cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill } = props;
  return (
    <g>
      <Sector
        cx={cx}
        cy={cy}
        innerRadius={innerRadius}
        outerRadius={outerRadius + 3}
        startAngle={startAngle}
        endAngle={endAngle}
        fill={fill}
        style={{ filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.15))' }}
      />
    </g>
  );
}

/* ────────────────────────────── component ────────────────────────────── */

interface Props {
  data: SpendDonutData;
}

export default function SpendDonut({ data }: Props) {
  const [hoverKey, setHoverKey] = useState<string | null>(null);

  // One column of Treasury's fiscal framework (issue #237), drawn against
  // that column's own total. This used to draw against appropriated_budget
  // (COB gross — counts principal redemption, excludes county transfers),
  // subtract interest-plus-principal from a recurrent figure that holds
  // interest only, and let an "Other (residual)" slice absorb the gap
  // between the bases. Absent or unreconciled -> the donut withholds.
  const uses = frameworkUses(frameworkOf(data));
  const total = uses?.total ?? null;

  /* Inner ring — macro buckets */
  const innerData = useMemo(() => {
    if (!uses) return [];
    const share = (v: number) => (v / uses.total) * 100;
    const items = [
      {
        key: 'debtService',
        name: 'Interest on debt',
        value: uses.interest,
        share: share(uses.interest),
        gradStart: INNER.debtService.start,
        gradEnd: INNER.debtService.end,
        color: INNER.debtService.base,
        note:
          'Interest on domestic and foreign debt. Principal repaid on maturing loans is financing, not spending, so it is not in this ring.',
      },
      {
        key: 'recurrent',
        name: 'Recurrent (ex-interest)',
        value: uses.recurrentExInterest,
        share: share(uses.recurrentExInterest),
        gradStart: INNER.recurrent.start,
        gradEnd: INNER.recurrent.end,
        color: INNER.recurrent.base,
        note: 'Wages, pensions, and operations & maintenance.',
      },
      {
        key: 'development',
        name: 'Development',
        value: uses.development,
        share: share(uses.development),
        gradStart: INNER.development.start,
        gradEnd: INNER.development.end,
        color: INNER.development.base,
        note: 'Capital projects and net lending — roads, hospitals, new classrooms.',
      },
      {
        key: 'counties',
        name: 'Counties',
        value: uses.counties,
        share: share(uses.counties),
        gradStart: INNER.counties.start,
        gradEnd: INNER.counties.end,
        color: INNER.counties.base,
        note: 'Transfers to the 47 county governments: equitable share plus conditional allocations.',
      },
      {
        key: 'other',
        name: 'Contingency fund',
        value: uses.contingency,
        share: share(uses.contingency),
        gradStart: INNER.other.start,
        gradEnd: INNER.other.end,
        color: INNER.other.base,
        note: 'Set aside for urgent and unforeseen needs — a printed line, not a residual.',
      },
    ];
    return items.filter((d) => d.value > 0);
  }, [uses]);

  /* Center readout — reflects whichever key is hovered */
  const centerInfo = useMemo(() => {
    const def = {
      eyebrow: 'Total spending',
      value: `KES ${fmtBillions(total)}`,
      caption: `${data.fiscal_year ?? 'Latest FY'}`,
      accent: '#1B3A2A',
    };
    if (!hoverKey) return def;
    const inner = innerData.find((d) => d.key === hoverKey);
    if (inner) {
      return {
        eyebrow: inner.name,
        value: `KES ${fmtBillions(inner.value)}`,
        caption: `${inner.share.toFixed(1)}% of spending`,
        accent: inner.color,
      };
    }
    return def;
  }, [hoverKey, innerData, total, data.fiscal_year]);

  if (!uses || innerData.length === 0) return null;
  const citationText = frameworkCitation(frameworkOf(data));

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.55 }}
      className='rounded-2xl bg-gradient-to-br from-white via-gov-sand/30 to-white dark:from-surface-elevated dark:via-surface-base dark:to-surface-elevated border border-neutral-border/40 shadow-surface p-5 sm:p-7'>
      <div className='flex items-start justify-between gap-4 flex-wrap mb-4'>
        <div>
          <div className='text-[11px] font-semibold uppercase tracking-[0.18em] text-gov-forest/80 dark:text-emerald-100/80'>
            Where the money goes
          </div>
          <h3 className='font-display text-xl sm:text-[22px] text-gov-dark dark:text-white leading-tight mt-0.5'>
            The {data.fiscal_year ?? 'current'} budget, visualised
          </h3>
          <p className='text-[12.5px] text-neutral-muted mt-1 max-w-lg'>
            Spending and net lending on Treasury&apos;s fiscal framework
            {citationText ? ` (${citationText})` : ''}, split into its printed lines.
            Hover a slice for the value. This total differs from the gross budget
            headline, which counts debt principal and excludes counties.
          </p>
        </div>
      </div>

      <div className='grid grid-cols-1 lg:grid-cols-5 gap-6 items-center'>
        {/* Donut column */}
        <div className='lg:col-span-2 relative'>
          <div className='relative w-full h-[340px] sm:h-[360px]'>
            <ResponsiveContainer width='100%' height='100%'>
              <PieChart>
                <defs>
                  {innerData.map((d, i) => (
                    <radialGradient
                      key={`spend-grad-inner-${i}`}
                      id={`spend-grad-inner-${i}`}
                      cx='50%'
                      cy='50%'
                      r='75%'
                      fx='40%'
                      fy='40%'>
                      <stop offset='0%' stopColor={d.gradStart} stopOpacity={1} />
                      <stop offset='100%' stopColor={d.gradEnd} stopOpacity={1} />
                    </radialGradient>
                  ))}
                </defs>
                {/* Inner ring — macro buckets */}
                <Pie
                  data={innerData}
                  dataKey='value'
                  cx='50%'
                  cy='50%'
                  innerRadius={74}
                  outerRadius={100}
                  paddingAngle={0.8}
                  cornerRadius={3}
                  startAngle={90}
                  endAngle={-270}
                  stroke='#FAF7F2'
                  strokeWidth={1}
                  activeIndex={
                    hoverKey ? innerData.findIndex((d) => d.key === hoverKey) : -1
                  }
                  activeShape={renderActiveShape}
                  onMouseEnter={(_, idx) => setHoverKey(innerData[idx]?.key ?? null)}
                  onMouseLeave={() => setHoverKey(null)}
                  isAnimationActive={true}
                  animationDuration={900}>
                  {innerData.map((_, idx) => (
                    <Cell key={`inner-${idx}`} fill={`url(#spend-grad-inner-${idx})`} />
                  ))}
                </Pie>
                {/* The outer ring — "county sector allocations" — was withdrawn
                    (credibility audit F11). Its shares were a fixed
                    25/20/15/10/8/7/5/4/3/3 template identical for all 47
                    counties, not sector lines read from any CoB report. */}
              </PieChart>
            </ResponsiveContainer>
            <div className='absolute inset-0 flex items-center justify-center pointer-events-none'>
              <motion.div
                key={centerInfo.eyebrow + centerInfo.value}
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                className='text-center'
                style={{ maxWidth: '130px' }}>
                <div
                  className='text-[11px] uppercase tracking-[0.18em] font-semibold truncate dark:brightness-150 dark:contrast-125'
                  style={{ color: centerInfo.accent, opacity: 0.85 }}>
                  {centerInfo.eyebrow}
                </div>
                <div className='text-[17px] sm:text-[19px] font-extrabold text-gov-dark dark:text-white tabular-nums tracking-tight mt-0.5 leading-none'>
                  {centerInfo.value}
                </div>
                <div className='text-[11px] text-gov-dark/70 dark:text-white/70 mt-1.5 leading-tight'>
                  {centerInfo.caption}
                </div>
              </motion.div>
            </div>
          </div>
        </div>

        {/* Inner-ring legend + sector list */}
        <div className='lg:col-span-3 space-y-5'>
          {/* Inner ring chips */}
          <div>
            <div className='text-[11px] uppercase tracking-[0.15em] font-semibold text-neutral-muted mb-2'>
              Macro buckets
            </div>
            <div className='grid grid-cols-1 sm:grid-cols-2 gap-1.5'>
              {innerData.map((d) => {
                const isHover = hoverKey === d.key;
                return (
                  <div
                    key={d.key}
                    onMouseEnter={() => setHoverKey(d.key)}
                    onMouseLeave={() => setHoverKey(null)}
                    className={`flex items-center gap-2 rounded-lg px-2.5 py-1.5 transition-all ${
                      isHover
                        ? 'bg-white dark:bg-surface-base shadow-sm border border-neutral-border/40'
                        : 'bg-transparent border border-transparent'
                    }`}>
                    <span
                      className='w-2.5 h-6 rounded-sm flex-shrink-0'
                      style={{
                        background: `linear-gradient(180deg, ${d.gradStart}, ${d.gradEnd})`,
                      }}
                    />
                    <div className='flex-1 min-w-0'>
                      <div className='flex items-baseline justify-between gap-2'>
                        <span className='text-[11.5px] font-semibold text-gov-dark dark:text-white truncate'>
                          {d.name}
                        </span>
                        <span className='text-[11.5px] font-bold tabular-nums text-gov-dark dark:text-white'>
                          {d.share.toFixed(1)}%
                        </span>
                      </div>
                      <div className='text-[11px] text-neutral-muted tabular-nums leading-tight'>
                        KES {fmtBillions(d.value)}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            {/* No residual slice exists any more: every slice is a printed line. */}
          </div>

          {/* The county-sector legend was withdrawn with the outer ring (F11). */}
        </div>
      </div>
    </motion.section>
  );
}
