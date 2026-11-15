'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import ChartReadout, { useChartReadout } from './ChartReadout';

type CountyPoint = { id: string; label: string; percentage: number | null };

export default function SpendingDistribution({ counties, target, national, takeaway }: {
  counties: readonly CountyPoint[];
  target: { value: number; label: string };
  national?: { value: number; label: string };
  takeaway: string;
}) {
  const { t, lang } = useLang();
  const { activeId, trigger } = useChartReadout();
  const format = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE', { maximumFractionDigits: 1 });
  const entries = counties.map(county => ({
    ...county,
    value: county.percentage == null || !Number.isFinite(county.percentage)
      ? null : `${format.format(county.percentage)}%`,
  }));
  const plotted = entries.filter(entry => entry.value !== null);
  const numbers = [...plotted.map(entry => entry.percentage!), target.value, ...(national ? [national.value] : [])];
  const min = Math.floor(Math.min(...numbers) / 10) * 10;
  const max = Math.ceil(Math.max(...numbers) / 10) * 10;
  const x = (value: number) => {
    const ratio = (value - min) / Math.max(10, max - min);
    return `calc(${ratio * 100}% + ${22 - 44 * ratio}px)`;
  };
  const missing = t('foundation.no_chart_value');
  return (
    <ChartReadout takeaway={takeaway} activeId={activeId} data={entries} columns={[t('foundation.county'), t('foundation.spent_share')]}>
      <ul className='flex flex-wrap gap-x-4 text-xs'>
        {[target, national].filter((guide): guide is { value: number; label: string } => Boolean(guide))
          .map(guide => <li key={guide.label}>{guide.label} · {format.format(guide.value)}%</li>)}
      </ul>
      <div className='relative min-h-28 border-b border-neutral-border'>
        {[target, national].filter((guide): guide is { value: number; label: string } => Boolean(guide))
          .map(guide => <span aria-hidden='true' key={guide.label} className='absolute inset-y-0 border-l border-dashed border-current' style={{ left: x(guide.value) }} />)}
        {plotted.map((entry, index) => (
          <button key={entry.id} {...trigger(entry, missing)}
            className='group absolute grid h-11 w-11 -translate-x-1/2 place-items-center rounded focus-visible:z-10'
            style={{ left: x(entry.percentage!), top: `${(index % 5) * 15}px` }}>
            <span aria-hidden='true' className={`h-2 w-2 rounded-full ${entry.percentage! < target.value ? 'bg-signal-caution' : 'bg-signal-good'} ${activeId === entry.id ? 'outline outline-offset-2 outline-current' : ''}`} />
          </button>
        ))}
      </div>
      <p aria-hidden='true' className='flex justify-between text-xs text-neutral-muted'><span>{min}%</span><span>{max}%</span></p>
    </ChartReadout>
  );
}
