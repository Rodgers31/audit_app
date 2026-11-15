'use client';

import { useState, type ReactNode } from 'react';
import { useLang } from '@/lib/i18n/LangProvider';
import ResponsiveTable from '@/components/ui/ResponsiveTable';

export type ChartDatum = { id: string; label: string; value: string | null };

export function useChartReadout() {
  const [active, setActive] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  return {
    activeId: active ?? selected,
    trigger: (datum: ChartDatum, missingLabel: string) => ({
      type: 'button' as const,
      'aria-label': `${datum.label} · ${datum.value ?? missingLabel}`,
      'aria-pressed': selected === datum.id,
      onPointerEnter: (event: React.PointerEvent) => {
        if (event.pointerType === 'mouse') setActive(datum.id);
      },
      onPointerLeave: () => setActive(null),
      onBlur: () => setActive(null),
      onFocus: () => setActive(datum.id),
      onClick: () => {
        setActive(null);
        setSelected(current => current === datum.id ? null : datum.id);
      },
      onKeyDown: (event: React.KeyboardEvent) => {
        if (event.key === 'Escape') {
          setActive(null);
          setSelected(null);
        }
      },
    }),
  };
}

export default function ChartReadout({ takeaway, columns, data, activeId, children }: {
  takeaway: string;
  columns: [string, string];
  data: readonly ChartDatum[];
  activeId: string | null;
  children: ReactNode;
}) {
  const { t } = useLang();
  const current = data.find(datum => datum.id === activeId);
  const missing = t('foundation.no_chart_value');
  return (
    <figure className='min-w-0 space-y-2'>
      <figcaption className='text-base font-semibold'>{takeaway}</figcaption>
      <p aria-live='polite' className='min-h-5 text-sm text-neutral-muted'>
        {current && <>{current.label} · {current.value ?? missing}</>}
      </p>
      {children}
      <details className='text-sm'>
        <summary className='flex min-h-11 cursor-pointer items-center underline underline-offset-4'>{t('foundation.chart_table')}</summary>
        <ResponsiveTable>
          <table className='w-full table-auto text-left'>
            <thead><tr>{columns.map(label => <th key={label} scope='col' className='border-b border-neutral-border py-2 pr-2'>{label}</th>)}</tr></thead>
            <tbody>{data.map(datum => (
              <tr key={datum.id}>
                <th scope='row' className='border-b border-neutral-border py-2 pr-2 font-normal'>{datum.label}</th>
                <td className='border-b border-neutral-border py-2 tabular-nums'>{datum.value ?? missing}</td>
              </tr>
            ))}</tbody>
          </table>
        </ResponsiveTable>
      </details>
    </figure>
  );
}
