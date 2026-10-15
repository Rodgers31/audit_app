'use client';

import CountyDetailSkeleton from './CountyDetailSkeleton';

/** Stream a data-free shell while the existing bounded SSR read is pending. */
export default function CountyDetailLoading() {
  return <CountyDetailSkeleton />;
}
