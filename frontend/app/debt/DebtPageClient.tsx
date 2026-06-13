'use client';

import DataFreshnessBadge from '@/components/DataFreshnessBadge';
import DataIntegrityBanner from '@/components/DataIntegrityBanner';
import InfoTip from '@/components/InfoTip';
import PageShell from '@/components/layout/PageShell';
import PDFExportButton from '@/components/PDFExportButton';
import BroaderDebtCard from '@/components/debt/BroaderDebtCard';
import DebtSourceReconciliation from '@/components/debt/DebtSourceReconciliation';
import LenderTreemap from '@/components/debt/LenderTreemap';
import MaturityLadder from '@/components/debt/MaturityLadder';
import PeerStrip from '@/components/debt/PeerStrip';
import {
  useDebtSustainability,
  useDebtTimeline,
  useNationalDebtOverview,
  useNationalLoans,
  usePendingBills,
  usePendingBillsSummary,
} from '@/lib/react-query/useDebt';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { apiClient } from '@/lib/api/axios';
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
  LineChart,
  ReferenceLine,
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

/* ═══════════════════════════════════════════════════════
   Small inline atoms
   ═══════════════════════════════════════════════════════ */

function RingGauge({
  value,
  max = 100,
  size = 120,
  strokeWidth = 10,
  color = '#C94A4A',
  track = 'rgba(31,58,42,0.10)',
  threshold,
  thresholdLabel = 'IMF',
  label,
  subLabel,
}: {
  value: number;
  max?: number;
  size?: number;
  strokeWidth?: number;
  color?: string;
  track?: string;
  threshold?: number;
  thresholdLabel?: string;
  label: string;
  subLabel?: string;
}) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(value, max));
  const offset = circumference - (clamped / max) * circumference;
  const thresholdAngle = threshold != null ? (threshold / max) * 360 : null;

  return (
    <div className='flex flex-col items-center'>
      <div className='relative inline-flex items-center justify-center' style={{ width: size, height: size }}>
        <svg width={size} height={size} className='-rotate-90'>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill='none'
            stroke={track}
            strokeWidth={strokeWidth}
          />
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill='none'
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap='round'
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
          />
          {thresholdAngle != null && (
            <line
              x1={size / 2}
              y1={strokeWidth / 2}
              x2={size / 2}
              y2={strokeWidth + 8}
              stroke='#1B3A2A'
              strokeWidth={2}
              strokeLinecap='round'
              transform={`rotate(${thresholdAngle - 90}, ${size / 2}, ${size / 2})`}
            />
          )}
        </svg>
        <div className='absolute inset-0 flex flex-col items-center justify-center'>
          <span className='text-2xl font-bold text-gov-dark dark:text-white tabular-nums'>{value.toFixed(1)}%</span>
          {threshold != null && (
            <span className='text-[10px] text-neutral-muted'>{thresholdLabel} {threshold}%</span>
          )}
        </div>
      </div>
      <div className='text-xs font-semibold text-gov-dark dark:text-white text-center mt-2'>{label}</div>
      {subLabel && <div className='text-[11px] text-neutral-muted mt-0.5 text-center max-w-[160px]'>{subLabel}</div>}
    </div>
  );
}

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
  const { data: pendingBillsData } = usePendingBills({ enabled: backendReady });
  const { data: rawPendingBillsSummary } = usePendingBillsSummary({ enabled: backendReady });
  const { data: rawDebtSustainability } = useDebtSustainability({ enabled: backendReady });

  /* ── Normalize pending bills summary (API returns dicts) ── */
  const pendingBillsSummary = useMemo(() => {
    if (!rawPendingBillsSummary) return null;
    const raw = rawPendingBillsSummary as any;
    const totalPending = raw.total_pending_amount || 0;

    let breakdownByType = raw.breakdown_by_type;
    if (breakdownByType && !Array.isArray(breakdownByType)) {
      breakdownByType = Object.entries(breakdownByType).map(([type, amount]: [string, any]) => ({
        type,
        amount: Number(amount) || 0,
        percentage: totalPending > 0 ? ((Number(amount) || 0) / totalPending) * 100 : 0,
      }));
    }

    let agingBuckets = raw.aging_buckets;
    if (agingBuckets && !Array.isArray(agingBuckets)) {
      agingBuckets = Object.entries(agingBuckets).map(([bucket, amount]: [string, any]) => ({
        bucket,
        amount: Number(amount) || 0,
        percentage: totalPending > 0 ? ((Number(amount) || 0) / totalPending) * 100 : 0,
        count: 0,
      }));
    }

    const topCounties = (raw.top_counties_by_amount || []).map((c: any) => ({
      ...c,
      county_name: c.county_name || c.county || 'Unknown',
      county_id: c.county_id || c.entity_id || c.id,
    }));

    return {
      ...raw,
      breakdown_by_type: breakdownByType || [],
      aging_buckets: agingBuckets || [],
      top_counties_by_amount: topCounties,
    };
  }, [rawPendingBillsSummary]);

  /* ── Normalize sustainability indicators ──
     The /debt/sustainability endpoint returns two different sets of
     figures for Kenya (top-level Treasury-based vs. regional_peers
     IMF-WEO-based). For a coherent on-page comparison, we override
     the Kenya peer row with the top-level authoritative values so the
     EAC panel doesn't contradict the sustainability ring gauges. */
  const debtSustainability = useMemo(() => {
    if (!rawDebtSustainability) return null;
    const raw = rawDebtSustainability as any;
    const extractNum = (field: any): number | null => {
      if (field == null) return null;
      if (typeof field === 'number') return field;
      if (typeof field === 'object' && field.value != null) return Number(field.value);
      return null;
    };
    const topDebtToGdp = extractNum(raw.debt_to_gdp) ?? 0;
    const topServiceToRev = extractNum(raw.debt_service_to_revenue) ?? 0;
    const topExternalShare = extractNum(raw.external_debt_share) ?? 0;
    return {
      ...raw,
      debt_to_gdp: topDebtToGdp,
      debt_service_to_revenue: topServiceToRev,
      external_debt_share: topExternalShare,
      projections: raw.projections || [],
      regional_peers: (raw.regional_peers || []).map((p: any) => {
        const isKenya = p.country === 'Kenya';
        return {
          ...p,
          debt_to_gdp: isKenya ? topDebtToGdp : extractNum(p.debt_to_gdp) ?? 0,
          debt_service_to_revenue: isKenya
            ? topServiceToRev
            : extractNum(p.debt_service_to_revenue) ?? 0,
          external_debt_share: isKenya
            ? topExternalShare
            : extractNum(p.external_debt_share) ?? 0,
        };
      }),
    };
  }, [rawDebtSustainability]);

  const [loanSort, setLoanSort] = useState<'outstanding' | 'rate' | 'service'>('outstanding');
  const [fetchedPopulation, setFetchedPopulation] = useState<number | null>(null);
  const [pbView, setPbView] = useState<'national' | 'counties'>('national');
  const [showAllLoans, setShowAllLoans] = useState(false);

  useEffect(() => {
    if (!backendReady) return;
    apiClient
      .get('/economic/population/latest')
      .then((res) => setFetchedPopulation(res.data?.population ?? null))
      .catch(() => setFetchedPopulation(null));
  }, [backendReady]);

  /* ── Derived data ── */
  const d = useMemo(() => {
    const api = overview?.data || overview || {};
    const hasData = Object.keys(api).length > 0;
    const totalDebt = api.total_outstanding ?? api.total_debt ?? null;
    const gdp = api.gdp ?? null;
    const gdpRatio = api.debt_to_gdp_ratio ?? (gdp && totalDebt ? (totalDebt / gdp) * 100 : null);
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

  const loans = useMemo(() => {
    if (!loansResp?.loans) return [];
    const arr = [...loansResp.loans];
    if (loanSort === 'rate') {
      arr.sort((a, b) => {
        const rA = parseFloat((a.interest_rate || '0').replace('%', ''));
        const rB = parseFloat((b.interest_rate || '0').replace('%', ''));
        return rB - rA;
      });
    } else if (loanSort === 'service') {
      arr.sort((a, b) => (b.annual_service_cost || 0) - (a.annual_service_cost || 0));
    } else {
      arr.sort((a, b) => (b.outstanding_numeric || 0) - (a.outstanding_numeric || 0));
    }
    return arr;
  }, [loansResp, loanSort]);

  const timeline = useMemo(() => timelineResp?.timeline || [], [timelineResp]);

  const fiscal = useMemo(() => {
    if (!fiscalResp) return null;
    const years = fiscalResp.history || [];
    const current = fiscalResp.current || years[years.length - 1];
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
    if (!pendingBillsData || pendingBillsData.status === 'no_data') return null;
    const s = pendingBillsData.summary;
    return {
      total: s.total_pending,
      national: s.national_total,
      county: s.county_total,
      count: s.record_count,
      bills: pendingBillsData.pending_bills || [],
      source: pendingBillsData.source,
      sourceUrl: pendingBillsData.source_url,
    };
  }, [pendingBillsData]);

  /* ── Treemap data adapter ── */
  const lenderCategories = useMemo(() => {
    return Object.entries(d.categories)
      .map(([key, val]: [string, any]) => {
        const outstanding = val.total_outstanding || val.total_principal || 0;
        const label = key
          .replace(/_/g, ' ')
          .replace(/\b\w/g, (c) => c.toUpperCase());
        return {
          category: key,
          label,
          outstanding,
          share: val.percentage_of_total || 0,
          lenders: (val.items || []).map((it: any) => ({
            lender: it.lender,
            outstanding: Number(it.outstanding) || 0,
            rate: it.interest_rate,
            annual_service_cost: it.annual_service_cost,
          })),
        };
      })
      .filter((c) => c.outstanding > 0);
  }, [d.categories]);

  /* ── Risk band from debt-to-GDP ── */
  const riskBand = useMemo(() => {
    const r = d.gdpRatio ?? 0;
    if (r >= 60) return { level: 'High', tone: 'text-gov-copper', bg: 'bg-gov-copper/15', pill: 'pill-risk' };
    if (r >= 40) return { level: 'Moderate', tone: 'text-gov-gold', bg: 'bg-gov-gold/15', pill: 'pill-risk' };
    return { level: 'Low', tone: 'text-gov-sage', bg: 'bg-gov-sage/15', pill: 'pill-safe' };
  }, [d.gdpRatio]);

  /* ── Revenue allocation (per KES 100 of revenue — authoritative) ──
     Uses backend's debt_service_per_shilling (Treasury figure).
     Framed as "per 100 of revenue" because:
       – Revenue doesn't fund the whole budget (borrowing covers the gap)
       – Debt service is a first-call charge BEFORE anything else
       – Revenue-based framing lets citizens see how much of their taxes
         the debt actually consumes before a single school is funded. */
  const taxAllocation = useMemo(() => {
    if (!fiscal?.current) return null;
    const c: any = fiscal.current;
    const rev = c.total_revenue || 0;
    if (!rev) return null;
    const ds = c.debt_service_cost || 0;
    const rec = Math.max((c.recurrent_spending || 0) - ds, 0);
    const dev = c.development_spending || 0;
    const counties = c.county_allocation || 0;
    const budget = c.appropriated_budget || ds + rec + dev + counties;
    const borrowing = Math.max(budget - rev, 0);

    // Authoritative: use backend-provided debt_service_per_shilling where available.
    const debtServicePerRev =
      c.debt_service_per_shilling != null
        ? c.debt_service_per_shilling
        : rev > 0
          ? (ds / rev) * 100
          : 0;

    const recPerRev = rev > 0 ? (rec / rev) * 100 : 0;
    const devPerRev = rev > 0 ? (dev / rev) * 100 : 0;
    const countiesPerRev = rev > 0 ? (counties / rev) * 100 : 0;
    const allocatedPerRev =
      debtServicePerRev + recPerRev + devPerRev + countiesPerRev;
    const borrowingPerRev = Math.max(allocatedPerRev - 100, 0);

    return {
      rev,
      budget,
      ds,
      borrowing,
      debtServicePerRev, // e.g. 47.7
      recPerRev,
      devPerRev,
      countiesPerRev,
      borrowingPerRev, // how much extra per 100 of rev is funded by borrowing
      fiscalYear: c.fiscal_year,
    };
  }, [fiscal]);

  /* ── Loading / Error states ── */
  const isLoading = ovLoading || loansLoading || tlLoading;
  const isError = ovError || loansError || tlError;

  if (isLoading) {
    return (
      <PageShell title="Kenya's National Debt" subtitle='Pulling the latest numbers from CBK, Treasury and COB…'>
        <div className='flex flex-col items-center justify-center py-24' role='status' aria-live='polite'>
          <div className='animate-spin rounded-full h-12 w-12 border-b-2 border-gov-forest mb-4' />
          <span className='text-sm text-neutral-muted'>Loading comprehensive debt data…</span>
        </div>
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
                  Added KES {fmtT(Math.abs(yoyGrowth.amount) * 1_000_000_000)} in {yoyGrowth.year}
                </span>
              </div>
            )}
            {timeline.length > 1 && (
              <div className='mt-4'>
                <p className='text-[10px] uppercase tracking-wider text-white/50 mb-1'>
                  10-year trajectory
                </p>
                <Sparkline data={timeline.map((t) => t.total)} color='#D9A441' height={48} />
              </div>
            )}
          </div>

          <div className='grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-1 gap-3'>
            <div className='rounded-xl bg-white/8 backdrop-blur border border-white/15 p-4'>
              <div className='flex items-center gap-2 text-[10px] uppercase tracking-wider text-white/60 mb-1.5'>
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
              <div className='flex items-center gap-2 text-[10px] uppercase tracking-wider text-white/60 mb-1.5'>
                <Scale size={12} />
                Debt-to-GDP
                <InfoTip term='debt-to-gdp' size={11} />
              </div>
              <div className='flex items-baseline gap-2'>
                <span className='text-2xl sm:text-3xl font-bold text-white tabular-nums'>
                  {pct(d.gdpRatio)}
                </span>
                <span className='text-[11px] text-white/50'>vs PFM Act 55%</span>
              </div>
              {d.gdpRatio != null && (
                <div className='mt-2 h-1.5 w-full rounded-full bg-white/10 overflow-hidden'>
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(d.gdpRatio, 100)}%` }}
                    transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
                    className='h-full rounded-full'
                    style={{
                      background:
                        d.gdpRatio >= 60
                          ? 'linear-gradient(90deg,#D9A441,#C94A4A)'
                          : d.gdpRatio >= 40
                            ? '#D9A441'
                            : '#4A7C5C',
                    }}
                  />
                </div>
              )}
            </div>
            <div className='rounded-xl bg-white/8 backdrop-blur border border-white/15 p-4'>
              <div className='flex items-center gap-2 text-[10px] uppercase tracking-wider text-white/60 mb-1.5'>
                <ShieldAlert size={12} />
                Risk level
              </div>
              <div className='flex items-center gap-2'>
                <span className={`text-2xl sm:text-3xl font-bold ${riskBand.tone.replace('text-', 'text-')}`}>
                  {riskBand.level}
                </span>
              </div>
              <p className='text-[11px] text-white/50 mt-1'>
                Based on IMF debt-sustainability thresholds
              </p>
            </div>
          </div>
        </div>
      </motion.section>

      {/* ═══════════ SECTION 1B — SOURCES & RECONCILIATION ═══════════
          Two totals exist for Kenya's public debt:
            • 11.85T — sum of every line item in CBK's Public Debt Bulletin
              (live-fetched, used as the headline everywhere on this site)
            • 12.5T — CBK/Treasury's published annual aggregate stock
          They disagree by ~5% because of consolidation adjustments.

          Hidden behind a disclosure because it's a methodology-audit story,
          not a headline one — most readers don't need the provenance dive.
          The *real* "how big is Kenya's debt?" question is CBK-vs-IMF (next
          section), so we lead with that and keep this available for anyone
          who spotted 11.85 vs 12.5 in the press and wants to square them. */}

      {/* ═══════════ SECTION 1B — BROADER (IMF) MEASURE ═══════════
          Leads the "what does public debt actually mean?" story: Treasury's
          narrow Central-Government number vs IMF's General-Government
          measure (adds counties, SOE guarantees, arrears, pending bills).
          For Kenya the gap is modest — the component's copy acknowledges
          that rather than overselling it. */}
      <BroaderDebtCard
        cbkTotalKes={d.totalDebt}
        cbkAsOf={d.lastUpdated}
      />

      {/* ═══════════ SECTION 1C — AUDIT TRAIL (collapsed by default) ═══════════
          Compact disclosure: live primary/secondary debt totals from the
          reconciliation block — click to expand the full Sources &
          Reconciliation card. Uses native <details> so it works without
          client state and is keyboard-accessible by default.

          Gate on BOTH primary_value_kes AND secondary_value_kes — pre-fix
          the headline + comparator were hardcoded "11.85T" / "12.50T"
          strings, which silently went stale every time the live data
          moved (CBK overlay, WB IDS overlay, fixture refresh…). The
          ``percent_diff`` slot was already dynamic so the rest of the
          line was internally inconsistent: "headline 11.85T … 1.3% gap"
          was actually a ~6% gap on the live numbers. */}
      {d.reconciliation &&
        d.reconciliation.primary_value_kes != null &&
        d.reconciliation.secondary_value_kes != null && (
          <details className='group rounded-xl border border-neutral-border/40 bg-white/60 dark:bg-surface-elevated overflow-hidden'>
            <summary className='flex items-center justify-between gap-3 px-5 py-3.5 cursor-pointer list-none hover:bg-neutral-50/50 transition-colors'>
              <div className='flex items-center gap-2.5 min-w-0'>
                <span className='text-[10px] uppercase tracking-widest font-semibold text-neutral-muted shrink-0'>
                  Audit trail
                </span>
                {/* Data vintage note: CBK publishes the Statistical
                    Bulletin biannually (June + December issues, ~6-month
                    publication lag). Surfacing the issue date in this
                    one-liner tells citizens our headline isn't stale per
                    se — it's the latest CBK has published — which is the
                    question they actually asked when they saw the number
                    move. The "June 2025 issue" string is currently
                    static; it'll need updating when the December 2025
                    issue ships (typically ~July 2026). TODO: plumb the
                    measurement_date the cbk_bulletin parser already
                    captures (in the loan record's ``notes`` field)
                    through the /debt/national API so this can be
                    rendered dynamically. */}
                <span className='text-sm text-gov-dark/85 dark:text-white/85 truncate'>
                  Our {fmtT(d.reconciliation.primary_value_kes)} figure is the
                  loan-level sum from CBK&apos;s Statistical Bulletin (June 2025
                  issue, the most recent published). The CBK/Treasury annual
                  aggregate reports {fmtT(d.reconciliation.secondary_value_kes)}{' '}
                  — a {(d.reconciliation.percent_diff ?? 0).toFixed(1)}% gap
                  typical for line-level vs. roll-up data. Click for details.
                </span>
              </div>
              <ChevronDown
                size={16}
                className='text-neutral-muted group-open:rotate-180 transition-transform shrink-0'
              />
            </summary>
            <div className='border-t border-neutral-border/40'>
              <DebtSourceReconciliation
                reconciliation={d.reconciliation}
                lastUpdated={d.lastUpdated}
              />
            </div>
          </details>
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
          totalOutstanding={d.totalDebt || 0}
        />
      </motion.section>

      {/* ═══════════ SECTION 3 — MATURITY LADDER ═══════════ */}
      {loans.length > 0 && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.5 }}>
          <MaturityLadder loans={loans} />
        </motion.section>
      )}

      {/* ═══════════ SECTION 4 — REGIONAL PEERS ═══════════ */}
      {debtSustainability?.regional_peers?.length > 0 && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.5 }}>
          <PeerStrip peers={debtSustainability.regional_peers} />
        </motion.section>
      )}

      {/* ═══════════ SECTION 5 — SUSTAINABILITY GAUGES + PROJECTION ═══════════ */}
      {debtSustainability && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.5 }}
          className='space-y-4'>
          <div>
            <h2 className='font-display text-2xl sm:text-3xl text-gov-dark dark:text-white flex items-center gap-2'>
              <Gauge className='text-gov-forest dark:text-emerald-100' size={24} />
              Can Kenya keep paying?
            </h2>
            <p className='text-sm text-neutral-muted mt-1'>
              Three sustainability ratios compared against internationally-agreed thresholds.
              Crossing them signals fiscal stress.
            </p>
          </div>
          <div className='rounded-xl bg-white/70 dark:bg-surface-elevated border border-white/70 shadow-surface p-5 sm:p-6'>
            <div className='grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6 mb-6'>
              <RingGauge
                value={debtSustainability.debt_to_gdp}
                color={debtSustainability.debt_to_gdp >= 55 ? '#C94A4A' : '#4A7C5C'}
                threshold={55}
                thresholdLabel='PFM Act'
                label='Debt-to-GDP'
                subLabel='Public debt as % of GDP (nominal). The PFM Act 55% anchor is measured in present-value terms.'
              />
              <RingGauge
                value={debtSustainability.debt_service_to_revenue}
                color={debtSustainability.debt_service_to_revenue >= 30 ? '#C94A4A' : '#D9A441'}
                threshold={30}
                label='Service / Revenue'
                subLabel='% of tax revenue going to debt repayment'
              />
              <RingGauge
                value={debtSustainability.external_debt_share}
                color='#8b5cf6'
                label='External share'
                subLabel='% of debt held by foreign lenders (FX-exposed)'
              />
            </div>

            {debtSustainability.projections?.length > 0 && (
              <div>
                <div className='flex items-center gap-2 mb-2'>
                  <TrendingUp size={16} className='text-gov-forest dark:text-emerald-100' />
                  <h3 className='text-sm font-semibold text-gov-dark dark:text-white'>5-year projection</h3>
                </div>
                <ResponsiveContainer width='100%' height={220}>
                  <LineChart data={debtSustainability.projections} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                    <CartesianGrid strokeDasharray='3 3' stroke='#E2DDD5' vertical={false} />
                    <XAxis dataKey='year' tick={{ fill: '#6B7280', fontSize: 11 }} tickLine={false} />
                    <YAxis
                      tick={{ fill: '#6B7280', fontSize: 11 }}
                      tickLine={false}
                      tickFormatter={(v) => `${v}%`}
                      width={45}
                    />
                    <Tooltip
                      contentStyle={{
                        background: 'rgba(255,255,255,0.95)',
                        border: '1px solid rgba(226,221,213,0.4)',
                        borderRadius: 12,
                        fontSize: 12,
                      }}
                      formatter={(v: any) => `${Number(v).toFixed(1)}%`}
                    />
                    <ReferenceLine y={55} stroke='#C94A4A' strokeDasharray='4 4'>
                      <text x='90%' y={-4} fill='#C94A4A' fontSize={10} fontWeight={600}>
                        PFM Act 55%
                      </text>
                    </ReferenceLine>
                    <Line
                      type='monotone'
                      dataKey='projected_debt_to_gdp'
                      name='Debt-to-GDP'
                      stroke='#C94A4A'
                      strokeWidth={2.5}
                      dot={{ r: 4, fill: '#C94A4A' }}
                      activeDot={{ r: 6 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </motion.section>
      )}

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
                  Debt service takes
                </div>
                <div className='flex items-baseline gap-2 leading-none'>
                  <span className='text-[64px] sm:text-[88px] font-extrabold text-gov-copper tabular-nums tracking-tight'>
                    {taxAllocation.debtServicePerRev.toFixed(0)}
                  </span>
                  <span className='text-2xl sm:text-3xl font-bold text-gov-copper/70'>KES</span>
                </div>
                <div className='text-sm text-gov-dark dark:text-white font-medium mt-2'>
                  out of every <span className='font-bold'>KES 100</span> collected in tax &amp; non-tax revenue
                </div>
                <div className='mt-4 flex items-center gap-2 text-xs text-neutral-muted'>
                  <span className='inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gov-copper/10 text-gov-copper font-semibold'>
                    <AlertTriangle size={12} />
                    Above IMF 30% ceiling
                  </span>
                </div>
                <p className='text-[11px] text-neutral-muted mt-3 leading-relaxed max-w-sm'>
                  Source: National Treasury Budget Policy Statement {taxAllocation.fiscalYear}.
                  Includes interest + principal redemption on Consolidated Fund Services.
                </p>
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
                          className={`relative text-[10px] sm:text-xs font-bold ${
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
                    Filled = shillings lost to debt service before anything else is funded
                  </span>
                </div>
              </div>
            </div>

            {/* Breakdown bar */}
            <div className='px-6 sm:px-8 pb-6 sm:pb-8 pt-4 border-t border-neutral-border/30'>
              <div className='flex items-center justify-between mb-2'>
                <span className='text-xs font-semibold text-gov-dark dark:text-white'>
                  Full allocation per KES 100 of revenue
                </span>
                <span className='text-[11px] text-neutral-muted'>
                  Sum exceeds 100 — shortfall funded by borrowing
                </span>
              </div>
              <div className='flex w-full h-10 rounded-lg overflow-hidden shadow-sm border border-neutral-border/30'>
                {[
                  {
                    key: 'ds',
                    val: taxAllocation.debtServicePerRev,
                    color: 'bg-gov-copper',
                    label: 'Debt service',
                  },
                  {
                    key: 'rec',
                    val: taxAllocation.recPerRev,
                    color: 'bg-gov-forest',
                    label: 'Recurrent',
                  },
                  {
                    key: 'dev',
                    val: taxAllocation.devPerRev,
                    color: 'bg-gov-sage',
                    label: 'Development',
                  },
                  {
                    key: 'counties',
                    val: taxAllocation.countiesPerRev,
                    color: 'bg-gov-gold',
                    label: 'Counties',
                  },
                ].map((seg) => {
                  const sumAllocated =
                    taxAllocation.debtServicePerRev +
                    taxAllocation.recPerRev +
                    taxAllocation.devPerRev +
                    taxAllocation.countiesPerRev +
                    taxAllocation.borrowingPerRev;
                  const w = sumAllocated > 0 ? (seg.val / sumAllocated) * 100 : 0;
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
                {taxAllocation.borrowingPerRev > 0 && (
                  <div
                    className='bg-neutral-muted/30 flex items-center justify-center text-gov-dark dark:text-white text-[11px] font-bold border-l-2 border-dashed border-gov-copper/40'
                    style={{
                      width: `${
                        (taxAllocation.borrowingPerRev /
                          (taxAllocation.debtServicePerRev +
                            taxAllocation.recPerRev +
                            taxAllocation.devPerRev +
                            taxAllocation.countiesPerRev +
                            taxAllocation.borrowingPerRev)) *
                        100
                      }%`,
                    }}
                    title={`Borrowing: KES ${taxAllocation.borrowingPerRev.toFixed(1)} per 100 of revenue`}>
                    {taxAllocation.borrowingPerRev > 10
                      ? `+${taxAllocation.borrowingPerRev.toFixed(0)}`
                      : '+'}
                  </div>
                )}
              </div>
              <div className='grid grid-cols-2 sm:grid-cols-5 gap-x-3 gap-y-1.5 mt-3 text-[11px]'>
                {[
                  { color: 'bg-gov-copper', label: 'Debt service', val: taxAllocation.debtServicePerRev },
                  { color: 'bg-gov-forest', label: 'Recurrent', val: taxAllocation.recPerRev },
                  { color: 'bg-gov-sage', label: 'Development', val: taxAllocation.devPerRev },
                  { color: 'bg-gov-gold', label: 'Counties', val: taxAllocation.countiesPerRev },
                  ...(taxAllocation.borrowingPerRev > 0
                    ? [
                        {
                          color: 'bg-neutral-muted/30',
                          label: 'Borrowing (shortfall)',
                          val: taxAllocation.borrowingPerRev,
                        },
                      ]
                    : []),
                ].map((row) => (
                  <div key={row.label} className='flex items-center gap-1.5'>
                    <span className={`w-2.5 h-2.5 rounded-sm ${row.color}`} />
                    <span className='text-neutral-muted truncate'>{row.label}</span>
                    <span className='ml-auto font-bold text-gov-dark dark:text-white tabular-nums'>
                      {row.val.toFixed(0)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </motion.section>
      )}

      {/* ═══════════ SECTION 7 — PENDING BILLS AGING ═══════════ */}
      {pb && (() => {
        const nationalPct = pb.total > 0 ? (pb.national / pb.total) * 100 : 0;
        const countyPct = pb.total > 0 ? (pb.county / pb.total) * 100 : 0;
        const buckets = pendingBillsSummary?.aging_buckets || [];
        const bucketsWithData = buckets.filter((b: any) => (b.amount || 0) > 0);
        const agingIsDegenerate =
          bucketsWithData.length === 1 && bucketsWithData[0].bucket?.includes('180');
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
                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                    pbView === 'national' ? 'bg-gov-dark text-white' : 'text-gov-dark dark:text-white hover:bg-neutral-border/30'
                  }`}>
                  National
                </button>
                <button
                  onClick={() => setPbView('counties')}
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
                  <div className='text-4xl sm:text-5xl font-extrabold text-gov-dark dark:text-white tabular-nums tracking-tight leading-none'>
                    {fmtKES(pb.total)}
                  </div>
                  <div className='mt-3 flex items-center gap-2 text-xs text-neutral-muted'>
                    <Users size={14} />
                    <span>
                      Across{' '}
                      <span className='font-bold text-gov-dark dark:text-white tabular-nums'>
                        {pb.count.toLocaleString()}
                      </span>{' '}
                      ministries, agencies &amp; counties
                    </span>
                  </div>
                </div>

                {/* Split gauge */}
                <div className='p-6 sm:p-8'>
                  <div className='text-[11px] uppercase tracking-[0.2em] font-semibold text-neutral-muted mb-3'>
                    National vs. counties
                  </div>
                  <div className='flex w-full h-10 rounded-lg overflow-hidden shadow-sm border border-neutral-border/30 mb-3'>
                    <div
                      className='bg-gov-copper flex items-center justify-center text-white text-xs font-bold'
                      style={{ width: `${nationalPct}%` }}
                      title={`National: ${fmtKES(pb.national)} (${nationalPct.toFixed(0)}%)`}>
                      {nationalPct > 15 ? `${nationalPct.toFixed(0)}%` : ''}
                    </div>
                    <div
                      className='bg-gov-gold flex items-center justify-center text-white text-xs font-bold'
                      style={{ width: `${countyPct}%` }}
                      title={`Counties: ${fmtKES(pb.county)} (${countyPct.toFixed(0)}%)`}>
                      {countyPct > 15 ? `${countyPct.toFixed(0)}%` : ''}
                    </div>
                  </div>
                  <div className='grid grid-cols-2 gap-3'>
                    <div className='flex items-start gap-2.5'>
                      <span className='w-2.5 h-2.5 rounded-sm bg-gov-copper mt-1.5 flex-shrink-0' />
                      <div>
                        <div className='text-[10px] uppercase tracking-wider text-neutral-muted font-semibold'>
                          National
                        </div>
                        <div className='text-xl font-bold text-gov-dark dark:text-white tabular-nums'>
                          {fmtKES(pb.national)}
                        </div>
                      </div>
                    </div>
                    <div className='flex items-start gap-2.5'>
                      <span className='w-2.5 h-2.5 rounded-sm bg-gov-gold mt-1.5 flex-shrink-0' />
                      <div>
                        <div className='text-[10px] uppercase tracking-wider text-neutral-muted font-semibold'>
                          Counties
                        </div>
                        <div className='text-xl font-bold text-gov-dark dark:text-white tabular-nums'>
                          {fmtKES(pb.county)}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {bucketsWithData.length > 0 && (
              <div className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-5 sm:p-6'>
                <div className='flex items-start justify-between gap-3 mb-4'>
                  <div>
                    <h3 className='text-sm font-semibold text-gov-dark dark:text-white'>
                      Aging — how long bills have gone unpaid
                    </h3>
                    <p className='text-[11px] text-neutral-muted mt-0.5'>
                      Bills older than 180 days are referred to the Pending Bills Verification Committee.
                    </p>
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
                {agingIsDegenerate && (
                  <div className='mt-3 flex items-start gap-2 text-[11px] text-neutral-muted bg-gov-gold/8 border border-gov-gold/25 rounded-lg px-3 py-2'>
                    <AlertTriangle size={14} className='text-gov-gold flex-shrink-0 mt-0.5' />
                    <span>
                      <span className='font-semibold text-gov-dark dark:text-white'>Data quality note:</span> The
                      backend currently derives aging from the loans table, where all entries are
                      flagged as 180d+. A richer breakdown will appear once the pending_bills seed
                      lands.
                    </span>
                  </div>
                )}
              </div>
            )}

            {pbView === 'counties' && pendingBillsSummary?.top_counties_by_amount?.length > 0 && (
              <div className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-5 sm:p-6'>
                <h3 className='text-sm font-semibold text-gov-dark dark:text-white mb-4'>
                  Top counties by stalled payments
                </h3>
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
                          <span className='text-xs font-medium text-gov-dark dark:text-white w-32 truncate flex-shrink-0'>
                            {c.county_name}
                          </span>
                          <div className='flex-1 h-5 bg-neutral-border/20 rounded-md overflow-hidden'>
                            <motion.div
                              initial={{ width: 0 }}
                              whileInView={{ width: `${w}%` }}
                              viewport={{ once: true }}
                              transition={{ duration: 0.8, delay: i * 0.05 }}
                              className='h-full rounded-md bg-gradient-to-r from-gov-copper/80 to-gov-copper'
                            />
                          </div>
                          <span className='text-xs font-bold text-gov-dark dark:text-white tabular-nums w-20 text-right'>
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
          </div>
          <div className='rounded-xl bg-white/70 dark:bg-surface-elevated border border-white/70 shadow-surface p-5'>
            <ResponsiveContainer width='100%' height={260}>
              <ComposedChart
                data={fiscal.years.map((y: any) => ({
                  year: y.fiscal_year,
                  service: y.debt_service_cost || 0,
                  ratio:
                    y.debt_service_cost && y.total_revenue
                      ? (y.debt_service_cost / y.total_revenue) * 100
                      : 0,
                }))}
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
                Every active loan facility, sortable by what matters most to you.
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
                  <th className='text-right px-4 py-3 font-semibold'>Annual cost</th>
                  <th className='text-left px-4 py-3 font-semibold'>Maturity</th>
                </tr>
              </thead>
              <tbody>
                {(showAllLoans ? loans : loans.slice(0, 10)).map((l, i) => (
                  <tr
                    key={`${l.lender}-${i}`}
                    className='border-b border-neutral-border/20 hover:bg-white/40 dark:bg-surface-elevated transition-colors'>
                    <td className='px-4 py-3 text-sm font-medium text-gov-dark dark:text-white'>{l.lender}</td>
                    <td className='px-4 py-3 text-xs text-neutral-muted'>
                      {l.lender_type?.replace(/_/g, ' ')}
                    </td>
                    <td className='px-4 py-3 text-sm font-semibold text-gov-dark dark:text-white text-right tabular-nums'>
                      {fmtKES(l.outstanding_numeric)}
                    </td>
                    <td className='px-4 py-3 text-xs text-gov-copper text-right tabular-nums'>
                      {l.interest_rate || '—'}
                    </td>
                    <td className='px-4 py-3 text-xs text-neutral-muted text-right tabular-nums'>
                      {fmtKES(l.annual_service_cost)}
                    </td>
                    <td className='px-4 py-3 text-xs text-neutral-muted'>
                      {l.maturity_date || 'Revolving'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Mobile cards */}
            <div className='md:hidden divide-y divide-neutral-border/20'>
              {(showAllLoans ? loans : loans.slice(0, 10)).map((l, i) => (
                <div key={`${l.lender}-${i}`} className='p-4'>
                  <div className='text-sm font-semibold text-gov-dark dark:text-white mb-0.5'>{l.lender}</div>
                  <div className='text-[11px] text-neutral-muted mb-2'>
                    {l.lender_type?.replace(/_/g, ' ')}
                  </div>
                  <div className='grid grid-cols-2 gap-2 text-xs'>
                    <div>
                      <span className='text-neutral-muted block text-[10px] uppercase'>Outstanding</span>
                      <span className='font-semibold text-gov-dark dark:text-white tabular-nums'>
                        {fmtKES(l.outstanding_numeric)}
                      </span>
                    </div>
                    <div>
                      <span className='text-neutral-muted block text-[10px] uppercase'>Rate</span>
                      <span className='font-semibold text-gov-copper tabular-nums'>
                        {l.interest_rate || '—'}
                      </span>
                    </div>
                    <div>
                      <span className='text-neutral-muted block text-[10px] uppercase'>Annual cost</span>
                      <span className='font-semibold text-gov-dark dark:text-white tabular-nums'>
                        {fmtKES(l.annual_service_cost)}
                      </span>
                    </div>
                    <div>
                      <span className='text-neutral-muted block text-[10px] uppercase'>Maturity</span>
                      <span className='text-gov-dark dark:text-white'>{l.maturity_date || 'Revolving'}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {loans.length > 10 && (
              <button
                onClick={() => setShowAllLoans((v) => !v)}
                className='w-full py-3 text-xs font-semibold text-gov-forest dark:text-emerald-100 hover:bg-white/40 dark:bg-surface-elevated transition-colors border-t border-neutral-border/20'>
                {showAllLoans
                  ? `Show top 10 only`
                  : `Show all ${loans.length} loans`}{' '}
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
            • Peer comparison: IMF World Economic Outlook, World Bank International Debt Statistics
          </li>
        </ul>
      </div>
    </PageShell>
  );
}
