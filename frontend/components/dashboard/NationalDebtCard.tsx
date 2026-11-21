'use client';

import FigureEvidence from '@/components/evidence/FigureEvidence';
import { publishedHeadlineRatio, headlineRatioDisclosure, publishedTimelineRatio, debtRatioDisclosure } from '@/lib/debt/qualification';
import { isModelledObservation, type Qualifications } from '@/lib/evidence/qualification';
import { DebtTimelineEntry } from '@/lib/api/debt';
import { dsaCitation, dsaHref, dsaIsAlarm, dsaSourceLabel, dsaVintageLabel, readDsaRating } from '@/lib/debt/dsaRating';
import { toRawKES } from '@/lib/utils';
import { useLang } from '@/lib/i18n/LangProvider';
import {
  useDebtTimeline,
  useNationalDebtOverview,
} from '@/lib/react-query/useDebt';
import Link from 'next/link';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { Skeleton } from '@/components/ui/Skeleton';
import { AlertTriangle, BarChart3, Globe2, Landmark, Loader2, MapPinned, TrendingUp } from 'lucide-react';
import { useMemo } from 'react';
import { gdpRatioComparison } from '@/lib/debt/debtCardBasis';
import {
  displayedSplit,
  externalShare,
  reconcileExternalDomestic,
} from '@/lib/debt/externalDomesticSplit';
import InfoTip from '@/components/InfoTip';
import NationalDebtChart, { type ChartEntry } from './NationalDebtChart';

/** Legacy export retained for callers; numeric shape never establishes origin. */
export function isRoundNumberEstimate(e: {
  external: number | null; domestic: number | null; total: number | null; qualifications?: Qualifications;
}): boolean {
  return isModelledObservation(e.qualifications);
}

/**
 * ChartEntry money fields are BILLIONS — `NationalDebtChart`'s `fmtT` divides
 * by 1000 for trillions and its tick formatter renders bare values as `${v}B`.
 *
 * The rows arriving here are not. Since the stage1 3a migration /debt/timeline
 * serves raw KES and declares it per row with `unit: "KES"`; a pre-migration
 * backend serves bare billions with no unit field. This previously passed both
 * through with the comment "already in billions from API", which was true
 * until the migration and 10⁹× wrong after it.
 *
 * So: normalise to raw KES on the DECLARED unit — never by guessing a value's
 * magnitude — then convert once to the billions the chart reads. Doing it here
 * also fixes the headline fallbacks below, which read `lastYear` and are
 * correct precisely when this function's output really is billions.
 *
 * Reported as F1 on PR #136, and confirmed the hard way: this migration was
 * applied to production on 2026-08-30 and rolled back within the hour.
 */
function toChartData(timeline: DebtTimelineEntry[]): ChartEntry[] {
  const toBillions = (v: number | null, unit?: string | null): number | null => {
    const raw = toRawKES(v, unit);
    return raw == null ? null : raw / 1e9;
  };
  return timeline.map((e) => {
    const row = {
      qualifications: e.qualifications,
      year: String(e.year),
      external: toBillions(e.external, e.unit),
      domestic: toBillions(e.domestic, e.unit),
      total: toBillions(e.total, e.unit),
      gdpRatio: publishedTimelineRatio(e),
      stockMonth: e.period?.stock_as_of_month,
      gdpYear: e.period?.gdp_calendar_year,
    };
    return { ...row, modelled: isRoundNumberEstimate(row) };
  });
}
/** `val` is typed nullable on purpose: the values flowing in derive from an
 *  `any`-typed API response, so TypeScript cannot catch an unguarded call —
 *  and did not. The CI production build did, prerendering `/` with no backend:
 *  `Cannot read properties of null (reading 'toLocaleString')`. */
function fmtKES(val: number | null | undefined): string {
  if (val == null) return '—';
  if (val >= 1_000_000_000_000)
    return `KES ${(val / 1_000_000_000_000).toFixed(2)}T`;
  if (val >= 1_000_000_000) return `KES ${(val / 1_000_000_000).toFixed(0)}B`;
  return `KES ${val.toLocaleString()}`;
}

