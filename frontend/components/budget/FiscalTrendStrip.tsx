'use client';

import { useId } from 'react';
import InfoSheet from '@/components/ui/InfoSheet';
import ResponsiveTable from '@/components/ui/ResponsiveTable';
import { FISCAL_FRAMEWORK_BASIS, type FiscalFramework } from '@/lib/fiscal/framework';
import { useLang } from '@/lib/i18n/LangProvider';

export interface FiscalHistoryRow {
  fiscal_year: string;
  appropriated_budget?: number | null;
  total_revenue?: number | null;
  total_borrowing?: number | null;
  debt_service_cost?: number | null;
  county_allocation?: number | null;
  /** Which basis total_borrowing is on; see lib/fiscal/framework.ts. */
  split_basis?: string | null;
  fiscal_framework?: FiscalFramework | null;
  debt_service_source?: { title?: string } | null;
  measure_qualifications?: Record<string, { vintage: string; source: { title?: string } }>;
}

const MEASURES = ['appropriated_budget', 'total_revenue', 'total_borrowing', 'debt_service_cost'] as const;
const BASIS_LABELS = {
  Approved: 'approved',
  Actual: 'actual',
  Preliminary: 'preliminary',
  'Supplementary I': 'supplementary',
} as const;

type Basis = (typeof BASIS_LABELS)[keyof typeof BASIS_LABELS];
type Observation = { year: string; value: number | null; basis?: Basis; source?: string };

function observation(row: FiscalHistoryRow, measure: (typeof MEASURES)[number]): Observation {
  const proof = row.measure_qualifications?.[measure];
  const amount = row[measure];
  const value = typeof amount === 'number' && Number.isFinite(amount) && amount >= 0 ? amount : null;
  return {
    year: row.fiscal_year.replace(/^FY\s*/i, ''),
    value,
    basis: proof && Object.hasOwn(BASIS_LABELS, proof.vintage)
      ? BASIS_LABELS[proof.vintage as keyof typeof BASIS_LABELS]
      : undefined,
    source: proof?.source?.title ?? (measure === 'debt_service_cost' ? row.debt_service_source?.title : undefined),
  };
}

function measureObservations(rows: FiscalHistoryRow[], measure: (typeof MEASURES)[number]) {
  // Borrowing comparisons use the same Treasury fiscal-framework basis.
  const eligible = measure === 'total_borrowing'
    ? rows.filter(row => row.split_basis === FISCAL_FRAMEWORK_BASIS)
    : rows;
  return eligible.map(row => observation(row, measure));
}

function abbreviatedYear(year: string) {
  return year.replace(/^\d{2}(?=\d{2}\/\d{2}$)/, '');
}

