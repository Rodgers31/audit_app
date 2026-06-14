'use client';

/**
 * SpendDonut
 *
 * Concentric donut for the Budget page, matching the Lender donut on the
 * Debt page so the two feel like sibling visualisations.
 *
 * Inner ring  — the 4 macro buckets of spending:
 *                 Debt service · Recurrent (ex-debt) · Development · Counties
 * Outer ring  — the 10 sector allocations from CoB (Health, Education, …)
 *
 * Center readout reflects whichever slice, flow-bar segment, legend chip,
 * or sector card the user is hovering. Defaults to the national total.
 */

import { motion } from 'framer-motion';
import { useMemo, useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer, Sector } from 'recharts';

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
  sectors: SpendSector[]; // 10 from CoB
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

/* ────── Outer ring — per-sector palette (tonal variation within a
   single family so it never looks like a rainbow) ────── */
const SECTOR_PALETTE: Record<string, { start: string; end: string; base: string }> = {
  Health: { start: '#D96868', end: '#8C2E2E', base: '#B94040' },
  Education: { start: '#4B8564', end: '#1F4A30', base: '#2F6343' },
  Infrastructure: { start: '#B38628', end: '#7D591A', base: '#A6781F' },
  'Water & Sanitation': { start: '#5088A8', end: '#2F5A70', base: '#3E6B84' },
  Agriculture: { start: '#6AA38B', end: '#3A7058', base: '#4E8770' },
  Administration: { start: '#7B8591', end: '#3F4754', base: '#5B6672' },
  'Trade & Enterprise': { start: '#B66F4B', end: '#7B4628', base: '#96593B' },
  Environment: { start: '#5B9774', end: '#2F6B4A', base: '#417F5E' },
  'Social Protection': { start: '#C37A94', end: '#8A4B62', base: '#A46278' },
  'Defense & Security': { start: '#576573', end: '#303944', base: '#414D59' },
  Energy: { start: '#C99641', end: '#8C6621', base: '#AC7E31' },
  Other: { start: '#9AA3AE', end: '#6B7280', base: '#838C99' },
};

const FALLBACK_SECTOR = { start: '#6B7280', end: '#3F4754', base: '#4B5563' };

