'use client';

import Image from 'next/image';

/**
 * GlobalBottomBackground
 *
 * Fixed bottom-of-viewport Kenyan flag background that appears on every page.
 * Uses position:fixed so it stays pinned as the user scrolls; page content
 * flows over it naturally. A multi-stop gradient blends the image into the
 * neutral gov-sand background above.
 */
export default function GlobalBottomBackground() {
  return (
    <div
      className='fixed bottom-0 left-0 right-0 pointer-events-none'
      style={{ height: '45vh', zIndex: 0 }}
      aria-hidden='true'>
      {/* Kenyan flag image — light + dark variants stacked, opacity
          flips on ``prefers-color-scheme: dark`` for a smooth swap. */}
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

      {/* Cinematic tint overlay */}
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

      {/* Top-edge fade: page background → transparent. Uses
          ``--page-bg-rgb`` (defined in globals.css) so the fade
          blends into cream in light mode and the deep dark in
          dark mode, no flicker on theme switch. */}
      <div className='absolute top-0 left-0 right-0 pointer-events-none' style={{ height: '50%' }}>
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
  );
}
