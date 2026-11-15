'use client';

import type { ReactNode } from 'react';
import { useLang } from '@/lib/i18n/LangProvider';

export type Signal = 'alarm' | 'caution' | 'good' | 'context';

const TEXT: Record<Signal, string> = {
  alarm: 'text-signal-alarm',
  caution: 'text-signal-caution',
  good: 'text-signal-good',
  context: 'text-signal-context',
};

export function Stamp({ signal, children }: { signal: Signal; children: ReactNode }) {
  return <span className={`inline-block rounded border border-current px-1.5 py-0.5 text-audit-label font-semibold ${TEXT[signal]}`}>{children}</span>;
}

export default function StatCard({ label, value, comparison, source, missingReason, verdict, hero = false }: {
  label: string;
  value: string | number | null;
  comparison?: ReactNode;
  source: ReactNode;
  missingReason?: string;
  verdict?: { signal: Signal; word: string; rule: string; details: ReactNode };
  hero?: boolean;
}) {
  const { t } = useLang();
  const tone = verdict && value != null ? TEXT[verdict.signal] : TEXT.context;
  return (
    <div className='audit-panel space-y-2 p-4'>
      <h3 className='text-sm font-semibold text-neutral-text'>{label}</h3>
      {value == null
        ? <p className='text-base font-semibold text-neutral-text'>{missingReason ?? t('foundation.not_published')}</p>
        : <p className={`audit-figure break-words ${hero ? 'text-audit-hero' : 'text-audit-stat'} ${tone}`}>{value}</p>}
      {comparison && <p className='text-sm text-neutral-muted'>{comparison}</p>}
      {verdict && value != null && (
        <div className='space-y-1 text-sm'>
          <Stamp signal={verdict.signal}>{verdict.word}</Stamp>
          <p>{verdict.rule}</p>
          {verdict.details}
        </div>
      )}
      {source}
    </div>
  );
}

export function DataRow({ label, value, source }: { label: ReactNode; value: ReactNode; source?: ReactNode }) {
  return (
    <div className='border-b border-neutral-border py-2 text-sm last:border-b-0'>
      <div className='grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-2'>
        <dt className='min-w-0 break-words'>{label}</dt>
        <dd className='text-right font-semibold tabular-nums'>{value}</dd>
      </div>
      {source}
    </div>
  );
}
