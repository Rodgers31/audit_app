'use client';

import { Skeleton } from '@/components/ui/Skeleton';
import { useDebtTimeline, useNationalDebtOverview } from '@/lib/react-query/useDebt';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { useLang } from '@/lib/i18n/LangProvider';
import { classifyDebtRisk, fmtBillionKES } from '@/lib/utils';
import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';
import DebtExplainerModal from './DebtExplainerModal';

/* ── Formatting helpers ── */
// fmtBillionKES imported from @/lib/utils — expects billions input (FiscalSummary data)

/**
 * Dashboard Hero — full hero zone with title + 3-container card layout.
 *
 *  ┌─────────────────────────────────────────────────────────┬──────────────┐
 *  │  Title: "Kenya Public Money Tracker"                    │              │
 *  │  Subtitle: "Where your taxes go, in real time"          │              │
 *  ├─ Container A (glass outer) ─────────────────────────────┤ Container C  │
 *  │  ┌ Summary strip: 🇰🇪 <total>  <pct>%  ● <risk> ───┐ │  (county     │
 *  │  │                                                      │ │   overview)  │
 *  │  ├─ Container B (white inner): Kenya's National Debt ──┤ │              │
 *  │  │  [chart] + [bottom facts row]                        │ │              │
 *  │  └──────────────────────────────────────────────────────┘ │              │
 *  └─────────────────────────────────────────────────────────┴──────────────┘
 */
export default function HeroSection() {
  const { t } = useLang();
  return (
    <div className='max-w-[1340px] mx-auto px-5 lg:px-8 pt-24 pb-6'>
      <motion.div
        initial={{ opacity: 0, y: 28 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1], delay: 0.15 }}
        className='max-w-2xl'>
        <h1 className='font-display text-[1.75rem] sm:text-5xl lg:text-[3.5rem] text-white leading-[1.08] mb-2 drop-shadow-lg sm:whitespace-nowrap'>
          {t('home.hero.title')}
        </h1>
        <p className='text-base sm:text-lg text-white/70 font-light tracking-wide drop-shadow-md'>
          {t('home.hero.subtitle')}
        </p>
      </motion.div>
    </div>
  );
}

/** Summary strip — headline figures from the authoritative /debt/national endpoint.
 *
 *  The backend exposes two debt data sources and explicitly flags which is
 *  authoritative via a reconciliation block:
 *    • loans_table        (loan-level register, ~11.85T) ← authoritative
 *    • debt_timeline_table (aggregate annual snapshot, ~12.5T)
 *
 *  The two disagree by ~5.5% — the timeline row for the current year can
 *  lag or include items not represented in the loan register (e.g. forex
 *  revaluation). We surface the register value here so this strip agrees
 *  with the /debt detail page and with the tiles in NationalDebtCard below.
 */
