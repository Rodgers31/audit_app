'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import { countySpendingMessages } from '@/lib/i18n/messages/transparency';
import CountySpendingDistribution from './CountySpendingDistribution';
import { ArrowDown, ArrowUp, ArrowUpDown, Search, X } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useId, useRef, useState, type CSSProperties } from 'react';
import {
  auditAmountCoverageNote,
  COUNTY_SPENDING_TARGET as TARGET,
  formatEfficiency,
  formatFlowKES,
  type CountyFlowRow,
  type CountySpendingPoint,
  type CountySortKey,
} from './moneyFlowPresentation';
import styles from './MoneyFlowPresentation.module.css';

const INITIAL_COUNT = 10;
const executionBands = [
  { min: 0, verdict: 'wellBelow', range: 'below65' },
  { min: 65, verdict: 'below', range: 'below70' },
  { min: TARGET, verdict: 'onTarget', range: 'below80' },
  { min: 80, verdict: 'above', range: 'atLeast80' },
] as const;
const highestBandFirst = [...executionBands].reverse();
const headingLabels = {
  name: 'headingCounty',
  efficiency: 'headingSpent',
  gap: 'unspent',
  flagged: 'auditQuestioned',
  allocated: 'headingAllocated',
} as const;

interface Props {
  rows: (CountyFlowRow & { rank: number })[];
  fiscalYear: string;
  countiesWithData: number;
  distribution: CountySpendingPoint[];
  distributionNational: number | null;
  nationalEfficiency: number | null;
  nationalAllocated: number | null;
  projected: boolean;
  loading: boolean;
  error: boolean;
  auditUnavailable: boolean;
  search: string;
  onSearch: (query: string) => void;
  sortKey: CountySortKey;
  reversed: boolean;
  onSort: (sort: CountySortKey) => void;
  onReverse: () => void;
}

function Amount({ amount, unavailable }: { amount: number | null; unavailable: string }) {
  return <b aria-label={amount == null ? unavailable : undefined}>{formatFlowKES(amount)}</b>;
}

function percentWidth(percent: number) {
  return `${Math.min(100, Math.max(0, percent))}%`;
}

