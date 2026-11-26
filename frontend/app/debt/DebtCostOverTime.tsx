'use client';

import { useEffect, useId, useRef, useState, type CSSProperties, type PointerEvent } from 'react';
import DebtServiceObservations from '@/components/debt/DebtServiceObservations';
import type { DebtServicePoint } from '@/lib/debt/debtServiceSeries';
import { useLang } from '@/lib/i18n/LangProvider';
import { chartFiscalYears, ratioPath, serviceTicks, type CostYear } from './debtCostPlot';
import styles from './DebtCostOverTime.module.css';

const HALF_REVENUE = 50;
const compactAmount = new Intl.NumberFormat('en-KE', { notation: 'compact', maximumFractionDigits: 2 });
const roundedShare = new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 });
const exactShare = new Intl.NumberFormat('en-KE', { maximumFractionDigits: 1 });
const fullAmount = new Intl.NumberFormat('en-KE', { maximumFractionDigits: 20 });
const vintageLabels = {
  Actual: 'debt.cost.actual',
  Preliminary: 'debt.cost.preliminary',
  Approved: 'debt.cost.approved',
  'Supplementary I': 'debt.cost.supplementary',
} as const;
type Measure = 'service' | 'ratio';
type Scrub = { pointer: number; startX: number; year: string | null };

function labelFor(measure: Measure, value: number) {
  if (measure === 'service') return compactAmount.format(value);
  const rounded = Math.round(value);
  return rounded !== value && (rounded === HALF_REVENUE || rounded === 0)
    ? exactShare.format(value)
    : roundedShare.format(value);
}

function latestValue(years: CostYear[], measure: Measure) {
  return years.findLast(year => year.point?.[measure] != null);
}