export function SummaryStrip() {
  const { t } = useLang();
  const { data: timelineResp } = useDebtTimeline();
  const { data: overviewResp } = useNationalDebtOverview();

  const apiData = overviewResp?.data ?? overviewResp;
  const latest = timelineResp?.timeline?.length
    ? timelineResp.timeline[timelineResp.timeline.length - 1]
    : null;

  // Headline total (KES) — prefer the authoritative loans-register sum.
  const totalKES =
    apiData?.total_outstanding ??
    apiData?.total_debt ??
    (latest ? latest.total * 1_000_000_000 : null);
  const totalT = totalKES != null ? (totalKES / 1_000_000_000_000).toFixed(2) : '—';

  // Debt-to-GDP — prefer overview's canonical ratio (uses fresher GDP base
  // than the timeline row, which can carry stale nominal-GDP figures).
  const gdpPct = apiData?.debt_to_gdp_ratio ?? latest?.gdp_ratio ?? '—';
  const year = apiData?.gdp_year ?? latest?.year ?? '—';

  // Trust the backend's risk_level when present (canonical source); fall back
  // to the centralized classifier so thresholds stay consistent across the UI.
  const riskLevel =
    apiData?.debt_sustainability?.risk_level ||
    classifyDebtRisk(typeof gdpPct === 'number' ? gdpPct : undefined);
  const isHigh = riskLevel === 'High';

  return (
    <div className='flex flex-wrap items-end gap-x-6 gap-y-3 mb-4 px-1'>
      {/* Flag + Total Debt */}
      <div className='flex items-center gap-2.5'>
        <span className='text-2xl' suppressHydrationWarning>
          🇰🇪
        </span>
        <div>
          <span className='text-4xl sm:text-5xl font-extrabold text-gov-dark dark:text-white tracking-tight leading-none'>
            {totalT}
            <span className='text-3xl sm:text-4xl ml-0.5'>T</span>
          </span>
        </div>
      </div>

      {/* Risk Level */}
      <div className='flex items-end gap-3'>
        <div>
          <span className='text-3xl sm:text-4xl font-bold text-gov-dark dark:text-white tracking-tight leading-none'>
            {typeof gdpPct === 'number' ? Math.round(gdpPct) : gdpPct}
            <span className='text-xl'>%</span>
          </span>
        </div>
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-white/60 dark:bg-surface-elevated border ${isHigh ? 'border-gov-copper/20 text-gov-copper' : 'border-gov-gold/20 text-gov-gold'} mb-0.5`}>
          <span
            className={`w-1.5 h-1.5 rounded-full ${isHigh ? 'bg-gov-copper' : 'bg-gov-gold'} inline-block`}
          />
          {riskLevel} {t('home.hero.risk_suffix')}
        </span>
      </div>

      {/* Labels row */}
      <div className='w-full flex gap-8 mt-0.5'>
        <span className='text-xs text-gov-dark/60 dark:text-white/60 font-medium inline-flex items-center gap-1'>
          {t('home.hero.total_debt_as_of')} {year}
          <DebtExplainerModal context='hero' />
        </span>
        <span className='text-xs text-gov-dark/60 dark:text-white/60 font-medium'>
          {t('home.hero.risk_level')}{' '}
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
  const { t } = useLang();
  const { data: fiscal, isLoading } = useFiscalSummary();
  const fy = fiscal?.current;

  // Debt vs the PFM Act 2023 anchor (55% of GDP). The former KES 10T numeric
  // ceiling was repealed in 2023, so debt is no longer framed as "% of 10T".
  const anchor = fiscal?.debt_anchor;
  const anchorLine = anchor?.anchor_pct_gdp ?? 55;
  const debtToGdp = anchor?.debt_to_gdp_pct ?? null;
  const aboveAnchor =
    anchor?.above_anchor ?? (debtToGdp != null ? debtToGdp > anchorLine : false);
  const gaugePct = debtToGdp != null ? Math.min(debtToGdp, 100) : 0;
  const fyLabel = fy?.fiscal_year || '—';

  /* Derive a "fiscal health" tier from debt-to-GDP vs the anchor */
  const healthTier = !fy
    ? 'loading'
    : debtToGdp == null
      ? 'stable'
      : debtToGdp > anchorLine + 12
        ? 'critical'
        : debtToGdp > anchorLine
          ? 'warning'
          : 'stable';

  const tierColors = {
    critical: {
      dot: 'bg-gov-copper',
      ring: 'ring-gov-copper/30',
      text: 'text-gov-copper',
      label: t('home.govcard.under_strain'),
    },
    warning: {
      dot: 'bg-gov-gold',
      ring: 'ring-gov-gold/30',
      text: 'text-gov-gold',
      label: t('home.govcard.watch_list'),
    },
    stable: {
      dot: 'bg-emerald-500',
      ring: 'ring-emerald-500/30',
      text: 'text-emerald-600',
      label: t('home.govcard.stable'),
    },
    loading: { dot: 'bg-gray-400', ring: 'ring-gray-400/20', text: 'text-gray-400 dark:text-neutral-muted/80', label: '...' },
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
              {t('home.govcard.title')}
            </h3>
            <p className='text-[11px] text-white/50 font-medium mt-0.5'>
              {fyLabel} {t('home.govcard.fiscal_snapshot')}
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
            {t('home.govcard.fiscal_health')}: {tier.label}
          </span>
        </div>
      </div>

      {/* ── Fiscal stats ── */}
      <div className='flex-1 flex flex-col bg-gradient-to-b from-white/60 to-white/40 dark:from-surface-base/95 dark:to-surface-base/85 backdrop-blur-md'>
        {isLoading ? (
          <div className='flex-1 p-3 space-y-3'>
            <div className='grid grid-cols-2 gap-2'>
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className='rounded-lg border border-gray-100 dark:border-neutral-border px-2.5 py-2 space-y-1.5'>
                  <Skeleton className='h-2 w-12' />
                  <Skeleton className='h-4 w-16' />
                  <Skeleton className='h-2 w-10' />
                </div>
              ))}
            </div>
            <div className='rounded-lg border border-gray-100 dark:border-neutral-border px-2 py-3 space-y-2'>
              <Skeleton className='h-2 w-20' />
              <Skeleton className='h-2.5 w-full rounded-full' />
            </div>
          </div>
        ) : fy ? (
          <div className='p-3 flex-1 flex flex-col gap-2'>
            {/* Row 1: Budget + Revenue side by side */}
            <div className='grid grid-cols-2 gap-2'>
              <StatMiniCard
                label={t('home.govcard.stat_budget')}
                value={fmtBillionKES(fy.appropriated_budget)}
                sub={fy.fiscal_year}
                color='forest'
                icon='📊'
              />
              <StatMiniCard
                label={t('home.govcard.stat_revenue')}
                value={fmtBillionKES(fy.total_revenue)}
                sub={t('home.govcard.tax_nontax')}
                color='teal'
                icon='💰'
              />
            </div>

            {/* Row 2: Borrowed + Debt Service side by side */}
            <div className='grid grid-cols-2 gap-2'>
              <StatMiniCard
                label={t('home.govcard.stat_borrowed')}
                value={fmtBillionKES(fy.total_borrowing)}
                sub={t('home.govcard.pct_of_budget').replace('{pct}', String(fy.borrowing_pct_of_budget))}
                color='copper'
                icon='📉'
                alert
              />
              <StatMiniCard
                label={t('home.govcard.stat_debt_service')}
                value={fmtBillionKES(fy.debt_service_cost)}
                sub={t('home.govcard.cents_per_kes').replace('{cents}', String(fy.debt_service_per_shilling))}
                color='gold'
                icon='⚖️'
              />
            </div>

            {/* Debt-to-GDP vs the PFM Act 2023 anchor (55% of GDP) */}
            <div className='mt-1 px-2 py-3 rounded-lg bg-white/50 dark:bg-surface-elevated border border-gray-100 dark:border-neutral-border'>
              <div className='flex items-center justify-between mb-2'>
                <span className='text-[10px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold'>
                  {t('home.govcard.debt_ceiling')}
                </span>
                <span
                  className={`text-xs font-black tabular-nums ${aboveAnchor ? 'text-gov-copper' : 'text-gov-dark dark:text-white'}`}>
                  {debtToGdp != null ? `${debtToGdp.toFixed(0)}%` : '—'}
                </span>
              </div>
              {/* Bar: debt as % of GDP (0–100), with the 55% anchor marked */}
              <div className='relative h-2.5 rounded-full bg-gray-100 dark:bg-surface-elevated overflow-hidden'>
                <div
                  className='absolute inset-y-0 left-0 rounded-full transition-all duration-700 ease-out'
                  style={{
                    width: `${gaugePct}%`,
                    background: aboveAnchor
                      ? 'linear-gradient(90deg, #D9A441 0%, #C94A4A 100%)'
                      : 'linear-gradient(90deg, #4A7C5C 0%, #D9A441 100%)',
                  }}
                />
                {/* 55% PFM Act anchor marker */}
                <div
                  className='absolute top-0 bottom-0 w-[2px] bg-gov-dark/50'
                  style={{ left: `${anchorLine}%`, transform: 'translateX(-1px)' }}
                />
              </div>
              {/* Scale markers */}
              <div className='flex justify-between mt-1'>
                <span className='text-[8px] text-gray-400 dark:text-neutral-muted/80'>0%</span>
                <span className='text-[8px] text-gray-500 dark:text-neutral-muted font-semibold'>
                  {anchorLine.toFixed(0)}% anchor
                </span>
                <span className='text-[8px] text-gray-400 dark:text-neutral-muted/80'>100%</span>
              </div>
              <p className='text-[9px] text-neutral-muted mt-1.5 text-center leading-snug'>
                {aboveAnchor && (
                  <span className='text-gov-copper font-medium'>
                    ⚠ {t('home.govcard.ceiling_breached')} ·{' '}
                  </span>
                )}
                {t('home.govcard.anchor_caption')}
              </p>
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
                  label: t('home.govcard.seg_recurrent'),
                  value: recurrentExclDebt,
                  color: 'bg-gov-forest',
                  dot: 'bg-gov-forest',
                },
                {
                  label: t('home.govcard.seg_debt_service'),
                  value: debtSvc,
                  color: 'bg-gov-copper',
                  dot: 'bg-gov-copper',
                },
                {
                  label: t('home.govcard.seg_development'),
                  value: development,
                  color: 'bg-gov-gold',
                  dot: 'bg-gov-gold',
                },
                { label: t('home.govcard.seg_counties'), value: county, color: 'bg-[#0D7377]', dot: 'bg-[#0D7377]' },
                ...(other > total * 0.01
                  ? [{ label: t('home.govcard.seg_other'), value: other, color: 'bg-gray-300', dot: 'bg-gray-300' }]
                  : []),
              ];

              return (
                <div className='px-2 py-2.5 rounded-lg bg-white/50 dark:bg-surface-elevated border border-gray-100 dark:border-neutral-border'>
                  <span className='text-[10px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold block mb-2'>
                    {t('home.govcard.where_money_goes')}
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
                        <span className='text-[9px] text-gray-500 dark:text-neutral-muted/80 truncate'>{seg.label}</span>
                        <span className='text-[9px] font-semibold text-gov-dark dark:text-white tabular-nums ml-auto'>
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
            {t('home.govcard.explore_debt')}
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
    forest: 'border-l-gov-forest/60 bg-gov-forest/5 dark:bg-surface-elevated',
    copper: 'border-l-gov-copper/60 bg-gov-copper/5 dark:bg-surface-elevated',
    gold: 'border-l-gov-gold/60 bg-gov-gold/5 dark:bg-surface-elevated',
    teal: 'border-l-[#0D7377]/60 bg-[#0D7377]/5 dark:bg-surface-elevated',
  };
  const valueColors = {
    forest: 'text-gov-dark dark:text-white',
    copper: 'text-gov-copper',
    gold: 'text-gov-dark dark:text-white',
    teal: 'text-gov-dark dark:text-white',
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
      <span className='text-[9px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-medium leading-none'>
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
      <span className='text-[9px] text-gray-400 dark:text-neutral-muted/80 leading-none mt-0.5 block'>{sub}</span>
    </div>
  );
}
