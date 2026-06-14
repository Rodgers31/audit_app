/**
 * MapSkeleton
 *
 * Lightweight placeholder for the InteractiveKenyaMap. Rendered while the
 * map chunk is still downloading so layout doesn't shift and the user
 * sees a reassuring "something is loading here" affordance.
 *
 * Keeps aspect-ratio 16/10 to match the final map container.
 */
export default function MapSkeleton({ className = '' }: { className?: string }) {
  return (
    <div
      className={`relative w-full overflow-hidden rounded-xl bg-gradient-to-br from-gov-sage/10 via-gray-100 to-gov-sage/5 ${className}`}
      style={{ aspectRatio: '16 / 10' }}
      role='status'
      aria-label='Map loading'>
      <div className='absolute inset-0 animate-pulse'>
        <div className='absolute inset-[15%] rounded-full bg-gray-200/60 blur-3xl' />
      </div>
    </div>
  );
}
