'use client';

import { KenyaFlag } from '@/components/ui/KenyaFlag';
import { Skeleton } from '@/components/ui/Skeleton';
import { useDebtTimeline, useNationalDebtOverview } from '@/lib/react-query/useDebt';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { useLang } from '@/lib/i18n/LangProvider';
import { classifyDebtRisk, fmtBillionKES, toRawKES } from '@/lib/utils';
import { motion, useReducedMotion } from 'framer-motion';
import {
  Banknote,
  BarChart3,
  Loader2,
  type LucideIcon,
  Scale,
  TrendingDown,
} from 'lucide-react';
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
  const reduceMotion = useReducedMotion();
  return (
    <section className='border-b border-neutral-border bg-gov-cream pt-16 dark:bg-[#0d1711]'>
      <div className='mx-auto grid max-w-[1400px] gap-6 px-5 py-9 sm:px-6 sm:py-12 lg:grid-cols-[minmax(0,1fr)_280px] lg:px-8 lg:py-14'>
        <motion.div
          initial={false}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: reduceMotion ? 0 : 0.42,
            ease: [0.22, 1, 0.36, 1],
            delay: reduceMotion ? 0 : 0.05,
          }}
          className='ledger-enter relative border-l-[5px] border-gov-copper pl-5 sm:pl-7'>
          <p className='source-label text-gov-sage'>National public-finance evidence desk</p>
          <h1 className='mt-3 max-w-[18ch] font-display text-[3.15rem] font-semibold uppercase leading-[0.88] tracking-[0.01em] text-gov-dark dark:text-white sm:text-7xl lg:text-[5rem]'>
            {t('home.hero.title')}
          </h1>
          <p className='mt-5 max-w-2xl text-base leading-7 text-neutral-muted sm:text-lg'>
            {t('home.hero.subtitle')}. Public money, traced to evidence.
          </p>
        </motion.div>

        <aside className='border-t border-neutral-border pt-5 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-2'>
          <p className='source-label'>Primary source index</p>
          <div className='mt-4 space-y-3 font-mono text-[11px] uppercase tracking-[0.08em] text-gov-dark dark:text-white'>
            {[
              ['CBK', 'Debt & monetary data'],
              ['Treasury', 'Budget & fiscal data'],
              ['OAG', 'Audit findings'],
              ['CoB', 'Budget execution'],
            ].map(([source, scope]) => (
              <div key={source} className='grid grid-cols-[70px_1fr] gap-3 border-b border-neutral-border pb-2'>
                <span className='font-semibold text-gov-sage'>{source}</span>
                <span className='text-neutral-muted'>{scope}</span>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </section>
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
  //
  // The timeline fallback normalises on the row's DECLARED unit. Since the
  // stage1 3a migration /debt/timeline serves raw KES and says so with
  // `unit: "KES"`; this previously multiplied by 1e9 unconditionally, making
  // the headline 10⁹× too large after the migration. Reported as F1 on #136,
  // and the reason that migration was rolled back in production on
  // 2026-08-30. `latest` is the RAW api row here — unlike NationalDebtCard's
  // `lastYear`, which has already been normalised for the chart — so the
  // conversion belongs here.
  const totalKES =
    apiData?.total_outstanding ??
    apiData?.total_debt ??
    (latest ? toRawKES(latest.total, latest.unit) : null);
  const totalT = totalKES != null ? (totalKES / 1_000_000_000_000).toFixed(2) : null;

  // Debt-to-GDP — prefer overview's canonical ratio (uses fresher GDP base
  // than the timeline row, which can carry stale nominal-GDP figures).
  const gdpPct = apiData?.debt_to_gdp_ratio ?? latest?.gdp_ratio ?? '—';
  const year = apiData?.gdp_year ?? latest?.year ?? '—';

  // Trust the backend's risk_level when present (canonical source); fall back
  // to the centralized classifier so thresholds stay consistent across the UI.
  const riskLevel: string | null =
    apiData?.debt_sustainability?.risk_level ||
    (typeof gdpPct === 'number' ? classifyDebtRisk(gdpPct) : null);
  const isHigh = riskLevel === 'High';

  return (
    <section aria-label='Headline public finance figures' className='ledger-panel overflow-hidden'>
      <div className='grid sm:grid-cols-3'>
        <div className='border-b border-neutral-border p-5 sm:border-b-0 sm:border-r sm:p-6'>
          <div className='flex items-center justify-between gap-3'>
            <span className='figure-label'>{t('home.hero.total_debt_as_of')} {year}</span>
            <KenyaFlag className='h-5 w-5 shrink-0' />
          </div>
          <p className='figure-value mt-4 text-[2.35rem] leading-none sm:text-5xl' data-figure>
            <span className='mr-2 text-sm tracking-[0.08em] text-neutral-muted'>KES</span>
            {totalT == null ? '—' : `${totalT}T`}
          </p>
          <div className='mt-3 inline-flex items-center gap-1 text-xs text-neutral-muted'>
            Source: CBK / National Treasury
            <DebtExplainerModal context='hero' />
          </div>
        </div>

        <div className='border-b border-neutral-border p-5 sm:border-b-0 sm:border-r sm:p-6'>
          <p className='figure-label'>Debt-to-GDP</p>
          <p className='figure-value mt-4 text-[2.35rem] leading-none sm:text-5xl' data-figure>
            {typeof gdpPct === 'number' ? `${gdpPct.toFixed(1)}%` : '—'}
          </p>
          <p className='mt-3 text-xs text-neutral-muted'>Source: CBK / IMF methodology</p>
        </div>

        <div className='p-5 sm:p-6'>
          <p className='figure-label'>{t('home.hero.risk_level')}</p>
          <p className={`mt-4 font-mono text-3xl font-semibold uppercase leading-none tracking-[0.04em] ${isHigh ? 'text-gov-copper' : riskLevel ? 'text-gov-gold' : 'text-neutral-muted'}`}>
            {riskLevel
              ? `${riskLevel} ${t('home.hero.risk_suffix')}`
              : t('home.hero.risk_unassessed_value')}
          </p>
          <div className='mt-4 flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.08em] text-neutral-muted'>
            <span className='inline-flex items-center gap-1'><span className='h-2 w-2 bg-emerald-600' />Low</span>
            <span className='inline-flex items-center gap-1'><span className='h-2 w-2 bg-gov-gold' />Moderate</span>
            <span className='inline-flex items-center gap-1'><span className='h-2 w-2 bg-gov-copper' />High</span>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════════
   CONTAINER C — Kenyan Government fiscal snapshot card
   Enticing overview of last year's national financials,
   links to the National Debt page for the full picture.
   ═══════════════════════════════════════════════════════════ */
/**
 * A fiscal money field, normalised to BILLIONS and formatted — or an em-dash.
 *
 * Two defects in one place, because they occur on the same values:
 *
 *  F1 (#136) — the stage1 3a migration rescales `fiscal_summaries` as well as
 *  `debt_timeline`, serving raw KES with a per-row `unit: "KES"`. Formatting
 *  those with `fmtBillionKES` directly would render a figure 10⁹× too large.
 *  `toRawKES` decides on the DECLARED unit, so this is a no-op against a
 *  pre-migration backend (billions -> raw -> billions) and correct after.
 *
 *  F2 (#136) — the fields are nullable and null is the NORMAL case: a fiscal
 *  year carries only an enacted budget until the Controller of Budget
 *  publishes execution. `fmtBillionKES(null)` would coerce to 0 and publish
 *  "0.0T" as a figure.
 */
function fiscalBillions(value: number | null, unit?: string | null): number | null {
  const raw = toRawKES(value, unit);
  return raw == null ? null : raw / 1e9;
}

function fmtFiscal(value: number | null, unit?: string | null): string {
  const billions = fiscalBillions(value, unit);
  return billions == null ? '\u2014' : fmtBillionKES(billions);
}

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
    <div className='ledger-panel overflow-hidden flex flex-col h-full'>
      {/* ── Header ── */}
      <div className='relative flex-shrink-0 bg-gov-dark px-4 pt-4 pb-5'>
        {/* Subtle flag stripe accents */}
        <div className='absolute top-0 left-0 right-0 h-[3px] flex'>
          <div className='flex-1 bg-black/60' />
          <div className='flex-1 bg-gov-copper/70' />
          <div className='flex-1 bg-gov-forest/80' />
        </div>

        <div className='flex items-center gap-3'>
          <div className='w-10 h-10 rounded-full bg-white/10 border border-white/20 flex items-center justify-center shadow-inner overflow-hidden'>
            <KenyaFlag className='w-6 h-6' />
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
            <span className={`relative inline-flex rounded-full h-2 w-2 ${tier.dot}`} />
          </span>
          <span
            className={`text-[11px] font-semibold uppercase tracking-widest ${healthTier === 'loading' ? 'text-white/40' : 'text-white/70'}`}>
            {t('home.govcard.fiscal_health')}: {tier.label}
          </span>
        </div>
      </div>

      {/* ── Fiscal stats ── */}
      <div className='flex-1 flex flex-col bg-surface-base'>
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
                value={fmtFiscal(fy.appropriated_budget, fy.unit)}
                sub={fy.fiscal_year}
                color='forest'
                icon={BarChart3}
              />
              <StatMiniCard
                label={t('home.govcard.stat_revenue')}
                value={fmtFiscal(fy.total_revenue, fy.unit)}
                sub={t('home.govcard.tax_nontax')}
                color='teal'
                icon={Banknote}
              />
            </div>

            {/* Row 2: Borrowed + Debt Service side by side */}
            <div className='grid grid-cols-2 gap-2'>
              <StatMiniCard
                label={t('home.govcard.stat_borrowed')}
                value={fmtFiscal(fy.total_borrowing, fy.unit)}
                sub={
                  fy.borrowing_pct_of_budget == null
                    ? '\u2014'
                    : t('home.govcard.pct_of_budget').replace(
                        '{pct}',
                        String(fy.borrowing_pct_of_budget)
                      )
                }
                color='copper'
                icon={TrendingDown}
                alert
              />
              <StatMiniCard
                label={t('home.govcard.stat_debt_service')}
                value={fmtFiscal(fy.debt_service_cost, fy.unit)}
                sub={
                  fy.debt_service_per_shilling == null
                    ? '\u2014'
                    : t('home.govcard.cents_per_kes').replace(
                        '{cents}',
                        String(fy.debt_service_per_shilling)
                      )
                }
                color='gold'
                icon={Scale}
              />
            </div>

            {/* Debt-to-GDP vs the PFM Act 2023 anchor (55% of GDP) */}
            <div className='mt-1 px-2 py-3 rounded-lg bg-white/50 dark:bg-surface-elevated border border-gray-100 dark:border-neutral-border'>
              <div className='flex items-center justify-between mb-2'>
                <span className='text-[11px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold'>
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
                  className='absolute inset-y-0 left-0 rounded-full transition-[width] duration-700 ease-out'
                  style={{ width: `${gaugePct}%`, backgroundColor: aboveAnchor ? '#C9473D' : '#176B49' }}
                />
                {/* 55% PFM Act anchor marker */}
                <div
                  className='absolute top-0 bottom-0 w-[2px] bg-gov-dark/50'
                  style={{ left: `${anchorLine}%`, transform: 'translateX(-1px)' }}
                />
              </div>
              {/* Scale markers */}
              <div className='flex justify-between mt-1'>
                <span className='text-[11px] text-gray-400 dark:text-neutral-muted/80'>0%</span>
                <span className='text-[11px] text-gray-500 dark:text-neutral-muted font-semibold'>
                  {anchorLine.toFixed(0)}% anchor
                </span>
                <span className='text-[11px] text-gray-400 dark:text-neutral-muted/80'>100%</span>
              </div>
              <p className='text-[11px] text-neutral-muted mt-1.5 text-center leading-snug'>
                {aboveAnchor && (
                  <span className='text-gov-copper font-medium'>
                    {t('home.govcard.ceiling_breached')} ·{' '}
                  </span>
                )}
                {t('home.govcard.anchor_caption')}
              </p>
            </div>

            {/* ── Where the Money Goes — budget breakdown bar ── */}
            {(() => {
              // Every part is normalised to billions on the declared unit, and
              // every part must be PRESENT. A stacked bar drawn from a partial
              // breakdown is not a partial answer — the missing component is
              // silently absorbed into "Other", which then reads as real
              // unallocated slack. That is a fabricated composition, so the
              // section is withheld instead. This is the ordinary case for a
              // fiscal year the Controller of Budget has not yet reported on.
              const debtSvc = fiscalBillions(fy.debt_service_cost, fy.unit);
              const development = fiscalBillions(fy.development_spending, fy.unit);
              const county = fiscalBillions(fy.county_allocation, fy.unit);
              const recurrent = fiscalBillions(fy.recurrent_spending, fy.unit);
              const total = fiscalBillions(fy.appropriated_budget, fy.unit);
              if (
                debtSvc == null ||
                development == null ||
                county == null ||
                recurrent == null ||
                total == null
              ) {
                return null;
              }
              // Recurrent spending in Kenya's budget INCLUDES debt service
              // (Consolidated Fund Services). Separate it out to avoid double-counting.
              const recurrentExclDebt = Math.max(recurrent - debtSvc, 0);
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
                  <span className='text-[11px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold block mb-2'>
                    {t('home.govcard.where_money_goes')}
                  </span>
                  {/* Stacked horizontal bar */}
                  <div className='flex h-3 rounded-full overflow-hidden gap-[1px]'>
                    {segments.map((seg) => (
                      <div
                        key={seg.label}
                        className={`${seg.color} transition-[width] duration-500 first:rounded-l-full last:rounded-r-full`}
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
                        <span className='text-[11px] text-gray-500 dark:text-neutral-muted/80 truncate'>{seg.label}</span>
                        <span className='text-[11px] font-semibold text-gov-dark dark:text-white tabular-nums ml-auto'>
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
            className='group w-full py-2.5 rounded-sm bg-gov-forest text-white text-sm font-semibold
                       hover:bg-gov-dark
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
  icon: Icon,
  alert,
}: {
  label: string;
  value: string;
  sub: string;
  color: 'forest' | 'copper' | 'gold' | 'teal';
  icon: LucideIcon;
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
      <Icon
        aria-hidden
        className='absolute -right-1.5 -bottom-1.5 w-8 h-8 opacity-[0.10] select-none pointer-events-none'
      />
      <span className='text-[11px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-medium leading-none'>
        {label}
      </span>
      <div className='flex items-baseline gap-1 mt-0.5'>
        {alert && (
          <span className='relative flex h-1.5 w-1.5 shrink-0'>
            <span className='relative inline-flex rounded-full h-1.5 w-1.5 bg-gov-copper' />
          </span>
        )}
        <span className={`text-sm font-bold tabular-nums leading-tight ${valueColors[color]}`}>
          {value}
        </span>
      </div>
      <span className='text-[11px] text-gray-400 dark:text-neutral-muted/80 leading-none mt-0.5 block'>{sub}</span>
    </div>
  );
}
