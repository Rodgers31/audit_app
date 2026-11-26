'use client';

import type { AuditStatistics } from '@/lib/api/audits';
import { useLang } from '@/lib/i18n/LangProvider';
import { AUDITS_MESSAGES } from '@/lib/i18n/messages/audits';
import { useAuditStatistics } from '@/lib/react-query/useAudits';
import { useEffect, useRef, useState } from 'react';

const LEVELS = [
  { id: 'critical', label: 'audits.severity_serious', fill: 'bg-signal-alarm', ink: 'text-white dark:text-gov-dark' },
  { id: 'warning', label: 'audits.severity_warning', fill: 'bg-signal-caution-fill', ink: 'text-gov-dark' },
  { id: 'info', label: 'audits.severity_note', fill: 'bg-chart-context', ink: 'text-gov-dark' },
] as const;

type Level = (typeof LEVELS)[number];
type SeverityRow = Level & { count: number };
type SeverityState =
  | { kind: 'missing' | 'invalid' | 'mismatch' | 'empty' | 'no_coverage' }
  | { kind: 'partial' | 'complete'; rows: SeverityRow[]; total: number; classified: number };

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}

function readSeverity(data: AuditStatistics | undefined, collectionTotal: number | undefined): SeverityState {
  const total = data?.total_findings;
  const counts = data?.by_severity;
  if (total == null || counts == null) return { kind: 'missing' };
  if (!isCount(total) || typeof counts !== 'object' || Array.isArray(counts) ||
      (data?._meta?.entity_scope && data._meta.entity_scope !== 'all')) return { kind: 'invalid' };
  if (!isCount(collectionTotal) || total !== collectionTotal) return { kind: 'mismatch' };

  const values = Object.values(counts);
  if (!values.every(isCount)) return { kind: 'invalid' };
  const received = values.reduce((sum, value) => sum + value, 0);
  if (received > total) return { kind: 'invalid' };
  if (total === 0) return { kind: 'empty' };

  const recorded = LEVELS.flatMap(level => Object.hasOwn(counts, level.id)
    ? [{ ...level, count: counts[level.id] }] : []);
  const classified = recorded.reduce((sum, row) => sum + row.count, 0);
  if (classified === 0) return { kind: 'no_coverage' };
  if (classified < total) return { kind: 'partial', rows: recorded, total, classified };

  // The publication reader groups every finding. Once the three known groups
  // account for the full population, a missing group has a measured zero.
  return { kind: 'complete', rows: LEVELS.map(level => ({ ...level, count: counts[level.id] ?? 0 })), total, classified };
}

interface AuditSeverityProps {
  collectionTotal: number | undefined;
  retryCollection: () => void;
}