function paletteForSector(name: string): { start: string; end: string; base: string } {
  return SECTOR_PALETTE[name] ?? FALLBACK_SECTOR;
}

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

  const budget = data.appropriated_budget ?? 0;
  const debtService = data.debt_service_cost ?? 0;
  const recurrent = data.recurrent_spending ?? 0;
  const dev = data.development_spending ?? 0;
  const counties = data.county_allocation ?? 0;

  const recurrentNonDebt = Math.max(0, recurrent - debtService);
  const otherSpend = Math.max(0, budget - recurrent - dev - counties);

  /* Inner ring — macro buckets */
  const innerData = useMemo(() => {
    const items = [
      {
        key: 'debtService',
        name: 'Debt service',
        value: debtService,
        share: budget > 0 ? (debtService / budget) * 100 : 0,
        gradStart: INNER.debtService.start,
        gradEnd: INNER.debtService.end,
        color: INNER.debtService.base,
        note:
          'Interest + principal on past debt. Paid ahead of any programme, per Article 221 of the Constitution.',
      },
      {
        key: 'recurrent',
        name: 'Recurrent (ex-debt)',
        value: recurrentNonDebt,
        share: budget > 0 ? (recurrentNonDebt / budget) * 100 : 0,
        gradStart: INNER.recurrent.start,
        gradEnd: INNER.recurrent.end,
        color: INNER.recurrent.base,
        note: 'Wages, pensions, and operations & maintenance.',
      },
      {
        key: 'development',
        name: 'Development',
        value: dev,
        share: budget > 0 ? (dev / budget) * 100 : 0,
        gradStart: INNER.development.start,
        gradEnd: INNER.development.end,
        color: INNER.development.base,
        note: 'Capital projects — roads, hospitals, new classrooms.',
      },
      {
        key: 'counties',
        name: 'Counties',
        value: counties,
        share: budget > 0 ? (counties / budget) * 100 : 0,
        gradStart: INNER.counties.start,
        gradEnd: INNER.counties.end,
        color: INNER.counties.base,
        note: "Equitable share transferred to the 47 county governments.",
      },
      {
        key: 'other',
        name: 'Other (residual)',
        value: otherSpend,
        share: budget > 0 ? (otherSpend / budget) * 100 : 0,
        gradStart: INNER.other.start,
        gradEnd: INNER.other.end,
        color: INNER.other.base,
        note: 'Computed residual — the balance after debt service, recurrent, development, and county transfers (largely Consolidated Fund Services: constitutional salaries, pensions, guaranteed payments).',
        isResidual: true,
      },
    ];
    return items.filter((d) => d.value > 0);
  }, [debtService, recurrentNonDebt, dev, counties, otherSpend, budget]);

  /* Outer ring — sector allocations. Sectors come in KES not billions
     from /budget/overview; normalise to billions. */
  const outerData = useMemo(() => {
    const sectorsBillions = (data.sectors ?? [])
      .filter((s) => s.allocated > 0)
      .map((s) => ({
        ...s,
        allocatedB: s.allocated >= 1000 ? s.allocated / 1_000_000_000 : s.allocated,
        spentB:
          s.spent != null
            ? s.spent >= 1000
              ? s.spent / 1_000_000_000
              : s.spent
            : null,
      }))
      .sort((a, b) => b.allocatedB - a.allocatedB);

    const sectorTotal = sectorsBillions.reduce((s, r) => s + r.allocatedB, 0);

    return sectorsBillions.map((s) => {
      const pal = paletteForSector(s.sector);
      return {
        key: `sector-${s.sector}`,
        name: s.sector,
        value: s.allocatedB,
        share: sectorTotal > 0 ? (s.allocatedB / sectorTotal) * 100 : 0,
        utilization: s.utilization ?? null,
        spentB: s.spentB,
        gradStart: pal.start,
        gradEnd: pal.end,
        color: pal.base,
      };
    });
  }, [data.sectors]);

  const sectorEnvelopeB = useMemo(
    () => outerData.reduce((sum, d) => sum + d.value, 0),
    [outerData]
  );

  /* Center readout — reflects whichever key is hovered */
  const centerInfo = useMemo(() => {
    const def = {
      eyebrow: 'Total budget',
      value: `KES ${fmtBillions(budget)}`,
      caption: `${data.fiscal_year ?? 'Latest FY'} · ${outerData.length} sectors`,
      accent: '#1B3A2A',
    };
    if (!hoverKey) return def;
    const inner = innerData.find((d) => d.key === hoverKey);
    if (inner) {
      return {
        eyebrow: inner.name,
        value: `KES ${fmtBillions(inner.value)}`,
        caption: `${inner.share.toFixed(1)}% of budget`,
        accent: inner.color,
      };
    }
    const outer = outerData.find((d) => d.key === hoverKey);
    if (outer) {
      return {
        eyebrow: outer.name,
        value: `KES ${fmtBillions(outer.value)}`,
        caption: `${outer.share.toFixed(1)}% of county envelope`,
        accent: outer.color,
      };
    }
    return def;
  }, [hoverKey, innerData, outerData, budget, data.fiscal_year]);

  if (innerData.length === 0 && outerData.length === 0) return null;

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
            The <strong className='font-semibold text-gov-dark dark:text-white'>inner ring</strong> splits the national
            budget into macro buckets. The <strong className='font-semibold text-gov-dark dark:text-white'>outer ring</strong> is
            a separate, county-level pool — county-government allocations by sector — so its
            shares are of the county envelope, not the national budget. Hover a slice for the value.
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
                  {outerData.map((d, i) => (
                    <radialGradient
                      key={`spend-grad-outer-${i}`}
                      id={`spend-grad-outer-${i}`}
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
                {/* Outer ring — sectors */}
                <Pie
                  data={outerData}
                  dataKey='value'
                  cx='50%'
                  cy='50%'
                  innerRadius={107}
                  outerRadius={138}
                  paddingAngle={0.5}
                  cornerRadius={3}
                  startAngle={90}
                  endAngle={-270}
                  stroke='#FAF7F2'
                  strokeWidth={1.25}
                  activeIndex={
                    hoverKey ? outerData.findIndex((d) => d.key === hoverKey) : -1
                  }
                  activeShape={renderActiveShape}
                  onMouseEnter={(_, idx) => setHoverKey(outerData[idx]?.key ?? null)}
                  onMouseLeave={() => setHoverKey(null)}
                  isAnimationActive={true}
                  animationDuration={1100}>
                  {outerData.map((_, idx) => (
                    <Cell key={`outer-${idx}`} fill={`url(#spend-grad-outer-${idx})`} />
                  ))}
                </Pie>
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
                  className='text-[9px] uppercase tracking-[0.18em] font-semibold truncate dark:brightness-150 dark:contrast-125'
                  style={{ color: centerInfo.accent, opacity: 0.85 }}>
                  {centerInfo.eyebrow}
                </div>
                <div className='text-[17px] sm:text-[19px] font-extrabold text-gov-dark dark:text-white tabular-nums tracking-tight mt-0.5 leading-none'>
                  {centerInfo.value}
                </div>
                <div className='text-[9.5px] text-gov-dark/70 dark:text-white/70 mt-1.5 leading-tight'>
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
            <div className='text-[10.5px] uppercase tracking-[0.15em] font-semibold text-neutral-muted mb-2'>
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
                      <div className='text-[10px] text-neutral-muted tabular-nums leading-tight'>
                        KES {fmtBillions(d.value)}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            {innerData.some((d: any) => d.isResidual) && (
              <p className='mt-2 text-[10px] leading-snug text-neutral-muted/75'>
                “Other (residual)” is a computed balancing item — the budget left after the
                named buckets — not a separately sourced line.
              </p>
            )}
          </div>

          {/* Outer ring — sector mini list */}
          <div>
            <div className='flex items-baseline justify-between gap-2 mb-2'>
              <div className='text-[10.5px] uppercase tracking-[0.15em] font-semibold text-neutral-muted'>
                County sector allocations
              </div>
              <div className='text-[10px] text-neutral-muted tabular-nums'>
                KES {fmtBillions(sectorEnvelopeB)} envelope
              </div>
            </div>
            <div className='grid grid-cols-1 sm:grid-cols-2 gap-1'>
              {outerData.map((d) => {
                const isHover = hoverKey === d.key;
                const util = d.utilization;
                return (
                  <div
                    key={d.key}
                    onMouseEnter={() => setHoverKey(d.key)}
                    onMouseLeave={() => setHoverKey(null)}
                    className={`flex items-center gap-2 rounded-md px-2 py-1 transition-all ${
                      isHover ? 'bg-white dark:bg-surface-base shadow-sm' : ''
                    }`}>
                    <span
                      className='w-1.5 h-4 rounded-sm flex-shrink-0'
                      style={{
                        background: `linear-gradient(180deg, ${d.gradStart}, ${d.gradEnd})`,
                      }}
                    />
                    <span className='text-[10.5px] font-medium text-gov-dark dark:text-white flex-1 min-w-0 truncate'>
                      {d.name}
                    </span>
                    <span className='text-[10px] text-neutral-muted tabular-nums'>
                      {d.share.toFixed(1)}%
                    </span>
                    {util != null && (
                      <span
                        className={`text-[9.5px] font-semibold tabular-nums px-1.5 py-[1px] rounded-full ${
                          util >= 80
                            ? 'bg-green-50 text-green-700'
                            : util >= 60
                              ? 'bg-amber-50 text-amber-700'
                              : 'bg-red-50 text-red-600'
                        }`}>
                        {util.toFixed(0)}%
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
            <div className='mt-2 flex items-center gap-3 text-[10px] text-neutral-muted'>
              <span className='inline-flex items-center gap-1'>
                <span className='w-2 h-2 rounded-sm bg-green-500' /> ≥80% used
              </span>
              <span className='inline-flex items-center gap-1'>
                <span className='w-2 h-2 rounded-sm bg-amber-500' /> 60–80%
              </span>
              <span className='inline-flex items-center gap-1'>
                <span className='w-2 h-2 rounded-sm bg-red-500' /> &lt;60%
              </span>
            </div>
          </div>
        </div>
      </div>
    </motion.section>
  );
}
