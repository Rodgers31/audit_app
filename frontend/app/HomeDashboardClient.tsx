/**
 * Homepage client component.
 *
 * This is the pure-UI part of the homepage. It reads prefetched data
 * from the React Query hydration boundary (populated server-side in
 * the parent page.tsx) so there are zero loading spinners on first paint.
 *
 * If the cache is somehow empty (e.g. prefetch failed), the hooks
 * gracefully fall back to client-side fetching.
 */
'use client';

import {
  AuditReportsSection,
  BudgetSnapshotCard,
  FeatureNavCards,
  HeroSection,
  KenyanGovCard,
  LearningHubCTA,
  MapWithDetailPanel,
  MoneyTraceRibbon,
  NationalDebtCard,
  NationalLoansCard,
  SummaryStrip,
} from '@/components/dashboard';
import NewsletterBanner from '@/components/NewsletterBanner';
import { useCounties } from '@/lib/react-query';

export default function HomeDashboardClient() {
  /* ── Dynamic county data from the database ── */
  const { data: counties = [] } = useCounties();

  return (
    <div className='min-h-screen bg-gov-sand dark:bg-[#0d1711]'>
      <HeroSection />

      <div className='mx-auto max-w-[1400px] space-y-6 px-5 py-7 sm:px-6 sm:py-9 lg:px-8 lg:py-11'>
        <SummaryStrip />
        <MoneyTraceRibbon />

        <div className='grid grid-cols-1 items-stretch gap-5 lg:grid-cols-[minmax(0,1fr)_300px]'>
          <NationalDebtCard />
          <KenyanGovCard />
        </div>

        <MapWithDetailPanel counties={counties} />

        <AuditReportsSection />

        <div className='grid grid-cols-1 gap-5 lg:grid-cols-2'>
          <BudgetSnapshotCard />
          <NationalLoansCard />
        </div>

        <FeatureNavCards />

        <LearningHubCTA />

        <NewsletterBanner />
      </div>
    </div>
  );
}
