'use client';

import DataFreshnessBadge from '@/components/DataFreshnessBadge';
import { apiClient } from '@/lib/api/axios';
import { useCounties } from '@/lib/react-query';
import { County } from '@/types';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  ArrowUpDown,
  ChevronDown,
  ChevronsLeft,
  Download,
  Filter,
  Search,
  TrendingUp,
} from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts';

/* ══════════════════════════════════════════════════════════════════════════════
   HELPERS
   ══════════════════════════════════════════════════════════════════════════════ */

function fmtKES(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return n.toLocaleString();
}
function fmtPop(n: number): string {
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return String(n);
}

function getGrade(score: number) {
  if (score >= 85) return { letter: 'A', cls: 'bg-emerald-500 text-white' };
  if (score >= 75) return { letter: 'A-', cls: 'bg-emerald-400 text-white' };
  if (score >= 70) return { letter: 'B+', cls: 'bg-green-200 text-green-900' };
  if (score >= 60) return { letter: 'B', cls: 'bg-green-300 text-green-900' };
  if (score >= 50) return { letter: 'B-', cls: 'bg-green-400 text-white' };
  if (score >= 40) return { letter: 'C', cls: 'bg-orange-600 text-white' };
  if (score >= 30) return { letter: 'C+', cls: 'bg-orange-700 text-white' };
  if (score >= 20) return { letter: 'D', cls: 'bg-red-500 text-white' };
  return { letter: 'D-', cls: 'bg-red-700 text-white' };
}

const GRADE_ALL = ['A', 'B', 'C', 'D', 'D-'] as const;
const GRADE_COLORS: Record<string, string> = {
  A: 'bg-emerald-500 text-white',
  B: 'bg-green-300 text-green-900',
  C: 'bg-orange-600 text-white',
  D: 'bg-red-500 text-white',
  'D-': 'bg-red-700 text-white',
};

const AUDIT_STATUS_CFG: Record<
  string,
  { label: string; dot: string; chipBg: string; chipText: string }
> = {
  clean: {
    label: 'Clean',
    dot: 'bg-emerald-500',
    chipBg: 'bg-emerald-50',
    chipText: 'text-emerald-700',
  },
  qualified: {
    label: 'Qualified',
    dot: 'bg-amber-500',
    chipBg: 'bg-amber-50',
    chipText: 'text-amber-700',
  },
  adverse: { label: 'Adverse', dot: 'bg-red-500', chipBg: 'bg-red-50', chipText: 'text-red-700' },
  disclaimer: {
    label: 'Disclaimer',
    dot: 'bg-red-700',
    chipBg: 'bg-red-100',
    chipText: 'text-red-800',
  },
  pending: {
    label: 'Pending',
    dot: 'bg-gray-400',
    chipBg: 'bg-gray-50',
    chipText: 'text-gray-600',
  },
};

type SortField = 'name' | 'population' | 'health' | 'budget' | 'utilization' | 'debt';
type SortDir = 'asc' | 'desc';

function gradeCategory(score: number): string {
  if (score >= 70) return 'A';
  if (score >= 55) return 'B';
  if (score >= 40) return 'C';
  if (score >= 20) return 'D';
  return 'D-';
}

/* ── Accountability Grade Badge ─────────── */
const ACCT_GRADE_COLORS: Record<string, string> = {
  A: 'bg-emerald-500 text-white',
  B: 'bg-teal-500 text-white',
  C: 'bg-yellow-400 text-yellow-900',
  D: 'bg-orange-500 text-white',
  F: 'bg-red-600 text-white',
};

function useAccountabilityGrades(countyIds: string[]) {
  return useQuery({
    queryKey: ['accountability-grades', countyIds.sort().join(',')],
    queryFn: async () => {
      const results: Record<string, string> = {};
      const promises = countyIds.map(async (id) => {
        try {
          const res = await apiClient.get<{ accountability_grade: string }>(
            `/counties/${id}/summary`
          );
          results[id] = res.data.accountability_grade;
        } catch {
          // Skip failed fetches
        }
      });
      await Promise.all(promises);
      return results;
    },
    enabled: countyIds.length > 0,
    staleTime: 30 * 60 * 1000,
  });
}

function AccountabilityBadge({ grade }: { grade?: string }) {
  if (!grade) return null;
  const cls = ACCT_GRADE_COLORS[grade] || 'bg-gray-200 text-gray-700';
  return (
    <span
      className={`inline-flex items-center justify-center w-5 h-5 text-[9px] font-bold rounded ${cls}`}
      title={`Accountability Grade: ${grade}`}>
      {grade}
    </span>
  );
}

/* ── County → Region mapping (Kenya's 8 former provinces) ─────────── */
const COUNTY_REGION: Record<string, string> = {
  // Central
  Kiambu: 'central',
  Kirinyaga: 'central',
  "Murang'a": 'central',
  Nyandarua: 'central',
  Nyeri: 'central',
  // Coast
  Kilifi: 'coast',
  Kwale: 'coast',
  Lamu: 'coast',
  Mombasa: 'coast',
  'Taita-Taveta': 'coast',
  'Tana River': 'coast',
  // Eastern
  Embu: 'eastern',
  Isiolo: 'eastern',
  Kitui: 'eastern',
  Machakos: 'eastern',
  Makueni: 'eastern',
  Marsabit: 'eastern',
  Meru: 'eastern',
  'Tharaka-Nithi': 'eastern',
  // Nairobi
  Nairobi: 'nairobi',
  'Nairobi City': 'nairobi',
  // North Eastern
  Garissa: 'north-eastern',
  Mandera: 'north-eastern',
  Wajir: 'north-eastern',
  // Nyanza
  'Homa Bay': 'nyanza',
  Kisii: 'nyanza',
  Kisumu: 'nyanza',
  Migori: 'nyanza',
  Nyamira: 'nyanza',
  Siaya: 'nyanza',
  // Rift Valley
  Baringo: 'rift-valley',
  Bomet: 'rift-valley',
  'Elgeyo-Marakwet': 'rift-valley',
  Kajiado: 'rift-valley',
  Kericho: 'rift-valley',
  Laikipia: 'rift-valley',
  Nakuru: 'rift-valley',
  Nandi: 'rift-valley',
  Narok: 'rift-valley',
  Samburu: 'rift-valley',
  'Trans-Nzoia': 'rift-valley',
  Turkana: 'rift-valley',
  'Uasin Gishu': 'rift-valley',
  'West Pokot': 'rift-valley',
  // Western
  Bungoma: 'western',
  Busia: 'western',
  Kakamega: 'western',
  Vihiga: 'western',
};

function getCountyRegion(name: string): string {
  // Direct lookup first
  if (COUNTY_REGION[name]) return COUNTY_REGION[name];
  // Try stripping " County" suffix
  const stripped = name.replace(/ County$/i, '');
  if (COUNTY_REGION[stripped]) return COUNTY_REGION[stripped];
  return '';
}

