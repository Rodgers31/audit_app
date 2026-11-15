'use client';

import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import InfoSheet from '@/components/ui/InfoSheet';
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
  /** Plain-language reading of this figure supplied by its caller. */
  explanation?: string;
  publisher?: string;
}

/** A disclosure describes individual observations; it never verifies their sum. */
export default function FigureEvidence({ label, labelKey, labelValues, qualifications, rows, table, recordId, note, explanation, publisher }: FigureEvidenceProps) {
  const { t } = useLang();
  const displayLabel = labelKey ? t(labelKey).replace(/\{(\w+)\}/g, (token, key: string) => labelValues?.[key] ?? token) : label;
  const words = (value: unknown) => typeof value === 'string' ? value.replace(/_/g, ' ') : t('evidence.unavailable');
  const statusLabel = (q: Parameters<typeof qualificationMessageKey>[0]) => t(qualificationMessageKey(q));
  const observations = rows
    ? Object.entries(rows).flatMap(([id, measures]) => Object.entries(measures ?? {}).map(([measure, q]) => ({ id, measure, q })))
    : Object.entries(qualifications ?? {}).map(([measure, q]) => ({ id: recordId, measure, q }));
  const recordIds = Array.from(new Set(observations.map(({ id }) => id).filter(id => id != null && /^[1-9]\d*$/.test(String(id)))));
  const statusKeys: Partial<Record<TranslationKey, TranslationKey>> = {
    'evidence.status.verified': 'foundation.verified',
    'evidence.status.qualified': 'foundation.qualified',
    'evidence.status.conflicting': 'foundation.conflicting',
    'evidence.status.unavailable': 'foundation.unavailable',
  };
  const statuses = new Set<TranslationKey>(observations.map(({ q }) => qualificationMessageKey(q)));
  if (!statuses.size) statuses.add(note?.status === 'qualified' && typeof note.reason === 'string' && note.reason.trim()
    ? 'evidence.status.qualified' : 'evidence.status.unavailable');
  const observedPublishers = new Set(observations.flatMap(({ q }) => typeof q?.publisher === 'string' && q.publisher.trim() ? [q.publisher.trim()] : []));
  const singlePublisher = publisher ?? (observedPublishers.size === 1 ? Array.from(observedPublishers)[0] : null);
  const chipLabel = singlePublisher ? t('foundation.source').replace('{publisher}', () => singlePublisher) : t('foundation.sources');
  const dot =
    statuses.has('evidence.status.conflicting') ? 'bg-signal-caution' :
    statuses.size === 1 && statuses.has('evidence.status.verified') ? 'bg-signal-good' :
    statuses.has('evidence.status.qualified') ? 'bg-signal-caution' : 'bg-neutral-muted';

  return (
    <div className='min-w-0' data-figure-evidence={label}>
      <InfoSheet title={t('foundation.evidence_title')} trigger={props => (
        <button {...props} type='button' className='audit-receipt text-left'
          aria-label={`${chipLabel} · ${t('evidence.for').replace('{label}', () => displayLabel)}`}>
          <span aria-hidden='true' className={`h-2 w-2 shrink-0 ${dot}`} />
          <span className='min-w-0 break-words'>{chipLabel}</span>
          <ArrowUpRight size={15} aria-hidden='true' className='shrink-0' />
        </button>
      )}>
        {explanation && <p>{explanation}</p>}
        <ul className='space-y-1 border-y border-neutral-border py-2'>
          {Array.from(statuses, key => <li key={key}>{t(statusKeys[key] ?? key)}</li>)}
        </ul>
        {table && recordIds.map(id => <Link key={id} href={`/sources/figures/${table}/${id}`} className='block min-h-11 py-2 underline underline-offset-2'>{t('evidence.details')}{recordIds.length > 1 ? ` · ${id}` : ''}</Link>)}
        <details className='border-b border-neutral-border pb-2'>
          <summary className='min-h-11 cursor-pointer py-2 font-semibold'>{t('foundation.technical_details')}</summary>
          <div className='space-y-3'>
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
          </div>
        </details>
      </InfoSheet>
    </div>
  );
}
