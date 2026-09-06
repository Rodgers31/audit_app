'use client';

/**
 * Follow the Money — narrative-first redesign.
 *
 * The page now mirrors the Budget and Debt pages:
 *   1. A small intro strip
 *   2. FiscalYearPicker drives the entire page
 *   3. MoneyFlowHero — the centrepiece waterfall (Allocated → Released →
 *      Spent → Flagged) with explicit gap callouts between stages
 *   4. KPI cards — allocated / unspent / flagged / national efficiency
 *   5. County comparison table (sortable, searchable)
 *   6. "What can you do" action cards
 *   7. Source reconciliation panel so every figure is traceable to an
 *      official CoB / OAG / CRA document for the chosen fiscal year
 */

import MoneyFlowHero from '@/components/transparency/MoneyFlowHero';
import MoneyFlowSourceReconciliation from '@/components/transparency/MoneyFlowSourceReconciliation';
import FiscalYearPicker from '@/components/budget/FiscalYearPicker';
import PageShell from '@/components/layout/PageShell';
import ResponsiveTable from '@/components/ui/ResponsiveTable';
import { useCountyFiscalYears } from '@/lib/react-query';
import { useAllCountiesMoneyFlow, useNationalMoneyFlow } from '@/lib/react-query/useMoneyFlow';
import { getCurrentFiscalYear, transparencyYearOptions } from '@/lib/utils';
import { MoneyFlowData } from '@/types';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpDown,
  CalendarClock,
  Clock,
  ExternalLink,
  GraduationCap,
  Loader2,
  Search,
  Users,
} from 'lucide-react';
import Link from 'next/link';
import { useEffect, useCallback, useMemo, useState } from 'react';

/* ═══════════ Helpers ═══════════ */

