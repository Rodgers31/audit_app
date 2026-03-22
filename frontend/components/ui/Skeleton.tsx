import { cn } from '@/lib/utils';

/** Base skeleton — animated pulse placeholder bar */
export function Skeleton({
  className,
  style,
}: {
  className?: string;
  style?: React.CSSProperties;
}) {
  return <div className={cn('animate-pulse bg-gray-200 rounded', className)} style={style} />;
}

/** Card-shaped skeleton with title + 3 content lines */
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn('glass-card p-6 space-y-4', className)}>
      {/* Title */}
      <Skeleton className='h-5 w-2/3' />
      {/* Subtitle */}
      <Skeleton className='h-3 w-1/2' />
      {/* Content lines */}
      <div className='space-y-3 pt-2'>
        <Skeleton className='h-3 w-full' />
        <Skeleton className='h-3 w-5/6' />
        <Skeleton className='h-3 w-4/6' />
      </div>
    </div>
  );
}

/** Chart-shaped skeleton (rectangle area) */
export function SkeletonChart({
  className,
  height = 256,
}: {
  className?: string;
  height?: number;
}) {
  return (
    <div className={cn('glass-card p-6 space-y-4', className)}>
      {/* Header area */}
      <div className='flex items-center justify-between'>
        <div className='space-y-2'>
          <Skeleton className='h-5 w-48' />
          <Skeleton className='h-3 w-32' />
        </div>
        <Skeleton className='h-4 w-4 rounded-full' />
      </div>
      {/* Stat cards row */}
      <div className='grid grid-cols-2 sm:grid-cols-4 gap-3'>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className='rounded-xl border border-neutral-border/30 px-3 py-2.5 space-y-2'>
            <Skeleton className='h-2 w-16' />
            <Skeleton className='h-4 w-20' />
            <Skeleton className='h-2 w-14' />
          </div>
        ))}
      </div>
      {/* Chart area */}
      <Skeleton className='w-full rounded-xl' style={{ height }} />
    </div>
  );
}

/** Table-shaped skeleton with header + rows */
export function SkeletonTable({
  rows = 5,
  cols = 4,
}: {
  rows?: number;
  cols?: number;
}) {
  return (
    <div className='glass-card overflow-hidden'>
      {/* Header */}
      <div className='px-6 py-4 border-b border-neutral-border/20 space-y-2'>
        <Skeleton className='h-5 w-48' />
        <Skeleton className='h-3 w-32' />
      </div>
      {/* Table rows */}
      <div className='p-4 space-y-3'>
        {/* Header row */}
        <div className='flex gap-4 pb-2 border-b border-gray-100'>
          {Array.from({ length: cols }).map((_, i) => (
            <Skeleton key={i} className='h-3 flex-1' />
          ))}
        </div>
        {/* Body rows */}
        {Array.from({ length: rows }).map((_, rowIdx) => (
          <div key={rowIdx} className='flex gap-4 items-center'>
            {Array.from({ length: cols }).map((_, colIdx) => (
              <Skeleton
                key={colIdx}
                className='h-3 flex-1'
                style={{ opacity: 1 - rowIdx * 0.1 }}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
