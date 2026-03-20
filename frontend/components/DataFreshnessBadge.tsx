'use client';

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/axios';

interface SourceFreshness {
  source: string;
  label: string;
  last_updated: string | null;
  covers_through: string | null;
  update_frequency: string;
  status: 'fresh' | 'stale' | 'outdated';
}

interface FreshnessResponse {
  sources: SourceFreshness[];
}

const STATUS_DOT: Record<string, string> = {
  fresh: 'bg-emerald-400',
  stale: 'bg-amber-400',
  outdated: 'bg-red-400',
};

const STATUS_LABEL: Record<string, string> = {
  fresh: 'Up to date',
  stale: 'May be stale',
  outdated: 'Outdated',
};

export function useDataFreshness() {
  return useQuery<FreshnessResponse>({
    queryKey: ['data-freshness'],
    queryFn: async () => {
      const { data } = await apiClient.get<FreshnessResponse>('/data/freshness');
      return data;
    },
    staleTime: 30 * 60 * 1000, // 30 min
  });
}

/**
 * Small badge showing data source + freshness.
 * Pass one or more source codes (e.g. "COB", "OAG", "CBK/Treasury").
 */
export default function DataFreshnessBadge({
  sources,
  className = '',
}: {
  sources: string; // "COB" or "COB/Treasury"
  className?: string;
}) {
  const { data } = useDataFreshness();

  const sourceCodes = sources.split('/').map((s) => s.trim());
  const matched = data?.sources.filter((s) => sourceCodes.includes(s.source)) ?? [];

  if (matched.length === 0) {
    return (
      <div className={`flex items-center gap-2 text-xs text-gray-400 ${className}`}>
        <span className='inline-block w-2 h-2 rounded-full bg-gray-300' />
        Source: {sources}
      </div>
    );
  }

  // Use the worst status among matched sources
  const worstStatus = matched.reduce<'fresh' | 'stale' | 'outdated'>((worst, s) => {
    const rank = { fresh: 0, stale: 1, outdated: 2 } as const;
    return rank[s.status] > rank[worst] ? s.status : worst;
  }, 'fresh');

  // Most recent last_updated among matched
  const dates = matched
    .map((s) => s.last_updated)
    .filter(Boolean)
    .sort()
    .reverse();
  const latestDate = dates[0];

  const label = matched.map((s) => s.label).join(' / ');

  return (
    <div
      className={`flex items-center gap-2 text-xs text-gray-500 ${className}`}
      title={`${label} — ${STATUS_LABEL[worstStatus]}. Updated: ${latestDate || 'unknown'}`}>
      <span className={`inline-block w-2 h-2 rounded-full ${STATUS_DOT[worstStatus]}`} />
      <span>
        Data as of: {latestDate ? new Date(latestDate).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}
        {' | '}Source: {sources}
      </span>
    </div>
  );
}
