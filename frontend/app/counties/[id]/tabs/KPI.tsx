/**
 * KPI pill — tiny label+value+sub block shared across overview/budget/projects tabs.
 */
export default function KPI({
  label,
  value,
  sub,
  accent = 'text-gray-900 dark:text-neutral-text',
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div>
      <div className='text-[10px] uppercase tracking-wider text-gray-400 dark:text-neutral-muted/80 mb-0.5'>{label}</div>
      <div className={`text-base font-bold leading-tight ${accent}`}>{value}</div>
      {sub && <div className='text-[11px] text-gray-500 dark:text-neutral-muted/80'>{sub}</div>}
    </div>
  );
}
