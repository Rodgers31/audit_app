'use client';

import React, { createContext, useContext } from 'react';

/* ─────────────────────────────────────────────────────────
   ScenicBackgroundLayout
   ─────────────────────────────────────────────────────────
   Reusable split-scenic layout for any page.

   Visual flow:
     user sees top landscape → scrolls into clean data → exits with bottom landscape

   Architecture (4 visual layers):
     L1  Fixed background images (top + bottom, position:fixed)
     L2  Gradient wash overlays on images (darken/blend)
     L3  Content flows normally — the readable "middle" zone
         backgrounds itself with a solid neutral to mask L1
     L4  Gradient transition edges (top-blend, bottom-blend)

   Key design decisions:
     • Images are position:fixed so they don't scroll with content.
     • Content is normal flow (position:relative, z-1) — no parallax jitter.
     • The "readable middle" simply has a solid bg color → masks the images.
     • Gradient transition divs at hero-bottom and CTA-top create
       the transparent→solid and solid→transparent fade.
     • Works with ANY content height — short, long, tables, charts, forms.

   Usage:
     <ScenicBackgroundLayout
       topImage="/kenya_bg_top.jpg"
       bottomImage="/kenya_bg_bottom.jpg"
     >
       {children}
     </ScenicBackgroundLayout>

   Tuning:
     intensity  0.0 → fully transparent middle (images bleed through)
                1.0 → fully opaque solid neutral (no bleed)
                default 0.92 → slight warmth from images bleeding

     readabilityMode  "light" → gov-sand neutral
                      "dark"  → gov-dark neutral

   ───────────────────────────────────────────────────────── */

export interface ScenicBackgroundLayoutProps {
  children: React.ReactNode;
  topImage: string;
  bottomImage: string;
  /** Optional dark-mode variants. When provided, both light + dark
   * images render stacked and crossfade via opacity on
   * ``prefers-color-scheme: dark``. */
  topImageDark?: string;
  bottomImageDark?: string;
  /** Height of the top scenic zone. Default "65vh". */
  topHeight?: string;
  /** Height of the bottom scenic zone. Default "45vh". */
  bottomHeight?: string;
  /** Theme mode for the readable middle zone. */
  readabilityMode?: 'light' | 'dark';
  /** 0 = fully transparent middle, 1 = fully opaque neutral. Default 0.92. */
  intensity?: number;
  className?: string;
}

/* ── Theme context — lets nested components read mode/intensity ── */
interface ScenicTheme {
  mode: 'light' | 'dark';
  intensity: number;
}
const ScenicThemeContext = createContext<ScenicTheme>({
  mode: 'light',
  intensity: 0.92,
});
export const useScenicTheme = () => useContext(ScenicThemeContext);

/* ── RGB tokens per mode ── */
const NEUTRAL_RGB = {
  light: '245,240,232', // gov-sand  #F5F0E8
  dark: '15,26,18', // gov-dark  #0F1A12
} as const;

