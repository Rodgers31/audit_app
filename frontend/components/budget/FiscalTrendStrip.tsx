'use client';

import { useId } from 'react';
import InfoSheet from '@/components/ui/InfoSheet';
import ResponsiveTable from '@/components/ui/ResponsiveTable';
import { useLang } from '@/lib/i18n/LangProvider';
import {
  comparableHistory, HISTORY_MEASURES, historyChange, historyPeriods, observeHistory,
  type FiscalHistoryRow, type HistoryCode, type HistoryObservation,
} from './fiscalHistory';

function abbreviatedYear(year: string) {
  return year.slice(2);
}

function TrendBars({ observations, max, className, formatAmount, debt }: {
  observations: HistoryObservation[];
  max: number;
  className: string;
  formatAmount: (value: number) => string;
  debt: boolean;
}) {
  const { t } = useLang();
  const highlight = debt ? 'bg-signal-alarm' : 'bg-neutral-text';
  return (
    <ul role='list' className={`m-0 list-none gap-x-2 p-0 ${className}`}
      style={{ gridTemplateColumns: `repeat(${observations.length}, minmax(0, 1fr))` }}>
      {observations.map(({ year, value, code, proof }, index) => (
        <li key={year} className='grid min-w-0 grid-rows-[auto_2.5rem_1fr] text-center text-xs tabular-nums min-[400px]:grid-rows-[auto_3.5rem_1fr]'>
          <span className='self-end font-medium [overflow-wrap:anywhere]'>
            {value == null
              ? <><span aria-hidden='true'>—</span><span className='sr-only'>
                {t(code === 'withheld' ? 'budget.history.withheld' : 'foundation.no_chart_value')}
              </span></>
              : formatAmount(value)}
          </span>
          <div aria-hidden='true' className='flex items-end border-b border-neutral-border'>
            {value != null && (
              <span
                className={`mx-auto w-3/4 max-w-10 rounded-t-sm ${proof && index === observations.length - 1 ? highlight : 'bg-chart-context'}`}
                style={{ height: `${100 * value / max}%` }}
              />
            )}
          </div>
          <span className='mt-1 text-neutral-muted [overflow-wrap:anywhere]'>
            <span className='block'><span aria-hidden='true'>{abbreviatedYear(year)}</span><span className='sr-only'>{year}</span></span>
            {code && <>
              <span aria-hidden='true' className='block'>{t(`budget.history.${code}_short`)}</span>
              {value != null && <span className='sr-only'>{t(`budget.history.${code}`)}</span>}
            </>}
          </span>
        </li>
      ))}
    </ul>
  );
}

function MiniTrend({ observations, max, debt }: { observations: HistoryObservation[]; max: number; debt: boolean }) {
  const points = observations.map(({ value }, index) => value == null ? null : {
    x: 4 + (112 * index) / (observations.length - 1),
    y: 32 - (28 * value) / max,
  });

  return (
    <svg aria-hidden='true' viewBox='0 0 120 36' className={`h-9 w-full min-[400px]:hidden ${debt ? 'text-signal-alarm' : 'text-neutral-text'}`}>
      {points.map((point, index) => {
        if (!point) return null;
        const previous = points[index - 1];
        return (
          <g key={observations[index].year}>
            {previous && comparableHistory(observations[index - 1], observations[index]) && (
              <line x1={previous.x} y1={previous.y} x2={point.x} y2={point.y} stroke='currentColor' strokeWidth='2' />
            )}
            <circle cx={point.x} cy={point.y} r='2.5' fill='currentColor' />
          </g>
        );
      })}
    </svg>
  );
}

