'use client';

import { Fragment, useId, useState } from 'react';
import { useChartReadout } from '@/components/charts/ChartReadout';
import InfoSheet from '@/components/ui/InfoSheet';
import type { PendingBillsAgingObservations, PendingBillsAgingScope } from '@/lib/api/debt';
import { readScopedAging } from '@/lib/debt/scopedPendingBillsAging';
import { formatAsAt } from '@/lib/counties/pendingBillsNotes';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';

const populations: Record<PendingBillsAgingScope, TranslationKey> = {
  county_executive: 'pending_aging.county_executive',
  county_assembly: 'pending_aging.county_assembly',
  national: 'pending_aging.national',
  combined: 'pending_aging.combined',
};
const bandKeys = ['pending_aging.band_under', 'pending_aging.band_one_two', 'pending_aging.band_two_three', 'pending_aging.band_over'] as const;
const bandColors = ['bg-chart-context', 'bg-signal-caution-fill', 'bg-signal-caution-fill', 'bg-signal-alarm'] as const;
const noteKeys: Record<string, TranslationKey> = {
  publisher_says_aging_not_provided: 'pending_aging.note_not_provided',
  cob_marked_inconsistent: 'pending_aging.note_inconsistent',
  missing_source_cells: 'pending_aging.note_missing',
  bands_differ_from_printed_total: 'pending_aging.note_bands_differ',
  payables_executive_total_differs: 'pending_aging.note_stock_differs',
  known_payables_executive_sum_differs: 'pending_aging.note_known_sum',
  reported_executive_population_only: 'pending_aging.note_scope',
  reported_assembly_population_only: 'pending_aging.note_assembly_scope',
  payables_assembly_total_differs: 'pending_aging.note_assembly_stock_differs',
  known_payables_assembly_sum_differs: 'pending_aging.note_assembly_known_sum',
};

type Observation = NonNullable<ReturnType<typeof readScopedAging>>;

