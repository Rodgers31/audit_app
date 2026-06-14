/**
 * Session-wide navigation-trail tracking.
 *
 * Used by `SmartBackLink` (below) to decide whether clicking a "← All
 * counties" style back link should do `router.back()` (which restores
 * scroll position + URL state) or `router.push(href)` (a fresh load).
 *
 * The native `history.length` is not enough on its own — it counts
 * *any* previous entry, even from a different section of the app.
 * Calling `router.back()` in that case sends the user somewhere
 * unexpected (often the dashboard or an unrelated page).
 *
 * Instead we maintain our own in-session trail of `{pathname, search}`
 * pairs. SmartBackLink inspects the entry immediately before the
 * current one and only pops the history stack when that entry matches
 * the back link's target pathname.
 *
 * Trail is stored in `sessionStorage` so it survives hard reloads
 * within the tab but is isolated per-tab — so two tabs don't fight
 * over each other's trail.
 */
'use client';

import { useEffect } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';

const STORAGE_KEY = 'auditgava-nav-trail';
const MAX_ENTRIES = 30;

export interface TrailEntry {
  pathname: string;
  search: string; // leading "?" included, or empty string
  ts: number;
}

function safeGet(): TrailEntry[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function safeSet(trail: TrailEntry[]): void {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(trail.slice(-MAX_ENTRIES)));
  } catch {
    // swallow — storage full / disabled; back navigation falls back to push.
  }
}

/**
 * Hook: appends the current URL to the trail on every pathname /
 * searchParams change. Mount this once at the root of every page
 * layout so every client navigation is recorded.
 */
export function useTrackNavTrail(): void {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const search = searchParams.toString();
    const current: TrailEntry = {
      pathname,
      search: search ? `?${search}` : '',
      ts: Date.now(),
    };
    const trail = safeGet();
    const last = trail[trail.length - 1];
    // De-dupe consecutive identical entries (e.g. tab URL replace → same
    // pathname with new search; we keep the most recent search).
    if (last && last.pathname === current.pathname) {
      trail[trail.length - 1] = current;
    } else {
      trail.push(current);
    }
    safeSet(trail);
  }, [pathname, searchParams]);
}

/** Returns the previous trail entry (the one before the current page). */
export function getPreviousTrailEntry(): TrailEntry | null {
  const trail = safeGet();
  if (trail.length < 2) return null;
  return trail[trail.length - 2] ?? null;
}

/**
 * Should a "back to X" link call `router.back()` (restores state), or
 * should it navigate forward to `href` as a fresh load?
 *
 * Returns `true` iff the previous trail entry's pathname matches the
 * back link's target pathname. If a match is found, router.back() will
 * land the user at the *exact* previous URL (with query params + scroll
 * position restored), which is almost always what the user wants.
 */
export function shouldUseBackNavigation(backHref: string): boolean {
  if (typeof window === 'undefined') return false;
  if (window.history.length < 2) return false;
  const prev = getPreviousTrailEntry();
  if (!prev) return false;
  // Target pathname is the `href` up to the first "?" — query strings
  // may differ (the previous page had filters set, the link doesn't).
  const targetPath = backHref.split('?')[0] ?? '/';
  return prev.pathname === targetPath;
}