function fmtKES(n: number | null | undefined): string {
  if (n == null || n === 0) return 'KES 0';
  const abs = Math.abs(n);
  if (abs >= 1e12) return `KES ${(n / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `KES ${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `KES ${(n / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `KES ${(n / 1e3).toFixed(0)}K`;
  return `KES ${n.toLocaleString()}`;
}

function fundingImpact(amount: number): string {
  if (amount >= 5e9) return `${Math.floor(amount / 10e6)} schools`;
  if (amount >= 1e9) return `${Math.floor(amount / 3e6)} classrooms`;
  if (amount >= 100e6) return `${Math.floor(amount / 500e3)} boreholes`;
  if (amount >= 10e6) return `${Math.floor(amount / 2e6)} health posts`;
  return '';
}

/** Convert a raw "YYYY/YY" string into the shape FiscalYearPicker wants.
 *
 * `is_current` drives a pulsing "still running" dot. That is a question about
 * the calendar, not about the data, so it stays on the clock — unlike the
 * DEFAULT year, which is now whatever the API reports it actually holds. */
function toPickerOptions(years: string[]): { fiscal_year: string; is_current?: boolean }[] {
  if (!years || years.length === 0) return [];
  const currentLabel = getCurrentFiscalYear();
  return years.map((y) => ({ fiscal_year: y, is_current: y === currentLabel }));
}

type SortKey = 'efficiency' | 'flagged' | 'gap' | 'name' | 'allocated';
type SortDir = 'asc' | 'desc';

/** Strip an optional "FY " prefix so we always operate on "YYYY/YY". */
function stripFY(label: string): string {
  return (label || '').replace(/^FY\s*/i, '').trim();
}

/** Parse the starting calendar year out of a fiscal-year label. */
function fiscalStartYear(label: string): number | null {
  const parts = stripFY(label).split('/');
  const y = parseInt(parts[0], 10);
  return Number.isNaN(y) ? null : y;
}

/**
 * Publication milestones for a projected FY.
 *
 * The Kenyan calendar: fiscal year starts 1 Jul and ends 30 Jun. The
 * Controller of Budget publishes quarterly County Budget Implementation
 * Review Reports (CBIRRs) roughly 2 months after each quarter closes, and
 * an annual consolidated CBIRR about 3-4 months after year-end. OAG then
 * audits the closed year, typically releasing findings ~18 months after
 * year-end.
 */
function projectedFYMilestones(label: string) {
  const startYr = fiscalStartYear(label);
  if (startYr == null) return null;
  return {
    firstQuarter: `Q1 CBIRR — expected Nov ${startYr}`,
    annual: `Annual CBIRR — expected Oct ${startYr + 1}`,
    audit: `OAG audit — expected Dec ${startYr + 2}`,
  };
}

/* ═══════════ Animation Wrapper ═══════════ */

function Section({
  children,
  delay = 0,
  className = '',
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.4, delay }}
      className={className}>
      {children}
    </motion.div>
  );
}

/* ═══════════ County Row Type ═══════════ */

interface CountyFlowRow {
  county_id: string;
  county_name: string;
  efficiency_score: number | null;
  flagged_amount: number | null;
  total_gap: number;
  allocated: number | null;
  spent: number | null;
}

/* ═══════════ Projected-FY banner ═══════════ */

function MilestoneChip({ icon, label, sub }: { icon: React.ReactNode; label: string; sub: string }) {
  return (
    <div className='rounded-xl bg-white/70 dark:bg-surface-elevated border border-amber-200/50 px-3 py-2 flex items-start gap-2'>
      <div className='flex-shrink-0 mt-0.5 text-amber-700'>{icon}</div>
      <div className='min-w-0'>
        <p className='text-[11px] font-semibold text-amber-900/60 uppercase tracking-wider'>
          {label}
        </p>
        <p className='text-xs text-amber-900 font-medium mt-0.5 truncate'>{sub}</p>
      </div>
    </div>
  );
}

function ProjectedFYBanner({ yearLabel }: { yearLabel: string }) {
  const milestones = projectedFYMilestones(yearLabel);
  const clean = stripFY(yearLabel);
  return (
    <div className='rounded-2xl border border-amber-200/60 bg-gradient-to-br from-amber-50/70 to-white p-5 sm:p-6'>
      <div className='flex items-start gap-4'>
        <div className='flex-shrink-0 w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center'>
          <Clock className='w-5 h-5 text-amber-700' />
        </div>
        <div className='flex-1 min-w-0 space-y-3'>
          <div>
            <h3 className='font-display text-base sm:text-lg text-amber-900'>
              FY {clean} is still executing
            </h3>
            <p className='text-sm text-amber-900/80 leading-relaxed mt-1'>
              Counties have been <strong>allocated</strong> their share of the Equitable
              Revenue, but spending and auditing happen over the full year. Execution
              figures appear here once the <strong>Controller of Budget</strong> publishes
              each quarterly County Budget Implementation Review Report (CBIRR). The{' '}
              <strong>Auditor General</strong> follows with findings roughly 18 months
              after year-end.
            </p>
          </div>
          {milestones && (
            <div className='grid grid-cols-1 sm:grid-cols-3 gap-2'>
              <MilestoneChip
                icon={<CalendarClock size={14} />}
                label='Next release'
                sub={milestones.firstQuarter}
              />
              <MilestoneChip
                icon={<CalendarClock size={14} />}
                label='Annual review'
                sub={milestones.annual}
              />
              <MilestoneChip
                icon={<AlertTriangle size={14} />}
                label='Audit findings'
                sub={milestones.audit}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ═══════════ Mini Efficiency Bar ═══════════ */

function EfficiencyBar({ score }: { score: number }) {
  const color = score >= 70 ? 'bg-emerald-500' : score >= 50 ? 'bg-amber-500' : 'bg-red-500';
  const textColor =
    score >= 70 ? 'text-emerald-700' : score >= 50 ? 'text-amber-700' : 'text-red-700';
  return (
    <div className='flex items-center gap-2 min-w-[120px]'>
      <div className='flex-1 h-2 bg-gray-100 dark:bg-surface-elevated rounded-full overflow-hidden'>
        <motion.div
          initial={{ width: 0 }}
          whileInView={{ width: `${Math.min(score, 100)}%` }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className={`h-full rounded-full ${color}`}
        />
      </div>
      <span className={`text-xs font-bold tabular-nums w-10 text-right ${textColor}`}>
        {score.toFixed(0)}%
      </span>
    </div>
  );
}

/* ═══════════ Page ═══════════ */

export default function TransparencyPage() {
  // Years and default both come from /counties/fiscal-years — the periods
  // county budget data actually exists for — not /audits/fiscal-years, which
  // is every FiscalPeriod row. Four of the eight pills this page used to offer
  // (FY2025/26 9M, FY2025/26 H1, FY2021/22, FY2020/21) carry no county budget
  // rows, so clicking them emptied the page. Labels arrive bare ("2024/25") so
  // `selectedYear` and the picker buttons compare equal (F37).
  const { data: fiscalYearsMeta } = useCountyFiscalYears();
  const { years, default: defaultYear } = useMemo(
    () => transparencyYearOptions(fiscalYearsMeta),
    [fiscalYearsMeta]
  );
  const pickerYears = useMemo(() => toPickerOptions(years), [years]);

  // Land on a year the picker actually offers.
  //
  // The default used to be the wall-clock "current FY" — 2026/27 in September
  // 2026, a year in no list at all — so the page fired two money-flow requests
  // for a year with nothing behind it before correcting to years[0], the CRA
  // projection. It now waits for the API's own answer and asks once.
  const [selectedYear, setSelectedYear] = useState<string>('');
  useEffect(() => {
    // Correct the selection whenever it is not one of the years the picker
    // offers — which covers both "nothing chosen yet" and a year dropped from
    // the list. Seeding on first render alone left the page parked on a year
    // absent from its own picker, no pill highlighted, "No data yet" body
    // (credibility audit F37).
    if (!defaultYear) return;
    if (!selectedYear || !years.includes(selectedYear)) {
      setSelectedYear(defaultYear);
    }
  }, [selectedYear, defaultYear, years]);
  const [sortKey, setSortKey] = useState<SortKey>('efficiency');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [searchQuery, setSearchQuery] = useState('');

  const { data: nationalFlow, isLoading: nationalLoading } = useNationalMoneyFlow(selectedYear);
  const { data: allCountyFlows, isLoading: allCountyFlowsLoading } =
    useAllCountiesMoneyFlow(selectedYear);

  /* ── Derived national insights ── */
  //
  // Nothing here falls back to 0. The Flagged stage in particular: the
  // waterfall correctly said "OAG audit report not yet published for this
  // year — data unavailable", and the KPI beside it turned the same null into
  // "KES 0 — No flagged findings", exonerating 47 county governments on the
  // strength of a report nobody has read (credibility audit F22).
  const insights = useMemo(() => {
    if (!nationalFlow?.stages) return null;
    const amountOf = (stage: string) =>
      nationalFlow.stages.find((s) => s.stage === stage)?.amount ?? null;
    const allocated = amountOf('Allocated');
    const spent = amountOf('Spent');
    const flagged = amountOf('Flagged');
    const gap = allocated != null && spent != null ? allocated - spent : null;
    const unspentPct =
      gap != null && allocated != null && allocated > 0 ? (gap / allocated) * 100 : null;
    return {
      allocated,
      spent,
      flagged,
      gap,
      unspentPct,
      efficiency: nationalFlow.efficiency_score ?? null,
    };
  }, [nationalFlow]);

  /* ── County rows ── */
  const countyRows: CountyFlowRow[] = useMemo(() => {
    if (!allCountyFlows || allCountyFlows.length === 0) return [];
    return allCountyFlows
      .map((flowData: MoneyFlowData) => {
        const flaggedStage = flowData.stages?.find((s) => s.stage === 'Flagged');
        const allocatedStage = flowData.stages?.find((s) => s.stage === 'Allocated');
        const spentStage = flowData.stages?.find((s) => s.stage === 'Spent');
        const totalGap = (flowData.stages || []).reduce(
          (sum, s) => sum + (s.gap_from_prev && s.gap_from_prev > 0 ? s.gap_from_prev : 0),
          0
        );
        return {
          county_id: String(flowData.county_id),
          county_name: (flowData.county_name || '').replace(' County', ''),
          efficiency_score: flowData.efficiency_score ?? null,
          flagged_amount: flaggedStage?.amount || null,
          total_gap: totalGap,
          allocated: allocatedStage?.amount || null,
          spent: spentStage?.amount || null,
        };
      })
      .filter((row) => {
        if (!searchQuery) return true;
        return row.county_name.toLowerCase().includes(searchQuery.toLowerCase());
      });
  }, [allCountyFlows, searchQuery]);

  /**
   * "Projected FY" = allocations are known but no execution data has been
   * published yet. We detect this from the data rather than the calendar so
   * that any mid-year CoB release flips the page into full-data mode
   * automatically. Guarded by a year check so a genuinely missing dataset
   * for a closed FY shows the normal empty-state.
   */
  const isProjectedFY = useMemo(() => {
    if (countyRows.length === 0) return false;
    const noSpendData = countyRows.every((r) => r.spent == null || r.spent === 0);
    if (!noSpendData) return false;
    const startYr = fiscalStartYear(selectedYear);
    if (startYr == null) return false;
    const now = new Date();
    const currentStartYr = now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1;
    return startYr >= currentStartYr;
  }, [countyRows, selectedYear]);

  const sortedRows = useMemo(() => {
    const sorted = [...countyRows];
    // In projected mode the efficiency/flagged/gap keys have no data to
    // compare — fall back to sorting by allocation so the table still shows
    // something coherent.
    const effectiveKey: SortKey =
      isProjectedFY && (sortKey === 'efficiency' || sortKey === 'flagged' || sortKey === 'gap')
        ? 'allocated'
        : sortKey;
    sorted.sort((a, b) => {
      let cmp = 0;
      switch (effectiveKey) {
        case 'name':
          cmp = a.county_name.localeCompare(b.county_name);
          break;
        case 'efficiency':
          cmp = (a.efficiency_score ?? 999) - (b.efficiency_score ?? 999);
          break;
        case 'flagged':
          // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- sort comparator
          cmp = (b.flagged_amount ?? 0) - (a.flagged_amount ?? 0);
          break;
        case 'gap':
          cmp = b.total_gap - a.total_gap;
          break;
        case 'allocated':
          // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- sort comparator
          cmp = (b.allocated ?? 0) - (a.allocated ?? 0);
          break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return sorted;
  }, [countyRows, sortKey, sortDir, isProjectedFY]);

  const toggleSort = useCallback(
    (key: SortKey) => {
      if (sortKey === key) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortKey(key);
        setSortDir(key === 'name' ? 'asc' : 'asc');
      }
    },
    [sortKey]
  );

  const countiesWithData = countyRows.filter((r) => r.allocated != null).length;

  const SortHeader = ({ label, field }: { label: string; field: SortKey }) => (
    <th
      className='py-3 pr-3 font-semibold text-gov-dark/60 dark:text-white/60 text-xs uppercase tracking-wider cursor-pointer select-none group'
      onClick={() => toggleSort(field)}>
      <span className='inline-flex items-center gap-1'>
        {label}
        <ArrowUpDown
          size={11}
          className={`transition-colors ${
            sortKey === field ? 'text-gov-forest dark:text-emerald-100' : 'text-gray-300 dark:text-neutral-muted/60 group-hover:text-gray-400 dark:text-neutral-muted/80'
          }`}
        />
      </span>
    </th>
  );

  return (
    <PageShell
      title='Follow the Money'
      subtitle='Trace every shilling from the Treasury to citizens — and see what the Auditor-General has questioned.'>
      {/* ═══ 1. Narrative intro ═══ */}
      <Section>
        <div className='max-w-3xl'>
          <p className='text-base text-gov-dark/70 dark:text-white/70 leading-relaxed'>
            Every year, the Treasury allocates trillions of shillings to Kenya&apos;s 47
            counties. But how much actually reaches citizens? The waterfall below traces
            the journey — from <strong>allocation</strong> by the Commission on Revenue
            Allocation, to <strong>release</strong> by the Exchequer, to what counties
            actually <strong>spent</strong>, to the portion the Auditor General
            <strong> questioned</strong> as irregular or unsupported.
          </p>
        </div>
      </Section>

      {/* ═══ 2. Fiscal year picker drives the page ═══ */}
      <Section delay={0.05}>
        <FiscalYearPicker
          years={pickerYears}
          selected={selectedYear}
          onSelect={setSelectedYear}
        />
      </Section>

      {/* ═══ 3. The waterfall hero ═══ */}
      <Section delay={0.08}>
        {nationalLoading ? (
          <div className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-16 flex items-center justify-center'>
            <Loader2 className='w-6 h-6 animate-spin text-gov-sage' />
            <span className='ml-3 text-gov-dark/60 dark:text-white/60 font-medium'>
              Loading money-flow waterfall…
            </span>
          </div>
        ) : (
          <MoneyFlowHero data={nationalFlow} />
        )}
      </Section>

      {/* ═══ 4. KPI cards ═══ */}
      {insights && insights.allocated != null && insights.allocated > 0 && (
        <Section delay={0.12}>
          <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4'>
            <InsightCard
              label='Total allocated'
              value={fmtKES(insights.allocated)}
              sublabel={`47 counties · FY ${stripFY(selectedYear)}`}
              accent='blue'
            />
            <InsightCard
              label={isProjectedFY ? 'Spent so far' : 'Gap to spend'}
              value={
                isProjectedFY
                  ? 'Pending'
                  : insights.gap != null
                    ? fmtKES(insights.gap)
                    : '—'
              }
              sublabel={
                isProjectedFY
                  ? 'Execution figures publish as the CoB releases quarterly CBIRRs'
                  : insights.unspentPct != null
                    ? `${insights.unspentPct.toFixed(1)}% of allocation unspent at report time`
                    : 'Execution not yet published for this period'
              }
              accent={isProjectedFY ? 'gray' : 'amber'}
            />
            <InsightCard
              label='Questioned by Auditor General'
              value={
                isProjectedFY
                  ? 'Not yet audited'
                  : insights.flagged != null
                    ? fmtKES(insights.flagged)
                    : 'Not yet published'
              }
              sublabel={
                isProjectedFY
                  ? 'OAG audits close ~18 months after year-end'
                  : insights.flagged == null
                    ? 'No Auditor-General report for this year traces to a source document yet. This is not a finding that nothing was questioned.'
                    : insights.flagged > 0
                      ? `≈ ${fundingImpact(insights.flagged) || 'irregular expenditure'}`
                      : 'The published report questioned no amount for this period'
              }
              accent={isProjectedFY ? 'gray' : 'red'}
            />
            <InsightCard
              label='National efficiency'
              value={
                isProjectedFY
                  ? '—'
                  : insights.efficiency != null
                    ? `${insights.efficiency.toFixed(1)}%`
                    : '—'
              }
              sublabel={
                isProjectedFY
                  ? 'Calculated once CoB + OAG publish'
                  : insights.efficiency != null
                    ? insights.efficiency >= 70
                      ? 'Good — above target'
                      : insights.efficiency >= 50
                        ? 'Fair — needs improvement'
                        : 'Poor — significant waste'
                    : 'Execution data pending'
              }
              accent={
                isProjectedFY
                  ? 'gray'
                  : insights.efficiency != null
                    ? insights.efficiency >= 70
                      ? 'green'
                      : insights.efficiency >= 50
                        ? 'amber'
                        : 'red'
                    : 'gray'
              }
            />
          </div>
        </Section>
      )}

      {/* ═══ 4b. Projected-FY explainer (shown when no execution data yet) ═══ */}
      {isProjectedFY && (
        <Section delay={0.14}>
          <ProjectedFYBanner yearLabel={selectedYear} />
        </Section>
      )}

      {/* ═══ 5. County comparison ═══ */}
      <Section delay={0.15}>
        <div className='space-y-4'>
          <div className='flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3'>
            <div>
              <h2 className='font-display text-xl text-gov-dark dark:text-white'>County-by-county breakdown</h2>
              <p className='text-sm text-gov-dark/50 dark:text-white/50'>
                {countiesWithData > 0
                  ? isProjectedFY
                    ? `${countiesWithData} of 47 counties have published allocations for FY ${stripFY(
                        selectedYear,
                      )} — execution figures pending`
                    : `${countiesWithData} of 47 counties have CoB + OAG data for FY ${stripFY(
                        selectedYear,
                      )}`
                  : 'Loading county data…'}
              </p>
            </div>
            <div className='relative'>
              <Search
                size={14}
                className='absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-neutral-muted/80'
              />
              <input
                type='text'
                placeholder='Search county…'
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className='pl-8 pr-3 py-2 text-sm rounded-xl border border-gray-200 dark:border-neutral-border bg-white/80 dark:bg-surface-elevated focus:outline-none focus:ring-2 focus:ring-gov-sage/30 focus:border-gov-sage w-60'
              />
            </div>
          </div>

          <div className='flex flex-wrap gap-2'>
            {(isProjectedFY
              ? [
                  { key: 'allocated' as SortKey, label: 'Largest allocation' },
                  { key: 'name' as SortKey, label: 'A–Z' },
                ]
              : [
                  { key: 'efficiency' as SortKey, label: 'Least efficient' },
                  { key: 'flagged' as SortKey, label: 'Most flagged' },
                  { key: 'gap' as SortKey, label: 'Highest gap' },
                  { key: 'name' as SortKey, label: 'A–Z' },
                ]
            ).map((btn) => (
              <button
                key={btn.key}
                onClick={() => toggleSort(btn.key)}
                className={`text-xs px-3 py-1.5 rounded-full transition-all ${
                  sortKey === btn.key
                    ? 'bg-gov-forest text-white shadow-sm'
                    : 'bg-white/60 dark:bg-surface-elevated text-gov-dark/60 dark:text-white/60 hover:bg-white dark:bg-surface-base border border-gray-200/60 dark:border-neutral-border/60'
                }`}>
                {btn.label}
              </button>
            ))}
          </div>

          {allCountyFlowsLoading ? (
            <div className='flex items-center justify-center py-20'>
              <Loader2 className='w-6 h-6 animate-spin text-gov-sage' />
              <span className='ml-3 text-gov-dark/60 dark:text-white/60 font-medium'>Loading county data…</span>
            </div>
          ) : isProjectedFY ? (
            <ResponsiveTable bleed>
              <div className='rounded-xl border border-gray-200/60 dark:border-neutral-border/60 bg-white/60 dark:bg-surface-elevated'>
                <table className='w-full text-sm'>
                  <thead>
                    <tr className='border-b border-gray-200 dark:border-neutral-border bg-gray-50/50 dark:bg-surface-elevated/70 text-left'>
                      <th className='py-3 pl-4 pr-3 font-semibold text-gov-dark/60 dark:text-white/60 text-xs uppercase tracking-wider w-8'>
                        #
                      </th>
                      <SortHeader label='County' field='name' />
                      <SortHeader label='Allocated' field='allocated' />
                      <th className='py-3 pr-3 font-semibold text-gov-dark/60 dark:text-white/60 text-xs uppercase tracking-wider'>
                        Share of national pot
                      </th>
                      <th className='py-3 pr-4 font-semibold text-gov-dark/60 dark:text-white/60 text-xs uppercase tracking-wider'>
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(() => {
                      const nationalAllocated =
                        // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- reducer accumulator
                        countyRows.reduce((s, r) => s + (r.allocated ?? 0), 0) || 0;
                      return sortedRows.map((row, i) => {
                        const share =
                          nationalAllocated > 0 && row.allocated != null
                            ? (row.allocated / nationalAllocated) * 100
                            : null;
                        return (
                          <tr
                            key={row.county_id}
                            className={`border-b border-gray-100 dark:border-neutral-border hover:bg-gov-forest/[0.04] transition-colors ${
                              i % 2 === 0 ? 'bg-white/40 dark:bg-surface-elevated' : 'bg-gray-50/30 dark:bg-surface-elevated/70'
                            }`}>
                            <td className='py-3 pl-4 pr-3 text-gov-dark/30 dark:text-white/30 font-mono text-xs'>
                              {i + 1}
                            </td>
                            <td className='py-3 pr-3'>
                              <Link
                                href={`/counties/${row.county_id}?tab=money&from=transparency`}
                                className='text-gov-forest dark:text-emerald-100 font-medium hover:underline decoration-gov-sage/30 underline-offset-2'>
                                {row.county_name}
                              </Link>
                            </td>
                            <td className='py-3 pr-3 font-mono text-xs text-gov-dark/80 dark:text-white/80'>
                              {row.allocated != null ? fmtKES(row.allocated) : '—'}
                            </td>
                            <td className='py-3 pr-3'>
                              {share != null ? (
                                <div className='flex items-center gap-2 min-w-[140px]'>
                                  <div className='flex-1 h-1.5 bg-gray-100 dark:bg-surface-elevated rounded-full overflow-hidden'>
                                    <motion.div
                                      initial={{ width: 0 }}
                                      whileInView={{ width: `${Math.min(share * 4, 100)}%` }}
                                      viewport={{ once: true }}
                                      transition={{ duration: 0.6, ease: 'easeOut' }}
                                      className='h-full rounded-full bg-gov-sage/70'
                                    />
                                  </div>
                                  <span className='text-xs font-mono text-gov-dark/50 dark:text-white/50 w-10 text-right'>
                                    {share.toFixed(1)}%
                                  </span>
                                </div>
                              ) : (
                                <span className='text-gray-300 dark:text-neutral-muted/60 text-xs'>—</span>
                              )}
                            </td>
                            <td className='py-3 pr-4'>
                              <span className='inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-50 border border-amber-200/60 text-[11px] font-medium text-amber-800'>
                                <Clock size={11} />
                                Execution pending
                              </span>
                            </td>
                          </tr>
                        );
                      });
                    })()}
                  </tbody>
                </table>
              </div>
            </ResponsiveTable>
          ) : (
            <ResponsiveTable bleed>
              <div className='rounded-xl border border-gray-200/60 dark:border-neutral-border/60 bg-white/60 dark:bg-surface-elevated'>
                <table className='w-full text-sm'>
                  <thead>
                    <tr className='border-b border-gray-200 dark:border-neutral-border bg-gray-50/50 dark:bg-surface-elevated/70 text-left'>
                      <th className='py-3 pl-4 pr-3 font-semibold text-gov-dark/60 dark:text-white/60 text-xs uppercase tracking-wider w-8'>
                        #
                      </th>
                      <SortHeader label='County' field='name' />
                      <th className='py-3 pr-3 font-semibold text-gov-dark/60 dark:text-white/60 text-xs uppercase tracking-wider text-right'>
                        Allocated
                      </th>
                      <th className='py-3 pr-3 font-semibold text-gov-dark/60 dark:text-white/60 text-xs uppercase tracking-wider text-right'>
                        Spent
                      </th>
                      <SortHeader label='Efficiency' field='efficiency' />
                      <SortHeader label='Flagged' field='flagged' />
                      <SortHeader label='Gap' field='gap' />
                      <th className='py-3 pr-4 font-semibold text-gov-dark/60 dark:text-white/60 text-xs uppercase tracking-wider hidden lg:table-cell'>
                        Impact
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedRows.map((row, i) => {
                      const impact = row.flagged_amount ? fundingImpact(row.flagged_amount) : '';
                      return (
                        <tr
                          key={row.county_id}
                          className={`border-b border-gray-100 dark:border-neutral-border hover:bg-gov-forest/[0.04] transition-colors ${
                            i % 2 === 0 ? 'bg-white/40 dark:bg-surface-elevated' : 'bg-gray-50/30 dark:bg-surface-elevated/70'
                          }`}>
                          <td className='py-3 pl-4 pr-3 text-gov-dark/30 dark:text-white/30 font-mono text-xs'>
                            {i + 1}
                          </td>
                          <td className='py-3 pr-3'>
                            <Link
                              href={`/counties/${row.county_id}?tab=money&from=transparency`}
                              className='text-gov-forest dark:text-emerald-100 font-medium hover:underline decoration-gov-sage/30 underline-offset-2'>
                              {row.county_name}
                            </Link>
                          </td>
                          <td className='py-3 pr-3 text-right font-mono text-xs text-gov-dark/70 dark:text-white/70'>
                            {row.allocated != null ? fmtKES(row.allocated) : '—'}
                          </td>
                          <td className='py-3 pr-3 text-right font-mono text-xs text-gov-dark/70 dark:text-white/70'>
                            {row.spent != null ? fmtKES(row.spent) : '—'}
                          </td>
                          <td className='py-3 pr-3'>
                            {row.efficiency_score != null ? (
                              <EfficiencyBar score={row.efficiency_score} />
                            ) : (
                              <span className='text-gray-300 dark:text-neutral-muted/60 text-xs'>—</span>
                            )}
                          </td>
                          <td className='py-3 pr-3 text-right'>
                            {row.flagged_amount != null && row.flagged_amount > 0 ? (
                              <span className='font-mono text-xs text-red-600 font-medium'>
                                {fmtKES(row.flagged_amount)}
                              </span>
                            ) : (
                              <span className='text-gray-300 dark:text-neutral-muted/60 text-xs'>—</span>
                            )}
                          </td>
                          <td className='py-3 pr-3 text-right'>
                            {row.total_gap > 0 ? (
                              <span className='font-mono text-xs text-amber-600'>
                                {fmtKES(row.total_gap)}
                              </span>
                            ) : (
                              <span className='text-gray-300 dark:text-neutral-muted/60 text-xs'>—</span>
                            )}
                          </td>
                          <td className='py-3 pr-4 hidden lg:table-cell'>
                            {impact && (
                              <span className='text-[11px] text-gov-dark/40 dark:text-white/40 italic'>
                                ≈ {impact}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </ResponsiveTable>
          )}

          {!allCountyFlowsLoading && sortedRows.length === 0 && (
            <div className='text-center py-12 text-gov-dark/40 dark:text-white/40'>
              {searchQuery
                ? 'No counties match your search.'
                : 'No data available for this fiscal year.'}
            </div>
          )}
        </div>
      </Section>

      {/* ═══ 6. Source reconciliation ═══ */}
      <Section delay={0.18}>
        <MoneyFlowSourceReconciliation fiscalYear={selectedYear} />
      </Section>

      {/* ═══ 7. What can you do? ═══ */}
      <Section delay={0.22}>
        <div className='rounded-2xl bg-gradient-to-br from-gov-forest/5 to-gov-sage/5 border border-gov-forest/10 p-6 sm:p-8'>
          <h2 className='font-display text-xl text-gov-dark dark:text-white mb-2'>What can you do?</h2>
          <p className='text-sm text-gov-dark/60 dark:text-white/60 mb-5 max-w-2xl'>
            Public-money transparency isn&apos;t just data — it&apos;s accountability.
            Here&apos;s how to turn these numbers into action.
          </p>
          <div className='grid grid-cols-1 sm:grid-cols-3 gap-4'>
            <ActionCard
              icon={<Users size={20} />}
              title='Explore your county'
              description='See how your county spends public money — budget, audit findings, and accountability grade.'
              href='/counties'
              linkText='County Explorer'
            />
            <ActionCard
              icon={<AlertTriangle size={20} />}
              title='Read the audit reports'
              description='The Office of the Auditor General publishes a full report for every county each year.'
              href='https://www.oagkenya.go.ke'
              linkText='OAG website'
              external
            />
            <ActionCard
              icon={<GraduationCap size={20} />}
              title='Learn how it works'
              description='Understand how public finance works in Kenya — budgets, audits, and devolution.'
              href='/learn'
              linkText='Learning Hub'
            />
          </div>
        </div>
      </Section>
    </PageShell>
  );
}

/* ═══════════ Sub-Components ═══════════ */

function InsightCard({
  label,
  value,
  sublabel,
  accent,
}: {
  label: string;
  value: string;
  sublabel: string;
  accent: 'blue' | 'amber' | 'red' | 'green' | 'gray';
}) {
  const styles = {
    blue: 'bg-blue-50/80 border-blue-200/50 text-blue-900',
    amber: 'bg-amber-50/80 border-amber-200/50 text-amber-900',
    red: 'bg-red-50/80 border-red-200/50 text-red-900',
    green: 'bg-emerald-50/80 border-emerald-200/50 text-emerald-900',
    gray: 'bg-gray-50/80 dark:bg-surface-elevated/70 border-gray-200/50 dark:border-neutral-border/50 text-gray-700 dark:text-neutral-muted',
  };
  return (
    <div className={`rounded-xl border p-4 transition-shadow hover:shadow-md ${styles[accent]}`}>
      <div className='text-[11px] font-semibold uppercase tracking-wider opacity-60 mb-1'>
        {label}
      </div>
      <div className='font-display text-2xl font-bold tracking-tight tabular-nums'>{value}</div>
      <div className='text-xs mt-1 opacity-50'>{sublabel}</div>
    </div>
  );
}

function ActionCard({
  icon,
  title,
  description,
  href,
  linkText,
  external,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  href: string;
  linkText: string;
  external?: boolean;
}) {
  const Comp = external ? 'a' : Link;
  const extraProps = external ? { target: '_blank', rel: 'noopener noreferrer' } : {};
  return (
    <div className='bg-white/60 dark:bg-surface-elevated rounded-xl border border-white/80 p-4 space-y-2 hover:shadow-sm transition-shadow'>
      <div className='w-9 h-9 rounded-lg bg-gov-forest/10 flex items-center justify-center text-gov-forest dark:text-emerald-100'>
        {icon}
      </div>
      <h3 className='font-semibold text-gov-dark dark:text-white text-sm'>{title}</h3>
      <p className='text-xs text-gov-dark/50 dark:text-white/50 leading-relaxed'>{description}</p>
      <Comp
        href={href}
        className='inline-flex items-center gap-1 text-xs font-medium text-gov-sage hover:text-gov-forest dark:text-emerald-100 transition-colors'
        {...extraProps}>
        {linkText}
        {external ? <ExternalLink size={11} /> : <ArrowRight size={11} />}
      </Comp>
    </div>
  );
}
