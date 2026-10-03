import Link from 'next/link';
import { evidenceUrl, qualificationLabel, type Qualifications, type QualificationRows, type QualificationTable } from '@/lib/evidence/qualification';

export interface FigureEvidenceProps {
  label: string;
  qualifications?: Qualifications | null;
  rows?: QualificationRows | null;
  table?: QualificationTable;
  recordId?: number | string;
  note?: { status: string; reason: string } | null;
}

const words = (value: unknown) => typeof value === 'string' ? value.replace(/_/g, ' ') : 'Unavailable';

/** A disclosure describes individual observations; it never verifies their sum. */
export default function FigureEvidence({ label, qualifications, rows, table, recordId, note }: FigureEvidenceProps) {
  const observations = rows
    ? Object.entries(rows).flatMap(([id, measures]) => Object.entries(measures ?? {}).map(([measure, q]) => ({ id, measure, q })))
    : Object.entries(qualifications ?? {}).map(([measure, q]) => ({ id: recordId, measure, q }));
  const recordIds = Array.from(new Set(observations.map(({ id }) => id).filter(id => id != null && /^[1-9]\d*$/.test(String(id)))));
  const labels = Array.from(new Set(observations.map(({ q }) => qualificationLabel(q))));
  return (
    <details className='mt-2 min-w-0 max-w-full text-xs text-gray-700 dark:text-neutral-text' data-figure-evidence={label}>
      <summary className='min-h-11 cursor-pointer rounded px-1 py-2 leading-relaxed break-words focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gov-forest'>
        Evidence for {label} · {labels.length ? labels.join(' / ') : note?.status === 'qualified' && typeof note.reason === 'string' && note.reason.trim() ? 'Qualified citation' : 'Evidence unavailable'}
      </summary>
      <div className='space-y-3 border-l-2 border-neutral-border pl-3 pb-2'>
        {!observations.length && <p>{note?.reason ? words(note.reason) : 'No measure qualification supplied.'} A source listing alone does not verify a figure.</p>}
        {observations.map(({ id, measure, q }, index) => {
          const source = evidenceUrl(q?.source_url);
          return (
            <div key={`${id ?? ''}-${measure}-${index}`} className='min-w-0 space-y-1 break-words'>
              <p className='font-semibold'>{words(measure)} · {qualificationLabel(q)}</p>
              <p>{q?.identity ? [q.identity.geography, q.identity.period, q.identity.unit, q.identity.basis].map(words).join(' · ') : 'Observation identity unavailable'}</p>
              {q?.identity?.dimensions && Object.keys(q.identity.dimensions).length > 0 && <p>{Object.entries(q.identity.dimensions).filter(([, value]) => value != null).map(([key, value]) => `${words(key)}: ${value}`).join(' · ')}</p>}
              <p>{q?.reason ? words(q.reason) : 'Qualification reason unavailable'}</p>
              <p>{q?.publisher ?? 'Publisher unavailable'} · {q?.source_kind ?? 'unknown'} source</p>
              {source && <a href={source} target='_blank' rel='noopener noreferrer' className='inline-block min-h-11 py-2 underline underline-offset-2'>Open source document</a>}
              <p>Source bytes: {q?.document_bytes_checked === true ? 'checked' : 'not checked'} · Value: {q?.value_checked === true ? 'matched' : 'not checked'}</p>
              {q?.locator && <p>Locator: {Object.entries(q.locator).map(([key, value]) => `${words(key)} ${typeof value === 'object' ? JSON.stringify(value) : String(value)}`).join(' · ')}</p>}
              {q?.digest && <p className='break-all'>Retained version SHA256: {q.digest}</p>}
            </div>
          );
        })}
        {table && recordIds.map(id => <Link key={id} href={`/sources/figures/${table}/${id}`} className='block min-h-11 py-2 underline underline-offset-2'>Observation evidence details{recordIds.length > 1 ? ` · ${id}` : ''}</Link>)}
      </div>
    </details>
  );
}