function ReportedAging({ observation }: { observation: Observation }) {
  const { lang, t } = useLang();
  const chartId = useId();
  const readout = useChartReadout();
  const assembly = observation.scope === 'county_assembly';
  const { coverage } = observation;
  const fill = (key: TranslationKey, values: Record<string, string | number>) =>
    t(key).replace(/\{(\w+)\}/g, (whole, name: string) => String(values[name] ?? whole));
  const locale = lang === 'sw' ? 'sw-KE' : 'en-KE';
  const exact = new Intl.NumberFormat(locale, { maximumFractionDigits: 20 });
  const short = new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 1 });
  const compact = (value: number) => value < 1000 ? exact.format(value) : short.format(value);
  const money = (value: number | null | undefined) =>
    value == null ? t('pending_aging.not_reported') : `KES ${exact.format(value)}`;
  const bands = observation.buckets.map((band, index) => ({
    ...band, id: band.bucket, label: t(bandKeys[index]), value: money(band.amount),
  }));
  const chartBands = observation.chart_supported
    ? bands.filter((band): band is typeof band & { amount: number } => band.amount != null)
    : [];
  const maximum = Math.max(1, ...chartBands.map(band => band.amount));
  const oldest = chartBands.find(band => band.bucket === 'Over 3 years');
  const largest = oldest && chartBands.every(band => band === oldest || band.amount < oldest.amount);
  const current = chartBands.find(band => band.id === readout.activeId);
  const discrepancy = observation.reader_notes.some(note => note.code === 'bands_differ_from_printed_total');
  const someAges = bands.some(band => band.amount != null);
  const table = someAges && (
    <table className='w-full table-fixed break-words text-sm'>
      <caption className='pb-2 text-left font-semibold'>{t(assembly ? 'pending_aging.caption_assembly' : 'pending_aging.caption')}</caption>
      <thead>
        <tr className='border-b border-neutral-border'>
          <th scope='col' className='py-2 pr-2 text-left'>{t('pending_aging.band_heading')}</th>
          <th scope='col' className='py-2 text-right'>{t('pending_aging.amount_heading')}</th>
        </tr>
      </thead>
      <tbody>{bands.map(band => (
        <tr key={band.bucket} className='border-b border-neutral-border'>
          <th scope='row' className='py-2 pr-2 text-left font-normal'>{band.label}</th>
          <td className='py-2 text-right tabular-nums'>{band.value}</td>
        </tr>
      ))}</tbody>
      <tfoot>
        <tr className='border-b border-neutral-border'>
          <th scope='row' className='py-2 pr-2 text-left font-semibold'>{t('pending_aging.printed_total')}</th>
          <td className='py-2 text-right tabular-nums'>{money(observation.reported_total)}</td>
        </tr>
      </tfoot>
    </table>
  );

  return (
    <div className='min-w-0 space-y-3 text-sm'>
      {oldest ? (
        <>
          <p className='text-base font-semibold'>
            {fill(largest ? 'pending_aging.oldest_largest' : 'pending_aging.oldest', { amount: compact(oldest.amount) })}
          </p>
          <div role='group' aria-label={t(assembly ? 'pending_aging.chart_assembly' : 'pending_aging.chart')}>
            {chartBands.map((band, index) => (
              <Fragment key={band.id}>
                <button {...readout.trigger(band, t('pending_aging.not_reported'))}
                  aria-label={undefined} aria-describedby={`${chartId}-${index}-exact`}
                  className='grid min-h-11 w-full grid-cols-[minmax(5.75rem,0.33fr)_minmax(0,1fr)_3.5rem] items-center gap-2 rounded text-left text-sm hover:bg-surface-sunken focus-visible:outline focus-visible:outline-2 focus-visible:outline-gov-sage sm:grid-cols-[minmax(7rem,0.28fr)_minmax(0,1fr)_4rem]'>
                  <span className={band === oldest && band.amount > 0 ? 'font-semibold text-signal-alarm' : undefined}>{band.label}</span>
                  <span aria-hidden='true' className='block min-w-0'>
                    {band.amount > 0 && <span data-age-bar={band.bucket} data-signal={band === oldest ? 'alarm' : undefined}
                      className={`block h-4 rounded-sm outline outline-1 -outline-offset-1 outline-neutral-muted ${bandColors[index]} ${current?.id === band.id ? 'outline-2 outline-neutral-text' : ''}`}
                      style={{ width: `${band.amount / maximum * 100}%` }} />}
                  </span>
                  <span className='text-right font-semibold tabular-nums'>{compact(band.amount)}</span>
                </button>
                <span id={`${chartId}-${index}-exact`} hidden>{band.value}</span>
              </Fragment>
            ))}
          </div>
          <p aria-live='polite' className='min-h-5 text-sm text-neutral-muted'>
            {current && <>{current.label} · {current.value}</>}
          </p>
        </>
      ) : (
        <p role='status' className='text-neutral-muted'>
          {discrepancy ? t('pending_aging.chart_discrepancy') : t(someAges ? 'pending_aging.chart_unavailable' : 'pending_aging.absent')}
        </p>
      )}
      <div className='space-y-1 text-neutral-muted'>
        <p>{fill('pending_aging.as_at', { population: t(populations[observation.scope]), date: formatAsAt(observation.as_at, lang)! })}</p>
        <p>{fill(assembly ? 'pending_aging.coverage_assembly' : 'pending_aging.coverage', { reported: coverage.reported_counties, expected: coverage.expected_counties })}</p>
        {coverage.counties_with_all_bands !== undefined && (
          <p>{fill('pending_aging.band_coverage', { reported: coverage.counties_with_all_bands, expected: coverage.expected_counties })}</p>
        )}
        <p>{t('pending_aging.withheld')}</p>
      </div>
      {table && (oldest ? (
        <details>
          <summary className='flex min-h-11 w-fit min-w-11 cursor-pointer items-center rounded font-semibold underline underline-offset-4'>
            {t('foundation.chart_table')}
          </summary>
          {table}
        </details>
      ) : table)}
      <div className='flex flex-wrap gap-x-5 gap-y-1'>
        <a href={observation.source_url} target='_blank' rel='noopener noreferrer' className='audit-receipt text-gov-sage'>
          {fill('pending_aging.source', { publisher: observation.publisher, table: observation.table, page: observation.page })}
        </a>
        <InfoSheet title={t('pending_aging.source_notes')} trigger={props => (
          <button {...props} type='button' className='audit-receipt text-left'>{t('pending_aging.source_notes')}</button>
        )}>
          <p>{t(assembly ? 'pending_aging.scope_assembly' : 'pending_aging.scope')}</p>
          {coverage.missing_counties.length > 0 && <p>{fill('pending_aging.missing', { counties: coverage.missing_counties.join(', ') })}</p>}
          {!!coverage.missing_band_counties?.length && <p>{fill('pending_aging.missing_bands', { counties: coverage.missing_band_counties.join(', ') })}</p>}
          {coverage.qualified_counties.length > 0 && <p>{fill('pending_aging.qualified_counties', { counties: coverage.qualified_counties.join(', ') })}</p>}
          {observation.reader_notes.filter(note => note.comparison_amount && note.comparison_table).map((note, index) => (
            <p key={index}>{fill(assembly ? 'pending_aging.comparison_assembly' : 'pending_aging.comparison', {
              comparison_table: note.comparison_table!,
              comparison_amount: money(Number(note.comparison_amount)),
              table: observation.table,
              amount: money(observation.reported_total),
            })}</p>
          ))}
          {observation.reader_notes.length > 0 && (
            <p>{fill('pending_aging.qualifications', { notes: observation.reader_notes.map(note => t(noteKeys[note.code] || 'pending_aging.note_other')).join(' · ') })}</p>
          )}
          <p>{t('pending_aging.sums')}</p>
        </InfoSheet>
      </div>
    </div>
  );
}

export default function PendingBillsAgingPanel({ observations, isLoading = false, isError = false }: {
  observations?: PendingBillsAgingObservations; isLoading?: boolean; isError?: boolean;
}) {
  const { t } = useLang();
  const id = useId();
  const [scope, setScope] = useState<PendingBillsAgingScope>('county_executive');
  const observation = readScopedAging(observations?.[scope], scope);
  return (
    <section aria-labelledby={`${id}-title`} className='min-w-0 space-y-3 border-t border-neutral-border pt-4'>
      <h3 id={`${id}-title`} className='font-display text-xl font-semibold'>{t('pending_aging.title')}</h3>
      <div>
        <label htmlFor={`${id}-scope`} className='mb-1 block text-sm font-semibold'>{t('pending_aging.population')}</label>
        <select id={`${id}-scope`} value={scope} disabled={isLoading || isError} onChange={event => setScope(event.target.value as PendingBillsAgingScope)}
          className='min-h-11 max-w-full rounded border border-neutral-muted bg-surface-elevated px-3 text-base text-neutral-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-gov-sage'>
          {Object.entries(populations).map(([key, label]) => <option key={key} value={key}>{t(label)}</option>)}
        </select>
      </div>
      {isError ? <p role='alert' className='text-sm text-signal-alarm'>{t('pending_aging.load_error')}</p>
        : isLoading ? <p role='status' className='text-sm text-neutral-muted'>{t('pending_aging.loading')}</p>
          : observation ? <ReportedAging key={scope} observation={observation} />
            : <p role='status' className='text-sm text-neutral-muted'>{t('pending_aging.absent')}</p>}
    </section>
  );
}
