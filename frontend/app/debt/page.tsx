'use client';

import PageShell from '@/components/layout/PageShell';
import PDFExportButton from '@/components/PDFExportButton';
import {
  useDebtTimeline,
  useDebtSustainability,
  useNationalDebtOverview,
  useNationalLoans,
  usePendingBills,
  usePendingBillsSummary,
} from '@/lib/react-query/useDebt';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  ArrowUpRight,
  BarChart3,
  Building2,
  ChevronDown,
  ChevronUp,
  Clock,
  DollarSign,
  FileWarning,
  Flag,
  Gauge,
  Globe,
  Landmark,
  MapPin,
  Scale,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
  Users,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { apiClient } from '@/lib/api/axios';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

/* ═══════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════ */

function fmtKES(val: number): string {
  if (!val || val === 0) return 'KES 0';
  const abs = Math.abs(val);
  if (abs >= 1e12) return `KES ${(val / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `KES ${(val / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `KES ${(val / 1e6).toFixed(1)}M`;
  return `KES ${val.toLocaleString()}`;
}

function fmtB(val: number): string {
  if (!val) return '—';
  if (val >= 1000) return `${(val / 1000).toFixed(2)}T`;
  return `${val.toFixed(0)}B`;
}

function pct(val: number): string {
  return `${val.toFixed(1)}%`;
}

const LENDER_TYPE_LABELS: Record<string, string> = {
  external_multilateral: 'Multilateral',
  external_bilateral: 'Bilateral',
  external_commercial: 'Commercial',
  domestic_bond: 'Treasury Bonds',
  domestic_tbill: 'Treasury Bills',
  domestic_cbk: 'CBK Advance',
  domestic_legacy: 'Legacy Debt',
};

const CATEGORY_COLORS: Record<string, string> = {
  external_multilateral: '#3b82f6',
  external_bilateral: '#8b5cf6',
  external_commercial: '#ef4444',
  domestic_bonds: '#10b981',
  domestic_bills: '#f59e0b',
  domestic_overdraft: '#6366f1',
  domestic_cbk: '#6366f1',
  domestic_legacy: '#94a3b8',
  pending_bills: '#dc2626',
  other: '#9ca3af',
};

/* ═══════════════════════════════════════════════════════
   Sub-components
   ═══════════════════════════════════════════════════════ */

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  accent = 'text-gov-dark',
  delay = 0,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
  accent?: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.45 }}
      className='bg-white rounded-xl p-5 border border-gray-100 shadow-sm'>
      <div className='flex items-center gap-3 mb-3'>
        <div className='w-10 h-10 rounded-lg bg-gov-forest/10 flex items-center justify-center'>
          <Icon className='text-gov-forest' size={20} />
        </div>
        <span className='text-xs font-semibold text-gray-500 uppercase tracking-wider'>
          {label}
        </span>
      </div>
      <div className={`text-2xl sm:text-3xl font-bold ${accent} leading-tight`}>{value}</div>
      {sub && <p className='text-xs text-gray-400 mt-1.5'>{sub}</p>}
    </motion.div>
  );
}

