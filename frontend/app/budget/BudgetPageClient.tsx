'use client';

import DataFreshnessBadge from '@/components/DataFreshnessBadge';
import PageShell from '@/components/layout/PageShell';
import PDFExportButton from '@/components/PDFExportButton';
import { useBudgetEnhanced, useBudgetOverview } from '@/lib/react-query';
import { useFiscalSummary } from '@/lib/react-query/useFiscal';
import { motion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  BarChart3,
  BookOpen,
  Briefcase,
  Building2,
  DollarSign,
  Droplets,
  ExternalLink,
  Factory,
  Globe,
  Heart,
  HeartHandshake,
  Info,
  Landmark,
  Leaf,
  Loader2,
  Minus,
  PieChart as PieIcon,
  Receipt,
  Shield,
  Sprout,
  TrendingUp,
  UserCheck,
  Users,
  Wrench,
  X,
  Zap,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
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
  if (val === undefined || val === null) return '—';
  return `${val.toFixed(1)}%`;
}

const SECTOR_ICONS: Record<string, React.ElementType> = {
  Health: Heart,
  Education: BookOpen,
  Infrastructure: Wrench,
  'Water & Sanitation': Droplets,
  Agriculture: Sprout,
  Administration: Building2,
  'Trade & Enterprise': Factory,
  Environment: Leaf,
  'Social Protection': HeartHandshake,
  'Defense & Security': Shield,
  Energy: Zap,
  Other: BarChart3,
};

const SECTOR_COLORS: Record<string, string> = {
  Health: '#ef4444',
  Education: '#3b82f6',
  Infrastructure: '#f59e0b',
  'Water & Sanitation': '#06b6d4',
  Agriculture: '#10b981',
  Administration: '#6b7280',
  'Trade & Enterprise': '#8b5cf6',
  Environment: '#22c55e',
  'Social Protection': '#ec4899',
  'Defense & Security': '#475569',
  Energy: '#eab308',
  Other: '#94a3b8',
};

const REVENUE_COLORS: Record<string, string> = {
  PAYE: '#3b82f6',
  'Corporation Tax': '#6366f1',
  VAT: '#10b981',
  'Excise Duty': '#f59e0b',
  'Customs & Import Duty': '#ef4444',
  'Other Tax Revenue': '#94a3b8',
};

const REVENUE_ICONS: Record<string, React.ElementType> = {
  PAYE: UserCheck,
  'Corporation Tax': Building2,
  VAT: Receipt,
  'Excise Duty': Briefcase,
  'Customs & Import Duty': Globe,
  'Other Tax Revenue': DollarSign,
};

/* ═══════════════════════════════════════════════════════
   Data sources used on this page
   ═══════════════════════════════════════════════════════ */

const DATA_SOURCES = [
  {
    section: 'Budget Execution by Sector',
    authority: 'Office of the Controller of Budget (OCOB)',
    description:
      'Sector-level expenditure vs. approved estimates from the Annual National Government Budget Implementation Review Reports (NG-BIRR).',
    methodology:
      'Approved Estimates from the Appropriation Act; Actual Expenditure from CoB Exchequer release reports to Parliament per Article 228(6) of the Constitution of Kenya.',
    url: 'https://cob.go.ke/publications/annual-national-government-budget-implementation-review-reports/',
    urlLabel: 'CoB Annual NG-BIRR Reports',
  },
  {
    section: 'Revenue by Source',
    authority: 'Kenya Revenue Authority (KRA)',
    description:
      'Tax revenue breakdown (PAYE, VAT, Corporation Tax, Excise Duty, Customs) from KRA annual performance press releases.',
    url: 'https://www.kra.go.ke/news-center/press-release/2122-kra-records-11-1-growth-in-revenue-collection',
    urlLabel: 'KRA Press Releases',
  },
  {
    section: 'County Budget Allocations',
    authority: 'Commission on Revenue Allocation (CRA)',
    description:
      'County-level budget allocations per the Division of Revenue Act and County Allocation of Revenue Act.',
    url: 'https://www.crakenya.org/county-allocations/',
    urlLabel: 'CRA County Allocations',
  },
  {
    section: 'Fiscal Summary & Borrowing',
    authority: 'National Treasury & Central Bank of Kenya',
    description:
      'High-level fiscal aggregates (revenue, expenditure, borrowing, debt service) from the Budget Policy Statement and Controller of Budget quarterly reports.',
    url: 'https://www.treasury.go.ke/budget-policy-statement/',
    urlLabel: 'National Treasury BPS',
  },
];

/* ═══════════════════════════════════════════════════════
   DataSourcesModal
   ═══════════════════════════════════════════════════════ */

function DataSourcesModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const overlayRef = useRef<HTMLDivElement>(null);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  // Prevent body scroll when open
  useEffect(() => {
    if (open) document.body.style.overflow = 'hidden';
    else document.body.style.overflow = '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      className='fixed inset-0 z-[200] flex items-center justify-center p-4'
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}>
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className='absolute inset-0 bg-black/40 backdrop-blur-sm'
      />

      {/* Panel */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: 'spring', duration: 0.4 }}
        className='relative z-10 w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-2xl bg-white shadow-2xl border border-gray-100'>
        {/* Header */}
        <div className='sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-white/95 backdrop-blur-sm rounded-t-2xl'>
          <div>
            <h3 className='text-lg font-bold text-gray-900'>Data Sources</h3>
            <p className='text-xs text-gray-500 mt-0.5'>Official resources used on this page</p>
          </div>
          <button
            onClick={onClose}
            className='p-1.5 rounded-lg hover:bg-gray-100 transition-colors text-gray-400 hover:text-gray-600'
            aria-label='Close'>
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className='px-6 py-4 space-y-5'>
          {DATA_SOURCES.map((src) => (
            <div key={src.section} className='group'>
              <h4 className='text-sm font-semibold text-gray-800 mb-1'>{src.section}</h4>
              <p className='text-xs text-gray-500 leading-relaxed mb-1.5'>{src.description}</p>
              {src.methodology && (
                <p className='text-[11px] text-gray-400 italic mb-1.5'>
                  Methodology: {src.methodology}
                </p>
              )}
              <div className='flex items-center gap-2 text-xs'>
                <span className='inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gov-forest/10 text-gov-forest font-medium'>
                  {src.authority}
                </span>
                <a
                  href={src.url}
                  target='_blank'
                  rel='noopener noreferrer'
                  className='inline-flex items-center gap-1 text-gov-forest hover:underline'>
                  {src.urlLabel}
                  <ExternalLink size={11} />
                </a>
              </div>
              <div className='mt-3 border-b border-gray-100 group-last:border-0' />
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className='sticky bottom-0 px-6 py-3 border-t border-gray-100 bg-gray-50/80 backdrop-blur-sm rounded-b-2xl'>
          <p className='text-[11px] text-gray-400 text-center'>
            All figures are sourced from official Kenyan government publications. Click any link
            above to verify directly.
          </p>
        </div>
      </motion.div>
    </div>
  );
}

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
        <span className='text-sm text-gray-500 font-medium'>{label}</span>
      </div>
      <p className={`text-2xl font-bold ${accent}`}>{value}</p>
      {sub && <p className='text-xs text-gray-400 mt-1'>{sub}</p>}
    </motion.div>
  );
}

