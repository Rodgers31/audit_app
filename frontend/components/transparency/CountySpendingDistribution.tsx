'use client';

import ChartReadout from '@/components/charts/ChartReadout';
import { useLang } from '@/lib/i18n/LangProvider';
import { countyDistributionMessages as messages } from '@/lib/i18n/messages/transparency';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useEffect, useId, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react';
import { COUNTY_SPENDING_TARGET as TARGET, type CountySpendingPoint } from './moneyFlowPresentation';
import styles from './MoneyFlowPresentation.module.css';

const ROW_STEP = 14;
const ROW_COUNT = 6;

type PlotPoint = CountySpendingPoint & { x: number; y: number; below: boolean };

function scale(counties: CountySpendingPoint[], national: number | null) {
  const values = [TARGET, ...counties.flatMap(({ percentage }) => percentage == null ? [] : [percentage])];
  if (national != null) values.push(national);
  const minimum = Math.floor(Math.min(...values) / 10) * 10;
  const maximum = Math.max(minimum + 10, Math.ceil(Math.max(...values) / 10) * 10);
  return { minimum, maximum, x: (value: number) => (value - minimum) / (maximum - minimum) };
}

export default function CountySpendingDistribution({
  counties,
  national,
  belowCount,
  filtering,
  onFilter,
}: {
  counties: CountySpendingPoint[];
  national: number | null;
  belowCount: number;
  filtering: boolean;
  onFilter: () => void;
}) {
  const { lang, t } = useLang();
  const helpId = useId();
  const chart = useRef<HTMLDivElement>(null);
  const plot = useRef<HTMLSpanElement>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  useEffect(() => {
    if (selected == null) return;
    function clearOutside(event: PointerEvent) {
      if (event.target instanceof Node && chart.current?.contains(event.target)) return;
      setSelected(null);
      setHovered(null);
    }
    document.addEventListener('pointerdown', clearOutside);
    return () => document.removeEventListener('pointerdown', clearOutside);
  }, [selected]);
  const copy = (key: keyof typeof messages, values: Record<string, number | string> = {}) =>
    messages[key][lang].replace(/\{(\w+)\}/g, (match, name) => String(values[name] ?? match));
  const format = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE', { maximumFractionDigits: 2 });

  const sorted = counties.filter(
    (point): point is CountySpendingPoint & { percentage: number } => point.percentage != null
  ).sort((left, right) => left.percentage - right.percentage || left.label.localeCompare(right.label));
  if (sorted.length === 0) return <p className={styles.distributionMissing}>{copy('unavailable')}</p>;

  const { minimum, maximum, x } = scale(counties, national);
  const plotted = sorted.map((point, index): PlotPoint => ({
    ...point, x: x(point.percentage), y: 8 + (index % ROW_COUNT) * ROW_STEP,
    below: point.percentage < TARGET,
  }));
  const active = hovered ?? selected;
  const data = counties.map(({ id, label, percentage }) => ({
    id, label, value: percentage == null ? null : `${format.format(percentage)}%`,
  }));
  const guides = [
    { label: copy('targetGuide', { percent: TARGET }), value: TARGET, target: true },
  ];
  if (national != null) guides.push({
    label: copy('nationalGuide', { percent: format.format(national) }), value: national, target: false,
  });
  const step = Math.ceil((maximum - minimum) / 30) * 10;
  const ticks = [minimum];
  for (let value = minimum + step; value < maximum; value += step) ticks.push(value);
  ticks.push(maximum);

  function nearest(event: { clientX: number; clientY: number }) {
    const bounds = plot.current?.getBoundingClientRect();
    if (!bounds) return null;
    let nearestPoint: PlotPoint | null = null;
    let nearestDistance = Infinity;
    for (const point of plotted) {
      const distance = Math.hypot(
        event.clientX - bounds.left - bounds.width * point.x,
        event.clientY - bounds.top - point.y
      );
      if (distance < nearestDistance) {
        nearestPoint = point;
        nearestDistance = distance;
      }
    }
    return nearestPoint;
  }

  function move(direction: number) {
    setHovered(null);
    setSelected((current) => {
      const index = plotted.findIndex((point) => point.id === current);
      if (index === -1) return plotted[direction < 0 ? plotted.length - 1 : 0].id;
      return plotted[(index + direction + plotted.length) % plotted.length].id;
    });
  }

  function select(event: MouseEvent<HTMLButtonElement>) {
    setHovered(null);
    if (event.detail === 0) {
      setSelected((current) => current == null ? plotted[0].id : null);
      return;
    }
    const point = nearest(event);
    if (!point) return;
    // A mark can contain multiple counties at exactly the same coordinates.
    // Repeated taps cycle through them without stacking pointer targets.
    const coincident = plotted.filter((entry) => entry.x === point.x && entry.y === point.y);
    setSelected((current) => {
      const index = coincident.findIndex((entry) => entry.id === current);
      if (coincident.length === 1 && index === 0) return null;
      return coincident[(index + 1) % coincident.length].id;
    });
  }

  function handleKey(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      move(event.key === 'ArrowRight' ? 1 : -1);
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      setHovered(null);
      setSelected(plotted[event.key === 'Home' ? 0 : plotted.length - 1].id);
    }
  }

  function clearOnEscape(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'Escape') return;
    setHovered(null);
    setSelected(null);
  }

  return (
    <div className={styles.distribution}>
      <div ref={chart} onKeyDown={clearOnEscape}>
        <ChartReadout
          activeId={active}
          data={data}
          columns={[t('foundation.county'), t('foundation.spent_share')]}
          takeaway={copy('takeaway', { below: belowCount, reported: plotted.length, target: TARGET })}>
          {plotted.length !== 47 && (
            <p className={styles.distributionCoverage}>{copy('coverage', { reported: plotted.length })}</p>
          )}
          <div className={styles.distributionGuides}>
            {guides.map((guide) => (
              <span className={styles.distributionGuide} key={guide.label} data-target={guide.target}>
                {guide.label}
              </span>
            ))}
          </div>
          <button
            type='button'
            className={styles.distributionPlot}
            aria-label={copy('plot')}
            aria-describedby={helpId}
            onClick={select}
            onKeyDown={handleKey}
            onPointerMove={(event) => {
              if (event.pointerType === 'mouse') setHovered(nearest(event)?.id ?? null);
            }}
            onPointerLeave={() => setHovered(null)}>
            <span ref={plot} className={styles.distributionBounds} aria-hidden='true'>
              <span className={styles.targetArea} style={{ width: `${x(TARGET) * 100}%` }} />
              {guides.map((guide) => (
                <span
                  key={guide.label}
                  className={styles.distributionLine}
                  data-target={guide.target}
                  style={{ left: `${x(guide.value) * 100}%` }}
                />
              ))}
              {plotted.map(({ id, x, y, below }) => (
                <span key={id} className={styles.distributionDot} data-below={below} data-selected={active === id}
                  style={{ left: `${x * 100}%`, top: y }} />
              ))}
            </span>
          </button>
          <div className={styles.distributionAxis} aria-hidden='true'>
            {ticks.map((value) => (
              <span key={value} style={{ left: `${x(value) * 100}%` }}>{format.format(value)}%</span>
            ))}
          </div>
          <div className={styles.distributionControls}>
            <p id={helpId}>{copy('plotHelp')}</p>
            <div className={styles.distributionArrows}>
              <button type='button' className='audit-control' aria-label={copy('previous')} onClick={() => move(-1)}>
                <ChevronLeft size={18} aria-hidden='true' />
              </button>
              <button type='button' className='audit-control' aria-label={copy('next')} onClick={() => move(1)}>
                <ChevronRight size={18} aria-hidden='true' />
              </button>
            </div>
          </div>
        </ChartReadout>
      </div>
      {belowCount > 0 && (
        <button
          type='button'
          className={`audit-control ${styles.sortChip}`}
          aria-pressed={filtering}
          onClick={onFilter}>
          {copy('belowChip', { count: belowCount })}
        </button>
      )}
    </div>
  );
}
