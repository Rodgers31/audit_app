'use client';

import { Skeleton } from '@/components/ui/Skeleton';
import { useDebtTimeline, useNationalDebtOverview } from '@/lib/react-query/useDebt';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';
import DebtExplainerModal from './DebtExplainerModal';

/* ── Formatting helpers ── */
function fmtB(val: number): string {
  if (val >= 1000) return `KES ${(val / 1000).toFixed(2)}T`;
  return `KES ${val}B`;
}

/**
 * Dashboard Hero — full hero zone with title + 3-container card layout.
 *
 *  ┌─────────────────────────────────────────────────────────┬──────────────┐
 *  │  Title: "Kenya Public Money Tracker"                    │              │
 *  │  Subtitle: "Where your taxes go, in real time"          │              │
 *  ├─ Container A (glass outer) ─────────────────────────────┤ Container C  │
 *  │  ┌ Summary strip: 🇰🇪 11.5T  74%  ● High Risk ──────┐ │  (county     │
 *  │  │                                                      │ │   overview)  │
 *  │  ├─ Container B (white inner): Kenya's National Debt ──┤ │              │
 *  │  │  [chart] + [bottom facts row]                        │ │              │
 *  │  └──────────────────────────────────────────────────────┘ │              │
 *  └─────────────────────────────────────────────────────────┴──────────────┘
 */
export default function HeroSection() {
  return (
    <div className='max-w-[1340px] mx-auto px-5 lg:px-8 pt-24 pb-6'>
      <motion.div
        initial={{ opacity: 0, y: 28 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1], delay: 0.15 }}
        className='max-w-2xl'>
        <h1 className='font-display text-4xl sm:text-5xl lg:text-[3.5rem] text-white leading-[1.08] mb-2 drop-shadow-lg whitespace-nowrap'>
          Kenya Public Money Tracker
        </h1>
        <p className='text-base sm:text-lg text-white/70 font-light tracking-wide drop-shadow-md'>
          Where your taxes go, in real time
        </p>
      </motion.div>
    </div>
  );
}