function CostPlot({ measure, years, active, selected, onPreview, onSelect }: {
  measure: Measure;
  years: CostYear[];
  active: string | null;
  selected: string | null;
  onPreview: (year: string | null) => void;
  onSelect: (year: string | null) => void;
}) {
  const { t } = useLang();
  const pointer = useRef<Scrub | null>(null);
  const suppressTouchClick = useRef(false);
  const line = measure === 'ratio';
  const values = years.map(year => year.point?.[measure] ?? null);
  const recent = latestValue(years, measure);
  const observed = recent?.point?.[measure];
  const vintage = recent?.point?.serviceQualification?.vintage;
  const vintageKey = vintageLabels[vintage as keyof typeof vintageLabels];
  const ratioMax = Math.ceil(Math.max(100, ...values.map(value => value ?? 0)) / 25) * 25;
  const ticks = line ? (ratioMax === 100 ? [0, 100] : [0, 100, ratioMax]) : serviceTicks(values);
  const maximum = ticks[ticks.length - 1];
  const extreme = Math.max(...values.map(value => value ?? 0));
  const reference = HALF_REVENUE / maximum * 100;
  const missing = t('foundation.no_chart_value');
  const key = line ? 'debt.cost.share' : 'debt.cost.repayments';
  const layout = { '--year-count': years.length } as CSSProperties;

  function startScrub(event: PointerEvent<HTMLDivElement>) {
    suppressTouchClick.current = false;
    if (line && event.pointerType === 'touch') {
      pointer.current = { pointer: event.pointerId, startX: event.clientX, year: null };
    }
  }

  function moveScrub(event: PointerEvent<HTMLDivElement>) {
    const drag = pointer.current;
    if (!drag || drag.pointer !== event.pointerId || (!drag.year && Math.abs(event.clientX - drag.startX) < 8)) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const position = Math.floor((event.clientX - bounds.left) / bounds.width * years.length);
    drag.year = years[Math.min(years.length - 1, Math.max(0, position))].year;
    onPreview(drag.year);
  }

  function finishScrub(event: PointerEvent<HTMLDivElement>) {
    const drag = pointer.current;
    if (drag?.pointer !== event.pointerId) return;
    if (event.type === 'pointerup' && drag.year) {
      suppressTouchClick.current = true;
      onSelect(drag.year);
    }
    onPreview(null);
    pointer.current = null;
  }

  return (
    <div className='min-w-0' style={layout}>
      <h3 className='text-base font-semibold'>{t(key)}</h3>
      <p className='mt-1 text-sm text-neutral-muted'>
        {recent && observed != null
          ? t(line ? 'debt.cost.share_takeaway' : 'debt.cost.service_takeaway')
            .replace('{amount}', labelFor(measure, observed)).replace('{year}', recent.year)
          : t(line ? 'debt.cost.no_share' : 'debt.cost.no_service')}
      </p>
      {observed != null && (
        <p className='text-sm text-neutral-muted'>
          {vintageKey ? t('debt.cost.basis').replace('{basis}', t(vintageKey)) : t('debt.cost.unconfirmed')}
          {' '}{line && observed > HALF_REVENUE && (
            <strong className='font-semibold text-signal-alarm'>· {t('debt.cost.over_half')}</strong>
          )}
        </p>
      )}
      <div className={`${styles.plot} ${line ? '' : styles.repaymentPlot}`}>
        <div role='img' aria-label={t(line ? 'debt.cost.share_chart' : 'debt.cost.service_chart')} className={styles.graph}>
          {ticks.map(tick => (
            <div key={tick} aria-hidden='true' className={styles.tick} style={{ bottom: `${tick / maximum * 100}%` }}>
              <span>{labelFor(measure, tick)}</span>
            </div>
          ))}
          {line && (
            <>
              <div aria-hidden='true' className={styles.reference} style={{ bottom: `${reference}%` }}>
                <span>{t('debt.cost.half')}</span>
              </div>
              <svg aria-hidden='true' className={styles.line} viewBox={`0 0 ${years.length} 100`} preserveAspectRatio='none'>
                <path data-debt-share-line='' d={ratioPath(values, maximum)} fill='none' stroke='currentColor' strokeWidth='2' vectorEffect='non-scaling-stroke' />
              </svg>
            </>
          )}
          <div aria-hidden='true' className={styles.columns}>
            {years.map(({ point, year }, index) => {
              const value = values[index];
              const current = active === year;
              const latest = year === recent?.year;
              const highest = extreme === value && values.indexOf(extreme) === index;
              const alarm = latest && point?.ratio != null && point.ratio > HALF_REVENUE;
              return (
                <div key={year} className={styles.column}>
                  {current && <span data-debt-cost-guide='' className={styles.guide} />}
                  {value != null && (
                    <>
                      <span
                        data-debt-cost-mark={year}
                        className={line ? styles.dot : styles.bar}
                        data-highlight={current || latest}
                        data-alarm={alarm}
                        style={line ? { bottom: `${value / maximum * 100}%` } : { height: `${value / maximum * 100}%` }}
                      />
                      {(latest || highest) && (
                        <span className={styles.value} style={{ bottom: `calc(${value / maximum * 100}% + 0.5rem)` }}>
                          {labelFor(measure, value)}
                        </span>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>
        <div className={styles.targets} data-debt-cost-targets=''
          onPointerDown={startScrub} onPointerMove={moveScrub}
          onPointerUp={finishScrub} onPointerCancel={finishScrub}>
          {years.map(({ year }, index) => (
            <button key={year} type='button' aria-pressed={selected === year}
              aria-label={`${year} · ${t(key)} · ${values[index] == null ? missing : line ? `KES ${exactShare.format(values[index])}` : `KES ${fullAmount.format(values[index])}`}`}
              onPointerEnter={event => { if (event.pointerType === 'mouse') onPreview(year); }}
              onPointerLeave={event => { if (event.pointerType === 'mouse') onPreview(null); }}
              onFocus={() => onPreview(year)} onBlur={() => onPreview(null)}
              onClick={event => {
                if (event.detail && suppressTouchClick.current) return;
                onPreview(null);
                onSelect(selected === year ? null : year);
              }}
              onKeyDown={event => { if (event.key === 'Escape') { onPreview(null); onSelect(null); } }} />
          ))}
        </div>
      </div>
      <div aria-hidden='true' className={`${styles.axis} ${line ? '' : styles.desktopAxis}`}>
        {years.map(({ shortYear, year }, index) => (
          <span key={year} className={index % 2 && index !== years.length - 1 ? styles.desktopYear : undefined}>{shortYear}</span>
        ))}
      </div>
    </div>
  );
}

export default function DebtCostOverTime({ points }: { points: DebtServicePoint[] }) {
  const { t } = useLang();
  const id = useId();
  const root = useRef<HTMLElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const years = chartFiscalYears(points);
  const active = preview ?? selected;
  const current = years.find(year => year.year === active);
  const count = years.filter(year => year.point?.ratio != null).length;
  const anyValue = years.some(year => year.point?.service != null || year.point?.ratio != null);

  useEffect(() => {
    if (!selected) return;
    const clear = (event: globalThis.PointerEvent) => {
      if (event.target instanceof Element && root.current?.contains(event.target)
        && event.target.closest('[data-debt-cost-targets]')) return;
      setPreview(null);
      setSelected(null);
    };
    document.addEventListener('pointerdown', clear);
    return () => document.removeEventListener('pointerdown', clear);
  }, [selected]);

  return (
    <figure ref={root} className='min-w-0 space-y-3' aria-labelledby={id + '-title'} aria-describedby={id + '-description'}>
      <figcaption>
        <h2 id={id + '-title'} className='font-display text-2xl sm:text-3xl'>{t('debt.cost.title')}</h2>
        <p id={id + '-description'} className='mt-1 text-sm text-neutral-muted'>{t('debt.cost.description')}</p>
      </figcaption>
      {anyValue ? (
        <>
          <div role='status' aria-live='polite' className='min-h-10 text-sm text-neutral-muted sm:min-h-5'>
            {current && (
              <>
                <strong className='font-semibold text-neutral-text'>{current.year}</strong>
                {' · '}{t('debt.cost.repayments')} {current.point?.service == null ? t('foundation.no_chart_value') : `KES ${fullAmount.format(current.point.service)}`}
                {' · '}{current.point?.ratio == null
                  ? t('debt.cost.withheld_share')
                  : t('debt.cost.readout_share').replace('{amount}', exactShare.format(current.point.ratio))}
              </>
            )}
          </div>
          <div className={styles.pair}>
            <CostPlot measure='service' {...{ years, active, selected, onPreview: setPreview, onSelect: setSelected }} />
            <CostPlot measure='ratio' {...{ years, active, selected, onPreview: setPreview, onSelect: setSelected }} />
          </div>
          {count < years.length && <p className='text-sm text-neutral-muted'>
            {t('debt.cost.share_coverage').replace('{count}', String(count)).replace('{total}', String(years.length))}
          </p>}
        </>
      ) : <p className='text-sm text-neutral-muted'>{t('debt.cost.empty')}</p>}
      {points.some(point => !years.some(year => year.point === point)) && (
        <p className='text-sm text-neutral-muted'>{t('debt.cost.history_in_table')}</p>
      )}
      <DebtServiceObservations points={points} />
    </figure>
  );
}