export default function ScenicBackgroundLayout({
  children,
  topImage,
  bottomImage,
  topImageDark,
  bottomImageDark,
  topHeight = '65vh',
  bottomHeight = '45vh',
  readabilityMode = 'light',
  intensity = 0.92,
  className = '',
}: ScenicBackgroundLayoutProps) {
  const rgb = NEUTRAL_RGB[readabilityMode];
  const a = intensity; // shorthand

  return (
    <ScenicThemeContext.Provider value={{ mode: readabilityMode, intensity }}>
      <div
        className={`scenic-layout relative min-h-screen overflow-hidden ${className}`}
        data-scenic-mode={readabilityMode}
        style={{ backgroundColor: `rgba(${rgb},${a})` }}>
        {/* ═══════════════════════════════════════════════
            L1 — ABSOLUTE BACKGROUND IMAGES
            Pinned to top / bottom of the layout container.
            Content scrolls past them naturally.
            ═══════════════════════════════════════════════ */}

        {/* Top image — anchored to top of layout container.
            ``lg:!h-[65vh]`` overrides the inline 50vh on laptop-sized
            viewports so the wider container still shows enough
            vertical image to keep both the starfield (top of image)
            and the moon/sun (~70% down) in frame at once. Without
            this, ``object-cover`` scales by width on wide screens
            and crops to ~55% of the image height — moon ends up
            below the visible region. ``!`` is required to beat the
            inline ``style`` declaration's specificity. */}
        <div
          className='scenic-bg-top lg:!h-[65vh]'
          aria-hidden='true'
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: topHeight,
            zIndex: 0,
          }}>
          {/* ``object-position: center 20%`` anchors the image so the
              upper portion (where the dark variant's starfield lives)
              stays visible. ``object-cover`` keeps the full hero
              filled — ``object-contain`` was tried briefly but left
              an ugly empty band on the sides, so we accept the
              bottom-of-image crop in exchange for full coverage. */}
          <img
            src={topImage}
            alt=''
            className={`absolute inset-0 w-full h-full object-cover ${
              topImageDark
                ? 'opacity-100 dark:opacity-0 transition-opacity duration-500'
                : ''
            }`}
            style={{ objectPosition: 'center 20%' }}
            loading='eager'
            decoding='async'
          />
          {topImageDark && (
            <img
              src={topImageDark}
              alt=''
              className='absolute inset-0 w-full h-full object-cover opacity-0 dark:opacity-100 transition-opacity duration-500'
              style={{ objectPosition: 'center 20%' }}
              loading='eager'
              decoding='async'
            />
          )}
          {/* L2 — header-matching tint: seamless merge with fixed nav.
               Uses a smooth multi-stop gradient that avoids any visible
               "line" where the nav ends and the image begins. */}
          <div
            className='absolute top-0 left-0 right-0 pointer-events-none'
            style={{ height: '75%' }}>
            {/* Vertical fade: solid header color at top → transparent */}
            <div
              className='absolute inset-0'
              style={{
                background: `linear-gradient(
                  to bottom,
                  rgba(15,26,18,0.97) 0%,
                  rgba(15,26,18,0.88) 8%,
                  rgba(15,26,18,0.72) 16%,
                  rgba(15,26,18,0.50) 26%,
                  rgba(15,26,18,0.30) 36%,
                  rgba(15,26,18,0.14) 46%,
                  rgba(15,26,18,0.05) 56%,
                  transparent 66%
                )`,
              }}
            />
            {/* Horizontal fade: stronger on left (under nav logo) → lighter on right */}
            <div
              className='absolute inset-0'
              style={{
                background: `linear-gradient(
                  to right,
                  rgba(15,26,18,0.35) 0%,
                  rgba(15,26,18,0.12) 30%,
                  transparent 55%
                )`,
              }}
            />
          </div>

          {/* Bottom-edge fade: scenic image → neutral background
              Uses a tall 50% zone with many stops for a perfectly smooth
              blend that eliminates the visible "layer line". */}
          <div
            className='absolute bottom-0 left-0 right-0 pointer-events-none'
            aria-hidden='true'
            style={{ height: '50%' }}>
            <div
              className='absolute inset-0'
              style={{
                background: `linear-gradient(to bottom,
                  transparent 0%,
                  rgba(${rgb},${a * 0.08}) 15%,
                  rgba(${rgb},${a * 0.22}) 30%,
                  rgba(${rgb},${a * 0.42}) 45%,
                  rgba(${rgb},${a * 0.65}) 60%,
                  rgba(${rgb},${a * 0.82}) 75%,
                  rgba(${rgb},${a * 0.94}) 88%,
                  rgba(${rgb},${a}) 100%
                )`,
              }}
            />
          </div>
        </div>

        {/* Bottom image — anchored to bottom of layout container */}
        <div
          className='scenic-bg-bottom'
          aria-hidden='true'
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            height: bottomHeight,
            zIndex: 0,
          }}>
          <img
            src={bottomImage}
            alt=''
            className={`absolute inset-0 w-full h-full object-cover ${
              bottomImageDark
                ? 'opacity-100 dark:opacity-0 transition-opacity duration-500'
                : ''
            }`}
            style={{ objectPosition: 'center 75%' }}
            loading='lazy'
            decoding='async'
          />
          {bottomImageDark && (
            <img
              src={bottomImageDark}
              alt=''
              className='absolute inset-0 w-full h-full object-cover opacity-0 dark:opacity-100 transition-opacity duration-500'
              style={{ objectPosition: 'center 75%' }}
              loading='lazy'
              decoding='async'
            />
          )}
          {/* L2 — cinematic overlay on bottom image */}
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

          {/* Top-edge fade: neutral background → scenic image
              Mirror of the top-image bottom-edge — tall zone, many stops. */}
          <div
            className='absolute top-0 left-0 right-0 pointer-events-none'
            aria-hidden='true'
            style={{ height: '50%' }}>
            <div
              className='absolute inset-0'
              style={{
                background: `linear-gradient(to top,
                  transparent 0%,
                  rgba(${rgb},${a * 0.08}) 15%,
                  rgba(${rgb},${a * 0.22}) 30%,
                  rgba(${rgb},${a * 0.42}) 45%,
                  rgba(${rgb},${a * 0.65}) 60%,
                  rgba(${rgb},${a * 0.82}) 75%,
                  rgba(${rgb},${a * 0.94}) 88%,
                  rgba(${rgb},${a}) 100%
                )`,
              }}
            />
          </div>
        </div>

        {/* ═══════════════════════════════════════════════
            L3 + L4 — CONTENT (normal document flow)
            Scrolls naturally. No parallax. No jitter.
            ═══════════════════════════════════════════════ */}
        <div className='relative z-[1]'>{children}</div>
      </div>
    </ScenicThemeContext.Provider>
  );
}

