'use client';
import { Analytics } from '@vercel/analytics/react';
import { SpeedInsights } from '@vercel/speed-insights/next';
import { usePathname, useSearchParams } from 'next/navigation';
import { filterAuthEvent, isPrivateAuthUrl } from '@/lib/auth/privacy';
export default function PrivacyCollectors() {
  const pathname = usePathname();
  const search = useSearchParams();
  if (!pathname || isPrivateAuthUrl(`${pathname}?${search.toString()}`))
    return null;
  return <><Analytics beforeSend={filterAuthEvent}/><SpeedInsights beforeSend={filterAuthEvent}/></>;
}