function ChangeIndicator({ current, previous }: { current: number; previous: number }) {
  if (!previous || !current) return null;
  const change = ((current - previous) / previous) * 100;
  const isUp = change > 0;
  const isFlat = Math.abs(change) < 0.5;
  return (
    <span
      className={`inline-flex items-center gap-0.5 text-xs font-medium px-1.5 py-0.5 rounded-full ${
        isFlat
          ? 'bg-gray-100 text-gray-500'
          : isUp
            ? 'bg-red-50 text-red-600'
            : 'bg-green-50 text-green-600'
      }`}>
      {isFlat ? <Minus size={12} /> : isUp ? <ArrowUp size={12} /> : <ArrowDown size={12} />}
      {Math.abs(change).toFixed(1)}%
    </span>
  );
}

/* ═══════════════════════════════════════════════════════
   Custom tooltip for recharts
   ═══════════════════════════════════════════════════════ */
function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className='bg-white border border-gray-200 rounded-lg p-3 shadow-lg text-sm'>
      <p className='font-semibold text-gray-800 mb-1'>{label}</p>
      {payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color }} className='flex justify-between gap-4'>
          <span>{p.name}:</span>
          <span className='font-medium'>
            {typeof p.value === 'number' ? fmtB(p.value) : p.value}
          </span>
        </p>
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   Main Page
   ═══════════════════════════════════════════════════════ */

