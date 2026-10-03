'use client';

import FigureEvidence from '@/components/evidence/FigureEvidence';
import { KenyaFlag } from '@/components/ui/KenyaFlag';
import Link from 'next/link';
import { Skeleton } from '@/components/ui/Skeleton';
import { useDebtTimeline, useNationalDebtOverview } from '@/lib/react-query/useDebt';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { useLang } from '@/lib/i18n/LangProvider';
import { registerSourceLabel, summedRegisterRows } from '@/lib/debt/registerScope';
import { frameworkOf, frameworkUses } from '@/lib/fiscal/framework';
import { dsaCitation, dsaHref, dsaIsAlarm, dsaSourceLabel, dsaVintageLabel, readDsaRating } from '@/lib/debt/dsaRating';
import { fmtBillionKES, toRawKES } from '@/lib/utils';
import { motion, useReducedMotion } from 'framer-motion';
import {
  AlertTriangle,
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
  // Same query KenyanGovCard below already runs, so React Query serves this
  // from cache rather than issuing a second request. Needed here for the
  // statutory debt anchor the headline is judged against.
  const { data: fiscal } = useFiscalSummary();

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

  // The debt-to-GDP ratio and the debt total beside it are on DIFFERENT
  // bases and are not two views of one number: `debt_to_gdp_ratio` is IMF
  // General-Government gross debt over GDP (69.3%), while `total_outstanding`
  // is our central-government loans table (11.86T as of 2026-09-06 — it was
  // 13.55T until the external book was replaced with per-creditor World Bank
  // IDS data). Dividing the two figures on screen gives 77%, not 69.3%. Name
  // the basis rather than letting a reader assume they divide (credibility
  // audit F4/F8).
  const gdpBasis: string | null = apiData?.debt_to_gdp_basis ?? null;
  const gdpSource: string | null = apiData?.debt_to_gdp_source ?? null;

  // What the headline total actually is. `total_outstanding` is the sum of the
  // debt rows in our loans table; `reconciliation.secondary_value_kes` is
  // the aggregate the publisher states for the same period. They disagree by
  // ~9%, so the card names both rather than attributing our sum to CBK, which
  // publishes a different number (credibility audit F3).
  //
  // The row count is NOT `loan_count`. That field is `len(loans)` — every
  // national row, pending bills included — while the total above them is
  // summed with `_is_debt_loan`, which drops the 13 pending-bill rows. The
  // label said "60 rows" over a 47-row sum. `summedRegisterRows` recovers the
  // real count from the per-category counts and only returns one when those
  // categories add back up to the figure it is labelling.
  const summedRows = summedRegisterRows(apiData?.categories, totalKES);
  const publishedTotalKES: number | null =
    apiData?.reconciliation?.secondary_value_kes ?? null;
  const publishedTotalT =
    publishedTotalKES != null
      ? (publishedTotalKES / 1_000_000_000_000).toFixed(2)
      : null;

  // The risk rating is the joint IMF–World Bank DSA's, quoted with its date
  // and page, or it is absent (issue #269). It used to be `risk_level`, which
  // the backend set to "High" whenever debt-to-GDP was above an unsourced
  // 65%. When that was missing, the ratio was banded here at an uncited
  // 40/60. Neither was the IMF's, and the site banding the ratio itself is
  // not a substitute for the IMF's rating.
  const dsa = readDsaRating(apiData?.debt_sustainability);
  const riskLevel: string | null = dsa?.overall_risk_of_debt_distress ?? null;
  const isHigh = dsaIsAlarm(dsa);

  const alarm = isHigh;
  // `.text-gov-copper` is re-pointed at the lighter accent token under
  // `:root.dark` (globals.css), so this needs no dark: variant to stay legible.
  const figureTone = alarm ? 'text-gov-copper' : '';

  return (
    <section
      aria-label='Headline public finance figures'
      className='ledger-panel overflow-hidden'>
      {/* Alert rule — a pre-attentive cue that the figures below are outside
          their statutory bounds. Never decorative: it is bound to the same
          `alarm` condition the copper figures and the chips are. */}
      {alarm && <div aria-hidden='true' className='h-1 w-full bg-gov-copper' />}
      <div className='grid md:grid-cols-3'>
        <div className='figure-cell border-b border-neutral-border p-5 md:border-b-0 md:border-r md:p-6'>
          <div className='flex items-center justify-between gap-3'>
            {/* The year here used to be `gdp_year` — the GDP observation year,
                not the debt vintage — so the card dated the debt figure by
                something else entirely (credibility audit F4). The basis now
                sits in the source line below, where it can be stated exactly. */}
            <span className='figure-label'>{t('home.hero.total_debt')}</span>
            <KenyaFlag className='h-5 w-5 shrink-0' />
          </div>
          <p className={`figure-value figure-fluid mt-4 leading-none ${figureTone}`} data-figure>
            <span className='mr-2 text-sm tracking-[0.08em] text-neutral-muted'>KES</span>
            {totalT == null ? '—' : `${totalT}T`}
          </p>
          {/* The alarm is the DSA's rating row, printed as the DSA prints it:
              label and value verbatim. It is not an adjective of ours. The
              citation link sits in the Risk Level cell beside this one. There
              is a text cue as well as the colour, so the warning does not
              depend on seeing red (WCAG 1.4.1). */}
          {dsa && isHigh && (
            <p className='mt-2 inline-flex items-start gap-1.5 font-mono text-[11px] font-semibold uppercase leading-snug tracking-[0.06em] text-gov-copper'>
              <AlertTriangle aria-hidden='true' className='mt-px h-3 w-3 shrink-0' />
              <span>
                Overall risk of debt distress: {dsa.overall_risk_of_debt_distress} · {dsaSourceLabel(dsa)}
              </span>
            </p>
          )}
          <FigureEvidence label='debt register operands' rows={apiData?.figure_qualifications?.loans} table='loans' />
          <div className='mt-3 text-xs leading-snug text-neutral-muted'>
            <span>{registerSourceLabel(summedRows)}</span>
            {publishedTotalT && (
              <span className='block mt-0.5'>
                CBK publishes KES {publishedTotalT}T for the same period —{' '}
                <Link href='/debt' className='underline hover:no-underline'>
                  the gap is unreconciled
                </Link>
                .
              </span>
            )}
            <span className='mt-0.5 inline-flex items-center gap-1'>
              <DebtExplainerModal context='hero' />
            </span>
          </div>
        </div>

        <div className='figure-cell border-b border-neutral-border p-5 md:border-b-0 md:border-r md:p-6'>
          <p className='figure-label'>Debt-to-GDP</p>
          <FigureEvidence label='GDP observations' rows={apiData?.figure_qualifications?.gdp_data} table='gdp_data' />
          <FigureEvidence label='debt-to-GDP observation' note={apiData?.debt_to_gdp_ratio != null ? apiData?.figure_qualifications?.derived_ratio : undefined} qualifications={apiData?.debt_to_gdp_ratio == null && latest?.qualifications?.gdp_ratio ? { gdp_ratio: latest.qualifications.gdp_ratio } : undefined} />
          <p className={`figure-value figure-fluid mt-4 leading-none ${figureTone}`} data-figure>
            {typeof gdpPct === 'number' ? `${gdpPct.toFixed(1)}%` : '—'}
          </p>
          <p className='mt-3 text-xs leading-snug text-neutral-muted'>
            {gdpBasis ?? 'Basis not declared by the source'}
            {gdpSource && <span className='block mt-0.5'>Source: {gdpSource}</span>}
            <span className='block mt-0.5'>
              A broader measure than the total on the left, so the two do not
              divide into each other.
            </span>
          </p>
        </div>

        <div className='figure-cell p-5 md:p-6'>
          <p className='figure-label'>{t('home.hero.risk_level')}</p>
          <p className={`mt-4 font-mono text-3xl font-semibold uppercase leading-none tracking-[0.04em] ${isHigh ? 'text-gov-copper' : riskLevel ? 'text-gov-gold' : 'text-neutral-muted'}`}>
            {riskLevel
              ? /^in debt distress$/i.test(riskLevel)
                ? riskLevel
                : `${riskLevel} ${t('home.hero.risk_suffix')}`
              : t('home.hero.risk_unassessed_value')}
          </p>
          {/* The four ratings of the IMF–World Bank LIC Debt Sustainability
              Framework, which is the scale the value above is on. */}
          <div className='mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] uppercase tracking-[0.08em] text-neutral-muted'>
            <span className='inline-flex items-center gap-1'><span className='h-2 w-2 bg-emerald-600' />Low</span>
            <span className='inline-flex items-center gap-1'><span className='h-2 w-2 bg-gov-gold' />Moderate</span>
            <span className='inline-flex items-center gap-1'><span className='h-2 w-2 bg-gov-copper' />High</span>
            <span className='inline-flex items-center gap-1'><span className='h-2 w-2 bg-gov-copper' />In distress</span>
          </div>
          <p className='mt-3 text-xs leading-snug text-neutral-muted'>
            {dsa ? (
              <>
              <a
                href={dsaHref(dsa)}
                title={dsaCitation(dsa)}
                target='_blank'
                rel='noopener noreferrer'
                className='underline hover:no-underline'>
                {dsaSourceLabel(dsa)}
              </a>
              <span className="block mt-1">{dsaVintageLabel(dsa)}</span>
              </>
            ) : (
              t('home.hero.risk_unassessed_reason')
            )}
          </p>
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
  const fyLabel = fy?.fiscal_year || '—';

  const healthTier = fy ? 'unassessed' : 'loading';
  const tier = { dot: 'bg-gray-400', ring: 'ring-gray-400/20', text: 'text-neutral-muted',
    label: fy ? 'Risk not assessed from this ratio' : '...' };

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
                value={fmtFiscal(fy.debt_service_source?.url ? fy.debt_service_cost : null, fy.unit)}
                sub={
                  !fy.debt_service_source?.url || fy.debt_service_per_shilling == null
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

            <div className='mt-1 px-2 py-3 rounded-lg bg-white/50 dark:bg-surface-elevated border border-gray-100 dark:border-neutral-border'>
              <p className='text-xs'>Nominal debt-to-GDP: {debtToGdp != null ? `${debtToGdp.toFixed(1)}%` : '—'}</p>
              <p className='text-[11px] text-neutral-muted mt-1'>
                The {anchorLine}% statutory anchor uses present value. A comparable ratio is unavailable.
              </p>
            </div>

            {/* ── Where the Money Goes — budget breakdown bar ── */}
            {(() => {
              // One column of Treasury's fiscal framework, drawn against that
              // column's own total (issue #237). This used to draw against
              // appropriated_budget (COB gross — counts principal redemption,
              // excludes counties), subtract interest-PLUS-principal from a
              // recurrent figure holding interest only, and push the gap into
              // "Other". Every segment is now a printed line; the parts sum to
              // the total; absent or unreconciled -> withheld, never zeros.
              // The framework is already in KSh billion.
              const uses = frameworkUses(frameworkOf(fy));
              if (!uses) return null;
              const total = uses.total;

              const segments = [
                {
                  label: t('home.govcard.seg_recurrent'),
                  value: uses.recurrentExInterest,
                  color: 'bg-gov-forest',
                  dot: 'bg-gov-forest',
                },
                {
                  label: t('home.govcard.seg_interest'),
                  value: uses.interest,
                  color: 'bg-gov-copper',
                  dot: 'bg-gov-copper',
                },
                {
                  label: t('home.govcard.seg_development'),
                  value: uses.development,
                  color: 'bg-gov-gold',
                  dot: 'bg-gov-gold',
                },
                { label: t('home.govcard.seg_counties'), value: uses.counties, color: 'bg-[#0D7377]', dot: 'bg-[#0D7377]' },
                {
                  label: t('home.govcard.seg_contingency'),
                  value: uses.contingency,
                  color: 'bg-gray-300',
                  dot: 'bg-gray-300',
                },
              ].filter((seg) => seg.value > 0);

              return (
                <div className='px-2 py-2.5 rounded-lg bg-white/50 dark:bg-surface-elevated border border-gray-100 dark:border-neutral-border'>
                  <span className='text-[11px] uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 font-semibold block mb-2'>
                    {t('home.govcard.where_money_goes')}
                  </span>
                  <span className='text-[11px] text-gray-500 dark:text-neutral-muted/80 block -mt-1.5 mb-2'>
                    {t('home.govcard.framework_total').replace(
                      '{total}',
                      total >= 1000 ? `${(total / 1000).toFixed(2)}T` : `${total.toFixed(0)}B`
                    )}
                  </span>
                  {/* Stacked horizontal bar */}
                  <div className='flex h-3 rounded-full overflow-hidden gap-[1px]'>
                    {segments.map((seg) => (
                      <div
                        key={seg.label}
                        className={`${seg.color} transition-[width] duration-500 first:rounded-l-full last:rounded-r-full`}
                        style={{ width: `${((seg.value / total) * 100).toFixed(1)}%` }}
                        title={`${seg.label}: KES ${(seg.value / 1000).toFixed(1)}T (${(seg.value / total) * 100 < 0.1 ? '<0.1' : ((seg.value / total) * 100).toFixed(0)}%)`}
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
                          {(seg.value / total) * 100 < 0.1 ? '<0.1' : ((seg.value / total) * 100).toFixed(0)}%
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