/* ─────────────────────────────────────────────────────────
   Sub-components for composing inside the layout
   ───────────────────────────────────────────────────────── */

/**
 * <ScenicHeroZone> — transparent zone where the top image shows through.
 * Place your hero content inside. Height should roughly match topHeight.
 */
export function ScenicHeroZone({
  children,
  className = '',
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`scenic-hero-zone relative ${className}`}>{children}</div>;
}

/**
 * <ScenicReadableZone> — solid neutral background for readable content.
 * This masks the fixed images behind it. Gradient edges are built-in.
 */
export function ScenicReadableZone({
  children,
  className = '',
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const { mode, intensity } = useScenicTheme();
  const rgb = NEUTRAL_RGB[mode];
  const a = intensity;

  return (
    <div className={`scenic-readable relative ${className}`}>
      {/* Top gradient edge: transparent → solid */}
      <div
        className='scenic-edge-top pointer-events-none'
        aria-hidden='true'
        style={{
          height: '160px',
          background: `linear-gradient(to bottom,
            rgba(${rgb},0) 0%,
            rgba(${rgb},${a * 0.5}) 40%,
            rgba(${rgb},${a}) 100%
          )`,
        }}
      />

      {/* Solid readable middle — grows with content */}
      <div style={{ background: `rgba(${rgb},${a})` }}>{children}</div>

      {/* Bottom gradient edge: solid → transparent */}
      <div
        className='scenic-edge-bottom pointer-events-none'
        aria-hidden='true'
        style={{
          height: '160px',
          background: `linear-gradient(to bottom,
            rgba(${rgb},${a}) 0%,
            rgba(${rgb},${a * 0.5}) 60%,
            rgba(${rgb},0) 100%
          )`,
        }}
      />
    </div>
  );
}

/**
 * <ScenicBottomZone> — transparent zone where the bottom image shows through.
 * Place your CTA / footer content inside.
 */
export function ScenicBottomZone({
  children,
  className = '',
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`scenic-bottom-zone relative ${className}`}>{children}</div>;
}
