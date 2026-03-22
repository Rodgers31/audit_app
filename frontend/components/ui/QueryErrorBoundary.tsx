'use client';

import ErrorCard from './ErrorCard';

interface QueryErrorBoundaryProps {
  /** Whether the query has an error */
  isError: boolean;
  /** The query's refetch function */
  refetch: () => void;
  /** Optional error title */
  title?: string;
  /** Optional error message */
  message?: string;
  /** Use compact inline style */
  compact?: boolean;
  /** Additional className */
  className?: string;
  /** Children to render when no error */
  children: React.ReactNode;
}

/**
 * Wraps React Query-powered content. Shows ErrorCard when the query has an error,
 * using the query's refetch() as the retry handler.
 *
 * Usage:
 * ```tsx
 * const { data, isError, refetch, isLoading } = useMyQuery();
 *
 * if (isLoading) return <SkeletonCard />;
 *
 * <QueryErrorBoundary isError={isError} refetch={refetch}>
 *   <MyComponent data={data} />
 * </QueryErrorBoundary>
 * ```
 */
export default function QueryErrorBoundary({
  isError,
  refetch,
  title,
  message,
  compact = false,
  className,
  children,
}: QueryErrorBoundaryProps) {
  if (isError) {
    return (
      <ErrorCard
        title={title}
        message={message}
        onRetry={refetch}
        compact={compact}
        className={className}
      />
    );
  }

  return <>{children}</>;
}