/* Tiny sparkline SVG — decorative trend indicator */
function Sparkline({ seed, positive }: { seed: number; positive: boolean }) {
  const pts: number[] = [];
  const count = 12;
  let v = 40 + (seed % 20);
  for (let i = 0; i < count; i++) {
    // Add a clear trend direction + small noise
    const trend = positive ? 1.5 : -1.2;
    const noise = (((seed * (i + 1) * 7) % 13) - 6) * 0.6;
    v += trend + noise;
    v = Math.max(15, Math.min(90, v));
    pts.push(v);
  }
  const w = 80;
  const h = 40;
  const stepX = w / (count - 1);
  const points = pts.map((y, i) => ({
    x: i * stepX,
    y: h - (y / 100) * h,
  }));
  const linePath = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(' ');
  const areaPath = `${linePath} L${points[points.length - 1].x.toFixed(1)},${h} L0,${h} Z`;
  const color = positive ? '#22c55e' : '#ef4444';
  const gradId = `spark-grad-${seed}`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className='w-16 h-10' preserveAspectRatio='none'>
      <defs>
        <linearGradient id={gradId} x1='0' y1='0' x2='0' y2='1'>
          <stop offset='0%' stopColor={color} stopOpacity='0.3' />
          <stop offset='100%' stopColor={color} stopOpacity='0.02' />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradId})`} />
      <path
        d={linePath}
        fill='none'
        stroke={color}
        strokeWidth='2'
        strokeLinecap='round'
        strokeLinejoin='round'
      />
      {/* End dot */}
      <circle
        cx={points[points.length - 1].x}
        cy={points[points.length - 1].y}
        r='2.5'
        fill={color}
      />
    </svg>
  );
}

/* Gauge component */
function GaugeMini({ value, target }: { value: number; target: number }) {
  const angle = Math.min(value / 100, 1) * 180;
  const targetAngle = Math.min(target / 100, 1) * 180;
  return (
    <div className='relative w-14 h-8'>
      <svg viewBox='0 0 100 55' className='w-full h-full'>
        <path
          d='M 10 50 A 40 40 0 0 1 90 50'
          fill='none'
          stroke='#e5e7eb'
          strokeWidth='7'
          strokeLinecap='round'
        />
        <path
          d='M 10 50 A 40 40 0 0 1 90 50'
          fill='none'
          stroke={value >= target ? '#22c55e' : value >= target * 0.6 ? '#f59e0b' : '#ef4444'}
          strokeWidth='7'
          strokeLinecap='round'
          strokeDasharray={`${(angle / 180) * 126} 126`}
        />
        <line
          x1={50 + 40 * Math.cos(Math.PI - (targetAngle * Math.PI) / 180)}
          y1={50 - 40 * Math.sin(Math.PI - (targetAngle * Math.PI) / 180)}
          x2={50 + 33 * Math.cos(Math.PI - (targetAngle * Math.PI) / 180)}
          y2={50 - 33 * Math.sin(Math.PI - (targetAngle * Math.PI) / 180)}
          stroke='#6b7280'
          strokeWidth='2'
        />
      </svg>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   KPI CARDS
   ══════════════════════════════════════════════════════════════════════════════ */

function KPICards({ counties }: { counties: County[] }) {
  const stats = useMemo(() => {
    const totalBudget = counties.reduce((s, c) => s + (c.totalBudget ?? c.budget ?? 0), 0);
    const totalDebt = counties.reduce((s, c) => s + (c.totalDebt ?? c.debt ?? 0), 0);
    const avgExec =
      counties.reduce((s, c) => s + (c.budgetUtilization ?? 0), 0) / (counties.length || 1);
    const auditCounts = { clean: 0, qualified: 0, adverse: 0 };
    counties.forEach((c) => {
      const st = c.auditStatus ?? 'pending';
      if (st in auditCounts) auditCounts[st as keyof typeof auditCounts]++;
    });
    const byDebt = [...counties]
      .sort((a, b) => (b.totalDebt ?? b.debt ?? 0) - (a.totalDebt ?? a.debt ?? 0))
      .slice(0, 3);
    return { totalBudget, totalDebt, avgExec, auditCounts, byDebt };
  }, [counties]);

  const donutData = [
    { name: 'Clean', value: stats.auditCounts.clean, color: '#22c55e' },
    { name: 'Qualified', value: stats.auditCounts.qualified, color: '#f59e0b' },
    { name: 'Adverse', value: stats.auditCounts.adverse, color: '#ef4444' },
  ];

  return (
    <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4'>
      {/* Card 1: Total Budget */}
      <Link
        href='/budget'
        className='bg-white/40 backdrop-blur-xl rounded-2xl p-5 shadow-[0_8px_40px_rgba(0,0,0,0.08)] border border-white/50 flex items-center justify-between hover:shadow-lg hover:scale-[1.02] transition-all'>
        <div>
          <div className='text-xs font-medium text-gray-500 mb-1'>Total Budget</div>
          <div className='text-2xl font-bold text-gray-900 tracking-tight'>
            KES {fmtKES(stats.totalBudget)}
          </div>
          <div className='text-[11px] text-emerald-600 font-medium mt-0.5'>+12% vs last year</div>
        </div>
        <Sparkline seed={42} positive />
      </Link>

      {/* Card 2: Total Debt */}
      <Link
        href='/budget?tab=debt'
        className='bg-white/40 backdrop-blur-xl rounded-2xl p-5 shadow-[0_8px_40px_rgba(0,0,0,0.08)] border border-white/50 flex items-center justify-between hover:shadow-lg hover:scale-[1.02] transition-all'>
        <div>
          <div className='text-xs font-medium text-gray-500 mb-1'>Total Debt</div>
          <div className='text-2xl font-bold text-gray-900 tracking-tight'>
            KES {fmtKES(stats.totalDebt)}
          </div>
          <div className='text-[11px] text-red-600 font-medium mt-0.5'>
            <span className='text-red-500'>▲</span> 8% vs last year
          </div>
        </div>
        <Sparkline seed={99} positive={false} />
      </Link>

      {/* Card 3: Avg. Execution Rate */}
      <div
        className='bg-white/40 backdrop-blur-xl rounded-2xl p-5 shadow-[0_8px_40px_rgba(0,0,0,0.08)] border border-white/50 flex items-center justify-between hover:shadow-lg hover:scale-[1.02] transition-all cursor-pointer'
        title='See county rankings below'>
        <div>
          <div className='text-xs font-medium text-gray-500 mb-1'>Avg. Execution Rate</div>
          <div className='text-2xl font-bold text-gray-900 tracking-tight'>
            {stats.avgExec.toFixed(0)}%
          </div>
          <div className='text-[11px] text-gray-500 mt-0.5'>Target: 70%</div>
        </div>
        <GaugeMini value={stats.avgExec} target={70} />
      </div>

      {/* Card 4: Audit Summary */}
      <div className='bg-white/40 backdrop-blur-xl rounded-2xl p-5 shadow-[0_8px_40px_rgba(0,0,0,0.08)] border border-white/50'>
        <div className='text-xs font-medium text-gray-500 mb-2'>Audit Summary</div>
        <div className='flex items-center gap-3'>
          <div className='w-14 h-14 flex-shrink-0'>
            <ResponsiveContainer width='100%' height='100%'>
              <PieChart>
                <Pie
                  data={donutData}
                  dataKey='value'
                  cx='50%'
                  cy='50%'
                  innerRadius={16}
                  outerRadius={26}
                  strokeWidth={0}>
                  {donutData.map((d, i) => (
                    <Cell key={i} fill={d.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className='space-y-1'>
            {donutData.map((d) => (
              <div key={d.name} className='flex items-center gap-1.5 text-xs'>
                <div className='w-2 h-2 rounded-full' style={{ background: d.color }} />
                <span className='text-gray-600'>{d.name}</span>
                <span className='font-semibold text-gray-800'>{d.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Card 5: High Debt Counties */}
      <div className='bg-white/40 backdrop-blur-xl rounded-2xl p-4 shadow-[0_8px_40px_rgba(0,0,0,0.08)] border border-white/50'>
        <div className='text-xs font-medium text-gray-500 mb-2'>High Debt Counties</div>
        <div className='space-y-2'>
          {stats.byDebt.map((c, i) => {
            const debt = c.totalDebt ?? c.debt ?? 0;
            const budget = c.totalBudget ?? c.budget ?? 0;
            const auditCfg = AUDIT_STATUS_CFG[c.auditStatus ?? 'pending'];
            return (
              <Link
                key={c.id}
                href={`/counties/${c.id}?tab=budget`}
                className='flex items-center gap-2 hover:bg-white/40 -mx-1 px-1 py-0.5 rounded-lg transition-colors'>
                <span className='text-[10px] font-bold text-gray-400 w-3'>{i + 1}</span>
                <div className='flex-1 min-w-0'>
                  <div className='flex items-center justify-between'>
                    <span className='text-xs font-semibold text-gray-800 truncate'>{c.name}</span>
                    <span
                      className={`text-[9px] font-semibold px-1.5 py-0.5 rounded-full ${auditCfg.chipBg} ${auditCfg.chipText}`}>
                      {auditCfg.label}
                    </span>
                  </div>
                  <div className='flex items-center gap-2 mt-0.5'>
                    <span className='text-[10px] text-gray-600 tabular-nums'>{fmtKES(debt)}</span>
                    <span className='text-[10px] text-gray-400 tabular-nums'>{fmtKES(budget)}</span>
                  </div>
                  <div className='h-1 bg-gray-100 rounded-full mt-1 overflow-hidden'>
                    <div
                      className='h-full bg-red-400 rounded-full'
                      style={{
                        width: `${Math.min((debt / (stats.byDebt[0]?.totalDebt ?? stats.byDebt[0]?.debt ?? 1)) * 100, 100)}%`,
                      }}
                    />
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   FILTERS SIDEBAR
   ══════════════════════════════════════════════════════════════════════════════ */

interface FilterState {
  search: string;
  region: string;
  grades: string[];
  auditStatuses: string[];
  spendingRange: [number, number];
  sortBy: string;
}

const defaultFilters: FilterState = {
  search: '',
  region: 'all',
  grades: [],
  auditStatuses: [],
  spendingRange: [0, 150],
  sortBy: 'budget-desc',
};

function FiltersSidebar({
  filters,
  setFilters,
  collapsed,
  setCollapsed,
  onApply,
  onReset,
}: {
  filters: FilterState;
  setFilters: React.Dispatch<React.SetStateAction<FilterState>>;
  collapsed: boolean;
  setCollapsed: (v: boolean) => void;
  onApply: () => void;
  onReset: () => void;
}) {
  const toggleGrade = (g: string) => {
    setFilters((f) => ({
      ...f,
      grades: f.grades.includes(g) ? f.grades.filter((x) => x !== g) : [...f.grades, g],
    }));
  };

  const toggleAudit = (status: string) => {
    setFilters((f) => ({
      ...f,
      auditStatuses: f.auditStatuses.includes(status)
        ? f.auditStatuses.filter((x) => x !== status)
        : [...f.auditStatuses, status],
    }));
  };

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className='bg-white/40 backdrop-blur-xl rounded-2xl shadow-[0_8px_40px_rgba(0,0,0,0.08)] border border-white/50 p-3 flex items-center justify-center hover:bg-white/50 transition-colors'>
        <Filter size={18} className='text-gray-500' />
      </button>
    );
  }

  return (
    <div className='bg-white/40 backdrop-blur-xl rounded-2xl shadow-[0_8px_40px_rgba(0,0,0,0.08)] border border-white/50 overflow-hidden'>
      {/* Header */}
      <div className='flex items-center justify-between px-5 py-4 border-b border-gray-100'>
        <h3 className='text-sm font-bold text-gray-900'>Filters</h3>
        <button
          onClick={() => setCollapsed(true)}
          className='text-gray-400 hover:text-gray-600 transition-colors'>
          <ChevronsLeft size={16} />
        </button>
      </div>

      <div className='p-5 space-y-5'>
        {/* Search County */}
        <div>
          <label className='text-[11px] font-semibold text-gray-600 uppercase tracking-wider mb-1.5 block'>
            Search County
          </label>
          <div className='relative'>
            <Search size={14} className='absolute left-3 top-1/2 -translate-y-1/2 text-gray-400' />
            <input
              type='text'
              value={filters.search}
              onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
              placeholder='Type to search...'
              className='w-full pl-9 pr-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-gov-forest/20 focus:border-gov-forest/40 placeholder-gray-400'
            />
          </div>
        </div>

        {/* Region */}
        <div>
          <label className='text-[11px] font-semibold text-gray-600 uppercase tracking-wider mb-1.5 block'>
            Region
          </label>
          <div className='relative'>
            <select
              value={filters.region}
              onChange={(e) => setFilters((f) => ({ ...f, region: e.target.value }))}
              className='w-full appearance-none bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 pr-8 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-gov-forest/20'>
              <option value='all'>All Regions</option>
              <option value='central'>Central</option>
              <option value='coast'>Coast</option>
              <option value='eastern'>Eastern</option>
              <option value='nairobi'>Nairobi</option>
              <option value='north-eastern'>North Eastern</option>
              <option value='nyanza'>Nyanza</option>
              <option value='rift-valley'>Rift Valley</option>
              <option value='western'>Western</option>
            </select>
            <ChevronDown
              size={14}
              className='absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none'
            />
          </div>
        </div>

        {/* Grade */}
        <div>
          <label className='text-[11px] font-semibold text-gray-600 uppercase tracking-wider mb-1.5 block'>
            Grade
          </label>
          <div className='flex items-center gap-1.5 flex-wrap'>
            {GRADE_ALL.map((g) => {
              const active = filters.grades.includes(g);
              return (
                <button
                  key={g}
                  onClick={() => toggleGrade(g)}
                  className={`w-8 h-8 rounded-lg text-xs font-bold transition-all ${
                    active
                      ? GRADE_COLORS[g] + ' shadow-sm ring-2 ring-offset-1 ring-gray-300'
                      : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                  }`}>
                  {g}
                </button>
              );
            })}
            <button className='text-gray-400 hover:text-gray-600 ml-1'>
              <ChevronDown size={14} />
            </button>
          </div>
        </div>

        {/* Audit Status */}
        <div>
          <label className='text-[11px] font-semibold text-gray-600 uppercase tracking-wider mb-1.5 block'>
            Audit Status
          </label>
          <div className='space-y-2'>
            {(['clean', 'qualified', 'adverse'] as const).map((status) => {
              const cfg = AUDIT_STATUS_CFG[status];
              const checked = filters.auditStatuses.includes(status);
              return (
                <label key={status} className='flex items-center gap-2.5 cursor-pointer group'>
                  <div
                    className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                      checked
                        ? 'bg-gov-forest border-gov-forest'
                        : 'border-gray-300 group-hover:border-gray-400'
                    }`}>
                    {checked && (
                      <svg viewBox='0 0 12 12' className='w-3 h-3 text-white'>
                        <path
                          d='M2 6L5 9L10 3'
                          stroke='currentColor'
                          strokeWidth='2'
                          fill='none'
                          strokeLinecap='round'
                          strokeLinejoin='round'
                        />
                      </svg>
                    )}
                  </div>
                  <div className={`w-2.5 h-2.5 rounded-full ${cfg.dot}`} />
                  <span className='text-sm text-gray-700'>{cfg.label}</span>
                </label>
              );
            })}
          </div>
        </div>

        {/* Spending Range */}
        <div>
          <label className='text-[11px] font-semibold text-gray-600 uppercase tracking-wider mb-2 block'>
            Spending Range
          </label>
          <input
            type='range'
            min={0}
            max={150}
            value={filters.spendingRange[1]}
            onChange={(e) =>
              setFilters((f) => ({ ...f, spendingRange: [0, Number(e.target.value)] }))
            }
            className='w-full h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-gov-forest'
          />
          <div className='flex justify-between text-[10px] text-gray-400 mt-1 tabular-nums'>
            <span>KES 0B</span>
            <span>—</span>
            <span>{filters.spendingRange[1]}B+</span>
          </div>
        </div>

        {/* Sort by */}
        <div>
          <label className='text-[11px] font-semibold text-gray-600 uppercase tracking-wider mb-1.5 block'>
            Sort by
          </label>
          <div className='relative'>
            <select
              value={filters.sortBy}
              onChange={(e) => setFilters((f) => ({ ...f, sortBy: e.target.value }))}
              className='w-full appearance-none bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 pr-8 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-gov-forest/20'>
              <option value='budget-desc'>Budget (High → Low)</option>
              <option value='budget-asc'>Budget (Low → High)</option>
              <option value='debt-desc'>Debt (High → Low)</option>
              <option value='population-desc'>Population (High → Low)</option>
              <option value='health-desc'>Grade (Best → Worst)</option>
              <option value='utilization-desc'>Execution (High → Low)</option>
            </select>
            <ChevronDown
              size={14}
              className='absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none'
            />
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className='px-5 pb-5 pt-2 flex gap-2'>
        <button
          onClick={onApply}
          className='flex-1 bg-gov-forest text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-gov-forest/90 transition-colors'>
          Apply Filters
        </button>
        <button
          onClick={onReset}
          className='px-4 bg-gray-100 text-gray-700 text-sm font-medium py-2.5 rounded-lg hover:bg-gray-200 transition-colors'>
          Reset
        </button>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   KENYA CHOROPLETH MAP — Real county boundaries colored by grade
   ══════════════════════════════════════════════════════════════════════════════ */

