'use client';

/**
 * CountyDetailClient — the interactive body of the /counties/[id] page.
 *
 * Data is prefetched by the server component (`page.tsx`) and handed down
 * via HydrationBoundary, so first paint renders with a populated React
 * Query cache. Each of the five tabs (overview, money, budget, audit,
 * accountability) is code-split via `next/dynamic` so we only
 * ship the ~400 lines of JSX for the tab the user actually opens.
 */
import PDFExportButton from '@/components/PDFExportButton';
import WatchButton from '@/components/WatchButton';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import {
  useCountyAccountability,
  useCountyComprehensive,
  useCountyFiscalYears,
} from '@/lib/react-query/useCounties';
import { serviceableFiscalYear } from '@/lib/utils';
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
  Info,
  Landmark,
  ShieldAlert,
  X,
} from 'lucide-react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import SmartBackLink from '@/lib/navigation/SmartBackLink';
import { usePathname, useParams, useRouter, useSearchParams } from 'next/navigation';
import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { fmtKES, fmtLabel, fmtPop, hasIngestedAudit, pct, Tab } from './shared';
import TabSkeleton from './tabs/TabSkeleton';
import styles from '../CountyExperience.module.css';
import { gradeSignal, SignalMark } from '../CountySignals';

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
// ProjectsTab withdrawn — see the note on the TABS array below.

const TABS: { id: Tab; labelKey: TranslationKey; icon: React.ElementType }[] = [
  { id: 'overview', labelKey: 'county.tab.overview', icon: Landmark },
  { id: 'money', labelKey: 'county.tab.money', icon: Banknote },
  { id: 'budget', labelKey: 'county.tab.budget_debt', icon: CircleDollarSign },
  { id: 'audit', labelKey: 'county.tab.audit_findings', icon: ShieldAlert },
  { id: 'accountability', labelKey: 'county.tab.accountability', icon: Award },
  // The "Projects" tab was withdrawn (credibility audit F6). It rendered 25
  // hand-written records from backend/seeding/real_data/stalled_projects.json
  // against 21 named counties, each carrying an Auditor-General case reference
  // (e.g. "OAG/MSA/2023/HLT-004"), a contract value, a completion percentage
  // and a narrative cause. No OAG report was ever read for any of them: the
  // domain's own fetcher records mark_fixture(reason="no_live_source", "...
  // source is OAG audit reports, for which no extractor exists yet"), and all
  // 25 records have amount_paid/contracted_amount equal to an exact whole
  // percent drawn only from {20,30,40,50,60}. Publishing a case number asserts
  // that a document exists. The fixture was deleted in #230 and the API now
  // carries COB's own per-county tables with a page citation on every row;
  // re-enabling this tab on that data is an open decision for the maintainer.
];

/** Tiny inline SVG sparkline — renders a trend without pulling in a chart lib.
 * Used under the HEALTH and AUDIT badges to show whether a county is trending
 * up or down over the last ~4 fiscal years. */
function Sparkline({
  values,
  stroke = 'var(--county-accent)',
  fill = 'var(--county-accent)',
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
      <path d={areaPath} fill={fill} fillOpacity={0.12} />
      <polyline
        points={points}
        fill='none'
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinejoin='round'
        strokeLinecap='round'
      />
      <circle
        cx={width}
        cy={lastY}
        r={2}
        fill={trendUp ? 'var(--county-accent)' : 'var(--county-negative)'}
        stroke={stroke}
        strokeWidth={0.8}
      />
    </svg>
  );
}

