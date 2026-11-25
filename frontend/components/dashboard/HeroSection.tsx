'use client';

import { KenyaFlag } from '@/components/ui/KenyaFlag';
import Link from 'next/link';
import { Skeleton } from '@/components/ui/Skeleton';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { useLang } from '@/lib/i18n/LangProvider';
import { HOME_TOPICS_MESSAGES } from '@/lib/i18n/messages/homeTopics';
import { frameworkOf, frameworkUses } from '@/lib/fiscal/framework';
import { fmtBillionKES, toRawKES } from '@/lib/utils';
import {
  Banknote,
  BarChart3,
  Loader2,
  type LucideIcon,
  Scale,
  TrendingDown,
} from 'lucide-react';
import HomeCountySearch from './HomeCountySearch';

/* ── Formatting helpers ── */
// fmtBillionKES imported from @/lib/utils — expects billions input (FiscalSummary data)

const TOPIC_LINKS = [
  ['home.topics.debt', '/debt'],
  ['home.topics.budget', '/budget'],
  ['home.topics.counties', '/counties'],
  ['home.topics.audits', '/audits'],
] as const;

export default function HeroSection() {
  const { lang, t } = useLang();
  return (
    <section aria-labelledby='home-hero-title' className='border-b border-neutral-border bg-gov-sand pt-[var(--public-page-top-offset)] dark:bg-surface-sunken'>
      <div className='mx-auto max-w-dashboard px-4 py-4 sm:px-6 sm:py-8 lg:px-8 lg:py-10'>
        <h1 id='home-hero-title' className='max-w-[17rem] text-pretty font-display text-[1.875rem] font-bold uppercase leading-none sm:max-w-none sm:text-audit-title lg:text-audit-hero'>
          {HOME_TOPICS_MESSAGES['home.topics.hero_title'][lang]}
        </h1>
        <p className='mt-1.5 text-audit-control text-neutral-muted sm:text-audit-body'>
          {HOME_TOPICS_MESSAGES['home.topics.hero_description'][lang]}
        </p>

        <nav aria-labelledby='home-topic-title' className='mt-3 sm:mt-5'>
          <h2 id='home-topic-title' className='text-audit-control font-semibold'>
            {HOME_TOPICS_MESSAGES['home.topics.heading'][lang]}
          </h2>
          <ul role='list' className='mt-2 flex flex-wrap gap-2'>
            {TOPIC_LINKS.map(([label, href]) => (
              <li key={href}>
                <Link href={href} className='inline-flex min-h-11 min-w-11 items-center rounded-full border border-neutral-border bg-surface-base px-3 py-1.5 text-audit-label font-semibold underline-offset-4 hover:underline'>
                  {HOME_TOPICS_MESSAGES[label][lang]}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <HomeCountySearch />

        <div className='mt-3 flex flex-wrap items-center gap-x-3 text-audit-caption text-neutral-muted'>
          <p>{HOME_TOPICS_MESSAGES['home.topics.publishers'][lang]}</p>
          <Link href='/sources' className='inline-flex min-h-11 min-w-11 items-center text-audit-control font-medium text-gov-sage underline underline-offset-4'>
            {t('shell.footer_sources')}
          </Link>
        </div>
      </div>
    </section>
  );
}

export { default as SummaryStrip } from './HomeDebtSummary';

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
