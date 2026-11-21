'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import type { Qualifications } from '@/lib/evidence/qualification';
import { ChevronDown } from 'lucide-react';
import { useId, useState } from 'react';

export interface ChartEntry {
  year: string;
  external: number | null;
  domestic: number | null;
  total: number | null;
  gdpRatio: number | null;
  modelled: boolean;
  qualifications?: Qualifications;
  stockMonth?: string | null;
  gdpYear?: number;
}

type PlotKey = 'total' | 'gdpRatio';
type PlotRow = Pick<ChartEntry, 'year' | 'total' | 'gdpRatio' | 'domestic' | 'external' | 'stockMonth' | 'gdpYear'>;
type Format = (value: number) => string;

function reportedAmount(row: ChartEntry, field: 'total' | 'external' | 'domestic') {
  const status = row.qualifications?.[field]?.status;
  const value = row[field];
  return value != null && Number.isFinite(value) && value >= 0 &&
    (!status || status === 'qualified' || status === 'verified') ? value : null;
}

function timelineYears(data: ChartEntry[]): PlotRow[] {
  const byYear = new Map(data.filter(row => /^\d{4}$/.test(row.year) && Number(row.year) >= 1900 &&
    Number(row.year) <= new Date().getUTCFullYear()).map(row => [Number(row.year), row]));
  const years = Array.from(byYear.keys()).sort((a, b) => a - b);
  if (years.length === 0) return [];
  return Array.from({ length: years[years.length - 1] - years[0] + 1 }, (_, index) => {
    const year = years[0] + index;
    const row = byYear.get(year);
    const total = row ? reportedAmount(row, 'total') : null;
    return {
      year: String(year), total,
      gdpRatio: row?.gdpRatio ?? null,
      stockMonth: total != null ? row?.stockMonth : undefined,
      gdpYear: row?.gdpYear,
      external: row ? reportedAmount(row, 'external') : null,
      domestic: row ? reportedAmount(row, 'domestic') : null,
    };
  });
}

function scaleTicks(highest: number) {
  if (highest === 0) return [0, 0.5, 1];
  const magnitude = 10 ** Math.floor(Math.log10(highest / 3));
  const step = [1, 2, 2.5, 5, 10].map(size => size * magnitude).find(size => size >= highest / 3) ?? highest;
  return Array.from({ length: Math.ceil(highest / step) + 1 }, (_, index) => index * step);
}

function plotSegments(rows: PlotRow[], key: PlotKey, ceiling: number) {
  const segments: Array<Array<{ x: number; y: number; index: number }>> = [];
  let segment: (typeof segments)[number] = [];
  for (const [index, row] of Array.from(rows.entries())) {
    const value = row[key];
    if (value == null) {
      if (segment.length) segments.push(segment);
      segment = [];
    } else {
      segment.push({ index, x: yearX(index, rows.length), y: 100 - 100 * value / ceiling });
    }
  }
  if (segment.length) segments.push(segment);
  return segments;
}

function yearX(index: number, length: number) {
  const edges = 5;
  return length === 1 ? 50 : edges + (100 - 2 * edges) * index / (length - 1);
}