function GradeBadge({
  scale,
  grade,
  score,
  label,
  title,
  onClick,
  sparklineValues,
}: {
  scale: 'health' | 'audit';
  /** null when there is no evidence to grade — rendered as an explicit
   *  "not assessed" state, never as a letter and never in a rating colour. */
  grade: string | null;
  score: number | null;
  label: string;
  title: string;
  onClick?: () => void;
  sparklineValues?: number[];
}) {
  const { t } = useLang();
  const signal = gradeSignal(grade, scale);
  const verdictId = useId();
  return (
    <button
      type='button'
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      title={title}
      aria-label={
        grade == null
          ? `${label}: not yet assessed — no sourced audit finding for this county`
          : `${label} grade: ${grade}${score !== null ? `, score ${score.toFixed(0)} out of 100` : ''}`
      }
      className={`${styles.gradeBadge} ${styles.signal}`}
      data-tone={signal.tone}
      aria-describedby={grade != null ? verdictId : undefined}
      data-grade={grade ?? 'unavailable'}>
      <div>
        {grade != null && (
          <span className={styles.gradeLetter} aria-hidden='true'>
            {grade}
          </span>
        )}
        <div>
          <div className={styles.gradeLabel}>
            {label}
            <Info size={12} aria-hidden='true' />
          </div>
          <div className={styles.gradeScore}>
            {grade == null ? 'Not assessed' : score !== null ? `${score.toFixed(0)} / 100` : '—'}
          </div>
        </div>
      </div>
      {grade != null && (
        <span id={verdictId} className={styles.gradeVerdict}>
          <SignalMark tone={signal.tone} />
          {t(signal.labelKey)}
        </span>
      )}
      {sparklineValues && sparklineValues.length >= 2 && (
        <div className='pt-1'>
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
  {
    min: 85,
    grade: 'A',
    labelKey: 'county.acct.grade_excellent',
    color: 'bg-emerald-500',
  },
  {
    min: 70,
    grade: 'B+',
    labelKey: 'county.acct.grade_good',
    color: 'bg-green-500',
  },
  {
    min: 55,
    grade: 'B',
    labelKey: 'county.acct.grade_fair',
    color: 'bg-amber-500',
  },
  {
    min: 40,
    grade: 'B-',
    labelKey: 'county.acct.grade_needs_improvement',
    color: 'bg-orange-500',
  },
  {
    min: 0,
    grade: 'C',
    labelKey: 'county.acct.grade_poor',
    color: 'bg-red-500',
  },
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

  const { financial_summary, budget, debt, audit } = data;
  const utilization = budget.utilization_rate;
  const healthScore = financial_summary.health_score;
  const grade = financial_summary.grade;

  // Determine which threshold is active
  const activeThreshold =
    healthScore == null
      ? null
      : GRADE_THRESHOLDS.find((th) => healthScore >= th.min) ||
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
                className={`text-4xl font-black ${activeThreshold?.color ?? 'bg-gray-500'} text-white w-14 h-14 rounded-xl flex items-center justify-center`}>
                {grade ?? '—'}
              </span>
              <div className='text-left'>
                <div className='text-2xl font-bold text-gray-900 dark:text-neutral-text'>
                  {healthScore == null ? '—' : healthScore.toFixed(1)}
                  {healthScore != null && (
                    <span className='text-sm text-gray-500 dark:text-neutral-muted/80 font-normal'>
                      {' '}
                      / 100
                    </span>
                  )}
                </div>
                <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>
                  {activeThreshold ? t(activeThreshold.labelKey) : 'Not assessed'}
                </div>
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
              <p className='text-xs text-gray-500 dark:text-neutral-muted/80 italic'>
                {t('county.healthmodal.max_note')}
              </p>
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
                  value: utilization == null ? '—' : `${utilization.toFixed(1)}%`,
                  highlight: true,
                },
                {
                  label: t('county.healthmodal.row.pending_bills'),
                  value: fmtKES(debt.pending_bills),
                },
                {
                  label: t('county.healthmodal.row.total_debt'),
                  value: fmtKES(debt.total_debt),
                },
                {
                  label: t('county.healthmodal.row.audit_issues'),
                  value: hasIngestedAudit(audit)
                    ? String(audit.findings_count)
                    : 'Not yet ingested',
                },
              ].map((row) => (
                <div
                  key={row.label}
                  className={`flex justify-between items-center py-2 px-3 rounded-lg ${
                    row.highlight
                      ? 'bg-gov-sage/10 font-semibold'
                      : 'even:bg-gray-50 dark:bg-surface-elevated'
                  }`}>
                  <span className='text-sm text-gray-600 dark:text-neutral-muted'>{row.label}</span>
                  <span className='text-sm text-gray-900 dark:text-neutral-text font-medium'>
                    {row.value}
                  </span>
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
                    th.grade === grade
                      ? 'bg-gray-100 dark:bg-surface-elevated ring-1 ring-gray-300 font-semibold'
                      : ''
                  }`}>
                  <span
                    className={`${th.color} text-white font-bold w-8 h-8 rounded-lg flex items-center justify-center text-xs`}>
                    {th.grade}
                  </span>
                  <span className='text-gray-700 dark:text-neutral-muted flex-1'>
                    {t(th.labelKey)}
                  </span>
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
    <div className={styles.sourceLinks}>
      <span className='text-[11px] text-gray-400 dark:text-neutral-muted/80 uppercase tracking-wider font-semibold'>
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
  // Only an EXPLICIT ?fy= pins the period. Without one we send nothing and
  // let the backend choose, which it does from the data
  // (_latest_county_actuals_period_ids: newest period carrying real CoB BIRR
  // classification rows). This page used to default to
  // getLatestReportedFiscalYear() — a label computed from `new Date()` with no
  // reference to what exists — which overrode that choice and landed on the
  // equitable-share projection period. That is why /counties said Mombasa's
  // budget was KES 14.63B and this page said KES 9.42B, and why Nairobi's
  // pending bills differed 23-fold between the two (credibility audit F7).
  //
  // The API now refuses a fiscal_year it holds no county budget data for
  // (it used to skip the period filter and sum every period into one figure),
  // so a stale ?fy= bookmark would render "Failed to load county data" over a
  // county that loads perfectly well. An unservable year is dropped rather
  // than sent; the API then resolves the period and the hero labels it.
  const requestedYear = searchParams.get('fy') || undefined;
  const { data: fiscalYearsMeta } = useCountyFiscalYears();
  const fiscalYear = serviceableFiscalYear(requestedYear, fiscalYearsMeta);
  const { data, isLoading, error } = useCountyComprehensive(countyId, fiscalYear);
  // Prefetch accountability so the hero can show the grade immediately
  const { data: acctData } = useCountyAccountability(countyId);

  const initialTab = (searchParams.get('tab') as Tab) || 'overview';
  const validTabs: Tab[] = ['overview', 'money', 'budget', 'audit', 'accountability'];
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
      <div className={styles.detail}>
        <div className={styles.container}>
          <header className={styles.detailHeader}>
            <h1>{t('county.page.title_fallback')}</h1>
            <p className={styles.intro}>{t('county.loading')}</p>
          </header>
          <div className={styles.pageState}>
            <div className='animate-spin rounded-full h-8 w-8 border-b-2 border-gov-forest' />
          </div>
        </div>
      </div>
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
      <div className={styles.detail}>
        <div className={styles.container}>
          <header className={styles.detailHeader}>
            <h1>{t('county.page.title_fallback')}</h1>
          </header>
          <div className={styles.pageState}>
            <ShieldAlert size={40} className='mx-auto text-red-400 mb-3' />
            <p className='text-red-600 mb-4'>{t('county.page.failed_load')}</p>
            <Link
              href={backHref}
              className='text-sm text-gov-forest dark:text-emerald-100 hover:underline'>
              &larr; {backLabel}
            </Link>
          </div>
        </div>
      </div>
    );
  }

  /* Tab content */
  const TabContent = {
    overview: OverviewTab,
    money: MoneyFlowTab,
    budget: BudgetTab,
    audit: AuditTab,
    accountability: AccountabilityTab,
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
      <div className={styles.detail}>
        <div className={styles.container}>
          <nav className={styles.backLinks} aria-label={t('county.page.all_counties_short')}>
            {fromHomeMap ? (
              <>
                <Link href='/#home-map'>
                  <ArrowLeft size={14} aria-hidden='true' />
                  {t('county.page.back_to_home_map')}
                </Link>
                <Link href='/counties'>
                  <Grid3x3 size={14} aria-hidden='true' />
                  {t('county.page.all_counties_short')}
                </Link>
              </>
            ) : (
              <SmartBackLink href={topBackHref}>
                <ArrowLeft size={14} aria-hidden='true' />
                {topBackLabel}
              </SmartBackLink>
            )}
          </nav>
          <header className={styles.detailHeader}>
            <div className={styles.detailIdentity}>
              <div>
                <p className={styles.eyebrow}>{t('county.hero.eyebrow')}</p>
                <h1>
                  {data.name} {t('county.page.name_suffix')}
                </h1>
                <p className={styles.detailDescription}>{t('county.page.subtitle')}</p>
                <p className={styles.detailDescription}>
                  {[
                    data.demographics.population != null
                      ? `${fmtPop(data.demographics.population)} ${t('county.hero.residents')}`
                      : null,
                    data.economic_profile.economic_base
                      ? `${fmtLabel(data.economic_profile.economic_base)} ${t('county.hero.economy_suffix')}`
                      : null,
                    data.governor ? `${t('county.hero.governor_short')} ${data.governor}` : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
                {data.budget.fiscal_year && (
                  <p className={styles.detailYear}>
                    <Clock size={13} aria-hidden='true' />
                    {t('county.hero.fy_badge')} {data.budget.fiscal_year}
                  </p>
                )}
              </div>
              <div className={styles.detailActions}>
                <WatchButton
                  itemType='county'
                  itemId={countyId}
                  label={`${data.name} ${t('county.page.name_suffix')}`}
                />
                <PDFExportButton
                  compact
                  documentTitle={`${data.name} ${t('county.pdf.report_suffix')}`}
                />
                <div className={styles.detailGrades}>
                  <GradeBadge
                    scale='health'
                    grade={data.financial_summary.grade}
                    score={data.financial_summary.health_score}
                    label={t('county.grade.health')}
                    title={t('county.grade.health_tooltip')}
                    onClick={() => setShowHealthModal(true)}
                    sparklineValues={data.health_history?.map((h) => h.score)}
                  />
                  <GradeBadge
                    scale='audit'
                    grade={acctData?.accountability_grade ?? null}
                    score={
                      typeof acctData?.accountability_score === 'number'
                        ? acctData.accountability_score
                        : null
                    }
                    label={t('county.grade.audit')}
                    title={t('county.grade.audit_tooltip')}
                    onClick={() => handleTabChange('accountability')}
                    sparklineValues={acctData?.audit_severity_history?.map((h) => h.score)}
                  />
                </div>
              </div>
            </div>
            <div className={styles.detailMetrics}>
              {[
                {
                  label: t('county.hero.kpi.budget'),
                  value: fmtKES(data.budget.total_allocated),
                  tone: 'neutral',
                },
                {
                  label: t('county.hero.kpi.execution'),
                  value: pct(data.budget.utilization_rate),
                  tone:
                    data.budget.utilization_rate == null
                      ? 'neutral'
                      : data.budget.utilization_rate >= 70
                        ? 'good'
                        : data.budget.utilization_rate >= 40
                          ? 'fair'
                          : 'low',
                },
                {
                  label: t('county.hero.kpi.total_debt'),
                  value: fmtKES(data.debt.total_debt),
                  tone: 'neutral',
                },
                {
                  label: t('county.hero.kpi.pending_bills'),
                  value: fmtKES(data.debt.pending_bills),
                  tone: 'neutral',
                },
                {
                  label: t('county.hero.kpi.audit_issues'),
                  value: hasIngestedAudit(data.audit) ? String(data.audit.findings_count) : '—',
                  tone: data.audit.findings_count > 0 ? 'low' : 'neutral',
                },
              ].map((kpi) => (
                <div key={kpi.label}>
                  <strong data-tone={kpi.tone}>{kpi.value}</strong>
                  <p>{kpi.label}</p>
                </div>
              ))}
            </div>
          </header>
          <div ref={tabBarRef} className={styles.sectionNavigation}>
            <p className={styles.sectionNavLabel}>{t('county.sections.label')}</p>
            <nav className={styles.tabs} aria-label={t('county.page.title_fallback')}>
              {TABS.map((item) => (
                <button
                  key={item.id}
                  onClick={() => handleTabChange(item.id)}
                  aria-pressed={tab === item.id}>
                  <item.icon size={17} aria-hidden='true' />
                  <span>{t(item.labelKey)}</span>
                </button>
              ))}
            </nav>
          </div>
          <div className={styles.reportBody}>
            <TabContent data={data} />
          </div>
          <SourcesFooter />
        </div>
      </div>
      <HealthScoreModal
        open={showHealthModal}
        onClose={() => setShowHealthModal(false)}
        data={data}
      />
    </>
  );
}
