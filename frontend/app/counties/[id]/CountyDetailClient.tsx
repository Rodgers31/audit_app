'use client';

/**
 * CountyDetailClient — the interactive body of the /counties/[id] page.
 *
 * Data is prefetched by the server component (`page.tsx`) and handed down
 * via HydrationBoundary, so first paint renders with a populated React
 * Query cache. Each of the six tabs (overview, money, budget, audit,
 * accountability, projects) is code-split via `next/dynamic` so we only
 * ship the ~400 lines of JSX for the tab the user actually opens.
 */
import PageShell from '@/components/layout/PageShell';
import PDFExportButton from '@/components/PDFExportButton';
import WatchButton from '@/components/WatchButton';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { useCountyAccountability, useCountyComprehensive } from '@/lib/react-query/useCounties';
import { getLatestReportedFiscalYear } from '@/lib/utils';
import { CountyComprehensive } from '@/types';
import { motion } from 'framer-motion';
import {
  ArrowLeft,
  Award,
  Banknote,
  CircleDollarSign,
  Clock,
  ExternalLink,
  Grid3x3,
  HardHat,
  Info,
  Landmark,
  ShieldAlert,
  X,
} from 'lucide-react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import SmartBackLink from '@/lib/navigation/SmartBackLink';
import { usePathname, useParams, useRouter, useSearchParams } from 'next/navigation';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ACCT_GRADE_BG,
  fmtKES,
  fmtLabel,
  fmtPop,
  HEALTH_GRADE_BG,
  pct,
  Tab,
} from './shared';
import TabSkeleton from './tabs/TabSkeleton';

/* ═══════════ Code-split tabs ═══════════
   Each tab is its own chunk. ssr:false is fine here because the parent
   page.tsx has already prefetched the data into the React Query cache;
   the tab body just consumes it. */
const OverviewTab = dynamic(() => import('./tabs/OverviewTab'), {
  ssr: false,
  loading: () => <TabSkeleton />,
});
const MoneyFlowTab = dynamic(() => import('./tabs/MoneyFlowTab'), {
  ssr: false,
  loading: () => <TabSkeleton />,
});
const BudgetTab = dynamic(() => import('./tabs/BudgetTab'), {
  ssr: false,
  loading: () => <TabSkeleton />,
});
const AuditTab = dynamic(() => import('./tabs/AuditTab'), {
  ssr: false,
  loading: () => <TabSkeleton />,
});
const AccountabilityTab = dynamic(() => import('./tabs/AccountabilityTab'), {
  ssr: false,
  loading: () => <TabSkeleton />,
});
const ProjectsTab = dynamic(() => import('./tabs/ProjectsTab'), {
  ssr: false,
  loading: () => <TabSkeleton />,
});

const TABS: { id: Tab; labelKey: TranslationKey; icon: React.ElementType }[] = [
  { id: 'overview', labelKey: 'county.tab.overview', icon: Landmark },
  { id: 'money', labelKey: 'county.tab.money', icon: Banknote },
  { id: 'budget', labelKey: 'county.tab.budget_debt', icon: CircleDollarSign },
  { id: 'audit', labelKey: 'county.tab.audit_findings', icon: ShieldAlert },
  { id: 'accountability', labelKey: 'county.tab.accountability', icon: Award },
  { id: 'projects', labelKey: 'county.tab.projects', icon: HardHat },
];

/** Tiny inline SVG sparkline — renders a trend without pulling in a chart lib.
 * Used under the HEALTH and AUDIT badges to show whether a county is trending
 * up or down over the last ~4 fiscal years. */
function Sparkline({
  values,
  stroke = 'rgba(255,255,255,0.85)',
  fill = 'rgba(255,255,255,0.18)',
  width = 80,
  height = 18,
  title,
}: {
  values: number[];
  stroke?: string;
  fill?: string;
  width?: number;
  height?: number;
  title?: string;
}) {
  if (!values.length) return null;
  const max = Math.max(...values, 100);
  const min = Math.min(...values, 0);
  const range = Math.max(max - min, 1);
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  const points = values
    .map((v, i) => `${(i * step).toFixed(1)},${(height - ((v - min) / range) * height).toFixed(1)}`)
    .join(' ');
  const areaPath = `M0,${height} L${points.replace(/\s/g, ' L')} L${width},${height} Z`;
  const last = values[values.length - 1];
  const lastY = height - ((last - min) / range) * height;
  const trendUp = values.length > 1 && last >= values[0];
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-label={title || `Trend across ${values.length} fiscal years`}
      className='overflow-visible'>
      <title>{title || `Trend across ${values.length} fiscal years`}</title>
      <path d={areaPath} fill={fill} />
      <polyline points={points} fill='none' stroke={stroke} strokeWidth={1.5} strokeLinejoin='round' strokeLinecap='round' />
      <circle cx={width} cy={lastY} r={2} fill={trendUp ? '#86efac' : '#fca5a5'} stroke={stroke} strokeWidth={0.8} />
    </svg>
  );
}

