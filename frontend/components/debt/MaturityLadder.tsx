'use client';

import { useQuery } from '@tanstack/react-query';
import { useEffect, useId, useRef, useState, type KeyboardEvent, type MouseEvent, type PointerEvent as ReactPointerEvent } from 'react';
import ResponsiveTable from '@/components/ui/ResponsiveTable';
import api from '@/lib/api/axios';
import { useLang } from '@/lib/i18n/LangProvider';
import { fmtKES } from '@/lib/utils';
import { describeMaturities, reportedCount, reportedNumber, type InstrumentsResponse } from './MaturityLadder.data';
import styles from './MaturityLadder.module.css';

function readableAmount(amount: number) {
  return fmtKES(amount).replace(/\.0([BM])$/, '$1');
}

function Ladder({ data }: { data: InstrumentsResponse }) {
  const { lang, t } = useLang();
  const instructionId = useId();
  const chart = useRef<HTMLOListElement>(null);
  const [active, setActive] = useState<number | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const { date, year, rows, range, windowAmount, windowComplete, peakAmount, peaks, maxBar } =
    describeMaturities(data);

  useEffect(() => {
    if (selected == null) return;
    function clearOutside(event: PointerEvent) {
      if (event.target instanceof Node && !chart.current?.parentElement?.contains(event.target)) {
        setSelected(null);
        setActive(null);
      }
    }
    document.addEventListener('pointerdown', clearOutside);
    return () => document.removeEventListener('pointerdown', clearOutside);
  }, [selected]);

  if (rows.length === 0) return <p className='text-sm text-neutral-muted'>{t('debt.maturity.empty')}</p>;

  const locale = lang === 'sw' ? 'sw-KE' : 'en-KE';
  const exact = new Intl.NumberFormat(locale, { maximumFractionDigits: 2 });
  const dateFormat = new Intl.DateTimeFormat(locale, { dateStyle: 'long', timeZone: 'UTC' });
  const asExact = (amount: number | null) => amount == null
    ? t('debt.maturity.amount_unavailable') : `KES ${exact.format(amount)}`;
  const rangeLabel = range ? `${range.start}–${range.end}` : null;
  const peakLabel = new Intl.ListFormat(locale).format(peaks.map(String));
  const current = rows.find(row => row.year === (active ?? selected));
  const count = reportedCount(data.instrument_count);
  const ambiguous = reportedCount(data.withheld_count);
  const gated = reportedCount(data.withheld_by_gate?.count);
  const ratio = reportedNumber(data.coverage?.coverage_ratio);
  const hasCoverage = ratio != null && ratio >= 0;
  const sourceUrl = data.source?.url;
  const hasSignedRows = rows.some(row => row.amount != null && row.amount < 0);

  function rowNote(row: (typeof rows)[number]) {
    if (peaks.includes(row.year)) return t('debt.maturity.peak');
    if (row.past) return t('debt.maturity.past');
    if (row.amount != null && row.amount < 0) return t('debt.maturity.signed');
    if (row.year === year) return t('debt.maturity.snapshot_year');
    return null;
  }

  function pointedYear(event: MouseEvent<HTMLButtonElement> | ReactPointerEvent<HTMLButtonElement>) {
    const items = chart.current?.children;
    return rows.find((_, index) => {
      const bounds = items?.[index]?.getBoundingClientRect();
      return bounds && event.clientY >= bounds.top && event.clientY < bounds.bottom;
    })?.year ?? null;
  }

  function selectYear(event: MouseEvent<HTMLButtonElement>) {
    const target = event.detail === 0 ? (active ?? selected ?? rows[0].year) : pointedYear(event);
    setActive(null);
    setSelected(previous => previous === target ? null : target);
  }

  function moveYear(event: KeyboardEvent<HTMLButtonElement>) {
    const index = rows.findIndex(row => row.year === (active ?? selected));
    switch (event.key) {
      case 'ArrowUp': setActive(rows[Math.max(0, index - 1)].year); break;
      case 'ArrowDown': setActive(rows[Math.min(rows.length - 1, index + 1)].year); break;
      case 'Home': setActive(rows[0].year); break;
      case 'End': setActive(rows[rows.length - 1].year); break;
      case 'Escape': setActive(null); setSelected(null); break;
      default: return;
    }
    event.preventDefault();
  }

  return (
    <>
      <div className={styles.horizons}>
        <div className={styles.horizon} data-signal={windowAmount == null ? undefined : 'near'}>
          <p className={styles.horizonAmount}>{windowAmount == null
            ? t('debt.maturity.amount_unavailable') : readableAmount(windowAmount)}</p>
          <p>{rangeLabel == null ? t('debt.maturity.range_unavailable')
            : t(windowAmount == null ? 'debt.maturity.range_only'
              : windowComplete ? 'debt.maturity.due_range' : 'debt.maturity.reported_range').replace('{range}', rangeLabel)}</p>
        </div>
        <div className={styles.horizon} data-signal={peakAmount == null ? undefined : 'peak'}>
          <p className={styles.horizonAmount}>{peakAmount == null
            ? t('debt.maturity.amount_unavailable') : readableAmount(peakAmount)}</p>
          <p>{peakAmount == null ? t('debt.maturity.peak_unavailable') :
            t(peaks.length > 1 ? 'debt.maturity.tied_peak'
              : date ? 'debt.maturity.due_peak' : 'debt.maturity.reported_peak').replace('{years}', peakLabel)}</p>
        </div>
      </div>
      {range && !windowComplete && (
        <p className='text-sm text-neutral-muted'>{t(windowAmount == null ? 'debt.maturity.empty_range' : 'debt.maturity.partial_range')}</p>
      )}
      <figure className='min-w-0' aria-label={t('debt.maturity.plot')}>
        <p className={styles.readout} aria-live='polite'>
          {current ? `${current.year} · ${asExact(current.amount)}${rowNote(current) ? ` · ${rowNote(current)}` : ''}`
            : t('debt.maturity.readout')}
        </p>
        <span id={instructionId} className='sr-only'>{t('debt.maturity.arrow_help')}</span>
        <div className={styles.chart}>
          <ol ref={chart} className={styles.ladder} aria-hidden='true'>
            {rows.map(row => {
              const note = rowNote(row);
              const isPeak = peaks.includes(row.year);
              const inHorizon = range != null && row.year >= range.start && row.year <= range.end;
              const amount = row.amount == null
                ? t('debt.maturity.amount_unavailable') : readableAmount(row.amount).replace(/^KES /, '');
              return (
                <li key={row.year} className={styles.year} data-signal={isPeak ? 'peak' : inHorizon ? 'near' : undefined}
                  data-horizon-end={row.year === range?.end ? true : undefined}
                  data-highlighted={current?.year === row.year}>
                  <span className={styles.yearLabel}>{row.year}</span>
                  <span className={styles.plot}>
                    {row.amount != null && row.amount > 0 && (
                      <span className={styles.bar} style={{ width: `calc((100% - var(--label-space)) * ${row.amount / maxBar})` }} />
                    )}
                    <span className={styles.rowAmount}>{amount}</span>
                    {note && <span className={styles.rowNote}>{note}</span>}
                  </span>
                </li>
              );
            })}
          </ol>
          <button type='button' className={styles.chartControl} aria-label={t('debt.maturity.explore')}
            aria-describedby={instructionId}
            aria-pressed={selected != null}
            onFocus={() => setActive(selected ?? rows[0].year)}
            onBlur={() => setActive(null)}
            onPointerMove={event => { if (event.pointerType === 'mouse') setActive(pointedYear(event)); }}
            onPointerLeave={event => { if (event.pointerType === 'mouse') setActive(null); }}
            onClick={selectYear} onKeyDown={moveYear} />
        </div>
      </figure>
      <p className='text-sm text-neutral-muted'>
        {count == null ? t('debt.maturity.scope_short') : t(count === 1 ? 'debt.maturity.scope_one' : 'debt.maturity.scope_count')
          .replace('{count}', exact.format(count))}
      </p>
      <details className='text-sm'>
        <summary className={styles.disclosure}>{t('debt.maturity.included')}</summary>
        <div className='space-y-2 pb-2 text-neutral-muted'>
          <p>{t('debt.maturity.scope_full')}</p>
          <p>{date ? t('debt.maturity.snapshot').replace('{date}', dateFormat.format(date))
            : t('debt.maturity.date_unavailable')}</p>
          <p>{hasCoverage
            ? t('debt.maturity.coverage_ratio').replace('{share}', new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 1 }).format(ratio))
            : t('debt.maturity.coverage_unavailable')}</p>
          {ambiguous != null && ambiguous > 0 && <p>{t('debt.maturity.ambiguous').replace('{count}', exact.format(ambiguous))}</p>}
          {gated != null && gated > 0 && (
            <p>{t('debt.maturity.gated').replace('{count}', exact.format(gated))}{hasCoverage && <> {t('debt.maturity.coverage_basis')}</>}</p>
          )}
          {hasSignedRows && <p>{t('debt.maturity.signed_basis')}</p>}
          {sourceUrl?.startsWith('https://') && (
            <a className='audit-control underline' href={sourceUrl} target='_blank' rel='noopener noreferrer'>
              {t('debt.maturity.source_link')}{data.source?.title && ` · ${data.source.title}`}
            </a>
          )}
        </div>
      </details>
      <details className='text-sm'>
        <summary className={styles.disclosure}>{t('foundation.chart_table')}</summary>
        <ResponsiveTable>
          <table className='w-full table-auto text-left'>
            <caption className='sr-only'>{t('debt.maturity.plot')}</caption>
            <thead><tr>
              <th className={styles.cell} scope='col'>{t('debt.maturity.year')}</th>
              <th className={styles.cell} scope='col'>{t('debt.maturity.face_value')}</th>
              <th className={styles.cell} scope='col'>{t('debt.maturity.bonds')}</th>
            </tr></thead>
            <tbody>{rows.map(row => (
              <tr key={row.year}>
                <th className={styles.cell} scope='row'>{row.year}{rowNote(row) && <span className='block font-normal'>{rowNote(row)}</span>}</th>
                <td className={styles.cell}>{asExact(row.amount)}</td>
                <td className={styles.cell}>{row.instruments == null ? t('debt.maturity.count_unavailable') : exact.format(row.instruments)}</td>
              </tr>
            ))}</tbody>
          </table>
        </ResponsiveTable>
      </details>
    </>
  );
}

