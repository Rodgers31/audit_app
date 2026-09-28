'use client';

/**
 * Follow the Money — narrative-first redesign.
 *
 * The page now mirrors the Budget and Debt pages:
 *   1. A small intro strip
 *   2. Reporting-period selector drives the entire page
 *   3. MoneyFlowHero — the centrepiece waterfall (Allocated → Spent →
 *      Flagged) with explicit gap callouts between stages
 *   4. Open summary — allocated / unspent / flagged / national efficiency
 *   5. Responsive county comparison list (sortable, searchable)
 *   6. "What can you do" action cards
 *   7. Source reconciliation panel so every figure is traceable to an
 *      official CoB / OAG / CRA document for the chosen fiscal year
 */

import MoneyFlowHero from '@/components/transparency/MoneyFlowHero';
import MoneyFlowSourceReconciliation from '@/components/transparency/MoneyFlowSourceReconciliation';
import MoneyFlowPeriodPicker from '@/components/transparency/MoneyFlowPeriodPicker';
import MoneyFlowOverview from '@/components/transparency/MoneyFlowOverview';
import CountySpendingList from '@/components/transparency/CountySpendingList';
import type {
  CountyFlowRow,
  CountySortKey as SortKey,
} from '@/components/transparency/moneyFlowPresentation';
import PageShell from '@/components/layout/PageShell';
import { useCountyFiscalYears } from '@/lib/react-query';
import { SSR_HYDRATED_STALE_TIME_MS } from '@/lib/react-query/isr';
import { useAllCountiesMoneyFlow, useNationalMoneyFlow } from '@/lib/react-query/useMoneyFlow';
import { transparencyYearOptions } from '@/lib/utils';
import { MoneyFlowData } from '@/types';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  Clock,
  ExternalLink,
  GraduationCap,
  Loader2,
  Users,
} from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';

/* ═══════════ Helpers ═══════════ */

// `fundingImpact()` used to sit here, turning a questioned amount into
// "≈ N schools / classrooms / boreholes / health posts" at KES 10M / 3M /
// 500K / 2M each. No source or vintage could be found for any of the four,
// so it was removed rather than cited (#231). Restore only with a published
// unit cost, its source and its year shown beside the conversion.

/**
 * The calendar year the in-progress Kenyan fiscal year began in (FY runs
 * 1 Jul – 30 Jun). On 2026-09-06 that is 2026, i.e. FY2026/27.
 *
 * This asks which year we are IN, which the calendar can answer. Both callers
 * below ask exactly that. Anything choosing a year to FETCH asks a question
 * about the data instead, and wants `transparencyYearOptions` /
 * `resolveExplorerYear` / `moneyFlowDefaultYear`, which resolve it from
 * GET /api/v1/counties/fiscal-years.
 *
 * Deliberately local and unexported. `getCurrentFiscalYear`,
 * `getLatestReportedFiscalYear` and `generateFiscalYears` were all removed
 * from `@/lib/utils`, because a shared, exported, clock-derived fiscal-year
 * helper is what put four pages on a year the database held no reported
 * figures for. Kept here it answers one page's calendar question and cannot
 * be reached for as a data one; it returns the start YEAR rather than a label
 * so both callers can use it without parsing one back apart.
 */
function currentFiscalStartYear(): number {
  const now = new Date();
  return now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1;
}

/** Convert a raw "YYYY/YY" string into the shape FiscalYearPicker wants.
 *
 * `is_current` drives a pulsing "still running" dot. That is a question about
 * the calendar, not about the data, so it stays on the clock — unlike the
 * DEFAULT year, which is now whatever the API reports it actually holds. */
function toPickerOptions(years: string[]): { fiscal_year: string; is_current?: boolean }[] {
  if (!years || years.length === 0) return [];
  const startYr = currentFiscalStartYear();
  const currentLabel = `${startYr}/${String(startYr + 1).slice(-2)}`;
  return years.map((y) => ({ fiscal_year: y, is_current: y === currentLabel }));
}

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

/* ═══════════ Projected-FY banner ═══════════ */