function TrendBars({ observations, max, className, formatAmount, debt }: {
  observations: Observation[];
  max: number;
  className: string;
  formatAmount: (value: number) => string;
  debt: boolean;
}) {
  const { t } = useLang();
  const highlight = debt ? 'bg-signal-alarm' : 'bg-neutral-text';
  return (
    <ul
      className={`m-0 list-none gap-x-2 p-0 ${className}`}
      style={{ gridTemplateColumns: `repeat(${observations.length}, minmax(0, 1fr))` }}>
      {observations.map(({ year, value, basis }, index) => (
        <li key={year} className='grid min-w-0 grid-rows-[auto_2.5rem_1fr] text-center text-xs tabular-nums min-[400px]:grid-rows-[auto_3.5rem_1fr]'>
          <span className='self-end font-medium [overflow-wrap:anywhere]'>
            {value == null
              ? <><span aria-hidden='true'>—</span><span className='sr-only'>{t('foundation.no_chart_value')}</span></>
              : formatAmount(value)}
          </span>
          <div aria-hidden='true' className='flex items-end border-b border-neutral-border'>
            {value != null && (
              <span
                className={`mx-auto w-3/4 max-w-10 rounded-t-sm ${index === observations.length - 1 ? highlight : 'bg-chart-context'}`}
                style={{ height: `${100 * value / max}%` }}
              />
            )}
          </div>
          <span className='mt-1 text-neutral-muted [overflow-wrap:anywhere]'>
            <span className='block'><span aria-hidden='true'>{abbreviatedYear(year)}</span><span className='sr-only'>{year}</span></span>
            {basis && (
              <>
                <span aria-hidden='true' className='block'>{t(`budget.history.${basis}_short`)}</span>
                <span className='sr-only'>{t(`budget.history.${basis}`)}</span>
              </>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

function MiniTrend({ observations, max, debt }: { observations: Observation[]; max: number; debt: boolean }) {
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
            {previous && <line x1={previous.x} y1={previous.y} x2={point.x} y2={point.y} stroke='currentColor' strokeWidth='2' />}
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
  const sorted = [...history]
    .filter(row => row?.fiscal_year)
    .sort((a, b) => a.fiscal_year.localeCompare(b.fiscal_year));
  if (sorted.length < 2) return null;

  const recent = sorted.slice(-5);
  const title = t(recent.length === 5 ? 'budget.history.five_years' : 'budget.history.title');
  const locale = lang === 'sw' ? 'sw-KE' : 'en-KE';
  const billions = new Intl.NumberFormat(locale, { maximumFractionDigits: 0, useGrouping: false });
  const trillions = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const percent = new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 0 });
  const formatAmount = (value: number) => value >= 1000 ? `${trillions.format(value / 1000)}T` : `${billions.format(value)}B`;

  const series = MEASURES.map(measure => ({ measure, name: t(`budget.history.${measure}`) }));
  const charts = series.flatMap(({ measure, name }) => {
    const observations = measureObservations(recent, measure);
    if (observations.length < 2) return [];
    const max = Math.max(1, ...observations.map(({ value }) => value ?? 0));
    const first = observations[0];
    const latest = observations[observations.length - 1];
    const change = first.value != null && first.value > 0 && latest.value != null
      ? (latest.value - first.value) / first.value
      : null;
    const takeaway = change == null ? null : t(
      change > 0.005 ? 'budget.history.up' : change < -0.005 ? 'budget.history.down' : 'budget.history.steady'
    ).replace('{change}', percent.format(Math.abs(change))).replace('{year}', `FY${first.year}`);
    return [{ measure, name, observations, max, takeaway }];
  });
  const tables = series.map(({ measure, name }) => ({ measure, name, observations: measureObservations(sorted, measure) }))
    .filter(({ observations }) => observations.length > 0);
  const bases = Array.from(new Set(charts.flatMap(({ observations }) =>
    observations.flatMap(({ basis }) => basis ? [basis] : [])
  )));
  const basisKey = bases.flatMap(basis => {
    const short = t(`budget.history.${basis}_short`);
    const full = t(`budget.history.${basis}`);
    return short === full ? [] : [`${short} = ${full}`];
  }).join(', ');

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
        <button {...trigger} type='button' className='audit-control'>{t('budget.history.open_sheet')}</button>
      )}>
        {tables.map(({ measure, name, observations }) => (
          <ResponsiveTable key={measure}>
            <table className='w-full table-fixed text-left [overflow-wrap:anywhere]'>
              <caption className='pb-2 text-left font-semibold'>{name}</caption>
              <colgroup><col className='w-1/4' /><col className='w-1/4' /><col /></colgroup>
              <thead>
                <tr className='border-b border-neutral-border'>
                  <th scope='col' className='pb-2 pr-2'>{t('budget.history.year_column')}</th>
                  <th scope='col' className='pb-2 pr-2'>{t('budget.history.amount_column')}</th>
                  <th scope='col' className='pb-2'>{t('budget.history.basis_column')}</th>
                </tr>
              </thead>
              <tbody>
                {observations.map(({ year, value, basis, source }) => (
                  <tr key={year} className='border-b border-neutral-border align-top'>
                    <th scope='row' className='py-2 pr-2 font-normal tabular-nums'>{year}</th>
                    <td className='py-2 pr-2 tabular-nums'>{value == null ? t('foundation.no_chart_value') : formatAmount(value)}</td>
                    <td className='py-2'>
                      {value == null ? '—' : t(basis ? `budget.history.${basis}` : 'budget.history.unconfirmed')}
                      {source && <span className='block text-xs text-neutral-muted'>{source}</span>}
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