export default function MaturityLadder() {
  const { t } = useLang();
  const headingId = useId();
  const { data, isLoading, isError, isFetching, refetch } = useQuery<InstrumentsResponse>({
    queryKey: ['debt', 'instruments'],
    queryFn: async ({ signal }) => (await api.get<InstrumentsResponse>('/debt/instruments', { signal })).data,
    staleTime: 60 * 60 * 1000,
  });

  return (
    <section aria-labelledby={headingId} className='min-w-0 space-y-3'>
      <h2 id={headingId} className='font-display text-2xl font-bold sm:text-3xl'>{t('debt.maturity.title')}</h2>
      {isLoading ? <p role='status' className='text-sm text-neutral-muted'>{t('debt.maturity.loading')}</p>
        : isError ? (
          <div className='text-sm text-neutral-muted'>
            <p role='status'>{t('debt.maturity.failed')}</p>
            <button type='button' className='audit-control underline' disabled={isFetching} onClick={() => refetch()}>
              {t('debt.maturity.retry')}
            </button>
          </div>
        ) : data?.status === 'success' ? <Ladder data={data} /> : (
          <div className='space-y-2 text-sm text-neutral-muted'>
            <p>{t(data?.reason === 'all_rows_withheld_by_gate' ? 'debt.maturity.all_withheld'
              : data?.reason === 'no_instrument_register_ingested' ? 'debt.maturity.not_ingested'
              : data?.reason === 'table_not_migrated' ? 'debt.maturity.awaiting_setup'
              : 'debt.maturity.unavailable')}</p>
            {data?.reason === 'all_rows_withheld_by_gate' && reportedCount(data.withheld_by_gate?.count) != null && (
              <p>{t('debt.maturity.gated').replace('{count}', String(data.withheld_by_gate?.count))}</p>
            )}
          </div>
        )}
    </section>
  );
}