export default function AuditSeverity({ collectionTotal, retryCollection }: AuditSeverityProps) {
  const { lang } = useLang();
  const copy = (key: keyof typeof AUDITS_MESSAGES) => AUDITS_MESSAGES[key][lang];
  const number = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE');
  const { data, isPending, isError, isFetching, refetch } = useAuditStatistics();
  const [active, setActive] = useState<Level['id'] | null>(null);
  const panel = useRef<HTMLElement>(null);
  const state = readSeverity(data, collectionTotal);
  const hasChart = state.kind === 'complete';
  const leadingLevel = state.kind === 'complete'
    ? state.rows.reduce((largest, row) => row.count > largest.count ? row : largest)
    : null;
  const periods = Array.isArray(data?.fiscal_years_covered)
    ? data.fiscal_years_covered.filter(period => typeof period === 'string' && period.trim()).join(' · ')
    : '';

  useEffect(() => {
    if (active == null) return;
    function clearOutside(event: PointerEvent) {
      if (event.target instanceof Node && !panel.current?.contains(event.target)) setActive(null);
    }
    document.addEventListener('pointerdown', clearOutside);
    return () => document.removeEventListener('pointerdown', clearOutside);
  }, [active]);

  return (
    <section ref={panel} aria-labelledby='audit-severity-heading' className='min-w-0 space-y-3' data-audit-severity
      onKeyDown={event => { if (event.key === 'Escape') setActive(null); }}>
      <h2 id='audit-severity-heading' className='font-display text-xl text-neutral-text'>
        {copy('audits.severity_title')}
      </h2>
      {isPending ? (
        <p role='status' className='text-sm text-neutral-muted'>{copy('audits.severity_loading')}</p>
      ) : isError ? (
        <div className='space-y-2'>
          <p role='alert' className='text-sm text-neutral-text'>{copy('audits.severity_error')}</p>
          <button type='button' disabled={isFetching} className='audit-control'
            onClick={() => void refetch({ cancelRefetch: false })}>
            {copy(isFetching ? 'audits.severity_loading' : 'audits.retry')}
          </button>
        </div>
      ) : state.kind === 'partial' || state.kind === 'complete' ? (
        <>
          <p className='text-sm text-neutral-text'>
            {leadingLevel
              ? copy('audits.severity_counts')
                .replace('{count}', number.format(leadingLevel.count))
                .replace('{total}', number.format(state.total))
                .replace('{level}', () => copy(leadingLevel.label))
              : copy('audits.severity_partial')
                .replace('{count}', number.format(state.classified))
                .replace('{total}', number.format(state.total))}
          </p>
          {hasChart && (
            <div aria-hidden='true' className='flex h-7 min-w-0 gap-0.5' data-severity-plot>
              {state.rows.filter(row => row.count > 0).map(row => (
                <span key={row.id} data-severity={row.id} style={{ flex: `${row.count} 1 0%` }}
                  className={`flex min-w-0 items-center overflow-hidden rounded [container-type:inline-size] ${row.fill} ${row.ink} ${active === row.id ? 'outline outline-2 outline-offset-1 outline-neutral-text' : ''}`}>
                  {number.format(row.count).length <= 5 && (
                    <span className='hidden px-1.5 text-sm font-semibold tabular-nums [@container(min-width:48px)]:inline'>
                      {number.format(row.count)}
                    </span>
                  )}
                </span>
              ))}
            </div>
          )}
          <ul role='list' className='flex min-w-0 flex-wrap gap-x-1 gap-y-1 text-sm text-neutral-text sm:gap-x-3'>
            {state.rows.map(row => {
              const label = (
                <>
                  <span aria-hidden='true' className={`size-2.5 shrink-0 rounded-sm ${row.fill}`} />
                  {copy(row.label)} <span className='font-normal tabular-nums'>{number.format(row.count)}</span>
                </>
              );
              return (
                <li key={row.id}>
                  {hasChart ? (
                    <button type='button' aria-pressed={active === row.id}
                      className='audit-control min-w-11 gap-1.5 border-transparent px-1 aria-pressed:border-neutral-text'
                      onClick={() => setActive(current => current === row.id ? null : row.id)}>
                      {label}
                    </button>
                  ) : <span className='inline-flex items-center gap-1.5'>{label}</span>}
                </li>
              );
            })}
          </ul>
          {hasChart && (
            <div aria-live='polite' className='empty:!mt-0'>
              {state.rows.filter(row => active === row.id).map(row => (
                <p key={row.id} className='text-sm text-neutral-text'>
                  {copy('audits.severity_readout')
                    .replace('{level}', () => copy(row.label))
                    .replace('{count}', number.format(row.count))
                    .replace('{total}', number.format(state.total))}
                </p>
              ))}
            </div>
          )}
          {periods && (
            <p className='text-sm text-neutral-muted [overflow-wrap:anywhere]'>
              {copy('audits.severity_periods').replace('{periods}', () => periods)}
            </p>
          )}
        </>
      ) : (
        <div className='space-y-2'>
          <p className='text-sm text-neutral-muted'>{copy(`audits.severity_${state.kind}`)}</p>
          {state.kind === 'mismatch' && (
            <button type='button' disabled={isFetching} className='audit-control' onClick={() => {
              retryCollection();
              void refetch({ cancelRefetch: false });
            }}>
              {copy(isFetching ? 'audits.severity_loading' : 'audits.retry')}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