function TimelinePlot({ rows, metric, selected, select, title, empty, format, axisFormat }: {
  rows: PlotRow[]; metric: PlotKey; selected: number; select: (year: string) => void;
  title: TranslationKey; empty: TranslationKey; format: Format; axisFormat: Format;
}) {
  const { t } = useLang();
  const heading = useId();
  const available = rows.filter(row => row[metric] != null);
  const first = available[0];
  const last = available[available.length - 1];
  const ticks = scaleTicks(Math.max(0, ...available.map(row => row[metric]!)));
  const ceiling = ticks[ticks.length - 1];
  const segments = plotSegments(rows, metric, ceiling);
  const points = segments.flat();
  const markCount = Math.min(4, rows.length);
  const yearMarks = Array.from({ length: markCount }, (_, index) =>
    Math.round(index * (rows.length - 1) / Math.max(1, markCount - 1)));

  return (
    <figure aria-labelledby={heading} className='min-w-0 space-y-2' data-home-debt-plot={metric}>
      <figcaption id={heading} className='font-display text-xl font-semibold text-neutral-text'>{t(title)}</figcaption>
      {available.length === 0 ? <p className='text-sm text-neutral-muted'>{t(empty)}</p> : <>
        <p className='text-sm text-neutral-muted'>
          {first === last
            ? t('home.debt.chart_single').replace('{year}', last.year).replace('{value}', format(last[metric]!))
            : t('home.debt.chart_range').replace('{first_year}', first.year).replace('{first_value}', format(first[metric]!))
                .replace('{last_year}', last.year).replace('{last_value}', format(last[metric]!))}
        </p>
        <div className='grid min-w-0 grid-cols-[4rem_minmax(0,1fr)] pb-2 pt-2' aria-hidden='true'>
          <div className='relative text-right text-xs tabular-nums text-neutral-muted'>
            {ticks.map(tick => <span key={tick} className='absolute right-2 -translate-y-1/2'
              style={{ top: `${100 - 100 * tick / ceiling}%` }}>{axisFormat(tick)}</span>)}
          </div>
          <div className={`relative cursor-crosshair border-x border-neutral-border ${metric === 'total' ? 'h-[clamp(8rem,30vw,14rem)]' : 'h-[clamp(6.5rem,22vw,10.5rem)]'}`}
            data-debt-plot-target onPointerUp={event => {
              const bounds = event.currentTarget.getBoundingClientRect();
              const fraction = ((event.clientX - bounds.left) / bounds.width * 100 - 5) / 90;
              const next = Math.min(rows.length - 1, Math.max(0, Math.round(fraction * (rows.length - 1))));
              select(rows[next].year);
            }}>
            <svg viewBox='0 0 100 100' preserveAspectRatio='none' className='pointer-events-none absolute inset-0 h-full w-full' focusable='false'>
              {ticks.map(tick => <line key={tick} x1={0} x2={100} y1={100 - 100 * tick / ceiling} y2={100 - 100 * tick / ceiling}
                vectorEffect='non-scaling-stroke' stroke='rgb(var(--c-neutral-border))' />)}
              {segments.map(segment => {
                const line = segment.map(({ x, y }, index) => `${index === 0 ? 'M' : 'L'} ${x} ${y}`).join(' ');
                return <g key={segment[0].index} data-debt-line-segment>
                  {metric === 'total' && segment.length > 1 && <path d={`${line} L ${segment[segment.length - 1].x} 100 L ${segment[0].x} 100 Z`}
                    fill='var(--signal-alarm)' fillOpacity={0.12} />}
                  <path d={line} fill='none' stroke='rgb(var(--c-neutral-text))' strokeWidth={2}
                    strokeLinejoin='round' vectorEffect='non-scaling-stroke' />
                </g>;
              })}
              <line x1={yearX(selected, rows.length)} x2={yearX(selected, rows.length)} y1={0} y2={100}
                vectorEffect='non-scaling-stroke' stroke='rgb(var(--c-neutral-text))' strokeDasharray='2 3' />
            </svg>
            {points.map(({ index, x, y }) => <span key={index} data-debt-point={rows[index].year}
              className={`pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-neutral-text ${selected === index ? 'h-3 w-3 bg-neutral-text' : 'h-2 w-2 bg-surface-base'}`}
              style={{ left: `${x}%`, top: `${y}%` }} />)}
          </div>
          <div />
          <div className='relative h-5 pt-1 text-xs tabular-nums text-neutral-muted'>
            {yearMarks.map((index, order) => <span key={index} data-debt-year-mark={rows[index].year}
              className={`absolute ${order === 0 && yearMarks.length > 1 ? '' : order === yearMarks.length - 1 ? '-translate-x-full' : '-translate-x-1/2'}`}
              style={{ left: `${yearX(index, rows.length)}%` }}>{rows[index].year}</span>)}
          </div>
        </div>
      </>}
    </figure>
  );
}

