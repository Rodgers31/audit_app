'use client';

import { useLang } from '@/lib/i18n/LangProvider';

import {
  ArrowUpDown,
  ChevronDown,
  Clock,
  Info,
  Loader2,
  Search,
  TriangleAlert,
  X,
} from 'lucide-react';
import Link from 'next/link';
import { useRef, type CSSProperties } from 'react';
import {
  auditAmountCoverageNote,
  efficiencyLabel,
  formatEfficiency,
  efficiencyTone,
  formatFlowKES,
  type CountyFlowRow,
  type CountySortKey,
} from './moneyFlowPresentation';
import styles from './MoneyFlowPresentation.module.css';

interface Props {
  rows: CountyFlowRow[];
  fiscalYear: string;
  countiesWithData: number;
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

function Amount({ amount }: { amount: number | null }) {
  const value = formatFlowKES(amount);
  return amount == null ? (
    <b aria-label='Unavailable'>—</b>
  ) : (
    <b>
      <small>KES </small>
      {value.slice(4)}
    </b>
  );
}

export default function CountySpendingList({
  rows,
  fiscalYear,
  countiesWithData,
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
  const { lang } = useLang();
  const searchInput = useRef<HTMLInputElement>(null);
  const options: { value: CountySortKey; label: string }[] = projected
    ? [
        { value: 'allocated', label: 'Largest allocation' },
        { value: 'name', label: 'A–Z' },
      ]
    : [
        { value: 'efficiency', label: 'Least efficient' },
        { value: 'flagged', label: 'Most flagged' },
        { value: 'gap', label: 'Highest gap' },
        { value: 'name', label: 'A–Z' },
      ];
  const activeSort = options.some((option) => option.value === sortKey)
    ? sortKey
    : options[0].value;
  const clearSearch = () => {
    onSearch('');
    searchInput.current?.focus();
  };
  return (
    <section
      className={`${styles.presentation} ${styles.countySection}`}
      aria-labelledby='county-spending-heading'>
      <header className={styles.countyHeading}>
        <div className={styles.reportTitle}>
          <h2 id='county-spending-heading'>County spending</h2>
          <p className={styles.reportPeriod}>FY {fiscalYear}</p>
        </div>
        <p className={styles.coverage}>
          {loading
            ? 'Loading county data…'
            : `${countiesWithData} of 47 counties have published allocations`}
          {projected ? ' — execution figures pending' : ''}
        </p>
      </header>
      <div className={styles.controls}>
        <div className={styles.searchWrap}>
          <label htmlFor='county-search' className={styles.fieldLabel}>
            Find your county
          </label>
          <Search size={18} className={styles.searchIcon} aria-hidden='true' />
          <input
            ref={searchInput}
            id='county-search'
            type='search'
            autoComplete='off'
            placeholder='Search counties'
            value={search}
            onChange={(event) => onSearch(event.target.value)}
          />
          {search && (
            <button
              className={styles.clearSearch}
              onClick={clearSearch}
              aria-label='Clear county search'>
              <X size={16} aria-hidden='true' />
            </button>
          )}
        </div>
        <div className={styles.sortWrap}>
          <label htmlFor='county-sort'>Sort by</label>
          <div className={styles.selectWrap}>
            <select
              id='county-sort'
              value={activeSort}
              onChange={(event) => onSort(event.target.value as CountySortKey)}>
              {options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <ChevronDown size={16} aria-hidden='true' />
          </div>
          <button
            className={styles.direction}
            onClick={onReverse}
            aria-label='Reverse sort order'
            aria-pressed={reversed}
            title='Reverse sort order'>
            <ArrowUpDown size={19} aria-hidden='true' />
          </button>
        </div>
      </div>
      {!projected && (
        <>
          <div className={styles.sectionMeta}>
            <p className={styles.reference}>
              {nationalEfficiency != null ? (
                <>
                  <span className={styles.referenceMark} aria-hidden='true' />
                  Reference line:{' '}
                  <strong>national efficiency {formatEfficiency(nationalEfficiency)}%</strong>
                </>
              ) : (
                'National efficiency unavailable for this period'
              )}
            </p>
            <details className={styles.auditNote}>
              <summary>
                <Info size={16} aria-hidden='true' />
                <span>
                  {auditUnavailable
                    ? 'Auditor-General amounts unavailable'
                    : 'About Auditor-General findings'}
                </span>
                <ChevronDown size={14} aria-hidden='true' />
              </summary>
              <p>
                {auditUnavailable
                  ? 'No finite cited finding amounts are available for this period. '
                  : 'Recorded finding amounts may include balances discussed in the report; they are not a measure of proven loss or theft. '}
                A dash means the amount is unavailable.
              </p>
            </details>
          </div>
          <p className={styles.efficiencyKey}>
            Budget execution: <span data-tone='good'>70% and above</span>
            <span data-tone='fair'>50% to below 70%</span>
            <span data-tone='low'>Below 50%</span>
          </p>
        </>
      )}
      <div className={styles.resultsLine}>
        <span role='status'>
          {loading
            ? 'Loading counties…'
            : `${rows.length} ${rows.length === 1 ? 'county' : 'counties'}${search ? ' found' : ''}`}
        </span>
        <span>{projected ? 'Share of national allocation' : 'Spent share of allocation'}</span>
      </div>
      {loading ? (
        <div className={styles.empty}>
          <Loader2 size={24} className='animate-spin' aria-hidden='true' />
          Loading county data…
        </div>
      ) : error ? (
        <p className={styles.empty} role='alert'>
          County data could not be loaded. Please try again.
        </p>
      ) : rows.length === 0 ? (
        <div className={styles.empty}>
          <strong>
            {search ? 'No counties match your search.' : 'No data available for this fiscal year.'}
          </strong>
          {search && <button onClick={clearSearch}>Clear search</button>}
        </div>
      ) : (
        <ol
          className={styles.counties}
          aria-label={`Counties ordered by ${options.find((option) => option.value === activeSort)?.label}${reversed ? ', reversed' : ''}`}>
          {rows.map((row, index) => {
            const tone = efficiencyTone(row.efficiency_score);
            const flagged = row.flagged_amount != null && row.flagged_amount > 0;
            const share =
              nationalAllocated != null && nationalAllocated > 0 && row.allocated != null
                ? (row.allocated / nationalAllocated) * 100
                : null;
            return (
              <li
                key={row.county_id}
                className={`${styles.county} ${projected ? styles.projectedCounty : ''}`}>
                <div className={styles.identity}>
                  <div className={styles.nameLine}>
                    <span className={styles.rank}>{String(index + 1).padStart(2, '0')}</span>
                    <h3>
                      <Link href={`/counties/${row.county_id}?tab=money&from=transparency`}>
                        {row.county_name}
                      </Link>
                    </h3>
                  </div>
                  <p className={styles.allocation}>
                    <b>{formatFlowKES(row.allocated)}</b> allocated
                  </p>
                </div>
                {projected ? (
                  <>
                    <div className={styles.spending}>
                      <p className={styles.share}>
                        {share != null ? `${share.toFixed(1)}%` : '—'}{' '}
                        <span>of national allocation</span>
                      </p>
                      {share != null && (
                        <div className={styles.measure} aria-hidden='true'>
                          <span
                            className={styles.fill}
                            data-tone='allocation'
                            style={{
                              width: `${Math.min(100, Math.max(0, share))}%`,
                            }}
                          />
                        </div>
                      )}
                    </div>
                    <p className={styles.pending}>
                      <Clock size={14} aria-hidden='true' />
                      Execution pending
                    </p>
                  </>
                ) : (
                  <>
                    <div className={styles.rate} data-tone={tone}>
                      <strong>
                        {row.efficiency_score != null
                          ? `${formatEfficiency(row.efficiency_score)}%`
                          : '—'}
                      </strong>
                      <span>{efficiencyLabel(row.efficiency_score)}</span>
                    </div>
                    <div className={styles.spending}>
                      <div className={styles.amounts}>
                        <p>
                          <span>Spent</span>
                          <Amount amount={row.spent} />
                        </p>
                        <p data-tone={row.total_gap > 0 ? 'fair' : 'neutral'}>
                          <span>Gap</span>
                          <Amount
                            amount={
                              row.total_gap > 0 || (row.allocated != null && row.spent != null)
                                ? row.total_gap
                                : null
                            }
                          />
                        </p>
                      </div>
                      {row.efficiency_score != null && (
                        <div
                          className={styles.measure}
                          role='img'
                          aria-label={`${row.county_name}: ${formatEfficiency(row.efficiency_score)}% budget execution${nationalEfficiency != null ? `. National reference: ${formatEfficiency(nationalEfficiency)}%` : ''}`}
                          style={
                            {
                              '--flow-value': `${Math.min(100, Math.max(0, row.efficiency_score))}%`,
                            } as CSSProperties
                          }>
                          <span className={styles.fill} data-tone={tone} />
                          {nationalEfficiency != null && (
                            <span
                              className={styles.nationalMarker}
                              style={{
                                left: `${Math.min(100, Math.max(0, nationalEfficiency))}%`,
                              }}
                            />
                          )}
                        </div>
                      )}
                    </div>
                    <div className={styles.auditAmount} data-tone={flagged ? 'low' : 'neutral'}>
                      <span>
                        {flagged && <TriangleAlert size={14} aria-hidden='true' />}
                        Flagged
                      </span>
                      <b
                        aria-label={
                          row.flagged_amount == null ? 'Flagged amount unavailable' : undefined
                        }>
                        {formatFlowKES(row.flagged_amount)}
                      </b>
                      {row.audit_amount_coverage && <small>{auditAmountCoverageNote(row.audit_amount_coverage, lang)}</small>}
                      {flagged && <small>Amounts discussed; not proven loss</small>}
                    </div>
                  </>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