function FiscalRow({
  label,
  value,
  sub,
  warn,
}: {
  label: string;
  value: string;
  sub?: string;
  warn?: boolean;
}) {
  return (
    <div className='flex items-start justify-between'>
      <div>
        <span className='text-sm text-gray-700'>{label}</span>
        {sub && <p className='text-xs text-gray-400 mt-0.5'>{sub}</p>}
      </div>
      <span className={`text-sm font-semibold ${warn ? 'text-red-600' : 'text-gray-800'}`}>
        {value}
      </span>
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
  const {
    data: loansResp,
    isLoading: loansLoading,
    isError: loansError,
    refetch: refetchLoans,
  } = useNationalLoans();
  const {
    data: timelineResp,
    isLoading: tlLoading,
    isError: tlError,
    refetch: refetchTimeline,
  } = useDebtTimeline();
  const { data: fiscalResp } = useFiscalSummary();
  const { data: pendingBillsData } = usePendingBills();
  const { data: pendingBillsSummary } = usePendingBillsSummary();
  const { data: debtSustainability } = useDebtSustainability();

  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);
  const [loanSort, setLoanSort] = useState<'outstanding' | 'rate' | 'service'>('outstanding');
  const [fetchedPopulation, setFetchedPopulation] = useState<number | null>(null);

  useEffect(() => {
    apiClient
      .get('/economic/population/latest')
      .then((res) => setFetchedPopulation(res.data?.population ?? null))
      .catch(() => setFetchedPopulation(null));
  }, []);

  // Derived data
  const d = useMemo(() => {
    const api = overview?.data || overview || {};
    const totalDebt = api.total_outstanding || api.total_debt || 0;
    const gdp = api.gdp || 0;
    const gdpRatio = api.debt_to_gdp_ratio || (gdp > 0 ? (totalDebt / gdp) * 100 : 0);
    const summary = api.summary || {};
    const categories = api.categories || {};
    const sustainability = api.debt_sustainability || {};
    const population = fetchedPopulation || api.population || 57_500_000;
    const perCapita = totalDebt > 0 ? totalDebt / population : 0;

    return {
      totalDebt,
      gdp,
      gdpRatio,
      summary,
      categories,
      sustainability,
      loanCount: api.loan_count || 0,
      perCapita,
      population,
      externalDebt: summary.external_debt || 0,
      domesticDebt: summary.domestic_debt || 0,
      externalPct: summary.external_percentage || 0,
      domesticPct: summary.domestic_percentage || 0,
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

  // Pending bills data from COB API
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
      explanation: pendingBillsData.explanation,
    };
  }, [pendingBillsData]);

  const pieData = useMemo(() => {
    const cats = d.categories;
    return Object.entries(cats)
      .map(([key, val]: [string, any]) => ({
        name: key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
        value: val.total_outstanding || val.total_principal || 0,
        key,
        pct: val.percentage_of_total || 0,
      }))
      .filter((c) => c.value > 0)
      .sort((a, b) => b.value - a.value);
  }, [d.categories]);

  // Loading & Error states
  const isLoading = ovLoading || loansLoading || tlLoading;
  const isError = ovError || loansError || tlError;

  if (isLoading) {
    return (
      <PageShell title="Kenya's National Debt" subtitle='Loading comprehensive debt data...'>
        <div className='flex items-center justify-center py-20' role='status' aria-live='polite'>
          <div className='animate-spin rounded-full h-12 w-12 border-b-2 border-gov-forest' />
          <span className='sr-only'>Loading debt data…</span>
        </div>
      </PageShell>
    );
  }

  if (isError) {
    return (
      <PageShell title="Kenya's National Debt" subtitle='Something went wrong'>
        <div className='max-w-md mx-auto py-20 text-center'>
          <AlertTriangle size={40} className='mx-auto text-red-400 mb-3' />
          <p className='text-red-600 mb-4'>Failed to load debt data. Please try again.</p>
          <button
            onClick={() => {
              refetchOverview();
              refetchLoans();
              refetchTimeline();
            }}
            className='px-4 py-2 bg-gov-dark text-white rounded-lg text-sm hover:bg-gov-dark/90 transition-colors'>
            Retry
          </button>
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Kenya's National Debt"
      subtitle='A comprehensive breakdown of every shilling the government owes — who lent it, what it costs, and what it means for you'>
      {/* ── Export button ── */}
      <div className='flex justify-end -mb-3'>
        <PDFExportButton compact documentTitle='Kenya National Debt Report' />
      </div>

      {/* SECTION 1 — KEY METRICS */}
      <div className='grid grid-cols-2 lg:grid-cols-4 gap-3'>
        <StatCard
          icon={DollarSign}
          label='Total Outstanding'
          value={fmtKES(d.totalDebt)}
          sub={`${d.loanCount} active loan facilities`}
          accent='text-red-600'
          delay={0.05}
        />
        <StatCard
          icon={Users}
          label='Per Citizen'
          value={fmtKES(d.perCapita)}
          sub={`Shared among ${(d.population / 1e6).toFixed(0)}M Kenyans`}
          delay={0.1}
        />
        <StatCard
          icon={TrendingUp}
          label='Debt-to-GDP'
          value={pct(d.gdpRatio)}
          sub={d.gdpRatio > 55 ? 'Exceeds IMF 55% recommended threshold' : 'Within safe levels'}
          accent={d.gdpRatio > 55 ? 'text-red-600' : 'text-green-600'}
          delay={0.15}
        />
        <StatCard
          icon={ShieldAlert}
          label='Risk Level'
          value={d.sustainability.risk_level || '—'}
          sub={
            d.sustainability.assessment ? d.sustainability.assessment.slice(0, 70) + '…' : undefined
          }
          accent={d.sustainability.risk_level === 'High' ? 'text-red-600' : 'text-yellow-600'}
          delay={0.2}
        />
      </div>

      {/* Year-over-year growth banner */}
      {yoyGrowth && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.25 }}
          className='flex items-center gap-3 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm'>
          <ArrowUpRight className='text-red-500 flex-shrink-0' size={18} />
          <span className='text-red-800'>
            Debt grew by <strong>KES {fmtB(yoyGrowth.amount)}</strong> (
            <strong>{yoyGrowth.change.toFixed(1)}%</strong>) in {yoyGrowth.year} — that&apos;s
            roughly <strong>KES {fmtB(yoyGrowth.amount / 365)}</strong> per day.
          </span>
        </motion.div>
      )}

      {/* SECTION 2 — DEBT COMPOSITION */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5 }}>
        <h2 className='text-xl font-bold text-gov-dark mb-1'>Who Do We Owe?</h2>
        <p className='text-sm text-gray-500 mb-4'>
          Breakdown by creditor type — external (multilateral, bilateral, commercial) vs domestic
          instruments
        </p>

        <div className='grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-5'>
          {/* Donut chart */}
          <div className='bg-white rounded-xl border border-gray-100 p-4'>
            <ResponsiveContainer width='100%' height={280}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx='50%'
                  cy='50%'
                  innerRadius={65}
                  outerRadius={110}
                  paddingAngle={2}
                  dataKey='value'
                  stroke='none'>
                  {pieData.map((entry) => (
                    <Cell key={entry.key} fill={CATEGORY_COLORS[entry.key] || '#94a3b8'} />
                  ))}
                </Pie>
                <Tooltip formatter={(val: number) => fmtKES(val)} labelFormatter={(name) => name} />
              </PieChart>
            </ResponsiveContainer>
            <div className='grid grid-cols-2 gap-x-4 gap-y-1.5 mt-2'>
              {pieData.map((entry) => (
                <div key={entry.key} className='flex items-center gap-2 text-xs'>
                  <div
                    className='w-2.5 h-2.5 rounded-full flex-shrink-0'
                    style={{ backgroundColor: CATEGORY_COLORS[entry.key] || '#94a3b8' }}
                  />
                  <span className='text-gray-600 truncate'>{entry.name}</span>
                  <span className='text-gray-400 ml-auto'>{entry.pct.toFixed(1)}%</span>
                </div>
              ))}
            </div>
            <div className='mt-4 pt-4 border-t border-gray-100 space-y-2'>
              <div className='flex items-center justify-between text-sm'>
                <span className='flex items-center gap-2 text-gray-600'>
                  <Globe size={14} className='text-blue-500' /> External Debt
                </span>
                <span className='font-semibold'>
                  {fmtKES(d.externalDebt)} ({pct(d.externalPct)})
                </span>
              </div>
              <div className='flex items-center justify-between text-sm'>
                <span className='flex items-center gap-2 text-gray-600'>
                  <Landmark size={14} className='text-green-500' /> Domestic Debt
                </span>
                <span className='font-semibold'>
                  {fmtKES(d.domesticDebt)} ({pct(d.domesticPct)})
                </span>
              </div>
            </div>
          </div>

          {/* Category breakdown cards */}
          <div className='space-y-2'>
            {Object.entries(d.categories).map(([key, cat]: [string, any]) => {
              if (cat.loan_count === 0) return null;
              const isExpanded = expandedCategory === key;
              const label = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
              const isExternal = key.startsWith('external');

              return (
                <div
                  key={key}
                  className='bg-white rounded-lg border border-gray-100 overflow-hidden'>
                  <button
                    onClick={() => setExpandedCategory(isExpanded ? null : key)}
                    className='w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors'>
                    <div
                      className='w-3 h-3 rounded-full flex-shrink-0'
                      style={{ backgroundColor: CATEGORY_COLORS[key] || '#94a3b8' }}
                    />
                    <div className='flex-1 min-w-0'>
                      <div className='flex items-center gap-2'>
                        <span className='font-medium text-sm text-gray-800'>{label}</span>
                        <span className='text-xs text-gray-400'>
                          {cat.loan_count} {cat.loan_count === 1 ? 'facility' : 'facilities'}
                        </span>
                        {isExternal && <Globe size={12} className='text-blue-400' />}
                      </div>
                      <div className='text-xs text-gray-500'>
                        Outstanding: {fmtKES(cat.total_outstanding)} •{' '}
                        {pct(cat.percentage_of_total)} of total
                      </div>
                    </div>
                    <div className='w-24 h-2 bg-gray-100 rounded-full overflow-hidden hidden sm:block'>
                      <div
                        className='h-full rounded-full'
                        style={{
                          width: `${Math.min(cat.percentage_of_total, 100)}%`,
                          backgroundColor: CATEGORY_COLORS[key] || '#94a3b8',
                        }}
                      />
                    </div>
                    {isExpanded ? (
                      <ChevronUp size={16} className='text-gray-400' />
                    ) : (
                      <ChevronDown size={16} className='text-gray-400' />
                    )}
                  </button>
                  {isExpanded && cat.items && (
                    <div className='border-t border-gray-50 bg-gray-50/50 px-4 py-2'>
                      <table className='w-full text-xs'>
                        <thead>
                          <tr className='text-gray-400'>
                            <th className='text-left py-1 font-medium'>Lender</th>
                            <th className='text-right py-1 font-medium'>Principal</th>
                            <th className='text-right py-1 font-medium'>Outstanding</th>
                            <th className='text-right py-1 font-medium'>Rate</th>
                          </tr>
                        </thead>
                        <tbody>
                          {cat.items.map((item: any, i: number) => (
                            <tr key={i} className='border-t border-gray-100'>
                              <td className='py-1.5 text-gray-700 font-medium'>{item.lender}</td>
                              <td className='py-1.5 text-right text-gray-500'>
                                {fmtKES(item.principal)}
                              </td>
                              <td className='py-1.5 text-right text-gray-700'>
                                {fmtKES(item.outstanding)}
                              </td>
                              <td className='py-1.5 text-right text-gray-500'>
                                {item.interest_rate ? `${item.interest_rate}%` : '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </motion.section>

      {/* SECTION 3 — DEBT GROWTH TIMELINE */}
      {timeline.length > 0 && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}>
          <h2 className='text-xl font-bold text-gov-dark mb-1'>
            Debt Growth — {timeline[0]?.year} to {timeline[timeline.length - 1]?.year}
          </h2>
          <p className='text-sm text-gray-500 mb-4'>
            How Kenya&apos;s domestic and external debts have grown year over year (KES Billions)
          </p>

          <div className='bg-white rounded-xl border border-gray-100 p-4'>
            <ResponsiveContainer width='100%' height={340}>
              <AreaChart data={timeline}>
                <defs>
                  <linearGradient id='extGrad' x1='0' y1='0' x2='0' y2='1'>
                    <stop offset='0%' stopColor='#3b82f6' stopOpacity={0.3} />
                    <stop offset='100%' stopColor='#3b82f6' stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id='domGrad' x1='0' y1='0' x2='0' y2='1'>
                    <stop offset='0%' stopColor='#10b981' stopOpacity={0.3} />
                    <stop offset='100%' stopColor='#10b981' stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray='3 3' stroke='#f0f0f0' />
                <XAxis
                  dataKey='year'
                  tick={{ fontSize: 11, fill: '#6b7280' }}
                  tickLine={false}
                  axisLine={{ stroke: '#e5e7eb' }}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: '#6b7280' }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${v >= 1000 ? (v / 1000).toFixed(1) + 'T' : v + 'B'}`}
                  width={50}
                />
                <Tooltip
                  contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}
                  formatter={(val: number, name: string) => [
                    `KES ${val >= 1000 ? (val / 1000).toFixed(2) + 'T' : val + 'B'}`,
                    name,
                  ]}
                />
                <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
                <Area
                  type='monotone'
                  dataKey='external'
                  name='External Debt'
                  stackId='1'
                  stroke='#3b82f6'
                  fill='url(#extGrad)'
                  strokeWidth={2}
                />
                <Area
                  type='monotone'
                  dataKey='domestic'
                  name='Domestic Debt'
                  stackId='1'
                  stroke='#10b981'
                  fill='url(#domGrad)'
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>

            {/* Debt-to-GDP trend mini bar */}
            <div className='mt-4 pt-4 border-t border-gray-100'>
              <h3 className='text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2'>
                Debt-to-GDP Ratio Trend
              </h3>
              <div className='flex items-end gap-1 h-12'>
                {timeline.map((yr: any) => {
                  const h = (yr.gdp_ratio / 100) * 48;
                  const danger = yr.gdp_ratio > 55;
                  return (
                    <div
                      key={yr.year}
                      className='flex-1 group relative'
                      title={`${yr.year}: ${yr.gdp_ratio}%`}>
                      <div
                        className={`rounded-t-sm transition-all ${danger ? 'bg-red-400' : 'bg-gov-sage'}`}
                        style={{ height: `${h}px` }}
                      />
                      <span className='absolute -bottom-4 left-1/2 -translate-x-1/2 text-[9px] text-gray-400 hidden lg:block'>
                        {yr.year.toString().slice(-2)}
                      </span>
                    </div>
                  );
                })}
              </div>
              <div className='flex items-center gap-2 mt-6 text-xs text-gray-400'>
                <div className='w-3 h-2 bg-gov-sage rounded-sm' /> <span>Below 55%</span>
                <div className='w-3 h-2 bg-red-400 rounded-sm ml-2' />{' '}
                <span>Above IMF 55% threshold</span>
              </div>
            </div>
          </div>
        </motion.section>
      )}

      {/* SECTION 4 — FISCAL CONTEXT: BORROWING vs BUDGET */}
      {fiscal && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}>
          <h2 className='text-xl font-bold text-gov-dark mb-1'>Borrowing vs The Budget</h2>
          <p className='text-sm text-gray-500 mb-4'>
            How much of the national budget is funded by debt, and how much goes back to servicing
            it
          </p>

          <div className='grid grid-cols-1 lg:grid-cols-2 gap-4'>
            {/* Current fiscal snapshot */}
            <div className='bg-white rounded-xl border border-gray-100 p-5 space-y-4'>
              <div className='flex items-center gap-2 mb-1'>
                <Scale size={16} className='text-gov-forest' />
                <h3 className='font-semibold text-sm text-gray-800'>
                  {fiscal.current.fiscal_year} Snapshot
                </h3>
              </div>
              <div className='space-y-3'>
                <FiscalRow
                  label='Appropriated Budget'
                  value={`KES ${fmtB(fiscal.current.appropriated_budget)}`}
                />
                <FiscalRow
                  label='Total Revenue'
                  value={`KES ${fmtB(fiscal.current.total_revenue)}`}
                  sub={`Tax: ${fmtB(fiscal.current.tax_revenue)} + Non-tax: ${fmtB(fiscal.current.non_tax_revenue)}`}
                />
                <FiscalRow
                  label='Borrowing Required'
                  value={`KES ${fmtB(fiscal.current.total_borrowing)}`}
                  sub={`${fiscal.current.borrowing_pct_of_budget}% of the budget`}
                  warn
                />
                <FiscalRow
                  label='Debt Service Cost'
                  value={`KES ${fmtB(fiscal.current.debt_service_cost)}`}
                  sub={`For every KES 100 collected, KES ${fiscal.current.debt_service_per_shilling?.toFixed(0) || '—'} goes to debt`}
                  warn
                />
                {fiscal.current.debt_ceiling_usage_pct > 100 && (
                  <div className='flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-700'>
                    <AlertTriangle size={14} className='flex-shrink-0 mt-0.5' />
                    <div>
                      <strong>Debt ceiling breached.</strong> Actual debt (KES{' '}
                      {fmtB(fiscal.current.actual_debt)}) exceeds the PFM Act ceiling of KES{' '}
                      {fmtB(fiscal.current.debt_ceiling)} by{' '}
                      {pct(fiscal.current.debt_ceiling_usage_pct - 100)}.
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Borrowing vs Development chart */}
            <div className='bg-white rounded-xl border border-gray-100 p-5'>
              <div className='flex items-center gap-2 mb-3'>
                <Flag size={16} className='text-gov-copper' />
                <h3 className='font-semibold text-sm text-gray-800'>
                  Borrowing vs Development Spending
                </h3>
              </div>
              <p className='text-xs text-gray-500 mb-3'>
                Kenyan law (PFM Act) requires borrowing to be used only for development. If
                borrowing exceeds development spending, funds are going to recurrent costs.
              </p>
              <ResponsiveContainer width='100%' height={220}>
                <BarChart
                  data={fiscal.years.map((fy: any) => ({
                    year: fy.fiscal_year.replace('FY ', ''),
                    borrowing: fy.total_borrowing,
                    development: fy.development_spending,
                  }))}>
                  <CartesianGrid strokeDasharray='3 3' stroke='#f0f0f0' />
                  <XAxis dataKey='year' tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} />
                  <YAxis
                    tick={{ fontSize: 10, fill: '#6b7280' }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `${v}B`}
                    width={45}
                  />
                  <Tooltip
                    contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 11 }}
                    formatter={(val: number) => [`KES ${val}B`, '']}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar
                    dataKey='borrowing'
                    name='Total Borrowing'
                    fill='#ef4444'
                    radius={[4, 4, 0, 0]}
                  />
                  <Bar
                    dataKey='development'
                    name='Dev Spending'
                    fill='#10b981'
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
              {fiscal.years.some((fy: any) => fy.total_borrowing > fy.development_spending) && (
                <div className='flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg p-3 mt-3 text-xs text-amber-800'>
                  <ShieldAlert size={14} className='flex-shrink-0 mt-0.5' />
                  <div>
                    In every recent fiscal year,{' '}
                    <strong>borrowing has exceeded development spending</strong>. This means
                    borrowed funds are being used for recurrent expenses (salaries, operations) — a
                    potential violation of the PFM Act.
                  </div>
                </div>
              )}
            </div>
          </div>
        </motion.section>
      )}

      {/* SECTION 5 — ENHANCED PENDING BILLS TRACKER */}
      {(pb && pb.total > 0) && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}>
          <div className='bg-white rounded-xl border border-red-200 shadow-sm overflow-hidden'>
            {/* Header */}
            <div className='bg-red-50 border-b border-red-200 px-5 py-4'>
              <div className='flex items-center gap-3'>
                <div className='w-9 h-9 rounded-lg bg-red-100 flex items-center justify-center'>
                  <FileWarning className='text-red-600' size={20} />
                </div>
                <div>
                  <h2 className='text-base font-bold text-red-900'>Pending Bills Tracker</h2>
                  <p className='text-xs text-red-700 mt-0.5'>
                    Verified but unpaid invoices owed to suppliers, contractors &amp; staff
                  </p>
                </div>
              </div>
            </div>

            <div className='p-5 space-y-5'>
              {/* Hero number */}
              <div className='text-center py-4'>
                <p className='text-xs font-semibold text-red-600 uppercase tracking-wider mb-2'>
                  Total Pending Bills — All Government
                </p>
                <p className='text-4xl sm:text-5xl font-black text-red-700'>{fmtKES(pendingBillsSummary?.total_pending_amount || pb.total)}</p>
                <div className='flex items-center justify-center gap-6 mt-3'>
                  <div>
                    <span className='text-sm font-semibold text-orange-700'>{fmtKES(pb.national)}</span>
                    <span className='text-xs text-gray-500 ml-1'>National</span>
                  </div>
                  <div className='w-px h-4 bg-gray-200' />
                  <div>
                    <span className='text-sm font-semibold text-amber-700'>{fmtKES(pb.county)}</span>
                    <span className='text-xs text-gray-500 ml-1'>Counties</span>
                  </div>
                </div>
              </div>

              {/* Breakdown by type + Aging buckets */}
              {pendingBillsSummary && (
                <div className='grid grid-cols-1 lg:grid-cols-2 gap-4'>
                  {/* Breakdown by type — donut chart */}
                  {pendingBillsSummary.breakdown_by_type?.length > 0 && (
                    <div className='bg-gray-50 rounded-xl p-4'>
                      <h3 className='text-sm font-semibold text-gray-800 mb-3'>Breakdown by Type</h3>
                      <ResponsiveContainer width='100%' height={220}>
                        <PieChart>
                          <Pie
                            data={pendingBillsSummary.breakdown_by_type.map((t) => ({
                              name: t.type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
                              value: t.amount,
                            }))}
                            cx='50%'
                            cy='50%'
                            innerRadius={50}
                            outerRadius={85}
                            paddingAngle={2}
                            dataKey='value'
                            stroke='none'>
                            {pendingBillsSummary.breakdown_by_type.map((_, i) => (
                              <Cell key={i} fill={['#ef4444', '#f59e0b', '#8b5cf6', '#3b82f6', '#10b981', '#ec4899'][i % 6]} />
                            ))}
                          </Pie>
                          <Tooltip formatter={(val: number) => fmtKES(val)} />
                        </PieChart>
                      </ResponsiveContainer>
                      <div className='grid grid-cols-2 gap-x-3 gap-y-1 mt-2'>
                        {pendingBillsSummary.breakdown_by_type.map((t, i) => (
                          <div key={t.type} className='flex items-center gap-2 text-xs'>
                            <div
                              className='w-2.5 h-2.5 rounded-full flex-shrink-0'
                              style={{ backgroundColor: ['#ef4444', '#f59e0b', '#8b5cf6', '#3b82f6', '#10b981', '#ec4899'][i % 6] }}
                            />
                            <span className='text-gray-600 truncate'>
                              {t.type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                            </span>
                            <span className='text-gray-400 ml-auto'>{t.percentage.toFixed(1)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Aging buckets — stacked bar visualization */}
                  {pendingBillsSummary.aging_buckets?.length > 0 && (
                    <div className='bg-gray-50 rounded-xl p-4'>
                      <h3 className='text-sm font-semibold text-gray-800 mb-3'>
                        Aging Analysis
                      </h3>
                      <div className='space-y-3'>
                        {pendingBillsSummary.aging_buckets.map((bucket) => {
                          const colors: Record<string, string> = {
                            '0-30d': 'bg-green-500',
                            '31-90d': 'bg-yellow-500',
                            '91-180d': 'bg-orange-500',
                            '180d+': 'bg-red-500',
                          };
                          const bgColor = colors[bucket.bucket] || 'bg-gray-400';
                          return (
                            <div key={bucket.bucket}>
                              <div className='flex items-center justify-between mb-1'>
                                <div className='flex items-center gap-2'>
                                  <Clock size={12} className='text-gray-400' />
                                  <span className='text-sm text-gray-700 font-medium'>{bucket.bucket}</span>
                                  <span className='text-xs text-gray-400'>{bucket.count} bills</span>
                                </div>
                                <span className='text-sm font-semibold text-gray-800'>{fmtKES(bucket.amount)}</span>
                              </div>
                              <div className='h-3 bg-gray-200 rounded-full overflow-hidden'>
                                <div
                                  className={`h-full rounded-full ${bgColor} transition-all`}
                                  style={{ width: `${Math.min(bucket.percentage, 100)}%` }}
                                />
                              </div>
                              <div className='text-[10px] text-gray-400 mt-0.5 text-right'>
                                {bucket.percentage.toFixed(1)}% of total
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Top counties by pending bills */}
              {(pendingBillsSummary?.top_counties_by_amount?.length ?? 0) > 0 && pendingBillsSummary && (
                <div className='bg-gray-50 rounded-xl p-4'>
                  <h3 className='text-sm font-semibold text-gray-800 mb-3'>
                    <MapPin size={14} className='inline mr-1 text-red-500' />
                    Top Counties by Pending Bills
                  </h3>
                  <div className='space-y-2'>
                    {pendingBillsSummary.top_counties_by_amount.slice(0, 10).map((county, i) => {
                      const maxAmount = pendingBillsSummary.top_counties_by_amount[0]?.amount || 1;
                      const barWidth = (county.amount / maxAmount) * 100;
                      return (
                        <div key={county.county_id} className='flex items-center gap-3'>
                          <span className='w-5 text-xs text-gray-400 text-right'>{i + 1}</span>
                          <div className='w-32 sm:w-40 text-sm truncate'>
                            <span className='font-medium text-gray-800'>{county.county_name}</span>
                          </div>
                          <div className='flex-1 h-4 bg-gray-200 rounded-full overflow-hidden'>
                            <div
                              className='h-full rounded-full bg-red-400 transition-all'
                              style={{ width: `${barWidth}%` }}
                            />
                          </div>
                          <div className='text-right shrink-0'>
                            <span className='text-xs font-semibold text-gray-700'>{fmtKES(county.amount)}</span>
                            {county.per_capita > 0 && (
                              <div className='text-[10px] text-gray-400'>
                                {fmtKES(county.per_capita)}/person
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Year-over-year trend */}
              {(pendingBillsSummary?.trend?.length ?? 0) > 1 && pendingBillsSummary && (
                <div className='bg-gray-50 rounded-xl p-4'>
                  <h3 className='text-sm font-semibold text-gray-800 mb-3'>
                    <TrendingUp size={14} className='inline mr-1 text-red-500' />
                    Pending Bills Trend — Are They Growing?
                  </h3>
                  <ResponsiveContainer width='100%' height={200}>
                    <BarChart data={pendingBillsSummary.trend}>
                      <CartesianGrid strokeDasharray='3 3' stroke='#f0f0f0' />
                      <XAxis dataKey='year' tick={{ fontSize: 11, fill: '#6b7280' }} tickLine={false} />
                      <YAxis
                        tick={{ fontSize: 11, fill: '#6b7280' }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => `${v >= 1e9 ? (v / 1e9).toFixed(0) + 'B' : (v / 1e6).toFixed(0) + 'M'}`}
                        width={50}
                      />
                      <Tooltip
                        contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 11 }}
                        formatter={(val: number) => [fmtKES(val), 'Pending Bills']}
                      />
                      <Bar dataKey='amount' name='Pending Bills' fill='#ef4444' radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                  {(() => {
                    const t = pendingBillsSummary.trend;
                    const last = t[t.length - 1];
                    const prev = t[t.length - 2];
                    if (!last || !prev || prev.amount === 0) return null;
                    const change = ((last.amount - prev.amount) / prev.amount) * 100;
                    const growing = change > 0;
                    return (
                      <div className={`flex items-center gap-2 mt-3 text-xs ${growing ? 'text-red-700' : 'text-green-700'}`}>
                        {growing ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                        <span>
                          Pending bills {growing ? 'grew' : 'decreased'} by <strong>{Math.abs(change).toFixed(1)}%</strong> from {prev.year} to {last.year}
                        </span>
                      </div>
                    );
                  })()}
                </div>
              )}

              {/* Detail table (existing) */}
              {pb.bills.length > 0 && (
                <div className='overflow-x-auto'>
                  <table className='w-full text-sm'>
                    <thead>
                      <tr className='bg-gray-50 border-b border-gray-200'>
                        <th className='text-left py-2 px-3 font-semibold text-gray-600'>Entity</th>
                        <th className='text-left py-2 px-3 font-semibold text-gray-600'>Category</th>
                        <th className='text-right py-2 px-3 font-semibold text-gray-600'>Total Pending</th>
                        <th className='text-right py-2 px-3 font-semibold text-gray-600'>Eligible</th>
                        <th className='text-right py-2 px-3 font-semibold text-gray-600'>Ineligible</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pb.bills.map((bill, idx) => (
                        <tr
                          key={`${bill.entity_name}-${idx}`}
                          className='border-b border-gray-100 hover:bg-gray-50 transition-colors'>
                          <td className='py-2 px-3 font-medium text-gray-800'>{bill.entity_name}</td>
                          <td className='py-2 px-3 text-gray-500 capitalize'>
                            {(bill.category || bill.entity_type).replace(/_/g, ' ')}
                          </td>
                          <td className='py-2 px-3 text-right font-semibold text-red-600'>{fmtKES(bill.total_pending)}</td>
                          <td className='py-2 px-3 text-right text-green-700'>
                            {bill.eligible_pending != null ? fmtKES(bill.eligible_pending) : '—'}
                          </td>
                          <td className='py-2 px-3 text-right text-gray-500'>
                            {bill.ineligible_pending != null ? fmtKES(bill.ineligible_pending) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Explanation & source */}
              <div className='flex flex-col sm:flex-row items-start gap-3 bg-gray-50 rounded-lg p-3 text-xs text-gray-600'>
                <AlertTriangle size={14} className='flex-shrink-0 mt-0.5 text-amber-500' />
                <div>
                  <p>{pb.explanation}</p>
                  <p className='mt-1.5'>
                    Source:{' '}
                    <a
                      href={pb.sourceUrl}
                      target='_blank'
                      rel='noopener noreferrer'
                      className='text-gov-forest hover:underline'>
                      {pb.source}
                    </a>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </motion.section>
      )}

      {/* SECTION 5b — DEBT SUSTAINABILITY WARNING */}
      {debtSustainability && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}>
          {/* Warning banner if any threshold breached */}
          {(debtSustainability.debt_to_gdp > 55 || debtSustainability.debt_service_to_revenue > 30) && (
            <div className='flex items-center gap-3 bg-red-600 text-white rounded-xl px-5 py-4 mb-4 shadow-lg'>
              <ShieldAlert size={24} className='flex-shrink-0' />
              <div>
                <h3 className='font-bold text-sm'>Debt Sustainability Warning</h3>
                <p className='text-xs text-white/90 mt-0.5'>
                  {debtSustainability.debt_to_gdp > 55 && `Debt-to-GDP (${debtSustainability.debt_to_gdp.toFixed(1)}%) exceeds the IMF 55% threshold. `}
                  {debtSustainability.debt_service_to_revenue > 30 && `Debt service (${debtSustainability.debt_service_to_revenue.toFixed(1)}% of revenue) exceeds the 30% danger threshold.`}
                </p>
              </div>
            </div>
          )}

          <h2 className='text-xl font-bold text-gov-dark mb-1'>Debt Sustainability Indicators</h2>
          <p className='text-sm text-gray-500 mb-4'>
            Key ratios that determine whether Kenya&apos;s debt is on a sustainable path
          </p>

          {/* Gauge indicators row */}
          <div className='grid grid-cols-1 md:grid-cols-3 gap-4 mb-4'>
            {/* Debt-to-GDP gauge */}
            <div className='bg-white rounded-xl border border-gray-100 p-5'>
              <div className='flex items-center gap-2 mb-3'>
                <Gauge size={16} className='text-gov-forest' />
                <h3 className='text-sm font-semibold text-gray-800'>Debt-to-GDP Ratio</h3>
              </div>
              {(() => {
                const val = debtSustainability.debt_to_gdp;
                const color = val < 50 ? '#22c55e' : val <= 55 ? '#f59e0b' : '#ef4444';
                const label = val < 50 ? 'Safe Zone' : val <= 55 ? 'Caution Zone' : 'Danger Zone';
                const r = 60;
                const circ = Math.PI * r;
                const offset = circ - (Math.min(val, 100) / 100) * circ;
                return (
                  <div className='flex flex-col items-center'>
                    <div className='relative' style={{ width: 140, height: 80 }}>
                      <svg width={140} height={80} viewBox='0 0 140 80'>
                        <path
                          d='M 10 75 A 60 60 0 0 1 130 75'
                          fill='none'
                          stroke='#f3f4f6'
                          strokeWidth={10}
                          strokeLinecap='round'
                        />
                        <path
                          d='M 10 75 A 60 60 0 0 1 130 75'
                          fill='none'
                          stroke={color}
                          strokeWidth={10}
                          strokeLinecap='round'
                          strokeDasharray={circ}
                          strokeDashoffset={offset}
                          className='transition-all duration-700'
                        />
                      </svg>
                      <div className='absolute inset-0 flex items-end justify-center pb-0'>
                        <span className='text-2xl font-black' style={{ color }}>{val.toFixed(1)}%</span>
                      </div>
                    </div>
                    <span className='text-xs font-semibold mt-1' style={{ color }}>{label}</span>
                    <div className='flex items-center gap-3 mt-2 text-[10px] text-gray-400'>
                      <span>EAC: 50%</span>
                      <span>IMF: 55%</span>
                    </div>
                  </div>
                );
              })()}
            </div>

            {/* Debt-service-to-revenue */}
            <div className='bg-white rounded-xl border border-gray-100 p-5'>
              <div className='flex items-center gap-2 mb-3'>
                <Scale size={16} className='text-gov-forest' />
                <h3 className='text-sm font-semibold text-gray-800'>Debt Service / Revenue</h3>
              </div>
              {(() => {
                const val = debtSustainability.debt_service_to_revenue;
                const color = val < 20 ? '#22c55e' : val <= 30 ? '#f59e0b' : '#ef4444';
                const label = val < 20 ? 'Manageable' : val <= 30 ? 'Elevated' : 'Critical';
                return (
                  <div className='flex flex-col items-center'>
                    <div className='text-4xl font-black' style={{ color }}>{val.toFixed(1)}%</div>
                    <span className='text-xs font-semibold mt-1' style={{ color }}>{label}</span>
                    <p className='text-[10px] text-gray-400 mt-1'>Threshold: 30%</p>
                    <div className='w-full h-3 bg-gray-100 rounded-full mt-3 overflow-hidden'>
                      <div
                        className='h-full rounded-full transition-all'
                        style={{ width: `${Math.min(val, 100)}%`, backgroundColor: color }}
                      />
                    </div>
                  </div>
                );
              })()}
            </div>

            {/* External debt share */}
            <div className='bg-white rounded-xl border border-gray-100 p-5'>
              <div className='flex items-center gap-2 mb-3'>
                <Globe size={16} className='text-gov-forest' />
                <h3 className='text-sm font-semibold text-gray-800'>External Debt Share</h3>
              </div>
              {(() => {
                const val = debtSustainability.external_debt_share;
                const color = val < 40 ? '#22c55e' : val <= 60 ? '#f59e0b' : '#ef4444';
                return (
                  <div className='flex flex-col items-center'>
                    <div className='text-4xl font-black' style={{ color }}>{val.toFixed(1)}%</div>
                    <span className='text-xs text-gray-500 mt-1'>of total public debt</span>
                    <div className='w-full mt-3'>
                      <div className='flex h-3 rounded-full overflow-hidden'>
                        <div
                          className='transition-all'
                          style={{ width: `${val}%`, backgroundColor: '#3b82f6' }}
                        />
                        <div
                          className='transition-all'
                          style={{ width: `${100 - val}%`, backgroundColor: '#10b981' }}
                        />
                      </div>
                      <div className='flex items-center justify-between mt-1 text-[10px] text-gray-400'>
                        <span>External {val.toFixed(0)}%</span>
                        <span>Domestic {(100 - val).toFixed(0)}%</span>
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>

          {/* 5-year projection chart */}
          {debtSustainability.projections?.length > 0 && (
            <div className='bg-white rounded-xl border border-gray-100 p-5 mb-4'>
              <h3 className='text-sm font-semibold text-gray-800 mb-1'>5-Year Debt Trajectory</h3>
              <p className='text-xs text-gray-500 mb-3'>
                Projected debt-to-GDP and debt-service-to-revenue ratios
              </p>
              <ResponsiveContainer width='100%' height={280}>
                <LineChart data={debtSustainability.projections}>
                  <CartesianGrid strokeDasharray='3 3' stroke='#f0f0f0' />
                  <XAxis dataKey='year' tick={{ fontSize: 11, fill: '#6b7280' }} tickLine={false} />
                  <YAxis
                    tick={{ fontSize: 11, fill: '#6b7280' }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `${v}%`}
                    width={45}
                    domain={[0, 'auto']}
                  />
                  <Tooltip
                    contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 11 }}
                    formatter={(val: number, name: string) => [`${val.toFixed(1)}%`, name]}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
                  <ReferenceLine y={55} stroke='#ef4444' strokeDasharray='5 5' label={{ value: 'IMF 55%', position: 'right', fill: '#ef4444', fontSize: 10 }} />
                  <ReferenceLine y={30} stroke='#f59e0b' strokeDasharray='5 5' label={{ value: '30% Service', position: 'right', fill: '#f59e0b', fontSize: 10 }} />
                  <Line
                    type='monotone'
                    dataKey='debt_to_gdp'
                    name='Debt-to-GDP'
                    stroke='#ef4444'
                    strokeWidth={2.5}
                    dot={{ r: 4, fill: '#ef4444' }}
                    activeDot={{ r: 6 }}
                  />
                  <Line
                    type='monotone'
                    dataKey='debt_service_to_revenue'
                    name='Service-to-Revenue'
                    stroke='#8b5cf6'
                    strokeWidth={2.5}
                    dot={{ r: 4, fill: '#8b5cf6' }}
                    activeDot={{ r: 6 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Regional peers comparison table */}
          {debtSustainability.regional_peers?.length > 0 && (
            <div className='bg-white rounded-xl border border-gray-100 p-5'>
              <h3 className='text-sm font-semibold text-gray-800 mb-1'>Regional Comparison</h3>
              <p className='text-xs text-gray-500 mb-3'>
                Kenya vs East African Community peers
              </p>
              {/* Mobile cards */}
              <div className='md:hidden space-y-3'>
                {debtSustainability.regional_peers.map((peer) => {
                  const isKenya = peer.country.toLowerCase() === 'kenya';
                  return (
                    <div
                      key={peer.country}
                      className={`rounded-lg border p-3 ${isKenya ? 'border-gov-forest bg-gov-forest/5' : 'border-gray-100'}`}>
                      <div className='flex items-center justify-between mb-2'>
                        <span className={`text-sm font-semibold ${isKenya ? 'text-gov-dark' : 'text-gray-800'}`}>
                          {peer.country} {isKenya && '(You)'}
                        </span>
                      </div>
                      <div className='grid grid-cols-3 gap-2 text-center'>
                        <div>
                          <div className='text-[10px] text-gray-500'>Debt/GDP</div>
                          <div className={`text-sm font-bold ${peer.debt_to_gdp > 55 ? 'text-red-600' : peer.debt_to_gdp > 50 ? 'text-amber-600' : 'text-green-600'}`}>
                            {peer.debt_to_gdp.toFixed(1)}%
                          </div>
                        </div>
                        <div>
                          <div className='text-[10px] text-gray-500'>Service/Rev</div>
                          <div className={`text-sm font-bold ${peer.debt_service_to_revenue > 30 ? 'text-red-600' : 'text-amber-600'}`}>
                            {peer.debt_service_to_revenue.toFixed(1)}%
                          </div>
                        </div>
                        <div>
                          <div className='text-[10px] text-gray-500'>External</div>
                          <div className='text-sm font-bold text-blue-600'>
                            {peer.external_debt_share.toFixed(1)}%
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
              {/* Desktop table */}
              <div className='hidden md:block overflow-x-auto'>
                <table className='w-full text-sm'>
                  <thead>
                    <tr className='bg-gray-50 border-b border-gray-200'>
                      <th className='text-left py-2 px-3 font-semibold text-gray-600'>Country</th>
                      <th className='text-right py-2 px-3 font-semibold text-gray-600'>Debt-to-GDP</th>
                      <th className='text-right py-2 px-3 font-semibold text-gray-600'>Service/Revenue</th>
                      <th className='text-right py-2 px-3 font-semibold text-gray-600'>External Debt %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {debtSustainability.regional_peers.map((peer) => {
                      const isKenya = peer.country.toLowerCase() === 'kenya';
                      return (
                        <tr
                          key={peer.country}
                          className={`border-b border-gray-100 ${isKenya ? 'bg-gov-forest/5 font-semibold' : 'hover:bg-gray-50'}`}>
                          <td className='py-2.5 px-3 text-gray-800'>
                            {peer.country} {isKenya && <span className='text-xs text-gov-forest'>(You)</span>}
                          </td>
                          <td className={`py-2.5 px-3 text-right ${peer.debt_to_gdp > 55 ? 'text-red-600 font-bold' : peer.debt_to_gdp > 50 ? 'text-amber-600' : 'text-green-600'}`}>
                            {peer.debt_to_gdp.toFixed(1)}%
                          </td>
                          <td className={`py-2.5 px-3 text-right ${peer.debt_service_to_revenue > 30 ? 'text-red-600 font-bold' : 'text-gray-700'}`}>
                            {peer.debt_service_to_revenue.toFixed(1)}%
                          </td>
                          <td className='py-2.5 px-3 text-right text-gray-700'>
                            {peer.external_debt_share.toFixed(1)}%
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </motion.section>
      )}

      {/* SECTION 6 — FULL LOAN REGISTER */}
      {loans.length > 0 && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}>
          <div className='flex items-center justify-between mb-4 flex-wrap gap-2'>
            <div>
              <h2 className='text-xl font-bold text-gov-dark'>Full Loan Register</h2>
              <p className='text-sm text-gray-500'>
                Every active national government loan — {loans.length} facilities totalling{' '}
                {fmtKES(loansResp?.total_outstanding || 0)}
              </p>
            </div>
            <div className='flex items-center gap-1 text-xs'>
              <span className='text-gray-400 mr-1'>Sort by:</span>
              {(['outstanding', 'rate', 'service'] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setLoanSort(s)}
                  className={`px-2.5 py-1 rounded-full border transition-colors ${loanSort === s ? 'bg-gov-forest text-white border-gov-forest' : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'}`}>
                  {s === 'outstanding' ? 'Balance' : s === 'rate' ? 'Interest' : 'Service Cost'}
                </button>
              ))}
            </div>
          </div>

          <div className='bg-white rounded-xl border border-gray-100 overflow-hidden'>
            {/* ── Mobile card layout ── */}
            <div className='md:hidden divide-y divide-gray-100'>
              {loans.map((loan: any, i: number) => {
                const outstanding = loan.outstanding_numeric || parseFloat(loan.outstanding || '0');
                const totalOutstanding = loansResp?.total_outstanding || 1;
                const shareOfTotal = (outstanding / totalOutstanding) * 100;
                const rate = loan.interest_rate || '—';
                const lenderType = LENDER_TYPE_LABELS[loan.lender_type] || loan.lender_type || '—';
                const isExternal = (loan.lender_type || '').startsWith('external');

                return (
                  <div key={i} className='px-4 py-3'>
                    <div className='flex items-start justify-between gap-3'>
                      <div className='flex-1 min-w-0'>
                        <div className='flex items-center gap-2'>
                          <span className='text-xs text-gray-400 font-medium'>{i + 1}.</span>
                          <span className='font-semibold text-gray-900 text-sm leading-tight'>
                            {loan.lender}
                          </span>
                        </div>
                        <div className='flex items-center gap-2 mt-1'>
                          <span
                            className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full ${isExternal ? 'bg-blue-50 text-blue-600' : 'bg-green-50 text-green-600'}`}>
                            {isExternal ? <Globe size={8} /> : <Building2 size={8} />}
                            {lenderType}
                          </span>
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded-full ${loan.status === 'active' ? 'bg-green-50 text-green-600' : loan.status === 'matured' ? 'bg-gray-100 text-gray-500' : 'bg-yellow-50 text-yellow-600'}`}>
                            {loan.status || 'active'}
                          </span>
                        </div>
                      </div>
                      <div className='text-right shrink-0'>
                        <div className='font-bold text-gov-dark text-sm'>{fmtKES(outstanding)}</div>
                        <div className='text-[10px] text-gray-400'>outstanding</div>
                      </div>
                    </div>
                    {/* Share bar */}
                    <div className='w-full h-1 bg-gray-100 rounded-full mt-2'>
                      <div
                        className='h-full rounded-full bg-gov-sage'
                        style={{ width: `${Math.min(shareOfTotal * 2, 100)}%` }}
                      />
                    </div>
                    {/* Secondary stats row */}
                    <div className='flex items-center justify-between mt-2 text-[11px] text-gray-500'>
                      <span>
                        Rate:{' '}
                        <span
                          className={`font-medium ${
                            parseFloat((rate || '0').toString().replace('%', '')) > 8
                              ? 'text-red-600'
                              : 'text-gray-700'
                          }`}>
                          {rate}
                        </span>
                      </span>
                      <span>
                        Service:{' '}
                        <span className='font-medium text-gray-700'>
                          {fmtKES(loan.annual_service_cost || 0)}
                        </span>
                        <span className='text-gray-300'>/yr</span>
                      </span>
                    </div>
                  </div>
                );
              })}
              {/* Mobile totals */}
              <div className='px-4 py-3 bg-gray-50 border-t-2 border-gray-200'>
                <div className='flex items-center justify-between'>
                  <span className='font-bold text-sm text-gray-700'>
                    TOTAL ({loans.length} facilities)
                  </span>
                  <span className='font-bold text-sm text-gov-dark'>
                    {fmtKES(loansResp?.total_outstanding || 0)}
                  </span>
                </div>
                <div className='flex items-center justify-between mt-1 text-xs text-gray-500'>
                  <span>
                    Principal:{' '}
                    <span className='font-medium text-gray-600'>
                      {fmtKES(
                        loans.reduce((s: number, l: any) => s + (l.principal_numeric || 0), 0)
                      )}
                    </span>
                  </span>
                  <span>
                    Service:{' '}
                    <span className='font-medium text-red-600'>
                      {fmtKES(loansResp?.total_annual_service_cost || 0)}
                    </span>
                    <span className='text-gray-400'>/yr</span>
                  </span>
                </div>
              </div>
            </div>

            {/* ── Desktop table layout ── */}
            <div className='hidden md:block overflow-x-auto'>
              <table className='w-full text-sm'>
                <thead>
                  <tr className='bg-gray-50 text-left'>
                    <th className='px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider'>
                      #
                    </th>
                    <th className='px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider'>
                      Lender
                    </th>
                    <th className='px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider'>
                      Type
                    </th>
                    <th className='px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right'>
                      Principal
                    </th>
                    <th className='px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right'>
                      Outstanding
                    </th>
                    <th className='px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right'>
                      Rate
                    </th>
                    <th className='px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right'>
                      Annual Cost
                    </th>
                    <th className='px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider'>
                      Status
                    </th>
                  </tr>
                </thead>
                <tbody className='divide-y divide-gray-50'>
                  {loans.map((loan: any, i: number) => {
                    const outstanding =
                      loan.outstanding_numeric || parseFloat(loan.outstanding || '0');
                    const totalOutstanding = loansResp?.total_outstanding || 1;
                    const shareOfTotal = (outstanding / totalOutstanding) * 100;
                    const rate = loan.interest_rate || '—';
                    const lenderType =
                      LENDER_TYPE_LABELS[loan.lender_type] || loan.lender_type || '—';
                    const isExternal = (loan.lender_type || '').startsWith('external');

                    return (
                      <tr key={i} className='hover:bg-gray-50/50 transition-colors'>
                        <td className='px-4 py-3 text-gray-400 text-xs'>{i + 1}</td>
                        <td className='px-4 py-3'>
                          <div className='font-medium text-gray-800'>{loan.lender}</div>
                          <div className='w-20 h-1 bg-gray-100 rounded-full mt-1'>
                            <div
                              className='h-full rounded-full bg-gov-sage'
                              style={{ width: `${Math.min(shareOfTotal * 2, 100)}%` }}
                            />
                          </div>
                        </td>
                        <td className='px-4 py-3'>
                          <span
                            className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${isExternal ? 'bg-blue-50 text-blue-700' : 'bg-green-50 text-green-700'}`}>
                            {isExternal ? <Globe size={10} /> : <Building2 size={10} />}
                            {lenderType}
                          </span>
                        </td>
                        <td className='px-4 py-3 text-right text-gray-500 text-xs'>
                          {fmtKES(loan.principal_numeric || parseFloat(loan.principal || '0'))}
                        </td>
                        <td className='px-4 py-3 text-right font-medium text-gray-800'>
                          {fmtKES(outstanding)}
                        </td>
                        <td className='px-4 py-3 text-right'>
                          <span
                            className={`text-xs font-medium ${parseFloat((rate || '0').toString().replace('%', '')) > 8 ? 'text-red-600' : 'text-gray-600'}`}>
                            {rate}
                          </span>
                        </td>
                        <td className='px-4 py-3 text-right text-xs text-gray-500'>
                          {fmtKES(loan.annual_service_cost || 0)}
                          <span className='text-gray-300'>/yr</span>
                        </td>
                        <td className='px-4 py-3'>
                          <span
                            className={`text-xs px-2 py-0.5 rounded-full ${loan.status === 'active' ? 'bg-green-50 text-green-700' : loan.status === 'matured' ? 'bg-gray-100 text-gray-500' : 'bg-yellow-50 text-yellow-700'}`}>
                            {loan.status || 'active'}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className='bg-gray-50 border-t-2 border-gray-200'>
                    <td colSpan={3} className='px-4 py-3 font-bold text-sm text-gray-700'>
                      TOTAL ({loans.length} facilities)
                    </td>
                    <td className='px-4 py-3 text-right font-bold text-sm text-gray-600'>
                      {fmtKES(
                        loans.reduce((s: number, l: any) => s + (l.principal_numeric || 0), 0)
                      )}
                    </td>
                    <td className='px-4 py-3 text-right font-bold text-sm text-gray-800'>
                      {fmtKES(loansResp?.total_outstanding || 0)}
                    </td>
                    <td className='px-4 py-3' />
                    <td className='px-4 py-3 text-right font-bold text-sm text-red-600'>
                      {fmtKES(loansResp?.total_annual_service_cost || 0)}
                      <span className='text-xs font-normal text-gray-400'>/yr</span>
                    </td>
                    <td className='px-4 py-3' />
                  </tr>
                </tfoot>
              </table>
            </div>
            <div className='px-4 py-2 bg-gray-50 border-t border-gray-100 text-xs text-gray-400 flex items-center gap-1'>
              <BarChart3 size={10} />
              Source: {loansResp?.source || 'National Treasury Public Debt Bulletin'}
              {loansResp?.last_updated && (
                <> • Updated: {new Date(loansResp.last_updated).toLocaleDateString()}</>
              )}
            </div>
          </div>
        </motion.section>
      )}

      {/* SECTION 7 — DEBT SERVICE: WHERE YOUR TAXES GO */}
      {fiscal && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}>
          <h2 className='text-xl font-bold text-gov-dark mb-1'>
            Debt Service — Where Your Tax Shillings Go
          </h2>
          <p className='text-sm text-gray-500 mb-4'>
            For every KES 100 the government collects in revenue, here&apos;s how it&apos;s divided
          </p>

          <div className='bg-white rounded-xl border border-gray-100 p-5'>
            <div className='flex items-center gap-1 h-10 rounded-lg overflow-hidden mb-4'>
              {(() => {
                const fy = fiscal.current;
                const debtPct = fy.debt_service_per_shilling || 0;
                const devPct = ((fy.development_spending || 0) / (fy.total_revenue || 1)) * 100;
                const recPct = ((fy.recurrent_spending || 0) / (fy.total_revenue || 1)) * 100;
                const countyPct = ((fy.county_allocation || 0) / (fy.total_revenue || 1)) * 100;
                return (
                  <>
                    <div
                      className='h-full bg-red-500 flex items-center justify-center text-white text-[10px] font-bold'
                      style={{ width: `${debtPct}%` }}
                      title={`Debt Service: ${debtPct.toFixed(0)}%`}>
                      {debtPct > 8 && `${debtPct.toFixed(0)}%`}
                    </div>
                    <div
                      className='h-full bg-blue-500 flex items-center justify-center text-white text-[10px] font-bold'
                      style={{ width: `${Math.min(recPct, 50)}%` }}
                      title={`Recurrent: ~${recPct.toFixed(0)}%`}>
                      {recPct > 8 && `${recPct.toFixed(0)}%`}
                    </div>
                    <div
                      className='h-full bg-green-500 flex items-center justify-center text-white text-[10px] font-bold'
                      style={{ width: `${Math.min(devPct, 40)}%` }}
                      title={`Development: ~${devPct.toFixed(0)}%`}>
                      {devPct > 8 && `${devPct.toFixed(0)}%`}
                    </div>
                    <div
                      className='h-full bg-amber-500 flex items-center justify-center text-white text-[10px] font-bold'
                      style={{ width: `${Math.min(countyPct, 20)}%` }}
                      title={`Counties: ~${countyPct.toFixed(0)}%`}>
                      {countyPct > 6 && `${countyPct.toFixed(0)}%`}
                    </div>
                  </>
                );
              })()}
            </div>
            <div className='grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs'>
              <div className='flex items-center gap-2'>
                <div className='w-3 h-3 rounded bg-red-500' />
                <span className='text-gray-600'>Debt Repayment</span>
              </div>
              <div className='flex items-center gap-2'>
                <div className='w-3 h-3 rounded bg-blue-500' />
                <span className='text-gray-600'>Recurrent (Salaries, Ops)</span>
              </div>
              <div className='flex items-center gap-2'>
                <div className='w-3 h-3 rounded bg-green-500' />
                <span className='text-gray-600'>Development Projects</span>
              </div>
              <div className='flex items-center gap-2'>
                <div className='w-3 h-3 rounded bg-amber-500' />
                <span className='text-gray-600'>County Transfers</span>
              </div>
            </div>

            <div className='mt-5 pt-5 border-t border-gray-100'>
              <h3 className='text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3'>
                Annual Debt Service Cost Trend (KES Billions)
              </h3>
              <ResponsiveContainer width='100%' height={160}>
                <BarChart
                  data={fiscal.years.map((fy: any) => ({
                    year: fy.fiscal_year.replace('FY ', ''),
                    cost: fy.debt_service_cost,
                  }))}>
                  <CartesianGrid strokeDasharray='3 3' stroke='#f0f0f0' />
                  <XAxis dataKey='year' tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} />
                  <YAxis
                    tick={{ fontSize: 10, fill: '#6b7280' }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `${v}B`}
                    width={45}
                  />
                  <Tooltip
                    contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 11 }}
                    formatter={(val: number) => [`KES ${val}B`, 'Debt Service']}
                  />
                  <Bar dataKey='cost' name='Debt Service' fill='#ef4444' radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </motion.section>
      )}

      {/* SECTION 8 — TOP 10 CREDITORS */}
      {loans.length > 0 && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}>
          <h2 className='text-xl font-bold text-gov-dark mb-1'>Top 10 Creditors</h2>
          <p className='text-sm text-gray-500 mb-4'>
            The largest outstanding lenders to the Kenyan government, ranked by balance
          </p>

          <div className='bg-white rounded-xl border border-gray-100 p-5 space-y-2'>
            {loans.slice(0, 10).map((loan: any, i: number) => {
              const outstanding = loan.outstanding_numeric || 0;
              const maxOutstanding = loans[0]?.outstanding_numeric || 1;
              const barWidth = (outstanding / maxOutstanding) * 100;
              const isExternal = (loan.lender_type || '').startsWith('external');

              return (
                <div key={i} className='flex items-center gap-3'>
                  <span className='w-5 text-xs text-gray-400 text-right'>{i + 1}</span>
                  <div className='w-36 sm:w-48 text-sm truncate'>
                    <span className='font-medium text-gray-800'>{loan.lender}</span>
                  </div>
                  <div className='flex-1 h-5 bg-gray-50 rounded-full overflow-hidden'>
                    <div
                      className={`h-full rounded-full transition-all ${isExternal ? 'bg-blue-400' : 'bg-green-400'}`}
                      style={{ width: `${barWidth}%` }}
                    />
                  </div>
                  <span className='text-xs font-medium text-gray-700 w-20 text-right'>
                    {fmtKES(outstanding)}
                  </span>
                </div>
              );
            })}
          </div>
        </motion.section>
      )}

      {/* SECTION 9 — KEY TAKEAWAYS */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5 }}>
        <h2 className='text-xl font-bold text-gov-dark mb-4'>Key Takeaways</h2>
        <div className='grid grid-cols-1 md:grid-cols-2 gap-3'>
          <div className='bg-red-50 border border-red-200 rounded-xl p-4'>
            <div className='flex items-center gap-2 mb-2'>
              <TrendingUp size={16} className='text-red-600' />
              <h3 className='font-semibold text-sm text-gray-800'>
                Debt is growing faster than the economy
              </h3>
            </div>
            <p className='text-xs text-gray-600 leading-relaxed'>
              At {pct(d.gdpRatio)} of GDP, Kenya&apos;s debt exceeds the IMF-recommended 55%
              threshold for low-income countries. Each year, the debt-to-GDP ratio has increased.
            </p>
          </div>
          <div className='bg-amber-50 border border-amber-200 rounded-xl p-4'>
            <div className='flex items-center gap-2 mb-2'>
              <Scale size={16} className='text-amber-600' />
              <h3 className='font-semibold text-sm text-gray-800'>
                Borrowing isn&apos;t all going to development
              </h3>
            </div>
            <p className='text-xs text-gray-600 leading-relaxed'>
              Under Kenyan law, government borrowing should fund development only. Our data shows
              borrowing consistently exceeds development spending, meaning borrowed money funds
              salaries and operations.
            </p>
          </div>
          <div className='bg-blue-50 border border-blue-200 rounded-xl p-4'>
            <div className='flex items-center gap-2 mb-2'>
              <DollarSign size={16} className='text-blue-600' />
              <h3 className='font-semibold text-sm text-gray-800'>
                Nearly half of revenue services debt
              </h3>
            </div>
            <p className='text-xs text-gray-600 leading-relaxed'>
              {fiscal
                ? `In ${fiscal.current.fiscal_year}, KES ${fiscal.current.debt_service_per_shilling?.toFixed(0) || '—'} of every KES 100 collected went to debt repayment — money that can't build roads, schools, or hospitals.`
                : 'A significant portion of government revenue is consumed by debt repayment, leaving less for public services.'}
            </p>
          </div>
          <div className='bg-red-50 border border-red-200 rounded-xl p-4'>
            <div className='flex items-center gap-2 mb-2'>
              <AlertTriangle size={16} className='text-red-600' />
              <h3 className='font-semibold text-sm text-gray-800'>
                The debt ceiling has been breached
              </h3>
            </div>
            <p className='text-xs text-gray-600 leading-relaxed'>
              {fiscal && fiscal.current.debt_ceiling_usage_pct > 100
                ? `Current debt is at ${fiscal.current.debt_ceiling_usage_pct.toFixed(0)}% of the legal ceiling set by the PFM Act. The government has exceeded its own legal borrowing limit.`
                : 'The PFM Act sets a debt ceiling, but actual borrowing has at times approached or exceeded this limit.'}
            </p>
          </div>
        </div>
      </motion.section>

      {/* Data source footer */}
      <div className='text-center text-xs text-neutral-muted pt-4 border-t border-neutral-border'>
        Data sourced from the Central Bank of Kenya, National Treasury Public Debt Bulletins,
        Controller of Budget Reports, and the Budget Policy Statement. Last updated:{' '}
        {timelineResp?.last_updated || fiscalResp?.last_updated || '—'}
      </div>
    </PageShell>
  );
}