function GradeBadge({
  grade,
  score,
  label,
  title,
  palette,
  onClick,
  sparklineValues,
}: {
  grade: string;
  score: number | null;
  label: string;
  title: string;
  palette: Record<string, string>;
  onClick?: () => void;
  sparklineValues?: number[];
}) {
  return (
    <button
      type='button'
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      title={title}
      style={{ position: 'relative', zIndex: 100 }}
      aria-label={`${label} grade: ${grade}${score !== null ? `, score ${score.toFixed(0)} out of 100` : ''}`}
      className={`inline-flex flex-col items-stretch gap-1 px-3.5 py-2 rounded-xl bg-gradient-to-r ${palette[grade] || palette.C || palette.F || 'from-gray-500 to-gray-600'} text-white shadow-lg cursor-pointer hover:brightness-110 hover:scale-105 transition-all group`}>
      <div className='flex items-center gap-2'>
        <span className='text-2xl font-black leading-none' aria-hidden='true'>
          {grade}
        </span>
        <div className='border-l border-white/30 pl-2 text-left'>
          <div className='text-[9px] uppercase tracking-widest opacity-80 flex items-center gap-1'>
            {label}
            <Info size={9} className='opacity-0 group-hover:opacity-100 transition-opacity' />
          </div>
          <div className='text-sm font-bold leading-tight tabular-nums'>
            {score !== null ? score.toFixed(0) : '—'}
          </div>
        </div>
      </div>
      {sparklineValues && sparklineValues.length >= 2 && (
        <div className='pt-1 border-t border-white/20'>
          <Sparkline
            values={sparklineValues}
            width={72}
            height={14}
            title={`${label} trend — last ${sparklineValues.length} FYs`}
          />
        </div>
      )}
    </button>
  );
}

