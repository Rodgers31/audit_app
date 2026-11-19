'use client';

import { useEffect, useRef, useState } from 'react';
import ChartReadout from '@/components/charts/ChartReadout';
import type { AuditTrendsData } from '@/lib/api/audits';
import { useLang } from '@/lib/i18n/LangProvider';
import { AUDITS_MESSAGES } from '@/lib/i18n/messages/audits';

export default function AuditYearBars({ trends }: { trends: AuditTrendsData }) {
  const { lang } = useLang();
  const copy = (key: keyof typeof AUDITS_MESSAGES) => AUDITS_MESSAGES[key][lang];
  const plot = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const format = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE');
  const data = Array.from(new Set(trends.years)).filter(Number.isSafeInteger).sort((a, b) => a - b).map(year => {
    const count = trends.findings_per_year[String(year)];
    const valid = Number.isSafeInteger(count) && count >= 0;
    return { id: String(year), label: String(year), count: valid ? count : null, value: valid ? format.format(count) : null };
  });
  const counts = data.flatMap(datum => datum.count === null ? [] : [datum.count]);
  const max = Math.max(1, ...counts);
  const total = counts.reduce((sum, count) => sum + count, 0);
  const takeaway = data.every(datum => datum.count !== null) && Number.isSafeInteger(total)
    ? copy('audits.years_total').replace('{count}', format.format(total))
    : copy('audits.years_partial');
  const activeId = preview ?? selected;

  // A selected bar stays readable until it is selected again, Escape is pressed,
  // or the reader taps elsewhere. Mouse and focus previews share its readout.
  useEffect(() => {
    function clearOutsideBar(event: PointerEvent) {
      if (event.target instanceof Element && plot.current?.contains(event.target.closest('[data-audit-year]'))) return;
      setSelected(null);
      setPreview(null);
    }
    function clearOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setSelected(null);
        setPreview(null);
      }
    }
    document.addEventListener('pointerdown', clearOutsideBar);
    document.addEventListener('keydown', clearOnEscape);
    return () => {
      document.removeEventListener('pointerdown', clearOutsideBar);
      document.removeEventListener('keydown', clearOnEscape);
    };
  }, []);

  if (!data.length) return <p className='text-sm text-neutral-muted'>{copy('audits.years_empty')}</p>;

  return (
    <div className='min-w-0 space-y-3' data-audit-year-chart>
      <ChartReadout takeaway={takeaway} columns={[copy('audits.year'), copy('audits.year_count')]}
        data={data} activeId={activeId}>
        <div ref={plot} role='region' aria-label={copy('audits.year_scroll')} tabIndex={0}
          className='overflow-x-auto pb-1'
          onKeyDown={event => {
            if (event.target !== event.currentTarget || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
            event.preventDefault();
            const direction = event.key === 'ArrowRight' ? 1 : -1;
            event.currentTarget.scrollLeft += direction * event.currentTarget.clientWidth / 2;
          }}>
          {/* Five years fit at 360px. Longer series scroll within this region. */}
          <div className='grid gap-2 pt-1' style={{ gridTemplateColumns: `repeat(${data.length}, minmax(44px, 1fr))` }}>
            {data.map(datum => (
              <button key={datum.id} type='button' data-audit-year={datum.id}
                aria-pressed={selected === datum.id}
                className='relative flex min-h-11 min-w-11 flex-col rounded text-sm text-neutral-text focus-visible:outline-offset-[-2px]'
                onPointerEnter={event => { if (event.pointerType === 'mouse') setPreview(datum.id); }}
                onPointerLeave={() => setPreview(null)}
                onFocus={() => setPreview(datum.id)} onBlur={() => setPreview(null)}
                onClick={() => {
                  setPreview(null);
                  setSelected(current => current === datum.id ? null : datum.id);
                }}>
                <span className={`order-2 block w-full py-2 tabular-nums ${activeId === datum.id ? 'font-bold underline underline-offset-4' : ''}`}>{datum.label}</span>
                <span className='sr-only'> · </span>
                <span className='order-1 flex min-h-24 w-full flex-1 flex-col items-center justify-end border-b border-neutral-muted'>
                  <span className='w-full break-words pb-1 tabular-nums'>{datum.value ?? copy('audits.unavailable')}</span>
                  <span className='sr-only'> {copy('audits.year_count')}</span>
                  {datum.count !== null && datum.count > 0 && (
                    <span aria-hidden='true' className={`block w-3/5 max-w-12 shrink-0 rounded-t border border-neutral-muted bg-chart-context ${activeId === datum.id ? 'outline outline-2 outline-offset-2 outline-neutral-text' : ''}`}
                      style={{ height: `${datum.count / max * 64}px` }} />
                  )}
                </span>
              </button>
            ))}
          </div>
        </div>
      </ChartReadout>
      <p className='text-sm font-semibold text-neutral-text'>{copy('audits.reports_unavailable')}</p>
      <p className='text-sm leading-relaxed text-neutral-muted'>{copy('audits.coverage_note')}</p>
    </div>
  );
}