function MilestoneChip({
  icon,
  label,
  sub,
}: {
  icon: React.ReactNode;
  label: string;
  sub: string;
}) {
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
              Counties have been <strong>allocated</strong> their share of the Equitable Revenue,
              but spending and auditing happen over the full year. Execution figures appear here
              once the <strong>Controller of Budget</strong> publishes each quarterly County Budget
              Implementation Review Report (CBIRR). The <strong>Auditor General</strong> follows
              with findings roughly 18 months after year-end.
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

/* ═══════════ Page ═══════════ */

export default function TransparencyPage() {
  // Years and default both come from /counties/fiscal-years — the periods
  // county budget data actually exists for — not /audits/fiscal-years, which
  // is every FiscalPeriod row. Four of the eight pills this page used to offer
  // (FY2025/26 9M, FY2025/26 H1, FY2021/22, FY2020/21) carry no county budget
  // rows, so clicking them emptied the page. Labels arrive bare ("2024/25") so
  // `selectedYear` and the picker buttons compare equal (F37).
  const { data: fiscalYearsMeta } = useCountyFiscalYears({
    staleTime: SSR_HYDRATED_STALE_TIME_MS,
  });
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
  //
  // Resolved DURING RENDER rather than in an effect. The invariant is the same
  // one the effect enforced — never sit on a year absent from the picker, which
  // covers both "nothing chosen yet" and a year dropped from the list
  // (credibility audit F37) — but an effect cannot run on the server, and it
  // does not run until after the client has mounted. So the first render always
  // asked for `''`, both money-flow queries were `enabled: false`, and the year
  // the server had just prefetched for was unreachable: the page rendered its
  // skeletons, hydrated, and only then went looking for data. Deriving it makes
  // the server's own render ask for the prefetched year (#221 finding #6).
  const [pickedYear, setPickedYear] = useState<string>('');
  const selectedYear = pickedYear && years.includes(pickedYear) ? pickedYear : (defaultYear ?? '');
  const [sortKey, setSortKey] = useState<SortKey>('efficiency');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [searchQuery, setSearchQuery] = useState('');

  const { data: nationalFlow, isLoading: nationalLoading } = useNationalMoneyFlow(selectedYear);
  const {
    data: allCountyFlows,
    isLoading: allCountyFlowsLoading,
    isError: countyFlowsError,
  } = useAllCountiesMoneyFlow(selectedYear);

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
    return allCountyFlows.map((flowData: MoneyFlowData) => {
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
        flagged_amount: flaggedStage?.amount ?? null,
        total_gap: totalGap,
        allocated: allocatedStage?.amount ?? null,
        spent: spentStage?.amount ?? null,
      };
    });
  }, [allCountyFlows]);

  /**
   * "Projected FY" = allocations are known but no execution data has been
   * published yet. We detect this from the data rather than the calendar so
   * that any mid-year CoB release flips the page into full-data mode
   * automatically. Guarded by a year check so a genuinely missing dataset
   * for a closed FY shows the normal empty-state.
   */
  const isProjectedFY = useMemo(() => {
    if (countyRows.length === 0) return false;
    const noSpendData = countyRows.every((r) => r.spent == null);
    if (!noSpendData) return false;
    const startYr = fiscalStartYear(selectedYear);
    if (startYr == null) return false;
    return startYr >= currentFiscalStartYear();
  }, [countyRows, selectedYear]);

  // The comparator and selector must use the same key in either reporting mode.
  const effectiveSortKey: SortKey = isProjectedFY
    ? sortKey === 'name'
      ? 'name'
      : 'allocated'
    : sortKey === 'allocated'
      ? 'efficiency'
      : sortKey;

  const sortedRows = useMemo(() => {
    const sorted = countyRows.filter((row) =>
      row.county_name.toLowerCase().includes(searchQuery.trim().toLowerCase())
    );
    sorted.sort((a, b) => {
      let cmp = 0;
      switch (effectiveSortKey) {
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
  }, [countyRows, searchQuery, effectiveSortKey, sortDir]);

  const countiesWithData = countyRows.filter((row) => row.allocated != null).length;
  // Coverage, projected-year mode, and allocation shares describe the whole
  // reporting period; filtering the list must not change those figures.
  const countyAllocationTotal = countyRows.reduce(
    // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- reducer accumulator
    (total, row) => total + (row.allocated ?? 0),
    0
  );

  return (
    <PageShell
      title='Follow the Money'
      subtitle='Trace every shilling from the Treasury to citizens — and see what the Auditor-General has questioned.'>
      {/* ═══ 1. Narrative intro ═══ */}
      <Section>
        <div className='max-w-3xl'>
          <p className='text-base text-gov-dark/70 dark:text-white/70 leading-relaxed'>
            Every year, the Treasury allocates trillions of shillings to Kenya&apos;s 47 counties.
            But how much actually reaches citizens? The waterfall below traces the journey — from
            what was <strong>allocated</strong> to the counties, to what they actually{' '}
            <strong>spent</strong>, to the portion the Auditor General
            <strong> questioned</strong> as irregular or unsupported.
          </p>
        </div>
      </Section>

      {/* ═══ 2. Fiscal year picker drives the page ═══ */}
      <Section delay={0.05}>
        <MoneyFlowPeriodPicker
          years={pickerYears}
          selected={selectedYear}
          onSelect={setPickedYear}
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

      {/* ═══ 4. National summary ═══ */}
      {insights && insights.allocated != null && insights.allocated > 0 && (
        <Section delay={0.12}>
          <MoneyFlowOverview
            insights={insights}
            fiscalYear={stripFY(selectedYear)}
            projected={isProjectedFY}
          />
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
        <CountySpendingList
          rows={sortedRows}
          fiscalYear={stripFY(selectedYear)}
          countiesWithData={countiesWithData}
          nationalEfficiency={insights?.efficiency ?? null}
          nationalAllocated={countyAllocationTotal}
          projected={isProjectedFY}
          loading={allCountyFlowsLoading}
          error={countyFlowsError}
          auditUnavailable={
            countyRows.length > 0 && countyRows.every((row) => row.flagged_amount == null)
          }
          search={searchQuery}
          onSearch={setSearchQuery}
          sortKey={effectiveSortKey}
          reversed={sortDir === 'desc'}
          onSort={(key) => {
            setSortKey(key);
            setSortDir('asc');
          }}
          onReverse={() => setSortDir((direction) => (direction === 'asc' ? 'desc' : 'asc'))}
        />
      </Section>

      {/* ═══ 6. Source reconciliation ═══ */}
      <Section delay={0.18}>
        <MoneyFlowSourceReconciliation
          fiscalYear={selectedYear}
          budgetSource={nationalFlow?.budget_source}
        />
      </Section>

      {/* ═══ 7. What can you do? ═══ */}
      <Section delay={0.22}>
        <div className='rounded-2xl bg-gradient-to-br from-gov-forest/5 to-gov-sage/5 border border-gov-forest/10 p-6 sm:p-8'>
          <h2 className='font-display text-xl text-gov-dark dark:text-white mb-2'>
            What can you do?
          </h2>
          <p className='text-sm text-gov-dark/60 dark:text-white/60 mb-5 max-w-2xl'>
            Public-money transparency isn&apos;t just data — it&apos;s accountability. Here&apos;s
            how to turn these numbers into action.
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
