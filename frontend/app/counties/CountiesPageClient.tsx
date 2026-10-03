'use client';

import FigureEvidence from '@/components/evidence/FigureEvidence';
import DataFreshnessBadge from '@/components/DataFreshnessBadge';
import ModelledDataNote from '@/components/ModelledDataNote';
import InfoTip from '@/components/InfoTip';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import {
  compareByPublishedFigure,
  countyBudget,
  countyDebt,
  countyPopulation,
  sumPublished,
} from '@/lib/countyFigures';
import { countyDebtRatio } from '@/components/map/MapUtilities';
import { useCounties, useCountyFiscalYears } from '@/lib/react-query';
import { resolveExplorerYear } from '@/lib/utils';
import { County } from '@/types';
import {
  AlertTriangle,
  ArrowUpDown,
  ChevronDown,
  Download,
  Filter,
  Search,
  TrendingUp,
} from 'lucide-react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import React, {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts';
import ResponsiveTable from '@/components/ui/ResponsiveTable';
import styles from './CountyExperience.module.css';
import { AuditStatusSignal } from './CountySignals';
import { FINANCIAL_HEALTH_BANDS, financialHealthBand } from '@/lib/counties/financialHealth';
import { getCountyRegion, normalizeCountyName } from '@/lib/counties/regions';

/* ══════════════════════════════════════════════════════════════════════════════
   HELPERS
   ══════════════════════════════════════════════════════════════════════════════ */

function fmtKES(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return n.toLocaleString();
}
/**
 * Figures whose absence must not be ranked. Ordering only — publishes nothing.
 */
const RANKED_FIGURE: Partial<Record<SortField, (c: County) => number | undefined>> = {
  budget: countyBudget,
  debt: countyDebt,
  population: countyPopulation,
};

/** Em dash for a figure the API withheld. A real 0 still renders as "0". */
function fmtKESorDash(n: number | null | undefined): string {
  return n == null ? '—' : fmtKES(n);
}
function fmtPop(n: number | null | undefined): string {
  // Null for a county with no KNBS census row. `String(null)` printed the
  // word "null" at the reader; the 0 the API used to send printed "0",
  // which is worse — it reads as a count.
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return String(n);
}

function getGrade(score: number | null | undefined) {
  const band = financialHealthBand(score);
  return band
    ? { letter: band.grade, cls: band.badgeClass }
    : { letter: '—', cls: 'bg-gray-200 text-gray-600' };
}

function rankedHealthScore(county: County): number | undefined {
  const score = county.financial_health_score;
  return typeof score === 'number' && financialHealthBand(score) ? score : undefined;
}

const AUDIT_STATUS_CFG: Record<
  string,
  {
    label: string;
    labelKey: TranslationKey;
  }
> = {
  clean: {
    label: 'Clean',
    labelKey: 'counties.audit_status.clean',
  },
  qualified: {
    label: 'Qualified',
    labelKey: 'counties.audit_status.qualified',
  },
  adverse: {
    label: 'Adverse',
    labelKey: 'counties.audit_status.adverse',
  },
  disclaimer: {
    label: 'Disclaimer',
    labelKey: 'counties.audit_status.disclaimer',
  },
  pending: {
    label: 'Pending',
    labelKey: 'counties.audit_status.pending',
  },
};

type SortField = 'name' | 'population' | 'health' | 'budget' | 'utilization' | 'debt';
type SortDir = 'asc' | 'desc';

/**
 * The sort column and its direction, held as one value.
 *
 * They used to be two `useState`s, which left no single place to decide both:
 * picking a direction meant calling `setSortDir` from inside the
 * `setSortField` updater. React treats updaters as pure and may call them more
 * than once — StrictMode does so deliberately — so the nested toggle ran twice
 * per click and cancelled itself, and the column headers did nothing in
 * development. One state means one updater, computing the pair from the pair.
 */
type SortState = { field: SortField; dir: SortDir };

/** Opening sort. Kept in step with `defaultFilters.sortBy` ('budget-desc'). */
const defaultSort: SortState = { field: 'budget', dir: 'desc' };

/** Which way a column opens when it first takes over the sort. */
function initialDir(field: SortField): SortDir {
  // Names read A → Z; every other column leads with its interesting end.
  return field === 'name' ? 'asc' : 'desc';
}


