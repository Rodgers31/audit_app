'use client';

import MoneyFlowHero, { nationalSpendingSummary } from '@/components/transparency/MoneyFlowHero';
import MoneyFlowSourceReconciliation from '@/components/transparency/MoneyFlowSourceReconciliation';
import MoneyFlowPeriodPicker from '@/components/transparency/MoneyFlowPeriodPicker';
import MoneyFlowOverview from '@/components/transparency/MoneyFlowOverview';
import CountySpendingList from '@/components/transparency/CountySpendingList';
import {
  countyDistributionPoints,
  isProjectedMoneyFlow,
  nationalDistributionGuide,
} from '@/components/transparency/moneyFlowPresentation';
import type {
  CountyFlowRow,
  CountySortKey as SortKey,
} from '@/components/transparency/moneyFlowPresentation';
import PageShell from '@/components/layout/PageShell';
import { useLang } from '@/lib/i18n/LangProvider';
import { nationalSpendingMessages } from '@/lib/i18n/messages/transparency';
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

  const { lang } = useLang();
  const {
    data: nationalFlow,
    isLoading: nationalLoading,
    isError: nationalError,
    refetch: retryNational,
  } = useNationalMoneyFlow(selectedYear);
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
  const {
    samePeriod: nationalPeriodFlow,
    share: nationalSpendingShare,
    allocated: nationalAllocated,
    spent: nationalSpent,
  } = nationalSpendingSummary(nationalFlow, selectedYear);
  const insights = useMemo(() => {
    if (!nationalPeriodFlow?.stages) return null;
    const questioned = nationalPeriodFlow.stages.find((stage) => stage.stage === 'Flagged');
    const recordedAmount = questioned?.amount;
    const flagged =
      recordedAmount != null && Number.isFinite(recordedAmount) && !questioned?.data_unavailable
        ? recordedAmount
        : null;
    const gap = nationalAllocated != null && nationalSpent != null ? nationalAllocated - nationalSpent : null;
    const unspentPct =
      gap != null && nationalAllocated != null && nationalAllocated > 0
        ? (gap / nationalAllocated) * 100
        : null;
    return {
      allocated: nationalAllocated,
      spent: nationalSpent,
      flagged,
      audit_amount_coverage: nationalPeriodFlow.audit_amount_coverage,
      gap,
      unspentPct,
      efficiency: nationalPeriodFlow.efficiency_score ?? null,
    };
  }, [nationalAllocated, nationalPeriodFlow, nationalSpent]);

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
        audit_amount_coverage: flowData.audit_amount_coverage,
        total_gap: totalGap,
        allocated: allocatedStage?.amount ?? null,
        spent: spentStage?.amount ?? null,
      };
    });
  }, [allCountyFlows]);

  const isProjectedFY = isProjectedMoneyFlow(nationalPeriodFlow);
  const distribution = useMemo(
    () => isProjectedFY ? [] : countyDistributionPoints(allCountyFlows ?? [], selectedYear),
    [allCountyFlows, isProjectedFY, selectedYear]
  );
  const isProjectedCountyList =
    isProjectedFY &&
    countyRows.every(
      (row) => row.spent == null && row.flagged_amount == null && row.efficiency_score == null
    );

  const auditUnavailable =
    countyRows.length > 0 && countyRows.every((row) => row.flagged_amount == null);
  // The control and comparator use the same key for the current reporting period.
  const effectiveSortKey: SortKey = isProjectedCountyList
    ? sortKey === 'name'
      ? 'name'
      : 'allocated'
    : sortKey === 'allocated' || (sortKey === 'flagged' && auditUnavailable)
      ? 'efficiency'
      : sortKey;

  const sortedRows = useMemo(() => {
    const sorted = [...countyRows];
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
    const search = searchQuery.trim().toLowerCase();
    return sorted
      .map((row, index) => ({ ...row, rank: index + 1 }))
      .filter((row) => row.county_name.toLowerCase().includes(search));
  }, [countyRows, searchQuery, effectiveSortKey, sortDir]);

  const countiesWithData = countyRows.filter((row) => row.allocated != null).length;

  const auditAbsenceExplained =
    auditUnavailable &&
    sortedRows.length > 0 &&
    !isProjectedCountyList &&
    !allCountyFlowsLoading &&
    !countyFlowsError;
  const nationalOverview = insights && (
    <MoneyFlowOverview
      insights={insights}
      fiscalYear={stripFY(selectedYear)}
      projected={isProjectedFY}
      auditOnly={nationalSpendingShare != null}
      auditAbsenceExplained={auditAbsenceExplained}
    />
  );

  return (
    <PageShell title='Follow the Money' subtitle={nationalSpendingMessages.subtitle[lang]}>
      <MoneyFlowPeriodPicker
        years={pickerYears}
        selected={selectedYear}
        onSelect={setPickedYear}
      />

      {nationalLoading ? (
        <p role='status' className='py-5 text-neutral-muted'>
          {nationalSpendingMessages.loading[lang]}
        </p>
      ) : nationalError && !nationalFlow ? (
        <div className='py-5'>
          <p role='status'>{nationalSpendingMessages.error[lang]}</p>
          <button
            type='button'
            className='min-h-11 text-sm font-semibold text-neutral-text underline underline-offset-4'
            onClick={() => void retryNational()}>
            {nationalSpendingMessages.retry[lang]}
          </button>
        </div>
      ) : (
        <MoneyFlowHero
          data={nationalFlow}
          selectedYear={selectedYear}
          auditCoverageInSource={
            nationalSpendingShare != null && auditAbsenceExplained && insights?.flagged == null
          }
        />
      )}

      {/* The verified verdict already covers allocation, the gap and spending share. */}
      {nationalSpendingShare == null && nationalOverview}

      {/* ═══ 4b. Projected-FY explainer (shown when no execution data yet) ═══ */}
      {isProjectedFY && fiscalStartYear(selectedYear) === currentFiscalStartYear() && (
        <Section delay={0.14}>
          <ProjectedFYBanner yearLabel={selectedYear} />
        </Section>
      )}

      {/* ═══ 5. County comparison ═══ */}
      <CountySpendingList
        key={selectedYear}
        rows={sortedRows}
        fiscalYear={stripFY(selectedYear)}
        countiesWithData={countiesWithData}
        distribution={distribution}
        distributionNational={nationalDistributionGuide(nationalFlow, selectedYear)}
        nationalEfficiency={insights?.efficiency ?? null}
        nationalAllocated={insights?.allocated ?? null}
        projected={isProjectedCountyList}
        loading={allCountyFlowsLoading}
        error={countyFlowsError}
        auditUnavailable={auditUnavailable}
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

      {nationalSpendingShare != null && nationalOverview}

      {/* ═══ 6. Source reconciliation ═══ */}
      <Section delay={0.18}>
        <MoneyFlowSourceReconciliation
          fiscalYear={selectedYear}
          data={nationalPeriodFlow}
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
