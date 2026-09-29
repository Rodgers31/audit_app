'use client';
import { readDsaRating, dsaIsAlarm, dsaSourceLabel, dsaVintageLabel, dsaHref, dsaCitation } from '@/lib/debt/dsaRating';

import { toRawKES } from '@/lib/utils';
import DataFreshnessBadge from '@/components/DataFreshnessBadge';
import DataIntegrityBanner from '@/components/DataIntegrityBanner';
import InfoTip from '@/components/InfoTip';
import { PageSkeleton } from '@/components/ui/Skeleton';
import PageShell from '@/components/layout/PageShell';
import PDFExportButton from '@/components/PDFExportButton';
import LenderTreemap from '@/components/debt/LenderTreemap';
import MaturityLadder from '@/components/debt/MaturityLadder';
import {
  useDebtTimeline,
  useNationalDebtOverview,
  useNationalLoans,
  usePendingBills,
  usePendingBillsSummary,
} from '@/lib/react-query/useDebt';
import { buildDebtServiceSeries, yearMissingRevenue } from '@/lib/debt/debtServiceSeries';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { apiClient } from '@/lib/api/axios';
import type { NationalLoan, PendingBillsSource } from '@/lib/api/debt';
import {
  computeRevenueAllocation,
  fiscalSourceLine,
  formatHeadlineKes,
  ratioWorking,
} from '@/lib/debt/revenueAllocation';
import { annualCostCell, rateCell, sortLoans } from '@/lib/debt/loanInterest';
import { motion, useMotionValue, useTransform, animate } from 'framer-motion';
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BadgeDollarSign,
  Building2,
  ChevronDown,
  ChevronUp,
  CircleDollarSign,
  FileWarning,
  Flame,
  Gauge,
  Scale,
  ShieldAlert,
  TrendingUp,
  Users,
} from 'lucide-react';
import {
  toTreemapCategories,
  treemapTotal,
} from '@/lib/debt/lenderTreemapAdapter';
import { formatAsAt } from '@/lib/counties/pendingBillsNotes';
import { displayLenderName } from '@/lib/debt/lenderName';
import {
  agingDistributionSupport,
  agingUnsupportedNote,
  normalizeAgingBuckets,
} from '@/lib/debt/pendingBillsAging';
import { useEffect, useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

/* ═══════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════ */

function fmtT(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return '—';
  if (val >= 1_000_000_000_000) return `${(val / 1_000_000_000_000).toFixed(2)}T`;
  if (val >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(1)}B`;
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  return val.toLocaleString();
}

function fmtKES(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return '—';
  return `KES ${fmtT(val)}`;
}

function pct(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return '—';
  return `${val.toFixed(1)}%`;
}

function sourceText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function sourceHref(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
}

function pendingAmount(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
}

function sameNames(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((name) => right.includes(name));
}

function PendingBillsSourceLine({ date, source }: { date: string | null; source?: PendingBillsSource }) {
  const href = sourceHref(source?.url);
  return (
    <div className='mt-1 text-xs leading-relaxed text-neutral-muted break-words'>
      {date ? `at ${formatAsAt(date, 'en')}` : 'Date unavailable'}
      {' · '}
      {href ? (
        <a href={href} target='_blank' rel='noopener noreferrer' className='underline underline-offset-2 hover:text-gov-copper'>
          {source?.title || 'Source document'}
        </a>
      ) : (
        <span>{source?.title ? `${source.title} · ` : ''}Source link unavailable</span>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   Animated number — counts up on mount, tabular-nums
   ═══════════════════════════════════════════════════════ */

function AnimatedCurrency({
  value,
  duration = 1.6,
  className = '',
}: {
  value: number;
  duration?: number;
  className?: string;
}) {
  const mv = useMotionValue(value * 0.6);
  const display = useTransform(mv, (v) => {
    if (v >= 1_000_000_000_000) return `KES ${(v / 1_000_000_000_000).toFixed(2)}T`;
    if (v >= 1_000_000_000) return `KES ${(v / 1_000_000_000).toFixed(1)}B`;
    return `KES ${Math.round(v).toLocaleString()}`;
  });

  useEffect(() => {
    const controls = animate(mv, value, { duration, ease: [0.22, 1, 0.36, 1] });
    return () => controls.stop();
  }, [value, duration, mv]);

  return <motion.span className={`tabular-nums ${className}`}>{display}</motion.span>;
}

/* RingGauge was removed with the sustainability gauges (F5/F10). */

function Sparkline({
  data,
  color = '#C94A4A',
  height = 40,
}: {
  data: number[];
  color?: string;
  height?: number;
}) {
  if (data.length < 2) return null;
  const series = data.map((v, i) => ({ i, v }));
  return (
    <div style={{ height }} className='w-full'>
      <ResponsiveContainer>
        <AreaChart data={series} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <defs>
            <linearGradient id='spark-grad' x1='0' y1='0' x2='0' y2='1'>
              <stop offset='0%' stopColor={color} stopOpacity={0.45} />
              <stop offset='100%' stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <Area
            type='monotone'
            dataKey='v'
            stroke={color}
            strokeWidth={2}
            fill='url(#spark-grad)'
            dot={false}
            isAnimationActive
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   Register cells — a figure, its basis tag, or "—" with the reason.
   See lib/debt/loanInterest for the rules (issue #235).
   ═══════════════════════════════════════════════════════ */

function FigureText({
  cell,
  kind,
  className = '',
}: {
  cell: ReturnType<typeof rateCell>;
  kind: 'rate' | 'kes';
  className?: string;
}) {
  if (cell.value == null) {
    return (
      <span className={`${className} text-neutral-muted`} title={cell.title} aria-label={`Not published: ${cell.title}`}>
        —
      </span>
    );
  }
  return (
    <span className={className} title={cell.title}>
      {kind === 'rate' ? `${cell.value.toFixed(2)}%` : fmtKES(cell.value)}
      {cell.tag && (
        <span className='ml-1 text-[10px] font-normal text-neutral-muted'>{cell.tag}</span>
      )}
    </span>
  );
}

function RateTd({ loan }: { loan: NationalLoan }) {
  return (
    <td className='px-4 py-3 text-xs text-right'>
      <FigureText cell={rateCell(loan)} kind='rate' className='text-gov-copper tabular-nums' />
    </td>
  );
}

function CostTd({ loan }: { loan: NationalLoan }) {
  return (
    <td className='px-4 py-3 text-xs text-right'>
      <FigureText cell={annualCostCell(loan)} kind='kes' className='text-neutral-muted tabular-nums' />
    </td>
  );
}

/* ═══════════════════════════════════════════════════════
   MAIN PAGE
   ═══════════════════════════════════════════════════════ */

export default function NationalDebtPage() {
  const {
    data: overview,
    isLoading: ovLoading,
    isError: ovError,
    refetch: refetchOverview,
  } = useNationalDebtOverview();

  const backendReady = !!overview;

  const {
    data: loansResp,
    isLoading: loansLoading,
    isError: loansError,
    refetch: refetchLoans,
  } = useNationalLoans({ enabled: backendReady });
  const {
    data: timelineResp,
    isLoading: tlLoading,
    isError: tlError,
    refetch: refetchTimeline,
  } = useDebtTimeline({ enabled: backendReady });
  const { data: fiscalResp } = useFiscalSummary({ enabled: backendReady });
  const { data: pendingBillsData, isError: pendingBillsError } = usePendingBills({ enabled: backendReady });
  const { data: rawPendingBillsSummary } = usePendingBillsSummary({ enabled: backendReady });

  /* ── Normalize pending bills summary (API returns dicts) ── */
  const pendingBillsSummary = useMemo(() => {
    if (!rawPendingBillsSummary) return null;
    const raw = rawPendingBillsSummary as any;
    const totalPending = raw.total_pending_amount;

    let breakdownByType = raw.breakdown_by_type;
    if (breakdownByType && !Array.isArray(breakdownByType)) {
      breakdownByType = Object.entries(breakdownByType).map(([type, amount]: [string, any]) => ({
        type,
        amount: Number(amount) || 0,
        percentage: totalPending != null && totalPending > 0 ? ((Number(amount) || 0) / totalPending) * 100 : 0,
      }));
    }

    // Shared with the county Budget tab so both surfaces hand the same shape
    // to the same guard — a component that normalised on its own could
    // otherwise bypass it.
    const agingBuckets = normalizeAgingBuckets(raw.aging_buckets, totalPending);

    const rawTopCounties = raw.top_counties_by_amount || [];
    const topCounties = rawTopCounties.filter((c: any) => pendingAmount(c.amount) != null).map((c: any) => ({
      ...c,
      county_name: c.county_name || c.county || 'Unknown',
      county_id: c.county_id || c.entity_id || c.id,
    }));

    return {
      ...raw,
      breakdown_by_type: breakdownByType || [],
      aging_buckets: agingBuckets,
      top_counties_by_amount: topCounties,
      invalid_ranking_amounts: rawTopCounties.length - topCounties.length,
    };
  }, [rawPendingBillsSummary]);

  /* The sustainability normaliser was removed with the gauges and the peer
     strip (F5/F10). It contained the `?? 0` that turned Kenya's null
     debt-service-to-revenue into a published 0.0%. */

  const [loanSort, setLoanSort] = useState<'outstanding' | 'rate' | 'service'>('outstanding');
  const [fetchedPopulation, setFetchedPopulation] = useState<number | null>(null);
  const [pbView, setPbView] = useState<'national' | 'counties'>('national');
  const [showAllLoans, setShowAllLoans] = useState(false);

  useEffect(() => {
    if (!backendReady) return;
    const controller = new AbortController();
    apiClient
      .get('/economic/population/latest', { signal: controller.signal })
      .then((res) => {
        if (!controller.signal.aborted) setFetchedPopulation(res.data?.population ?? null);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFetchedPopulation(null);
      });
    return () => controller.abort();
  }, [backendReady]);

  /* ── Derived data ── */
  const d = useMemo(() => {
    const api = overview?.data || overview || {};
    const hasData = Object.keys(api).length > 0;
    const totalDebt = api.total_outstanding ?? api.total_debt ?? null;
    const gdp = api.gdp ?? null;
    // The API declares the ratio's measure and observation year. The register
    // total and GDP can be from different periods; they cannot fill its absence.
    const gdpRatio =
      typeof api.debt_to_gdp_ratio === 'number' &&
      Number.isFinite(api.debt_to_gdp_ratio) && api.debt_to_gdp_ratio >= 0
        ? api.debt_to_gdp_ratio : null;
    const summary = api.summary || {};
    const categories = api.categories || {};
    const population = fetchedPopulation || api.population || null;
    const perCapita = totalDebt != null && totalDebt > 0 && population ? totalDebt / population : null;
    const asOf = api.as_of || api.last_updated || null;
    const source = api.source || 'CBK / Treasury';
    const reconciliation = api.reconciliation || null;
    const lastUpdated = overview?.last_updated || api.last_updated || null;

    return {
      hasData,
      totalDebt,
      gdp,
      gdpRatio,
      gdpRatioYear:
        typeof api.debt_to_gdp_year === 'number' && Number.isInteger(api.debt_to_gdp_year) &&
        api.debt_to_gdp_year >= 1000 && api.debt_to_gdp_year <= 9999
          ? api.debt_to_gdp_year : null,
      gdpRatioBasis: sourceText(api.debt_to_gdp_basis),
      gdpRatioSource: sourceText(api.debt_to_gdp_source),
      summary,
      categories,
      loanCount: api.loan_count ?? null,
      perCapita,
      population,
      externalDebt: summary.external_debt ?? null,
      domesticDebt: summary.domestic_debt ?? null,
      externalPct: summary.external_percentage ?? null,
      domesticPct: summary.domestic_percentage ?? null,
      asOf,
      source,
      reconciliation,
      lastUpdated,
    };
  }, [overview, fetchedPopulation]);

  // Absent rates and costs sort LAST. The old comparator read them as 0,
  // which ranked "no publisher gives a rate" as "the cheapest loan".
  const loans = useMemo(
    () => (loansResp?.loans ? sortLoans(loansResp.loans, loanSort) : []),
    [loansResp, loanSort]
  );

  // Normalise both series to RAW KES once, on each row's declared unit
  // (raw KES since the stage1 3a migration; bare billions from an older
  // backend). Everything below works in raw KES.
  const timeline = useMemo(
    () =>
      (timelineResp?.timeline || []).map((t) => ({
        ...t,
        external: toRawKES(t.external, t.unit) ?? 0,
        domestic: toRawKES(t.domestic, t.unit) ?? 0,
        total: toRawKES(t.total, t.unit) ?? 0,
        gdp: t.gdp != null ? (toRawKES(t.gdp, t.unit) ?? 0) : t.gdp,
      })),
    [timelineResp]
  );

  const fiscal = useMemo(() => {
    if (!fiscalResp) return null;
    const normalise = (y: any) =>
      y && {
        ...y,
        appropriated_budget: toRawKES(y.appropriated_budget, y.unit),
        total_revenue: toRawKES(y.total_revenue, y.unit),
        // The same figure in billions, so the revenue card can check it IS
        // the fiscal framework's ordinary revenue (which is in billions).
        total_revenue_billion:
          toRawKES(y.total_revenue, y.unit) == null
            ? null
            : toRawKES(y.total_revenue, y.unit)! / 1e9,
        tax_revenue: toRawKES(y.tax_revenue, y.unit),
        non_tax_revenue: toRawKES(y.non_tax_revenue, y.unit),
        total_borrowing: toRawKES(y.total_borrowing, y.unit),
        debt_service_cost: toRawKES(y.debt_service_cost, y.unit),
        // debt_ceiling / actual_debt are no longer published: the KES 10T
        // ceiling was repealed in 2023, and actual_debt duplicated
        // debt_timeline with the superseded pre-correction values (F31).
        development_spending: toRawKES(y.development_spending, y.unit),
        recurrent_spending: toRawKES(y.recurrent_spending, y.unit),
        county_allocation: toRawKES(y.county_allocation, y.unit),
      };
    const years = (fiscalResp.history || []).map(normalise);
    const current = normalise(fiscalResp.current) || years[years.length - 1];
    return { current, years };
  }, [fiscalResp]);

  const yoyGrowth = useMemo(() => {
    if (timeline.length < 2) return null;
    const last = timeline[timeline.length - 1];
    const prev = timeline[timeline.length - 2];
    const change = ((last.total - prev.total) / prev.total) * 100;
    return { change, amount: last.total - prev.total, year: last.year };
  }, [timeline]);

  const pb = useMemo(() => {
    if (!pendingBillsData || pendingBillsData.status !== 'success') return null;
    const s = pendingBillsData.summary;
    return {
      total: s.total_pending,
      national: s.national_total,
      county: s.county_total,
      totalAbsentReason: s.total_absent_reason,
      reportedCountySum: s.reported_county_sum,
      coverage: s.coverage,
      count: s.record_count,
      bills: pendingBillsData.pending_bills || [],
      source: pendingBillsData.source,
      sourceUrl: pendingBillsData.source_url,
      sources: pendingBillsData.sources || [],
      // The day each half is a stock on. Since #238 they can differ by a
      // year — national from the BROP, counties from the CoB — and then the
      // API withholds the total, so the page says why.
      nationalAsAt: s.national_as_at ?? null,
      countyAsAt: s.county_as_at ?? null,
    };
  }, [pendingBillsData]);

  /* ── Treemap data adapter ── */
  //
  // Two things this fixes.
  //
  // 1. The slices used to sum to 106.9%. `percentage_of_total` comes from the
  //    backend divided by a total that EXCLUDES pending bills, while pending
  //    bills were rendered as one of the parts (credibility audit F25). Shares
  //    are now computed here, over the categories actually drawn, so the parts
  //    make the whole by construction.
  //
  // 2. Pending bills are not in the chart at all. They are unpaid obligations,
  //    not borrowed money — the backend's own `_is_debt_loan` says exactly
  //    that and keeps them out of every debt total. Charting them beside
  //    Treasury bonds double-counted them against the page's own "Stalled
  //    payments" section, which is where they belong.
  // Adapter lives in lib/debt/lenderTreemapAdapter so its rules are unit-
  // tested against the shipped code rather than a copy of it.
  const lenderCategories = useMemo(
    () => toTreemapCategories(d.categories),
    [d.categories]
  );

  // The denominator the treemap actually divides by, so the component can
  // print the number its percentages are of rather than inheriting a total
  // that includes something it does not draw.
  const treemapTotalValue = useMemo(
    () => treemapTotal(lenderCategories),
    [lenderCategories]
  );

  const dsa = readDsaRating((overview?.data || overview)?.debt_sustainability);

  /* ── Revenue allocation (per KES 100 of revenue — authoritative) ──
     APDMR-style framing: tax + non-tax revenue as denominator, total
     debt service (interest + principal redemptions) as numerator.
     Backend exposes the pre-computed ratio in
     `debt_service_per_shilling`; we fall back to (ds / rev) × 100 only
     if it's missing.
     Framed as "per 100 of revenue" because:
       – Revenue doesn't fund the whole budget (borrowing covers the gap)
       – Debt service is a first-call charge BEFORE anything else
       – Revenue-based framing lets citizens see how much of their taxes
         the debt actually consumes before a single school is funded.
     The math itself lives in lib/debt/revenueAllocation.ts so it can be
     unit-tested in isolation. */
  const taxAllocation = useMemo(
    () => computeRevenueAllocation(fiscal?.current),
    [fiscal],
  );

  /* ── Loading / Error states ── */
  const isLoading = ovLoading || loansLoading || tlLoading;
  const isError = ovError || loansError || tlError;

  if (isLoading) {
    return (
      <PageShell title="Kenya's National Debt" subtitle='Pulling the latest numbers from CBK, Treasury and COB…'>
        <PageSkeleton />
      </PageShell>
    );
  }

  if (isError) {
    return (
      <PageShell title="Kenya's National Debt" subtitle='Data temporarily unavailable.'>
        <div className='flex flex-col items-center justify-center py-20 text-center'>
          <AlertTriangle size={48} className='text-gov-copper mb-4' />
          <h3 className='text-lg font-semibold text-gov-dark dark:text-white mb-1'>Failed to load debt data</h3>
          <p className='text-sm text-neutral-muted mb-5 max-w-md'>
            Upstream sources (CBK, Treasury) may be slow. You can retry without leaving the page.
          </p>
          <button
            onClick={() => {
              refetchOverview();
              refetchLoans();
              refetchTimeline();
            }}
            className='btn btn-primary'>
            Retry fetch
          </button>
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Kenya's National Debt"
      subtitle='Every shilling owed, every lender named, every cent of interest — so you can hold power to account.'>
      {!d.hasData && (
        <DataIntegrityBanner
          severity='warning'
          message='The backend returned no debt-overview record. Sections below may be blank until the seeding pipeline publishes fresh numbers.'
        />
      )}

      <div className='flex flex-wrap items-center justify-between gap-3'>
        <DataFreshnessBadge sources='CBK/Treasury' variant='inline' />
        <PDFExportButton />
      </div>

      {/* ═══════════ SECTION 1 — DEBT CLOCK HERO ═══════════ */}
      <motion.section
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className='relative overflow-hidden rounded-2xl bg-gradient-to-br from-gov-dark via-gov-forest to-gov-dark text-white p-6 sm:p-8'>
        <div
          className='absolute inset-0 opacity-20 pointer-events-none'
          aria-hidden='true'
          style={{
            backgroundImage:
              'radial-gradient(circle at 20% 20%, rgba(217,164,65,0.25), transparent 40%), radial-gradient(circle at 80% 80%, rgba(201,74,74,0.22), transparent 45%)',
          }}
        />
        <div className='relative grid grid-cols-1 lg:grid-cols-[1.35fr_1fr] gap-6 lg:gap-8 items-center'>
          <div>
            <div className='flex items-center gap-2 mb-3'>
              <Flame className='text-gov-gold' size={18} />
              <span className='text-[11px] uppercase tracking-[0.2em] font-semibold text-gov-gold/90'>
                Live national debt counter
              </span>
            </div>
            <div className='metric-hero leading-none'>
              {d.totalDebt != null ? (
                <AnimatedCurrency value={d.totalDebt} />
              ) : (
                <span className='opacity-50'>KES —</span>
              )}
            </div>
            <p className='mt-3 text-white/70 text-sm sm:text-base max-w-xl'>
              Outstanding public debt — money borrowed by the Kenyan government that must be
              repaid, with interest, from taxes you pay.
            </p>
            {yoyGrowth && (
              <div className='mt-4 flex flex-wrap items-center gap-2 text-sm'>
                <span
                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full font-semibold ${
                    yoyGrowth.change >= 0
                      ? 'bg-gov-copper/20 text-gov-copper border border-gov-copper/40'
                      : 'bg-gov-sage/20 text-gov-sage border border-gov-sage/40'
                  }`}>
                  {yoyGrowth.change >= 0 ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
                  {yoyGrowth.change >= 0 ? '+' : ''}
                  {yoyGrowth.change.toFixed(1)}% YoY
                </span>
                <span className='text-white/70'>
                  Added KES {fmtT(Math.abs(yoyGrowth.amount))} in {yoyGrowth.year}
                </span>
              </div>
            )}
            {timeline.length > 1 && (
              <div className='mt-4'>
                <p className='text-[11px] uppercase tracking-wider text-white/50 mb-1'>
                  10-year trajectory
                </p>
                <Sparkline data={timeline.map((t) => t.total)} color='#D9A441' height={48} />
              </div>
            )}
          </div>

          <div className='grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-1 gap-3'>
            <div className='rounded-xl bg-white/8 backdrop-blur border border-white/15 p-4'>
              <div className='flex items-center gap-2 text-[11px] uppercase tracking-wider text-white/60 mb-1.5'>
                <Users size={12} />
                Per citizen
              </div>
              <div className='text-2xl sm:text-3xl font-bold text-white tabular-nums'>
                {d.perCapita != null ? `KES ${Math.round(d.perCapita).toLocaleString()}` : '—'}
              </div>
              <p className='text-[11px] text-white/50 mt-1'>
                If every Kenyan paid an equal share
              </p>
            </div>
            <div className='rounded-xl bg-white/8 backdrop-blur border border-white/15 p-4'>
              <div className='flex items-center gap-2 text-[11px] uppercase tracking-wider text-white/60 mb-1.5'>
                <Scale size={12} />
                Debt-to-GDP
                <InfoTip term='debt-to-gdp' size={11} />
              </div>
              <div className='text-2xl sm:text-3xl font-bold text-white tabular-nums'>
                {d.gdpRatio != null ? pct(d.gdpRatio) : 'Not published'}
              </div>
              {d.gdpRatio != null ? (
                <p className='text-[11px] text-white/70 mt-1'>
                  <span className='block'>Nominal debt · {d.gdpRatioBasis || 'Basis unavailable'}</span>
                  <span className='block mt-1'>
                    {d.gdpRatioSource || 'Source unavailable'} ·{' '}
                    {d.gdpRatioYear != null ? `Observation: ${d.gdpRatioYear}` : 'Observation year unavailable'}
                  </span>
                </p>
              ) : (
                <p className='text-[11px] text-white/70 mt-1'>No debt-to-GDP observation received.</p>
              )}
            </div>
            <div className='rounded-xl bg-white/8 backdrop-blur border border-white/15 p-4'>
              <div className='flex items-center gap-2 text-[11px] uppercase tracking-wider text-white/60 mb-1.5'>
                <ShieldAlert size={12} />
                Overall risk of debt distress
              </div>
              <div className='flex items-center gap-2'>
                <span
                  className={`text-2xl sm:text-3xl font-bold ${
                    dsaIsAlarm(dsa) ? 'text-gov-copper' : 'text-white/50'
                  }`}>
                  {dsa ? dsa.overall_risk_of_debt_distress : 'Not assessed'}
                </span>
              </div>
              <p className='text-[11px] text-white/50 mt-1'>
                {dsa ? <>
                  <a href={dsaHref(dsa)} title={dsaCitation(dsa)} target='_blank' rel='noopener noreferrer' className='underline'>{dsaSourceLabel(dsa)}</a>
                  <span className='block mt-1'>{dsaVintageLabel(dsa)}</span>
                </> : 'No published assessment received.'}
              </p>
            </div>
          </div>
        </div>
      </motion.section>

      {/* ═══════════ SECTION 1B — SOURCE DIVERGENCE ═══════════
          What used to sit here was withdrawn (credibility audit F8/F9):

          • A "Two measures of public debt" dual card that labelled the IMF
            General-Government figure the BROADER measure — "includes counties,
            SOE debt, pension arrears, and pending bills" — while rendering it
            1.26T SMALLER than the Treasury/CBK figure beside it. A broader
            measure that is smaller refutes itself on sight.

          • An "Audit trail" strip claiming our headline came from the CBK
            Statistical Bulletin "June 2025 issue" (a static string the code's
            own TODO admitted was hardcoded; the seeded source is the December
            2025 issue), and describing the gap as "typical for line-level vs.
            roll-up data" — then, on expand, attributing it to forex
            revaluation, T-bills in transit and unbooked pending bills. None of
            that is supported: the backend's own note says the two tables are
            seeded from different source documents, and every mechanism listed
            would make the aggregate LARGER, not smaller.

          The divergence itself is real and worth telling the reader about, so
          the warning stays — stripped back to what can actually be shown: two
          numbers, the gap between them, and the fact that we cannot yet say
          which is right. No internal table names (the old copy printed
          `loans_table` and `debt_timeline_table` to the public). */}
      {d.reconciliation &&
        d.reconciliation.primary_value_kes != null &&
        d.reconciliation.secondary_value_kes != null &&
        d.reconciliation.status === 'divergent' && (
          <section className='rounded-xl border border-amber-400/50 bg-amber-50/70 dark:bg-amber-500/10 px-5 py-4'>
            <div className='flex items-start gap-2.5'>
              <AlertTriangle className='w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0' />
              <div className='text-[12.5px] leading-relaxed text-amber-900 dark:text-amber-200'>
                <span className='font-semibold'>
                  Two official figures for this number disagree, and we cannot
                  yet say which is right.
                </span>{' '}
                Summing the individual instruments we hold gives{' '}
                {fmtT(d.reconciliation.primary_value_kes)}. The published
                aggregate for the same period is{' '}
                {fmtT(d.reconciliation.secondary_value_kes)} — a gap of{' '}
                {(d.reconciliation.percent_diff ?? 0).toFixed(1)}%. The larger
                figure is used as the headline on this page. Treat both as
                provisional until the instrument register is reconciled against
                the published aggregate.
              </div>
            </div>
          </section>
        )}

      {/* ═══════════ SECTION 2 — WHO KENYA OWES ═══════════ */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-80px' }}
        transition={{ duration: 0.5 }}
        className='space-y-4'>
        <div>
          <h2 className='font-display text-2xl sm:text-3xl text-gov-dark dark:text-white flex items-center gap-2'>
            <Building2 className='text-gov-forest dark:text-emerald-100' size={24} />
            Who Kenya owes
          </h2>
          <p className='text-sm text-neutral-muted mt-1'>
            The debt broken down by lender category — foreign creditors (external) vs. local banks
            and pension funds (domestic). Hover to compare.
          </p>
        </div>
        <LenderTreemap
          categories={lenderCategories}
          totalOutstanding={treemapTotalValue}
        />
      </motion.section>

      {/* ═══════════ SECTION 3 — MATURITY LADDER ═══════════
          Restored on real instrument data. The withdrawn version drew its
          walls from 3 of 28 register rows and filed amortising multilateral
          credits as "revolving" (credibility audit F24). This reads the CBK
          bond register: individual securities with their own maturity dates
          and coupons. The component renders its own absent state and its own
          scope caveat — the bars are ~60% of the domestic bond book and no
          part of the external one. */}
      <MaturityLadder />

      {/* ═══════════ SECTIONS 4 & 5 — PEERS + SUSTAINABILITY (withdrawn) ═══════════
          Both were withdrawn (credibility audit F5/F10/F26).

          The peer strip and the "Service / Revenue" gauge shared one root
          cause: the backend fills them from World Bank indicators that measure
          something else. GC.XPN.INTP.RV.ZS is titled by the World Bank
          "Interest payments (% of revenue)" — interest only, no principal —
          and was rendered as "% of tax revenue going to debt repayment"
          against an IMF 30% DEBT-SERVICE threshold. DT.DOD.DECT.GN.ZS is
          "External debt stocks (% of GNI)" and was rendered as "% of debt held
          by foreign lenders", so Rwanda's 94%-of-GNI read as 94%-of-its-debt.
          Kenya's own service ratio arrives null and was rendered 0.0%, placing
          Kenya below every peer on the metric where it is worst.

          The debt-to-GDP column mixed five bases in one chart: Ethiopia's 31%
          is World Bank central-government debt from 2019 (IMF WEO 2025 says
          43.1, and Ethiopia has been in default since Dec 2023, yet it was
          labelled "Within sustainable band"); Uganda's is World Bank 2024;
          Tanzania's and Rwanda's are hardcoded fallback constants in
          backend/main.py; Kenya's is our own CBK-derived ratio. The panel was
          titled "EAC peer average" while including Ethiopia, which is not an
          EAC member, and omitting Burundi, South Sudan, DRC and Somalia, which
          are.

          The 5-year projection was a straight-line least-squares extrapolation
          of our own series (+0.3pp/yr), published beside an IMF WEO projection
          we already ingest and which says something different.

          Restore per-metric, each against the indicator it actually names. */}

      {/* ═══════════ SECTION 6 — REVENUE ALLOCATION ═══════════ */}
      {taxAllocation && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.5 }}
          className='space-y-4'>
          <div>
            <h2 className='font-display text-2xl sm:text-3xl text-gov-dark dark:text-white flex items-center gap-2'>
              <CircleDollarSign className='text-gov-forest dark:text-emerald-100' size={24} />
              Where every KES 100 of revenue goes
            </h2>
            <p className='text-sm text-neutral-muted mt-1'>
              Kenya&rsquo;s revenue ({taxAllocation.fiscalYear}) doesn&rsquo;t cover the whole
              budget — debt service is a <span className='font-semibold text-gov-copper'>first-call
              charge</span>, paid before anything else. What&rsquo;s left funds the rest; the
              shortfall is borrowed.
            </p>
          </div>

          <div className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface overflow-hidden'>
            {/* Headline row */}
            <div className='grid grid-cols-1 lg:grid-cols-[1.1fr_1.4fr]'>
              {/* Left: dramatic headline */}
              <div className='relative p-6 sm:p-8 bg-gradient-to-br from-gov-copper/12 via-gov-copper/6 to-white border-b lg:border-b-0 lg:border-r border-neutral-border/40'>
                <div className='text-[11px] uppercase tracking-[0.2em] font-semibold text-gov-copper mb-2'>
                  Debt service takes about
                </div>
                <div className='flex items-baseline gap-2 leading-none'>
                  <span
                    className='text-[64px] sm:text-[88px] font-extrabold text-gov-copper tabular-nums tracking-tight'
                    data-testid='debt-headline-kes'>
                    {formatHeadlineKes(taxAllocation.debtServicePerRev)}
                  </span>
                  <span className='text-2xl sm:text-3xl font-bold text-gov-copper/70'>KES</span>
                </div>
                <div className='text-sm text-gov-dark dark:text-white font-medium mt-2'>
                  out of every <span className='font-bold'>KES 100</span> collected in
                  tax &amp; non-tax revenue
                </div>
                {/* An "Above IMF 30% ceiling" pill sat here, unconditionally.
                    No IMF threshold applies to this ratio: it is TOTAL debt
                    service (domestic + external, interest + principal) over
                    revenue, and the IMF-World Bank LIC-DSF debt-service-to-
                    revenue thresholds (14/18/23% by debt-carrying capacity)
                    are for EXTERNAL public debt service only. A comparison
                    that cannot be made honestly is not made (issue #235). */}
                <p className='text-[11px] text-neutral-muted mt-3 leading-relaxed max-w-sm'>
                  {fiscalSourceLine(fiscal?.current)} Uses tax &amp; non-tax
                  revenue; debt figure includes total debt service
                  (interest + principal redemptions).
                </p>
                <details className='group mt-3 max-w-sm'>
                  <summary className='flex items-center gap-1.5 cursor-pointer list-none text-[11px] font-semibold text-gov-forest dark:text-emerald-300 hover:underline'>
                    <ChevronDown
                      size={12}
                      className='transition-transform group-open:rotate-180'
                    />
                    How this is calculated
                  </summary>
                  <div className='mt-2 pl-5 text-[11px] text-neutral-muted leading-relaxed space-y-2'>
                    {/* `ds` and `rev` are RAW KES here (normalised above).
                        This divided them by 1,000 and labelled the result
                        trillions, which would have printed ~2315884392.206T
                        — unseen only because the card never rendered for
                        a year without a split (#237). */}
                    <p>
                      Calculated as {taxAllocation.fiscalYear}{' '}
                      {ratioWorking(taxAllocation)}, the Treasury APDMR
                      definition. It counts principal repaid on maturing
                      loans as well as interest; the bar below counts interest
                      only, because principal is refinanced rather than
                      spent.
                    </p>
                    <p>
                      Different official debt-service measures may give
                      lower or higher figures depending on the numerator
                      or denominator used, but this card sticks to the
                      seeded fiscal-summary ratio so the page stays
                      internally consistent.
                    </p>
                  </div>
                </details>
              </div>

              {/* Right: coin split visual */}
              <div className='p-6 sm:p-8'>
                <div className='text-[11px] uppercase tracking-[0.2em] font-semibold text-neutral-muted mb-4'>
                  Your 100-shilling coin, split
                </div>

                {/* 10 coins grid — each coin = 10% */}
                <div className='flex flex-wrap gap-1.5 mb-4'>
                  {Array.from({ length: 10 }).map((_, i) => {
                    const filledPct = Math.min(
                      10,
                      Math.max(0, taxAllocation.debtServicePerRev - i * 10)
                    );
                    const partial = filledPct / 10;
                    return (
                      <motion.div
                        key={i}
                        initial={{ scale: 0, opacity: 0 }}
                        whileInView={{ scale: 1, opacity: 1 }}
                        viewport={{ once: true }}
                        transition={{ delay: i * 0.04, duration: 0.3 }}
                        className='relative w-10 h-10 sm:w-12 sm:h-12 rounded-full border-2 border-gov-copper/30 bg-gov-cream dark:bg-surface-sunken overflow-hidden flex items-center justify-center shadow-sm'>
                        {/* Filled portion for debt service */}
                        <div
                          className='absolute inset-0 bg-gradient-to-br from-gov-copper to-[#8C2E2E]'
                          style={{
                            clipPath: `inset(${100 - partial * 100}% 0 0 0)`,
                          }}
                        />
                        <span
                          className={`relative text-[11px] sm:text-xs font-bold ${
                            partial > 0.5 ? 'text-white' : 'text-gov-copper'
                          }`}>
                          {i * 10 + 10}
                        </span>
                      </motion.div>
                    );
                  })}
                </div>

                <div className='flex items-center gap-2 text-[11px]'>
                  <span className='inline-block w-3 h-3 rounded-full bg-gov-copper' />
                  <span className='text-neutral-muted'>
                    Filled = total debt service per KES 100 of revenue (interest plus
                    principal repaid; most principal is refinanced, not spent)
                  </span>
                </div>
              </div>
            </div>

            {/* Breakdown bar — one column of Treasury's fiscal framework,
                per KES 100 of the same revenue (issue #237). No residual:
                the part above 100 is shown with what financed it. */}
            {taxAllocation.breakdown == null ? (
              <div className='px-6 sm:px-8 pb-6 sm:pb-8 pt-4 border-t border-neutral-border/30 text-[11px] text-neutral-muted'>
                How {taxAllocation.fiscalYear} spending divides is not published on the
                same basis as this revenue figure, so the breakdown is withheld rather
                than drawn from mixed measures.
              </div>
            ) : (
              (() => {
                const b = taxAllocation.breakdown!;
                const segs = [
                  { key: 'int', val: b.interestPerRev, color: 'bg-gov-copper', label: 'Interest on debt' },
                  { key: 'rec', val: b.recPerRev, color: 'bg-gov-forest', label: 'Recurrent (ex-interest)' },
                  { key: 'dev', val: b.devPerRev, color: 'bg-gov-sage', label: 'Development' },
                  { key: 'cty', val: b.countiesPerRev, color: 'bg-gov-gold', label: 'Counties' },
                  { key: 'con', val: b.contingencyPerRev, color: 'bg-neutral-muted/50', label: 'Contingency fund' },
                ];
                const financed = [
                  { label: 'A-i-A', val: b.aiaPerRev },
                  { label: 'grants', val: b.grantsPerRev },
                  { label: 'net borrowing', val: b.borrowingPerRev },
                  ...(Math.abs(b.cashAdjustmentPerRev) >= 0.05
                    ? [{ label: 'cash-basis adjustment & statistical discrepancy', val: b.cashAdjustmentPerRev }]
                    : []),
                ];
                return (
                  <div className='px-6 sm:px-8 pb-6 sm:pb-8 pt-4 border-t border-neutral-border/30'>
                    <div className='flex items-center justify-between mb-2 gap-3'>
                      <span className='text-xs font-semibold text-gov-dark dark:text-white'>
                        Spending per KES 100 of revenue: {b.spendingPerRev.toFixed(1)}
                      </span>
                      <span className='text-[11px] text-neutral-muted text-right'>
                        The {Math.max(b.spendingPerRev - 100, 0).toFixed(1)} above 100 is
                        financed by{' '}
                        {financed.map((f) => `${f.label} (${f.val.toFixed(1)})`).join(', ')}.
                      </span>
                    </div>
                    <div className='flex w-full h-10 rounded-lg overflow-hidden shadow-sm border border-neutral-border/30'>
                      {segs.map((seg) => {
                        const w = (seg.val / b.spendingPerRev) * 100;
                        return (
                          <div
                            key={seg.key}
                            className={`${seg.color} flex items-center justify-center text-white text-[11px] font-bold`}
                            style={{ width: `${w}%` }}
                            title={`${seg.label}: KES ${seg.val.toFixed(1)} per 100 of revenue`}>
                            {w > 10 ? `${seg.val.toFixed(0)}` : ''}
                          </div>
                        );
                      })}
                    </div>
                    <div className='grid grid-cols-2 sm:grid-cols-5 gap-x-3 gap-y-1.5 mt-3 text-[11px]'>
                      {segs.map((row) => (
                        <div key={row.key} className='flex items-center gap-1.5'>
                          <span className={`w-2.5 h-2.5 rounded-sm ${row.color}`} />
                          <span className='text-neutral-muted truncate'>{row.label}</span>
                          <span className='ml-auto font-bold text-gov-dark dark:text-white tabular-nums'>
                            {/* One decimal: the legend must visibly sum to the total above. */}
                            {row.val.toFixed(1)}
                          </span>
                        </div>
                      ))}
                    </div>
                    <p className='mt-3 text-[11px] text-neutral-muted leading-relaxed'>
                      Treasury fiscal framework, {fiscal?.current?.fiscal_framework?.source?.edition ?? 'Budget Summary'},{' '}
                      {fiscal?.current?.fiscal_framework?.source?.page}. Interest is the debt
                      line here because it is the part inside spending; the headline
                      above also counts principal repaid.
                    </p>
                  </div>
                );
              })()
            )}
          </div>
        </motion.section>
      )}

      {/* ═══════════ SECTION 7 — PENDING BILLS AGING ═══════════ */}
      {(pendingBillsData?.status === 'no_data' || (!pendingBillsData && pendingBillsError) ||
        (pendingBillsData && pendingBillsData.status !== 'success')) && (
        <section className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-5 sm:p-6'>
          <h2 className='font-display text-2xl sm:text-3xl text-gov-dark dark:text-white flex items-center gap-2'>
            <FileWarning className='text-gov-forest dark:text-emerald-100' size={24} />
            Stalled payments
            <InfoTip term='pending-bills' size={14} />
          </h2>
          <p className='mt-3 text-sm text-neutral-muted'>
            {pendingBillsData?.status === 'no_data'
              ? 'No pending-bills figure is published here. National, county and combined totals are unavailable.'
              : 'Pending-bills information is temporarily unavailable. No total can be confirmed.'}
          </p>
        </section>
      )}
      {pb && (() => {
        // No split without a total: the API withholds it unless national and
        // county are both published and stated at one date, and a half over
        // nothing is not a share.
        const buckets = pendingBillsSummary?.aging_buckets || [];
        // Whether an aging distribution may be DRAWN at all. This used to draw
        // the chart unconditionally and append a caveat under it — a solid bar
        // reading "180d+ · KES 1.11T" with a note beneath saying the backend
        // made it up. A reader takes the chart; the note is the small print.
        // The same guard now runs on /counties/[id], so one rule governs both
        // surfaces. See lib/debt/pendingBillsAging.
        const agingSupport = agingDistributionSupport(buckets, pendingBillsSummary);
        const nationalSource = pb.sources.find((source) => source.side === 'national');
        const countySource = pb.sources.find((source) => source.side === 'county');
        const qualifiedCount = pb.coverage?.qualified_counties.length ?? 0;
        const rankingCoverage = pendingBillsSummary?.coverage;
        const rankingCoverageAgrees = !!pb.coverage && !!rankingCoverage &&
          pb.coverage.county_count === rankingCoverage.county_count &&
          pb.coverage.county_expected === rankingCoverage.county_expected &&
          pb.coverage.county_complete === rankingCoverage.county_complete &&
          sameNames(pb.coverage.missing_counties, rankingCoverage.missing_counties) &&
          sameNames(pb.coverage.qualified_counties, rankingCoverage.qualified_counties);
        const sourceSummaryConflict = !!pendingBillsSummary && (
          pendingBillsSummary.total_pending_amount !== pb.total ||
          (!!pb.coverage && !!rankingCoverage && !rankingCoverageAgrees)
        );
        const national = pb.coverage?.national_complete === false ? null : pendingAmount(pb.national);
        const county = pb.coverage?.county_complete === false ? null : pendingAmount(pb.county);
        const reportedCountySum = pendingAmount(pb.reportedCountySum);
        const publishedTotal = pendingAmount(pb.total);
        const statedAtOneDate = !!pb.nationalAsAt && pb.nationalAsAt === pb.countyAsAt;
        const total = !sourceSummaryConflict &&
          pb.coverage?.national_complete === true && pb.coverage.county_complete === true &&
          national != null && county != null && statedAtOneDate &&
          sourceHref(nationalSource?.url) && sourceHref(countySource?.url) &&
          publishedTotal != null && Math.abs(publishedTotal - national - county) <= 1
            ? publishedTotal : null;
        const splitOf = (part: number | null) =>
          total != null && total > 0 && part != null ? (part / total) * 100 : 0;
        const nationalPct = splitOf(national);
        const countyPct = splitOf(county);
        const rankingIsComplete = rankingCoverage?.county_complete === true &&
          rankingCoverage.qualified_counties.length === 0 && rankingCoverageAgrees &&
          pendingBillsSummary.invalid_ranking_amounts === 0;
        return (
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.5 }}
            className='space-y-4'>
            <div className='flex flex-wrap items-start justify-between gap-3'>
              <div>
                <h2 className='font-display text-2xl sm:text-3xl text-gov-dark dark:text-white flex items-center gap-2'>
                  <FileWarning className='text-gov-forest dark:text-emerald-100' size={24} />
                  Stalled payments
                  <InfoTip term='pending-bills' size={14} />
                </h2>
                <p className='text-sm text-neutral-muted mt-1'>
                  Money already owed to suppliers, contractors and staff — but not yet paid. Older
                  bills are a signal of cashflow distress.
                </p>
              </div>
              <div className='inline-flex rounded-lg bg-white dark:bg-surface-base border border-neutral-border/40 p-1 shadow-sm'>
                <button
                  onClick={() => setPbView('national')}
                  aria-pressed={pbView === 'national'}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                    pbView === 'national' ? 'bg-gov-dark text-white' : 'text-gov-dark dark:text-white hover:bg-neutral-border/30'
                  }`}>
                  National
                </button>
                <button
                  onClick={() => setPbView('counties')}
                  aria-pressed={pbView === 'counties'}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                    pbView === 'counties' ? 'bg-gov-dark text-white' : 'text-gov-dark dark:text-white hover:bg-neutral-border/30'
                  }`}>
                  Counties
                </button>
              </div>
            </div>

            {/* Unified hero card with total + split + entities */}
            <div className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface overflow-hidden'>
              <div className='grid grid-cols-1 lg:grid-cols-[1.1fr_1.5fr]'>
                {/* Big total */}
                <div className='relative p-6 sm:p-8 bg-gradient-to-br from-gov-copper/10 via-gov-copper/4 to-white border-b lg:border-b-0 lg:border-r border-neutral-border/40'>
                  <div className='text-[11px] uppercase tracking-[0.2em] font-semibold text-gov-copper mb-2'>
                    Total money owed, unpaid
                  </div>
                  <div className='text-4xl sm:text-5xl font-extrabold text-gov-dark dark:text-white tabular-nums tracking-tight leading-tight break-words'>
                    {fmtKES(total)}
                  </div>
                  {total == null && (
                    <p className='mt-2 text-xs leading-relaxed text-neutral-muted'>
                      {sourceSummaryConflict ? (
                        <>Combined total not published: the two pending-bills source summaries do not agree about the amount or coverage.</>
                      ) : pb.totalAbsentReason === 'incomplete_county_publication' ? (
                        <>
                          Combined total not published: county amounts cover{' '}
                          {pb.coverage ? `${pb.coverage.county_count} of ${pb.coverage.county_expected} counties` : 'an unconfirmed number of counties'}.
                          {qualifiedCount > 0 && ` ${qualifiedCount} ${qualifiedCount === 1 ? 'county has' : 'counties have'} qualified reported amounts.`}
                        </>
                      ) : pb.totalAbsentReason === 'incomplete_national_publication' ? (
                        <>Combined total not published: the national publication does not contain both required Treasury BROP components.
                          {pb.coverage?.county_complete === false && ' County publication is also incomplete or qualified.'}</>
                      ) : pb.totalAbsentReason === 'national_and_county_stated_at_different_dates' ? (
                        <>
                          Combined total not published: the national figure
                          {pb.nationalAsAt ? ` is at ${formatAsAt(pb.nationalAsAt, 'en')}` : ' has no stated date'} and the county figure
                          {pb.countyAsAt ? ` at ${formatAsAt(pb.countyAsAt, 'en')}` : ' has no stated date'}.
                        </>
                      ) : (
                        <>Combined total not published: complete coverage and a shared reporting date have not been confirmed.</>
                      )}
                    </p>
                  )}
                  <div className='mt-3 flex items-center gap-2 text-xs text-neutral-muted'>
                    <Users size={14} />
                    <span>
                      From{' '}
                      <span className='font-bold text-gov-dark dark:text-white tabular-nums'>
                        {pb.count.toLocaleString()}
                      </span>{' '}
                      published national and county records
                    </span>
                  </div>
                </div>

                {/* Split gauge */}
                <div className='p-6 sm:p-8'>
                  <div className='text-[11px] uppercase tracking-[0.2em] font-semibold text-neutral-muted mb-3'>
                    National vs. counties
                  </div>
                  {total != null && total > 0 && <div className='flex w-full h-10 rounded-lg overflow-hidden shadow-sm border border-neutral-border/30 mb-3'>
                    <div
                      className='bg-gov-copper flex items-center justify-center text-white text-xs font-bold'
                      style={{ width: `${nationalPct}%` }}
                      title={`National: ${fmtKES(national)} (${nationalPct.toFixed(0)}%)`}>
                      {nationalPct > 15 ? `${nationalPct.toFixed(0)}%` : ''}
                    </div>
                    <div
                      className='bg-gov-gold flex items-center justify-center text-white text-xs font-bold'
                      style={{ width: `${countyPct}%` }}
                      title={`Counties: ${fmtKES(county)} (${countyPct.toFixed(0)}%)`}>
                      {countyPct > 15 ? `${countyPct.toFixed(0)}%` : ''}
                    </div>
                  </div>}
                  <div className='grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-3'>
                    <div className='flex items-start gap-2.5'>
                      <span className='w-2.5 h-2.5 rounded-sm bg-gov-copper mt-1.5 flex-shrink-0' />
                      <div>
                        <div className='text-[11px] uppercase tracking-wider text-neutral-muted font-semibold'>
                          National
                        </div>
                        <div className='text-xl font-bold text-gov-dark dark:text-white tabular-nums'>
                          {fmtKES(national)}
                        </div>
                        <PendingBillsSourceLine date={pb.nationalAsAt} source={nationalSource} />
                      </div>
                    </div>
                    <div className='flex items-start gap-2.5'>
                      <span className='w-2.5 h-2.5 rounded-sm bg-gov-gold mt-1.5 flex-shrink-0' />
                      <div>
                        <div className='text-[11px] uppercase tracking-wider text-neutral-muted font-semibold'>
                          Counties
                        </div>
                        <div className='text-xl font-bold text-gov-dark dark:text-white tabular-nums'>
                          {fmtKES(county)}
                        </div>
                        {county == null && reportedCountySum != null && (
                          <div className='mt-2 text-xs leading-relaxed text-neutral-muted'>
                            Reported county sum: <span className='font-semibold text-gov-dark dark:text-white tabular-nums'>{fmtKES(reportedCountySum)}</span>
                            {' '}— {pb.coverage ? `${pb.coverage.county_count} of ${pb.coverage.county_expected} counties` : 'coverage unconfirmed'};
                            {qualifiedCount > 0 ? ' includes qualified reported amounts.' : ' not a complete county total.'}
                          </div>
                        )}
                        <PendingBillsSourceLine date={pb.countyAsAt} source={countySource} />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {agingSupport.supported && (
              <div className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-5 sm:p-6'>
                <div className='flex items-start justify-between gap-3 mb-4'>
                  <div>
                    <h3 className='text-sm font-semibold text-gov-dark dark:text-white'>
                      Aging — how long bills have gone unpaid
                    </h3>
                    {/* "Bills older than 180 days are referred to the Pending
                        Bills Verification Committee" was here. The committee's
                        mandate is national bills accumulated 1 June 2005 –
                        30 June 2022; there is no 180-day referral rule. */}
                  </div>
                </div>
                <ResponsiveContainer width='100%' height={220}>
                  <BarChart
                    data={buckets}
                    margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
                    <defs>
                      <linearGradient id='agingGrad0' x1='0' y1='0' x2='0' y2='1'>
                        <stop offset='0%' stopColor='#4A7C5C' stopOpacity={0.95} />
                        <stop offset='100%' stopColor='#2E5A3E' />
                      </linearGradient>
                      <linearGradient id='agingGrad1' x1='0' y1='0' x2='0' y2='1'>
                        <stop offset='0%' stopColor='#D9A441' stopOpacity={0.95} />
                        <stop offset='100%' stopColor='#BA8B33' />
                      </linearGradient>
                      <linearGradient id='agingGrad2' x1='0' y1='0' x2='0' y2='1'>
                        <stop offset='0%' stopColor='#E07B45' stopOpacity={0.95} />
                        <stop offset='100%' stopColor='#B05A2F' />
                      </linearGradient>
                      <linearGradient id='agingGrad3' x1='0' y1='0' x2='0' y2='1'>
                        <stop offset='0%' stopColor='#C94A4A' stopOpacity={0.95} />
                        <stop offset='100%' stopColor='#8C2E2E' />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray='3 3' stroke='#E2DDD5' vertical={false} />
                    <XAxis dataKey='bucket' tick={{ fill: '#4B5563', fontSize: 12, fontWeight: 500 }} tickLine={false} axisLine={{ stroke: '#E2DDD5' }} />
                    <YAxis
                      tickFormatter={(v) => fmtT(v)}
                      tick={{ fill: '#4B5563', fontSize: 11 }}
                      tickLine={false}
                      axisLine={{ stroke: '#E2DDD5' }}
                      width={60}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#ffffff',
                        border: '1px solid rgba(226,221,213,0.8)',
                        borderRadius: 12,
                        fontSize: 12,
                        boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
                      }}
                      formatter={(v: any) => fmtKES(Number(v))}
                    />
                    <Bar dataKey='amount' radius={[6, 6, 0, 0]}>
                      {buckets.map((b: any, i: number) => (
                        <Cell key={b.bucket} fill={`url(#agingGrad${Math.min(i, 3)})`} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* No distribution to draw. The panel still appears — the absence
                is itself a fact about the public record, and silently dropping
                the section would leave a reader assuming nobody had asked. */}
            {!agingSupport.supported && agingSupport.reason !== 'no-data' && (
              <div className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-5 sm:p-6'>
                <h3 className='text-sm font-semibold text-gov-dark dark:text-white'>
                  Aging — how long bills have gone unpaid
                </h3>
                <div className='mt-3 flex items-start gap-2 text-[11px] text-neutral-muted bg-gov-gold/8 border border-gov-gold/25 rounded-lg px-3 py-2'>
                  <AlertTriangle size={14} className='text-gov-gold flex-shrink-0 mt-0.5' />
                  <span>
                    <span className='font-semibold text-gov-dark dark:text-white'>Not published:</span>{' '}
                    {agingUnsupportedNote(agingSupport.reason, total != null)}
                  </span>
                </div>
              </div>
            )}

            {pbView === 'counties' && pendingBillsSummary?.top_counties_by_amount?.length > 0 && (
              <div className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-5 sm:p-6'>
                <h3 className='text-sm font-semibold text-gov-dark dark:text-white mb-4'>
                  {rankingIsComplete ? 'Top counties by stalled payments' : 'Reported counties by stalled payments'}
                </h3>
                {!rankingIsComplete && (
                  <p className='mb-4 text-xs leading-relaxed text-neutral-muted'>
                    {!rankingCoverageAgrees
                      ? 'Ranking includes counties with reported amounts; full coverage is unconfirmed because the source summaries do not agree.'
                      : `Ranking covers ${rankingCoverage.county_count} of ${rankingCoverage.county_expected} counties with reported amounts.`}
                    {rankingCoverageAgrees && rankingCoverage.qualified_counties.length > 0 &&
                      ` Ranking includes ${rankingCoverage.qualified_counties.length} ${rankingCoverage.qualified_counties.length === 1 ? 'county' : 'counties'} with qualified reported amounts.`}
                  </p>
                )}
                <div className='space-y-2.5'>
                  {pendingBillsSummary.top_counties_by_amount
                    .filter((c: any) => c.county_name !== 'National Government')
                    .slice(0, 8)
                    .map((c: any, i: number) => {
                      const filtered = pendingBillsSummary.top_counties_by_amount.filter(
                        (x: any) => x.county_name !== 'National Government'
                      );
                      const max = filtered[0]?.amount || 1;
                      const w = (c.amount / max) * 100;
                      return (
                        <div key={c.county_id || c.county_name} className='flex items-center gap-3'>
                          <span className='text-[11px] text-neutral-muted font-bold w-5 text-right tabular-nums'>
                            {i + 1}
                          </span>
                          <span className='text-xs font-medium text-gov-dark dark:text-white w-24 sm:w-32 min-w-0 truncate flex-shrink-0' title={c.county_name}>
                            {c.county_name}
                          </span>
                          <div className='flex-1 min-w-0 h-5 bg-neutral-border/20 rounded-md overflow-hidden'>
                            <motion.div
                              initial={{ width: 0 }}
                              whileInView={{ width: `${w}%` }}
                              viewport={{ once: true }}
                              transition={{ duration: 0.8, delay: i * 0.05 }}
                              className='h-full rounded-md bg-gradient-to-r from-gov-copper/80 to-gov-copper'
                            />
                          </div>
                          <span className='text-xs font-bold text-gov-dark dark:text-white tabular-nums w-16 sm:w-20 flex-shrink-0 text-right'>
                            {fmtT(c.amount)}
                          </span>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}
          </motion.section>
        );
      })()}

      {/* ═══════════ SECTION 8 — DEBT SERVICE TREND ═══════════ */}
      {fiscal?.years && fiscal.years.length > 1 && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.5 }}
          className='space-y-4'>
          <div>
            <h2 className='font-display text-2xl sm:text-3xl text-gov-dark dark:text-white flex items-center gap-2'>
              <TrendingUp className='text-gov-forest dark:text-emerald-100' size={24} />
              The cost of debt over time
            </h2>
            <p className='text-sm text-neutral-muted mt-1'>
              Annual debt service (interest + principal repayments) and what share of revenue it
              consumes.
            </p>
            {yearMissingRevenue(fiscal.years) && (
              <p className='text-xs text-neutral-muted mt-1.5'>
                The share stops at {yearMissingRevenue(fiscal.years)}: that year has an enacted
                debt-service figure but no revenue figure in our data yet, and a share cannot be
                computed from one of the two.
              </p>
            )}
          </div>
          <div className='rounded-xl bg-white/70 dark:bg-surface-elevated border border-white/70 shadow-surface p-5'>
            <ResponsiveContainer width='100%' height={260}>
              <ComposedChart
                data={buildDebtServiceSeries(fiscal.years)}
                margin={{ top: 8, right: 40, left: 0, bottom: 8 }}>
                <defs>
                  <linearGradient id='serviceFill' x1='0' y1='0' x2='0' y2='1'>
                    <stop offset='0%' stopColor='#C94A4A' stopOpacity={0.5} />
                    <stop offset='100%' stopColor='#C94A4A' stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray='3 3' stroke='#E2DDD5' vertical={false} />
                <XAxis dataKey='year' tick={{ fill: '#6B7280', fontSize: 11 }} tickLine={false} />
                <YAxis
                  yAxisId='left'
                  tickFormatter={(v) => fmtT(v)}
                  tick={{ fill: '#6B7280', fontSize: 11 }}
                  tickLine={false}
                  width={60}
                />
                <YAxis
                  yAxisId='right'
                  orientation='right'
                  tickFormatter={(v) => `${v}%`}
                  tick={{ fill: '#D9A441', fontSize: 11 }}
                  tickLine={false}
                  width={40}
                />
                <Tooltip
                  contentStyle={{
                    background: 'rgba(255,255,255,0.95)',
                    border: '1px solid rgba(226,221,213,0.4)',
                    borderRadius: 12,
                    fontSize: 12,
                  }}
                  formatter={(v: any, name: any) => {
                    if (v == null) return ['Not published', name === 'ratio' ? 'Service / Revenue' : 'Debt service'];
                    if (name === 'ratio') return [`${Number(v).toFixed(1)}%`, 'Service / Revenue'];
                    return [fmtKES(Number(v)), 'Debt service'];
                  }}
                />
                <Area
                  yAxisId='left'
                  type='monotone'
                  dataKey='service'
                  stroke='#C94A4A'
                  strokeWidth={2.5}
                  fill='url(#serviceFill)'
                  name='service'
                />
                <Line
                  yAxisId='right'
                  type='monotone'
                  dataKey='ratio'
                  stroke='#D9A441'
                  strokeWidth={2}
                  dot={{ r: 3, fill: '#D9A441' }}
                  name='ratio'
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </motion.section>
      )}

      {/* ═══════════ SECTION 9 — FULL LOAN REGISTER ═══════════ */}
      {loans.length > 0 && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.5 }}
          className='space-y-4'>
          <div className='flex flex-wrap items-start justify-between gap-3'>
            <div>
              <h2 className='font-display text-2xl sm:text-3xl text-gov-dark dark:text-white flex items-center gap-2'>
                <BadgeDollarSign className='text-gov-forest dark:text-emerald-100' size={24} />
                The full loan register
              </h2>
              <p className='text-sm text-neutral-muted mt-1'>
                Every row of the register — one per external creditor, one per domestic
                instrument — sortable by what matters most to you.
              </p>
            </div>
            <div className='inline-flex rounded-lg bg-white/70 dark:bg-surface-elevated border border-white/70 p-1 text-xs'>
              {(['outstanding', 'rate', 'service'] as const).map((key) => (
                <button
                  key={key}
                  onClick={() => setLoanSort(key)}
                  className={`px-3 py-1.5 font-semibold rounded-md transition-colors ${
                    loanSort === key ? 'bg-gov-dark text-white' : 'text-gov-dark dark:text-white hover:bg-white dark:bg-surface-base'
                  }`}>
                  {key === 'outstanding'
                    ? 'Balance'
                    : key === 'rate'
                      ? 'Interest rate'
                      : 'Service cost'}
                </button>
              ))}
            </div>
          </div>

          <div className='rounded-xl bg-white/70 dark:bg-surface-elevated border border-white/70 shadow-surface overflow-hidden'>
            {/* Desktop table */}
            <table className='w-full hidden md:table'>
              <thead className='bg-gov-dark/5 border-b border-neutral-border/40'>
                <tr className='text-[11px] uppercase tracking-wider text-neutral-muted'>
                  <th className='text-left px-4 py-3 font-semibold'>Lender</th>
                  <th className='text-left px-4 py-3 font-semibold'>Type</th>
                  <th className='text-right px-4 py-3 font-semibold'>Outstanding</th>
                  <th className='text-right px-4 py-3 font-semibold'>Rate</th>
                  <th className='text-right px-4 py-3 font-semibold'>Annual interest</th>
                  <th className='text-left px-4 py-3 font-semibold'>Maturity</th>
                </tr>
              </thead>
              <tbody>
                {(showAllLoans ? loans : loans.slice(0, 10)).map((l, i) => (
                  <tr
                    key={`${l.lender}-${i}`}
                    className='border-b border-neutral-border/20 hover:bg-white/40 dark:bg-surface-elevated transition-colors'>
                    <td className='px-4 py-3 text-sm font-medium text-gov-dark dark:text-white'>
                      {displayLenderName(l.lender)}
                    </td>
                    <td className='px-4 py-3 text-xs text-neutral-muted'>
                      {l.lender_type?.replace(/_/g, ' ')}
                    </td>
                    <td className='px-4 py-3 text-sm font-semibold text-gov-dark dark:text-white text-right tabular-nums'>
                      {fmtKES(l.outstanding_numeric)}
                    </td>
                    <RateTd loan={l} />
                    <CostTd loan={l} />
                    <td className='px-4 py-3 text-xs text-neutral-muted'>
                      {/* No maturity date is unknown, not "Revolving" — these are
                          aggregate buckets and IDS creditor totals (F24). */}
                      {l.maturity_date || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Mobile cards */}
            <div className='md:hidden divide-y divide-neutral-border/20'>
              {(showAllLoans ? loans : loans.slice(0, 10)).map((l, i) => (
                <div key={`${l.lender}-${i}`} className='p-4'>
                  <div className='text-sm font-semibold text-gov-dark dark:text-white mb-0.5'>
                    {displayLenderName(l.lender)}
                  </div>
                  <div className='text-[11px] text-neutral-muted mb-2'>
                    {l.lender_type?.replace(/_/g, ' ')}
                  </div>
                  <div className='grid grid-cols-2 gap-2 text-xs'>
                    <div>
                      <span className='text-neutral-muted block text-[11px] uppercase'>Outstanding</span>
                      <span className='font-semibold text-gov-dark dark:text-white tabular-nums'>
                        {fmtKES(l.outstanding_numeric)}
                      </span>
                    </div>
                    <div>
                      <span className='text-neutral-muted block text-[11px] uppercase'>Rate</span>
                      <FigureText cell={rateCell(l)} kind='rate' className='font-semibold text-gov-copper tabular-nums' />
                    </div>
                    <div>
                      <span className='text-neutral-muted block text-[11px] uppercase'>Annual interest</span>
                      <FigureText cell={annualCostCell(l)} kind='kes' className='font-semibold text-gov-dark dark:text-white tabular-nums' />
                    </div>
                    <div>
                      <span className='text-neutral-muted block text-[11px] uppercase'>Maturity</span>
                      <span className='text-gov-dark dark:text-white'>{l.maturity_date || '—'}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <p className='px-4 py-3 text-[11px] text-neutral-muted border-t border-neutral-border/20 leading-relaxed'>
              <span className='font-semibold text-gov-dark dark:text-white'>How to read the rate and interest columns.</span>{' '}
              External rows show the interest Kenya actually paid each creditor in the year World Bank
              IDS reports (&ldquo;paid&rdquo;); IDS gives no rate per creditor. Treasury bonds show the
              average coupon of the bonds in CBK&rsquo;s register and bills show CBK&rsquo;s 91-day
              yield; their interest is <em>modelled</em> as balance × that rate, not published.
              &ldquo;—&rdquo; means no publisher gives the figure; hover for why. These columns do not
              add up to a total: they are on different bases and different years.
            </p>

            {loans.length > 10 && (
              <button
                onClick={() => setShowAllLoans((v) => !v)}
                className='w-full py-3 text-xs font-semibold text-gov-forest dark:text-emerald-100 hover:bg-white/40 dark:bg-surface-elevated transition-colors border-t border-neutral-border/20'>
                {showAllLoans
                  ? `Show top 10 only`
                  : `Show all ${loans.length} creditor and instrument lines`}{' '}
                {showAllLoans ? (
                  <ChevronUp size={14} className='inline' />
                ) : (
                  <ChevronDown size={14} className='inline' />
                )}
              </button>
            )}
          </div>
        </motion.section>
      )}

      {/* ═══════════ FOOTER / SOURCES ═══════════ */}
      <div className='rounded-xl bg-gov-dark/5 border border-gov-dark/10 p-5 text-xs text-neutral-muted'>
        <p className='font-semibold text-gov-dark dark:text-white mb-1'>Sources</p>
        <ul className='space-y-0.5'>
          <li>• Central Bank of Kenya — Monthly Statistical Bulletin &amp; Public Debt Register</li>
          <li>• National Treasury — Budget Policy Statement, Budget Review &amp; Outlook</li>
          <li>• Office of the Controller of Budget — Budget Implementation Review Reports</li>
          <li>
            • World Bank International Debt Statistics — external debt and interest paid, by creditor
          </li>
          <li>• IMF World Economic Outlook — debt-to-GDP</li>
        </ul>
      </div>
    </PageShell>
  );
}