export default function FiscalTrendStrip({ history }: { history: FiscalHistoryRow[] }) {
  const { t, lang } = useLang();
  const titleId = useId();
  const periods = historyPeriods(history);
  if (periods.length < 2) return null;

  const recent = periods.slice(-5);
  const title = t(recent.length === 5 ? 'budget.history.five_years' : 'budget.history.title');
  const locale = lang === 'sw' ? 'sw-KE' : 'en-KE';
  const billions = new Intl.NumberFormat(locale, { maximumFractionDigits: 0, useGrouping: false });
  const trillions = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const exactKes = new Intl.NumberFormat(locale, { maximumFractionDigits: 2 });
  const percent = new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 0 });
  const formatAmount = (value: number) => value >= 1000 ? `${trillions.format(value / 1000)}T` : `${billions.format(value)}B`;

  const charts = HISTORY_MEASURES.map(measure => {
    const all = periods.map(period => observeHistory(period, measure));
    const observations = all.slice(-recent.length);
    const max = Math.max(1, ...observations.map(({ value }) => value ?? 0));
    const delta = historyChange(observations);
    const latestCode = observations.at(-1)?.code;
    const takeaway = delta && latestCode ? `${t(
      delta.change > 0.005 ? 'budget.history.up' : delta.change < -0.005 ? 'budget.history.down' : 'budget.history.steady'
    ).replace('{change}', percent.format(Math.abs(delta.change))).replace('{year}', `FY${delta.start}`)} · ${t(`budget.history.${latestCode}`)}` : null;
    return { measure, name: t(`budget.history.${measure}`), all, observations, max, takeaway };
  });
  const codes = new Set<HistoryCode>(charts.flatMap(({ observations }) =>
    observations.flatMap(({ code }) => code ? [code] : [])
  ));
  const basisKey = Array.from(codes, code => `${t(`budget.history.${code}_short`)} = ${t(`budget.history.${code}`)}`).join(' · ');

  return (
    <section aria-labelledby={titleId} className='audit-panel space-y-3 p-3 sm:p-5'>
      <h2 id={titleId} className='font-display text-2xl font-semibold text-neutral-text'>{title}</h2>
      <div className='grid grid-cols-1 gap-3 lg:grid-cols-2'>
        {charts.map(({ measure, name, observations, max, takeaway }) => (
          <article key={measure} aria-label={name} className='audit-panel space-y-2 p-3'>
            <h3 className='text-sm font-semibold'>{name}</h3>
            {takeaway && <p className='text-sm text-neutral-muted'>{takeaway}</p>}
            <MiniTrend observations={observations} max={max} debt={measure === 'debt_service_cost'} />
            <TrendBars observations={observations.slice(-2)} max={max} debt={measure === 'debt_service_cost'} formatAmount={formatAmount} className='grid min-[400px]:hidden' />
            <TrendBars observations={observations} max={max} debt={measure === 'debt_service_cost'} formatAmount={formatAmount} className='hidden min-[400px]:grid' />
          </article>
        ))}
      </div>
      {basisKey && (
        <p className='text-xs leading-relaxed text-neutral-muted'>
          {t('budget.history.basis_key')}: {basisKey}
        </p>
      )}
      <InfoSheet title={t('budget.history.title')} trigger={trigger => (
        <button {...trigger} type='button' className='audit-control' onClick={event => {
          event.currentTarget.focus({ preventScroll: true });
          trigger.onClick();
        }}>{t('budget.history.open_sheet')}</button>
      )}>
        {charts.map(({ measure, name, all }) => (
          <ResponsiveTable key={measure}>
            <table className='w-full table-fixed text-left [overflow-wrap:anywhere]'>
              <caption className='pb-2 text-left font-semibold'>{name}</caption>
              <colgroup><col className='w-[22%]' /><col className='w-[32%]' /><col /></colgroup>
              <thead>
                <tr className='border-b border-neutral-border'>
                  <th scope='col' className='pb-2 pr-2'>{t('budget.history.year_column')}</th>
                  <th scope='col' className='pb-2 pr-2'>{t('budget.history.amount_column')}</th>
                  <th scope='col' className='pb-2'>{t('budget.history.basis_column')}</th>
                </tr>
              </thead>
              <tbody>
                {all.map(({ year, value, code, proof, sourceTitle }) => (
                  <tr key={year} className='border-b border-neutral-border align-top'>
                    <th scope='row' className='py-2 pr-2 font-normal tabular-nums'>{year}</th>
                    <td className='py-2 pr-2 tabular-nums'>
                      {value == null ? t(code === 'withheld' ? 'budget.history.withheld' : 'foundation.no_chart_value')
                        : proof ? exactKes.format(proof.value_kes) : formatAmount(value)}
                    </td>
                    <td className='py-2'>
                      {value != null && code ? t(`budget.history.${code}`) : '—'}
                      {proof && <a href={proof.source.url} className='audit-receipt min-w-11 text-left' target='_blank' rel='noopener noreferrer'>
                        <span className='min-w-0'>
                          {proof.source.title ?? t('budget.history.source_document')} · {proof.source.page}
                        </span>
                      </a>}
                      {sourceTitle && <span className='block text-xs text-neutral-muted'>{sourceTitle}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ResponsiveTable>
        ))}
      </InfoSheet>
    </section>
  );
}