function KPICards({ counties }: { counties: County[] }) {
  const { t } = useLang();
  const stats = useMemo(() => {
    // Totals cover only the counties that published a figure. Summing an
    // absent one as 0 yields a total that looks complete and is silently
    // short — see lib/countyFigures.ts.
    const totalBudget = sumPublished(counties, countyBudget);
    const totalDebt = sumPublished(counties, countyDebt);
    // Average only across counties that actually reported execution — otherwise
    // the mean gets diluted by zeros and makes every year look underperforming.
    // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- comparison, not a published figure: this predicate SELECTS the reporters
    const execReporters = counties.filter((c) => (c.budgetUtilization ?? 0) > 0);
    const avgExec =
      execReporters.length > 0
        ? // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- guarded: execReporters is filtered to > 0 above, so no zero is summed
          execReporters.reduce((s, c) => s + (c.budgetUtilization ?? 0), 0) / execReporters.length
        : null;
    const auditCounts = { clean: 0, qualified: 0, adverse: 0 };
    counties.forEach((c) => {
      const st = c.auditStatus ?? 'pending';
      if (st in auditCounts) auditCounts[st as keyof typeof auditCounts]++;
    });
    const totalAudits = auditCounts.clean + auditCounts.qualified + auditCounts.adverse;
    // Only counties that published a debt figure can be ranked by it; an
    // absent figure is not a small one.
    const byDebt = counties
      .filter((c) => countyDebt(c) != null)
      .sort((a, b) => (countyDebt(b) as number) - (countyDebt(a) as number))
      .slice(0, 3);
    return {
      totalBudget,
      totalDebt,
      avgExec,
      auditCounts,
      totalAudits,
      byDebt,
    };
  }, [counties]);

  const donutData = [
    {
      name: t('counties.audit_status.clean'),
      value: stats.auditCounts.clean,
      color: '#42765d',
    },
    {
      name: t('counties.audit_status.qualified'),
      value: stats.auditCounts.qualified,
      color: '#ad8346',
    },
    {
      name: t('counties.audit_status.adverse'),
      value: stats.auditCounts.adverse,
      color: '#a85d53',
    },
  ];

  return (
    <div className={styles.summaryStrip}>
      {/* Card 1: Total Budget */}
      <Link href='/budget' className={styles.summaryMetric}>
        <div className='min-w-0'>
          <div className='text-xs font-medium text-gray-500 dark:text-neutral-muted/80 mb-1'>
            {t('counties.kpi.total_budget')}
          </div>
          <div className='text-2xl font-bold text-gray-900 dark:text-neutral-text tracking-tight'>
            {fmtKESorDash(stats.totalBudget.total)}
          </div>
          <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 font-medium mt-0.5'>
            {t('counties.kpi.across_counties').replace('{n}', String(stats.totalBudget.reported))}
          </div>
        </div>
      </Link>

      {/* Card 2: Total Debt */}
      <Link href='/budget?tab=debt' className={styles.summaryMetric}>
        <div className='min-w-0'>
          <div className='text-xs font-medium text-gray-500 dark:text-neutral-muted/80 mb-1'>
            {t('counties.kpi.total_debt')}
          </div>
          <div className='text-2xl font-bold text-gray-900 dark:text-neutral-text tracking-tight'>
            {fmtKESorDash(stats.totalDebt.total)}
          </div>
          <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 font-medium mt-0.5'>
            {t('counties.kpi.pending_bills_loans')}
          </div>
        </div>
      </Link>

      {/* Card 3: Avg. Execution Rate */}
      <div className={styles.summaryMetric}>
        <div className='min-w-0'>
          <div className='text-xs font-medium text-gray-500 dark:text-neutral-muted/80 mb-1'>
            {t('counties.kpi.avg_execution_rate')} <InfoTip term='budget-execution' size={11} />
          </div>
          {stats.avgExec != null ? (
            <>
              <div className='text-2xl font-bold text-gray-900 dark:text-neutral-text tracking-tight'>
                {stats.avgExec.toFixed(0)}%
              </div>
              <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
                {t('counties.kpi.target_70')}
              </div>
            </>
          ) : (
            <>
              <div className='text-2xl font-bold text-gray-400 dark:text-neutral-muted/80 tracking-tight'>
                —
              </div>
              <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80 mt-0.5'>
                {t('counties.kpi.not_reported')}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Card 4: Audit Summary */}
      <div className={styles.summaryMetric}>
        <div className='text-xs font-medium text-gray-500 dark:text-neutral-muted/80 mb-2'>
          {t('counties.kpi.audit_summary')}
        </div>
        {stats.totalAudits > 0 ? (
          <div className='flex flex-wrap items-center gap-3'>
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
                    isAnimationActive={false}
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
                  <span className='font-semibold text-gray-800 dark:text-neutral-text'>
                    {d.value}
                  </span>
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
      <div className={styles.summaryMetric}>
        <div className='text-xs font-medium text-gray-500 dark:text-neutral-muted/80 mb-2'>
          {t('counties.kpi.high_debt_counties')}
        </div>
        <div className='space-y-2'>
          {stats.byDebt.length === 0 && (
            <p className='text-xs text-neutral-muted'>{t('counties.kpi.not_reported')}</p>
          )}
          {stats.byDebt.map((c, i) => {
            const debt = countyDebt(c);
            const budget = countyBudget(c);
            const topDebt = countyDebt(stats.byDebt[0]);
            const auditCfg = AUDIT_STATUS_CFG[c.auditStatus ?? 'pending'];
            return (
              <Link
                key={c.id}
                href={`/counties/${c.id}?tab=budget`}
                className='flex items-center gap-2 hover:bg-white/40 dark:bg-surface-elevated -mx-1 px-1 py-0.5 rounded-lg transition-colors'>
                <span className='text-[11px] font-bold text-gray-400 dark:text-neutral-muted/80 w-3'>
                  {i + 1}
                </span>
                <div className='flex-1 min-w-0'>
                  <div className='flex items-center justify-between'>
                    <span className='text-xs font-semibold text-gray-800 dark:text-neutral-text truncate'>
                      {c.name}
                    </span>
                    <AuditStatusSignal status={c.auditStatus} label={t(auditCfg.labelKey)} />
                  </div>
                  <div className='flex items-center gap-2 mt-0.5'>
                    <span className='text-[11px] text-gray-600 dark:text-neutral-muted tabular-nums'>
                      {fmtKESorDash(debt)}
                    </span>
                    <span className='text-[11px] text-gray-400 dark:text-neutral-muted/80 tabular-nums'>
                      {fmtKESorDash(budget)}
                    </span>
                  </div>
                  <div className='h-1 bg-gray-100 dark:bg-surface-elevated rounded-full mt-1 overflow-hidden'>
                    <div
                      className='h-full bg-red-400 rounded-full'
                      style={{
                        width:
                          debt != null && topDebt != null && topDebt > 0
                            ? `${Math.min((debt / topDebt) * 100, 100)}%`
                            : '0%',
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

  return (
    <section className={styles.filters} aria-label={t('counties.filters.title')}>
      <div className={styles.filterToolbar}>
        <label className={styles.searchField}>
          <span>{t('counties.filters.search_county')}</span>
          <div>
            <Search size={17} aria-hidden='true' />
            <input
              type='search'
              value={filters.search}
              onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
              placeholder={t('counties.filters.type_to_search')}
            />
          </div>
        </label>
        <label className={styles.selectField}>
          <span>{t('counties.filter.region')}</span>
          <select
            value={filters.region}
            onChange={(e) => setFilters((f) => ({ ...f, region: e.target.value }))}>
            <option value='all'>{t('counties.filters.all_regions')}</option>
            {(
              [
                'central',
                'coast',
                'eastern',
                'nairobi',
                'north-eastern',
                'nyanza',
                'rift-valley',
                'western',
              ] as const
            ).map((r) => (
              <option key={r} value={r}>
                {t(`counties.region.${r.replace(/-/g, '_')}` as TranslationKey)}
              </option>
            ))}
          </select>
        </label>
        <button
          className={styles.filterToggle}
          onClick={() => setCollapsed(!collapsed)}
          aria-expanded={!collapsed}
          aria-controls='county-filter-options'>
          <Filter size={16} aria-hidden='true' />
          {t('counties.filters.title')}
          <ChevronDown size={14} aria-hidden='true' />
        </button>
      </div>
      {!collapsed && (
        <div id='county-filter-options' className={styles.filterOptions}>
          <fieldset>
            <legend>{t('counties.filters.grade')}</legend>
            <div className={styles.gradeChoices}>
              {FINANCIAL_HEALTH_BANDS.map(({ grade: g }) => (
                <button
                  key={g}
                  aria-pressed={filters.grades.includes(g)}
                  onClick={() => toggleGrade(g)}>
                  {g}
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend>
              {t('counties.filters.audit_status')} <InfoTip term='audit-clean' size={11} />
            </legend>
            <div className={styles.auditChoices}>
              {(['clean', 'qualified', 'adverse'] as const).map((status) => (
                <label key={status}>
                  <input
                    type='checkbox'
                    checked={filters.auditStatuses.includes(status)}
                    onChange={() => toggleAudit(status)}
                  />
                  {t(AUDIT_STATUS_CFG[status].labelKey)}
                </label>
              ))}
            </div>
          </fieldset>
          <label className={styles.rangeField}>
            <span>{t('counties.filters.spending_range')}</span>
            <input
              type='range'
              min={0}
              max={150}
              value={filters.spendingRange[1]}
              onChange={(e) =>
                setFilters((f) => ({
                  ...f,
                  spendingRange: [0, Number(e.target.value)],
                }))
              }
            />
            <span>KES 0B — {filters.spendingRange[1]}B+</span>
          </label>
          <label className={styles.selectField}>
            <span>{t('counties.filter.sort')}</span>
            <select
              value={filters.sortBy}
              onChange={(e) => setFilters((f) => ({ ...f, sortBy: e.target.value }))}>
              {(
                [
                  'budget-desc',
                  'budget-asc',
                  'debt-desc',
                  'population-desc',
                  'population-asc',
                  'health-desc',
                  'utilization-desc',
                ] as const
              ).map((value, i) => (
                <option key={value} value={value}>
                  {t(
                    [
                      'counties.sort.budget_high_low',
                      'counties.sort.budget_low_high',
                      'counties.sort.debt_high_low',
                      'counties.sort.population_high_low',
                      'counties.sort.population_low_high',
                      'counties.sort.grade_best_worst',
                      'counties.sort.execution_high_low',
                    ][i] as TranslationKey
                  )}
                </option>
              ))}
            </select>
          </label>
          <div className={styles.filterActions}>
            <button onClick={onApply}>{t('counties.filters.apply')}</button>
            <button onClick={onReset}>{t('counties.filters.reset')}</button>
          </div>
        </div>
      )}
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   KENYA CHOROPLETH MAP — Real county boundaries colored by grade
   ══════════════════════════════════════════════════════════════════════════════ */

import { KENYA_COUNTY_PATHS } from '@/data/kenya-county-paths';

function CountyPerformanceMap({
  counties,
  allCounties,
  activeGrades,
  onToggleGrade,
  selectedRegion,
  fiscalYear,
}: {
  counties: County[]; // filtered counties (for highlight)
  allCounties: County[]; // all counties (always render all polygons)
  activeGrades: string[];
  onToggleGrade: (grade: string) => void;
  selectedRegion: string;
  fiscalYear?: string;
}) {
  const { t } = useLang();
  const router = useRouter();
  const [hoveredCountyId, setHoveredCountyId] = useState<County['id'] | null>(null);
  const [hoveredGadm, setHoveredGadm] = useState<string | null>(null);

  // Build lookup for ALL counties (so all polygons get colored)
  const allLookup = useMemo(() => {
    const map = new Map<string, County>();
    allCounties.forEach((c) => {
      map.set(normalizeCountyName(c.name), c);
    });
    return map;
  }, [allCounties]);

  // Build set of filtered county names (for highlight control)
  const filteredNames = useMemo(() => {
    const set = new Set<string>();
    counties.forEach((c) => set.add(normalizeCountyName(c.name)));
    return set;
  }, [counties]);

  // Compute region bounding box for zoom
  const regionViewBox = useMemo(() => {
    if (selectedRegion === 'all') return '0 0 360 400';
    // find county paths that belong to this region
    const regionPaths = KENYA_COUNTY_PATHS.filter((cp) => {
      const county = allLookup.get(normalizeCountyName(cp.name));
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

  // Resolve from the current period and filters; never retain a previous year's figures.
  const inspected = counties.find((county) => county.id === hoveredCountyId) ?? counties[0] ?? null;
  const countyHref = (county: County) =>
    `/counties/${county.id}${fiscalYear ? `?fy=${encodeURIComponent(fiscalYear)}` : ''}`;
  return (
    <section aria-labelledby='county-map-title'>
      <header className={styles.sectionHeading}>
        <h2 id='county-map-title'>{t('counties.map.title')}</h2>
        <span>{fiscalYear}</span>
      </header>
      <div className={styles.mapCanvas}>
        <svg viewBox={regionViewBox} className={styles.mapSvg} aria-label={t('counties.map.title')}>
          {KENYA_COUNTY_PATHS.map((cp) => {
            const county = allLookup.get(normalizeCountyName(cp.name));
            const band = county ? financialHealthBand(county.financial_health_score) : null;
            const fill = band?.fill ?? '#b8bcb2';
            const dimmed =
              !filteredNames.has(normalizeCountyName(cp.name)) ||
              (activeGrades.length > 0 && (!band || !activeGrades.includes(band.grade)));
            const interactive = county != null && !dimmed;
            return (
              <path
                key={cp.name}
                d={cp.path}
                fill={fill}
                stroke='var(--county-map-boundary)'
                strokeWidth={interactive && hoveredGadm === cp.name ? 1.8 : 0.7}
                opacity={dimmed ? 0.2 : 1}
                role={interactive ? 'link' : undefined}
                tabIndex={interactive ? 0 : undefined}
                aria-label={
                  county
                    ? `${county.name}, ${t('counties.map.tooltip_grade')}: ${getGrade(county.financial_health_score).letter}`
                    : cp.name
                }
                onClick={() => {
                  if (interactive) router.push(countyHref(county));
                }}
                onKeyDown={(e) => {
                  if (interactive && e.key === 'Enter') router.push(countyHref(county));
                }}
                onFocus={() => {
                  if (interactive) {
                    setHoveredCountyId(county.id);
                    setHoveredGadm(cp.name);
                  }
                }}
                onMouseEnter={() => {
                  if (interactive) {
                    setHoveredCountyId(county.id);
                    setHoveredGadm(cp.name);
                  }
                }}>
                <title>{county?.name ?? cp.name}</title>
              </path>
            );
          })}
        </svg>
      </div>
      <div className={styles.mapReadout}>
        {inspected && (
          <>
            <Link href={countyHref(inspected)}>
              {inspected.name}
              <span aria-hidden='true'>↗</span>
            </Link>
            <dl>
              <div>
                <dt>{t('counties.map.tooltip_grade')}</dt>
                <dd>{getGrade(inspected.financial_health_score).letter}</dd>
              </div>
              <div>
                <dt>{t('counties.map.tooltip_exec')}</dt>
                <dd>
                  {inspected.budgetUtilization != null
                    ? `${inspected.budgetUtilization.toFixed(0)}%`
                    : '—'}
                </dd>
              </div>
              <div>
                <dt>{t('counties.map.tooltip_budget')}</dt>
                <dd>
                  {countyBudget(inspected) != null
                    ? `KES ${fmtKES(countyBudget(inspected) as number)}`
                    : '—'}
                </dd>
              </div>
            </dl>
          </>
        )}
      </div>
      <div className={styles.mapLegend}>
        <span>{t('counties.map.performance')}:</span>
        {FINANCIAL_HEALTH_BANDS.map(({ grade: g, fill }) => (
          <button
            key={g}
            onClick={() => onToggleGrade(g)}
            aria-pressed={activeGrades.includes(g)}
            style={{ '--grade-color': fill } as React.CSSProperties}>
            <i aria-hidden='true' />
            {g}
          </button>
        ))}
        {activeGrades.length > 0 && (
          <button onClick={() => activeGrades.forEach(onToggleGrade)}>
            {t('counties.map.clear')}
          </button>
        )}
      </div>
    </section>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   COUNTY INSIGHTS PANEL — replaces separate Top Performers / High Debt
   Shows best & worst performers (no overlap) + region summary stats
   ══════════════════════════════════════════════════════════════════════════════ */

function CountyInsightsPanel({ counties }: { counties: County[] }) {
  const { t } = useLang();

  const { best, worst, stats } = useMemo(() => {
    // Only assessed counties can be described as best or needing attention.
    const sorted = counties.filter((c) => rankedHealthScore(c) != null).sort((a, b) =>
      compareByPublishedFigure(a, b, rankedHealthScore, 'desc')
    );
    const scoredCount = sorted.length;
    // Take top 3 and bottom 3 without overlap.
    const takeTop = Math.min(3, Math.ceil(scoredCount / 2));
    const takeBottom = Math.min(3, scoredCount - takeTop);
    const bestList = sorted.slice(0, takeTop);
    const worstList = takeBottom > 0 ? sorted.slice(scoredCount - takeBottom).reverse() : [];

    const totalBudget = sumPublished(counties, countyBudget);
    const totalDebt = sumPublished(counties, countyDebt);
    // Average only across counties that actually reported execution — a
    // non-reporter is not a county that executed 0% of its budget.
    const utilReporters = counties.filter((c) => c.budgetUtilization != null);
    const avgUtil =
      utilReporters.length > 0
        ? utilReporters.reduce((s, c) => s + (c.budgetUtilization as number), 0) /
          utilReporters.length
        : null;
    // Same rule as avgUtil above: a county with no score is not a county
    // that scored zero.
    const healthReporters = counties.filter((c) => financialHealthBand(c.financial_health_score));
    const avgHealth =
      healthReporters.length > 0
        ? healthReporters.reduce((s, c) => s + (c.financial_health_score as number), 0) /
          healthReporters.length
        : null;

    return {
      best: bestList,
      worst: worstList,
      stats: { totalBudget, totalDebt, avgUtil, avgHealth, count: counties.length },
    };
  }, [counties]);

  if (counties.length === 0) {
    return <div className={styles.insights}>{t('counties.insights.no_match')}</div>;
  }

  // The backend rounds individual health scores to one decimal before grading.
  // Grade the displayed one-decimal regional mean by the same convention.
  const displayedAvgHealth =
    stats.avgHealth == null ? null : Math.round((stats.avgHealth + Number.EPSILON) * 10) / 10;
  const avgHealthGrade = getGrade(displayedAvgHealth);

  return (
    <div className={styles.insights}>
      {/* Region summary bar */}
      <div className='flex items-center gap-4 mb-4 pb-3 border-b border-gray-200/60 dark:border-neutral-border/60 flex-wrap'>
        <span className='text-sm font-bold text-gray-900 dark:text-neutral-text'>
          {stats.count} {stats.count === 1 ? t('common.county') : t('common.counties')}
        </span>
        <div className='flex items-center gap-1.5 text-xs text-gray-500 dark:text-neutral-muted/80'>
          <span className='font-semibold text-gray-700 dark:text-neutral-muted'>
            {t('counties.insights.budget')}:
          </span>
          <span className='tabular-nums'>{fmtKESorDash(stats.totalBudget.total)}</span>
        </div>
        <div className='flex items-center gap-1.5 text-xs text-gray-500 dark:text-neutral-muted/80'>
          <span className='font-semibold text-gray-700 dark:text-neutral-muted'>
            {t('counties.insights.debt')}:
          </span>
          <span className='tabular-nums text-red-600'>{fmtKESorDash(stats.totalDebt.total)}</span>
        </div>
        <div className='flex items-center gap-1.5 text-xs text-gray-500 dark:text-neutral-muted/80'>
          <span className='font-semibold text-gray-700 dark:text-neutral-muted'>
            {t('counties.insights.avg_exec')}:
          </span>
          <span className='tabular-nums'>
            {stats.avgUtil != null ? `${stats.avgUtil.toFixed(0)}%` : '—'}
          </span>
        </div>
        <div className='flex items-center gap-1.5 text-xs'>
          <span className='font-semibold text-gray-700 dark:text-neutral-muted'>
            {t('counties.insights.avg_health')}:
          </span>
          <span
            className={`px-1.5 py-0.5 rounded font-bold text-[11px] ${
              avgHealthGrade.cls
            }`}>
            {displayedAvgHealth == null
              ? '—'
              : `${avgHealthGrade.letter} (${displayedAvgHealth.toFixed(1)})`}
          </span>
        </div>
      </div>

      {best.length === 0 ? (
        <p className='text-sm text-gray-500 dark:text-neutral-muted'>
          {t('counties.insights.no_health_scores')}
        </p>
      ) : (
        <div className={styles.insightGroups}>
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
          {worst.length > 0 && (
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
          )}
        </div>
      )}
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
  const util = c.budgetUtilization;
  const debt = countyDebt(c);
  const budget = countyBudget(c);
  const health = c.financial_health_score;
  const grade = getGrade(health);
  const ratio = countyDebtRatio(c);
  const debtRatio = ratio != null ? ratio.toFixed(0) : null;
  const auditCfg = AUDIT_STATUS_CFG[c.auditStatus ?? 'pending'];

  return (
    <Link href={`/counties/${c.id}`} className={styles.insightRow}>
      <span className='text-xs font-bold text-gray-400 dark:text-neutral-muted/80 w-3 text-right'>
        {rank}
      </span>
      <div className='flex-1 min-w-0'>
        <div className='flex flex-wrap items-center gap-2 mb-0.5'>
          <span className='text-sm font-semibold text-gray-800 dark:text-neutral-text truncate'>
            {c.name}
          </span>
          <span className={`text-[11px] font-bold px-1.5 py-0.5 rounded ${grade.cls}`}>
            {grade.letter}
          </span>
          <AuditStatusSignal
            status={c.auditStatus}
            label={t(auditCfg.labelKey)}
            className='ml-auto'
          />
        </div>
        <div className='flex items-center gap-3'>
          {/* Utilization bar */}
          <div className='flex items-center gap-1.5 flex-1'>
            <span className='text-[11px] text-gray-500 dark:text-neutral-muted/80 w-7'>
              {t('counties.insights.exec_short')}
            </span>
            <div className='flex-1 h-1.5 bg-gray-100 dark:bg-surface-elevated rounded-full overflow-hidden'>
              <div
                className={`h-full rounded-full ${
                  util == null
                    ? 'bg-gray-200 dark:bg-neutral-700'
                    : util >= 70
                      ? 'bg-emerald-500'
                      : util >= 50
                        ? 'bg-amber-500'
                        : 'bg-red-400'
                }`}
                style={{
                  width: util == null ? '100%' : `${Math.min(util, 100)}%`,
                }}
              />
            </div>
            <span className='text-[11px] font-semibold text-gray-700 dark:text-neutral-muted w-7 tabular-nums'>
              {util != null ? `${util.toFixed(0)}%` : '—'}
            </span>
          </div>
          {/* Debt ratio */}
          <div className='flex items-center gap-1.5'>
            <span className='text-[11px] text-gray-500 dark:text-neutral-muted/80'>
              {t('counties.insights.debt_short')}
            </span>
            <span
              className={`text-[11px] font-bold tabular-nums ${
                ratio != null && ratio > 50
                  ? 'text-red-600'
                  : 'text-gray-600 dark:text-neutral-muted'
              }`}>
              {debtRatio != null ? `${debtRatio}%` : '—'}
            </span>
            <span className='text-[11px] text-gray-400 dark:text-neutral-muted/80 tabular-nums'>
              {fmtKESorDash(budget)}
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   EXECUTION BAR
   ══════════════════════════════════════════════════════════════════════════════ */

function ExecBar({ pct }: { pct: number | null | undefined }) {
  // A county that reported no execution is not a county that executed 0%.
  if (pct == null) {
    return <span className='text-xs text-gray-400 dark:text-neutral-muted/80'>—</span>;
  }
  const clamped = Math.min(pct, 100);
  const clr = pct >= 70 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className='flex items-center gap-2'>
      <div className='w-20 h-2 bg-gray-100 dark:bg-surface-elevated rounded-full overflow-hidden'>
        <div className={`h-full rounded-full ${clr}`} style={{ width: `${clamped}%` }} />
      </div>
      <span className='text-xs tabular-nums text-gray-700 dark:text-neutral-muted w-8'>
        {pct.toFixed(0)}%
      </span>
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
      tabIndex={0}
      aria-sort={active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSort(field);
        }
      }}
      className={`text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-neutral-muted/80 py-3 px-3 cursor-pointer select-none hover:text-gray-800 dark:text-neutral-text transition-colors whitespace-nowrap ${className}`}
      onClick={() => onSort(field)}>
      <span className='inline-flex items-center gap-1'>
        {children}
        {suffix && (
          <span className='text-[11px] text-gray-400 dark:text-neutral-muted/80 font-normal normal-case tracking-normal'>
            {suffix}
          </span>
        )}
        <ArrowUpDown
          size={11}
          className={
            active
              ? 'text-gov-forest dark:text-emerald-100'
              : 'text-gray-300 dark:text-neutral-muted/60'
          }
        />
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

const subscribeToNothing = () => () => {};

/**
 * True while React is hydrating server HTML, false on every other render.
 * `useSyncExternalStore` answers with the server snapshot during hydration
 * (and on the server) and the client snapshot otherwise.
 */
function useIsHydrating(): boolean {
  return useSyncExternalStore(
    subscribeToNothing,
    () => false,
    () => true
  );
}

/**
 * Calls `onChange` on mount and whenever `useSearchParams()` changes identity,
 * i.e. when a Next.js navigation changes the query without remounting the
 * route or firing popstate. Renders nothing.
 *
 * It exists to quarantine the hook: on a statically prerendered route
 * `useSearchParams()` bails its subtree out to client-side rendering, up to
 * the nearest Suspense boundary. Rendered behind its own
 * `<Suspense fallback={null}>`, the subtree that bails out is this null leaf,
 * and the page around it server-renders.
 */
function SearchParamsChange({ onChange }: { onChange: () => void }) {
  const searchParams = useSearchParams();
  useEffect(() => {
    onChange();
  }, [searchParams, onChange]);
  return null;
}

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
  /** The year the list is showing, or undefined while the API has not said
   *  which one that is. Undefined omits ?fy= from the row links, which leaves
   *  the detail page to resolve the period itself — the same period this list
   *  is showing, since both go through the API's own rule. */
  fiscalYear: string | undefined;
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
  //
  // The hook is still what tells us a Next.js navigation changed the query,
  // but it is called in `SearchParamsChange` below, never here: on this
  // statically prerendered route, calling it anywhere in the page bails the
  // render out to the client up to the nearest Suspense boundary — which was
  // `loading.tsx`'s, so the whole explorer and its LCP element were missing
  // from the served HTML (#221 finding #3).
  const router = useRouter();
  const pathname = usePathname();

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

  // The prerendered document is built once, with no query string, and served
  // for /counties?p=3 too. While hydrating it, the first render must produce
  // what the server did — page 1, paginated — or React discards the server
  // HTML as a mismatch. The URL takes over one effect later, via
  // `SearchParamsChange`'s mount. A client-side mount (back from a county
  // page) is not hydrating and reads the URL straight away, so the list the
  // reader left is on screen in the first commit, which is what the browser
  // restores scroll against.
  const hydrating = useIsHydrating();
  const [pageFromUrl, setPageFromUrl] = useState<number>(() => (hydrating ? 1 : readPageFromUrl()));
  const [showAll, setShowAllLocal] = useState<boolean>(() =>
    hydrating ? false : readShowAllFromUrl()
  );

  const syncFromUrl = useCallback(() => {
    setPageFromUrl(readPageFromUrl());
    setShowAllLocal(readShowAllFromUrl());
  }, [readPageFromUrl, readShowAllFromUrl]);

  // Keep local mirrors in sync with browser history (back/forward, manual edits).
  useEffect(() => {
    window.addEventListener('popstate', syncFromUrl);
    return () => window.removeEventListener('popstate', syncFromUrl);
  }, [syncFromUrl]);

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
      router.replace(newSearch ? `${pathname}?${newSearch}` : pathname, {
        scroll: false,
      });
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
      router.replace(newSearch ? `${pathname}?${newSearch}` : pathname, {
        scroll: false,
      });
      setShowAllLocal(resolved);
    },
    [showAll, pathname, router]
  );

  // Normalize an out-of-range URL to the same last page the table renders,
  // including when filters or a new period shrink the list. Leave valid
  // pages, View All and empty results alone so navigation state survives.
  useEffect(() => {
    // SearchParamsChange may be syncing a new navigation in this same commit.
    // Do not let the old local mirrors overwrite its newly requested URL.
    if (pageFromUrl !== readPageFromUrl() || showAll !== readShowAllFromUrl()) return;
    if (!showAll && pageFromUrl > totalPages && totalPages >= 1) {
      setPage(page);
    }
  }, [totalPages, pageFromUrl, page, showAll, setPage, readPageFromUrl, readShowAllFromUrl]);

  const pageNums = useMemo(() => {
    const nums: number[] = [];
    const start = Math.max(1, page - 2);
    const end = Math.min(totalPages, start + 4);
    for (let i = start; i <= end; i++) nums.push(i);
    return nums;
  }, [page, totalPages]);

  return (
    <div className={styles.rankings}>
      {/* Resyncs on mount and whenever a Next.js navigation changes the query.
          Its own boundary keeps the client-only render to this empty leaf. */}
      <Suspense fallback={null}>
        <SearchParamsChange onChange={syncFromUrl} />
      </Suspense>
      <div className='flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-neutral-border'>
        <div className='flex items-center gap-2'>
          <h3 className='text-sm font-bold text-gray-900 dark:text-neutral-text'>
            {t('counties.rankings.title')}
          </h3>
          <span className='text-xs text-gray-400 dark:text-neutral-muted/80'>
            (
            {t('counties.rankings.range_of')
              .replace('{from}', String((page - 1) * PAGE_SIZE + 1))
              .replace('{to}', String(Math.min(page * PAGE_SIZE, counties.length)))
              .replace('{total}', String(counties.length))}
            )
          </span>
        </div>
      </div>

      <div className={styles.mobileSort}>
        <label className={styles.selectField}>
          <span>{t('counties.filter.sort')}</span>
          <select
            aria-label={`${t('counties.rankings.title')} — ${t('counties.filter.sort')}`}
            value={sortField}
            onChange={(event) => onSort(event.target.value as SortField)}>
            {(
              [
                ['name', 'counties.rankings.col_county'],
                ['population', 'counties.rankings.col_population'],
                ['health', 'counties.rankings.col_health'],
                ['budget', 'counties.rankings.col_budget'],
                ['utilization', 'counties.rankings.col_execution'],
                ['debt', 'counties.rankings.col_debt'],
              ] as const
            ).map(([field, label]) => (
              <option key={field} value={field}>
                {t(label)}
              </option>
            ))}
          </select>
        </label>
        <button
          className={styles.exportButton}
          onClick={() => onSort(sortField)}
          aria-label={t('counties.sort.reverse_direction')}>
          <span aria-hidden='true'>{sortDir === 'asc' ? '↑' : '↓'}</span>
          {t(sortDir === 'asc' ? 'counties.sort.ascending' : 'counties.sort.descending')}
        </button>
      </div>
      <ResponsiveTable className={styles.rankingsTable}>
        <table className='w-full border-collapse' aria-label={t('counties.rankings.title')}>
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
              const budget = countyBudget(county);
              const debt = countyDebt(county);
              const util = county.budgetUtilization;
              const grade = getGrade(county.financial_health_score);
              const issues = county.auditIssues?.length ?? 0;
              const auditCfg = AUDIT_STATUS_CFG[county.auditStatus ?? 'pending'];
              // No ?fy= when the year is not yet known: pinning a period we
              // cannot name would be a guess, and the detail page resolves the
              // same one on its own.
              const base = fiscalYear
                ? `/counties/${county.id}?fy=${encodeURIComponent(fiscalYear)}`
                : `/counties/${county.id}`;
              const rank = showAll ? i + 1 : (page - 1) * PAGE_SIZE + i + 1;

              return (
                <tr
                  key={county.id}
                  className='group border-b border-gray-50 dark:border-neutral-border last:border-0 hover:bg-gov-forest/[0.025] transition-colors cursor-pointer'>
                  <td
                    data-label='#'
                    className='py-3 px-4 text-xs text-gray-400 dark:text-neutral-muted/80 tabular-nums'>
                    {rank}
                  </td>
                  <td data-label={t('counties.rankings.col_county')} className='py-3 px-3'>
                    <Link href={base} className='flex items-center gap-2'>
                      <span className={styles.mobileRank}>{rank}</span>
                      <span className='font-semibold text-sm text-gray-900 dark:text-neutral-text group-hover:text-gov-forest dark:text-emerald-100 transition-colors'>
                        {county.name}
                      </span>
                    </Link>
                  </td>
                  <td
                    data-label={t('counties.rankings.col_population')}
                    className='py-3 px-3 text-sm text-gray-600 dark:text-neutral-muted tabular-nums'>
                    <Link href={base} className='block'>
                      {fmtPop(county.population)}
                    </Link>
                  </td>
                  <td data-label={t('counties.rankings.col_health')} className='py-3 px-3'>
                    <Link
                      href={`${base}${base.includes('?') ? '&' : '?'}tab=budget`}
                      className='block'>
                      <span
                        className={`inline-flex items-center justify-center w-8 h-6 text-[11px] font-bold rounded-md ${grade.cls}`}>
                        {grade.letter}
                      </span>
                    </Link>
                  </td>
                  <td data-label={t('counties.rankings.col_budget')} className='py-3 px-3'>
                    <Link
                      href={`${base}${base.includes('?') ? '&' : '?'}tab=budget`}
                      className='block text-sm text-gray-700 dark:text-neutral-muted tabular-nums font-medium hover:text-gov-forest dark:text-emerald-100 transition-colors'>
                      {fmtKESorDash(budget)}
                    </Link>
                    <FigureEvidence label={`${county.name} budget`} rows={county.figureQualifications?.budget_lines} table="budget_lines" />
                  </td>
                  <td data-label={t('counties.rankings.col_execution')} className='py-3 px-3'>
                    <Link
                      href={`${base}${base.includes('?') ? '&' : '?'}tab=budget`}
                      className='block'>
                      <ExecBar pct={util} />
                    </Link>
                  </td>
                  <td data-label={t('counties.rankings.col_debt')} className='py-3 px-3'>
                    <Link
                      href={`${base}${base.includes('?') ? '&' : '?'}tab=budget`}
                      className='flex items-center gap-1.5 text-sm text-gray-700 dark:text-neutral-muted tabular-nums hover:text-gov-forest dark:text-emerald-100 transition-colors'>
                      <span
                        className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                          debt == null
                            ? 'bg-gray-300'
                            : debt > 50e9
                              ? 'bg-red-500'
                              : debt > 15e9
                                ? 'bg-amber-500'
                                : 'bg-emerald-500'
                        }`}
                      />
                      {fmtKESorDash(debt)}
                    </Link>
                  </td>
                  <td data-label={t('counties.rankings.col_audit')} className='py-3 px-3'>
                    <Link
                      href={`${base}${base.includes('?') ? '&' : '?'}tab=audit`}
                      className='flex items-center gap-1.5'>
                      <AuditStatusSignal status={county.auditStatus} label={t(auditCfg.labelKey)} />
                      {issues > 0 && (
                        <span className='text-[11px] text-gray-500 dark:text-neutral-muted/80 font-medium'>
                          ({issues})
                        </span>
                      )}
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </ResponsiveTable>

      {counties.length === 0 && (
        <div className='text-center py-12 px-4'>
          <Search size={28} className='mx-auto text-gray-300 dark:text-neutral-muted/60 mb-2' />
          <p className='text-sm text-gray-500 dark:text-neutral-muted/80'>
            {t('counties.rankings.no_match')}
          </p>
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
            <div className='flex flex-wrap items-center justify-center gap-1'>
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
                    n === page
                      ? 'bg-gov-forest text-white'
                      : 'text-gray-600 dark:text-neutral-muted hover:bg-gray-100 dark:bg-surface-elevated'
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
  // Year dropdown state (must be declared before useCounties which depends on it).
  //
  // This used to seed from generateFiscalYears(4) / getLatestReportedFiscalYear(),
  // both computed from `new Date()` with no reference to what the database
  // holds. In September 2026 that named FY2025/26 — the CRA equitable-share
  // projection — so the explorer asked for that year and published Baringo at
  // KES 7.13B, while the county's own page sent no year, let the API resolve
  // the period from the rows that exist, and published KES 9.54B from the
  // Controller of Budget's CBIRR. Same county, same site, two budgets
  // (credibility audit F7, reopened through this explicit fiscal_year).
  //
  // The API now reports which years county budget data exists for and which
  // one it resolves to by default, by the same rule GET /counties applies when
  // given no year. Only a year the reader picks is sent — until then the query
  // goes unparameterised and the backend chooses, so the label below and the
  // figures on screen are always the same period.
  const { data: fiscalYearsMeta } = useCountyFiscalYears();
  const YEARS = fiscalYearsMeta?.years.map((y) => y.label) ?? [];
  const [pickedYear, setPickedYear] = useState<string | undefined>(undefined);
  const selectedYear = resolveExplorerYear(pickedYear, fiscalYearsMeta);

  const { data: counties, isLoading, error, refetch } = useCounties({ fiscalYear: pickedYear });

  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);

  const [sort, setSort] = useState<SortState>(defaultSort);
  const { field: sortField, dir: sortDir } = sort;

  // NOTE: "View All" toggle state now lives inside CountyRankingsTable
  // and is URL-driven via ?view=all so that back-navigation from a
  // county detail page restores the full-list view.

  // Grade filter driven by the map legend
  const [mapGrades, setMapGrades] = useState<string[]>([]);
  const handleToggleMapGrade = useCallback((g: string) => {
    setMapGrades((prev) => (prev.includes(g) ? prev.filter((x) => x !== g) : [...prev, g]));
  }, []);

  // Clicking the active column flips it; clicking any other takes it over at
  // that column's opening direction. Both come out of one pure updater, so it
  // is safe for React to call this twice with the same `prev`.
  const handleSort = useCallback((field: SortField) => {
    setSort((prev) => ({
      field,
      dir: prev.field === field ? (prev.dir === 'asc' ? 'desc' : 'asc') : initialDir(field),
    }));
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
    const field = fieldMap[sf];
    const dir = sd === 'asc' || sd === 'desc' ? sd : undefined;
    if (!field && !dir) return;
    // Each half still falls back to what the sort already had, so a value the
    // select does not spell out in full changes only the half it names.
    setSort((prev) => ({ field: field ?? prev.field, dir: dir ?? prev.dir }));
  }, [filters.sortBy]);

  const handleApply = useCallback(() => {
    // Filters now apply immediately — this is a no-op kept for the sidebar interface
  }, []);

  const handleReset = useCallback(() => {
    setFilters(defaultFilters);
    setSort(defaultSort);
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
      list = list.filter((c) => {
        const grade = financialHealthBand(c.financial_health_score)?.grade;
        return grade != null && filters.grades.includes(grade);
      });
    }

    // Map-legend grade filter (applied independently of sidebar)
    if (mapGrades.length > 0) {
      list = list.filter((c) => {
        const grade = financialHealthBand(c.financial_health_score)?.grade;
        return grade != null && mapGrades.includes(grade);
      });
    }

    if (filters.auditStatuses.length > 0) {
      list = list.filter((c) => filters.auditStatuses.includes(c.auditStatus ?? 'pending'));
    }

    if (filters.spendingRange[1] < 150) {
      const maxB = filters.spendingRange[1] * 1e9;
      // A county whose budget was never published is kept rather than judged
      // against a figure it does not have.
      list = list.filter((c) => {
        const b = countyBudget(c);
        return b == null || b <= maxB;
      });
    }

    list.sort((a, b) => {
      // Handled whole rather than through the direction flip below, so a
      // county with no published figure sinks in BOTH directions.
      const pick = RANKED_FIGURE[sortField];
      if (pick) return compareByPublishedFigure(a, b, pick, sortDir);
      if (sortField === 'health') {
        return compareByPublishedFigure(a, b, rankedHealthScore, sortDir);
      }

      let cmp = 0;
      switch (sortField) {
        case 'name':
          cmp = a.name.localeCompare(b.name);
          break;

        case 'utilization':
          // eslint-disable-next-line local/no-zero-fallback-on-published-figure -- ordering only: sorts unreported counties last, publishes nothing
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
      c.population ?? '',
      getGrade(c.financial_health_score).letter,
      countyBudget(c) ?? '',
      c.budgetUtilization != null ? c.budgetUtilization.toFixed(1) : '',
      countyDebt(c) ?? '',
      c.auditStatus ?? 'pending',
    ]);
    const csv = [headers, ...rows].map((r) => r.map((v) => `"${v}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `county_data_${(selectedYear ?? 'unspecified-fy').replace('/', '-')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [filtered, selectedYear]);

  if (isLoading || error || !counties) {
    return (
      <div className={styles.explorer}>
        <div className={styles.container}>
          <header className={styles.explorerHeader}>
            <div>
              <p className={styles.eyebrow}>AuditGava / county evidence</p>
              <h1>{t('counties.title')}</h1>
              {isLoading && <p className={styles.intro}>Loading the latest county evidence…</p>}
            </div>
          </header>
          <div className={styles.pageState} style={isLoading ? { minHeight: 1200 } : undefined}>
            {isLoading ? (
              <div className='animate-spin rounded-full h-8 w-8 border-b-2 border-gov-forest' />
            ) : (
              <>
                <AlertTriangle size={28} aria-hidden='true' />
                <p>{t('counties.error.title')}</p>
                <button onClick={() => refetch()} className={styles.exportButton}>
                  {t('counties.header.retry')}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.explorer}>
      <div className={styles.container}>
        <header className={styles.explorerHeader}>
          <div>
            <p className={styles.eyebrow}>AuditGava / county evidence</p>
            <h1>{t('counties.title')}</h1>
            <p className={styles.intro}>
              {t('counties.header.subtitle_rich').replace(
                '{strong}',
                t('counties.header.subtitle_strong')
              )}
            </p>
          </div>
          <div className={styles.headerActions}>
            {YEARS.length > 0 && (
              <label className={styles.selectField}>
                <span>{t('counties.header.year')}</span>
                <select value={selectedYear ?? ''} onChange={(e) => setPickedYear(e.target.value)}>
                  {YEARS.map((y) => (
                    <option key={y} value={y}>
                      {y}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button onClick={handleExport} className={styles.exportButton}>
              <Download size={16} aria-hidden='true' />
              {t('counties.header.export')}
            </button>
          </div>
        </header>
        <DataFreshnessBadge sources='COB' variant='banner' className={styles.freshness} />
        <ModelledDataNote
          className={styles.provenance}
          budgetSource={filtered.map((c) => c.budgetSource)}
        />
        <KPICards counties={counties} />
        <FiltersSidebar
          filters={filters}
          setFilters={setFilters}
          collapsed={sidebarCollapsed}
          setCollapsed={setSidebarCollapsed}
          onApply={handleApply}
          onReset={handleReset}
        />
        <div className={styles.atlasLayout}>
          <CountyPerformanceMap
            counties={filtered}
            allCounties={counties}
            activeGrades={mapGrades}
            onToggleGrade={handleToggleMapGrade}
            selectedRegion={filters.region}
            fiscalYear={selectedYear}
          />
          <CountyInsightsPanel counties={filtered} />
        </div>
        <CountyRankingsTable
          counties={filtered}
          sortField={sortField}
          sortDir={sortDir}
          onSort={handleSort}
          fiscalYear={selectedYear}
        />
        <DataFreshnessBadge sources='COB' className={styles.sourceFooter} />
      </div>
    </div>
  );
}
