'use client';

import { motion } from 'framer-motion';
import { ArrowLeft } from 'lucide-react';
import Image from 'next/image';
import React from 'react';
import SmartBackLink from '@/lib/navigation/SmartBackLink';

/**
 * PageShell
 *
 * Consistent page layout for all inner pages (debt, budget, counties, learn).
 * NO top scenic image — only the home page has that.
 * Provides:
 *   - Dark-green header band (matches scrolled nav) with white title text,
 *     optional back-link breadcrumb, a subtle radial highlight, and a
 *     gold hairline separating the band from the body
 *   - Cream gov-sand body
 *   - Translucent glass container for data content
 *   - Bottom scenic (Kenyan flag) image visible when scrolled down
 */

interface PageShellProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
  /** Optional breadcrumb link rendered above the title in the dark band. */
  back?: { href: string; label: string };
}

const NEUTRAL_RGB = '245,240,232'; // gov-sand #F5F0E8

export default function PageShell({
  title,
  subtitle,
  children,
  className = '',
  back,
}: PageShellProps) {
  return (
    <div className='relative min-h-screen bg-gov-sand'>
      {/* ═══ Bottom scenic image (Kenyan flag) — pinned to bottom ═══ */}
      <div
        className='absolute bottom-0 left-0 right-0'
        aria-hidden='true'
        style={{ height: '45vh', zIndex: 0 }}>
        {/* Light + dark variants stacked. Opacity is the only thing
            that flips on ``prefers-color-scheme: dark`` so the swap
            crossfades smoothly instead of snapping. */}
        <Image
          src='/kenya_bg_bottom.jpg'
          alt=''
          fill
          sizes='100vw'
          className='object-cover opacity-100 dark:opacity-0 transition-opacity duration-500'
          style={{ objectPosition: 'center 75%' }}
        />
        <Image
          src='/kenya_bg_bottom_dk.jpg'
          alt=''
          fill
          sizes='100vw'
          className='object-cover opacity-0 dark:opacity-100 transition-opacity duration-500'
          style={{ objectPosition: 'center 75%' }}
        />
        {/* Cinematic tint */}
        <div
          className='absolute inset-0'
          style={{
            background: `linear-gradient(180deg,
              rgba(15,26,18,0.60) 0%,
              rgba(15,26,18,0.18) 40%,
              rgba(15,26,18,0.32) 100%
            )`,
          }}
        />
        {/* Top-edge fade into the page background. Uses
            ``--page-bg-rgb`` (defined in globals.css) so the fade
            blends into cream in light mode and the deep dark in
            dark mode. */}
        <div className='absolute top-0 left-0 right-0' style={{ height: '50%' }}>
          <div
            className='absolute inset-0'
            style={{
              background: `linear-gradient(to top,
                transparent 0%,
                rgba(var(--page-bg-rgb),0.07) 15%,
                rgba(var(--page-bg-rgb),0.21) 30%,
                rgba(var(--page-bg-rgb),0.39) 45%,
                rgba(var(--page-bg-rgb),0.61) 60%,
                rgba(var(--page-bg-rgb),0.77) 75%,
                rgba(var(--page-bg-rgb),0.88) 88%,
                rgba(var(--page-bg-rgb),0.94) 100%
              )`,
            }}
          />
        </div>
      </div>

      {/* ═══ Content layer (above the bottom image) ═══ */}
      <div className='relative z-[1]'>
        {/* ── Dark-green header band ── */}
        <div className='relative overflow-hidden bg-gov-dark'>
          {/* Subtle decorative layers — kept faint so existing pages still feel the same */}
          <div
            aria-hidden
            className='pointer-events-none absolute inset-0'
            style={{
              background:
                'radial-gradient(65% 140% at 92% 12%, rgba(74,122,89,0.32) 0%, transparent 60%), radial-gradient(40% 90% at 10% 100%, rgba(212,165,76,0.09) 0%, transparent 60%)',
            }}
          />
          {/* Gold hairline at the bottom edge */}
          <div
            aria-hidden
            className='pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-gov-gold/40 to-transparent'
          />
          {/* Spacer for the fixed navigation bar */}
          <div className='h-[72px]' />
          <div className='relative max-w-[1340px] mx-auto px-5 lg:px-8 pt-6 pb-10'>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: 'easeOut' }}
              className='max-w-3xl'>
              {back && (
                <SmartBackLink
                  href={back.href}
                  className='mb-3 inline-flex items-center gap-1.5 rounded-full bg-white/8 px-3 py-1 text-[12.5px] font-semibold text-white/80 ring-1 ring-inset ring-white/10 backdrop-blur-sm transition-colors hover:bg-white/12 hover:text-white'>
                  <ArrowLeft size={13} />
                  {back.label}
                </SmartBackLink>
              )}
              <h1 className='font-display text-3xl sm:text-4xl lg:text-[2.75rem] text-white leading-[1.12] mb-2 drop-shadow-lg'>
                {title}
              </h1>
              {subtitle && (
                <p className='text-base sm:text-lg text-white/70 font-light tracking-wide drop-shadow-md'>
                  {subtitle}
                </p>
              )}
            </motion.div>
          </div>
        </div>

        {/* ── Glass container ── */}
        <div className='max-w-[1340px] mx-auto px-5 lg:px-8 py-8'>
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: 0.15 }}
            className={`rounded-2xl bg-white/40 dark:bg-surface-base/70 backdrop-blur-xl border border-white/50 dark:border-white/10 shadow-[0_8px_40px_rgba(0,0,0,0.08)] dark:shadow-[0_8px_40px_rgba(0,0,0,0.4)] p-4 sm:p-6 space-y-6 ${className}`}>
            {children}
          </motion.div>
        </div>

        {/* Spacer so bottom scenic image peeks through */}
        <div className='h-24' />
      </div>
    </div>
  );
}
