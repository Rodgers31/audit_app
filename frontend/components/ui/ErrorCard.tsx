'use client';

import { cn } from '@/lib/utils';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorCardProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  compact?: boolean;
  className?: string;
}

/**
 * Reusable error state component.
 * - `compact`: small inline version for use within cards/sections
 * - default: full card version for empty sections
 */
export default function ErrorCard({
  title = 'Something went wrong',
  message = 'Data temporarily unavailable',
  onRetry,
  compact = false,
  className,
}: ErrorCardProps) {
  if (compact) {
    return (
      <div
        className={cn(
          'flex items-center gap-3 rounded-lg bg-red-50/60 border border-red-200/40 px-4 py-3',
          className
        )}>
        <AlertTriangle className='w-4 h-4 text-red-500/70 flex-shrink-0' />
        <div className='flex-1 min-w-0'>
          <p className='text-xs font-medium text-gov-dark'>{title}</p>
          <p className='text-[11px] text-gov-dark/50'>{message}</p>
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            className='flex items-center gap-1 text-[11px] font-medium text-red-600 hover:text-red-700 transition-colors flex-shrink-0'>
            <RefreshCw className='w-3 h-3' />
            Retry
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        'glass-card flex flex-col items-center justify-center py-12 px-6 text-center',
        className
      )}>
      <div className='w-12 h-12 rounded-full bg-red-50 border border-red-200/40 flex items-center justify-center mb-4'>
        <AlertTriangle className='w-6 h-6 text-red-500/70' />
      </div>
      <h3 className='font-display text-lg text-gov-dark mb-1'>{title}</h3>
      <p className='text-sm text-gov-dark/50 max-w-sm mb-5'>{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className='inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gov-dark text-white text-sm font-medium hover:bg-gov-dark/90 active:scale-[0.98] transition-all shadow-sm'>
          <RefreshCw className='w-3.5 h-3.5' />
          Try Again
        </button>
      )}
    </div>
  );
}
