'use client';

import { cn } from '@/lib/utils';
import { useEffect, useRef, useState } from 'react';

interface ResponsiveTableProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * Wraps a table for mobile responsiveness.
 * - Desktop (md+): renders normally
 * - Mobile: horizontal scroll container with a subtle "← scroll →" hint
 */
export default function ResponsiveTable({ children, className }: ResponsiveTableProps) {
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
        className='overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0 scrollbar-thin scrollbar-thumb-gray-300'>
        {children}
      </div>
      {/* Scroll hint — only on mobile when content overflows */}
      {showHint && (
        <div className='md:hidden absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-full pt-2'>
          <span className='text-[10px] text-gov-dark/30 font-medium animate-pulse'>
            ← scroll →
          </span>
        </div>
      )}
    </div>
  );
}
