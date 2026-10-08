'use client';

import Link from 'next/link';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { evidenceUrl, qualificationMessageKey, type Qualifications, type QualificationRows, type QualificationTable } from '@/lib/evidence/qualification';

export type EvidenceLabelKey = Extract<TranslationKey, `evidence.label.${string}`>;

export interface FigureEvidenceProps {
  /** Stable selector/source label. Application copy opts into explicit display keys. */
  label: string;
  labelKey?: EvidenceLabelKey;
  labelValues?: Readonly<Record<string, string>>;
  qualifications?: Qualifications | null;
  rows?: QualificationRows | null;
  table?: QualificationTable;
  recordId?: number | string;
  note?: { status: string; reason: string } | null;
}

/** A disclosure describes individual observations; it never verifies their sum. */
export default function FigureEvidence({ label, labelKey, labelValues, qualifications, rows, table, recordId, note }: FigureEvidenceProps) {
  const { t } = useLang();
  const displayLabel = labelKey ? t(labelKey).replace(/\{(\w+)\}/g, (token, key: string) => labelValues?.[key] ?? token) : label;
  const words = (value: unknown) => typeof value === 'string' ? value.replace(/_/g, ' ') : t('evidence.unavailable');
  const statusLabel = (q: Parameters<typeof qualificationMessageKey>[0]) => t(qualificationMessageKey(q));
  const observations = rows
    ? Object.entries(rows).flatMap(([id, measures]) => Object.entries(measures ?? {}).map(([measure, q]) => ({ id, measure, q })))
    : Object.entries(qualifications ?? {}).map(([measure, q]) => ({ id: recordId, measure, q }));
  const recordIds = Array.from(new Set(observations.map(({ id }) => id).filter(id => id != null && /^[1-9]\d*$/.test(String(id)))));
  const labels = Array.from(new Set(observations.map(({ q }) => statusLabel(q))));
  return (
    <details className='mt-2 min-w-0 max-w-full text-xs text-gray-700 dark:text-neutral-text' data-figure-evidence={label}>
      <summary className='min-h-11 cursor-pointer rounded px-1 py-2 leading-relaxed break-words focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gov-forest'>
        {t('evidence.for').replace('{label}', () => displayLabel)} · {labels.length ? labels.join(' / ') : note?.status === 'qualified' && typeof note.reason === 'string' && note.reason.trim() ? t('evidence.status.qualified') : t('evidence.status.unavailable')}
      </summary>
      <div className='space-y-3 border-l-2 border-neutral-border pl-3 pb-2'>
        {!observations.length && <p>{note?.reason ? words(note.reason) : t('evidence.no_qualification')}{' '}{t('evidence.listing_limit')}</p>}
        {observations.map(({ id, measure, q }, index) => {
          const source = evidenceUrl(q?.source_url);
          return (
            <div key={`${id ?? ''}-${measure}-${index}`} className='min-w-0 space-y-1 break-words'>
              <p className='font-semibold'>{words(measure)} · {statusLabel(q)}</p>
              <p>{q?.identity ? [q.identity.geography, q.identity.period, q.identity.unit, q.identity.basis].map(words).join(' · ') : t('evidence.identity_unavailable')}</p>
              {q?.identity?.dimensions && Object.keys(q.identity.dimensions).length > 0 && <p>{Object.entries(q.identity.dimensions).filter(([, value]) => value != null).map(([key, value]) => `${words(key)}: ${value}`).join(' · ')}</p>}
              <p>{q?.reason ? words(q.reason) : t('evidence.reason_unavailable')}</p>
              <p>{q?.publisher ?? t('evidence.publisher_unavailable')} · {t('evidence.source_kind').replace('{kind}', () => q?.source_kind && q.source_kind !== 'unknown' ? q.source_kind : t('evidence.unknown_kind'))}</p>
              {source && <a href={source} target='_blank' rel='noopener noreferrer' className='inline-block min-h-11 py-2 underline underline-offset-2'>{t('evidence.open_source')}</a>}
              <p>{t('evidence.bytes')}: {q?.document_bytes_checked === true ? t('evidence.checked') : t('evidence.not_checked')} · {t('evidence.value')}: {q?.value_checked === true ? t('evidence.matched') : t('evidence.not_checked')}</p>
              {q?.locator && <p>{t('evidence.locator')}: {Object.entries(q.locator).map(([key, value]) => `${words(key)} ${typeof value === 'object' ? JSON.stringify(value) : String(value)}`).join(' · ')}</p>}
              {q?.digest && <p className='break-all'>{t('evidence.digest')}: {q.digest}</p>}
            </div>
          );
        })}
        {table && recordIds.map(id => <Link key={id} href={`/sources/figures/${table}/${id}`} className='block min-h-11 py-2 underline underline-offset-2'>{t('evidence.details')}{recordIds.length > 1 ? ` · ${id}` : ''}</Link>)}
      </div>
    </details>
  );
}
