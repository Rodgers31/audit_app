'use client';

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/axios';
import { Clock, RefreshCw } from 'lucide-react';

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

const STATUS_BANNER_BG: Record<string, string> = {
  fresh: 'bg-emerald-50 border-emerald-200',
  stale: 'bg-amber-50 border-amber-200',
  outdated: 'bg-red-50 border-red-200',
};

const STATUS_BANNER_TEXT: Record<string, string> = {
  fresh: 'text-emerald-800',
  stale: 'text-amber-800',
  outdated: 'text-red-800',
};

const STATUS_ICON_COLOR: Record<string, string> = {
  fresh: 'text-emerald-500',
  stale: 'text-amber-500',
  outdated: 'text-red-500',
};

export function useDataFreshness() {
  return useQuery<FreshnessResponse>({
    queryKey: ['data-freshness'],
    queryFn: async () => {
      const { data } = await apiClient.get<FreshnessResponse>('/data/freshness');
      return data;
    },
    staleTime: 30 * 60 * 1000, // 30 min
    retry: 1, // Don't hammer a failing endpoint
    meta: { silent: true }, // Suppress console noise for non-critical data
  });
}

/** Compute relative time string (e.g. "3 days ago", "2 hours ago") */
function relativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins} minute${diffMins === 1 ? '' : 's'} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
  if (diffDays < 30) return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
  const diffMonths = Math.floor(diffDays / 30);
  return `${diffMonths} month${diffMonths === 1 ? '' : 's'} ago`;
}

/**
 * Badge showing data source + freshness.
 * Pass one or more source codes (e.g. "COB", "OAG", "CBK/Treasury").
 *
 * Variants:
 * - "inline" (default) — compact text with status dot
 * - "banner" — prominent card with colored background, icon, and relative time
 */
export default function DataFreshnessBadge({
  sources,
  className = '',
  variant = 'inline',
}: {
  sources: string; // "COB" or "COB/Treasury"
  className?: string;
  variant?: 'inline' | 'banner';
}) {
  const { data } = useDataFreshness();

  const sourceCodes = sources.split('/').map((s) => s.trim());
  const matched = data?.sources.filter((s) => sourceCodes.includes(s.source)) ?? [];

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

  if (variant === 'banner') {
    return (
      <div
        className={`flex items-center gap-3 rounded-xl border p-3 ${STATUS_BANNER_BG[worstStatus] || STATUS_BANNER_BG.fresh} ${className}`}
        role="status"
        aria-label={`Data freshness: ${STATUS_LABEL[worstStatus]}. ${latestDate ? `Last updated ${relativeTime(latestDate)}` : 'Update time unknown'}. Source: ${sources}`}
      >
        <div className={`flex-shrink-0 ${STATUS_ICON_COLOR[worstStatus]}`}>
          {worstStatus === 'fresh' ? <RefreshCw size={18} /> : <Clock size={18} />}
        </div>
        <div className="flex-1 min-w-0">
          <div className={`text-sm font-medium ${STATUS_BANNER_TEXT[worstStatus]}`}>
            {STATUS_LABEL[worstStatus]}
            {latestDate && (
              <span className="font-normal opacity-80">
                {' — Updated '}
                {relativeTime(latestDate)}
              </span>
            )}
          </div>
          <div className="text-xs opacity-60 mt-0.5">
            Source: {label || sources}
            {latestDate && (
              <>
                {' · '}
                {new Date(latestDate).toLocaleDateString('en-GB', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                })}
              </>
            )}
          </div>
        </div>
        <span
          className={`inline-block w-2.5 h-2.5 rounded-full flex-shrink-0 ${STATUS_DOT[worstStatus]}`}
          aria-label={`Status: ${STATUS_LABEL[worstStatus]}`}
        />
      </div>
    );
  }

  // Default: inline variant
  if (matched.length === 0) {
    return (
      <div className={`flex items-center gap-2 text-xs text-gray-400 ${className}`}>
        <span
          className='inline-block w-2 h-2 rounded-full bg-gray-300'
          aria-label="Data freshness status: unknown"
        />
        Source: {sources}
      </div>
    );
  }

  return (
    <div
      className={`flex items-center gap-2 text-xs text-gray-500 ${className}`}
      title={`${label} — ${STATUS_LABEL[worstStatus]}. Updated: ${latestDate || 'unknown'}`}>
      <span
        className={`inline-block w-2 h-2 rounded-full ${STATUS_DOT[worstStatus]}`}
        aria-label={`Data freshness status: ${STATUS_LABEL[worstStatus]}`}
      />
      <span>
        Data as of: {latestDate ? new Date(latestDate).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}
        {' | '}Source: {sources}
      </span>
    </div>
  );
}
