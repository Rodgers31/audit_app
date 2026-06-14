/**
 * Client component that records every client-side navigation into the
 * session navigation trail. Mounted once inside the root layout so it
 * fires for every route change.
 *
 * Wrapped in <Suspense> by the consumer because `useSearchParams()`
 * requires it in Next 15.
 */
'use client';

import { useTrackNavTrail } from './trail';

export default function NavTrailTracker(): null {
  useTrackNavTrail();
  return null;
}
