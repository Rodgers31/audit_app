'use client';

import { useSyncExternalStore } from 'react';
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

const subscribe = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;

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

/** A status word cannot certify an absent, impossible or future publication. */
function isPublicationDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:Z|[+-]\d{2}:\d{2})?)?$/.test(value)) return false;
  const stamp = Date.parse(value);
  const calendar = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isFinite(stamp) && stamp <= Date.now() &&
    Number.isFinite(calendar.getTime()) && calendar.toISOString().slice(0, 10) === value.slice(0, 10);
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
    queryFn: async ({ signal }) => {
      const { data } = await apiClient.get<FreshnessResponse>('/data/freshness', { signal });
      return data;
    },
    staleTime: 30 * 60 * 1000, // 30 min
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

function publicationCalendarDate(dateStr: string): string {
  // A publisher's date does not change when its timestamp crosses a UTC day.
  return new Date(`${dateStr.slice(0, 10)}T00:00:00Z`).toLocaleDateString('en-GB', {
    timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric',
  });
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
  const { data, isPending, isError } = useDataFreshness();
  const hydrated = useSyncExternalStore(subscribe, clientSnapshot, serverSnapshot);

  const sourceCodes = Array.from(new Set(sources.split('/').map((s) => s.trim()).filter(Boolean)));
  const entries = Array.isArray(data?.sources) ? data.sources : [];
  const matched = entries.filter((s) => s && typeof s === 'object' && sourceCodes.includes(s.source));

  // Worst status among matched sources. No match, or any status we do not
  // recognise, is not a measurement — it must not default to 'fresh'.
  const measured = !isError && sourceCodes.length > 0 &&
    sourceCodes.every((code) => matched.some((s) => s.source === code)) &&
    matched.every((s) => isFreshnessStatus(s.status) && isPublicationDate(s.last_updated));
  const state: BadgeState = measured
    ? matched.reduce<FreshnessStatus>(
        (worst, s) => (STATUS_RANK[s.status] > STATUS_RANK[worst] ? s.status : worst),
        matched[0].status,
      )
    : isPending && hydrated
      ? 'checking'
      : 'unknown';

  // A multi-publisher badge cannot date the whole group by its newest member.
  const dates = (measured ? matched : [])
    .map((s) => s.last_updated)
    .filter(Boolean)
    .sort();
  const latestDate = measured && dates.length === matched.length ? dates[0] : null;

  const label = measured ? matched.map((s) => typeof s.label === 'string' ? s.label : s.source).join(' / ') : sources;

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
                {publicationCalendarDate(latestDate)}
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
        <span>{STATUS_LABEL[state]} · Source: {sources}</span>
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
        Data as of: {latestDate ? publicationCalendarDate(latestDate) : '—'}
        {' | '}Source: {sources}
      </span>
    </div>
  );
}
