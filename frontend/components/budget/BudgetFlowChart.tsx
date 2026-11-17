'use client';

import ChartReadout from '@/components/charts/ChartReadout';
import { useLang } from '@/lib/i18n/LangProvider';
import { useEffect, useId, useRef, useState, type KeyboardEvent, type MouseEvent, type PointerEvent as ReactPointerEvent } from 'react';
import styles from './BudgetFlowChart.module.css';

export interface BudgetFlowSegment {
  id: 'tax' | 'nonTax' | 'ordinary' | 'aia' | 'grants' | 'borrowing' | 'cashAdjustment' |
    'interest' | 'recurrent' | 'development' | 'counties' | 'contingency';
  amount: number;
}

export function formatBudgetPart(amount: number): string {
  const abs = Math.abs(amount);
  const formatted = abs >= 1000 ? `${(abs / 1000).toFixed(2)}T`
    : abs >= 1 ? `${abs.toFixed(0)}B`
    : abs > 0 ? `${(abs * 1000).toFixed(0)}M` : '0';
  return amount < 0 ? `−${formatted}` : formatted;
}

export function formatBudgetShare(amount: number, total: number): string {
  const share = amount / total * 100;
  if (share > 0 && share < 0.1) return '<0.1';
  const whole = Math.round(share);
  if ((whole === 0 && share > 0) || (whole === 100 && share < 100)) {
    const precise = share.toLocaleString('en-KE', { maximumFractionDigits: 2 });
    return precise === '100' ? '<100' : precise;
  }
  return String(whole);
}

export default function BudgetFlowChart({
  heading, takeaway, basis, total, segments, notes,
}: {
  heading: string;
  takeaway: string;
  basis: string;
  total: number;
  segments: BudgetFlowSegment[];
  notes?: string[];
}) {
  const { lang, t } = useLang();
  const headingId = useId();
  const instructionId = useId();
  const chartRef = useRef<HTMLElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [selection, setSelection] = useState<string | null>(null);
  const selected = preview ?? selection;
  const hasSigned = segments.some(segment => segment.amount < 0);
  const canPlot = total > 0 && !hasSigned;
  const exactNumber = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE');
  const parts = segments.map(({ id, amount }) => ({
    id,
    amount,
    label: t(`budget.flow.${id}`),
    value: `KES ${exactNumber.format(Math.round(amount * 1e9))}${
      canPlot ? ` · ${formatBudgetShare(amount, total)}%` : ''
    }`,
  }));
  const plotted = canPlot ? parts.filter(segment => segment.amount > 0) : [];
  const plottedTotal = plotted.reduce((sum, part) => sum + part.amount, 0);

  useEffect(() => {
    if (!selection) return;
    function clearOutside(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Element &&
          chartRef.current?.contains(target) &&
          target.closest('button, summary')) return;
      setSelection(null);
      setPreview(null);
    }
    document.addEventListener('pointerdown', clearOutside);
    return () => document.removeEventListener('pointerdown', clearOutside);
  }, [selection]);

  function toggle(id: string) {
    setPreview(null);
    setSelection(current => current === id ? null : id);
  }

  function pointedSegment(event: MouseEvent<HTMLButtonElement> | ReactPointerEvent<HTMLButtonElement>) {
    const { left, width } = event.currentTarget.getBoundingClientRect();
    if (width === 0) return null;
    const position = (event.clientX - left) / width * plottedTotal;
    let end = 0;
    return plotted.find((part) => {
      end += part.amount;
      return position < end;
    })?.id ?? plotted.at(-1)?.id ?? null;
  }

  function chooseSegment(event: MouseEvent<HTMLButtonElement>) {
    const id = event.detail === 0
      ? preview ?? selection ?? plotted[0]?.id
      : pointedSegment(event);
    if (id) toggle(id);
  }

  function moveSegment(event: KeyboardEvent<HTMLButtonElement>) {
    const current = plotted.findIndex(part => part.id === selected);
    let next: number;
    switch (event.key) {
      case 'ArrowLeft':
        next = current > 0 ? current - 1 : plotted.length - 1;
        break;
      case 'ArrowRight':
        next = (current + 1) % plotted.length;
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = plotted.length - 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    setPreview(plotted[next].id);
  }

  return (
    <section ref={chartRef} aria-labelledby={headingId} className='min-w-0'
      onKeyDown={event => {
        if (event.key === 'Escape') {
          setPreview(null);
          setSelection(null);
        }
      }}>
      <h3 id={headingId} className='font-display text-xl font-bold leading-tight'>{heading}</h3>
      <p className='text-xs text-neutral-muted'>{basis}</p>
      <ChartReadout
        activeId={selected}
        columns={[t('budget.flow.component'), t(canPlot ? 'budget.flow.amount_share' : 'budget.flow.amount')]}
        data={parts}
        takeaway={canPlot ? takeaway : t(hasSigned ? 'budget.flow.signed' : 'budget.flow.zero_total')}>
        {plotted.length > 0 && (
          <>
            <span id={instructionId} className='sr-only'>{t('budget.flow.arrow_help')}</span>
            <div className={styles.plot}>
              <div className={styles.bar} aria-hidden='true'>
                {plotted.map(part => (
                  <span key={part.id} className={styles.part} data-segment={part.id} data-highlighted={selected === part.id}
                    style={{ flexGrow: part.amount }}>
                    <span className={styles.share}>{formatBudgetShare(part.amount, total)}%</span>
                  </span>
                ))}
              </div>
              <button className={styles.plotControl} type='button'
                aria-label={t('budget.flow.explore').replace('{name}', heading)}
                aria-describedby={instructionId}
                onClick={chooseSegment}
                onKeyDown={moveSegment}
                onFocus={() => setPreview(selection ?? plotted[0].id)}
                onBlur={() => setPreview(null)}
                onPointerMove={event => { if (event.pointerType === 'mouse') setPreview(pointedSegment(event)); }}
                onPointerLeave={event => { if (event.pointerType === 'mouse') setPreview(null); }} />
            </div>
          </>
        )}
        <ul className={styles.legend}>
          {parts.filter(part => part.id !== 'cashAdjustment' || part.amount !== 0).map(part => (
            <li key={part.id}>
              <button className={styles.legendButton} type='button' aria-pressed={selection === part.id}
                data-highlighted={selected === part.id}
                onFocus={() => setPreview(part.id)}
                onBlur={() => setPreview(null)}
                onPointerEnter={event => { if (event.pointerType === 'mouse') setPreview(part.id); }}
                onPointerLeave={event => { if (event.pointerType === 'mouse') setPreview(null); }}
                onClick={() => toggle(part.id)}>
                <span className={styles.swatch} data-segment={part.id} aria-hidden='true' />
                <span className='min-w-0'>
                  <span className='block font-medium'>{part.label}</span>
                  <span className='block tabular-nums text-neutral-muted'>KES {formatBudgetPart(part.amount)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        {notes?.map(note => <p key={note} className='text-sm text-neutral-muted'>{note}</p>)}
      </ChartReadout>
    </section>
  );
}
