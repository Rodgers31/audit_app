'use client';

import PageShell from '@/components/layout/PageShell';
import PDFExportButton from '@/components/PDFExportButton';
import WatchButton from '@/components/WatchButton';
import { useCountyAccountability, useCountyComprehensive } from '@/lib/react-query/useCounties';
import { useCountyMoneyFlow } from '@/lib/react-query/useMoneyFlow';
import { useAvailableFiscalYears } from '@/lib/react-query';
import { useCountyPendingBills } from '@/lib/react-query/useDebt';
import { AccountabilityScorecard, CountyComprehensive } from '@/types';
import { AnimatePresence, motion } from 'framer-motion';
import FollowTheMoney, { YearSelector } from '@/components/FollowTheMoney';
import {
  AlertTriangle,
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Award,
  Banknote,
  CheckCircle2,
  ChevronDown,
  CircleDollarSign,
  Clock,
  ExternalLink,
  FileWarning,
  HardHat,
  Info,
  Landmark,
  Scale,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
  X,
} from 'lucide-react';
import Link from 'next/link';
import { useParams, useSearchParams } from 'next/navigation';
import React, { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

/* ═══════════ Utilities ═══════════ */
function fmtKES(n: number): string {
  if (n >= 1e9) return `KES ${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `KES ${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `KES ${(n / 1e3).toFixed(0)}K`;
  return `KES ${n.toLocaleString()}`;
}
function fmtShort(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)}M`;
  return n.toLocaleString();
}
function fmtPop(n: number): string {
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return String(n);
}
/** Convert snake_case to Title Case (e.g. "financial_services" → "Financial Services") */
function fmtLabel(s: string): string {
  return s
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}
function pct(n: number): string {
  return `${n.toFixed(1)}%`;
}

/* ═══════════ Shared constants ═══════════ */
const PALETTE = [
  '#3b82f6',
  '#ef4444',
  '#22c55e',
  '#f59e0b',
  '#8b5cf6',
  '#06b6d4',
  '#ec4899',
  '#14b8a6',
  '#f97316',
  '#6366f1',
  '#a855f7',
  '#84cc16',
  '#0ea5e9',
  '#e11d48',
  '#94a3b8',
];

type Tab = 'overview' | 'budget' | 'audit' | 'accountability' | 'projects' | 'money';

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: 'overview', label: 'Overview', icon: Landmark },
  { id: 'money', label: 'Follow the Money', icon: Banknote },
  { id: 'budget', label: 'Budget & Debt', icon: CircleDollarSign },
  { id: 'audit', label: 'Audit Findings', icon: ShieldAlert },
  { id: 'accountability', label: 'Accountability', icon: Award },
  { id: 'projects', label: 'Projects', icon: HardHat },
];

const SEVERITY_STYLE: Record<string, { label: string; dot: string; bg: string; text: string }> = {
  critical: { label: 'Critical', dot: 'bg-red-500', bg: 'bg-red-50', text: 'text-red-800' },
  warning: { label: 'Warning', dot: 'bg-amber-500', bg: 'bg-amber-50', text: 'text-amber-800' },
  info: { label: 'Info', dot: 'bg-blue-500', bg: 'bg-blue-50', text: 'text-blue-800' },
};

/* ═══════════ Grade Badge ═══════════ */
function GradeBadge({
  grade,
  score,
  onClick,
}: {
  grade: string;
  score: number;
  onClick?: () => void;
}) {
  const bg: Record<string, string> = {
    A: 'from-emerald-500 to-emerald-600',
    'B+': 'from-green-500 to-green-600',
    B: 'from-amber-500 to-amber-600',
    'B-': 'from-orange-500 to-orange-600',
    C: 'from-red-500 to-red-600',
  };
  return (
    <button
      type='button'
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      title='Click to see how this score is calculated'
      style={{ position: 'relative', zIndex: 100 }}
      className={`inline-flex items-center gap-2.5 px-5 py-2.5 rounded-xl bg-gradient-to-r ${bg[grade] || bg.C} text-white shadow-lg cursor-pointer hover:brightness-110 hover:scale-105 transition-all group`}>
      <span className='text-3xl font-black leading-none'>{grade}</span>
      <div className='border-l border-white/30 pl-2.5'>
        <div className='text-[10px] uppercase tracking-widest opacity-70 flex items-center gap-1'>
          Health <Info size={10} className='opacity-0 group-hover:opacity-100 transition-opacity' />
        </div>
        <div className='text-base font-bold leading-tight'>{score.toFixed(0)}</div>
      </div>
    </button>
  );
}

/* ═══════════ Health Score Methodology Modal ═══════════ */
const GRADE_THRESHOLDS = [
  { min: 85, grade: 'A', label: 'Excellent', color: 'bg-emerald-500' },
  { min: 70, grade: 'B+', label: 'Good', color: 'bg-green-500' },
  { min: 55, grade: 'B', label: 'Fair', color: 'bg-amber-500' },
  { min: 40, grade: 'B-', label: 'Needs Improvement', color: 'bg-orange-500' },
  { min: 0, grade: 'C', label: 'Poor', color: 'bg-red-500' },
];

function HealthScoreModal({
  open,
  onClose,
  data,
}: {
  open: boolean;
  onClose: () => void;
  data: CountyComprehensive;
}) {
  // Close on Escape key
  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [open, onClose]);

  if (!open) return null;

  const { financial_summary, budget, debt, audit, stalled_projects } = data;
  const utilization = budget.utilization_rate;
  const healthScore = financial_summary.health_score;
  const grade = financial_summary.grade;

  // Determine which threshold is active
  const activeThreshold =
    GRADE_THRESHOLDS.find((t) => healthScore >= t.min) ||
    GRADE_THRESHOLDS[GRADE_THRESHOLDS.length - 1];

  return (
    <div
      className='fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm'
      onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        onClick={(e) => e.stopPropagation()}
        className='bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto'>
        {/* Header */}
        <div className='bg-gradient-to-r from-gov-dark to-gov-forest px-6 py-5 rounded-t-2xl flex items-center justify-between'>
          <div>
            <h2 className='text-lg font-bold text-white'>Financial Health Score</h2>
            <p className='text-sm text-white/70 mt-0.5'>{data.name} County</p>
          </div>
          <button
            onClick={onClose}
            className='text-white/70 hover:text-white transition-colors p-1 rounded-lg hover:bg-white/10'>
            <X size={20} />
          </button>
        </div>

        <div className='px-6 py-5 space-y-6'>
          {/* Score display */}
          <div className='text-center'>
            <div className='inline-flex items-center gap-3 bg-gray-50 rounded-xl px-6 py-4'>
              <span
                className={`text-4xl font-black ${activeThreshold.color} text-white w-14 h-14 rounded-xl flex items-center justify-center`}>
                {grade}
              </span>
              <div className='text-left'>
                <div className='text-2xl font-bold text-gray-900'>
                  {healthScore.toFixed(1)}
                  <span className='text-sm text-gray-500 font-normal'> / 100</span>
                </div>
                <div className='text-sm text-gray-500'>{activeThreshold.label}</div>
              </div>
            </div>
          </div>

          {/* How it's calculated */}
          <div>
            <h3 className='text-sm font-semibold text-gray-900 uppercase tracking-wide mb-3'>
              How It&apos;s Calculated
            </h3>
            <div className='bg-gray-50 rounded-xl p-4 space-y-3 text-sm text-gray-700'>
              <p>
                The health score is derived from the county&apos;s{' '}
                <strong>budget execution rate</strong> &mdash; how much of the allocated budget was
                actually spent in the fiscal year.
              </p>
              <div className='border-l-2 border-gov-sage pl-3 space-y-1'>
                <p>
                  <strong>If utilization &le; 95%:</strong> Score = utilization percentage
                </p>
                <p>
                  <strong>If 95% &lt; utilization &le; 100%:</strong> Score = 90 (near-perfect
                  execution)
                </p>
                <p>
                  <strong>If utilization &gt; 100% (overspend):</strong> Score = 80 &minus;
                  overspend %, penalizing excess spending
                </p>
              </div>
              <p className='text-xs text-gray-500 italic'>
                A score of 95 is the maximum — counties that spend close to their budget without
                overspending demonstrate the best fiscal discipline.
              </p>
            </div>
          </div>

          {/* This county's breakdown */}
          <div>
            <h3 className='text-sm font-semibold text-gray-900 uppercase tracking-wide mb-3'>
              This County&apos;s Numbers
            </h3>
            <div className='space-y-2'>
              {[
                { label: 'Budget Allocated', value: fmtKES(budget.total_allocated) },
                { label: 'Budget Spent', value: fmtKES(budget.total_spent) },
                {
                  label: 'Execution Rate',
                  value: `${utilization.toFixed(1)}%`,
                  highlight: true,
                },
                { label: 'Pending Bills', value: fmtKES(debt.pending_bills) },
                { label: 'Total Debt', value: fmtKES(debt.total_debt) },
                { label: 'Audit Issues', value: String(audit.findings_count) },
                { label: 'Stalled Projects', value: String(stalled_projects.count) },
              ].map((row) => (
                <div
                  key={row.label}
                  className={`flex justify-between items-center py-2 px-3 rounded-lg ${
                    row.highlight ? 'bg-gov-sage/10 font-semibold' : 'even:bg-gray-50'
                  }`}>
                  <span className='text-sm text-gray-600'>{row.label}</span>
                  <span className='text-sm text-gray-900 font-medium'>{row.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Grade scale */}
          <div>
            <h3 className='text-sm font-semibold text-gray-900 uppercase tracking-wide mb-3'>
              Grade Scale
            </h3>
            <div className='space-y-1.5'>
              {GRADE_THRESHOLDS.map((t) => (
                <div
                  key={t.grade}
                  className={`flex items-center gap-3 py-2 px-3 rounded-lg text-sm ${
                    t.grade === grade ? 'bg-gray-100 ring-1 ring-gray-300 font-semibold' : ''
                  }`}>
                  <span
                    className={`${t.color} text-white font-bold w-8 h-8 rounded-lg flex items-center justify-center text-xs`}>
                    {t.grade}
                  </span>
                  <span className='text-gray-700 flex-1'>{t.label}</span>
                  <span className='text-gray-400 text-xs'>{t.min > 0 ? `≥ ${t.min}` : `< 40`}</span>
                  {t.grade === grade && (
                    <span className='text-xs bg-gov-forest text-white px-2 py-0.5 rounded-full'>
                      Current
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Data source note */}
          <p className='text-xs text-gray-400 text-center'>
            Source: Office of the Auditor General &middot; FY 2024/25 county financial statements
          </p>
        </div>
      </motion.div>
    </div>
  );
}

/* ═══════════ KPI Pill ═══════════ */
function KPI({
  label,
  value,
  sub,
  accent = 'text-gray-900',
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div>
      <div className='text-[10px] uppercase tracking-wider text-gray-400 mb-0.5'>{label}</div>
      <div className={`text-base font-bold leading-tight ${accent}`}>{value}</div>
      {sub && <div className='text-[11px] text-gray-500'>{sub}</div>}
    </div>
  );
}

/* ═══════════ Circular progress ═══════════ */
function CircleProgress({
  value,
  size = 72,
  stroke = 5,
}: {
  value: number;
  size?: number;
  stroke?: number;
}) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (Math.min(value, 100) / 100) * circ;
  const color = value >= 70 ? '#22c55e' : value >= 50 ? '#f59e0b' : '#ef4444';
  return (
    <div
      className='relative inline-flex items-center justify-center'
      style={{ width: size, height: size }}>
      <svg width={size} height={size} className='-rotate-90'>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill='none'
          stroke='#f3f4f6'
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill='none'
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap='round'
          strokeDasharray={circ}
          strokeDashoffset={offset}
          className='transition-all duration-700'
        />
      </svg>
      <span className='absolute text-sm font-bold text-gray-800'>{value.toFixed(0)}%</span>
    </div>
  );
}

/* ═══════════ Tab: Overview ═══════════ */
function OverviewTab({ data }: { data: CountyComprehensive }) {
  const {
    demographics,
    economic_profile,
    budget,
    debt,
    audit,
    stalled_projects,
    financial_summary,
    missing_funds,
    revenue,
  } = data;

  const sustainLabel: Record<string, { text: string; color: string; Icon: React.ElementType }> = {
    sustainable: { text: 'Sustainable', color: 'text-emerald-700', Icon: TrendingUp },
    moderate: { text: 'Moderate Risk', color: 'text-amber-700', Icon: Scale },
    at_risk: { text: 'At Risk', color: 'text-red-700', Icon: TrendingDown },
  };
  const sust = sustainLabel[financial_summary.debt_sustainability] ?? sustainLabel.moderate;

  const typeLabels: Record<string, string> = {
    capital_city: 'Capital City',
    standard_county: 'Standard County',
    major_urban: 'Major Urban',
    pastoral: 'Pastoral',
    arid_semi_arid: 'Arid / Semi-Arid',
  };

  return (
    <div className='space-y-5'>
      {/* Key indicators row */}
      <div className='grid grid-cols-1 md:grid-cols-3 gap-4'>
        {/* Budget execution */}
        <div className='bg-white rounded-xl border border-gray-100 p-5 flex items-center gap-5'>
          <CircleProgress value={budget.utilization_rate} />
          <div>
            <div className='text-sm font-semibold text-gray-800 mb-1'>Budget Execution</div>
            <div className='text-xs text-gray-500'>
              {fmtKES(budget.total_spent)} of {fmtKES(budget.total_allocated)}
            </div>
          </div>
        </div>

        {/* Debt sustainability */}
        <div className='bg-white rounded-xl border border-gray-100 p-5'>
          <div className='flex items-center gap-2 mb-2'>
            <sust.Icon size={16} className={sust.color} />
            <span className={`text-sm font-semibold ${sust.color}`}>{sust.text}</span>
          </div>
          <div className='text-xs text-gray-500 space-y-1'>
            <div>Total debt: {fmtKES(debt.total_debt)}</div>
            <div>Debt-to-budget: {pct(debt.debt_to_budget_ratio)}</div>
            <div>Pending bills: {fmtKES(debt.pending_bills)}</div>
          </div>
        </div>

        {/* Audit snapshot */}
        <div className='bg-white rounded-xl border border-gray-100 p-5'>
          <div className='text-sm font-semibold text-gray-800 mb-2'>Audit Snapshot</div>
          <div className='flex items-center gap-4 mb-2'>
            {(['critical', 'warning', 'info'] as const).map((sev) => {
              const count = audit.by_severity[sev] || 0;
              const s = SEVERITY_STYLE[sev];
              return (
                <div key={sev} className='flex items-center gap-1.5'>
                  <div className={`w-2 h-2 rounded-full ${s.dot}`} />
                  <span className='text-xs text-gray-600'>
                    {count} {s.label.toLowerCase()}
                  </span>
                </div>
              );
            })}
          </div>
          {audit.total_amount_involved > 0 && (
            <div className='text-xs text-gray-500'>
              {fmtKES(audit.total_amount_involved)} total amount involved
            </div>
          )}
        </div>
      </div>

      {/* Missing funds banner */}
      {(missing_funds.total_amount > 0 || missing_funds.cases_count > 0) && (
        <div className='bg-red-50 border border-red-200 rounded-xl p-4 flex items-center gap-4'>
          <div className='w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0'>
            <AlertTriangle size={20} className='text-red-600' />
          </div>
          <div>
            <div className='text-sm font-semibold text-red-900'>
              {fmtKES(missing_funds.total_amount)} Unaccounted
            </div>
            <div className='text-xs text-red-700'>
              {missing_funds.cases_count} cases identified by OAG
            </div>
          </div>
        </div>
      )}

      {/* About this county */}
      <div className='bg-white rounded-xl border border-gray-100 p-5'>
        <h3 className='text-sm font-semibold text-gray-800 mb-3'>County Profile</h3>
        <div className='grid grid-cols-2 sm:grid-cols-4 gap-y-4 gap-x-6'>
          <KPI
            label='Population'
            value={fmtPop(demographics.population)}
            sub={
              demographics.population_year ? `Census ${demographics.population_year}` : undefined
            }
            accent='text-blue-700'
          />
          <KPI label='Governor' value={data.governor || 'N/A'} accent='text-purple-700' />
          <KPI
            label='Economic Base'
            value={fmtLabel(economic_profile.economic_base)}
            accent='text-emerald-700'
          />
          <KPI
            label='Total Revenue'
            value={fmtKES(revenue.total_revenue)}
            sub={revenue.local_revenue > 0 ? `Local: ${fmtKES(revenue.local_revenue)}` : undefined}
            accent='text-green-700'
          />
        </div>

        {economic_profile.major_issues.length > 0 && (
          <div className='mt-4 pt-4 border-t border-gray-100'>
            <div className='text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2'>
              Key Challenges
            </div>
            <div className='flex flex-wrap gap-2'>
              {economic_profile.major_issues.map((issue, i) => (
                <span
                  key={i}
                  className='text-xs bg-amber-50 text-amber-800 border border-amber-200 rounded-full px-2.5 py-1'>
                  {issue}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Stalled projects summary */}
      {stalled_projects.count > 0 && (
        <div className='bg-white rounded-xl border border-gray-100 p-5'>
          <div className='flex items-center gap-2 mb-2'>
            <HardHat size={16} className='text-red-600' />
            <h3 className='text-sm font-semibold text-gray-800'>
              {stalled_projects.count} Stalled Project{stalled_projects.count !== 1 ? 's' : ''}
            </h3>
          </div>
          <div className='text-xs text-gray-500 mb-1'>
            Total contracted: {fmtKES(stalled_projects.total_contracted_value)} &middot; Paid:{' '}
            {fmtKES(stalled_projects.total_amount_paid)} (
            {pct(
              (stalled_projects.total_amount_paid /
                (stalled_projects.total_contracted_value || 1)) *
                100
            )}{' '}
            disbursed)
          </div>
          <p className='text-xs text-gray-400'>See the Projects tab for full details.</p>
        </div>
      )}
    </div>
  );
}

/* ═══════════ Tab: Budget & Debt ═══════════ */
function BudgetTab({ data }: { data: CountyComprehensive }) {
  const { budget, debt } = data;
  const { data: countyPendingBills } = useCountyPendingBills(data.id.toString());

  const sectors = useMemo(
    () =>
      Object.entries(budget.sector_breakdown)
        .map(([name, vals], i) => ({
          name: name.length > 22 ? name.slice(0, 20) + '...' : name,
          fullName: name,
          allocated: vals.allocated,
          spent: vals.spent,
          fill: PALETTE[i % PALETTE.length],
        }))
        .sort((a, b) => b.allocated - a.allocated)
        .slice(0, 10),
    [budget.sector_breakdown]
  );

  const pieData = sectors.map((s) => ({ name: s.name, value: s.allocated, fill: s.fill }));

  return (
    <div className='space-y-5'>
      {/* Top-level budget stats */}
      <div className='bg-white rounded-xl border border-gray-100 p-5'>
        <h3 className='text-sm font-semibold text-gray-800 mb-4'>Budget Summary</h3>
        <div className='grid grid-cols-2 sm:grid-cols-4 gap-y-4 gap-x-6'>
          <KPI
            label='Total Allocated'
            value={fmtKES(budget.total_allocated)}
            accent='text-blue-700'
          />
          <KPI
            label='Total Spent'
            value={fmtKES(budget.total_spent)}
            sub={`${pct(budget.utilization_rate)} execution`}
            accent='text-emerald-700'
          />
          <KPI
            label='Development'
            value={fmtKES(budget.development_budget)}
            accent='text-amber-700'
          />
          <KPI label='Recurrent' value={fmtKES(budget.recurrent_budget)} accent='text-purple-700' />
        </div>
      </div>

      {/* Sector charts */}
      <div className='grid grid-cols-1 lg:grid-cols-5 gap-4'>
        {/* Bar chart: 3/5 */}
        <div className='lg:col-span-3 bg-white rounded-xl border border-gray-100 p-5'>
          <h3 className='text-sm font-semibold text-gray-800 mb-3'>Sector Spending</h3>
          <div className='h-[340px]'>
            <ResponsiveContainer width='100%' height='100%'>
              <BarChart
                data={sectors}
                layout='vertical'
                margin={{ left: 5, right: 15, top: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray='3 3' stroke='#f3f4f6' />
                <XAxis type='number' tickFormatter={(v) => fmtShort(v)} tick={{ fontSize: 10 }} />
                <YAxis type='category' dataKey='name' width={115} tick={{ fontSize: 11 }} />
                <Tooltip
                  formatter={(v: number, name: string) => [
                    fmtKES(v),
                    name === 'allocated' ? 'Allocated' : 'Spent',
                  ]}
                  contentStyle={{ borderRadius: 10, border: '1px solid #e5e7eb', fontSize: 12 }}
                />
                <Bar
                  dataKey='allocated'
                  fill='#3b82f6'
                  radius={[0, 3, 3, 0]}
                  name='Allocated'
                  barSize={12}
                />
                <Bar
                  dataKey='spent'
                  fill='#22c55e'
                  radius={[0, 3, 3, 0]}
                  name='Spent'
                  barSize={12}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Pie chart: 2/5 */}
        <div className='lg:col-span-2 bg-white rounded-xl border border-gray-100 p-5'>
          <h3 className='text-sm font-semibold text-gray-800 mb-3'>Distribution</h3>
          <div className='h-[300px]'>
            <ResponsiveContainer width='100%' height='100%'>
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey='value'
                  nameKey='name'
                  cx='50%'
                  cy='50%'
                  outerRadius={100}
                  innerRadius={48}
                  paddingAngle={1.5}
                  strokeWidth={1}>
                  {pieData.map((e, i) => (
                    <Cell key={i} fill={e.fill} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(v: number) => fmtKES(v)}
                  contentStyle={{ borderRadius: 10, fontSize: 12 }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          {/* Legend */}
          <div className='flex flex-wrap gap-x-3 gap-y-1 mt-2'>
            {sectors.slice(0, 6).map((s) => (
              <div key={s.name} className='flex items-center gap-1'>
                <div className='w-2 h-2 rounded-full' style={{ backgroundColor: s.fill }} />
                <span className='text-[10px] text-gray-600'>{s.name}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Debt breakdown */}
      {debt.breakdown.length > 0 && (
        <div className='bg-white rounded-xl border border-gray-100 p-5'>
          <h3 className='text-sm font-semibold text-gray-800 mb-4'>Debt Breakdown</h3>
          <div className='space-y-3'>
            {debt.breakdown.map((d, i) => {
              const pctOfTotal = debt.total_debt > 0 ? (d.outstanding / debt.total_debt) * 100 : 0;
              return (
                <div key={i}>
                  <div className='flex items-center justify-between mb-1'>
                    <span className='text-sm text-gray-700'>{d.lender}</span>
                    <span className='text-sm font-semibold text-gray-900 tabular-nums'>
                      {fmtKES(d.outstanding)}
                    </span>
                  </div>
                  <div className='h-2 bg-gray-100 rounded-full overflow-hidden'>
                    <div
                      className='h-full rounded-full bg-red-400'
                      style={{ width: `${Math.min(pctOfTotal, 100)}%` }}
                    />
                  </div>
                  <div className='text-[10px] text-gray-400 mt-0.5'>
                    {pct(pctOfTotal)} of total debt
                  </div>
                </div>
              );
            })}
          </div>
          <div className='mt-4 pt-3 border-t border-gray-100 flex items-center justify-between text-sm'>
            <span className='text-gray-500'>Total Debt</span>
            <span className='font-bold text-red-700'>{fmtKES(debt.total_debt)}</span>
          </div>
        </div>
      )}

      {/* County Pending Bills Breakdown */}
      {(countyPendingBills || debt.pending_bills > 0) && (
        <div className='bg-white rounded-xl border border-red-200 p-5'>
          <div className='flex items-center gap-2 mb-4'>
            <FileWarning size={16} className='text-red-600' />
            <h3 className='text-sm font-semibold text-gray-800'>Pending Bills</h3>
            <span className='text-sm font-bold text-red-700 ml-auto'>
              {fmtKES(countyPendingBills?.total_pending || debt.pending_bills)}
            </span>
          </div>

          {/* Breakdown by type */}
          {countyPendingBills?.breakdown_by_type && countyPendingBills.breakdown_by_type.length > 0 && (
            <div className='space-y-2 mb-4'>
              <h4 className='text-xs font-semibold text-gray-500 uppercase tracking-wider'>By Type</h4>
              {countyPendingBills.breakdown_by_type.map((t) => {
                const colors: Record<string, string> = {
                  supplier_arrears: 'bg-red-500',
                  salary: 'bg-blue-500',
                  pension: 'bg-purple-500',
                  statutory: 'bg-amber-500',
                  court_awards: 'bg-orange-500',
                };
                const bgColor = Object.entries(colors).find(([k]) => t.type.toLowerCase().includes(k))?.[1] || 'bg-gray-400';
                return (
                  <div key={t.type}>
                    <div className='flex items-center justify-between mb-0.5'>
                      <span className='text-xs text-gray-700'>
                        {t.type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                      </span>
                      <span className='text-xs font-semibold text-gray-800'>{fmtKES(t.amount)}</span>
                    </div>
                    <div className='h-2 bg-gray-100 rounded-full overflow-hidden'>
                      <div
                        className={`h-full rounded-full ${bgColor}`}
                        style={{ width: `${Math.min(t.percentage, 100)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Aging buckets */}
          {countyPendingBills?.aging_buckets && countyPendingBills.aging_buckets.length > 0 && (
            <div>
              <h4 className='text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2'>Aging</h4>
              <div className='flex h-4 rounded-full overflow-hidden'>
                {countyPendingBills.aging_buckets.map((bucket) => {
                  const colors: Record<string, string> = {
                    '0-30d': '#22c55e',
                    '31-90d': '#f59e0b',
                    '91-180d': '#f97316',
                    '180d+': '#ef4444',
                  };
                  return (
                    <div
                      key={bucket.bucket}
                      className='transition-all'
                      style={{
                        width: `${bucket.percentage}%`,
                        backgroundColor: colors[bucket.bucket] || '#94a3b8',
                      }}
                      title={`${bucket.bucket}: ${fmtKES(bucket.amount)} (${bucket.percentage.toFixed(1)}%)`}
                    />
                  );
                })}
              </div>
              <div className='flex items-center gap-3 mt-2 text-[10px] text-gray-400 flex-wrap'>
                {countyPendingBills.aging_buckets.map((bucket) => {
                  const colors: Record<string, string> = {
                    '0-30d': '#22c55e',
                    '31-90d': '#f59e0b',
                    '91-180d': '#f97316',
                    '180d+': '#ef4444',
                  };
                  return (
                    <div key={bucket.bucket} className='flex items-center gap-1'>
                      <div
                        className='w-2 h-2 rounded-full'
                        style={{ backgroundColor: colors[bucket.bucket] || '#94a3b8' }}
                      />
                      <span>{bucket.bucket}: {fmtKES(bucket.amount)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {!countyPendingBills && debt.pending_bills > 0 && (
            <p className='text-xs text-gray-500'>
              This county has {fmtKES(debt.pending_bills)} in pending bills. Detailed breakdown data
              will be available once the county reports are processed.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/* ═══════════ Tab: Audit ═══════════ */

const CATEGORY_CONFIG: Record<string, { label: string; color: string; bg: string; icon: string }> =
  {
    'Financial Irregularity': {
      label: 'Financial Irregularity',
      color: 'text-red-700',
      bg: 'bg-red-50 border-red-200',
      icon: '💰',
    },
    'Asset Management': {
      label: 'Asset Management',
      color: 'text-amber-700',
      bg: 'bg-amber-50 border-amber-200',
      icon: '🏗️',
    },
    'Missing Funds': {
      label: 'Missing / Unaccounted Funds',
      color: 'text-red-800',
      bg: 'bg-red-100 border-red-300',
      icon: '🚨',
    },
    'Procurement Issues': {
      label: 'Procurement Issues',
      color: 'text-orange-700',
      bg: 'bg-orange-50 border-orange-200',
      icon: '📋',
    },
    'Payroll Issues': {
      label: 'Payroll Issues',
      color: 'text-purple-700',
      bg: 'bg-purple-50 border-purple-200',
      icon: '👥',
    },
    'Revenue Collection': {
      label: 'Revenue Collection',
      color: 'text-blue-700',
      bg: 'bg-blue-50 border-blue-200',
      icon: '🏦',
    },
    other: { label: 'Other', color: 'text-gray-700', bg: 'bg-gray-50 border-gray-200', icon: '📄' },
  };

const STATUS_CONFIG: Record<string, { label: string; color: string; dot: string }> = {
  'Under Review': {
    label: 'Under Review',
    color: 'text-yellow-700 bg-yellow-50 border-yellow-200',
    dot: 'bg-yellow-500',
  },
  Escalated: {
    label: 'Escalated',
    color: 'text-red-700 bg-red-50 border-red-200',
    dot: 'bg-red-500',
  },
  Resolved: {
    label: 'Resolved',
    color: 'text-green-700 bg-green-50 border-green-200',
    dot: 'bg-green-500',
  },
  Pending: {
    label: 'Pending',
    color: 'text-gray-600 bg-gray-50 border-gray-200',
    dot: 'bg-gray-400',
  },
  open: {
    label: 'Open',
    color: 'text-yellow-700 bg-yellow-50 border-yellow-200',
    dot: 'bg-yellow-500',
  },
};

function AuditTab({ data }: { data: CountyComprehensive }) {
  const { audit, missing_funds } = data;
  const [expanded, setExpanded] = useState<number | null>(null);
  const [filterCategory, setFilterCategory] = useState<string>('all');

  // Group findings by category for the summary
  const categoryBreakdown = useMemo(() => {
    const map: Record<string, { count: number; amount: number }> = {};
    for (const f of audit.findings) {
      const cat = f.category || 'other';
      if (!map[cat]) map[cat] = { count: 0, amount: 0 };
      map[cat].count++;
      map[cat].amount += f.amount_involved || 0;
    }
    return Object.entries(map).sort((a, b) => b[1].amount - a[1].amount);
  }, [audit.findings]);

  const filteredFindings = useMemo(() => {
    if (filterCategory === 'all') return audit.findings;
    return audit.findings.filter((f) => (f.category || 'other') === filterCategory);
  }, [audit.findings, filterCategory]);

  const statusCounts = useMemo(() => {
    const map: Record<string, number> = {};
    for (const f of audit.findings) {
      const st = f.status || 'open';
      map[st] = (map[st] || 0) + 1;
    }
    return map;
  }, [audit.findings]);

  return (
    <div className='space-y-5'>
      {/* ── What this means (plain language intro) ── */}
      <div className='bg-gov-forest/5 border border-gov-forest/20 rounded-xl p-4'>
        <h3 className='text-sm font-semibold text-gov-dark mb-1'>What are audit findings?</h3>
        <p className='text-xs text-gray-600 leading-relaxed'>
          The Office of the Auditor-General examines how your county government spends public money.
          When they find problems — like missing funds, irregular spending, or poor record-keeping —
          they report them as &quot;audit findings.&quot; Each finding below shows{' '}
          <strong>what went wrong</strong>, <strong>how much money is involved</strong>, and the{' '}
          <strong>current status</strong> of the issue.
        </p>
      </div>

      {/* ── Top-level stats ── */}
      <div className='grid grid-cols-2 sm:grid-cols-4 gap-3'>
        <div className='bg-white rounded-xl border border-gray-100 p-4 text-center'>
          <div className='text-2xl font-bold text-gray-900'>{audit.findings_count}</div>
          <div className='text-[11px] text-gray-500 mt-0.5'>Total Findings</div>
        </div>
        <div className='bg-white rounded-xl border border-gray-100 p-4 text-center'>
          <div className='text-2xl font-bold text-red-700'>
            {audit.total_amount_involved > 0 ? fmtKES(audit.total_amount_involved) : 'KES 0'}
          </div>
          <div className='text-[11px] text-gray-500 mt-0.5'>Total Money Questioned</div>
        </div>
        <div className='bg-white rounded-xl border border-gray-100 p-4 text-center'>
          <div className='flex items-center justify-center gap-1.5'>
            <div className='w-2 h-2 rounded-full bg-red-500' />
            <span className='text-2xl font-bold text-gray-900'>
              {audit.by_severity.critical || 0}
            </span>
          </div>
          <div className='text-[11px] text-gray-500 mt-0.5'>Critical Issues</div>
        </div>
        <div className='bg-white rounded-xl border border-gray-100 p-4 text-center'>
          <div className='text-2xl font-bold text-green-700'>{statusCounts['Resolved'] || 0}</div>
          <div className='text-[11px] text-gray-500 mt-0.5'>Resolved</div>
        </div>
      </div>

      {/* ── Category breakdown ── */}
      {categoryBreakdown.length > 0 && (
        <div className='bg-white rounded-xl border border-gray-100 p-5'>
          <h3 className='text-sm font-semibold text-gray-800 mb-3'>Findings by Category</h3>
          <div className='space-y-2'>
            {categoryBreakdown.map(([cat, { count, amount }]) => {
              const cfg = CATEGORY_CONFIG[cat] || CATEGORY_CONFIG.other;
              const pctOfTotal =
                audit.total_amount_involved > 0 ? (amount / audit.total_amount_involved) * 100 : 0;
              return (
                <button
                  key={cat}
                  onClick={() => setFilterCategory(filterCategory === cat ? 'all' : cat)}
                  className={`w-full text-left rounded-lg border p-3 transition-all ${
                    filterCategory === cat
                      ? 'ring-2 ring-gov-forest/30 border-gov-forest/40 bg-gov-forest/5'
                      : 'hover:bg-gray-50 border-gray-100'
                  }`}>
                  <div className='flex items-center justify-between mb-1'>
                    <div className='flex items-center gap-2'>
                      <span className='text-sm'>{cfg.icon}</span>
                      <span className='text-sm font-medium text-gray-800'>{cfg.label}</span>
                      <span className='text-xs text-gray-400'>
                        {count} finding{count !== 1 ? 's' : ''}
                      </span>
                    </div>
                    {amount > 0 && (
                      <span className={`text-sm font-semibold ${cfg.color}`}>{fmtKES(amount)}</span>
                    )}
                  </div>
                  {pctOfTotal > 0 && (
                    <div className='h-1.5 bg-gray-100 rounded-full overflow-hidden'>
                      <div
                        className='h-full bg-red-400 rounded-full transition-all'
                        style={{ width: `${Math.min(pctOfTotal, 100)}%` }}
                      />
                    </div>
                  )}
                </button>
              );
            })}
          </div>
          {filterCategory !== 'all' && (
            <button
              onClick={() => setFilterCategory('all')}
              className='mt-2 text-xs text-gov-forest hover:underline'>
              ← Show all categories
            </button>
          )}
        </div>
      )}

      {/* ── Status summary row ── */}
      <div className='flex flex-wrap gap-2'>
        {Object.entries(statusCounts).map(([status, count]) => {
          const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.open;
          return (
            <div
              key={status}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border ${cfg.color}`}>
              <div className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
              {cfg.label}: {count}
            </div>
          );
        })}
      </div>

      {/* ── Missing funds alert ── */}
      {(missing_funds.total_amount > 0 || missing_funds.cases_count > 0) && (
        <div className='bg-red-50 border border-red-200 rounded-xl p-4'>
          <div className='flex items-center gap-2 mb-1'>
            <AlertTriangle size={16} className='text-red-600' />
            <span className='text-sm font-semibold text-red-900'>
              {fmtKES(missing_funds.total_amount)} Missing / Unaccounted
            </span>
          </div>
          <div className='text-xs text-red-700'>
            {missing_funds.cases_count} case(s) flagged by the Auditor-General as money that cannot
            be accounted for.
          </div>
        </div>
      )}

      {/* ── Findings list ── */}
      <div className='space-y-3'>
        <div className='flex items-center justify-between'>
          <h3 className='text-sm font-semibold text-gray-800'>
            {filterCategory === 'all'
              ? 'All Audit Findings'
              : `${(CATEGORY_CONFIG[filterCategory] || CATEGORY_CONFIG.other).label} Findings`}
          </h3>
          <span className='text-xs text-gray-400'>
            {filteredFindings.length} finding{filteredFindings.length !== 1 ? 's' : ''}
          </span>
        </div>

        {filteredFindings.slice(0, 20).map((f) => {
          const s = SEVERITY_STYLE[f.severity] || SEVERITY_STYLE.info;
          const catCfg = CATEGORY_CONFIG[f.category] || CATEGORY_CONFIG.other;
          const stCfg = STATUS_CONFIG[f.status] || STATUS_CONFIG.open;
          const open = expanded === f.id;

          return (
            <div
              key={f.id}
              className={`rounded-xl border border-gray-100 bg-white overflow-hidden transition-shadow ${
                open ? 'shadow-md ring-1 ring-gray-200' : 'hover:shadow-sm'
              }`}>
              <button
                onClick={() => setExpanded(open ? null : f.id)}
                className='w-full text-left px-4 py-3.5 hover:bg-gray-50/50 transition-colors'>
                {/* Top row: category tag + status + amount */}
                <div className='flex items-center gap-2 flex-wrap mb-2'>
                  <span
                    className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border ${catCfg.bg} ${catCfg.color}`}>
                    {catCfg.icon} {catCfg.label}
                  </span>
                  <span
                    className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full border ${stCfg.color}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${stCfg.dot}`} />
                    {stCfg.label}
                  </span>
                  <span className={`text-[10px] font-bold uppercase tracking-wider ${s.text}`}>
                    {s.label}
                  </span>
                  {f.audit_year && (
                    <span className='text-[10px] text-gray-400 ml-auto'>FY {f.audit_year}</span>
                  )}
                </div>

                {/* Finding text */}
                <p className='text-sm text-gray-800 leading-relaxed mb-1.5'>{f.finding}</p>

                {/* Bottom row: amount + reference + expand arrow */}
                <div className='flex items-center gap-3'>
                  {f.amount_involved > 0 && (
                    <span className='text-sm font-bold text-red-700 tabular-nums'>
                      {fmtKES(f.amount_involved)}
                    </span>
                  )}
                  {f.reference && (
                    <span className='text-[10px] text-gray-400 font-mono'>Ref: {f.reference}</span>
                  )}
                  <ChevronDown
                    size={14}
                    className={`text-gray-400 ml-auto flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
                  />
                </div>
              </button>

              <AnimatePresence>
                {open && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className='overflow-hidden'>
                    <div className='px-4 pb-4 pt-0 border-t border-gray-100'>
                      {/* What this means section */}
                      <div className='mt-3 mb-3 bg-blue-50 border border-blue-100 rounded-lg p-3'>
                        <h4 className='text-xs font-semibold text-blue-800 mb-1'>
                          What does this mean?
                        </h4>
                        <p className='text-xs text-blue-700 leading-relaxed'>
                          {f.category === 'Missing Funds' &&
                            `The auditors found KES ${f.amount_involved > 0 ? f.amount_involved.toLocaleString() : 'an undisclosed amount'} that the county government cannot explain where it went. This money was meant for public services.`}
                          {f.category === 'Financial Irregularity' &&
                            `The county spent KES ${f.amount_involved > 0 ? f.amount_involved.toLocaleString() : 'an amount'} without proper documentation or following financial rules. This makes it impossible to verify the money was used correctly.`}
                          {f.category === 'Asset Management' &&
                            `County assets worth KES ${f.amount_involved > 0 ? f.amount_involved.toLocaleString() : 'an undisclosed value'} are not being properly tracked, insured, or maintained — putting public property at risk.`}
                          {f.category === 'Procurement Issues' &&
                            `KES ${f.amount_involved > 0 ? f.amount_involved.toLocaleString() : 'Funds'} were spent on purchases that didn't follow proper procurement rules — potentially meaning taxpayers didn't get value for money.`}
                          {f.category === 'Payroll Issues' &&
                            `There are irregularities in how county staff are paid, involving KES ${f.amount_involved > 0 ? f.amount_involved.toLocaleString() : 'undisclosed amounts'}. This could mean ghost workers or unauthorized payments.`}
                          {![
                            'Missing Funds',
                            'Financial Irregularity',
                            'Asset Management',
                            'Procurement Issues',
                            'Payroll Issues',
                          ].includes(f.category || '') &&
                            `The auditors flagged an issue with how public money was managed${f.amount_involved > 0 ? `, involving KES ${f.amount_involved.toLocaleString()}` : ''}. This requires attention to ensure taxpayer money is protected.`}
                        </p>
                      </div>

                      {/* Recommendation */}
                      {f.recommendation && (
                        <div className='bg-green-50 border border-green-100 rounded-lg p-3'>
                          <h4 className='text-xs font-semibold text-green-800 mb-1'>
                            <CheckCircle2 size={12} className='inline mr-1' />
                            Auditor&apos;s Recommendation
                          </h4>
                          <p className='text-xs text-green-700 leading-relaxed'>
                            {f.recommendation}
                          </p>
                        </div>
                      )}

                      {/* Status explanation */}
                      <div className='mt-2 text-[11px] text-gray-500'>
                        {f.status === 'Resolved' &&
                          '✅ This issue has been addressed by the county government.'}
                        {f.status === 'Escalated' &&
                          '⚠️ This issue has been escalated for further investigation or action.'}
                        {f.status === 'Under Review' &&
                          '🔍 This issue is currently being reviewed by the relevant authorities.'}
                        {f.status === 'Pending' &&
                          '⏳ This issue is awaiting action from the county government.'}
                        {!['Resolved', 'Escalated', 'Under Review', 'Pending'].includes(
                          f.status || ''
                        ) && '📋 Status of this issue is being tracked.'}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>

      {filteredFindings.length > 20 && (
        <p className='text-xs text-gray-500 text-center'>
          Showing 20 of {filteredFindings.length} findings
        </p>
      )}
    </div>
  );
}

/* ═══════════ Tab: Projects ═══════════ */
function ProjectsTab({ data }: { data: CountyComprehensive }) {
  const { stalled_projects } = data;

  if (stalled_projects.count === 0) {
    return (
      <div className='bg-emerald-50 border border-emerald-200 rounded-xl p-6 text-center'>
        <CheckCircle2 size={32} className='mx-auto text-emerald-500 mb-2' />
        <p className='text-sm text-emerald-800 font-medium'>
          No stalled or significantly delayed projects
        </p>
        <p className='text-xs text-emerald-600 mt-1'>
          All audited development projects are progressing within acceptable parameters.
        </p>
      </div>
    );
  }

  return (
    <div className='space-y-4'>
      {/* Summary */}
      <div className='bg-white rounded-xl border border-gray-100 p-5'>
        <div className='grid grid-cols-3 gap-4'>
          <KPI
            label='Stalled / Delayed'
            value={String(stalled_projects.count)}
            accent='text-red-700'
          />
          <KPI
            label='Contracted Value'
            value={fmtKES(stalled_projects.total_contracted_value)}
            accent='text-blue-700'
          />
          <KPI
            label='Already Paid'
            value={fmtKES(stalled_projects.total_amount_paid)}
            sub={`${pct((stalled_projects.total_amount_paid / (stalled_projects.total_contracted_value || 1)) * 100)} disbursed`}
            accent='text-amber-700'
          />
        </div>
      </div>

      {/* Project cards */}
      {stalled_projects.projects.map((p, i) => (
        <div key={i} className='bg-white rounded-xl border border-gray-100 p-5'>
          <div className='flex items-start justify-between gap-3 mb-3'>
            <div className='min-w-0'>
              <h4 className='text-sm font-semibold text-gray-900'>{p.project_name}</h4>
              <div className='flex items-center gap-2 mt-0.5 flex-wrap'>
                <span className='text-xs text-gray-500'>{p.sector}</span>
                {p.oag_reference && (
                  <span className='text-[10px] text-gray-400 border border-gray-200 rounded px-1.5 py-0.5'>
                    {p.oag_reference}
                  </span>
                )}
              </div>
            </div>
            <span
              className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full border flex-shrink-0 ${
                p.status === 'stalled'
                  ? 'bg-red-50 border-red-200 text-red-700'
                  : 'bg-amber-50 border-amber-200 text-amber-700'
              }`}>
              {p.status === 'stalled' ? 'Stalled' : 'Delayed'}
            </span>
          </div>

          {/* Progress */}
          <div className='mb-3'>
            <div className='flex items-center justify-between mb-1'>
              <span className='text-xs text-gray-500'>{p.completion_pct}% complete</span>
              <span className='text-xs text-gray-500 tabular-nums'>
                {fmtKES(p.amount_paid)} / {fmtKES(p.contracted_amount)}
              </span>
            </div>
            <div className='h-2 bg-gray-100 rounded-full overflow-hidden'>
              <div
                className={`h-full rounded-full transition-all ${
                  p.status === 'stalled' ? 'bg-red-500' : 'bg-amber-500'
                }`}
                style={{ width: `${p.completion_pct}%` }}
              />
            </div>
          </div>

          {/* Meta */}
          <div className='flex items-center gap-4 text-xs text-gray-500 flex-wrap'>
            <span className='flex items-center gap-1'>
              <Clock size={11} />
              Started {p.start_year}
            </span>
            <span className='flex items-center gap-1'>
              <Clock size={11} />
              Expected {p.expected_completion}
            </span>
          </div>
          {p.reason && (
            <p className='text-xs text-gray-600 mt-2 bg-gray-50 rounded-lg p-2.5 border border-gray-100 italic'>
              {p.reason}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

/* ═══════════ Accountability Grade Colors ═══════════ */
const ACCT_GRADE_STYLE: Record<string, { bg: string; text: string; border: string; label: string }> = {
  A: { bg: 'bg-emerald-500', text: 'text-white', border: 'border-emerald-600', label: 'Excellent' },
  B: { bg: 'bg-teal-500', text: 'text-white', border: 'border-teal-600', label: 'Good' },
  C: { bg: 'bg-yellow-400', text: 'text-yellow-900', border: 'border-yellow-500', label: 'Fair' },
  D: { bg: 'bg-orange-500', text: 'text-white', border: 'border-orange-600', label: 'Needs Improvement' },
  F: { bg: 'bg-red-600', text: 'text-white', border: 'border-red-700', label: 'Poor' },
};

const OPINION_COLOR: Record<string, string> = {
  Unqualified: 'bg-emerald-500 text-white',
  Qualified: 'bg-yellow-400 text-yellow-900',
  Adverse: 'bg-red-500 text-white',
  Disclaimer: 'bg-red-700 text-white',
};

/* ═══════════ Tab: Accountability ═══════════ */
function AccountabilityTab({ data: countyData }: { data: CountyComprehensive }) {
  const { data, isLoading, error } = useCountyAccountability(countyData.id);

  if (isLoading) {
    return (
      <div className='flex items-center justify-center py-16'>
        <div className='animate-spin rounded-full h-10 w-10 border-b-2 border-gov-forest' />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className='bg-red-50 border border-red-200 rounded-xl p-6 text-center'>
        <ShieldAlert size={28} className='mx-auto text-red-400 mb-2' />
        <p className='text-sm text-red-700'>Failed to load accountability data</p>
      </div>
    );
  }

  const gradeStyle = ACCT_GRADE_STYLE[data.accountability_grade] || ACCT_GRADE_STYLE.F;
  const peer = data.peer_comparison;
  const isBelowRegion = data.total_flagged_amount > peer.region_avg_flagged_amount;
  const isBelowBracket = data.total_flagged_amount > peer.population_bracket_avg;

  return (
    <div className='space-y-5'>
      {/* A. GRADE CARD */}
      <div className='bg-white rounded-xl border border-gray-100 p-6'>
        <div className='flex flex-col sm:flex-row items-center gap-6'>
          <div className={`w-24 h-24 rounded-2xl ${gradeStyle.bg} ${gradeStyle.text} flex items-center justify-center shadow-lg`}>
            <span className='text-5xl font-black'>{data.accountability_grade}</span>
          </div>
          <div className='text-center sm:text-left'>
            <h3 className='text-lg font-bold text-gray-900'>Accountability Grade</h3>
            <p className='text-sm text-gray-500 mt-1'>
              {gradeStyle.label} — Based on audit opinions, flagged amounts, recurring findings, and budget absorption
            </p>
          </div>
        </div>
      </div>

      {/* C. KEY METRICS — 4 stat cards */}
      <div className='grid grid-cols-2 sm:grid-cols-4 gap-3'>
        <div className='bg-white rounded-xl border border-gray-100 p-4 text-center'>
          <div className='text-2xl font-bold text-red-700'>
            {data.total_flagged_amount > 0 ? fmtKES(data.total_flagged_amount) : 'KES 0'}
          </div>
          <div className='text-[11px] text-gray-500 mt-0.5'>Total Flagged Amount</div>
        </div>
        <div className='bg-white rounded-xl border border-gray-100 p-4 text-center'>
          <div className='text-2xl font-bold text-amber-700'>{data.recurring_findings_count}</div>
          <div className='text-[11px] text-gray-500 mt-0.5'>Recurring Findings</div>
        </div>
        <div className='bg-white rounded-xl border border-gray-100 p-4 text-center'>
          <div className='text-2xl font-bold text-orange-700'>{data.unresolved_findings_count}</div>
          <div className='text-[11px] text-gray-500 mt-0.5'>Unresolved Findings</div>
        </div>
        <div className='bg-white rounded-xl border border-gray-100 p-4 text-center'>
          <div className='text-2xl font-bold text-blue-700'>
            {data.absorption_rate !== null ? `${(data.absorption_rate * 100).toFixed(1)}%` : 'N/A'}
          </div>
          <div className='text-[11px] text-gray-500 mt-0.5'>Absorption Rate</div>
        </div>
      </div>

      {/* B. AUDIT OPINION HISTORY */}
      {data.audit_opinion_history.length > 0 && (
        <div className='bg-white rounded-xl border border-gray-100 p-5'>
          <h3 className='text-sm font-semibold text-gray-800 mb-4'>Audit Opinion History</h3>
          <div className='overflow-x-auto'>
            <table className='w-full border-collapse'>
              <thead>
                <tr className='border-b border-gray-100'>
                  <th className='text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500 py-2 px-3'>
                    Year
                  </th>
                  <th className='text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500 py-2 px-3'>
                    Opinion
                  </th>
                </tr>
              </thead>
              <tbody>
                {[...data.audit_opinion_history]
                  .sort((a, b) => b.year - a.year)
                  .map((entry) => {
                    const opinionCls = OPINION_COLOR[entry.opinion] || 'bg-gray-200 text-gray-700';
                    return (
                      <tr key={entry.year} className='border-b border-gray-50 last:border-0'>
                        <td className='py-2.5 px-3 text-sm text-gray-700 tabular-nums font-medium'>
                          FY {entry.year}/{(entry.year + 1).toString().slice(-2)}
                        </td>
                        <td className='py-2.5 px-3'>
                          <span
                            className={`inline-block text-xs font-semibold px-2.5 py-1 rounded-full ${opinionCls}`}>
                            {entry.opinion}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* D. PEER COMPARISON */}
      <div className='bg-white rounded-xl border border-gray-100 p-5'>
        <h3 className='text-sm font-semibold text-gray-800 mb-4'>Peer Comparison</h3>
        <div className='grid grid-cols-1 sm:grid-cols-2 gap-4'>
          {/* vs Region Average */}
          <div className='bg-gray-50 rounded-lg p-4'>
            <div className='text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-2'>
              vs {peer.region ? peer.region.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : 'Region'} Average
            </div>
            <div className='flex items-center gap-2 mb-1'>
              {isBelowRegion ? (
                <ArrowUp size={16} className='text-red-500' />
              ) : (
                <ArrowDown size={16} className='text-emerald-500' />
              )}
              <span className={`text-sm font-bold ${isBelowRegion ? 'text-red-700' : 'text-emerald-700'}`}>
                {isBelowRegion ? 'Above' : 'Below'} peer average
              </span>
            </div>
            <div className='text-xs text-gray-500 space-y-0.5'>
              <div>This county: {fmtKES(data.total_flagged_amount)} flagged</div>
              <div>Region avg: {fmtKES(peer.region_avg_flagged_amount)} flagged</div>
              {peer.region_avg_grade && (
                <div>Region avg grade: {peer.region_avg_grade}</div>
              )}
            </div>
          </div>

          {/* vs Population Bracket */}
          <div className='bg-gray-50 rounded-lg p-4'>
            <div className='text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-2'>
              vs {peer.population_bracket || 'Population Bracket'} Average
            </div>
            <div className='flex items-center gap-2 mb-1'>
              {isBelowBracket ? (
                <ArrowUp size={16} className='text-red-500' />
              ) : (
                <ArrowDown size={16} className='text-emerald-500' />
              )}
              <span className={`text-sm font-bold ${isBelowBracket ? 'text-red-700' : 'text-emerald-700'}`}>
                {isBelowBracket ? 'Above' : 'Below'} bracket average
              </span>
            </div>
            <div className='text-xs text-gray-500 space-y-0.5'>
              <div>This county: {fmtKES(data.total_flagged_amount)} flagged</div>
              <div>Bracket avg: {fmtKES(peer.population_bracket_avg)} flagged</div>
            </div>
          </div>
        </div>
        <p className='text-[11px] text-gray-400 mt-3'>
          Higher flagged amounts indicate more audit issues relative to peers. Lower is better.
        </p>
      </div>
    </div>
  );
}

/* ═══════════ Tab: Follow the Money ═══════════ */
const DEFAULT_FISCAL_YEARS = ['2024/25', '2023/24', '2022/23', '2021/22', '2020/21'];

function MoneyFlowTab({ data: countyData }: { data: CountyComprehensive }) {
  const [selectedYear, setSelectedYear] = useState(DEFAULT_FISCAL_YEARS[0]);
  const { data: fiscalYears } = useAvailableFiscalYears();
  const { data, isLoading } = useCountyMoneyFlow(countyData.id, selectedYear);

  const years = fiscalYears && fiscalYears.length > 0 ? fiscalYears : DEFAULT_FISCAL_YEARS;

  return (
    <div className='space-y-4'>
      <div className='bg-white rounded-xl border border-gray-100 p-5'>
        <div className='flex items-center justify-between mb-4'>
          <div>
            <h3 className='text-sm font-semibold text-gray-800'>Follow the Money</h3>
            <p className='text-xs text-gray-500 mt-0.5'>
              Trace how public funds flow from allocation to expenditure
            </p>
          </div>
          <YearSelector value={selectedYear} onChange={setSelectedYear} years={years} />
        </div>
        <FollowTheMoney data={data} isLoading={isLoading} />
      </div>
    </div>
  );
}

/* ═══════════ Data Sources Footer ═══════════ */
function SourcesFooter({ data }: { data: CountyComprehensive }) {
  const sources = [
    {
      key: 'budget',
      label: 'Budget',
      url: 'https://cob.go.ke/reports/county-budget-implementation-review-reports/',
    },
    {
      key: 'audit',
      label: 'Audit',
      url: 'https://www.oagkenya.go.ke/county-government-audit-reports/',
    },
    { key: 'debt', label: 'Debt', url: 'https://www.treasury.go.ke/county-governments/' },
    { key: 'population', label: 'Population', url: 'https://www.knbs.or.ke/publications/' },
  ];

  return (
    <div className='flex flex-wrap items-center gap-x-4 gap-y-1 pt-3 border-t border-gray-100'>
      <span className='text-[10px] text-gray-400 uppercase tracking-wider font-semibold'>
        Sources:
      </span>
      {sources.map((s) => (
        <a
          key={s.key}
          href={s.url}
          target='_blank'
          rel='noopener noreferrer'
          className='inline-flex items-center gap-1 text-[11px] text-gov-forest hover:underline'>
          {s.label}
          <ExternalLink size={9} />
        </a>
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════
   Main Page
   ═══════════════════════════════════════════ */
export default function CountyDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const countyId = params.id as string;
  const { data, isLoading, error } = useCountyComprehensive(countyId);

  const initialTab = (searchParams.get('tab') as Tab) || 'overview';
  const validTabs: Tab[] = ['overview', 'money', 'budget', 'audit', 'accountability', 'projects'];
  const [tab, setTab] = useState<Tab>(validTabs.includes(initialTab) ? initialTab : 'overview');
  const [showHealthModal, setShowHealthModal] = useState(false);

  /* Loading */
  if (isLoading) {
    return (
      <PageShell title='County Details' subtitle='Loading county data...'>
        <div className='flex items-center justify-center py-24'>
          <div className='animate-spin rounded-full h-14 w-14 border-b-2 border-gov-forest' />
        </div>
      </PageShell>
    );
  }

  /* Error */
  if (error || !data) {
    return (
      <PageShell title='County Details'>
        <div className='text-center py-16'>
          <ShieldAlert size={40} className='mx-auto text-red-400 mb-3' />
          <p className='text-red-600 mb-4'>Failed to load county data</p>
          <Link href='/counties' className='text-sm text-gov-forest hover:underline'>
            &larr; Back to County Explorer
          </Link>
        </div>
      </PageShell>
    );
  }

  /* Tab content */
  const TabContent = {
    overview: OverviewTab,
    money: MoneyFlowTab,
    budget: BudgetTab,
    audit: AuditTab,
    accountability: AccountabilityTab,
    projects: ProjectsTab,
  }[tab];

  return (
    <>
      <PageShell title={`${data.name} County`} subtitle='County government transparency report'>
        {/* Back */}
        <Link
          href='/counties'
          className='inline-flex items-center gap-1.5 text-sm text-gov-forest hover:text-gov-dark transition-colors'>
          <ArrowLeft size={14} />
          All Counties
        </Link>

        {/* ── Hero ── */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className='bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden'>
          {/* Top band with grade */}
          <div className='bg-gradient-to-r from-gov-dark to-gov-forest px-6 py-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4'>
            <div>
              <h1 className='text-xl font-bold text-white'>{data.name} County</h1>
              <p className='text-sm text-white/70 mt-0.5'>
                {fmtPop(data.demographics.population)} residents &middot;{' '}
                {fmtLabel(data.economic_profile.economic_base)} economy
              </p>
            </div>
            <div className='flex items-center gap-3'>
              <WatchButton itemType='county' itemId={countyId} label={`${data.name} County`} />
              <PDFExportButton
                compact
                documentTitle={`${data.name} County Report`}
                className='text-white/70 hover:text-white hover:bg-white/10'
              />
              <GradeBadge
                grade={data.financial_summary.grade}
                score={data.financial_summary.health_score}
                onClick={() => setShowHealthModal(true)}
              />
            </div>
          </div>

          {/* Quick KPIs */}
          <div className='grid grid-cols-3 sm:grid-cols-6 divide-x divide-gray-100'>
            {[
              { label: 'Budget', value: fmtKES(data.budget.total_allocated) },
              { label: 'Execution', value: pct(data.budget.utilization_rate) },
              { label: 'Total Debt', value: fmtKES(data.debt.total_debt) },
              { label: 'Pending Bills', value: fmtKES(data.debt.pending_bills) },
              { label: 'Audit Issues', value: String(data.audit.findings_count) },
              { label: 'Stalled', value: String(data.stalled_projects.count) },
            ].map((kpi) => (
              <div key={kpi.label} className='px-4 py-3 text-center'>
                <div className='text-sm font-bold text-gray-900 tabular-nums'>{kpi.value}</div>
                <div className='text-[10px] text-gray-500'>{kpi.label}</div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* ── Tabs ── */}
        <div className='flex items-center gap-1 bg-white rounded-xl border border-gray-200 p-1 shadow-sm overflow-x-auto'>
          {TABS.map((t) => {
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap ${
                  active
                    ? 'bg-gov-forest text-white shadow-sm'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                }`}>
                <t.icon size={14} />
                {t.label}
              </button>
            );
          })}
        </div>

        {/* ── Tab Content ── */}
        <motion.div
          key={tab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}>
          <TabContent data={data} />
        </motion.div>

        {/* ── Sources ── */}
        <SourcesFooter data={data} />
      </PageShell>

      {/* ── Health Score Modal ── rendered outside PageShell to avoid stacking context */}
      <HealthScoreModal
        open={showHealthModal}
        onClose={() => setShowHealthModal(false)}
        data={data}
      />
    </>
  );
}
