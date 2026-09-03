'use client';

import { cn } from '@/lib/utils';
import { useEffect, useRef, useState } from 'react';

interface ResponsiveTableProps {
  children: React.ReactNode;
  className?: string;
  /**
   * Let the scroll area bleed to the viewport edge on mobile.
   *
   * Only correct when the table is NOT inside a padded card — the negative
   * margin pulls the scroller out past its parent's padding, which reads as a
   * misalignment anywhere the card supplies its own gutter.
   */
  bleed?: boolean;
}

/**
 * Wraps a table for mobile responsiveness.
 * - Desktop (md+): renders normally
 * - Mobile: horizontal scroll container with a subtle "← scroll →" hint
 */
export default function ResponsiveTable({
  children,
  className,
  bleed = false,
}: ResponsiveTableProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showHint, setShowHint] = useState(false);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const checkOverflow = () => {
      setShowHint(el.scrollWidth > el.clientWidth + 8);
    };

    checkOverflow();
    const observer = new ResizeObserver(checkOverflow);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    // Hide hint once user has scrolled
    if (el.scrollLeft > 20) {
      setShowHint(false);
    }
  };

  return (
    <div className={cn('relative', className)}>
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className={cn(
          'overflow-x-auto scrollbar-thin scrollbar-thumb-gray-300',
          bleed && '-mx-4 px-4 md:mx-0 md:px-0'
        )}>
        {children}
      </div>
      {/* Scroll hint — only on mobile when content overflows.
          Kept in normal flow rather than absolutely positioned below the box:
          several callers sit inside a card with ``overflow-hidden``, which
          clips an out-of-box hint into invisibility.
          ``text-neutral-muted`` rather than a low-opacity tint — the previous
          ``text-gov-dark/30`` measured 1.94:1, well under the 4.5:1 AA floor. */}
      {showHint && (
        <div className='md:hidden flex justify-center pt-2'>
          <span className='text-[11px] text-neutral-muted font-medium animate-pulse'>← scroll →</span>
        </div>
      )}
    </div>
  );
}
