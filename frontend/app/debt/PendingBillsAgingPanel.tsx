'use client';

import { useState } from 'react';
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
const bandKeys: TranslationKey[] = ['pending_aging.band_under', 'pending_aging.band_one_two', 'pending_aging.band_two_three', 'pending_aging.band_over'];
const noteKeys: Record<string, TranslationKey> = {
  publisher_says_aging_not_provided: 'pending_aging.note_not_provided',
  cob_marked_inconsistent: 'pending_aging.note_inconsistent',
  missing_source_cells: 'pending_aging.note_missing',
  bands_differ_from_printed_total: 'pending_aging.note_bands_differ',
  payables_executive_total_differs: 'pending_aging.note_stock_differs',
  known_payables_executive_sum_differs: 'pending_aging.note_known_sum',
  reported_executive_population_only: 'pending_aging.note_scope',
};

export default function PendingBillsAgingPanel({ observations, isLoading = false, isError = false }: {
  observations?: PendingBillsAgingObservations; isLoading?: boolean; isError?: boolean;
}) {
  const { lang, t } = useLang();
  const fill = (key: TranslationKey, values: Record<string, string | number>) =>
    t(key).replace(/\{(\w+)\}/g, (whole, name: string) => String(values[name] ?? whole));
  const [scope, setScope] = useState<PendingBillsAgingScope>('county_executive');
  const observation = readScopedAging(observations?.[scope], scope);
  const chartMaximum = observation?.chart_supported
    ? Math.max(...observation.buckets.map((band) => band.amount!), 1)
    : 1;
  const money = (value: number) => `KES ${value.toLocaleString(lang === 'sw' ? 'sw-KE' : 'en-KE', { maximumFractionDigits: 0 })}`;
  return (
    <section aria-labelledby='pending-aging-title' className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-5 sm:p-6'>
      <h3 id='pending-aging-title' className='text-sm font-semibold text-gov-dark dark:text-white'>
        {t('pending_aging.title')}
      </h3>
      <label htmlFor='aging-population' className='block text-sm mt-3 mb-1'>{t('pending_aging.population')}</label>
      <select id='aging-population' value={scope} disabled={isLoading || isError} onChange={(event) => setScope(event.target.value as PendingBillsAgingScope)}
        className='min-h-11 rounded-lg border border-neutral-border bg-white dark:bg-surface-base px-3 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-gov-sage'>
        {Object.entries(populations).map(([key, label]) => <option key={key} value={key}>{t(label)}</option>)}
      </select>
      <div aria-live='polite' className='mt-3 text-sm'>
        {isError ? (
          <p role='alert'>{t('pending_aging.load_error')}</p>
        ) : isLoading ? (
          <p role='status'>{t('pending_aging.loading')}</p>
        ) : !observation ? (
          <p>{fill('pending_aging.absent', { population: t(populations[scope]).toLocaleLowerCase() })}</p>
        ) : (
          <>
            <p className='font-medium'>{fill('pending_aging.as_at', { population: t(populations[scope]), date: formatAsAt(observation.as_at, lang)! })}</p>
            <p className='mt-2 text-neutral-muted'>{t('pending_aging.scope')}</p>
            <p className='mt-2'>{fill('pending_aging.coverage', { reported: observation.coverage.reported_counties, expected: observation.coverage.expected_counties })}
              {observation.coverage.missing_counties.length > 0 ? ` ${fill('pending_aging.missing', { counties: observation.coverage.missing_counties.join(', ') })}` : ''}
              {' '}{t('pending_aging.withheld')}</p>
            <table className='mt-4 w-full text-sm'>
              <caption className='text-left font-medium mb-2'>{t('pending_aging.caption')}</caption>
              <thead><tr><th scope='col' className='text-left'>{t('pending_aging.band_heading')}</th><th scope='col' className='text-right'>{t('pending_aging.amount_heading')}</th></tr></thead>
              <tbody>{observation.buckets.map((band, index) => <tr key={band.bucket}>
                <th scope='row' className='py-2 text-left font-normal'>{t(bandKeys[index])}</th>
                <td className='text-right'>{band.amount == null ? t('pending_aging.not_reported') : money(band.amount)}</td>
              </tr>)}</tbody>
            </table>
            {observation.chart_supported && (
              <div aria-label={t('pending_aging.chart')} role='img' className='mt-4 space-y-2'>
                {observation.buckets.map((band, index) => <div key={band.bucket} className='flex items-center gap-2' aria-hidden='true'>
                  <span className='w-28 shrink-0 text-xs'>{t(bandKeys[index])}</span>
                  <div className='flex-1 min-w-0'>
                    <div className='h-3 bg-gov-forest rounded-sm' style={{ width: `${band.amount! / chartMaximum * 100}%` }} />
                  </div>
                </div>)}
              </div>
            )}
            <p className='mt-3 text-neutral-muted'>{fill('pending_aging.reported_total', { amount: observation.reported_total == null ? t('pending_aging.not_reported') : money(observation.reported_total) })}</p>
            {observation.reader_notes.filter((note) => note.comparison_amount).map((note, i) => (
              <p key={i} className='mt-2 text-neutral-muted'>
                {fill('pending_aging.comparison', { comparison_table: note.comparison_table!, comparison_amount: money(Number(note.comparison_amount)), table: observation.table, amount: money(observation.reported_total!) })}
              </p>
            ))}
            {observation.reader_notes.length > 0 && <p className='mt-2 text-neutral-muted'>{fill('pending_aging.qualifications', { notes: observation.reader_notes.map((note) => t(noteKeys[note.code] || 'pending_aging.note_other')).join('; ') })}</p>}
            {observation.coverage.qualified_counties.length > 0 && <p className='mt-2 text-neutral-muted'>{fill('pending_aging.qualified_counties', { counties: observation.coverage.qualified_counties.join(', ') })}</p>}
            <p className='mt-2 text-neutral-muted'>{t('pending_aging.sums')}</p>
            <a href={observation.source_url} target='_blank' rel='noopener noreferrer' className='mt-3 inline-block underline text-gov-forest dark:text-gov-gold'>
              {fill('pending_aging.source', { publisher: observation.publisher, table: observation.table, page: observation.page })}
            </a>
          </>
        )}
      </div>
    </section>
  );
}