/* ═══════════ Health Score Methodology Modal ═══════════ */
const GRADE_THRESHOLDS: Array<{
  min: number;
  grade: string;
  labelKey: TranslationKey;
  color: string;
}> = [
  { min: 85, grade: 'A', labelKey: 'county.acct.grade_excellent', color: 'bg-emerald-500' },
  { min: 70, grade: 'B+', labelKey: 'county.acct.grade_good', color: 'bg-green-500' },
  { min: 55, grade: 'B', labelKey: 'county.acct.grade_fair', color: 'bg-amber-500' },
  {
    min: 40,
    grade: 'B-',
    labelKey: 'county.acct.grade_needs_improvement',
    color: 'bg-orange-500',
  },
  { min: 0, grade: 'C', labelKey: 'county.acct.grade_poor', color: 'bg-red-500' },
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
  const { t } = useLang();
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
    GRADE_THRESHOLDS.find((th) => healthScore >= th.min) ||
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
        className='bg-white dark:bg-surface-base rounded-2xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto'>
        {/* Header */}
        <div className='bg-gradient-to-r from-gov-dark to-gov-forest px-6 py-5 rounded-t-2xl flex items-center justify-between'>
          <div>
            <h2 className='text-lg font-bold text-white'>{t('county.healthmodal.title')}</h2>
            <p className='text-sm text-white/70 mt-0.5'>
              {data.name} {t('county.page.name_suffix')}
            </p>
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
            <div className='inline-flex items-center gap-3 bg-gray-50 dark:bg-surface-elevated rounded-xl px-6 py-4'>
              <span
                className={`text-4xl font-black ${activeThreshold.color} text-white w-14 h-14 rounded-xl flex items-center justify-center`}>
                {grade}
              </span>
              <div className='text-left'>
                <div className='text-2xl font-bold text-gray-900 dark:text-neutral-text'>
                  {healthScore.toFixed(1)}
                  <span className='text-sm text-gray-500 dark:text-neutral-muted/80 font-normal'> / 100</span>
                </div>
                <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>{t(activeThreshold.labelKey)}</div>
              </div>
            </div>
          </div>

          {/* How it's calculated */}
          <div>
            <h3 className='text-sm font-semibold text-gray-900 dark:text-neutral-text uppercase tracking-wide mb-3'>
              {t('county.healthmodal.how_calc')}
            </h3>
            <div className='bg-gray-50 dark:bg-surface-elevated rounded-xl p-4 space-y-3 text-sm text-gray-700 dark:text-neutral-muted'>
              <p>{t('county.healthmodal.derived_from')}</p>
              <div className='border-l-2 border-gov-sage pl-3 space-y-1'>
                <p>
                  <strong>{t('county.healthmodal.rule_1')}</strong>{' '}
                  {t('county.healthmodal.rule_1_body')}
                </p>
                <p>
                  <strong>{t('county.healthmodal.rule_2')}</strong>{' '}
                  {t('county.healthmodal.rule_2_body')}
                </p>
                <p>
                  <strong>{t('county.healthmodal.rule_3')}</strong>{' '}
                  {t('county.healthmodal.rule_3_body')}
                </p>
              </div>
              <p className='text-xs text-gray-500 dark:text-neutral-muted/80 italic'>{t('county.healthmodal.max_note')}</p>
            </div>
          </div>

          {/* This county's breakdown */}
          <div>
            <h3 className='text-sm font-semibold text-gray-900 dark:text-neutral-text uppercase tracking-wide mb-3'>
              {t('county.healthmodal.this_county_numbers')}
            </h3>
            <div className='space-y-2'>
              {[
                {
                  label: t('county.healthmodal.row.budget_allocated'),
                  value: fmtKES(budget.total_allocated),
                },
                {
                  label: t('county.healthmodal.row.budget_spent'),
                  value: fmtKES(budget.total_spent),
                },
                {
                  label: t('county.healthmodal.row.execution_rate'),
                  value: `${utilization.toFixed(1)}%`,
                  highlight: true,
                },
                {
                  label: t('county.healthmodal.row.pending_bills'),
                  value: fmtKES(debt.pending_bills),
                },
                { label: t('county.healthmodal.row.total_debt'), value: fmtKES(debt.total_debt) },
                {
                  label: t('county.healthmodal.row.audit_issues'),
                  value: String(audit.findings_count),
                },
                {
                  label: t('county.healthmodal.row.stalled_projects'),
                  value: String(stalled_projects.count),
                },
              ].map((row) => (
                <div
                  key={row.label}
                  className={`flex justify-between items-center py-2 px-3 rounded-lg ${
                    row.highlight ? 'bg-gov-sage/10 font-semibold' : 'even:bg-gray-50 dark:bg-surface-elevated'
                  }`}>
                  <span className='text-sm text-gray-600 dark:text-neutral-muted'>{row.label}</span>
                  <span className='text-sm text-gray-900 dark:text-neutral-text font-medium'>{row.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Grade scale */}
          <div>
            <h3 className='text-sm font-semibold text-gray-900 dark:text-neutral-text uppercase tracking-wide mb-3'>
              {t('county.healthmodal.grade_scale')}
            </h3>
            <div className='space-y-1.5'>
              {GRADE_THRESHOLDS.map((th) => (
                <div
                  key={th.grade}
                  className={`flex items-center gap-3 py-2 px-3 rounded-lg text-sm ${
                    th.grade === grade ? 'bg-gray-100 dark:bg-surface-elevated ring-1 ring-gray-300 font-semibold' : ''
                  }`}>
                  <span
                    className={`${th.color} text-white font-bold w-8 h-8 rounded-lg flex items-center justify-center text-xs`}>
                    {th.grade}
                  </span>
                  <span className='text-gray-700 dark:text-neutral-muted flex-1'>{t(th.labelKey)}</span>
                  <span className='text-gray-400 dark:text-neutral-muted/80 text-xs'>
                    {th.min > 0 ? `≥ ${th.min}` : `< 40`}
                  </span>
                  {th.grade === grade && (
                    <span className='text-xs bg-gov-forest text-white px-2 py-0.5 rounded-full'>
                      {t('county.healthmodal.current')}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Data source note */}
          <p className='text-xs text-gray-400 dark:text-neutral-muted/80 text-center'>
            {t('county.healthmodal.source_line')}
          </p>
        </div>
      </motion.div>
    </div>
  );
}

/* ═══════════ Data Sources Footer ═══════════ */
function SourcesFooter() {
  const { t } = useLang();
  const sources: Array<{ key: string; labelKey: TranslationKey; url: string }> = [
    {
      key: 'budget',
      labelKey: 'county.sources.budget',
      url: 'https://cob.go.ke/publications/county-budget-implementation-review-reports/',
    },
    {
      key: 'audit',
      labelKey: 'county.sources.audit',
      url: 'https://www.oagkenya.go.ke/county-government-audit-reports/',
    },
    {
      key: 'debt',
      labelKey: 'county.sources.debt',
      url: 'https://www.treasury.go.ke/county-governments/',
    },
    {
      key: 'population',
      labelKey: 'county.sources.population',
      url: 'https://www.knbs.or.ke/publications/',
    },
  ];

  return (
    <div className='flex flex-wrap items-center gap-x-4 gap-y-1 pt-3 border-t border-gray-100 dark:border-neutral-border'>
      <span className='text-[10px] text-gray-400 dark:text-neutral-muted/80 uppercase tracking-wider font-semibold'>
        {t('county.sources.prefix')}
      </span>
      {sources.map((s) => (
        <a
          key={s.key}
          href={s.url}
          target='_blank'
          rel='noopener noreferrer'
          className='inline-flex items-center gap-1 text-[11px] text-gov-forest dark:text-emerald-100 hover:underline'>
          {t(s.labelKey)}
          <ExternalLink size={9} />
        </a>
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════
   Main Page
   ═══════════════════════════════════════════ */
export default function CountyDetailClient() {
  const { t } = useLang();
  const params = useParams();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const countyId = params.id as string;
  // Respect ?fy=... from the listing so the Health badge matches the column
  // the user clicked from. Fall back to the last reported FY.
  const fiscalYear = searchParams.get('fy') || getLatestReportedFiscalYear();
  const { data, isLoading, error } = useCountyComprehensive(countyId, fiscalYear);
  // Prefetch accountability so the hero can show the grade immediately
  const { data: acctData } = useCountyAccountability(countyId);

  const initialTab = (searchParams.get('tab') as Tab) || 'overview';
  const validTabs: Tab[] = ['overview', 'money', 'budget', 'audit', 'accountability', 'projects'];
  const [tab, setTab] = useState<Tab>(validTabs.includes(initialTab) ? initialTab : 'overview');
  const [showHealthModal, setShowHealthModal] = useState(false);

  // Sync the active tab to the URL so reload / share-link / browser-back
  // all restore the user's place. `?tab=overview` is the default and is
  // omitted to keep the URL clean; any other tab is written as a query
  // param via `router.replace` (no history entry — tab switching
  // shouldn't clutter the back-button stack).
  const tabBarRef = useRef<HTMLDivElement | null>(null);
  const handleTabChange = useCallback(
    (next: Tab) => {
      setTab(next);
      // Mirror the tab into the URL.
      const current = new URLSearchParams(Array.from(searchParams.entries()));
      if (next === 'overview') {
        current.delete('tab');
      } else {
        current.set('tab', next);
      }
      const qs = current.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });

      // Scroll the tab bar into view. Without this, the browser preserves
      // pixel-offset scroll position — if the user was deep into Overview
      // and clicks Budget & Debt (shorter), they'd land on the footer.
      requestAnimationFrame(() => {
        tabBarRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        });
      });
    },
    [pathname, router, searchParams]
  );

  /* Loading */
  if (isLoading) {
    return (
      <PageShell title={t('county.page.title_fallback')} subtitle={t('county.loading')}>
        <div className='flex items-center justify-center py-24'>
          <div className='animate-spin rounded-full h-14 w-14 border-b-2 border-gov-forest' />
        </div>
      </PageShell>
    );
  }

  /* Error */
  if (error || !data) {
    const from = searchParams.get('from');
    const backHref = from === 'transparency' ? '/transparency' : '/counties';
    const backLabel =
      from === 'transparency'
        ? t('county.page.back_follow_money')
        : t('county.page.back_county_explorer');
    return (
      <PageShell title={t('county.page.title_fallback')}>
        <div className='text-center py-16'>
          <ShieldAlert size={40} className='mx-auto text-red-400 mb-3' />
          <p className='text-red-600 mb-4'>{t('county.page.failed_load')}</p>
          <Link href={backHref} className='text-sm text-gov-forest dark:text-emerald-100 hover:underline'>
            &larr; {backLabel}
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

  const fromParam = searchParams.get('from');
  // from=home-map is set by InteractiveKenyaMap's tooltip CTA. It
  // means "the user arrived here by clicking a county on the home
  // dashboard map" — render two explicit shortcuts (back to that
  // map, or jump to the all-counties explorer) instead of the single
  // SmartBackLink. Other from= values keep the existing single-link
  // behaviour.
  const fromHomeMap = fromParam === 'home-map';
  const topBackHref = fromParam === 'transparency' ? '/transparency' : '/counties';
  const topBackLabel =
    fromParam === 'transparency'
      ? t('county.page.follow_money_short')
      : t('county.page.all_counties_short');

  return (
    <>
      <PageShell
        title={`${data.name} ${t('county.page.name_suffix')}`}
        subtitle={t('county.page.subtitle')}>
        {/* Back — default flow uses SmartBackLink so coming from
            /counties?p=2 pops history (restoring pagination, filters,
            scroll) instead of pushing a fresh /counties. The home-map
            arrival path is different: we want an explicit "rewind to
            the exact scroll position of the map" (via /#home-map) AND
            a separate shortcut to the full list — so we render two
            dedicated buttons instead. */}
        {fromHomeMap ? (
          <div className='flex flex-wrap items-center gap-2'>
            {/* Primary action: solid forest fill + back arrow so it
                reads as "rewind to where I came from". The all-counties
                shortcut next to it is deliberately secondary (outlined
                + muted) so the eye lands on the return path first. */}
            <Link
              href='/#home-map'
              className='inline-flex items-center gap-1.5 rounded-full bg-gov-forest px-3.5 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-gov-dark transition-colors'>
              <ArrowLeft size={14} />
              {t('county.page.back_to_home_map')}
            </Link>
            <Link
              href='/counties'
              className='inline-flex items-center gap-1.5 rounded-full border border-neutral-border/60 bg-white dark:bg-surface-base px-3 py-1.5 text-sm text-neutral-muted hover:text-gov-dark dark:text-white hover:border-neutral-border transition-colors'>
              <Grid3x3 size={14} />
              {t('county.page.all_counties_short')}
            </Link>
          </div>
        ) : (
          <SmartBackLink
            href={topBackHref}
            className='inline-flex items-center gap-1.5 text-sm text-gov-forest dark:text-emerald-100 hover:text-gov-dark dark:text-white transition-colors'>
            <ArrowLeft size={14} />
            {topBackLabel}
          </SmartBackLink>
        )}

        {/* ── Hero ── */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className='relative overflow-hidden rounded-2xl bg-gradient-to-br from-gov-dark via-gov-forest to-gov-forest text-white shadow-lg'>
          {/* Decorative blurred blobs for depth */}
          <div
            aria-hidden
            className='pointer-events-none absolute -top-16 -right-16 h-64 w-64 rounded-full bg-emerald-400/20 blur-3xl'
          />
          <div
            aria-hidden
            className='pointer-events-none absolute -bottom-20 -left-10 h-56 w-56 rounded-full bg-sky-400/10 blur-3xl'
          />

          <div className='relative px-6 pt-6 pb-5 flex flex-col lg:flex-row lg:items-start justify-between gap-6'>
            {/* Identity */}
            <div className='min-w-0'>
              <div className='flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] text-white/60 mb-2'>
                <Landmark size={12} />
                {t('county.hero.eyebrow')}
              </div>
              <h1 className='text-2xl sm:text-3xl font-bold tracking-tight'>
                {data.name} {t('county.page.name_suffix')}
              </h1>
              <p className='text-sm text-white/75 mt-1.5 max-w-md'>
                {fmtPop(data.demographics.population)} {t('county.hero.residents')} ·{' '}
                {fmtLabel(data.economic_profile.economic_base)} {t('county.hero.economy_suffix')}
                {data.governor ? ` · ${t('county.hero.governor_short')} ${data.governor}` : ''}
              </p>
              {data.budget.fiscal_year && (
                <div className='mt-3 inline-flex items-center gap-1.5 rounded-full bg-white/10 backdrop-blur-sm px-3 py-1 text-[11px] font-medium text-white/90 border border-white/10'>
                  <Clock size={10} />
                  {t('county.hero.fy_badge')} {data.budget.fiscal_year}
                </div>
              )}
            </div>

            {/* Actions + Grades */}
            <div className='flex items-center gap-3 flex-shrink-0 flex-wrap justify-end'>
              <WatchButton
                itemType='county'
                itemId={countyId}
                label={`${data.name} ${t('county.page.name_suffix')}`}
              />
              <PDFExportButton
                compact
                documentTitle={`${data.name} ${t('county.pdf.report_suffix')}`}
                className='text-white/70 hover:text-white hover:bg-white/10'
              />
              <div className='flex items-center gap-2'>
                <GradeBadge
                  grade={data.financial_summary.grade}
                  score={data.financial_summary.health_score}
                  label={t('county.grade.health')}
                  title={t('county.grade.health_tooltip')}
                  palette={HEALTH_GRADE_BG}
                  onClick={() => setShowHealthModal(true)}
                  sparklineValues={data.health_history?.map((h) => h.score)}
                />
                <GradeBadge
                  grade={acctData?.accountability_grade || '—'}
                  score={
                    typeof acctData?.accountability_score === 'number'
                      ? acctData.accountability_score
                      : null
                  }
                  label={t('county.grade.audit')}
                  title={t('county.grade.audit_tooltip')}
                  palette={ACCT_GRADE_BG}
                  onClick={() => setTab('accountability')}
                  sparklineValues={acctData?.audit_severity_history?.map((h) => h.score)}
                />
              </div>
            </div>
          </div>

          {/* Quick KPIs — glassy strip */}
          <div className='relative grid grid-cols-3 sm:grid-cols-6 bg-black/15 backdrop-blur-sm border-t border-white/10'>
            {[
              {
                label: t('county.hero.kpi.budget'),
                value: fmtKES(data.budget.total_allocated),
                accent: 'text-white',
              },
              {
                label: t('county.hero.kpi.execution'),
                value: pct(data.budget.utilization_rate),
                accent:
                  data.budget.utilization_rate >= 70
                    ? 'text-emerald-300'
                    : data.budget.utilization_rate >= 40
                      ? 'text-amber-300'
                      : 'text-rose-300',
              },
              {
                label: t('county.hero.kpi.total_debt'),
                value: fmtKES(data.debt.total_debt),
                accent: 'text-white',
              },
              {
                label: t('county.hero.kpi.pending_bills'),
                value: fmtKES(data.debt.pending_bills),
                accent: 'text-white',
              },
              {
                label: t('county.hero.kpi.audit_issues'),
                value: String(data.audit.findings_count),
                accent: data.audit.findings_count > 0 ? 'text-rose-300' : 'text-white',
              },
              {
                label: t('county.hero.kpi.stalled'),
                value: String(data.stalled_projects.count),
                accent: data.stalled_projects.count > 0 ? 'text-amber-300' : 'text-white',
              },
            ].map((kpi, i, arr) => (
              <div
                key={kpi.label}
                className={`px-4 py-3.5 ${i < arr.length - 1 ? 'border-r border-white/10' : ''} text-center`}>
                <div className={`text-sm font-bold tabular-nums ${kpi.accent}`}>{kpi.value}</div>
                <div className='text-[10px] uppercase tracking-wider text-white/55 mt-0.5'>
                  {kpi.label}
                </div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* ── Tabs ── pill-button group with a clear active state.
             The container itself is a subtle rounded surface; each tab
             is a chip that lights up when active (solid gov-forest in
             both modes so the active state reads instantly), while
             inactive chips stay ghosted with hover affordance. */}
        <div
          ref={tabBarRef}
          style={{ scrollMarginTop: '88px' }}
          className='flex items-center gap-1 overflow-x-auto rounded-full bg-gov-dark/5 dark:bg-surface-elevated/60 p-1 ring-1 ring-inset ring-gov-dark/10 dark:ring-white/10'>
          {TABS.map((tabItem) => {
            const active = tab === tabItem.id;
            return (
              <button
                key={tabItem.id}
                onClick={() => handleTabChange(tabItem.id)}
                aria-pressed={active}
                className={`relative flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors ${
                  active
                    ? 'text-white'
                    : 'text-gov-dark/70 dark:text-white/70 hover:text-gov-dark dark:hover:text-white'
                }`}>
                {active && (
                  <motion.div
                    layoutId='county-tab-pill'
                    className='absolute inset-0 rounded-full bg-gov-forest shadow-sm'
                    transition={{ type: 'spring', stiffness: 400, damping: 32 }}
                  />
                )}
                <tabItem.icon
                  size={14}
                  className={`relative z-[1] ${
                    active ? 'text-white' : 'text-gov-dark/55 dark:text-white/55'
                  }`}
                />
                <span className='relative z-[1]'>{t(tabItem.labelKey)}</span>
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
        <SourcesFooter />
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
