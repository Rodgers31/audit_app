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
  NationalDebtCard,
  NationalLoansCard,
  SummaryStrip,
} from '@/components/dashboard';
import { ScenicBackgroundLayout } from '@/components/layout';
import NewsletterBanner from '@/components/NewsletterBanner';
import { useCounties } from '@/lib/react-query';
import { County } from '@/types';
import { motion } from 'framer-motion';
import { useState } from 'react';

export default function HomeDashboardClient() {
  /* ── Dynamic county data from the database ── */
  const { data: counties = [] } = useCounties();

  // `hoveredCounty` is deliberately NOT stored here — it's owned by
  // MapWithDetailPanel so mouse-move events don't re-render the entire
  // dashboard (SummaryStrip, NationalDebtCard, etc.).
  const [selectedCounty, setSelectedCounty] = useState<County | null>(null);
  const [countyIndex, setCountyIndex] = useState(0);

  return (
    <ScenicBackgroundLayout
      topImage='/kenya_bg_top.jpg'
      bottomImage='/kenya_bg_bottom.jpg'
      topImageDark='/kenya_bg_top_dk.jpg'
      bottomImageDark='/kenya_bg_bottom_dk.jpg'
      topHeight='50vh'
      bottomHeight='50vh'
      readabilityMode='light'
      intensity={0.94}>
      {/* Hero title — scenic image visible behind */}
      <HeroSection />

      {/* ══════════════════════════════════════════════════
          ONE GLASS CONTAINER — wraps ALL dashboard content.
          Background transitions (scenic → neutral → scenic)
          show through the translucent glass as you scroll.
          ══════════════════════════════════════════════════ */}
      <div className='max-w-[1340px] mx-auto px-5 lg:px-8 pb-12'>
        <motion.div
          initial={{ opacity: 0, y: 36 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.4 }}
          className='rounded-2xl bg-white/20 dark:bg-surface-base/60 backdrop-blur-xl border border-white/25 dark:border-white/10 shadow-[0_8px_40px_rgba(0,0,0,0.12)] dark:shadow-[0_8px_40px_rgba(0,0,0,0.4)] p-4 sm:p-6 space-y-6'>
          {/* ── Summary strip ── */}
          <SummaryStrip />

          {/* ── Debt chart + Kenyan Government card ── */}
          <div className='grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-stretch'>
            <NationalDebtCard />
            <KenyanGovCard />
          </div>

          {/* ── Map + County Details — unified container ──
              hoveredCounty state is local to this subtree so hover
              doesn't re-render the entire homepage. */}
          <MapWithDetailPanel
            counties={counties}
            selectedCounty={selectedCounty}
            setSelectedCounty={setSelectedCounty}
            countyIndex={countyIndex}
            setCountyIndex={setCountyIndex}
          />

          {/* ── Latest Audit Reports ── */}
          <AuditReportsSection />

          {/* ── Budget Snapshot + National Loans ── */}
          <div className='grid grid-cols-1 lg:grid-cols-2 gap-5'>
            <BudgetSnapshotCard />
            <NationalLoansCard />
          </div>

          {/* ── Feature Navigation Cards ── */}
          <FeatureNavCards />

          {/* ── Learning Hub CTA ── */}
          <LearningHubCTA />

          {/* ── Newsletter ── */}
          <NewsletterBanner />
        </motion.div>
      </div>

      {/* Spacer for bottom scenic image to show below glass */}
      <div className='h-20' />
    </ScenicBackgroundLayout>
  );
}