export default function CountySpendingList({
  rows: searchedRows,
  fiscalYear,
  countiesWithData,
  distribution,
  distributionNational,
  nationalEfficiency,
  nationalAllocated,
  projected,
  loading,
  error,
  auditUnavailable,
  search,
  onSearch,
  sortKey,
  reversed,
  onSort,
  onReverse,
}: Props) {
  const { lang, t } = useLang();
  const listId = useId();
  const searchInput = useRef<HTMLInputElement>(null);
  const firstAdditionalCounty = useRef<HTMLAnchorElement>(null);
  const [showAll, setShowAll] = useState(false);
  const [belowTargetOnly, setBelowTargetOnly] = useState(false);
  const belowTarget = new Set(distribution.filter(
    (point) => point.percentage != null && point.percentage < TARGET
  ).map((point) => point.id));
  const filtering = belowTargetOnly && belowTarget.size > 0;
  const rows = filtering
    ? searchedRows.filter((row) => belowTarget.has(row.county_id))
    : searchedRows;
  useEffect(() => {
    if (showAll) firstAdditionalCounty.current?.focus();
  }, [showAll]);
  const shownRows = showAll ? rows : rows.slice(0, INITIAL_COUNT);
  const messages = countySpendingMessages;
  const copy = (key: keyof typeof messages, values: Record<string, string | number> = {}) =>
    messages[key][lang].replace(/\{(\w+)\}/g, (match, name) => String(values[name] ?? match));
  const period = copy('fiscalYear', { year: fiscalYear });
  const sortOptions: CountySortKey[] = projected ? ['allocated', 'name'] : ['efficiency', 'gap', 'name'];
  if (!projected && !auditUnavailable) sortOptions.push('flagged');
  const desktopOptions: CountySortKey[] = ['name', ...sortOptions.filter((option) => option !== 'name')];
  const columnLabels = shownRows.length > 1 ? ['leftColumn', 'rightColumn'] as const : ['leftColumn'] as const;
  const markerNote =
    nationalEfficiency == null
      ? copy('targetMarker', { target: TARGET })
      : copy('markers', { target: TARGET, national: formatEfficiency(nationalEfficiency) });

  function clearSearch() {
    onSearch('');
    searchInput.current?.focus();
  }

  return (
    <section
      className={`${styles.presentation} ${styles.countySection}`}
      aria-labelledby='county-spending-heading'>
      <header className={styles.countyHeading}>
        <div className={styles.reportTitle}>
          <h2 id='county-spending-heading'>{copy('title')}</h2>
          <p className={styles.reportPeriod}>{period}</p>
        </div>
        {!loading && !error && (
          <p className={styles.coverage}>
            {copy(projected ? 'allocationCoverageProjected' : 'allocationCoverage', {
              count: countiesWithData,
            })}
          </p>
        )}
      </header>
      {fiscalYear && !loading && !error && (
        <CountySpendingDistribution
          counties={distribution}
          national={distributionNational}
          belowCount={belowTarget.size}
          filtering={filtering}
          onFilter={() => {
            setBelowTargetOnly(!filtering);
            setShowAll(false);
          }}
        />
      )}
      <div className={styles.controls}>
        <div className={styles.searchWrap}>
          <label htmlFor='county-search' className='sr-only'>{copy('search')}</label>
          <Search size={18} className={styles.searchIcon} aria-hidden='true' />
          <input
            ref={searchInput}
            id='county-search'
            type='search'
            autoComplete='off'
            placeholder={copy('search')}
            value={search}
            onChange={(event) => onSearch(event.target.value)}
          />
          {search && (
            <button
              type='button'
              className={styles.clearSearch}
              onClick={clearSearch}
              aria-label={copy('clearSearch')}>
              <X size={16} aria-hidden='true' />
            </button>
          )}
        </div>
        <div className={styles.sortWrap} role='group' aria-label={copy('sort')}
          data-desktop-headings={!loading && !error && rows.length > 0 || undefined}>
          {sortOptions.map((option) => (
            <button
              key={option}
              type='button'
              className={`audit-control ${styles.sortChip}`}
              aria-pressed={option === sortKey}
              onClick={() => onSort(option)}>
              {copy(option)}
            </button>
          ))}
          <button
            type='button'
            className={`audit-control ${styles.sortChip}`}
            onClick={onReverse}
            aria-label={copy('reverse')}
            aria-pressed={reversed}
            title={copy('reverse')}>
            <ArrowUpDown size={18} aria-hidden='true' />
          </button>
        </div>
      </div>
      {!projected && !loading && !error && rows.length > 0 && (
        <>
          <p className={styles.efficiencyKey}>
            {executionBands.map(({ verdict, range }) => (
              <span key={verdict} data-execution={verdict}>{copy(range)}</span>
            ))}
            {copy('target', { target: TARGET })}
          </p>
          <p className={styles.countyNote}>{markerNote}</p>
          <p className={styles.countyNote}>
            {auditUnavailable ? copy('auditMissing', { period }) : copy('auditContext')}
          </p>
        </>
      )}
      {(filtering || search.trim()) && !loading && !error && rows.length > 0 && (
        <p role='status' className={styles.countyNote}>
          {rows.length === 1 ? copy('oneCounty') : copy('countyCount', { count: rows.length })}
        </p>
      )}
      {loading ? (
        <p role='status' className={styles.empty}>{copy('loading')}</p>
      ) : error ? (
        <p className={styles.empty} role='alert'>{copy('error')}</p>
      ) : rows.length === 0 ? (
        <p className={styles.empty} role='status'>
          {filtering ? copy('noBelowMatch') : search.trim() ? copy('noMatch') : copy('noData')}
        </p>
      ) : (
        <>
          <div className={styles.desktopSorts}>
            {columnLabels.map((column) => (
              <div key={column} role='group' aria-label={copy('columnSortGroup', { column: copy(column) })}>
                {desktopOptions.map((option) => {
                  const active = option === sortKey;
                  const ascending = (option === 'name' || option === 'efficiency') !== reversed;
                  const Icon = active ? ascending ? ArrowUp : ArrowDown : ArrowUpDown;
                  const heading = copy(headingLabels[option]);
                  const context = active
                    ? copy('activeColumnSort', { column: copy(column), direction: copy(ascending ? 'sortAscending' : 'sortDescending') })
                    : copy('inactiveColumnSort', { column: copy(column) });
                  return (
                    <button key={option} type='button' className={`audit-control ${styles.desktopSortButton}`}
                      aria-controls={listId} aria-pressed={active} aria-label={heading + context}
                      onClick={() => active ? onReverse() : onSort(option)}>
                      {heading}
                      <Icon size={16} aria-hidden='true' />
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
          <ol
            id={listId}
            className={styles.counties}
            style={{ '--county-rows': Math.ceil(shownRows.length / 2) } as CSSProperties}
            role='list'
            aria-label={copy(reversed ? 'reversedOrder' : 'orderedBy', { sort: copy(sortKey) })}>
            {shownRows.map((row, index) => {
              const efficiency = row.efficiency_score;
              const band = efficiency == null
                ? null
                : highestBandFirst.find(({ min }) => efficiency >= min) ?? executionBands[0];
              const share =
                projected && nationalAllocated != null && nationalAllocated > 0 && row.allocated != null
                  ? (row.allocated / nationalAllocated) * 100
                  : null;
              const coverage = row.audit_amount_coverage;
              const coverageNote = !auditUnavailable && coverage && coverage.reason !== 'no_findings'
                ? auditAmountCoverageNote(coverage, lang)
                : null;

              return (
                <li
                  key={row.county_id}
                  className={styles.county}
                  data-execution={band?.verdict}
                  data-column-end={index + 1 === Math.ceil(shownRows.length / 2) || undefined}>
                  <div className={styles.nameLine}>
                    <span className={styles.rank}>{String(row.rank).padStart(2, '0')}</span>
                    <h3>
                      <Link
                        ref={index === INITIAL_COUNT ? firstAdditionalCounty : undefined}
                        href={`/counties/${row.county_id}?tab=money&from=transparency`}>
                        {row.county_name}
                      </Link>
                    </h3>
                    {!projected && (
                      <strong className={styles.countyRate}>
                        {efficiency == null ? '—' : `${formatEfficiency(efficiency)}%`}
                      </strong>
                    )}
                  </div>
                  <div className={styles.countyDetails}>
                    <p>{copy('allocation', { amount: formatFlowKES(row.allocated) })}</p>
                    {!projected && <strong>{copy(band?.verdict ?? 'unreported')}</strong>}
                  </div>
                  {projected ? (
                    <>
                      <p className={styles.countyNote}>
                        {share == null ? '—' : `${share.toFixed(1)}%`} {copy('allocationShare')} · {copy('pending')}
                      </p>
                      {share != null && (
                        <div className={styles.measure} aria-hidden='true'>
                          <span className={styles.fill} data-tone='allocation' style={{ width: percentWidth(share) }} />
                        </div>
                      )}
                    </>
                  ) : (
                    <>
                      {efficiency != null && (
                        <div
                          className={styles.measure}
                          role='img'
                          aria-label={copy(nationalEfficiency == null ? 'efficiencyBar' : 'nationalBar', {
                            county: row.county_name,
                            spent: formatEfficiency(efficiency),
                            target: TARGET,
                            national: nationalEfficiency == null ? '' : formatEfficiency(nationalEfficiency),
                          })}>
                          <span className={styles.fill} style={{ width: percentWidth(efficiency) }} />
                          <span className={styles.targetMarker} style={{ left: percentWidth(TARGET) }} />
                          {nationalEfficiency != null && (
                            <span
                              className={styles.nationalMarker}
                              style={{ left: percentWidth(nationalEfficiency) }}
                            />
                          )}
                        </div>
                      )}
                      <dl className={styles.ledger}>
                        <div>
                          <dt>{copy('spent')}</dt>
                          <dd><Amount amount={row.spent} unavailable={copy('unavailable')} /></dd>
                        </div>
                        <div className={styles.countyGap}>
                          <dt>{copy('unspent')}</dt>
                          <dd>
                            <Amount
                              amount={
                                row.total_gap > 0 || (row.allocated != null && row.spent != null)
                                  ? row.total_gap
                                  : null
                              }
                              unavailable={copy('unavailable')}
                            />
                          </dd>
                        </div>
                        <div>
                          <dt>{copy(auditUnavailable ? 'auditFlagged' : 'auditQuestioned')}</dt>
                          <dd><Amount amount={row.flagged_amount} unavailable={copy('auditAmountUnavailable')} /></dd>
                        </div>
                      </dl>
                      {coverageNote && <p className={styles.countyNote}>{coverageNote}</p>}
                    </>
                  )}
                </li>
              );
            })}
          </ol>
          {rows.length > INITIAL_COUNT && (
            <button
              type='button'
              className={`audit-control ${styles.countyShowAll}`}
              aria-controls={listId}
              aria-expanded={showAll}
              onClick={() => setShowAll(!showAll)}>
              {showAll ? t('foundation.show_less') : copy('showAll', { count: rows.length })}
            </button>
          )}
        </>
      )}
    </section>
  );
}
