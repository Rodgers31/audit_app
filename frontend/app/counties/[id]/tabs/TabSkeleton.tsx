/**
 * TabSkeleton
 *
 * Minimal pulsing placeholder rendered while a dynamically-imported
 * county-detail tab is still downloading. Kept shape-agnostic so every
 * tab can reuse it.
 */
export default function TabSkeleton() {
  return (
    <div className='space-y-4' role='status' aria-label='Loading tab content'>
      <div className='h-24 rounded-xl bg-gray-100 dark:bg-surface-elevated animate-pulse' />
      <div className='grid grid-cols-1 sm:grid-cols-2 gap-4'>
        <div className='h-48 rounded-xl bg-gray-100 dark:bg-surface-elevated animate-pulse' />
        <div className='h-48 rounded-xl bg-gray-100 dark:bg-surface-elevated animate-pulse' />
      </div>
      <div className='h-64 rounded-xl bg-gray-100 dark:bg-surface-elevated animate-pulse' />
    </div>
  );
}