/** Summary strip — pulls latest figures from the debt timeline API */
export function SummaryStrip() {
  const { data: timelineResp } = useDebtTimeline();
  const { data: overviewResp } = useNationalDebtOverview();

  const latest = timelineResp?.timeline?.length
    ? timelineResp.timeline[timelineResp.timeline.length - 1]
    : null;

  const totalT = latest ? (latest.total / 1000).toFixed(1) : '—';
  const gdpPct = latest?.gdp_ratio ?? overviewResp?.data?.debt_to_gdp_ratio ?? '—';
  const year = latest?.year ?? '—';
  const riskLevel =
    overviewResp?.data?.debt_sustainability?.risk_level ||
    (Number(gdpPct) >= 70 ? 'High' : 'Moderate');
  const isHigh = riskLevel === 'High';

  return (
    <div className='flex flex-wrap items-end gap-x-6 gap-y-3 mb-4 px-1'>
      {/* Flag + Total Debt */}
      <div className='flex items-center gap-2.5'>
        <span className='text-2xl' suppressHydrationWarning>
          🇰🇪
        </span>
        <div>
          <span className='text-4xl sm:text-5xl font-extrabold text-gov-dark tracking-tight leading-none'>
            {totalT}
            <span className='text-3xl sm:text-4xl ml-0.5'>T</span>
          </span>
        </div>
      </div>

      {/* Risk Level */}
      <div className='flex items-end gap-3'>
        <div>
          <span className='text-3xl sm:text-4xl font-bold text-gov-dark tracking-tight leading-none'>
            {typeof gdpPct === 'number' ? Math.round(gdpPct) : gdpPct}
            <span className='text-xl'>%</span>
          </span>
        </div>
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-white/60 border ${isHigh ? 'border-gov-copper/20 text-gov-copper' : 'border-gov-gold/20 text-gov-gold'} mb-0.5`}>
          <span
            className={`w-1.5 h-1.5 rounded-full ${isHigh ? 'bg-gov-copper' : 'bg-gov-gold'} inline-block`}
          />
          {riskLevel} Risk
        </span>
      </div>

      {/* Labels row */}
      <div className='w-full flex gap-8 mt-0.5'>
        <span className='text-xs text-gov-dark/60 font-medium inline-flex items-center gap-1'>
          Total Debt as of {year}
          <DebtExplainerModal context='hero' />
        </span>
        <span className='text-xs text-gov-dark/60 font-medium'>
          Risk Level{' '}
          <span className='inline-flex gap-0.5 ml-1'>
            <span>👍</span>
            <span>❓</span>
            <span className='text-gov-copper'>🔴</span>
          </span>
        </span>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   CONTAINER C — Kenyan Government fiscal snapshot card
   Enticing overview of last year's national financials,
   links to the National Debt page for the full picture.
   ═══════════════════════════════════════════════════════════ */
export function KenyanGovCard() {
  const { data: fiscal, isLoading } = useFiscalSummary();
  const fy = fiscal?.current;

  const ceilingPct = fy ? Math.min(fy.debt_ceiling_usage_pct, 100) : 0;
  const ceilingRaw = fy?.debt_ceiling_usage_pct ?? 0;
  const ceilingOver = ceilingRaw > 100;
  const fyLabel = fy?.fiscal_year || '—';

  /* Derive a "fiscal health" tier from the data */
  const healthTier = !fy
    ? 'loading'
    : ceilingRaw > 110
      ? 'critical'
      : ceilingRaw > 90
        ? 'warning'
        : 'stable';

  const tierColors = {
    critical: {
      dot: 'bg-gov-copper',
      ring: 'ring-gov-copper/30',
      text: 'text-gov-copper',
      label: 'Under Strain',
    },
    warning: {
      dot: 'bg-gov-gold',
      ring: 'ring-gov-gold/30',
      text: 'text-gov-gold',
      label: 'Watch List',
    },
    stable: {
      dot: 'bg-emerald-500',
      ring: 'ring-emerald-500/30',
      text: 'text-emerald-600',
      label: 'Stable',
    },
    loading: { dot: 'bg-gray-400', ring: 'ring-gray-400/20', text: 'text-gray-400', label: '...' },
  };
  const tier = tierColors[healthTier];

  return (
    <div className='rounded-xl overflow-hidden flex flex-col h-full shadow-lg border border-white/15'>
      {/* ── Header ── */}
      <div className='relative flex-shrink-0 bg-gradient-to-br from-gov-forest via-gov-dark to-[#0a1a10] px-4 pt-4 pb-5'>
        {/* Subtle flag stripe accents */}
        <div className='absolute top-0 left-0 right-0 h-[3px] flex'>
          <div className='flex-1 bg-black/60' />
          <div className='flex-1 bg-gov-copper/70' />
          <div className='flex-1 bg-gov-forest/80' />
        </div>

        <div className='flex items-center gap-3'>
          <div
            className='w-10 h-10 rounded-full bg-white/10 border border-white/20 flex items-center justify-center text-xl shadow-inner'
            suppressHydrationWarning>
            🇰🇪
          </div>
          <div className='flex-1 min-w-0'>
            <h3 className='text-[15px] font-bold text-white leading-tight tracking-tight'>
              Kenyan Government
            </h3>
            <p className='text-[11px] text-white/50 font-medium mt-0.5'>
              {fyLabel} Fiscal Snapshot
            </p>
          </div>
          {isLoading && <Loader2 className='w-4 h-4 animate-spin text-white/30' />}
        </div>

        {/* Health status pill */}
        <div className='mt-3 flex items-center gap-2'>
          <span className={`relative flex h-2 w-2`}>
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full ${tier.dot} opacity-60`}
            />
            <span className={`relative inline-flex rounded-full h-2 w-2 ${tier.dot}`} />
          </span>
          <span
            className={`text-[10px] font-semibold uppercase tracking-widest ${healthTier === 'loading' ? 'text-white/40' : 'text-white/70'}`}>
            Fiscal Health: {tier.label}
          </span>
        </div>
      </div>

      {/* ── Fiscal stats ── */}
      <div className='flex-1 flex flex-col bg-gradient-to-b from-white/60 to-white/40 backdrop-blur-md'>
        {isLoading ? (
          <div className='flex-1 p-3 space-y-3'>
            <div className='grid grid-cols-2 gap-2'>
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className='rounded-lg border border-gray-100 px-2.5 py-2 space-y-1.5'>
                  <Skeleton className='h-2 w-12' />
                  <Skeleton className='h-4 w-16' />
                  <Skeleton className='h-2 w-10' />
                </div>
              ))}
            </div>
            <div className='rounded-lg border border-gray-100 px-2 py-3 space-y-2'>
              <Skeleton className='h-2 w-20' />
              <Skeleton className='h-2.5 w-full rounded-full' />
            </div>
          </div>
        ) : fy ? (
          <div className='p-3 flex-1 flex flex-col gap-2'>
            {/* Row 1: Budget + Revenue side by side */}
            <div className='grid grid-cols-2 gap-2'>
              <StatMiniCard
                label='Budget'
                value={fmtB(fy.appropriated_budget)}
                sub={fy.fiscal_year}
                color='forest'
                icon='📊'
              />
              <StatMiniCard
                label='Revenue'
                value={fmtB(fy.total_revenue)}
                sub='Tax + non-tax'
                color='teal'
                icon='💰'
              />
            </div>

            {/* Row 2: Borrowed + Debt Service side by side */}
            <div className='grid grid-cols-2 gap-2'>
              <StatMiniCard
                label='Borrowed'
                value={fmtB(fy.total_borrowing)}
                sub={`${fy.borrowing_pct_of_budget}% of budget`}
                color='copper'
                icon='📉'
                alert
              />
              <StatMiniCard
                label='Debt Service'
                value={fmtB(fy.debt_service_cost)}
                sub={`${fy.debt_service_per_shilling}¢/KES`}
                color='gold'
                icon='⚖️'
              />
            </div>

            {/* Debt ceiling gauge — dramatic arc */}
            <div className='mt-1 px-2 py-3 rounded-lg bg-white/50 border border-gray-100'>
              <div className='flex items-center justify-between mb-2'>
                <span className='text-[10px] uppercase tracking-wider text-gray-500 font-semibold'>
                  Debt Ceiling
                </span>
                <span
                  className={`text-xs font-black tabular-nums ${ceilingOver ? 'text-gov-copper' : 'text-gov-dark'}`}>
                  {ceilingRaw.toFixed(0)}%
                </span>
              </div>
              {/* Multi-segment bar */}
              <div className='relative h-2.5 rounded-full bg-gray-100 overflow-hidden'>
                {/* Safe zone fill */}
                <div
                  className='absolute inset-y-0 left-0 rounded-full transition-all duration-700 ease-out'
                  style={{
                    width: `${Math.min(ceilingPct, 75)}%`,
                    background: 'linear-gradient(90deg, #4A7C5C 0%, #D9A441 100%)',
                  }}
                />
                {/* Warning zone fill */}
                {ceilingPct > 75 && (
                  <div
                    className='absolute inset-y-0 rounded-full transition-all duration-700 ease-out'
                    style={{
                      left: '75%',
                      width: `${Math.min(ceilingPct - 75, 25)}%`,
                      background: 'linear-gradient(90deg, #D9A441 0%, #C94A4A 100%)',
                    }}
                  />
                )}
                {/* 100% threshold marker */}
                <div
                  className='absolute top-0 bottom-0 w-[2px] bg-gov-dark/40'
                  style={{ left: '100%', transform: 'translateX(-2px)' }}
                />
              </div>
              {/* Scale markers */}
              <div className='flex justify-between mt-1'>
                <span className='text-[8px] text-gray-400'>0%</span>
                <span className='text-[8px] text-gray-400'>50%</span>
                <span className='text-[8px] text-gray-400 font-semibold'>100%</span>
              </div>
              {ceilingOver && (
                <p
                  className='text-[9px] text-gov-copper font-medium mt-1.5 text-center'
                  suppressHydrationWarning>
                  ⚠ Ceiling breached by {(ceilingRaw - 100).toFixed(0)}%
                </p>
              )}
            </div>

            {/* ── Where the Money Goes — budget breakdown bar ── */}
            {(() => {
              const debtSvc = fy.debt_service_cost;
              const development = fy.development_spending;
              const county = fy.county_allocation;
              // Recurrent spending in Kenya's budget INCLUDES debt service
              // (Consolidated Fund Services). Separate it out to avoid double-counting.
              const recurrentExclDebt = Math.max(fy.recurrent_spending - debtSvc, 0);
              // Use appropriated budget as denominator (the actual spending envelope)
              const total = fy.appropriated_budget;
              if (total <= 0) return null;
              // "Other" captures any remaining slice (e.g. contingency, unallocated)
              const accounted = debtSvc + recurrentExclDebt + development + county;
              const other = Math.max(total - accounted, 0);

              const segments = [
                {
                  label: 'Recurrent',
                  value: recurrentExclDebt,
                  color: 'bg-gov-forest',
                  dot: 'bg-gov-forest',
                },
                {
                  label: 'Debt Service',
                  value: debtSvc,
                  color: 'bg-gov-copper',
                  dot: 'bg-gov-copper',
                },
                {
                  label: 'Development',
                  value: development,
                  color: 'bg-gov-gold',
                  dot: 'bg-gov-gold',
                },
                { label: 'Counties', value: county, color: 'bg-[#0D7377]', dot: 'bg-[#0D7377]' },
                ...(other > total * 0.01
                  ? [{ label: 'Other', value: other, color: 'bg-gray-300', dot: 'bg-gray-300' }]
                  : []),
              ];

              return (
                <div className='px-2 py-2.5 rounded-lg bg-white/50 border border-gray-100'>
                  <span className='text-[10px] uppercase tracking-wider text-gray-500 font-semibold block mb-2'>
                    Where the Money Goes
                  </span>
                  {/* Stacked horizontal bar */}
                  <div className='flex h-3 rounded-full overflow-hidden gap-[1px]'>
                    {segments.map((seg) => (
                      <div
                        key={seg.label}
                        className={`${seg.color} transition-all duration-500 first:rounded-l-full last:rounded-r-full`}
                        style={{ width: `${((seg.value / total) * 100).toFixed(1)}%` }}
                        title={`${seg.label}: KES ${(seg.value / 1000).toFixed(1)}T (${((seg.value / total) * 100).toFixed(0)}%)`}
                      />
                    ))}
                  </div>
                  {/* Legend grid */}
                  <div className='grid grid-cols-2 gap-x-3 gap-y-0.5 mt-2'>
                    {segments.map((seg) => (
                      <div key={seg.label} className='flex items-center gap-1.5 min-w-0'>
                        <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${seg.dot}`} />
                        <span className='text-[9px] text-gray-500 truncate'>{seg.label}</span>
                        <span className='text-[9px] font-semibold text-gov-dark tabular-nums ml-auto'>
                          {((seg.value / total) * 100).toFixed(0)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}
          </div>
        ) : null}

        {/* CTA */}
        <div className='px-3 pb-3 mt-auto'>
          <a
            href='/debt'
            className='group w-full py-2.5 rounded-xl bg-gov-forest text-white text-sm font-semibold
                       hover:bg-gov-dark transition-all duration-300 shadow-md hover:shadow-lg
                       text-center flex items-center justify-center gap-2'>
            Explore National Debt
            <span className='inline-block transition-transform duration-300 group-hover:translate-x-1'>
              →
            </span>
          </a>
        </div>
      </div>
    </div>
  );
}

/* ── Mini stat card used inside KenyanGovCard ── */
function StatMiniCard({
  label,
  value,
  sub,
  color,
  icon,
  alert,
}: {
  label: string;
  value: string;
  sub: string;
  color: 'forest' | 'copper' | 'gold' | 'teal';
  icon: string;
  alert?: boolean;
}) {
  const colors = {
    forest: 'border-l-gov-forest/60 bg-gov-forest/5',
    copper: 'border-l-gov-copper/60 bg-gov-copper/5',
    gold: 'border-l-gov-gold/60 bg-gov-gold/5',
    teal: 'border-l-[#0D7377]/60 bg-[#0D7377]/5',
  };
  const valueColors = {
    forest: 'text-gov-dark',
    copper: 'text-gov-copper',
    gold: 'text-gov-dark',
    teal: 'text-gov-dark',
  };

  return (
    <div
      className={`rounded-lg border-l-[3px] ${colors[color]} px-2.5 py-2 relative overflow-hidden`}>
      {/* Icon watermark */}
      <span
        className='absolute -right-1 -bottom-1 text-lg opacity-[0.08] select-none pointer-events-none'
        suppressHydrationWarning>
        {icon}
      </span>
      <span className='text-[9px] uppercase tracking-wider text-gray-500 font-medium leading-none'>
        {label}
      </span>
      <div className='flex items-baseline gap-1 mt-0.5'>
        {alert && (
          <span className='relative flex h-1.5 w-1.5 shrink-0'>
            <span className='animate-ping absolute inline-flex h-full w-full rounded-full bg-gov-copper opacity-50' />
            <span className='relative inline-flex rounded-full h-1.5 w-1.5 bg-gov-copper' />
          </span>
        )}
        <span className={`text-sm font-bold tabular-nums leading-tight ${valueColors[color]}`}>
          {value}
        </span>
      </div>
      <span className='text-[9px] text-gray-400 leading-none mt-0.5 block'>{sub}</span>
    </div>
  );
}
