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

type FreshnessStatus = SourceFreshness['status'];

/**
 * What the badge can say. 'checking' and 'unknown' are not freshness verdicts:
 * they are what renders when nothing was measured (request in flight or the
 * server prerender; request failed or no entry for these sources). They must
 * never fall through to 'fresh'.
 */
type BadgeState = FreshnessStatus | 'checking' | 'unknown';

const STATUS_RANK: Record<FreshnessStatus, number> = { fresh: 0, stale: 1, outdated: 2 };

function isFreshnessStatus(status: unknown): status is FreshnessStatus {
  return typeof status === 'string' && Object.prototype.hasOwnProperty.call(STATUS_RANK, status);
}

const STATUS_DOT: Record<BadgeState, string> = {
  fresh: 'bg-emerald-400',
  stale: 'bg-amber-400',
  outdated: 'bg-red-400',
  checking: 'bg-gray-300',
  unknown: 'bg-gray-300',
};

const STATUS_LABEL: Record<BadgeState, string> = {
  fresh: 'Up to date',
  stale: 'May be stale',
  outdated: 'Outdated',
  checking: 'Checking data freshness…',
  unknown: 'Freshness unknown',
};

const NEUTRAL_BANNER_BG = 'bg-gray-50 border-gray-200 dark:bg-surface-elevated dark:border-neutral-border';
const NEUTRAL_BANNER_TEXT = 'text-gray-700 dark:text-neutral-muted';
const NEUTRAL_ICON_COLOR = 'text-gray-400 dark:text-neutral-muted';

const STATUS_BANNER_BG: Record<BadgeState, string> = {
  fresh: 'bg-emerald-50 border-emerald-200 dark:bg-emerald-900/30 dark:border-emerald-700/40',
  stale: 'bg-amber-50 border-amber-200 dark:bg-amber-900/30 dark:border-amber-700/40',
  outdated: 'bg-red-50 border-red-200 dark:bg-red-900/30 dark:border-red-700/40',
  checking: NEUTRAL_BANNER_BG,
  unknown: NEUTRAL_BANNER_BG,
};

const STATUS_BANNER_TEXT: Record<BadgeState, string> = {
  fresh: 'text-emerald-800 dark:text-emerald-100',
  stale: 'text-amber-800 dark:text-amber-100',
  outdated: 'text-red-800 dark:text-red-100',
  checking: NEUTRAL_BANNER_TEXT,
  unknown: NEUTRAL_BANNER_TEXT,
};

const STATUS_ICON_COLOR: Record<BadgeState, string> = {
  fresh: 'text-emerald-500 dark:text-emerald-300',
  stale: 'text-amber-500 dark:text-amber-300',
  outdated: 'text-red-500 dark:text-red-300',
  checking: NEUTRAL_ICON_COLOR,
  unknown: NEUTRAL_ICON_COLOR,
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
  const { data, isPending } = useDataFreshness();

  const sourceCodes = sources.split('/').map((s) => s.trim());
  const matched = data?.sources.filter((s) => sourceCodes.includes(s.source)) ?? [];

  // Worst status among matched sources. No match, or any status we do not
  // recognise, is not a measurement — it must not default to 'fresh'.
  const measured = matched.length > 0 && matched.every((s) => isFreshnessStatus(s.status));
  const state: BadgeState = measured
    ? matched.reduce<FreshnessStatus>(
        (worst, s) => (STATUS_RANK[s.status] > STATUS_RANK[worst] ? s.status : worst),
        matched[0].status,
      )
    : isPending
      ? 'checking'
      : 'unknown';

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
        className={`flex items-center gap-3 rounded-xl border p-3 ${STATUS_BANNER_BG[state]} ${className}`}
        role="status"
        aria-label={`Data freshness: ${STATUS_LABEL[state]}. ${latestDate ? `Last updated ${relativeTime(latestDate)}` : 'Update time unknown'}. Source: ${sources}`}
      >
        <div className={`flex-shrink-0 ${STATUS_ICON_COLOR[state]}`}>
          {state === 'fresh' ? <RefreshCw size={18} /> : <Clock size={18} />}
        </div>
        <div className="flex-1 min-w-0">
          <div className={`text-sm font-medium ${STATUS_BANNER_TEXT[state]}`}>
            {STATUS_LABEL[state]}
            {latestDate && (
              <span className="font-normal opacity-80">
                {' — Updated '}
                {relativeTime(latestDate)}
              </span>
            )}
          </div>
          <div className="text-xs opacity-60 dark:opacity-90 mt-0.5">
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
          className={`inline-block w-2.5 h-2.5 rounded-full flex-shrink-0 ${STATUS_DOT[state]}`}
          aria-label={`Status: ${STATUS_LABEL[state]}`}
        />
      </div>
    );
  }

  // Default: inline variant
  if (!measured) {
    return (
      <div className={`flex items-center gap-2 text-xs text-gray-400 dark:text-neutral-muted/80 ${className}`}>
        <span
          className={`inline-block w-2 h-2 rounded-full ${STATUS_DOT[state]}`}
          aria-label={`Data freshness status: ${STATUS_LABEL[state]}`}
        />
        Source: {sources}
      </div>
    );
  }

  return (
    <div
      className={`flex items-center gap-2 text-xs text-gray-500 dark:text-neutral-muted/80 ${className}`}
      title={`${label} — ${STATUS_LABEL[state]}. Updated: ${latestDate || 'unknown'}`}>
      <span
        className={`inline-block w-2 h-2 rounded-full ${STATUS_DOT[state]}`}
        aria-label={`Data freshness status: ${STATUS_LABEL[state]}`}
      />
      <span>
        Data as of: {latestDate ? new Date(latestDate).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}
        {' | '}Source: {sources}
      </span>
    </div>
  );
}