export default function NationalDebtCard() {
  const { t } = useLang();
  const { data: resp, isLoading } = useNationalDebtOverview();
  const { data: timelineResp, isLoading: isTimelineLoading } = useDebtTimeline();
  const { data: fiscal } = useFiscalSummary();

  // Transform API timeline → chart data (memoised)
  const debtTimeline = useMemo<ChartEntry[]>(() => {
    if (!timelineResp?.timeline?.length) return [];
    return toChartData(timelineResp.timeline);
  }, [timelineResp]);

  // Extract live values from API, fallback to latest timeline entry
  const apiData = resp?.data || resp;
  const sustainability = apiData?.debt_sustainability || {};
  const debtServiceRatio =
    fiscal?.current?.debt_service_per_shilling ?? null;

  const firstYear = debtTimeline[0];
  const lastYear = debtTimeline[debtTimeline.length - 1];

  // Derive headline numbers from the authoritative /debt/national endpoint
  // (loans-table sum — same source /debt page uses) so home and the debt
  // detail page agree. Fall back to the last timeline year only if the
  // authoritative value is missing.
  const totalDebt =
    apiData?.total_outstanding ?? apiData?.total_debt ?? (lastYear?.total != null ? lastYear.total * 1_000_000_000 : null);
  const headlineRatio = publishedHeadlineRatio(apiData);
  const gdpRatio = headlineRatio ?? lastYear?.gdpRatio ?? null;
  const rawLastYear = timelineResp?.timeline?.[timelineResp.timeline.length - 1];
  const ratioBasis = headlineRatio != null
    ? headlineRatioDisclosure(apiData)
    : debtRatioDisclosure(rawLastYear);

  // Absence is not a risk band. This was `|| 'High'`, so an API that reported
  // no assessment rendered the WORST rating. That was a claim about the
  // public finances manufactured from a missing field (G3 on PR #135).
  //
  // The rating is the joint IMF–World Bank DSA's, cited, or nothing (issue
  // #269). The fallback of banding debt-to-GDP at an uncited 40/60 is gone.
  // So is the backend's `risk_level`, which was debt-to-GDP > 65 and was
  // captioned here as the IMF's classification.
  const dsa = readDsaRating(sustainability);
  const riskLevel: string | null = dsa?.overall_risk_of_debt_distress ?? null;
  // External vs domestic split.
  //
  // `summary.external_debt` is NOT the sum of the external creditors this site
  // publishes. The backend computes that sum, then overwrites it with the
  // register TOTAL re-split by a proportion taken from the DebtTimeline table
  // — a different table on a different date. In production the two answers
  // differ by KSh 467.7Bn (5.27T here vs 4.80T across /debt's creditor cards),
  // so these tiles named a figure that describes no set of rows on the site,
  // and a reader following them to /debt found cards that do not add up to it.
  //
  // The reconciler prefers the register's own sum whenever the two disagree
  // and reports the gap so the disclosure below can state it. When the backend
  // fix lands and they agree, `reconciles` goes true and this reverts to the
  // API's own figures with no further change here. See
  // lib/debt/externalDomesticSplit.
  const splitReconciliation = useMemo(
    () => reconcileExternalDomestic(apiData?.categories, apiData?.summary),
    [apiData?.categories, apiData?.summary],
  );
  const shownSplit = displayedSplit(splitReconciliation);
  const timelineSplit =
    lastYear && lastYear.external != null && lastYear.domestic != null
      ? { external: lastYear.external * 1_000_000_000, domestic: lastYear.domestic * 1_000_000_000 }
      : null;
  const split = shownSplit ?? timelineSplit;
  const externalDebt = split ? split.external : null;
  const domesticDebt = split ? split.domestic : null;
  // Shares of (external + domestic) so the two always sum to exactly 100%.
  // Rounding each independently off the total previously produced 100.2%
  // (51.5% + 48.7%).
  //
  // The split only exists when BOTH sides are known. With one side missing it
  // used to fall back to 0, which rendered "0% of total" and a "0% / 0%"
  // split beside an em-dash value — a fabricated statistic presented with the
  // same confidence as a real one. Absent inputs now yield null and every
  // consumer renders "—".
  const externalPct = externalShare(split);
  const domesticPct = externalPct != null ? +(100 - externalPct).toFixed(1) : null;
  // The gap is only disclosed when the tiles beside it are the register's own
  // sum — i.e. when the page has actually chosen one of two disagreeing
  // answers on the reader's behalf and owes them that fact.
  const splitGapKes =
    !splitReconciliation.reconciles && shownSplit === splitReconciliation.register
      ? splitReconciliation.gapKes
      : null;

  // Both derived claims must start from the earliest SOURCED year, not the
  // earliest year on the chart. Anchoring "4.0× since 2013" and "From 58.4% in
  // 2013" to a round-number estimate published a growth story built on an
  // invented base — and it understated the real rise (F13).
  const firstSourced = debtTimeline.find((e) => ['qualified', 'verified'].includes(e.qualifications?.total?.status ?? '')) ?? null;
  // A "from X% in YEAR" comparison is only defensible when the base and the
  // displayed value are on the SAME basis — see lib/debt/debtCardBasis.
  const firstRatio = debtTimeline.find(e => e.gdpRatio != null);
  const gdpComparison = gdpRatio == null ? null : gdpRatioComparison(headlineRatio, firstRatio);
  const modelledYears = debtTimeline.filter((e) => e.modelled);
  const growthMultiple =
    firstSourced?.total != null && lastYear?.total != null && firstSourced.total > 0
      ? (lastYear.total / firstSourced.total).toFixed(1)
      : '—';
  const growthBaseYear = firstSourced?.year ?? '—';
  const yearRange = firstYear && lastYear ? `${firstYear.year}–${lastYear.year}` : '—';
  const hasTimeline = debtTimeline.length > 0;

  return (
    <section aria-labelledby='home-national-debt-heading' className='audit-panel flex h-full min-w-0 flex-col'>
      <div className='px-6 sm:px-8'><FigureEvidence label='debt timeline observations' labelKey='evidence.label.timeline_observations' rows={Object.fromEntries(debtTimeline.map(row => [row.year, row.qualifications ?? {}]))} /></div>
      {/* Header */}
      <div className='bg-surface-sunken/45 px-6 sm:px-8 pt-5 pb-4 border-b border-neutral-border'>
        <div className='flex items-start justify-between'>
          <div>
            <h2 id='home-national-debt-heading' className='font-display text-xl sm:text-2xl text-gov-dark dark:text-white mb-1'>
              {t('home.debt.title')}
            </h2>
            <p className='text-xs text-neutral-muted'>
              {t('home.debt.source_note').replace('{range}', yearRange)}
            </p>
            {/* Say which years on this chart are not readings. Derived from the
                data, so the sentence shrinks and then disappears as years get
                re-sourced. */}
            {modelledYears.length > 0 && (
              <p className='mt-1 text-sm text-neutral-muted'>
                {t('home.debt.chart_modelled_years').replace('{years}', modelledYears.map(row => row.year).join(', '))}
              </p>
            )}
          </div>
          {isLoading || isTimelineLoading ? (
            <Loader2 className='w-4 h-4 animate-spin text-neutral-muted/40 mt-1' />
          ) : null}
        </div>
      </div>

      {/* Reconciliation divergence — surfaced on home too (audit §2.1/§4), not
          just /debt. Renders only when the two debt sources disagree materially. */}
      {apiData?.reconciliation?.status === 'divergent' && (
        <div className='mx-6 sm:mx-8 mt-3 flex items-start gap-2 rounded-sm border border-amber-400/50 bg-amber-50/70 dark:bg-amber-500/10 px-3 py-2'>
          <AlertTriangle className='w-3.5 h-3.5 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0' />
          {/* `primary_source` / `secondary_source` are internal table names
              (`loans_table`, `debt_timeline_table`). They were being printed to
              the public. The divergence is worth telling the reader about; the
              schema is not. */}
          <p className='text-[11px] leading-snug text-amber-800 dark:text-amber-200'>
            Two official figures for this total differ by{' '}
            {Math.abs(Number(apiData.reconciliation.percent_diff) || 0).toFixed(1)}%
            and we cannot yet say which is right.{' '}
            <Link href='/debt' className='font-semibold underline hover:no-underline'>
              See both figures
            </Link>
            .
          </p>
        </div>
      )}

      {/* Stat cards row */}
      <div className='px-6 sm:px-8 pt-5 pb-2'>
        <div className='grid grid-cols-2 sm:grid-cols-4 gap-3'>
          <StatCard
            icon={<Landmark className='w-3.5 h-3.5 text-gov-copper opacity-70' />}
            label={t('home.debt.total_public')}
            value={totalDebt != null ? fmtKES(totalDebt) : '—'}
            sub={t('home.debt.growth_sub')
              .replace('{x}', String(growthMultiple))
              .replace('{year}', String(growthBaseYear))}
            accent='copper'
          />
          <StatCard
            icon={<TrendingUp className='w-3.5 h-3.5 text-gov-gold opacity-70' />}
            label={
              <div className='flex items-center gap-1'>
                <span>{t('home.debt.tooltip_gdp')}</span>
                <InfoTip term='debt-to-gdp' size={11} />
              </div>
            }
            value={gdpRatio != null ? `${gdpRatio}%` : '—'}
            sub={[
              gdpComparison
                ? t('home.debt.from_year_sub')
                    .replace('{pct}', String(gdpComparison.pct))
                    .replace('{year}', String(gdpComparison.year))
                : null,
              ratioBasis,
            ].filter(Boolean).join(' · ') || 'No sourced stock/GDP pair available'}
            accent='gold'
          />
          <StatCard
            icon={<Globe2 className='w-3.5 h-3.5 text-gov-forest dark:text-emerald-100' />}
            label={
              <div className='flex items-center gap-1'>
                <span>{t('home.debt.external_label')}</span>
                <InfoTip term='external-debt' size={11} />
              </div>
            }
            value={externalDebt != null ? fmtKES(externalDebt) : '—'}
            sub={
              externalPct != null
                ? t('home.debt.pct_of_total').replace('{pct}', String(externalPct))
                : '—'
            }
            accent='forest'
          />
          <StatCard
            icon={<MapPinned className='w-3.5 h-3.5 text-gov-sage' />}
            label={
              <div className='flex items-center gap-1'>
                <span>{t('home.debt.domestic_label')}</span>
                <InfoTip term='domestic-debt' size={11} />
              </div>
            }
            value={domesticDebt != null ? fmtKES(domesticDebt) : '—'}
            sub={
              domesticPct != null
                ? t('home.debt.pct_of_total').replace('{pct}', String(domesticPct))
                : '\u2014'
            }
            accent='sage'
          />
        </div>

        {/* Two answers, one question. The API's `summary` split and the sum of
            the creditor categories on /debt disagree; the tiles above show the
            latter, because it is the one that describes rows this site
            publishes. Saying so is not optional — without it a reader takes
            the tiles for the composition of the register and finds /debt's
            cards adding to something else. Disappears when the two agree. */}
        {splitGapKes != null && (
          <p className='mt-3 text-[11px] leading-snug text-neutral-muted'>
            <span className='font-semibold text-gov-dark dark:text-white'>
              Two sources disagree by {fmtKES(splitGapKes)}.
            </span>{' '}
            The figures above are our own creditor rows added up — the same rows{' '}
            <Link href='/debt' className='underline hover:no-underline'>
              /debt
            </Link>{' '}
            breaks down by lender. The API also reports a split derived from the
            CBK aggregate series, which puts external debt {fmtKES(splitGapKes)}{' '}
            higher. Neither is reconciled to a source document.
          </p>
        )}

        {/* The "IMF broader measure … includes counties, SOEs, pending bills"
            callout was withdrawn (credibility audit F8). It described the IMF
            General-Government figure as BROADER than the headline while
            rendering it 1.26T SMALLER — a claim that refutes itself in the
            same sentence. The IMF series is still ingested and is a legitimate
            second measure; it needs a presentation that states which is larger
            and why, not one that asserts a composition the numbers contradict. */}
      </div>

      {/* Chart */}
      <div className='px-4 sm:px-6 pt-3 pb-2 flex-1 min-h-0'>
        {isTimelineLoading ? (
          <div className='h-64 sm:h-72 flex flex-col justify-end gap-2 px-2'>
            <div className='flex items-end gap-1 h-full'>
              {[68, 45, 72, 38, 55, 82, 60, 50].map((h, i) => (
                <Skeleton
                  key={i}
                  className='flex-1 rounded-t-sm'
                  style={{ height: `${h}%` }}
                />
              ))}
            </div>
            <Skeleton className='h-2 w-full' />
          </div>
        ) : !hasTimeline ? (
          <div className='h-64 sm:h-72 flex items-center justify-center text-neutral-muted text-sm'>
            {t('home.debt.no_timeline')}
          </div>
        ) : (
          <NationalDebtChart data={debtTimeline} />
        )}
      </div>

      {/* Bottom insights bar */}
      <div className='px-6 sm:px-8 py-4 mt-auto border-t border-neutral-border bg-surface-sunken/30'>
        <div className='grid grid-cols-1 sm:grid-cols-3 gap-4'>
          <InsightPill
            icon={<Landmark className='w-4 h-4 text-gov-sage' />}
            title={t('home.debt.cents_of_revenue').replace('{n}', String(debtServiceRatio ?? '\u2014'))}
            desc={t('home.debt.insight_service')}
          />
          <InsightPill
            icon={<BarChart3 className='w-4 h-4 text-gov-gold' />}
            title={
              domesticPct != null && externalPct != null
                ? `${domesticPct}% / ${externalPct}%`
                : '—'
            }
            desc={t('home.debt.insight_split')}
          />
          {/* The alarm treatment (copper icon, highlight) is for a rating of
              High or In debt distress. A lower rating renders neutral, and a
              missing one renders "not assessed". */}
          <InsightPill
            icon={
              <AlertTriangle
                className={`w-4 h-4 ${
                  dsaIsAlarm(dsa) ? 'text-gov-copper' : 'text-neutral-muted'
                }`}
              />
            }
            title={
              riskLevel
                ? t('home.debt.insight_risk_label').replace('{level}', riskLevel)
                : t('home.debt.insight_risk_unassessed')
            }
            desc={
              dsa ? (
                <>
                  {t('home.debt.insight_risk_desc')} ·{' '}
                  <a
                    href={dsaHref(dsa)}
                    title={dsaCitation(dsa)}
                    target='_blank'
                    rel='noopener noreferrer'
                    className='underline hover:no-underline'>
                    {dsaSourceLabel(dsa)}
                  </a>
                  <span className='block mt-1'>{dsaVintageLabel(dsa)}</span>
                </>
              ) : (
                t('home.debt.insight_risk_unassessed_desc')
              )
            }
            highlight={dsaIsAlarm(dsa)}
          />
        </div>
      </div>
    </section>
  );
}