export default function NationalDebtChart({ data }: { data: ChartEntry[] }) {
  const { t, lang } = useLang();
  const selectId = useId();
  const [year, selectYear] = useState<string>();
  const rows = timelineYears(data);
  if (rows.length === 0) return <p className='text-sm text-neutral-muted'>{t('home.debt.no_timeline')}</p>;
  const selected = rows.findIndex(row => row.year === year);
  const selection = selected < 0 ? rows.length - 1 : selected;
  const row = rows[selection];
  const numbers = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE', { maximumFractionDigits: 2 });
  const ratio: Format = value => `${numbers.format(value)}%`;
  const axisMoney: Format = value => value >= 1000 ? `${numbers.format(value / 1000)}T` : `${numbers.format(value)}B`;
  const money: Format = value => `KES ${value >= 1000 ? `${(value / 1000).toFixed(2)}T` : `${numbers.format(value)}B`}`;
  const amount = (value: number | null, formatter = money) => value == null ? t('home.debt.chart_unavailable') : formatter(value);
  const columns = [
    { key: 'total', label: 'home.debt.chart_nominal_short', format: money },
    { key: 'domestic', label: 'home.debt.domestic', format: money },
    { key: 'external', label: 'home.debt.external', format: money },
    { key: 'gdpRatio', label: 'home.debt.tooltip_gdp', format: ratio },
  ] as const;

  return (
    <div className='min-w-0 space-y-4' data-home-debt-charts>
      <TimelinePlot rows={rows} metric='total' selected={selection} select={selectYear}
        title='home.debt.chart_nominal' empty='home.debt.chart_no_nominal' format={money} axisFormat={axisMoney} />
      <TimelinePlot rows={rows} metric='gdpRatio' selected={selection} select={selectYear}
        title='home.debt.chart_gdp' empty='home.debt.chart_no_ratio' format={ratio} axisFormat={ratio} />
      <div className='flex flex-wrap items-center gap-2'>
        <label htmlFor={selectId} className='shrink-0 text-sm font-semibold text-neutral-text'>{t('home.debt.chart_year')}</label>
        <div className='relative'>
          <select id={selectId} value={row.year} onChange={event => selectYear(event.currentTarget.value)}
            className='min-h-11 appearance-none rounded border border-neutral-border bg-surface-base pl-3 pr-9 text-base text-neutral-text'>
            {rows.map(option => <option key={option.year}>{option.year}</option>)}
          </select>
          <ChevronDown size={16} aria-hidden='true' className='pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-neutral-text' />
        </div>
      </div>
      <div aria-live='polite' data-home-debt-readout className='audit-panel space-y-2 p-3'>
        <p className='font-semibold text-neutral-text'>{row.year}</p>
        <dl className='grid grid-cols-2 gap-3 text-sm text-neutral-text sm:grid-cols-4'>
          {columns.map(({ key, label, format }) => <div key={key}>
            <dt className='text-neutral-muted'>{t(label)}</dt>
            <dd className='font-semibold tabular-nums'>{amount(row[key], format)}</dd>
          </div>)}
        </dl>
        {row.stockMonth && <p className='text-sm text-neutral-muted'>
          {row.gdpRatio != null && row.gdpYear
            ? t('home.debt.chart_ratio_basis').replace('{month}', row.stockMonth).replace('{year}', String(row.gdpYear))
            : t('home.debt.chart_stock_basis').replace('{month}', row.stockMonth)}
        </p>}
      </div>
      <details>
        <summary className='inline-flex min-h-11 cursor-pointer items-center gap-2 rounded text-sm font-semibold text-neutral-text underline underline-offset-4'>
          <ChevronDown size={16} aria-hidden='true' /> {t('home.debt.chart_table')}
        </summary>
        <table className='w-full table-fixed border-collapse text-left text-sm text-neutral-text [overflow-wrap:anywhere]'>
          <caption className='sr-only'>{t('home.debt.chart_table')}</caption>
          <thead><tr className='border-b border-neutral-border'>
            <th scope='col' className='w-12 py-2'>{t('home.debt.chart_year_column')}</th>
            {columns.map(({ key, label }) => <th key={key} scope='col' className='px-1 py-2'>{t(label)}</th>)}
          </tr></thead>
          <tbody>
            {rows.map(item => <tr key={item.year} className='border-b border-neutral-border align-top'>
              <th scope='row' className='py-2 font-semibold'>{item.year}</th>
              {columns.map(({ key, format }) => <td key={key} className='px-1 py-2 tabular-nums'>{amount(item[key], format)}</td>)}
            </tr>)}
          </tbody>
        </table>
      </details>
    </div>
  );
}