import { KENYA_COUNTY_PATHS } from '@/data/kenya-county-paths';

// Normalize names for matching between GADM data and API data
function normalizeName(name: string): string {
  return name
    .replace(/ County$/i, '')
    .replace(/['\s-]/g, '')
    .toLowerCase();
}

// Grade → fill color for choropleth
const GRADE_FILLS: Record<string, string> = {
  A: '#22c55e', // green
  B: '#86efac', // light green
  C: '#ea580c', // deep orange
  D: '#ef4444', // red
  'D-': '#991b1b', // dark red
};

function CountyPerformanceMap({
  counties,
  allCounties,
  activeGrades,
  onToggleGrade,
  selectedRegion,
}: {
  counties: County[]; // filtered counties (for highlight)
  allCounties: County[]; // all counties (always render all polygons)
  activeGrades: string[];
  onToggleGrade: (grade: string) => void;
  selectedRegion: string;
}) {
  const router = useRouter();
  const [hoveredCounty, setHoveredCounty] = useState<County | null>(null);
  const [hoveredGadm, setHoveredGadm] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  // Build lookup for ALL counties (so all polygons get colored)
  const allLookup = useMemo(() => {
    const map = new Map<string, County>();
    allCounties.forEach((c) => {
      map.set(normalizeName(c.name), c);
    });
    return map;
  }, [allCounties]);

  // Build set of filtered county names (for highlight control)
  const filteredNames = useMemo(() => {
    const set = new Set<string>();
    counties.forEach((c) => set.add(normalizeName(c.name)));
    return set;
  }, [counties]);

  // Compute region bounding box for zoom
  const regionViewBox = useMemo(() => {
    if (selectedRegion === 'all') return '0 0 360 400';
    // find county paths that belong to this region
    const regionPaths = KENYA_COUNTY_PATHS.filter((cp) => {
      const county = allLookup.get(normalizeName(cp.name));
      return county ? getCountyRegion(county.name) === selectedRegion : false;
    });
    if (regionPaths.length === 0) return '0 0 360 400';
    let minX = Infinity,
      minY = Infinity,
      maxX = -Infinity,
      maxY = -Infinity;
    regionPaths.forEach((cp) => {
      // Extract coordinates from path data
      const nums = cp.path.match(/[\d.]+/g);
      if (!nums) return;
      for (let i = 0; i < nums.length - 1; i += 2) {
        const x = parseFloat(nums[i]);
        const y = parseFloat(nums[i + 1]);
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    });
    // Add padding
    const pad = 20;
    minX = Math.max(0, minX - pad);
    minY = Math.max(0, minY - pad);
    maxX = Math.min(360, maxX + pad);
    maxY = Math.min(400, maxY + pad);
    return `${minX} ${minY} ${maxX - minX} ${maxY - minY}`;
  }, [selectedRegion, allLookup]);

  return (
    <div className='bg-white/40 backdrop-blur-xl rounded-2xl shadow-[0_8px_40px_rgba(0,0,0,0.08)] border border-white/50 p-5 h-full'>
      <h3 className='text-sm font-bold text-gray-900 mb-3'>County Performance Map</h3>
      <div
        ref={containerRef}
        className='relative bg-gov-forest/5 rounded-xl overflow-hidden flex items-center justify-center'
        style={{ height: 280 }}>
        <svg viewBox={regionViewBox} className='w-auto h-full p-1 transition-all duration-500'>
          <defs>
            <filter id='mapShadow'>
              <feDropShadow dx='0' dy='1' stdDeviation='2' floodOpacity='0.12' />
            </filter>
          </defs>
          {/* Lake Victoria */}
          <ellipse cx='24' cy='225' rx='22' ry='35' fill='#bbdefb' opacity='0.35' />
          {/* County polygons */}
          {KENYA_COUNTY_PATHS.map((cp) => {
            const county = allLookup.get(normalizeName(cp.name));
            const grade = county ? gradeCategory(county.financial_health_score) : null;
            const fill = grade ? (GRADE_FILLS[grade] ?? '#d1d5db') : '#e5e7eb';
            const inFilter = filteredNames.has(normalizeName(cp.name));
            const dimmedByGrade = activeGrades.length > 0 && grade && !activeGrades.includes(grade);
            const dimmed = !inFilter || dimmedByGrade;

            return (
              <g key={cp.name}>
                <path
                  d={cp.path}
                  fill={fill}
                  stroke='#fff'
                  strokeWidth='0.8'
                  opacity={dimmed ? 0.2 : 0.85}
                  className='cursor-pointer transition-opacity duration-200'
                  onClick={() => {
                    if (county) router.push(`/counties/${county.id}`);
                  }}
                  onMouseEnter={(e) => {
                    if (county) {
                      setHoveredCounty(county);
                      setHoveredGadm(cp.name);
                      const rect = containerRef.current?.getBoundingClientRect();
                      if (rect) {
                        setTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
                      }
                    }
                  }}
                  onMouseMove={(e) => {
                    const rect = containerRef.current?.getBoundingClientRect();
                    if (rect) {
                      setTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
                    }
                  }}
                  onMouseLeave={() => {
                    setHoveredCounty(null);
                    setHoveredGadm(null);
                  }}
                />
                {/* Highlight border on hover */}
                {hoveredGadm === cp.name && (
                  <path
                    d={cp.path}
                    fill='none'
                    stroke='#0F1A12'
                    strokeWidth='1.8'
                    pointerEvents='none'
                  />
                )}
              </g>
            );
          })}
        </svg>
        {/* Tooltip */}
        {hoveredCounty && (
          <div
            className='absolute z-50 bg-gov-dark text-white text-xs rounded-lg px-3 py-2 shadow-lg pointer-events-none'
            style={{
              left: tooltipPos.x + 14,
              top: tooltipPos.y - 8,
              transform: 'translateY(-100%)',
            }}>
            <div className='font-semibold'>{hoveredCounty.name}</div>
            <div className='text-white/70 mt-0.5'>
              Grade: {getGrade(hoveredCounty.financial_health_score).letter} · Exec:{' '}
              {(hoveredCounty.budgetUtilization ?? 0).toFixed(0)}%
            </div>
            <div className='text-white/60'>
              Budget: KES {fmtKES(hoveredCounty.totalBudget ?? hoveredCounty.budget ?? 0)}
            </div>
          </div>
        )}
      </div>
      {/* Grade legend — clickable to filter */}
      <div className='flex items-center gap-2 mt-3'>
        <span className='text-[11px] text-gray-500 font-medium'>Performance:</span>
        {GRADE_ALL.map((g) => {
          const isActive = activeGrades.length === 0 || activeGrades.includes(g);
          return (
            <button
              key={g}
              onClick={() => onToggleGrade(g)}
              className={`w-7 h-6 rounded text-[10px] font-bold flex items-center justify-center border-2 transition-all ${
                isActive
                  ? `${GRADE_COLORS[g]} border-transparent shadow-sm`
                  : 'bg-gray-100 text-gray-400 border-gray-200 opacity-50'
              }`}>
              {g}
            </button>
          );
        })}
        {activeGrades.length > 0 && (
          <button
            onClick={() => activeGrades.forEach((g) => onToggleGrade(g))}
            className='text-[10px] text-gray-400 hover:text-gray-600 ml-1 underline'>
            clear
          </button>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   COUNTY INSIGHTS PANEL — replaces separate Top Performers / High Debt
   Shows best & worst performers (no overlap) + region summary stats
   ══════════════════════════════════════════════════════════════════════════════ */

function CountyInsightsPanel({ counties }: { counties: County[] }) {
  const { best, worst, stats } = useMemo(() => {
    const sorted = [...counties].sort(
      (a, b) => b.financial_health_score - a.financial_health_score
    );
    const count = sorted.length;
    // Take top 3 and bottom 3 — guaranteed no overlap when count > 5
    const takeTop = Math.min(3, Math.ceil(count / 2));
    const takeBottom = Math.min(3, count - takeTop);
    const bestList = sorted.slice(0, takeTop);
    const worstList = sorted.slice(count - takeBottom).reverse(); // worst first

    const totalBudget = counties.reduce((s, c) => s + (c.totalBudget ?? c.budget ?? 0), 0);
    const totalDebt = counties.reduce((s, c) => s + (c.totalDebt ?? c.debt ?? 0), 0);
    const avgUtil = counties.reduce((s, c) => s + (c.budgetUtilization ?? 0), 0) / (count || 1);
    const avgHealth = counties.reduce((s, c) => s + c.financial_health_score, 0) / (count || 1);

    return {
      best: bestList,
      worst: worstList,
      stats: { totalBudget, totalDebt, avgUtil, avgHealth, count },
    };
  }, [counties]);

  if (counties.length === 0) {
    return (
      <div className='bg-white/40 backdrop-blur-xl rounded-2xl shadow-[0_8px_40px_rgba(0,0,0,0.08)] border border-white/50 p-5 md:col-span-2 flex items-center justify-center text-sm text-gray-400'>
        No counties match the current filters
      </div>
    );
  }

  return (
    <div className='bg-white/40 backdrop-blur-xl rounded-2xl shadow-[0_8px_40px_rgba(0,0,0,0.08)] border border-white/50 p-5 md:col-span-2'>
      {/* Region summary bar */}
      <div className='flex items-center gap-4 mb-4 pb-3 border-b border-gray-200/60 flex-wrap'>
        <span className='text-sm font-bold text-gray-900'>
          {stats.count} {stats.count === 1 ? 'County' : 'Counties'}
        </span>
        <div className='flex items-center gap-1.5 text-xs text-gray-500'>
          <span className='font-semibold text-gray-700'>Budget:</span>
          <span className='tabular-nums'>{fmtKES(stats.totalBudget)}</span>
        </div>
        <div className='flex items-center gap-1.5 text-xs text-gray-500'>
          <span className='font-semibold text-gray-700'>Debt:</span>
          <span className='tabular-nums text-red-600'>{fmtKES(stats.totalDebt)}</span>
        </div>
        <div className='flex items-center gap-1.5 text-xs text-gray-500'>
          <span className='font-semibold text-gray-700'>Avg Exec:</span>
          <span className='tabular-nums'>{stats.avgUtil.toFixed(0)}%</span>
        </div>
        <div className='flex items-center gap-1.5 text-xs'>
          <span className='font-semibold text-gray-700'>Avg Health:</span>
          <span
            className={`px-1.5 py-0.5 rounded font-bold text-[10px] ${GRADE_COLORS[gradeCategory(stats.avgHealth)]}`}>
            {gradeCategory(stats.avgHealth)} ({stats.avgHealth.toFixed(0)})
          </span>
        </div>
      </div>

      <div className='grid grid-cols-1 md:grid-cols-2 gap-4'>
        {/* Best performers */}
        <div>
          <h4 className='flex items-center gap-1.5 text-xs font-bold text-emerald-700 uppercase tracking-wider mb-2'>
            <TrendingUp size={13} /> Best Performers
          </h4>
          <div className='space-y-2'>
            {best.map((c, i) => (
              <InsightRow key={c.id} county={c} rank={i + 1} variant='best' />
            ))}
          </div>
        </div>

        {/* Needs attention */}
        <div>
          <h4 className='flex items-center gap-1.5 text-xs font-bold text-red-700 uppercase tracking-wider mb-2'>
            <AlertTriangle size={13} /> Needs Attention
          </h4>
          <div className='space-y-2'>
            {worst.map((c, i) => (
              <InsightRow key={c.id} county={c} rank={i + 1} variant='worst' />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function InsightRow({
  county: c,
  rank,
  variant,
}: {
  county: County;
  rank: number;
  variant: 'best' | 'worst';
}) {
  const util = c.budgetUtilization ?? 0;
  const debt = c.totalDebt ?? c.debt ?? 0;
  const budget = c.totalBudget ?? c.budget ?? 0;
  const health = c.financial_health_score;
  const grade = getGrade(health);
  const debtRatio = budget > 0 ? ((debt / budget) * 100).toFixed(0) : '0';
  const auditCfg = AUDIT_STATUS_CFG[c.auditStatus ?? 'pending'];

  return (
    <Link
      href={`/counties/${c.id}`}
      className='flex items-center gap-2.5 hover:bg-white/50 -mx-2 px-2 py-1.5 rounded-lg transition-colors'>
      <span className='text-xs font-bold text-gray-400 w-3 text-right'>{rank}</span>
      <div className='flex-1 min-w-0'>
        <div className='flex items-center gap-2 mb-0.5'>
          <span className='text-sm font-semibold text-gray-800 truncate'>{c.name}</span>
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${grade.cls}`}>
            {grade.letter}
          </span>
          <span
            className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ml-auto flex items-center gap-1 ${auditCfg.chipBg} ${auditCfg.chipText}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${auditCfg.dot}`} />
            {auditCfg.label}
          </span>
        </div>
        <div className='flex items-center gap-3'>
          {/* Utilization bar */}
          <div className='flex items-center gap-1.5 flex-1'>
            <span className='text-[10px] text-gray-500 w-7'>Exec</span>
            <div className='flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden'>
              <div
                className={`h-full rounded-full ${util >= 70 ? 'bg-emerald-500' : util >= 50 ? 'bg-amber-500' : 'bg-red-400'}`}
                style={{ width: `${Math.min(util, 100)}%` }}
              />
            </div>
            <span className='text-[10px] font-semibold text-gray-700 w-7 tabular-nums'>
              {util.toFixed(0)}%
            </span>
          </div>
          {/* Debt ratio */}
          <div className='flex items-center gap-1.5'>
            <span className='text-[10px] text-gray-500'>Debt</span>
            <span
              className={`text-[10px] font-bold tabular-nums ${
                Number(debtRatio) > 50 ? 'text-red-600' : 'text-gray-600'
              }`}>
              {debtRatio}%
            </span>
            <span className='text-[10px] text-gray-400 tabular-nums'>{fmtKES(budget)}</span>
          </div>
        </div>
      </div>
    </Link>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   EXECUTION BAR
   ══════════════════════════════════════════════════════════════════════════════ */

function ExecBar({ pct }: { pct: number }) {
  const clamped = Math.min(pct, 100);
  const clr = pct >= 70 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className='flex items-center gap-2'>
      <div className='w-20 h-2 bg-gray-100 rounded-full overflow-hidden'>
        <div className={`h-full rounded-full ${clr}`} style={{ width: `${clamped}%` }} />
      </div>
      <span className='text-xs tabular-nums text-gray-700 w-8'>{pct.toFixed(0)}%</span>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   SORTABLE TABLE HEADER
   ══════════════════════════════════════════════════════════════════════════════ */

function Th({
  children,
  field,
  current,
  dir,
  onSort,
  className = '',
  suffix,
}: {
  children: React.ReactNode;
  field: SortField;
  current: SortField;
  dir: SortDir;
  onSort: (f: SortField) => void;
  className?: string;
  suffix?: string;
}) {
  const active = current === field;
  return (
    <th
      className={`text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500 py-3 px-3 cursor-pointer select-none hover:text-gray-800 transition-colors whitespace-nowrap ${className}`}
      onClick={() => onSort(field)}>
      <span className='inline-flex items-center gap-1'>
        {children}
        {suffix && (
          <span className='text-[9px] text-gray-400 font-normal normal-case tracking-normal'>
            {suffix}
          </span>
        )}
        <ArrowUpDown size={11} className={active ? 'text-gov-forest' : 'text-gray-300'} />
        {active && (
          <span className='text-[9px] text-gov-forest font-normal'>
            {dir === 'asc' ? '↑' : '↓'}
          </span>
        )}
      </span>
    </th>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   COUNTY RANKINGS TABLE
   ══════════════════════════════════════════════════════════════════════════════ */

const PAGE_SIZE = 10;

function CountyRankingsTable({
  counties,
  sortField,
  sortDir,
  onSort,
  showAll,
  setShowAll,
  acctGrades,
}: {
  counties: County[];
  sortField: SortField;
  sortDir: SortDir;
  onSort: (f: SortField) => void;
  showAll: boolean;
  setShowAll: React.Dispatch<React.SetStateAction<boolean>>;
  acctGrades?: Record<string, string>;
}) {
  const [page, setPage] = useState(1);
  const totalPages = Math.ceil(counties.length / PAGE_SIZE);
  const paged = showAll ? counties : counties.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  React.useEffect(() => {
    setPage(1);
  }, [counties.length]);

  const pageNums = useMemo(() => {
    const nums: number[] = [];
    const start = Math.max(1, page - 2);
    const end = Math.min(totalPages, start + 4);
    for (let i = start; i <= end; i++) nums.push(i);
    return nums;
  }, [page, totalPages]);

  return (
    <div className='bg-white/40 backdrop-blur-xl rounded-2xl shadow-[0_8px_40px_rgba(0,0,0,0.08)] border border-white/50 overflow-hidden'>
      <div className='flex items-center justify-between px-5 py-4 border-b border-gray-100'>
        <div className='flex items-center gap-2'>
          <h3 className='text-sm font-bold text-gray-900'>County Rankings</h3>
          <span className='text-xs text-gray-400'>
            ({(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, counties.length)} of{' '}
            {counties.length})
          </span>
        </div>
      </div>

      <div className='overflow-x-auto'>
        <table className='w-full border-collapse min-w-[820px]'>
          <thead>
            <tr className='border-b border-gray-100 bg-gray-50/60'>
              <th className='text-left text-[11px] font-semibold uppercase tracking-wider text-gray-400 py-3 px-4 w-8'>
                #
              </th>
              <Th field='name' current={sortField} dir={sortDir} onSort={onSort}>
                County
              </Th>
              <Th field='population' current={sortField} dir={sortDir} onSort={onSort}>
                Population
              </Th>
              <Th field='health' current={sortField} dir={sortDir} onSort={onSort}>
                Grade
              </Th>
              <Th field='budget' current={sortField} dir={sortDir} onSort={onSort} suffix='(KES)'>
                Budget
              </Th>
              <Th field='utilization' current={sortField} dir={sortDir} onSort={onSort}>
                Execution
              </Th>
              <Th field='debt' current={sortField} dir={sortDir} onSort={onSort}>
                Debt
              </Th>
              <th className='text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500 py-3 px-3'>
                Audit
              </th>
              <th className='text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500 py-3 px-3'>
                Trends
              </th>
            </tr>
          </thead>
          <tbody>
            {paged.map((county, i) => {
              const budget = county.totalBudget ?? county.budget ?? 0;
              const debt = county.totalDebt ?? county.debt ?? 0;
              const util = county.budgetUtilization ?? 0;
              const grade = getGrade(county.financial_health_score);
              const issues = county.auditIssues?.length ?? 0;
              const auditCfg = AUDIT_STATUS_CFG[county.auditStatus ?? 'pending'];
              const base = `/counties/${county.id}`;
              const rank = showAll ? i + 1 : (page - 1) * PAGE_SIZE + i + 1;
              const improving = util >= 50;

              return (
                <tr
                  key={county.id}
                  className='group border-b border-gray-50 last:border-0 hover:bg-gov-forest/[0.025] transition-colors cursor-pointer'>
                  <td className='py-3 px-4 text-xs text-gray-400 tabular-nums'>{rank}</td>
                  <td className='py-3 px-3'>
                    <Link href={base} className='flex items-center gap-2'>
                      <div className='w-6 h-6 rounded-md bg-gov-forest/10 flex items-center justify-center flex-shrink-0'>
                        <span className='text-[10px]'>🏛️</span>
                      </div>
                      <span className='font-semibold text-sm text-gray-900 group-hover:text-gov-forest transition-colors'>
                        {county.name}
                      </span>
                      <AccountabilityBadge grade={acctGrades?.[county.id]} />
                    </Link>
                  </td>
                  <td className='py-3 px-3 text-sm text-gray-600 tabular-nums'>
                    <Link href={base} className='block'>
                      {fmtPop(county.population)}
                    </Link>
                  </td>
                  <td className='py-3 px-3'>
                    <Link href={`${base}?tab=budget`} className='block'>
                      <span
                        className={`inline-flex items-center justify-center w-8 h-6 text-[11px] font-bold rounded-md ${grade.cls}`}>
                        {grade.letter}
                      </span>
                    </Link>
                  </td>
                  <td className='py-3 px-3'>
                    <Link
                      href={`${base}?tab=budget`}
                      className='block text-sm text-gray-700 tabular-nums font-medium hover:text-gov-forest transition-colors'>
                      {fmtKES(budget)}
                    </Link>
                  </td>
                  <td className='py-3 px-3'>
                    <Link href={`${base}?tab=budget`} className='block'>
                      <ExecBar pct={util} />
                    </Link>
                  </td>
                  <td className='py-3 px-3'>
                    <Link
                      href={`${base}?tab=budget`}
                      className='flex items-center gap-1.5 text-sm text-gray-700 tabular-nums hover:text-gov-forest transition-colors'>
                      <span
                        className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${debt > 50e9 ? 'bg-red-500' : debt > 15e9 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                      />
                      {fmtKES(debt)}
                    </Link>
                  </td>
                  <td className='py-3 px-3'>
                    <Link href={`${base}?tab=audit`} className='flex items-center gap-1.5'>
                      <span
                        className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-full ${auditCfg.chipBg} ${auditCfg.chipText}`}>
                        {auditCfg.label === 'Adverse'
                          ? '🔺'
                          : auditCfg.label === 'Clean'
                            ? '✅'
                            : '⚠️'}{' '}
                        {auditCfg.label}
                      </span>
                      {issues > 0 && (
                        <span className='text-[10px] text-gray-500 font-medium'>({issues})</span>
                      )}
                    </Link>
                  </td>
                  <td className='py-3 px-3'>
                    <Sparkline seed={rank * 7 + (county.population % 100)} positive={improving} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {counties.length === 0 && (
        <div className='text-center py-12 px-4'>
          <Search size={28} className='mx-auto text-gray-300 mb-2' />
          <p className='text-sm text-gray-500'>No counties match your filters</p>
        </div>
      )}

      {counties.length > 0 && (
        <div className='flex items-center justify-between px-5 py-3 border-t border-gray-100 bg-gray-50/40'>
          <span className='text-xs text-gray-500'>
            {showAll
              ? `Showing all ${counties.length} Counties`
              : `Showing ${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, counties.length)} of ${counties.length} Counties`}
          </span>
          {!showAll && (
            <div className='flex items-center gap-1'>
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className='px-2.5 py-1.5 text-xs text-gray-500 hover:text-gray-800 disabled:opacity-30 disabled:cursor-not-allowed rounded-md hover:bg-gray-100'>
                &lt; Prev
              </button>
              {pageNums.map((n) => (
                <button
                  key={n}
                  onClick={() => setPage(n)}
                  className={`w-7 h-7 text-xs font-medium rounded-md transition-colors ${
                    n === page ? 'bg-gov-forest text-white' : 'text-gray-600 hover:bg-gray-100'
                  }`}>
                  {n}
                </button>
              ))}
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className='px-2.5 py-1.5 text-xs text-gray-500 hover:text-gray-800 disabled:opacity-30 disabled:cursor-not-allowed rounded-md hover:bg-gray-100'>
                Next &gt;
              </button>
            </div>
          )}
          <button
            onClick={() => setShowAll((v) => !v)}
            className='text-xs text-gov-forest font-medium hover:underline'>
            {showAll ? 'Show Paginated' : 'View All Counties'}
          </button>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   MAIN PAGE
   ══════════════════════════════════════════════════════════════════════════════ */

export default function CountyExplorerPage() {
  // Year dropdown state (must be declared before useCounties which depends on it)
  const YEARS = ['2025/26', '2024/25', '2023/24', '2022/23'];
  const [selectedYear, setSelectedYear] = useState('2024/25');
  const [yearOpen, setYearOpen] = useState(false);

  const { data: counties, isLoading, error, refetch } = useCounties({ fiscalYear: selectedYear });

  // Fetch accountability grades for all counties
  const countyIds = useMemo(() => (counties || []).map((c) => c.id), [counties]);
  const { data: acctGrades } = useAccountabilityGrades(countyIds);

  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const [sortField, setSortField] = useState<SortField>('budget');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // "View All" toggle
  const [showAll, setShowAll] = useState(false);

  // Grade filter driven by the map legend
  const [mapGrades, setMapGrades] = useState<string[]>([]);
  const handleToggleMapGrade = useCallback((g: string) => {
    setMapGrades((prev) => (prev.includes(g) ? prev.filter((x) => x !== g) : [...prev, g]));
  }, []);

  const handleSort = useCallback((field: SortField) => {
    setSortField((prev) => {
      if (prev === field) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
        return prev;
      }
      setSortDir(field === 'name' ? 'asc' : 'desc');
      return field;
    });
  }, []);

  // Apply sort when sortBy filter changes
  useEffect(() => {
    const [sf, sd] = filters.sortBy.split('-');
    const fieldMap: Record<string, SortField> = {
      budget: 'budget',
      debt: 'debt',
      population: 'population',
      health: 'health',
      utilization: 'utilization',
    };
    if (fieldMap[sf]) setSortField(fieldMap[sf]);
    if (sd === 'asc' || sd === 'desc') setSortDir(sd);
  }, [filters.sortBy]);

  const handleApply = useCallback(() => {
    // Filters now apply immediately — this is a no-op kept for the sidebar interface
  }, []);

  const handleReset = useCallback(() => {
    setFilters(defaultFilters);
    setSortField('budget');
    setSortDir('desc');
  }, []);

  const filtered = useMemo(() => {
    if (!counties) return [];
    let list = [...counties];

    if (filters.search.trim()) {
      const q = filters.search.toLowerCase();
      list = list.filter((c) => c.name.toLowerCase().includes(q));
    }

    // Region filter (applied immediately like search)
    if (filters.region !== 'all') {
      list = list.filter((c) => getCountyRegion(c.name) === filters.region);
    }

    if (filters.grades.length > 0) {
      list = list.filter((c) => filters.grades.includes(gradeCategory(c.financial_health_score)));
    }

    // Map-legend grade filter (applied independently of sidebar)
    if (mapGrades.length > 0) {
      list = list.filter((c) => mapGrades.includes(gradeCategory(c.financial_health_score)));
    }

    if (filters.auditStatuses.length > 0) {
      list = list.filter((c) => filters.auditStatuses.includes(c.auditStatus ?? 'pending'));
    }

    if (filters.spendingRange[1] < 150) {
      const maxB = filters.spendingRange[1] * 1e9;
      list = list.filter((c) => (c.totalBudget ?? c.budget ?? 0) <= maxB);
    }

    list.sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'name':
          cmp = a.name.localeCompare(b.name);
          break;
        case 'budget':
          cmp = (a.totalBudget ?? a.budget ?? 0) - (b.totalBudget ?? b.budget ?? 0);
          break;
        case 'health':
          cmp = a.financial_health_score - b.financial_health_score;
          break;
        case 'debt':
          cmp = (a.totalDebt ?? a.debt ?? 0) - (b.totalDebt ?? b.debt ?? 0);
          break;
        case 'population':
          cmp = a.population - b.population;
          break;
        case 'utilization':
          cmp = (a.budgetUtilization ?? 0) - (b.budgetUtilization ?? 0);
          break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return list;
  }, [counties, filters, mapGrades, sortField, sortDir]);

  // Export filtered data as CSV
  const handleExport = useCallback(() => {
    if (!filtered.length) return;
    const headers = [
      'Rank',
      'County',
      'Population',
      'Grade',
      'Budget (KES)',
      'Execution %',
      'Debt (KES)',
      'Audit Status',
    ];
    const rows = filtered.map((c, i) => [
      i + 1,
      c.name,
      c.population,
      getGrade(c.financial_health_score).letter,
      c.totalBudget ?? c.budget ?? 0,
      (c.budgetUtilization ?? 0).toFixed(1),
      c.totalDebt ?? c.debt ?? 0,
      c.auditStatus ?? 'pending',
    ]);
    const csv = [headers, ...rows].map((r) => r.map((v) => `"${v}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `county_data_${selectedYear.replace('/', '-')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [filtered, selectedYear]);

  if (isLoading) {
    return (
      <div className='relative min-h-screen' style={{ backgroundColor: 'rgb(245,240,232)' }}>
        <div className='relative z-[1]'>
          <div className='bg-gov-dark'>
            <div className='h-[72px]' />
            <div className='max-w-[1340px] mx-auto px-5 lg:px-8 pt-8 pb-10'>
              <div className='h-10 w-64 bg-white/10 rounded animate-pulse' />
              <div className='h-4 w-96 bg-white/5 rounded mt-3 animate-pulse' />
            </div>
          </div>
          <div className='max-w-[1340px] mx-auto px-5 lg:px-8 py-8'>
            <div className='flex items-center justify-center py-24'>
              <div className='animate-spin rounded-full h-14 w-14 border-b-2 border-gov-forest' />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !counties) {
    return (
      <div className='relative min-h-screen' style={{ backgroundColor: 'rgb(245,240,232)' }}>
        <div className='relative z-[1]'>
          <div className='bg-gov-dark'>
            <div className='h-[72px]' />
            <div className='max-w-[1340px] mx-auto px-5 lg:px-8 pt-8 pb-10'>
              <h1 className='font-display text-3xl sm:text-4xl lg:text-[2.75rem] text-white leading-[1.12] drop-shadow-lg'>
                County Explorer
              </h1>
            </div>
          </div>
          <div className='max-w-[1340px] mx-auto px-5 lg:px-8 py-8 text-center'>
            <AlertTriangle size={40} className='mx-auto text-red-400 mb-3' />
            <p className='text-red-600 mb-4'>Failed to load county data</p>
            <button
              onClick={() => refetch()}
              className='px-4 py-2 bg-gov-dark text-white rounded-lg text-sm'>
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  const NEUTRAL_RGB = '245,240,232';

  return (
    <div className='relative min-h-screen' style={{ backgroundColor: `rgb(${NEUTRAL_RGB})` }}>
      {/* ═══ Bottom scenic image (Kenyan flag) ═══ */}
      <div
        className='absolute bottom-0 left-0 right-0'
        aria-hidden='true'
        style={{ height: '45vh', zIndex: 0 }}>
        <img
          src='/kenya_bg_bottom.jpg'
          alt=''
          className='absolute inset-0 w-full h-full object-cover'
          style={{ objectPosition: 'center 75%' }}
          loading='lazy'
          decoding='async'
        />
        <div
          className='absolute inset-0'
          style={{
            background: `linear-gradient(180deg,
              rgba(15,26,18,0.60) 0%,
              rgba(15,26,18,0.18) 40%,
              rgba(15,26,18,0.32) 100%
            )`,
          }}
        />
        <div className='absolute top-0 left-0 right-0' style={{ height: '50%' }}>
          <div
            className='absolute inset-0'
            style={{
              background: `linear-gradient(to top,
                transparent 0%,
                rgba(${NEUTRAL_RGB},0.07) 15%,
                rgba(${NEUTRAL_RGB},0.21) 30%,
                rgba(${NEUTRAL_RGB},0.39) 45%,
                rgba(${NEUTRAL_RGB},0.61) 60%,
                rgba(${NEUTRAL_RGB},0.77) 75%,
                rgba(${NEUTRAL_RGB},0.88) 88%,
                rgba(${NEUTRAL_RGB},0.94) 100%
              )`,
            }}
          />
        </div>
      </div>

      {/* ═══ Content layer ═══ */}
      <div className='relative z-[1]'>
        {/* ══ Dark-green header band ══ */}
        <div className='bg-gov-dark'>
          <div className='h-[72px]' />
          <div className='max-w-[1340px] mx-auto px-5 lg:px-8 pt-8 pb-10'>
            <div className='flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4'>
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, ease: 'easeOut' }}
                className='max-w-3xl'>
                <h1 className='font-display text-3xl sm:text-4xl lg:text-[2.75rem] text-white leading-[1.12] mb-2 drop-shadow-lg'>
                  County Explorer
                </h1>
                <p className='text-base sm:text-lg text-white/70 font-light tracking-wide drop-shadow-md'>
                  Compare <strong className='text-white/90'>47 Counties</strong> · Budgets,
                  Spending, Debts &amp; Audit Outcomes
                </p>
              </motion.div>
              <div className='flex items-center gap-3'>
                <div className='relative'>
                  <button
                    onClick={() => setYearOpen((v) => !v)}
                    className='inline-flex items-center gap-2 bg-white/10 hover:bg-white/15 text-white text-sm font-medium px-4 py-2 rounded-lg border border-white/20 transition-colors'>
                    Year: {selectedYear}
                    <ChevronDown
                      size={14}
                      className={`transition-transform ${yearOpen ? 'rotate-180' : ''}`}
                    />
                  </button>
                  {yearOpen && (
                    <div className='absolute right-0 mt-1 bg-white rounded-lg shadow-xl border border-gray-200 py-1 z-50 min-w-[140px]'>
                      {YEARS.map((y) => (
                        <button
                          key={y}
                          onClick={() => {
                            setSelectedYear(y);
                            setYearOpen(false);
                          }}
                          className={`block w-full text-left px-4 py-2 text-sm transition-colors ${
                            y === selectedYear
                              ? 'bg-gov-forest/10 text-gov-forest font-semibold'
                              : 'text-gray-700 hover:bg-gray-50'
                          }`}>
                          {y}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  onClick={handleExport}
                  className='inline-flex items-center gap-2 bg-white/10 hover:bg-white/15 text-white text-sm font-medium px-4 py-2 rounded-lg border border-white/20 transition-colors'>
                  <Download size={14} />
                  Export
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* ═══ Main content ═══ */}
        <div className='max-w-[1340px] mx-auto px-5 lg:px-8 py-8'>
          {/* KPI Cards */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.1 }}>
            <KPICards counties={counties} />
          </motion.div>

          {/* Two-column layout */}
          <div className='mt-6 flex gap-6'>
            {/* Left: Filters */}
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.4, delay: 0.2 }}
              className={`flex-shrink-0 ${sidebarCollapsed ? 'w-12' : 'w-[280px]'} hidden lg:block transition-all`}>
              <div className='sticky top-[88px]'>
                <FiltersSidebar
                  filters={filters}
                  setFilters={setFilters}
                  collapsed={sidebarCollapsed}
                  setCollapsed={setSidebarCollapsed}
                  onApply={handleApply}
                  onReset={handleReset}
                />
              </div>
            </motion.div>

            {/* Right: Analytics */}
            <div className='flex-1 min-w-0 space-y-6'>
              {/* Middle row: Map + County Insights */}
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.3 }}
                className='grid grid-cols-1 md:grid-cols-3 gap-4'>
                <CountyPerformanceMap
                  counties={filtered}
                  allCounties={counties}
                  activeGrades={mapGrades}
                  onToggleGrade={handleToggleMapGrade}
                  selectedRegion={filters.region}
                />
                <CountyInsightsPanel counties={filtered} />
              </motion.div>

              {/* County Rankings Table */}
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.4 }}>
                <CountyRankingsTable
                  counties={filtered}
                  sortField={sortField}
                  sortDir={sortDir}
                  onSort={handleSort}
                  showAll={showAll}
                  setShowAll={setShowAll}
                  acctGrades={acctGrades}
                />
              </motion.div>
            </div>
          </div>
        </div>

        <DataFreshnessBadge sources="COB" className="mt-4 justify-center" />

        {/* Spacer so bottom scenic image peeks through */}
        <div className='h-24' />
      </div>
    </div>
  );
}
