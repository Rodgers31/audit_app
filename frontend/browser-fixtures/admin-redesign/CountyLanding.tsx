'use client';
import CountyDetailClient from '@/app/counties/[id]/CountyDetailClient';
import { WatchlistProvider } from '@/lib/auth/WatchlistProvider';
import { LangProvider } from '@/lib/i18n/LangProvider';
export default function CountyLanding() {
 return <LangProvider><WatchlistProvider><CountyDetailClient /></WatchlistProvider></LangProvider>;
}
