'use client';

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/axios';
import { useLang } from '@/lib/i18n/LangProvider';

interface SourceFreshness {
  source: string;
  label: string;
  last_updated: string | null;
  last_checked?: string | null;
  status: 'fresh' | 'stale' | 'outdated' | 'unknown';
}

interface FreshnessResponse {
  sources: SourceFreshness[];
}

const STATUS_RANK = { fresh: 0, stale: 1, outdated: 2 } as const;
type FreshnessStatus = keyof typeof STATUS_RANK;

function isFreshnessStatus(status: unknown): status is FreshnessStatus {
  return typeof status === 'string' && Object.prototype.hasOwnProperty.call(STATUS_RANK, status);
}

/** A status word cannot certify an absent, impossible or future publication. */
function isPublicationDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:Z|[+-]\d{2}:\d{2})?)?$/.test(value)) return false;
  const stamp = Date.parse(value);
  const calendar = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isFinite(stamp) && stamp <= Date.now() &&
    Number.isFinite(calendar.getTime()) && calendar.toISOString().slice(0, 10) === value.slice(0, 10);
}

export function useDataFreshness() {
  return useQuery<FreshnessResponse>({
    queryKey: ['data-freshness'],
    queryFn: async ({ signal }) => {
      const { data } = await apiClient.get<FreshnessResponse>('/data/freshness', { signal });
      return data;
    },
    staleTime: 30 * 60 * 1000, // 30 min
    meta: { silent: true }, // Suppress console noise for non-critical data
  });
}

export default function DataFreshnessBadge({ sources, className = '', variant = 'inline' }: {
  sources: string;
  className?: string;
  variant?: 'inline' | 'banner';
}) {
  const { data, isError } = useDataFreshness();
  const { t, lang } = useLang();
  const codes = Array.from(new Set(sources.split('/').map(code => code.trim()).filter(Boolean)));
  const entries = Array.isArray(data?.sources) ? data.sources : [];
  const matched = codes.map(code => {
    const matches = entries.filter(entry => entry?.source === code);
    return matches.length === 1 ? matches[0] : null;
  });
  const format = (date: string) => new Date(`${date.slice(0, 10)}T00:00:00Z`).toLocaleDateString(lang === 'sw' ? 'sw-KE' : 'en-GB', {
    timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric',
  });

  // A request failure or partial publisher coverage cannot certify the group.
  if (isError) return null;
  const measured = matched.filter((entry): entry is SourceFreshness & { last_updated: string; status: FreshnessStatus } =>
    Boolean(entry && isFreshnessStatus(entry.status) && isPublicationDate(entry.last_updated)));
  if (measured.length && measured.length === codes.length) {
    const worst = measured.reduce((a, b) => STATUS_RANK[a.status] >= STATUS_RANK[b.status] ? a : b);
    const oldest = measured.map(entry => entry.last_updated).sort()[0];
    const warning = worst.status !== 'fresh';
    return (
      <p className={`${warning ? 'text-signal-caution' : 'text-neutral-muted'} ${variant === 'banner' ? 'audit-panel p-3 text-sm' : 'text-xs'} ${className}`}>
        <strong>{t(`foundation.${worst.status}`)}</strong>{' · '}
        {t('foundation.published_date').replace('{date}', format(oldest))}{' · '}
        {measured.map(entry => entry.label || entry.source).join(' / ')}
      </p>
    );
  }

  const checked = matched.flatMap(entry => entry && isPublicationDate(entry.last_checked)
    ? [{ source: entry.source, name: entry.label || entry.source, date: entry.last_checked }]
    : []);
  return checked.length > 0 ? (
    <ul className={`space-y-1 text-xs text-neutral-muted ${className}`}>
      {checked.map(({ source, date, name }) => (
        <li key={source}>{t('foundation.checked_date').replace('{date}', format(date))} · {name}</li>
      ))}
    </ul>
  ) : null;
}
