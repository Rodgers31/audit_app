'use client';

import type { WatchlistItem } from '@/lib/api/auth';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useWatchlist } from '@/lib/auth/WatchlistProvider';
import { AnimatePresence, motion } from 'framer-motion';
import { Bookmark, BookmarkCheck, Loader2 } from 'lucide-react';
import { useCallback, useState } from 'react';

interface WatchButtonProps {
  itemType: WatchlistItem['item_type'];
  itemId: string;
  label: string;
  /** Render as compact icon-only (for cards) vs full button */
  compact?: boolean;
  className?: string;
}

/**
 * Reusable "Watch / Unwatch" toggle.
 *
 * Reads from the shared WatchlistProvider context instead of
 * fetching per-instance (no N+1 queries).
 *
 * When the user is NOT logged in, clicking opens the auth modal
 * (handled via a custom event so AuthModal can listen).
 */
export default function WatchButton({
  itemType,
  itemId,
  label,
  compact = false,
  className = '',
}: WatchButtonProps) {
  const { isAuthenticated } = useAuth();
  const { isWatching, watchId: getWatchId, add, remove } = useWatchlist();
  const [loading, setLoading] = useState(false);

  const watching = isWatching(itemType, itemId);
  const currentWatchId = getWatchId(itemType, itemId);

  const handleToggle = useCallback(async () => {
    if (!isAuthenticated) {
      window.dispatchEvent(new CustomEvent('open-auth-modal'));
      return;
    }
    setLoading(true);
    try {
      if (watching && currentWatchId) {
        await remove(currentWatchId);
      } else {
        await add({ item_type: itemType, item_id: itemId, label });
      }
    } catch {
      // 409 = already watching
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, watching, currentWatchId, itemType, itemId, label, add, remove]);

  if (compact) {
    return (
      <button
        onClick={handleToggle}
        disabled={loading}
        title={watching ? 'Remove from watchlist' : 'Add to watchlist'}
        className={`p-2 rounded-lg transition-all ${
          watching
            ? 'text-gov-gold bg-gov-gold/15 hover:bg-gov-gold/25'
            : 'text-gov-forest/40 dark:text-emerald-100/40 hover:text-gov-sage hover:bg-gov-sage/10'
        } disabled:opacity-50 ${className}`}>
        {loading ? (
          <Loader2 className='w-4 h-4 animate-spin' />
        ) : watching ? (
          <BookmarkCheck className='w-4 h-4' />
        ) : (
          <Bookmark className='w-4 h-4' />
        )}
      </button>
    );
  }

  return (
    <motion.button
      onClick={handleToggle}
      disabled={loading}
      whileTap={{ scale: 0.96 }}
      className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all border ${
        watching
          ? 'bg-gov-gold/15 text-gov-gold border-gov-gold/30 hover:bg-gov-gold/25'
          : 'bg-white/80 dark:bg-surface-elevated text-gov-forest/70 dark:text-emerald-100/70 border-gov-sage/20 hover:bg-gov-sage/10 hover:text-gov-sage'
      } disabled:opacity-50 shadow-sm ${className}`}>
      <AnimatePresence mode='wait'>
        {loading ? (
          <motion.span
            key='loading'
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}>
            <Loader2 className='w-4 h-4 animate-spin' />
          </motion.span>
        ) : watching ? (
          <motion.span
            key='watching'
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}>
            <BookmarkCheck className='w-4 h-4' />
          </motion.span>
        ) : (
          <motion.span
            key='not-watching'
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}>
            <Bookmark className='w-4 h-4' />
          </motion.span>
        )}
      </AnimatePresence>
      {watching ? 'Watching' : 'Watch'}
    </motion.button>
  );
}
