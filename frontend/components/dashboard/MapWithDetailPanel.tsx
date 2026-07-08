/**
 * MapWithDetailPanel
 *
 * Isolates the InteractiveKenyaMap + CountyDetailsPanel pair so that ALL
 * map-driven state (`hoveredCounty`, `selectedCounty`, `countyIndex`)
 * stays local to this subtree. This state used to live on the homepage
 * root, which meant every county tap and every 8s auto-rotate tick
 * re-rendered SummaryStrip, NationalDebtCard, AuditReportsSection, and
 * the rest of the dashboard — an expensive cascade that showed up as
 * multi-second INP on low-end mobile devices. Nothing outside this pair
 * consumes the selection, so the state lives here.
 */
'use client';

import { CountyDetailsPanel } from '@/components/dashboard';
import MapSkeleton from '@/components/MapSkeleton';
import { County } from '@/types';
import { motion } from 'framer-motion';
import dynamic from 'next/dynamic';
import { useCallback, useState } from 'react';

// next/dynamic with ssr:false keeps the 100KB+ map payload out of the
// server bundle and off the initial JS download. The skeleton provides
// an immediate visual and prevents layout shift during hydration.
const InteractiveKenyaMap = dynamic(() => import('@/components/InteractiveKenyaMap'), {
  ssr: false,
  loading: () => <MapSkeleton className='p-4' />,
});

interface MapWithDetailPanelProps {
  counties: County[];
}

export default function MapWithDetailPanel({ counties }: MapWithDetailPanelProps) {
  const [hoveredCounty, setHoveredCounty] = useState<County | null>(null);
  const [selectedCounty, setSelectedCounty] = useState<County | null>(null);
  const [countyIndex, setCountyIndex] = useState(0);

  const handleCountyHover = useCallback((county: County | null) => {
    setHoveredCounty(county);
  }, []);

  // Priority: hover > explicit click > auto-rotate
  const activeCounty = hoveredCounty ?? selectedCounty ?? counties[countyIndex] ?? null;

  return (
    <motion.div
      id='home-map'
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.8, delay: 0.2 }}
      className='grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-0 items-stretch rounded-xl bg-gray-50/60 dark:bg-surface-elevated/70 border border-gray-200/40 dark:border-neutral-border/40 overflow-hidden scroll-mt-24'>
      <InteractiveKenyaMap
        counties={counties}
        onCountySelect={setSelectedCounty}
        onCountyHover={handleCountyHover}
        selectedCounty={selectedCounty}
        currentCountyIndex={countyIndex}
        onCountyIndexChange={setCountyIndex}
        className='p-4'
      />
      <div className='border-t lg:border-t-0 lg:border-l border-gray-200/50 dark:border-neutral-border/50'>
        <CountyDetailsPanel
          county={activeCounty}
          className='h-full rounded-none border-0 shadow-none'
        />
      </div>
    </motion.div>
  );
}
