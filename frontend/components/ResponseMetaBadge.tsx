'use client';

/**
 * ResponseMetaBadge
 * -----------------
 * Renders a compact freshness/trust indicator driven by the `_meta`
 * envelope now attached to every major finance endpoint (see
 * `backend/main.py::_response_meta`).
 *
 * This is complementary to `DataFreshnessBadge` — that component keys
 * off the global `/data/freshness` pipeline (when the ETL last ran),
 * while this one reads the per-endpoint response metadata:
 *
 *   {
 *     generated_at:       "2026-04-18T14:32:11Z",   // always present
 *     source_updated_at:  "2026-04-10T03:15:00Z",   // optional
 *     covers_through:     "FY2024/25",              // optional
 *     cache_ttl_seconds:  1800,                     // optional
 *     data_quality:       "official"|"estimated"|"projected"|"mixed"|"unknown",
 *     quality_notes:      ["..."],
 *     scope_detail:       "..."                     // existing field
 *   }
 *
 * Place once per page, typically in the page header near the title.
 * Non-alarmist: shows neutral grey for "official", amber for anything
 * else. Never red — broken data paths already throw HTTP errors.
 */

import { useState } from 'react';
import { Clock, Info } from 'lucide-react';

export interface ResponseMeta {
  unit?: string;
  entity_scope?: string;
  fiscal_period?: string | null;
  scope_detail?: string;
  generated_at?: string;
  source_updated_at?: string;
  covers_through?: string | null;
  cache_ttl_seconds?: number;
  data_quality?: 'official' | 'estimated' | 'projected' | 'historical' | 'mixed' | 'unknown' | string;
  quality_notes?: string[];
}

function relativeTime(iso: string | undefined): string | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return null;
  const diffMs = Date.now() - then;
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

const QUALITY_LABEL: Record<string, string> = {
  official: 'Official source',
  estimated: 'Modeled estimate',
  projected: 'Forward projection',
  historical: 'Historical record',
  mixed: 'Mixed sources',
  unknown: 'Provenance unknown',
};

const QUALITY_TONE: Record<string, { dot: string; text: string; bg: string }> = {
  official: {
    dot: 'bg-emerald-400',
    text: 'text-gray-700 dark:text-neutral-muted',
    bg: 'bg-gray-50 dark:bg-surface-elevated border-gray-200 dark:border-neutral-border',
  },
  estimated: {
    dot: 'bg-amber-400',
    text: 'text-amber-900',
    bg: 'bg-amber-50 border-amber-200',
  },
  projected: {
    dot: 'bg-amber-400',
    text: 'text-amber-900',
    bg: 'bg-amber-50 border-amber-200',
  },
  historical: {
    dot: 'bg-slate-400',
    text: 'text-gray-700 dark:text-neutral-muted',
    bg: 'bg-gray-50 dark:bg-surface-elevated border-gray-200 dark:border-neutral-border',
  },
  mixed: {
    dot: 'bg-amber-400',
    text: 'text-amber-900',
    bg: 'bg-amber-50 border-amber-200',
  },
  unknown: {
    dot: 'bg-gray-300',
    text: 'text-gray-600 dark:text-neutral-muted',
    bg: 'bg-gray-50 dark:bg-surface-elevated border-gray-200 dark:border-neutral-border',
  },
};

export default function ResponseMetaBadge({
  meta,
  className = '',
}: {
  meta: ResponseMeta | undefined | null;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  if (!meta) return null;

  const quality = (meta.data_quality || 'unknown').toLowerCase();
  const tone = QUALITY_TONE[quality] || QUALITY_TONE.unknown;
  const label = QUALITY_LABEL[quality] || meta.data_quality || '';

  const ago = relativeTime(meta.source_updated_at || meta.generated_at);
  const coverage = meta.covers_through || meta.fiscal_period;
  const hasNotes = Array.isArray(meta.quality_notes) && meta.quality_notes.length > 0;
  const hasScope = Boolean(meta.scope_detail);

  return (
    <div className={`inline-flex flex-col gap-1 ${className}`}>
      <button
        type='button'
        onClick={() => setOpen((v) => !v)}
        disabled={!hasNotes && !hasScope}
        className={`inline-flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs ${tone.bg} ${tone.text} ${
          hasNotes || hasScope ? 'cursor-pointer hover:brightness-95' : 'cursor-default'
        }`}
        aria-expanded={open}
        aria-label={`Data quality: ${label}${ago ? `, updated ${ago}` : ''}${
          coverage ? `, covering ${coverage}` : ''
        }`}
      >
        <span
          className={`inline-block w-2 h-2 rounded-full ${tone.dot}`}
          aria-hidden='true'
        />
        <span className='font-medium'>{label}</span>
        {coverage && (
          <>
            <span className='opacity-40'>·</span>
            <span>{coverage}</span>
          </>
        )}
        {ago && (
          <>
            <span className='opacity-40'>·</span>
            <Clock size={11} className='opacity-60' aria-hidden='true' />
            <span>{ago}</span>
          </>
        )}
        {(hasNotes || hasScope) && (
          <Info size={11} className='opacity-60' aria-hidden='true' />
        )}
      </button>

      {open && (hasNotes || hasScope) && (
        <div
          className={`max-w-md rounded-md border p-3 text-xs leading-relaxed ${tone.bg} ${tone.text}`}
          role='region'
          aria-label='Data quality details'
        >
          {hasScope && (
            <p className='mb-2 font-medium'>{meta.scope_detail}</p>
          )}
          {hasNotes && (
            <ul className='list-disc pl-4 space-y-1'>
              {meta.quality_notes!.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          )}
          {typeof meta.cache_ttl_seconds === 'number' && (
            <p className='mt-2 text-[11px] opacity-60'>
              Cached up to {Math.round(meta.cache_ttl_seconds / 60)} min.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
