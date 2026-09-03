'use client';

import DataFreshnessBadge from '@/components/DataFreshnessBadge';
import ModelledDataNote from '@/components/ModelledDataNote';
import InfoTip from '@/components/InfoTip';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { useCounties } from '@/lib/react-query';
import { generateFiscalYears, getLatestReportedFiscalYear } from '@/lib/utils';
import { County } from '@/types';
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
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts';

/* ══════════════════════════════════════════════════════════════════════════════
   HELPERS
   ══════════════════════════════════════════════════════════════════════════════ */

const COUNTIES_NEUTRAL_RGB = '243,238,228';

/** Scenic flag image pinned to the bottom of the page. Extracted into a
 * component so all three page states (loading, error, loaded) can render
 * it identically — otherwise the image is only in the loaded-state
 * markup, which makes it "appear" after data arrives and scores a
 * 0.5+ CLS hit the first time the user lands here. */
function CountiesScenicBottom() {
  return <div aria-hidden='true' className='absolute inset-x-0 bottom-0 h-1 bg-gov-copper' />;
}

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

// Financial-health letter grade. Scale MUST match the backend's
// `financial_summary.grade` bands in main.py so the listing and the
// county detail hero show the same letter for the same county.
//   A ≥ 85 · B+ ≥ 70 · B ≥ 55 · B- ≥ 40 · else C
function getGrade(score: number) {
  if (score >= 85) return { letter: 'A', cls: 'bg-emerald-500 text-white' };
  if (score >= 70) return { letter: 'B+', cls: 'bg-green-500 text-white' };
  if (score >= 55) return { letter: 'B', cls: 'bg-amber-500 text-white' };
  if (score >= 40) return { letter: 'B-', cls: 'bg-orange-500 text-white' };
  return { letter: 'C', cls: 'bg-red-500 text-white' };
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
  { label: string; labelKey: TranslationKey; dot: string; chipBg: string; chipText: string }
> = {
  clean: {
    label: 'Clean',
    labelKey: 'counties.audit_status.clean',
    dot: 'bg-emerald-500',
    chipBg: 'bg-emerald-50',
    chipText: 'text-emerald-700',
  },
  qualified: {
    label: 'Qualified',
    labelKey: 'counties.audit_status.qualified',
    dot: 'bg-amber-500',
    chipBg: 'bg-amber-50',
    chipText: 'text-amber-700',
  },
  adverse: {
    label: 'Adverse',
    labelKey: 'counties.audit_status.adverse',
    dot: 'bg-red-500',
    chipBg: 'bg-red-50',
    chipText: 'text-red-700',
  },
  disclaimer: {
    label: 'Disclaimer',
    labelKey: 'counties.audit_status.disclaimer',
    dot: 'bg-red-700',
    chipBg: 'bg-red-100',
    chipText: 'text-red-800',
  },
  pending: {
    label: 'Pending',
    labelKey: 'counties.audit_status.pending',
    dot: 'bg-gray-400',
    chipBg: 'bg-gray-50 dark:bg-surface-elevated',
    chipText: 'text-gray-600 dark:text-neutral-muted',
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

/* Small icon badge used as the right-side accent on money KPI cards.
   Historical sparklines aren't available yet, so this is purely decorative. */
function KpiIcon({ tone }: { tone: 'positive' | 'negative' }) {
  const bg = tone === 'positive' ? 'bg-emerald-50' : 'bg-rose-50';
  const stroke = tone === 'positive' ? '#059669' : '#e11d48';
  return (
    <div
      className={`w-10 h-10 rounded-full ${bg} flex items-center justify-center flex-shrink-0`}
      aria-hidden>
      <svg viewBox='0 0 20 20' className='w-5 h-5' fill='none' stroke={stroke} strokeWidth='2'>
        {tone === 'positive' ? (
          <path d='M4 14 L9 9 L12 12 L16 6' strokeLinecap='round' strokeLinejoin='round' />
        ) : (
          <path d='M4 6 L9 11 L12 8 L16 14' strokeLinecap='round' strokeLinejoin='round' />
        )}
      </svg>
    </div>
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
  const { t } = useLang();
  const stats = useMemo(() => {
    const totalBudget = counties.reduce((s, c) => s + (c.totalBudget ?? c.budget ?? 0), 0);
    const totalDebt = counties.reduce((s, c) => s + (c.totalDebt ?? c.debt ?? 0), 0);
    // Average only across counties that actually reported execution — otherwise
    // the mean gets diluted by zeros and makes every year look underperforming.
    const execReporters = counties.filter((c) => (c.budgetUtilization ?? 0) > 0);
    const avgExec =
      execReporters.length > 0
        ? execReporters.reduce((s, c) => s + (c.budgetUtilization ?? 0), 0) / execReporters.length
        : 0;
    const auditCounts = { clean: 0, qualified: 0, adverse: 0 };
    counties.forEach((c) => {
      const st = c.auditStatus ?? 'pending';
      if (st in auditCounts) auditCounts[st as keyof typeof auditCounts]++;
    });
    const totalAudits = auditCounts.clean + auditCounts.qualified + auditCounts.adverse;
    const byDebt = [...counties]
      .sort((a, b) => (b.totalDebt ?? b.debt ?? 0) - (a.totalDebt ?? a.debt ?? 0))
      .slice(0, 3);
    return { totalBudget, totalDebt, avgExec, auditCounts, totalAudits, byDebt };
  }, [counties]);

  const donutData = [
    { name: t('counties.audit_status.clean'), value: stats.auditCounts.clean, color: '#22c55e' },
    { name: t('counties.audit_status.qualified'), value: stats.auditCounts.qualified, color: '#f59e0b' },
    { name: t('counties.audit_status.adverse'), value: stats.auditCounts.adverse, color: '#ef4444' },
  ];

  return (
    <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4'>
      {/* Card 1: Total Budget */}
      <Link
        href='/budget'
        className='ledger-panel-interactive flex items-center justify-between gap-3 p-5'>
        <div className='min-w-0'>
          <div className='text-xs font-medium text-gray-500 dark:text-neutral-muted/80 mb-1'>{t('counties.kpi.total_budget')}</div>
          <div className='text-2xl font-bold text-gray-900 dark:text-neutral-text tracking-tight'>
            {fmtKES(stats.totalBudget)}
          </div>
          <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 font-medium mt-0.5'>
            {t('counties.kpi.across_counties').replace('{n}', String(counties.length))}
          </div>
        </div>
        <KpiIcon tone='positive' />
      </Link>

      {/* Card 2: Total Debt */}
      <Link
        href='/budget?tab=debt'
        className='ledger-panel-interactive flex items-center justify-between gap-3 p-5'>
        <div className='min-w-0'>
          <div className='text-xs font-medium text-gray-500 dark:text-neutral-muted/80 mb-1'>{t('counties.kpi.total_debt')}</div>
          <div className='text-2xl font-bold text-gray-900 dark:text-neutral-text tracking-tight'>
            {fmtKES(stats.totalDebt)}
          </div>
          <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 font-medium mt-0.5'>
            {t('counties.kpi.pending_bills_loans')}
          </div>
        </div>
        <KpiIcon tone='negative' />
      </Link>

      {/* Card 3: Avg. Execution Rate */}
      <div className='ledger-panel flex items-center justify-between gap-3 p-5'>
        <div className='min-w-0'>
          <div className='text-xs font-medium text-gray-500 dark:text-neutral-muted/80 mb-1'>
            {t('counties.kpi.avg_execution_rate')} <InfoTip term='budget-execution' size={11} />
          </div>
          {stats.avgExec > 0 ? (
            <>
              <div className='text-2xl font-bold text-gray-900 dark:text-neutral-text tracking-tight'>
                {stats.avgExec.toFixed(0)}%
              </div>
              <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-0.5'>{t('counties.kpi.target_70')}</div>
            </>
          ) : (
            <>
              <div className='text-2xl font-bold text-gray-400 dark:text-neutral-muted/80 tracking-tight'>—</div>
              <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-0.5'>{t('counties.kpi.not_reported')}</div>
            </>
          )}
        </div>
        <GaugeMini value={stats.avgExec} target={70} />
      </div>

      {/* Card 4: Audit Summary */}
      <div className='ledger-panel p-5'>
        <div className='text-xs font-medium text-gray-500 dark:text-neutral-muted/80 mb-2'>{t('counties.kpi.audit_summary')}</div>
        {stats.totalAudits > 0 ? (
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
                  <span className='text-gray-600 dark:text-neutral-muted'>{d.name}</span>
                  <span className='font-semibold text-gray-800 dark:text-neutral-text'>{d.value}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className='flex items-center h-14 text-xs text-gray-400 dark:text-neutral-muted/80'>
            {t('counties.kpi.no_audits_year')}
          </div>
        )}
        <p className='mt-2 text-[11px] leading-snug text-gray-400 dark:text-neutral-muted/80 italic'>
          {t('counties.kpi.audit_status_derived')}
        </p>
      </div>

      {/* Card 5: High Debt Counties */}
      <div className='ledger-panel p-4'>
        <div className='text-xs font-medium text-gray-500 dark:text-neutral-muted/80 mb-2'>{t('counties.kpi.high_debt_counties')}</div>
        <div className='space-y-2'>
          {stats.byDebt.map((c, i) => {
            const debt = c.totalDebt ?? c.debt ?? 0;
            const budget = c.totalBudget ?? c.budget ?? 0;
            const auditCfg = AUDIT_STATUS_CFG[c.auditStatus ?? 'pending'];
            return (
              <Link
                key={c.id}
                href={`/counties/${c.id}?tab=budget`}
                className='flex items-center gap-2 hover:bg-white/40 dark:bg-surface-elevated -mx-1 px-1 py-0.5 rounded-lg transition-colors'>
                <span className='text-[11px] font-bold text-gray-400 dark:text-neutral-muted/80 w-3'>{i + 1}</span>
                <div className='flex-1 min-w-0'>
                  <div className='flex items-center justify-between'>
                    <span className='text-xs font-semibold text-gray-800 dark:text-neutral-text truncate'>{c.name}</span>
                    <span
                      className={`text-[11px] font-semibold px-1.5 py-0.5 rounded-full ${auditCfg.chipBg} ${auditCfg.chipText}`}>
                      {t(auditCfg.labelKey)}
                    </span>
                  </div>
                  <div className='flex items-center gap-2 mt-0.5'>
                    <span className='text-[11px] text-gray-600 dark:text-neutral-muted tabular-nums'>{fmtKES(debt)}</span>
                    <span className='text-[11px] text-gray-400 dark:text-neutral-muted/80 tabular-nums'>{fmtKES(budget)}</span>
                  </div>
                  <div className='h-1 bg-gray-100 dark:bg-surface-elevated rounded-full mt-1 overflow-hidden'>
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
  const { t } = useLang();

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
        className='ledger-panel-interactive flex items-center justify-center p-3'>
        <Filter size={18} className='text-gray-500 dark:text-neutral-muted/80' />
      </button>
    );
  }

  return (
    <div className='ledger-panel overflow-hidden'>
      {/* Header */}
      <div className='flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-neutral-border'>
        <h3 className='text-sm font-bold text-gray-900 dark:text-neutral-text'>{t('counties.filters.title')}</h3>
        <button
          onClick={() => setCollapsed(true)}
          className='text-gray-400 dark:text-neutral-muted/80 hover:text-gray-600 dark:text-neutral-muted transition-colors'>
          <ChevronsLeft size={16} />
        </button>
      </div>

      <div className='p-5 space-y-5'>
        {/* Search County */}
        <div>
          <label className='text-[11px] font-semibold text-gray-600 dark:text-neutral-muted uppercase tracking-wider mb-1.5 block'>
            {t('counties.filters.search_county')}
          </label>
          <div className='relative'>
            <Search size={14} className='absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-neutral-muted/80' />
            <input
              type='text'
              value={filters.search}
              onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
              placeholder={t('counties.filters.type_to_search')}
              className='w-full pl-9 pr-3 py-2 bg-gray-50 dark:bg-surface-elevated border border-gray-200 dark:border-neutral-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-gov-forest/20 focus:border-gov-forest/40 placeholder-gray-400'
            />
          </div>
        </div>

        {/* Region */}
        <div>
          <label className='text-[11px] font-semibold text-gray-600 dark:text-neutral-muted uppercase tracking-wider mb-1.5 block'>
            {t('counties.filter.region')}
          </label>
          <div className='relative'>
            <select
              value={filters.region}
              onChange={(e) => setFilters((f) => ({ ...f, region: e.target.value }))}
              className='w-full appearance-none bg-gray-50 dark:bg-surface-elevated border border-gray-200 dark:border-neutral-border rounded-lg px-3 py-2 pr-8 text-sm text-gray-700 dark:text-neutral-muted focus:outline-none focus:ring-2 focus:ring-gov-forest/20'>
              <option value='all'>{t('counties.filters.all_regions')}</option>
              <option value='central'>{t('counties.region.central')}</option>
              <option value='coast'>{t('counties.region.coast')}</option>
              <option value='eastern'>{t('counties.region.eastern')}</option>
              <option value='nairobi'>{t('counties.region.nairobi')}</option>
              <option value='north-eastern'>{t('counties.region.north_eastern')}</option>
              <option value='nyanza'>{t('counties.region.nyanza')}</option>
              <option value='rift-valley'>{t('counties.region.rift_valley')}</option>
              <option value='western'>{t('counties.region.western')}</option>
            </select>
            <ChevronDown
              size={14}
              className='absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-neutral-muted/80 pointer-events-none'
            />
          </div>
        </div>

        {/* Grade */}
        <div>
          <label className='text-[11px] font-semibold text-gray-600 dark:text-neutral-muted uppercase tracking-wider mb-1.5 block'>
            {t('counties.filters.grade')}
          </label>
          <div className='flex items-center gap-1.5 flex-wrap'>
            {GRADE_ALL.map((g) => {
              const active = filters.grades.includes(g);
              return (
                <button
                  key={g}
                  onClick={() => toggleGrade(g)}
                  className={`w-8 h-8 rounded-lg text-xs font-bold transition-[background-color,border-color,color,box-shadow] ${
                    active
                      ? GRADE_COLORS[g] + ' shadow-sm ring-2 ring-offset-1 ring-gray-300'
                      : 'bg-gray-100 dark:bg-surface-elevated text-gray-500 dark:text-neutral-muted/80 hover:bg-gray-200 dark:bg-surface-sunken'
                  }`}>
                  {g}
                </button>
              );
            })}
            <button className='text-gray-400 dark:text-neutral-muted/80 hover:text-gray-600 dark:text-neutral-muted ml-1'>
              <ChevronDown size={14} />
            </button>
          </div>
        </div>

        {/* Audit Status */}
        <div>
          <label className='text-[11px] font-semibold text-gray-600 dark:text-neutral-muted uppercase tracking-wider mb-1.5 block'>
            {t('counties.filters.audit_status')} <InfoTip term='audit-clean' size={11} />
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
                        : 'border-gray-300 dark:border-neutral-border group-hover:border-gray-400'
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
                  <span className='text-sm text-gray-700 dark:text-neutral-muted'>{t(cfg.labelKey)}</span>
                </label>
              );
            })}
          </div>
        </div>

        {/* Spending Range */}
        <div>
          <label className='text-[11px] font-semibold text-gray-600 dark:text-neutral-muted uppercase tracking-wider mb-2 block'>
            {t('counties.filters.spending_range')}
          </label>
          <input
            type='range'
            min={0}
            max={150}
            value={filters.spendingRange[1]}
            onChange={(e) =>
              setFilters((f) => ({ ...f, spendingRange: [0, Number(e.target.value)] }))
            }
            className='w-full h-1.5 bg-gray-200 dark:bg-surface-sunken rounded-full appearance-none cursor-pointer accent-gov-forest'
          />
          <div className='flex justify-between text-[11px] text-gray-400 dark:text-neutral-muted/80 mt-1 tabular-nums'>
            <span>KES 0B</span>
            <span>—</span>
            <span>{filters.spendingRange[1]}B+</span>
          </div>
        </div>

        {/* Sort by */}
        <div>
          <label className='text-[11px] font-semibold text-gray-600 dark:text-neutral-muted uppercase tracking-wider mb-1.5 block'>
            {t('counties.filter.sort')}
          </label>
          <div className='relative'>
            <select
              value={filters.sortBy}
              onChange={(e) => setFilters((f) => ({ ...f, sortBy: e.target.value }))}
              className='w-full appearance-none bg-gray-50 dark:bg-surface-elevated border border-gray-200 dark:border-neutral-border rounded-lg px-3 py-2 pr-8 text-sm text-gray-700 dark:text-neutral-muted focus:outline-none focus:ring-2 focus:ring-gov-forest/20'>
              <option value='budget-desc'>{t('counties.sort.budget_high_low')}</option>
              <option value='budget-asc'>{t('counties.sort.budget_low_high')}</option>
              <option value='debt-desc'>{t('counties.sort.debt_high_low')}</option>
              <option value='population-desc'>{t('counties.sort.population_high_low')}</option>
              <option value='health-desc'>{t('counties.sort.grade_best_worst')}</option>
              <option value='utilization-desc'>{t('counties.sort.execution_high_low')}</option>
            </select>
            <ChevronDown
              size={14}
              className='absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-neutral-muted/80 pointer-events-none'
            />
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className='px-5 pb-5 pt-2 flex gap-2'>
        <button
          onClick={onApply}
          className='flex-1 bg-gov-forest text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-gov-forest/90 transition-colors'>
          {t('counties.filters.apply')}
        </button>
        <button
          onClick={onReset}
          className='px-4 bg-gray-100 dark:bg-surface-elevated text-gray-700 dark:text-neutral-muted text-sm font-medium py-2.5 rounded-lg hover:bg-gray-200 dark:bg-surface-sunken transition-colors'>
          {t('counties.filters.reset')}
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
  const { t } = useLang();
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
    <div className='ledger-panel h-full p-5'>
      <h3 className='text-sm font-bold text-gray-900 dark:text-neutral-text mb-3'>{t('counties.map.title')}</h3>
      <div
        ref={containerRef}
        className='relative bg-gov-forest/5 rounded-xl overflow-hidden flex items-center justify-center'
        style={{ height: 280 }}>
        <svg viewBox={regionViewBox} className='w-auto h-full p-1 transition-[width,height,transform] duration-500'>
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
              {t('counties.map.tooltip_grade')}: {getGrade(hoveredCounty.financial_health_score).letter} · {t('counties.map.tooltip_exec')}:{' '}
              {(hoveredCounty.budgetUtilization ?? 0).toFixed(0)}%
            </div>
            <div className='text-white/60'>
              {t('counties.map.tooltip_budget')}: KES {fmtKES(hoveredCounty.totalBudget ?? hoveredCounty.budget ?? 0)}
            </div>
          </div>
        )}
      </div>
      {/* Grade legend — clickable to filter */}
      <div className='flex items-center gap-2 mt-3'>
        <span className='text-[11px] text-gray-500 dark:text-neutral-muted/80 font-medium'>{t('counties.map.performance')}:</span>
        {GRADE_ALL.map((g) => {
          const isActive = activeGrades.length === 0 || activeGrades.includes(g);
          return (
            <button
              key={g}
              onClick={() => onToggleGrade(g)}
              className={`w-7 h-6 rounded text-[11px] font-bold flex items-center justify-center border-2 transition-[background-color,border-color,color,opacity,box-shadow] ${
                isActive
                  ? `${GRADE_COLORS[g]} border-transparent shadow-sm`
                  : 'bg-gray-100 dark:bg-surface-elevated text-gray-400 dark:text-neutral-muted/80 border-gray-200 dark:border-neutral-border opacity-50'
              }`}>
              {g}
            </button>
          );
        })}
        {activeGrades.length > 0 && (
          <button
            onClick={() => activeGrades.forEach((g) => onToggleGrade(g))}
            className='text-[11px] text-gray-400 dark:text-neutral-muted/80 hover:text-gray-600 dark:text-neutral-muted ml-1 underline'>
            {t('counties.map.clear')}
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
  const { t } = useLang();

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
      <div className='ledger-panel flex items-center justify-center p-5 text-sm text-gray-400 dark:text-neutral-muted/80 md:col-span-2'>
        {t('counties.insights.no_match')}
      </div>
    );
  }

  return (
    <div className='ledger-panel p-5 md:col-span-2'>
      {/* Region summary bar */}
      <div className='flex items-center gap-4 mb-4 pb-3 border-b border-gray-200/60 dark:border-neutral-border/60 flex-wrap'>
        <span className='text-sm font-bold text-gray-900 dark:text-neutral-text'>
          {stats.count} {stats.count === 1 ? t('common.county') : t('common.counties')}
        </span>
        <div className='flex items-center gap-1.5 text-xs text-gray-500 dark:text-neutral-muted/80'>
          <span className='font-semibold text-gray-700 dark:text-neutral-muted'>{t('counties.insights.budget')}:</span>
          <span className='tabular-nums'>{fmtKES(stats.totalBudget)}</span>
        </div>
        <div className='flex items-center gap-1.5 text-xs text-gray-500 dark:text-neutral-muted/80'>
          <span className='font-semibold text-gray-700 dark:text-neutral-muted'>{t('counties.insights.debt')}:</span>
          <span className='tabular-nums text-red-600'>{fmtKES(stats.totalDebt)}</span>
        </div>
        <div className='flex items-center gap-1.5 text-xs text-gray-500 dark:text-neutral-muted/80'>
          <span className='font-semibold text-gray-700 dark:text-neutral-muted'>{t('counties.insights.avg_exec')}:</span>
          <span className='tabular-nums'>{stats.avgUtil.toFixed(0)}%</span>
        </div>
        <div className='flex items-center gap-1.5 text-xs'>
          <span className='font-semibold text-gray-700 dark:text-neutral-muted'>{t('counties.insights.avg_health')}:</span>
          <span
            className={`px-1.5 py-0.5 rounded font-bold text-[11px] ${GRADE_COLORS[gradeCategory(stats.avgHealth)]}`}>
            {gradeCategory(stats.avgHealth)} ({stats.avgHealth.toFixed(0)})
          </span>
        </div>
      </div>

      <div className='grid grid-cols-1 md:grid-cols-2 gap-4'>
        {/* Best performers */}
        <div>
          <h4 className='flex items-center gap-1.5 text-xs font-bold text-emerald-700 uppercase tracking-wider mb-2'>
            <TrendingUp size={13} /> {t('counties.insights.best_performers')}
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
            <AlertTriangle size={13} /> {t('counties.insights.needs_attention')}
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
  const { t } = useLang();
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
      className='flex items-center gap-2.5 hover:bg-white/50 dark:bg-surface-elevated -mx-2 px-2 py-1.5 rounded-lg transition-colors'>
      <span className='text-xs font-bold text-gray-400 dark:text-neutral-muted/80 w-3 text-right'>{rank}</span>
      <div className='flex-1 min-w-0'>
        <div className='flex items-center gap-2 mb-0.5'>
          <span className='text-sm font-semibold text-gray-800 dark:text-neutral-text truncate'>{c.name}</span>
          <span className={`text-[11px] font-bold px-1.5 py-0.5 rounded ${grade.cls}`}>
            {grade.letter}
          </span>
          <span
            className={`text-[11px] font-medium px-1.5 py-0.5 rounded-full ml-auto flex items-center gap-1 ${auditCfg.chipBg} ${auditCfg.chipText}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${auditCfg.dot}`} />
            {t(auditCfg.labelKey)}
          </span>
        </div>
        <div className='flex items-center gap-3'>
          {/* Utilization bar */}
          <div className='flex items-center gap-1.5 flex-1'>
            <span className='text-[11px] text-gray-500 dark:text-neutral-muted/80 w-7'>{t('counties.insights.exec_short')}</span>
            <div className='flex-1 h-1.5 bg-gray-100 dark:bg-surface-elevated rounded-full overflow-hidden'>
              <div
                className={`h-full rounded-full ${util >= 70 ? 'bg-emerald-500' : util >= 50 ? 'bg-amber-500' : 'bg-red-400'}`}
                style={{ width: `${Math.min(util, 100)}%` }}
              />
            </div>
            <span className='text-[11px] font-semibold text-gray-700 dark:text-neutral-muted w-7 tabular-nums'>
              {util.toFixed(0)}%
            </span>
          </div>
          {/* Debt ratio */}
          <div className='flex items-center gap-1.5'>
            <span className='text-[11px] text-gray-500 dark:text-neutral-muted/80'>{t('counties.insights.debt_short')}</span>
            <span
              className={`text-[11px] font-bold tabular-nums ${
                Number(debtRatio) > 50 ? 'text-red-600' : 'text-gray-600 dark:text-neutral-muted'
              }`}>
              {debtRatio}%
            </span>
            <span className='text-[11px] text-gray-400 dark:text-neutral-muted/80 tabular-nums'>{fmtKES(budget)}</span>
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
      <div className='w-20 h-2 bg-gray-100 dark:bg-surface-elevated rounded-full overflow-hidden'>
        <div className={`h-full rounded-full ${clr}`} style={{ width: `${clamped}%` }} />
      </div>
      <span className='text-xs tabular-nums text-gray-700 dark:text-neutral-muted w-8'>{pct.toFixed(0)}%</span>
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
      className={`text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 py-3 px-3 cursor-pointer select-none hover:text-gray-800 dark:text-neutral-text transition-colors whitespace-nowrap ${className}`}
      onClick={() => onSort(field)}>
      <span className='inline-flex items-center gap-1'>
        {children}
        {suffix && (
          <span className='text-[11px] text-gray-400 dark:text-neutral-muted/80 font-normal normal-case tracking-normal'>
            {suffix}
          </span>
        )}
        <ArrowUpDown size={11} className={active ? 'text-gov-forest dark:text-emerald-100' : 'text-gray-300 dark:text-neutral-muted/60'} />
        {active && (
          <span className='text-[11px] text-gov-forest dark:text-emerald-100 font-normal'>
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
  fiscalYear,
}: {
  counties: County[];
  sortField: SortField;
  sortDir: SortDir;
  onSort: (f: SortField) => void;
  fiscalYear: string;
}) {
  const { t } = useLang();
  // BOTH pagination (?p=N) and the "View All" toggle (?view=all) are
  // URL-driven so that browser back from a county detail page restores
  // whichever list mode the user was in. Local `useState` would reset
  // on every re-mount after client navigation — that's exactly the bug
  // the user reported ("View All → click county → back → lost full list").
  //
  // We read the URL via `window.location.search` rather than the
  // `useSearchParams()` hook because the hook can return an empty
  // params map on first client render in App Router — the URL shows
  // `?p=3` but the hook says `{}`, so the table renders page 1. Direct
  // window access bypasses that hydration-timing bug.
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const readPageFromUrl = useCallback((): number => {
    if (typeof window === 'undefined') return 1;
    const raw = new URLSearchParams(window.location.search).get('p');
    const n = parseInt(raw || '1', 10);
    return Number.isFinite(n) && n > 0 ? n : 1;
  }, []);

  const readShowAllFromUrl = useCallback((): boolean => {
    if (typeof window === 'undefined') return false;
    return new URLSearchParams(window.location.search).get('view') === 'all';
  }, []);

  const [pageFromUrl, setPageFromUrl] = useState<number>(() => readPageFromUrl());
  const [showAll, setShowAllLocal] = useState<boolean>(() => readShowAllFromUrl());

  // Keep local mirrors in sync with browser history (back/forward, manual edits).
  useEffect(() => {
    const onPop = () => {
      setPageFromUrl(readPageFromUrl());
      setShowAllLocal(readShowAllFromUrl());
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, [readPageFromUrl, readShowAllFromUrl]);

  // Also resync when Next.js internal navigation updates `searchParams`.
  useEffect(() => {
    setPageFromUrl(readPageFromUrl());
    setShowAllLocal(readShowAllFromUrl());
  }, [searchParams, readPageFromUrl, readShowAllFromUrl]);

  const totalPages = Math.ceil(counties.length / PAGE_SIZE);
  // Clamp to valid range — an out-of-range `p` just clamps to last page.
  const page = Math.min(Math.max(1, pageFromUrl), Math.max(1, totalPages));
  const paged = showAll ? counties : counties.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const setPage = useCallback(
    (next: number | ((prev: number) => number)) => {
      const resolved = typeof next === 'function' ? next(page) : next;
      const clamped = Math.min(Math.max(1, resolved), Math.max(1, totalPages));
      const qs = new URLSearchParams(window.location.search);
      if (clamped === 1) qs.delete('p');
      else qs.set('p', String(clamped));
      const newSearch = qs.toString();
      router.replace(newSearch ? `${pathname}?${newSearch}` : pathname, { scroll: false });
      setPageFromUrl(clamped);
    },
    [page, totalPages, pathname, router]
  );

  const setShowAll = useCallback(
    (next: boolean | ((prev: boolean) => boolean)) => {
      const resolved = typeof next === 'function' ? next(showAll) : next;
      const qs = new URLSearchParams(window.location.search);
      if (resolved) {
        qs.set('view', 'all');
        // ?p=N is meaningless in "view all" mode — strip it so a subsequent
        // toggle-off doesn't resurrect a stale page index.
        qs.delete('p');
      } else {
        qs.delete('view');
      }
      const newSearch = qs.toString();
      router.replace(newSearch ? `${pathname}?${newSearch}` : pathname, { scroll: false });
      setShowAllLocal(resolved);
    },
    [showAll, pathname, router]
  );

  // If the filter changes and the current page no longer has rows,
  // drop back to page 1. Do NOT write the URL on mount — that would
  // strip `?p=N` during back-navigation from the detail page.
  useEffect(() => {
    if (pageFromUrl > totalPages && totalPages >= 1) {
      setPage(1);
    }
  }, [totalPages, pageFromUrl, setPage]);

  const pageNums = useMemo(() => {
    const nums: number[] = [];
    const start = Math.max(1, page - 2);
    const end = Math.min(totalPages, start + 4);
    for (let i = start; i <= end; i++) nums.push(i);
    return nums;
  }, [page, totalPages]);

  return (
    <div className='ledger-panel overflow-hidden'>
      <div className='flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-neutral-border'>
        <div className='flex items-center gap-2'>
          <h3 className='text-sm font-bold text-gray-900 dark:text-neutral-text'>{t('counties.rankings.title')}</h3>
          <span className='text-xs text-gray-400 dark:text-neutral-muted/80'>
            ({t('counties.rankings.range_of')
              .replace('{from}', String((page - 1) * PAGE_SIZE + 1))
              .replace('{to}', String(Math.min(page * PAGE_SIZE, counties.length)))
              .replace('{total}', String(counties.length))})
          </span>
        </div>
      </div>

      <div className='overflow-x-auto'>
        <table className='w-full border-collapse min-w-[820px]'>
          <thead>
            <tr className='border-b border-gray-100 dark:border-neutral-border bg-gray-50/60 dark:bg-surface-elevated/70'>
              <th className='text-left text-[11px] font-semibold uppercase tracking-wider text-gray-400 dark:text-neutral-muted/80 py-3 px-4 w-8'>
                #
              </th>
              <Th field='name' current={sortField} dir={sortDir} onSort={onSort}>
                {t('counties.rankings.col_county')}
              </Th>
              <Th field='population' current={sortField} dir={sortDir} onSort={onSort}>
                {t('counties.rankings.col_population')}
              </Th>
              <Th field='health' current={sortField} dir={sortDir} onSort={onSort}>
                {t('counties.rankings.col_health')} <InfoTip term='financial-health' size={10} />
              </Th>
              <Th field='budget' current={sortField} dir={sortDir} onSort={onSort} suffix='(KES)'>
                {t('counties.rankings.col_budget')}
              </Th>
              <Th field='utilization' current={sortField} dir={sortDir} onSort={onSort}>
                {t('counties.rankings.col_execution')} <InfoTip term='budget-execution' size={10} />
              </Th>
              <Th field='debt' current={sortField} dir={sortDir} onSort={onSort}>
                {t('counties.rankings.col_debt')}
              </Th>
              <th className='text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 py-3 px-3'>
                {t('counties.rankings.col_audit')} <InfoTip term='audit-clean' size={10} />
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
              const base = `/counties/${county.id}?fy=${encodeURIComponent(fiscalYear)}`;
              const rank = showAll ? i + 1 : (page - 1) * PAGE_SIZE + i + 1;

              return (
                <tr
                  key={county.id}
                  className='group border-b border-gray-50 dark:border-neutral-border last:border-0 hover:bg-gov-forest/[0.025] transition-colors cursor-pointer'>
                  <td className='py-3 px-4 text-xs text-gray-400 dark:text-neutral-muted/80 tabular-nums'>{rank}</td>
                  <td className='py-3 px-3'>
                    <Link href={base} className='flex items-center gap-2'>
                      <div className='w-6 h-6 rounded-md bg-gov-forest/10 flex items-center justify-center flex-shrink-0'>
                        <span className='text-[11px]'>🏛️</span>
                      </div>
                      <span className='font-semibold text-sm text-gray-900 dark:text-neutral-text group-hover:text-gov-forest dark:text-emerald-100 transition-colors'>
                        {county.name}
                      </span>
                    </Link>
                  </td>
                  <td className='py-3 px-3 text-sm text-gray-600 dark:text-neutral-muted tabular-nums'>
                    <Link href={base} className='block'>
                      {fmtPop(county.population)}
                    </Link>
                  </td>
                  <td className='py-3 px-3'>
                    <Link href={`${base}&tab=budget`} className='block'>
                      <span
                        className={`inline-flex items-center justify-center w-8 h-6 text-[11px] font-bold rounded-md ${grade.cls}`}>
                        {grade.letter}
                      </span>
                    </Link>
                  </td>
                  <td className='py-3 px-3'>
                    <Link
                      href={`${base}&tab=budget`}
                      className='block text-sm text-gray-700 dark:text-neutral-muted tabular-nums font-medium hover:text-gov-forest dark:text-emerald-100 transition-colors'>
                      {fmtKES(budget)}
                    </Link>
                  </td>
                  <td className='py-3 px-3'>
                    <Link href={`${base}&tab=budget`} className='block'>
                      <ExecBar pct={util} />
                    </Link>
                  </td>
                  <td className='py-3 px-3'>
                    <Link
                      href={`${base}&tab=budget`}
                      className='flex items-center gap-1.5 text-sm text-gray-700 dark:text-neutral-muted tabular-nums hover:text-gov-forest dark:text-emerald-100 transition-colors'>
                      <span
                        className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${debt > 50e9 ? 'bg-red-500' : debt > 15e9 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                      />
                      {fmtKES(debt)}
                    </Link>
                  </td>
                  <td className='py-3 px-3'>
                    <Link href={`${base}&tab=audit`} className='flex items-center gap-1.5'>
                      <span
                        className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-full ${auditCfg.chipBg} ${auditCfg.chipText}`}>
                        {auditCfg.label === 'Adverse'
                          ? '🔺'
                          : auditCfg.label === 'Clean'
                            ? '✅'
                            : '⚠️'}{' '}
                        {t(auditCfg.labelKey)}
                      </span>
                      {issues > 0 && (
                        <span className='text-[11px] text-gray-500 dark:text-neutral-muted/80 font-medium'>({issues})</span>
                      )}
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {counties.length === 0 && (
        <div className='text-center py-12 px-4'>
          <Search size={28} className='mx-auto text-gray-300 dark:text-neutral-muted/60 mb-2' />
          <p className='text-sm text-gray-500 dark:text-neutral-muted/80'>{t('counties.rankings.no_match')}</p>
        </div>
      )}

      {counties.length > 0 && (
        <div className='flex items-center justify-between px-5 py-3 border-t border-gray-100 dark:border-neutral-border bg-gray-50/40 dark:bg-surface-elevated/70'>
          <span className='text-xs text-gray-500 dark:text-neutral-muted/80'>
            {showAll
              ? t('counties.rankings.showing_all').replace('{n}', String(counties.length))
              : t('counties.rankings.showing_range')
                  .replace('{from}', String((page - 1) * PAGE_SIZE + 1))
                  .replace('{to}', String(Math.min(page * PAGE_SIZE, counties.length)))
                  .replace('{total}', String(counties.length))}
          </span>
          {!showAll && (
            <div className='flex items-center gap-1'>
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className='px-2.5 py-1.5 text-xs text-gray-500 dark:text-neutral-muted/80 hover:text-gray-800 dark:text-neutral-text disabled:opacity-30 disabled:cursor-not-allowed rounded-md hover:bg-gray-100 dark:bg-surface-elevated'>
                {t('counties.rankings.prev')}
              </button>
              {pageNums.map((n) => (
                <button
                  key={n}
                  onClick={() => setPage(n)}
                  className={`w-7 h-7 text-xs font-medium rounded-md transition-colors ${
                    n === page ? 'bg-gov-forest text-white' : 'text-gray-600 dark:text-neutral-muted hover:bg-gray-100 dark:bg-surface-elevated'
                  }`}>
                  {n}
                </button>
              ))}
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className='px-2.5 py-1.5 text-xs text-gray-500 dark:text-neutral-muted/80 hover:text-gray-800 dark:text-neutral-text disabled:opacity-30 disabled:cursor-not-allowed rounded-md hover:bg-gray-100 dark:bg-surface-elevated'>
                {t('counties.rankings.next')}
              </button>
            </div>
          )}
          <button
            onClick={() => setShowAll((v) => !v)}
            className='text-xs text-gov-forest dark:text-emerald-100 font-medium hover:underline'>
            {showAll ? t('counties.rankings.show_paginated') : t('counties.rankings.view_all')}
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
  const { t } = useLang();
  // Year dropdown state (must be declared before useCounties which depends on it)
  // Default to the latest *reported* FY — the current FY usually has allocations
  // but no execution/audit data yet, which makes the KPI row look broken.
  const YEARS = generateFiscalYears(4);
  const [selectedYear, setSelectedYear] = useState(getLatestReportedFiscalYear());
  const [yearOpen, setYearOpen] = useState(false);

  const { data: counties, isLoading, error, refetch } = useCounties({ fiscalYear: selectedYear });

  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const [sortField, setSortField] = useState<SortField>('budget');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // NOTE: "View All" toggle state now lives inside CountyRankingsTable
  // and is URL-driven via ?view=all so that back-navigation from a
  // county detail page restores the full-list view.

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
      'Health Grade',
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
      <div className='county-explorer relative min-h-screen' style={{ backgroundColor: `rgb(${COUNTIES_NEUTRAL_RGB})` }}>
        <CountiesScenicBottom />
        <div className='relative z-[1]'>
          <div className='bg-gov-dark'>
            <div className='h-16' />
            <div className='max-w-[1400px] mx-auto px-5 lg:px-8 pt-8 pb-10'>
              <h1 className='font-display text-4xl font-semibold uppercase leading-[0.95] text-white sm:text-5xl lg:text-[4.25rem]'>
                {t('counties.title')}
              </h1>
              <p className='mt-3 max-w-xl text-sm text-white/60'>Loading the latest county evidence…</p>
            </div>
          </div>
          {/* Reserve roughly the height of the loaded rankings + sidebar
              so the scenic image below doesn't leap into a different
              position once `useCounties` resolves. The table at a
              typical viewport runs ~1100px; pad to 1200 to account for
              KPI row + pagination. */}
          <div
            className='max-w-[1400px] mx-auto px-5 lg:px-8 py-8'
            style={{ minHeight: 1200 }}>
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
      <div className='county-explorer relative min-h-screen' style={{ backgroundColor: `rgb(${COUNTIES_NEUTRAL_RGB})` }}>
        <CountiesScenicBottom />
        <div className='relative z-[1]'>
          <div className='bg-gov-dark'>
            <div className='h-16' />
            <div className='max-w-[1400px] mx-auto px-5 lg:px-8 pt-8 pb-10'>
              <h1 className='font-display text-4xl font-semibold uppercase sm:text-5xl lg:text-[4.25rem] text-white leading-[0.95]'>
                {t('counties.title')}
              </h1>
            </div>
          </div>
          <div className='max-w-[1400px] mx-auto px-5 lg:px-8 py-8 text-center'>
            <AlertTriangle size={40} className='mx-auto text-red-400 mb-3' />
            <p className='text-red-600 mb-4'>{t('counties.error.title')}</p>
            <button
              onClick={() => refetch()}
              className='btn-primary text-sm'>
              {t('counties.header.retry')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className='county-explorer relative min-h-screen dark:bg-[#0d1711]'
      style={{ backgroundColor: `rgb(${COUNTIES_NEUTRAL_RGB})` }}>
      <CountiesScenicBottom />

      {/* ═══ Content layer ═══ */}
      <div className='relative z-[1]'>
        {/* ══ Dark-green header band ══ */}
        <div className='relative border-b border-white/10 bg-gov-dark'>
          <div aria-hidden='true' className='absolute inset-y-0 left-0 w-1.5 bg-gov-copper' />
          <div className='h-16' />
          <div className='max-w-[1400px] mx-auto px-5 lg:px-8 pt-8 pb-10'>
            <div className='flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4'>
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, ease: 'easeOut' }}
                className='max-w-3xl'>
                <p className='mb-2 font-mono text-[11px] uppercase tracking-[0.18em] text-gov-gold'>AuditGava / county evidence</p>
                <h1 className='font-display text-4xl font-semibold uppercase sm:text-5xl lg:text-[4.25rem] text-white leading-[0.95] mb-3'>
                  {t('counties.title')}
                </h1>
                <p className='max-w-3xl text-[15px] leading-6 text-white/68 sm:text-base'>
                  {(() => {
                    const tpl = t('counties.header.subtitle_rich');
                    const strong = t('counties.header.subtitle_strong');
                    const [before, after] = tpl.split('{strong}');
                    return (
                      <>
                        {before}
                        <strong className='text-white/90'>{strong}</strong>
                        {after}
                      </>
                    );
                  })()}
                </p>
              </motion.div>
              <div className='flex items-center gap-3'>
                <div className='relative'>
                  <button
                    onClick={() => setYearOpen((v) => !v)}
                    className='inline-flex min-h-10 items-center gap-2 border border-white/25 bg-transparent px-4 py-2 text-sm font-semibold text-white hover:border-gov-gold'>
                    {t('counties.header.year')}: {selectedYear}
                    <ChevronDown
                      size={14}
                      className={`transition-transform ${yearOpen ? 'rotate-180' : ''}`}
                    />
                  </button>
                  {yearOpen && (
                    <div className='absolute right-0 z-50 mt-1 min-w-[140px] rounded-sm border border-neutral-border bg-surface-elevated py-1 shadow-elevated'>
                      {YEARS.map((y) => (
                        <button
                          key={y}
                          onClick={() => {
                            setSelectedYear(y);
                            setYearOpen(false);
                          }}
                          className={`block w-full text-left px-4 py-2 text-sm transition-colors ${
                            y === selectedYear
                              ? 'bg-gov-forest/10 text-gov-forest dark:text-emerald-100 font-semibold'
                              : 'text-gray-700 dark:text-neutral-muted hover:bg-gray-50 dark:bg-surface-elevated'
                          }`}>
                          {y}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  onClick={handleExport}
                  className='inline-flex min-h-10 items-center gap-2 border border-white/25 bg-transparent px-4 py-2 text-sm font-semibold text-white hover:border-gov-gold'>
                  <Download size={14} />
                  {t('counties.header.export')}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* ═══ Main content ═══ */}
        <div className='max-w-[1400px] mx-auto px-5 lg:px-8 py-8'>
          {/* Data freshness banner */}
          <DataFreshnessBadge sources='COB' variant='banner' className='mb-2' />
          {/* County financials are modelled estimates, not official COB data */}
          <ModelledDataNote className='mb-4' />

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
              className={`flex-shrink-0 ${sidebarCollapsed ? 'w-12' : 'w-[280px]'} hidden transition-[width] lg:block`}>
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
                  fiscalYear={selectedYear}
                />
              </motion.div>
            </div>
          </div>
        </div>

        <DataFreshnessBadge sources='COB' className='mt-4 justify-center' />

        {/* Spacer so bottom scenic image peeks through */}
        <div className='h-24' />
      </div>
    </div>
  );
}