export default function BudgetSpendingPage() {
  const {
    data: overview,
    isLoading: loadingOverview,
    isError: errorOverview,
    refetch: refetchOverview,
  } = useBudgetOverview();
  const {
    data: fiscal,
    isLoading: loadingFiscal,
    isError: errorFiscal,
    refetch: refetchFiscal,
  } = useFiscalSummary();
  const { data: enhanced, isLoading: loadingEnhanced } = useBudgetEnhanced();
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const closeSourcesModal = useCallback(() => setSourcesOpen(false), []);
  const [selectedFY, setSelectedFY] = useState<string | null>(null);

  const isLoading = loadingOverview || loadingFiscal;
  const isError = errorOverview || errorFiscal;

  /* ── derived data ── */
  const summary = overview?.summary ?? {};
  const sectors = overview?.sectors ?? [];
  const fiscalHistory = overview?.fiscal_history ?? fiscal?.history ?? [];
  const countyUtil = overview?.county_utilization ?? {};
  const current = fiscal?.current ?? {};

  /* ── enhanced data ── */
  const revenueBySource = enhanced?.revenue_by_source ?? [];
  const economicContext = enhanced?.economic_context ?? {};
  const executionBySector = enhanced?.execution_by_sector ?? [];

  // Pick which fiscal year to highlight in comparison
  const fiscalYears = useMemo(() => fiscalHistory.map((f: any) => f.fiscal_year), [fiscalHistory]);
  const activeFY =
    selectedFY ?? (fiscalYears.length > 0 ? fiscalYears[fiscalYears.length - 1] : null);
  const prevFY = useMemo(() => {
    const idx = fiscalYears.indexOf(activeFY);
    return idx > 0 ? fiscalYears[idx - 1] : null;
  }, [fiscalYears, activeFY]);

  const activeData = useMemo(
    () => fiscalHistory.find((f: any) => f.fiscal_year === activeFY) ?? {},
    [fiscalHistory, activeFY]
  );
  const prevData = useMemo(
    () => fiscalHistory.find((f: any) => f.fiscal_year === prevFY) ?? {},
    [fiscalHistory, prevFY]
  );

  /* ── chart data ── */
  const budgetTrendData = useMemo(
    () =>
      fiscalHistory.map((f: any) => ({
        year: f.fiscal_year?.replace('FY ', '') ?? '',
        Budget: f.appropriated_budget ?? 0,
        Revenue: f.total_revenue ?? 0,
        Borrowing: f.total_borrowing ?? 0,
      })),
    [fiscalHistory]
  );

  const spendingMixData = useMemo(
    () =>
      fiscalHistory.map((f: any) => ({
        year: f.fiscal_year?.replace('FY ', '') ?? '',
        Recurrent: f.recurrent_spending ?? 0,
        Development: f.development_spending ?? 0,
        Counties: f.county_allocation ?? 0,
      })),
    [fiscalHistory]
  );

  const pieData = useMemo(
    () =>
      sectors.map((s: any) => ({
        name: s.sector,
        value: s.allocated,
        color: SECTOR_COLORS[s.sector] || '#94a3b8',
      })),
    [sectors]
  );

  /* ── enhanced chart data — revenue ── */
  const latestRevenueYear = useMemo(() => {
    // Get the latest FY that has actual amounts (not just targets)
    const withAmounts = revenueBySource.filter((fy: any) =>
      fy.sources?.some((s: any) => s.amount != null && s.amount > 0)
    );
    return withAmounts.length > 0 ? withAmounts[withAmounts.length - 1] : null;
  }, [revenueBySource]);

  const prevRevenueYear = useMemo(() => {
    const withAmounts = revenueBySource.filter((fy: any) =>
      fy.sources?.some((s: any) => s.amount != null && s.amount > 0)
    );
    return withAmounts.length > 1 ? withAmounts[withAmounts.length - 2] : null;
  }, [revenueBySource]);

  const revenuePieData = useMemo(() => {
    if (!latestRevenueYear) return [];
    return latestRevenueYear.sources
      .filter((s: any) => s.amount != null && s.amount > 0)
      .sort((a: any, b: any) => b.amount - a.amount)
      .map((s: any) => ({
        name: s.revenue_type,
        value: s.amount,
        color: REVENUE_COLORS[s.revenue_type] || '#94a3b8',
        share: s.share_pct,
        growth: s.yoy_growth_pct,
      }));
  }, [latestRevenueYear]);

  const revenueTrendData = useMemo(() => {
    return revenueBySource
      .filter((fy: any) => fy.sources?.some((s: any) => s.amount != null))
      .map((fy: any) => {
        const row: any = { year: fy.fiscal_year?.replace('FY ', '') ?? '' };
        fy.sources.forEach((s: any) => {
          if (s.amount != null) row[s.revenue_type] = s.amount;
        });
        return row;
      });
  }, [revenueBySource]);

  /* ── execution by sector data ── */
  const executionData = useMemo(
    () =>
      executionBySector
        .filter((s: any) => s.allocated > 0)
        .sort((a: any, b: any) => b.allocated - a.allocated)
        .map((s: any) => ({
          sector: s.sector,
          allocated: +(s.allocated / 1e9).toFixed(1),
          spent: +(s.spent / 1e9).toFixed(1),
          unspent: +(s.unspent / 1e9).toFixed(1),
          execution_rate: s.execution_rate,
        })),
    [executionBySector]
  );

  const overallExecRate = useMemo(() => {
    const totalAlloc = executionData.reduce((s: number, d: any) => s + d.allocated, 0);
    const totalSpent = executionData.reduce((s: number, d: any) => s + d.spent, 0);
    return totalAlloc > 0 ? +((totalSpent / totalAlloc) * 100).toFixed(1) : 0;
  }, [executionData]);

  /* ─────────────── render ─────────────── */

  if (isLoading) {
    return (
      <PageShell
        title="Kenya's Budget & Spending"
        subtitle='Understanding how public funds are allocated and spent'>
        <div className='flex items-center justify-center py-32' role='status' aria-live='polite'>
          <Loader2 className='animate-spin text-gov-forest mr-3' size={28} />
          <span className='text-gray-500 text-lg'>Loading budget data…</span>
        </div>
      </PageShell>
    );
  }

  if (isError) {
    return (
      <PageShell title="Kenya's Budget & Spending" subtitle='Something went wrong'>
        <div className='max-w-md mx-auto py-20 text-center'>
          <AlertTriangle size={40} className='mx-auto text-red-400 mb-3' />
          <p className='text-red-600 mb-4'>Failed to load budget data. Please try again.</p>
          <button
            onClick={() => {
              refetchOverview();
              refetchFiscal();
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
      title="Kenya's Budget & Spending"
      subtitle='How public funds are allocated, spent, and tracked across sectors and counties'>
      {/* ── Data freshness banner ── */}
      <DataFreshnessBadge sources="COB/Treasury" variant="banner" />

      {/* ── Data Sources Modal ── */}
      <DataSourcesModal open={sourcesOpen} onClose={closeSourcesModal} />

      {/* ── Subtle info trigger (top-right) ── */}
      <div className='flex justify-end items-center gap-2 -mb-3'>
        <PDFExportButton compact documentTitle='Kenya Budget & Spending Report' />
        <button
          onClick={() => setSourcesOpen(true)}
          className='inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-400 hover:text-gov-forest hover:bg-gov-forest/5 rounded-lg transition-colors'
          title='View data sources'>
          <Info size={14} />
          <span>Sources</span>
        </button>
      </div>

      {/* ═══ Section 1 — Key Metrics ═══ */}
      <motion.section
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5 }}>
        <div className='grid grid-cols-2 lg:grid-cols-4 gap-4'>
          <StatCard
            icon={DollarSign}
            label='Total Budget'
            value={fmtB(activeData.appropriated_budget)}
            sub={activeFY ?? ''}
            delay={0}
          />
          <StatCard
            icon={TrendingUp}
            label='Total Revenue'
            value={fmtB(activeData.total_revenue)}
            sub={`Tax: ${fmtB(activeData.tax_revenue)}`}
            delay={0.08}
          />
          <StatCard
            icon={Landmark}
            label='Borrowing'
            value={fmtB(activeData.total_borrowing)}
            sub={`${pct(activeData.borrowing_pct_of_budget)} of budget`}
            delay={0.16}
          />
          <StatCard
            icon={PieIcon}
            label='Execution Rate'
            value={pct(summary.execution_rate)}
            sub='County budget utilization'
            delay={0.24}
          />
        </div>
      </motion.section>

      {/* ═══ Section 2 — Year Selector + Fiscal Comparison ═══ */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ delay: 0.1, duration: 0.5 }}>
        <div className='bg-white rounded-xl border border-gray-100 p-5'>
          <div className='flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-5'>
            <h2 className='text-lg font-bold text-gray-900'>Fiscal Year Comparison</h2>
            <div className='flex gap-2 flex-wrap'>
              {fiscalYears.map((fy: string) => (
                <button
                  key={fy}
                  onClick={() => setSelectedFY(fy)}
                  className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                    fy === activeFY
                      ? 'bg-gov-forest text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}>
                  {fy.replace('FY ', '')}
                </button>
              ))}
            </div>
          </div>

          {/* Comparison grid */}
          <div className='grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4'>
            {[
              { label: 'Appropriated Budget', key: 'appropriated_budget' },
              { label: 'Total Revenue', key: 'total_revenue' },
              { label: 'Total Borrowing', key: 'total_borrowing' },
              { label: 'Debt Service Cost', key: 'debt_service_cost' },
              { label: 'County Allocation', key: 'county_allocation' },
            ].map(({ label, key }) => (
              <div key={key} className='bg-gray-50 rounded-lg p-3'>
                <p className='text-xs text-gray-500 mb-1'>{label}</p>
                <p className='text-lg font-bold text-gray-900'>{fmtB(activeData[key])}</p>
                {prevData[key] != null && (
                  <div className='mt-1'>
                    <ChangeIndicator current={activeData[key]} previous={prevData[key]} />
                    <span className='text-xs text-gray-400 ml-1'>
                      vs {prevFY?.replace('FY ', '')}
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </motion.section>

      {/* ═══ Section 3 — Budget Growth Timeline ═══ */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ delay: 0.1, duration: 0.5 }}>
        <div className='bg-white rounded-xl border border-gray-100 p-5'>
          <h2 className='text-lg font-bold text-gray-900 mb-1'>Budget, Revenue & Borrowing</h2>
          <p className='text-sm text-gray-500 mb-5'>
            KES Billions — how the budget gap is financed
          </p>
          <div className='h-72' role="img" aria-label="Area chart showing Kenya's budget, revenue, and borrowing trends over time in KES Billions">
            <ResponsiveContainer width='100%' height='100%'>
              <AreaChart data={budgetTrendData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id='gBudget' x1='0' y1='0' x2='0' y2='1'>
                    <stop offset='5%' stopColor='#1a5632' stopOpacity={0.25} />
                    <stop offset='95%' stopColor='#1a5632' stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id='gRevenue' x1='0' y1='0' x2='0' y2='1'>
                    <stop offset='5%' stopColor='#3b82f6' stopOpacity={0.25} />
                    <stop offset='95%' stopColor='#3b82f6' stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray='3 3' stroke='#f0f0f0' />
                <XAxis dataKey='year' tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `${v}B`} />
                <Tooltip content={<ChartTooltip />} />
                <Legend iconType='circle' wrapperStyle={{ fontSize: 13 }} />
                <Area
                  type='monotone'
                  dataKey='Budget'
                  stroke='#1a5632'
                  fill='url(#gBudget)'
                  strokeWidth={2}
                />
                <Area
                  type='monotone'
                  dataKey='Revenue'
                  stroke='#3b82f6'
                  fill='url(#gRevenue)'
                  strokeWidth={2}
                />
                <Area
                  type='monotone'
                  dataKey='Borrowing'
                  stroke='#ef4444'
                  fill='none'
                  strokeWidth={2}
                  strokeDasharray='5 5'
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </motion.section>

      {/* ═══ Section 4 — Where Revenue Comes From ═══ */}
      {latestRevenueYear && revenuePieData.length > 0 && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1, duration: 0.5 }}>
          <div className='bg-white rounded-xl border border-gray-100 p-5'>
            <div className='flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-2 mb-5'>
              <div>
                <h2 className='text-lg font-bold text-gray-900'>Where Revenue Comes From</h2>
                <p className='text-sm text-gray-500'>
                  KRA tax collection breakdown — {latestRevenueYear.fiscal_year}
                </p>
              </div>
              <p className='text-sm font-semibold text-gov-forest'>
                Total: KES{' '}
                {revenuePieData.reduce((sum: number, r: any) => sum + (r.value ?? 0), 0).toFixed(0)}
                B
              </p>
            </div>

            <div className='grid lg:grid-cols-2 gap-6'>
              {/* Donut chart */}
              <div className='h-64 sm:h-80'>
                <ResponsiveContainer width='100%' height='100%'>
                  <PieChart>
                    <Pie
                      data={revenuePieData}
                      dataKey='value'
                      nameKey='name'
                      cx='50%'
                      cy='50%'
                      outerRadius='80%'
                      innerRadius='40%'
                      paddingAngle={2}
                      strokeWidth={1}
                      stroke='#fff'>
                      {revenuePieData.map((entry: any, i: number) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value: number) => `KES ${value}B`}
                      contentStyle={{ borderRadius: 8, fontSize: 13 }}
                    />
                    <Legend
                      layout='vertical'
                      align='right'
                      verticalAlign='middle'
                      iconType='circle'
                      wrapperStyle={{ fontSize: 12, lineHeight: '1.8em' }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              {/* Revenue breakdown — mobile cards / desktop table */}
              <div>
                {/* Mobile card layout */}
                <div className='sm:hidden space-y-2'>
                  {revenuePieData.map((r: any) => {
                    const Icon = REVENUE_ICONS[r.name] || DollarSign;
                    const total = revenuePieData.reduce(
                      (sum: number, x: any) => sum + (x.value ?? 0),
                      0
                    );
                    const shareWidth = total > 0 ? ((r.value ?? 0) / total) * 100 : 0;
                    return (
                      <div key={r.name} className='rounded-lg border border-gray-100 p-3'>
                        <div className='flex items-center justify-between gap-2'>
                          <div className='flex items-center gap-2 min-w-0'>
                            <div
                              className='w-7 h-7 rounded-md flex items-center justify-center shrink-0'
                              style={{ backgroundColor: `${r.color}15` }}>
                              <Icon size={14} style={{ color: r.color }} />
                            </div>
                            <span className='font-semibold text-gray-900 text-sm truncate'>
                              {r.name}
                            </span>
                          </div>
                          <span className='font-bold text-gov-dark text-sm shrink-0'>
                            KES {r.value}B
                          </span>
                        </div>
                        {/* Share bar */}
                        <div className='w-full h-1.5 bg-gray-100 rounded-full mt-2'>
                          <div
                            className='h-full rounded-full'
                            style={{ width: `${shareWidth}%`, backgroundColor: r.color }}
                          />
                        </div>
                        <div className='flex items-center justify-between mt-1.5 text-[11px] text-gray-500'>
                          <span>{pct(r.share)} of revenue</span>
                          {r.growth != null ? (
                            <span
                              className={`inline-flex items-center gap-0.5 font-medium px-1.5 py-0.5 rounded-full ${
                                r.growth > 0
                                  ? 'bg-green-50 text-green-600'
                                  : r.growth < 0
                                    ? 'bg-red-50 text-red-600'
                                    : 'bg-gray-100 text-gray-500'
                              }`}>
                              {r.growth > 0 ? (
                                <ArrowUp size={10} />
                              ) : r.growth < 0 ? (
                                <ArrowDown size={10} />
                              ) : (
                                <Minus size={10} />
                              )}
                              {Math.abs(r.growth).toFixed(1)}%
                            </span>
                          ) : (
                            <span className='text-gray-400'>—</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Desktop table */}
                <div className='hidden sm:block overflow-x-auto'>
                  <table className='w-full text-sm'>
                    <thead>
                      <tr className='border-b border-gray-200'>
                        <th className='text-left py-2 text-gray-500 font-medium'>Source</th>
                        <th className='text-right py-2 text-gray-500 font-medium'>Amount</th>
                        <th className='text-right py-2 text-gray-500 font-medium'>Share</th>
                        <th className='text-right py-2 text-gray-500 font-medium'>YoY</th>
                      </tr>
                    </thead>
                    <tbody>
                      {revenuePieData.map((r: any) => {
                        const Icon = REVENUE_ICONS[r.name] || DollarSign;
                        return (
                          <tr
                            key={r.name}
                            className='border-b border-gray-50 hover:bg-gray-50/60 transition-colors'>
                            <td className='py-2.5'>
                              <div className='flex items-center gap-2'>
                                <div
                                  className='w-7 h-7 rounded-md flex items-center justify-center'
                                  style={{ backgroundColor: `${r.color}15` }}>
                                  <Icon size={14} style={{ color: r.color }} />
                                </div>
                                <span className='font-medium text-gray-800'>{r.name}</span>
                              </div>
                            </td>
                            <td className='text-right text-gray-700'>KES {r.value}B</td>
                            <td className='text-right text-gray-700'>{pct(r.share)}</td>
                            <td className='text-right'>
                              {r.growth != null ? (
                                <span
                                  className={`inline-flex items-center gap-0.5 text-xs font-medium px-1.5 py-0.5 rounded-full ${
                                    r.growth > 0
                                      ? 'bg-green-50 text-green-600'
                                      : r.growth < 0
                                        ? 'bg-red-50 text-red-600'
                                        : 'bg-gray-100 text-gray-500'
                                  }`}>
                                  {r.growth > 0 ? (
                                    <ArrowUp size={12} />
                                  ) : r.growth < 0 ? (
                                    <ArrowDown size={12} />
                                  ) : (
                                    <Minus size={12} />
                                  )}
                                  {Math.abs(r.growth).toFixed(1)}%
                                </span>
                              ) : (
                                <span className='text-gray-400'>—</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Year-over-year comparison by source */}
            {revenueTrendData.length > 1 && (
              <div className='mt-6 pt-5 border-t border-gray-100'>
                <h3 className='text-sm font-semibold text-gray-700 mb-4'>
                  Revenue Growth by Source
                </h3>
                <div className='grid sm:grid-cols-2 lg:grid-cols-3 gap-4'>
                  {Object.keys(REVENUE_COLORS).map((type) => {
                    const color = REVENUE_COLORS[type];
                    const Icon = REVENUE_ICONS[type] || DollarSign;
                    // Get values per year for this type
                    const yearValues = revenueTrendData.map((fy: any) => ({
                      year: fy.year,
                      amount: fy[type] ?? 0,
                    }));
                    const max = Math.max(...yearValues.map((v: any) => v.amount), 1);
                    const latest = yearValues[yearValues.length - 1];
                    const prev = yearValues.length > 1 ? yearValues[yearValues.length - 2] : null;
                    const growth =
                      prev && prev.amount > 0
                        ? ((latest.amount - prev.amount) / prev.amount) * 100
                        : null;

                    return (
                      <div key={type} className='bg-gray-50 rounded-lg p-4 flex flex-col gap-3'>
                        {/* Header */}
                        <div className='flex items-center justify-between'>
                          <div className='flex items-center gap-2'>
                            <div
                              className='w-7 h-7 rounded-md flex items-center justify-center'
                              style={{ backgroundColor: `${color}15` }}>
                              <Icon size={14} style={{ color }} />
                            </div>
                            <span className='text-sm font-semibold text-gray-800'>{type}</span>
                          </div>
                          {growth != null && (
                            <span
                              className={`inline-flex items-center gap-0.5 text-xs font-medium px-1.5 py-0.5 rounded-full ${
                                growth > 0
                                  ? 'bg-green-50 text-green-600'
                                  : growth < 0
                                    ? 'bg-red-50 text-red-600'
                                    : 'bg-gray-100 text-gray-500'
                              }`}>
                              {growth > 0 ? (
                                <ArrowUp size={10} />
                              ) : growth < 0 ? (
                                <ArrowDown size={10} />
                              ) : (
                                <Minus size={10} />
                              )}
                              {Math.abs(growth).toFixed(1)}%
                            </span>
                          )}
                        </div>

                        {/* Year bars */}
                        <div className='space-y-2'>
                          {yearValues.map((v: any) => (
                            <div key={v.year} className='flex items-center gap-2'>
                              <span className='text-[11px] text-gray-400 w-14 shrink-0 tabular-nums'>
                                {v.year}
                              </span>
                              <div className='flex-1 h-4 bg-gray-200/60 rounded-full overflow-hidden'>
                                <div
                                  className='h-full rounded-full transition-all duration-500'
                                  style={{
                                    width: `${(v.amount / max) * 100}%`,
                                    backgroundColor: color,
                                    opacity: v.year === latest.year ? 1 : 0.5,
                                  }}
                                />
                              </div>
                              <span className='text-xs font-medium text-gray-700 w-12 text-right tabular-nums'>
                                {v.amount > 0 ? `${v.amount}B` : '—'}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </motion.section>
      )}

      {/* ═══ Section 5 — Sector Allocation (Pie + Table) ═══ */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ delay: 0.1, duration: 0.5 }}>
        <div className='bg-white rounded-xl border border-gray-100 p-5'>
          <h2 className='text-lg font-bold text-gray-900 mb-1'>Where the Money Goes</h2>
          <p className='text-sm text-gray-500 mb-5'>Sector allocation from county budget lines</p>

          <div className='grid lg:grid-cols-2 gap-6'>
            {/* Pie chart */}
            <div className='h-64 sm:h-80'>
              <ResponsiveContainer width='100%' height='100%'>
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey='value'
                    nameKey='name'
                    cx='50%'
                    cy='50%'
                    outerRadius='80%'
                    innerRadius='40%'
                    paddingAngle={2}
                    strokeWidth={1}
                    stroke='#fff'>
                    {pieData.map((entry: any, i: number) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number) => fmtKES(value)}
                    contentStyle={{ borderRadius: 8, fontSize: 13 }}
                  />
                  <Legend
                    layout='vertical'
                    align='right'
                    verticalAlign='middle'
                    iconType='circle'
                    wrapperStyle={{ fontSize: 12, lineHeight: '1.8em' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* Sector breakdown — mobile cards / desktop table */}
            <div>
              {/* Mobile card layout */}
              <div className='sm:hidden space-y-2'>
                {sectors.map((s: any) => {
                  const Icon = SECTOR_ICONS[s.sector] || BarChart3;
                  const color = SECTOR_COLORS[s.sector] || '#94a3b8';
                  return (
                    <div key={s.sector} className='rounded-lg border border-gray-100 p-3'>
                      <div className='flex items-center justify-between gap-2'>
                        <div className='flex items-center gap-2 min-w-0'>
                          <div
                            className='w-7 h-7 rounded-md flex items-center justify-center shrink-0'
                            style={{ backgroundColor: `${color}15` }}>
                            <Icon size={14} style={{ color }} />
                          </div>
                          <div className='min-w-0'>
                            <span className='font-semibold text-gray-900 text-sm block truncate'>
                              {s.sector}
                            </span>
                            <span className='text-[11px] text-gray-400'>
                              {pct(s.percentage)} of budget
                            </span>
                          </div>
                        </div>
                        <div className='text-right shrink-0'>
                          <div className='font-bold text-gov-dark text-sm'>
                            {fmtKES(s.allocated)}
                          </div>
                          <div className='text-[10px] text-gray-400'>allocated</div>
                        </div>
                      </div>
                      {/* Utilisation bar */}
                      <div className='w-full h-1.5 bg-gray-100 rounded-full mt-2'>
                        <div
                          className='h-full rounded-full'
                          style={{
                            width: `${Math.min(s.utilization || 0, 100)}%`,
                            backgroundColor: color,
                          }}
                        />
                      </div>
                      <div className='flex items-center justify-between mt-1.5 text-[11px] text-gray-500'>
                        <span>
                          Spent:{' '}
                          <span className='font-medium text-gray-700'>{fmtKES(s.spent)}</span>
                        </span>
                        <span
                          className={`font-semibold ${
                            s.utilization >= 50
                              ? 'text-green-600'
                              : s.utilization >= 25
                                ? 'text-amber-600'
                                : 'text-red-500'
                          }`}>
                          {pct(s.utilization)} used
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Desktop table */}
              <div className='hidden sm:block overflow-x-auto'>
                <table className='w-full text-sm'>
                  <thead>
                    <tr className='border-b border-gray-200'>
                      <th className='text-left py-2 text-gray-500 font-medium'>Sector</th>
                      <th className='text-right py-2 text-gray-500 font-medium'>Allocated</th>
                      <th className='text-right py-2 text-gray-500 font-medium'>Spent</th>
                      <th className='text-right py-2 text-gray-500 font-medium'>Utilization</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sectors.map((s: any) => {
                      const Icon = SECTOR_ICONS[s.sector] || BarChart3;
                      const color = SECTOR_COLORS[s.sector] || '#94a3b8';
                      return (
                        <tr
                          key={s.sector}
                          className='border-b border-gray-50 hover:bg-gray-50/60 transition-colors'>
                          <td className='py-2.5'>
                            <div className='flex items-center gap-2'>
                              <div
                                className='w-7 h-7 rounded-md flex items-center justify-center'
                                style={{ backgroundColor: `${color}15` }}>
                                <Icon size={14} style={{ color }} />
                              </div>
                              <span className='font-medium text-gray-800'>{s.sector}</span>
                              <span className='text-xs text-gray-400'>{pct(s.percentage)}</span>
                            </div>
                          </td>
                          <td className='text-right text-gray-700'>{fmtKES(s.allocated)}</td>
                          <td className='text-right text-gray-700'>{fmtKES(s.spent)}</td>
                          <td className='text-right'>
                            <span
                              className={`font-semibold ${
                                s.utilization >= 50
                                  ? 'text-green-600'
                                  : s.utilization >= 25
                                    ? 'text-amber-600'
                                    : 'text-red-500'
                              }`}>
                              {pct(s.utilization)}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </motion.section>

      {/* ═══ Section 6 — Budget Execution by Sector ═══ */}
      {executionData.length > 0 && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1, duration: 0.5 }}>
          <div className='bg-white rounded-xl border border-gray-100 p-5'>
            <div className='flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-2 mb-5'>
              <div>
                <h2 className='text-lg font-bold text-gray-900'>Budget Execution by Sector</h2>
                <p className='text-sm text-gray-500'>
                  How much of each sector&apos;s allocation was actually spent
                </p>
              </div>
              <div className='flex items-center gap-2 text-sm'>
                <span className='text-gray-500'>Overall:</span>
                <span
                  className={`font-bold text-lg ${
                    overallExecRate >= 70
                      ? 'text-green-600'
                      : overallExecRate >= 50
                        ? 'text-amber-600'
                        : 'text-red-500'
                  }`}>
                  {pct(overallExecRate)}
                </span>
              </div>
            </div>

            {/* ── Mobile card layout ── */}
            <div className='sm:hidden space-y-3'>
              {executionData.map((s: any, i: number) => {
                const Icon = SECTOR_ICONS[s.sector] || BarChart3;
                const color = SECTOR_COLORS[s.sector] || '#94a3b8';
                const fillWidth = s.allocated > 0 ? (s.spent / s.allocated) * 100 : 0;
                return (
                  <motion.div
                    key={s.sector}
                    initial={{ opacity: 0, x: -12 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.04, duration: 0.35 }}
                    className='rounded-lg border border-gray-100 p-3'>
                    <div className='flex items-center justify-between gap-2'>
                      <div className='flex items-center gap-2 min-w-0'>
                        <div
                          className='w-7 h-7 rounded-md flex items-center justify-center shrink-0'
                          style={{ backgroundColor: `${color}15` }}>
                          <Icon size={14} style={{ color }} />
                        </div>
                        <span className='font-semibold text-gray-900 text-sm truncate'>
                          {s.sector}
                        </span>
                      </div>
                      <span
                        className={`text-sm font-bold shrink-0 ${
                          s.execution_rate >= 70
                            ? 'text-green-600'
                            : s.execution_rate >= 50
                              ? 'text-amber-600'
                              : 'text-red-500'
                        }`}>
                        {pct(s.execution_rate)}
                      </span>
                    </div>
                    {/* Full-width execution bar */}
                    <div className='w-full h-2 bg-gray-100 rounded-full mt-2.5 overflow-hidden'>
                      <div
                        className='h-full rounded-full transition-all duration-700'
                        style={{
                          width: `${fillWidth}%`,
                          backgroundColor: color,
                        }}
                      />
                    </div>
                    <div className='flex items-center justify-between mt-1.5 text-[11px] text-gray-500'>
                      <span>
                        Spent: <span className='font-medium text-gray-700'>KES {s.spent}B</span>
                      </span>
                      <span>
                        of <span className='font-medium text-gray-700'>{s.allocated}B</span>{' '}
                        allocated
                      </span>
                    </div>
                  </motion.div>
                );
              })}
            </div>

            {/* ── Desktop bar rows ── */}
            <div className='hidden sm:block space-y-4'>
              {executionData.map((s: any, i: number) => {
                const Icon = SECTOR_ICONS[s.sector] || BarChart3;
                const color = SECTOR_COLORS[s.sector] || '#94a3b8';
                const maxAlloc = executionData[0]?.allocated || 1;
                const barWidth = (s.allocated / maxAlloc) * 100;
                const fillWidth = s.allocated > 0 ? (s.spent / s.allocated) * 100 : 0;
                return (
                  <motion.div
                    key={s.sector}
                    initial={{ opacity: 0, x: -12 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.04, duration: 0.35 }}
                    className='group'>
                    <div className='flex items-center gap-3 mb-1.5'>
                      <div
                        className='w-7 h-7 rounded-md flex items-center justify-center shrink-0'
                        style={{ backgroundColor: `${color}15` }}>
                        <Icon size={14} style={{ color }} />
                      </div>
                      <span className='text-sm font-medium text-gray-800 min-w-[110px]'>
                        {s.sector}
                      </span>
                      <div className='flex-1 flex items-center gap-2'>
                        {/* Progress bar — outer width = relative size, inner fill = execution */}
                        <div
                          className='h-6 bg-gray-100 rounded-full overflow-hidden relative'
                          style={{ width: `${Math.max(barWidth, 12)}%` }}>
                          <div
                            className='h-full rounded-full transition-all duration-700'
                            style={{
                              width: `${fillWidth}%`,
                              backgroundColor: color,
                              opacity: 0.8,
                            }}
                          />
                          {/* Text inside bar */}
                          <span className='absolute inset-0 flex items-center justify-center text-[11px] font-semibold text-gray-700'>
                            {pct(s.execution_rate)}
                          </span>
                        </div>
                      </div>
                      <div className='text-right shrink-0 w-28'>
                        <p className='text-sm font-semibold text-gray-800 tabular-nums'>
                          KES {s.spent}B
                        </p>
                        <p className='text-[10px] text-gray-400 tabular-nums'>
                          of {s.allocated}B allocated
                        </p>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>

            {/* Legend */}
            <div className='flex items-center gap-4 mt-5 pt-4 border-t border-gray-100 text-xs text-gray-400'>
              <div className='flex items-center gap-1.5'>
                <div className='w-3 h-3 rounded-sm bg-gray-100 border border-gray-200' />
                <span>Allocated</span>
              </div>
              <div className='flex items-center gap-1.5'>
                <div className='w-3 h-3 rounded-sm bg-gov-forest/60' />
                <span>Spent</span>
              </div>
              <span className='ml-auto'>Source: Controller of Budget, FY 2023/24</span>
            </div>
          </div>
        </motion.section>
      )}

      {/* ═══ Section 7 — Recurrent vs Development Spending ═══ */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ delay: 0.1, duration: 0.5 }}>
        <div className='bg-white rounded-xl border border-gray-100 p-5'>
          <h2 className='text-lg font-bold text-gray-900 mb-1'>Spending Mix Over Time</h2>
          <p className='text-sm text-gray-500 mb-5'>
            Recurrent vs development vs county allocation — KES Billions
          </p>
          <div className='h-72' role="img" aria-label="Bar chart showing recurrent versus development versus county allocation spending mix over time">
            <ResponsiveContainer width='100%' height='100%'>
              <BarChart data={spendingMixData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray='3 3' stroke='#f0f0f0' />
                <XAxis dataKey='year' tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `${v}B`} />
                <Tooltip content={<ChartTooltip />} />
                <Legend iconType='circle' wrapperStyle={{ fontSize: 13 }} />
                <Bar dataKey='Recurrent' fill='#6b7280' radius={[4, 4, 0, 0]} />
                <Bar dataKey='Development' fill='#1a5632' radius={[4, 4, 0, 0]} />
                <Bar dataKey='Counties' fill='#3b82f6' radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </motion.section>

      {/* ═══ Section 6 — County Utilization Leaderboard ═══ */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ delay: 0.1, duration: 0.5 }}>
        <div className='grid md:grid-cols-2 gap-4'>
          {/* Top performers */}
          <div className='bg-white rounded-xl border border-gray-100 p-5'>
            <h3 className='text-base font-bold text-gray-900 mb-1'>Top Budget Utilization</h3>
            <p className='text-xs text-gray-400 mb-4'>
              Counties spending their allocated budgets most efficiently
            </p>
            <div className='space-y-3'>
              {(countyUtil.top_5 ?? []).map((c: any, i: number) => (
                <div key={c.county} className='flex items-center gap-3'>
                  <span className='w-6 h-6 rounded-full bg-green-50 text-green-700 text-xs font-bold flex items-center justify-center'>
                    {i + 1}
                  </span>
                  <div className='flex-1'>
                    <div className='flex items-center justify-between mb-1'>
                      <span className='text-sm font-medium text-gray-800'>{c.county}</span>
                      <span className='text-sm font-bold text-green-600'>{pct(c.utilization)}</span>
                    </div>
                    <div className='h-1.5 bg-gray-100 rounded-full overflow-hidden'>
                      <div
                        className='h-full bg-green-500 rounded-full transition-all'
                        style={{ width: `${Math.min(c.utilization, 100)}%` }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Bottom performers */}
          <div className='bg-white rounded-xl border border-gray-100 p-5'>
            <h3 className='text-base font-bold text-gray-900 mb-1'>Lowest Budget Utilization</h3>
            <p className='text-xs text-gray-400 mb-4'>
              Counties with the most unspent allocated funds
            </p>
            <div className='space-y-3'>
              {(countyUtil.bottom_5 ?? []).map((c: any, i: number) => (
                <div key={c.county} className='flex items-center gap-3'>
                  <span className='w-6 h-6 rounded-full bg-red-50 text-red-600 text-xs font-bold flex items-center justify-center'>
                    {(countyUtil.bottom_5?.length ?? 0) - i}
                  </span>
                  <div className='flex-1'>
                    <div className='flex items-center justify-between mb-1'>
                      <span className='text-sm font-medium text-gray-800'>{c.county}</span>
                      <span className='text-sm font-bold text-red-500'>{pct(c.utilization)}</span>
                    </div>
                    <div className='h-1.5 bg-gray-100 rounded-full overflow-hidden'>
                      <div
                        className='h-full bg-red-400 rounded-full transition-all'
                        style={{ width: `${Math.min(c.utilization, 100)}%` }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {countyUtil.average > 0 && (
          <div className='bg-gov-forest/5 rounded-xl p-4 mt-4 text-center'>
            <p className='text-sm text-gray-600'>
              National average county budget utilization:{' '}
              <span className='font-bold text-gov-forest text-base'>{pct(countyUtil.average)}</span>
            </p>
          </div>
        )}
      </motion.section>

      {/* ═══ Section 9 — Budget in Economic Context ═══ */}
      {economicContext.gdp_billion_kes && (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1, duration: 0.5 }}>
          <div className='bg-white rounded-xl border border-gray-100 p-5'>
            <h2 className='text-lg font-bold text-gray-900 mb-1'>Budget in Economic Context</h2>
            <p className='text-sm text-gray-500 mb-5'>
              How Kenya&apos;s budget relates to the wider economy —{' '}
              {economicContext.fiscal_year ?? ''}
            </p>

            <div className='grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4'>
              {[
                {
                  icon: TrendingUp,
                  label: 'GDP',
                  value: `KES ${(economicContext.gdp_billion_kes / 1000).toFixed(1)}T`,
                  sub: `Growth: ${pct(economicContext.gdp_growth_pct)}`,
                  color: '#1a5632',
                },
                {
                  icon: PieIcon,
                  label: 'Budget / GDP',
                  value: pct(economicContext.budget_to_gdp_pct),
                  sub: `Revenue / GDP: ${pct(economicContext.revenue_to_gdp_pct)}`,
                  color: '#3b82f6',
                },
                {
                  icon: Activity,
                  label: 'Inflation',
                  value: pct(economicContext.inflation_pct),
                  sub: 'Consumer Price Index',
                  color:
                    economicContext.inflation_pct > 7
                      ? '#ef4444'
                      : economicContext.inflation_pct > 5
                        ? '#f59e0b'
                        : '#10b981',
                },
                {
                  icon: Users,
                  label: 'Per Capita Budget',
                  value: `KES ${Math.round(economicContext.per_capita_budget_kes).toLocaleString()}`,
                  sub: `Revenue: KES ${Math.round(economicContext.per_capita_revenue_kes).toLocaleString()}`,
                  color: '#6366f1',
                },
                {
                  icon: Briefcase,
                  label: 'Unemployment',
                  value: pct(economicContext.unemployment_pct),
                  sub: `Pop: ${(economicContext.total_population / 1e6).toFixed(1)}M`,
                  color: '#ec4899',
                },
              ].map(({ icon: Icon, label, value, sub, color }, i) => (
                <motion.div
                  key={label}
                  initial={{ opacity: 0, y: 12 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.06, duration: 0.4 }}
                  className='bg-gray-50 rounded-lg p-4 text-center'>
                  <div
                    className='w-10 h-10 rounded-lg flex items-center justify-center mx-auto mb-2'
                    style={{ backgroundColor: `${color}12` }}>
                    <Icon size={20} style={{ color }} />
                  </div>
                  <p className='text-xs text-gray-500 mb-1'>{label}</p>
                  <p className='text-xl font-bold text-gray-900'>{value}</p>
                  {sub && <p className='text-[11px] text-gray-400 mt-0.5'>{sub}</p>}
                </motion.div>
              ))}
            </div>

            {/* Interpretation strip */}
            <div className='mt-4 bg-gov-forest/5 rounded-lg p-3 flex items-start gap-2'>
              <ArrowRight size={16} className='text-gov-forest mt-0.5 shrink-0' />
              <p className='text-xs text-gray-600 leading-relaxed'>
                Kenya&apos;s government spends approximately{' '}
                <span className='font-semibold text-gray-800'>
                  {pct(economicContext.budget_to_gdp_pct)}
                </span>{' '}
                of national output, collecting{' '}
                <span className='font-semibold text-gray-800'>
                  {pct(economicContext.revenue_to_gdp_pct)}
                </span>{' '}
                in revenue. That leaves a fiscal gap filled by borrowing. Each citizen&apos;s share
                of the budget is roughly{' '}
                <span className='font-semibold text-gray-800'>
                  KES {Math.round(economicContext.per_capita_budget_kes).toLocaleString()}
                </span>{' '}
                per year.
              </p>
            </div>
          </div>
        </motion.section>
      )}

      {/* ═══ Section 10 — Key Takeaways ═══ */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ delay: 0.1, duration: 0.5 }}>
        <div className='bg-white rounded-xl border border-gray-100 p-5'>
          <h2 className='text-lg font-bold text-gray-900 mb-4'>Key Takeaways</h2>
          <div className='grid sm:grid-cols-2 lg:grid-cols-3 gap-4'>
            {activeData.appropriated_budget && (
              <div className='bg-gray-50 rounded-lg p-4'>
                <h4 className='text-sm font-semibold text-gray-800 mb-1'>Budget Size</h4>
                <p className='text-xs text-gray-600 leading-relaxed'>
                  The {activeFY} national budget stands at KES{' '}
                  {fmtB(activeData.appropriated_budget)}, with{' '}
                  {pct(
                    ((activeData.recurrent_spending ?? 0) / (activeData.appropriated_budget ?? 1)) *
                      100
                  )}{' '}
                  going to recurrent expenditure and{' '}
                  {pct(
                    ((activeData.development_spending ?? 0) /
                      (activeData.appropriated_budget ?? 1)) *
                      100
                  )}{' '}
                  to development.
                </p>
              </div>
            )}
            {activeData.total_borrowing > 0 && (
              <div className='bg-gray-50 rounded-lg p-4'>
                <h4 className='text-sm font-semibold text-gray-800 mb-1'>Borrowing Gap</h4>
                <p className='text-xs text-gray-600 leading-relaxed'>
                  Revenue covers KES {fmtB(activeData.total_revenue)} of the budget. The remaining
                  KES {fmtB(activeData.total_borrowing)} ({pct(activeData.borrowing_pct_of_budget)})
                  is financed through borrowing — both domestic and external.
                </p>
              </div>
            )}
            {sectors.length > 0 && (
              <div className='bg-gray-50 rounded-lg p-4'>
                <h4 className='text-sm font-semibold text-gray-800 mb-1'>Top Sector</h4>
                <p className='text-xs text-gray-600 leading-relaxed'>
                  {sectors[0]?.sector} receives the largest county allocation at{' '}
                  {pct(sectors[0]?.percentage)} of total funds ({fmtKES(sectors[0]?.allocated)}),
                  followed by {sectors[1]?.sector} ({pct(sectors[1]?.percentage)}) and{' '}
                  {sectors[2]?.sector} ({pct(sectors[2]?.percentage)}).
                </p>
              </div>
            )}
          </div>
        </div>
      </motion.section>

      {/* ═══ Data source attribution ═══ */}
      <motion.div
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        className='text-center text-xs text-gray-400 pt-2'>
        Data: National Treasury Budget Policy Statement, Controller of Budget, CRA, Kenya Revenue
        Authority
        {overview?.last_updated && (
          <span> · Updated {new Date(overview.last_updated).toLocaleDateString()}</span>
        )}
      </motion.div>
    </PageShell>
  );
}
