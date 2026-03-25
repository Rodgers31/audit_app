'use client';

import { motion } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';
import InfoTip from '@/components/InfoTip';

/**
 * Zone 3: Floating metrics surface — overlaps the hero.
 * Semi-transparent surface with Total Debt, Risk Level, and Kenya map preview.
 * This surface is NOT a card — it bleeds across zone boundaries.
 */
export default function MetricsStrip() {
  return (
    <div className='relative z-20 max-w-dashboard mx-auto px-4 sm:px-6 lg:px-8 -mt-[14vh]'>
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.5 }}
        className='relative'>
        {/* Floating surface — translucent, overlapping */}
        <div className='glass-surface rounded-3xl px-6 sm:px-10 py-8 sm:py-10 shadow-elevated'>
          <div className='flex flex-col lg:flex-row items-start lg:items-center justify-between gap-8'>
            {/* LEFT: Primary metrics */}
            <div className='flex flex-col sm:flex-row items-start sm:items-end gap-6 sm:gap-10'>
              {/* Total Debt */}
              <div>
                <div className='flex items-center gap-2 mb-1'>
                  <span className='text-2xl'>🇰🇪</span>
                  <span className='text-xs font-medium text-neutral-muted uppercase tracking-widest'>
                    Total Debt as of 2024
                  </span>
                  <InfoTip term='debt-to-gdp' size={11} />
                </div>
                <span className='metric-hero text-gov-dark'>
                  11.5<span className='text-4xl md:text-5xl ml-1'>T</span>
                </span>
              </div>

              {/* Divider */}
              <div className='hidden sm:block w-px h-16 bg-neutral-border/60' />

              {/* Risk Level */}
              <div>
                <div className='flex items-center gap-2 mb-1'>
                  <span className='text-xs font-medium text-neutral-muted uppercase tracking-widest'>
                    Risk Level
                  </span>
                  <InfoTip term='debt-sustainability' size={11} />
                </div>
                <div className='flex items-end gap-3'>
                  <span className='metric-large text-gov-dark'>74%</span>
                  <span className='pill-risk mb-1'>
                    <AlertTriangle className='w-3.5 h-3.5' />
                    High Risk
                  </span>
                </div>
              </div>
            </div>

            {/* RIGHT: Connect-to-map teaser — small Kenya silhouette */}
            <div className='hidden lg:flex items-center justify-center w-44 h-32 rounded-xl bg-gov-forest/5 border border-gov-forest/10 overflow-hidden relative'>
              <svg viewBox='0 0 200 220' className='w-full h-full opacity-50'>
                <path
                  d='M80 10 L120 8 L150 22 L165 50 L158 75 L140 95 L120 110 L95 108 L70 95 L52 72 L48 50 L60 28 Z'
                  fill='#1B3A2A'
                  opacity='0.25'
                  stroke='#1B3A2A'
                  strokeWidth='1'
                />
                <circle cx='110' cy='48' r='3' fill='#C94A4A' opacity='0.7' />
                <circle cx='90' cy='65' r='2.5' fill='#4A7C5C' opacity='0.6' />
                <circle cx='125' cy='72' r='2.5' fill='#D9A441' opacity='0.6' />
              </svg>
              <div className='absolute bottom-2 right-2 text-[10px] text-gov-forest/40 font-medium'>
                47 Counties
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
