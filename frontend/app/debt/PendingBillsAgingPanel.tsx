'use client';

import { useState } from 'react';
import type { PendingBillsAgingObservations, PendingBillsAgingScope } from '@/lib/api/debt';
import { readScopedAging } from '@/lib/debt/scopedPendingBillsAging';
import { formatAsAt } from '@/lib/counties/pendingBillsNotes';

const populations: Record<PendingBillsAgingScope, string> = {
  county_executive: 'County executives',
  county_assembly: 'County assemblies',
  national: 'National government',
  combined: 'Combined governments',
};

export default function PendingBillsAgingPanel({ observations }: { observations?: PendingBillsAgingObservations }) {
  const [scope, setScope] = useState<PendingBillsAgingScope>('county_executive');
  const observation = readScopedAging(observations?.[scope], scope);
  const chartMaximum = observation?.chart_supported
    ? Math.max(...observation.buckets.map((band) => band.amount!), 1)
    : 1;
  const money = (value: number) => `KES ${value.toLocaleString('en-KE', { maximumFractionDigits: 0 })}`;
  return (
    <section aria-labelledby='pending-aging-title' className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-5 sm:p-6'>
      <h3 id='pending-aging-title' className='text-sm font-semibold text-gov-dark dark:text-white'>
        Aging — how long bills have gone unpaid
      </h3>
      <label htmlFor='aging-population' className='block text-sm mt-3 mb-1'>Aging population</label>
      <select id='aging-population' value={scope} onChange={(event) => setScope(event.target.value as PendingBillsAgingScope)}
        className='min-h-11 rounded-lg border border-neutral-border bg-white dark:bg-surface-base px-3 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-gov-sage'>
        {Object.entries(populations).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select>
      <div aria-live='polite' className='mt-3 text-sm'>
        {!observation ? (
          <p>No source-bound aging observation is available in this app for {populations[scope].toLowerCase()}. No age breakdown is shown.</p>
        ) : (
          <>
            <p className='font-medium'>{populations[scope]} — reported aging as at {formatAsAt(observation.as_at, 'en')}</p>
            <p className='mt-2 text-neutral-muted'>These source year bands cover county executives only. They do not describe assembly or national bills, and are not a combined total.</p>
            <p className='mt-2'>{observation.coverage.reported_counties} of {observation.coverage.expected_counties} counties have an available executive aging total.
              {observation.coverage.missing_counties.length > 0 ? ` Missing: ${observation.coverage.missing_counties.join(', ')}.` : ''}
              {' '}The complete total is withheld; missing cells and source qualifications remain unresolved.</p>
            <table className='mt-4 w-full text-sm'>
              <caption className='text-left font-medium mb-2'>Reported executive aging (KES)</caption>
              <thead><tr><th scope='col' className='text-left'>Source age band</th><th scope='col' className='text-right'>Reported amount</th></tr></thead>
              <tbody>{observation.buckets.map((band) => <tr key={band.bucket}>
                <th scope='row' className='py-2 text-left font-normal'>{band.bucket}</th>
                <td className='text-right'>{band.amount == null ? 'Not reported' : money(band.amount)}</td>
              </tr>)}</tbody>
            </table>
            {observation.chart_supported && (
              <div aria-label='Reported county executive aging chart' role='img' className='mt-4 space-y-2'>
                {observation.buckets.map((band) => <div key={band.bucket} className='flex items-center gap-2' aria-hidden='true'>
                  <span className='w-28 shrink-0 text-xs'>{band.bucket}</span>
                  <div className='flex-1 min-w-0'>
                    <div className='h-3 bg-gov-forest rounded-sm' style={{ width: `${band.amount! / chartMaximum * 100}%` }} />
                  </div>
                </div>)}
              </div>
            )}
            <p className='mt-3 text-neutral-muted'>Reported source total: {observation.reported_total == null ? 'Not reported' : money(observation.reported_total)}.</p>
            {observation.reader_notes.filter((note) => note.comparison_amount).map((note, i) => (
              <p key={i} className='mt-2 text-neutral-muted'>
                {note.comparison_table} reports an executive amount of {money(Number(note.comparison_amount))};
                {' '}{observation.table} reports {money(observation.reported_total!)}. These source figures remain unreconciled.
              </p>
            ))}
            {observation.reader_notes.length > 0 && <p className='mt-2 text-neutral-muted'>Source qualifications: {observation.reader_notes.map((note) => note.code.replaceAll('_', ' ')).join('; ')}.</p>}
            {observation.coverage.qualified_counties.length > 0 && <p className='mt-2 text-neutral-muted'>Counties with source qualifications or missing bands: {observation.coverage.qualified_counties.join(', ')}.</p>}
            <p className='mt-2 text-neutral-muted'>Column sums retain missing cells; the source’s printed totals are not silently reconciled.</p>
            <a href={observation.source_url} target='_blank' rel='noopener noreferrer' className='mt-3 inline-block underline text-gov-forest dark:text-gov-gold'>
              {observation.publisher}, {observation.table}, PDF p.{observation.page}
            </a>
          </>
        )}
      </div>
    </section>
  );
}