/* ── Sub-components ── */

function StatCard({
  icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: React.ReactNode;
  label: React.ReactNode;
  value: string;
  sub: string;
  accent: string;
}) {
  const bgMap: Record<string, string> = {
    copper: 'bg-gov-copper/[0.04]',
    gold: 'bg-gov-gold/[0.05]',
    forest: 'bg-gov-forest/[0.04]',
    sage: 'bg-gov-sage/[0.06]',
  };
  const textMap: Record<string, string> = {
    copper: 'text-gov-copper',
    gold: 'text-gov-gold',
    forest: 'text-gov-forest dark:text-emerald-100',
    sage: 'text-gov-sage',
  };
  return (
    <div
      className={`rounded-sm ${bgMap[accent] || bgMap.copper} border border-neutral-border/30 px-3 py-2.5`}>
      <div className='flex items-center gap-1.5 mb-1'>
        {icon}
        <span className='text-[11px] text-neutral-muted font-medium uppercase tracking-wider leading-none'>
          {label}
        </span>
      </div>
      <span
        className={`text-sm font-bold ${textMap[accent] || textMap.copper} tabular-nums leading-none block`}>
        {value}
      </span>
      <span className='text-[11px] text-neutral-muted mt-0.5 block'>{sub}</span>
    </div>
  );
}

function InsightPill({
  icon,
  title,
  desc,
  highlight,
}: {
  icon: React.ReactNode;
  title: string;
  desc: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <div
      className={`flex items-start gap-2.5 ${highlight ? 'bg-gov-copper/[0.04] rounded-sm px-2.5 py-1.5 -mx-1' : ''}`}>
      <span className='text-base mt-0.5 flex-shrink-0' suppressHydrationWarning>
        {typeof icon === 'string' ? icon : icon}
      </span>
      <div>
        <span
          className={`text-xs font-semibold block ${highlight ? 'text-gov-copper' : 'text-gov-dark dark:text-white'}`}>
          {title}
        </span>
        <span className='text-[11px] text-neutral-muted leading-tight'>{desc}</span>
      </div>
    </div>
  );
}
