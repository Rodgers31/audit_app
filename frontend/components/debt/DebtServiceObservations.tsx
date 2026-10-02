import type { DebtServicePoint } from '@/lib/debt/debtServiceSeries';

const money = (value: number | null) =>
  value == null ? 'Not published' : value.toLocaleString('en-KE', { maximumFractionDigits: 20 });

function share(point: DebtServicePoint): string {
  if (point.ratio != null) return `${point.ratio.toFixed(1)}%`;
  const reasons = [];
  if (point.service == null) reasons.push('debt service not published');
  if (point.revenue == null) reasons.push('revenue not published');
  else if (point.revenue <= 0) reasons.push('revenue must be greater than zero');
  return `Withheld: ${reasons.join('; ')}`;
}

/** Same observations as the plotted series, available without pointer hover. */
export default function DebtServiceObservations({ points }: { points: DebtServicePoint[] }) {
  return (
    <details className='mt-3 min-w-0'>
      <summary className='cursor-pointer rounded-lg py-3 text-sm font-semibold text-gov-dark dark:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gov-forest'>
        Read chart data
      </summary>
      {/* Fixed table layout lets cells wrap within the card at narrow widths. */}
      <table className='w-full table-fixed text-xs sm:text-sm text-gov-dark dark:text-white'>
        <caption className='text-left py-3 font-semibold'>Debt cost observations by fiscal year</caption>
        <thead>
          <tr className='border-b border-neutral-border text-left align-top'>
            <th scope='col' className='w-1/5 px-1 py-2 sm:px-3'>Fiscal year</th>
            <th scope='col' className='px-1 py-2 sm:px-3'>Debt service (KES)</th>
            <th scope='col' className='px-1 py-2 sm:px-3'>Revenue (KES)</th>
            <th scope='col' className='px-1 py-2 sm:px-3'>Service / revenue (%)</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point, index) => (
            <tr key={`${point.year}-${index}`} className='border-b border-neutral-border/40 align-top'>
              <th scope='row' className='px-1 py-3 sm:px-3 text-left font-medium break-words'>
                {point.year ?? 'Fiscal year not published'}
              </th>
              <td className='px-1 py-3 sm:px-3 tabular-nums break-words'>{money(point.service)}</td>
              <td className='px-1 py-3 sm:px-3 tabular-nums break-words'>{money(point.revenue)}</td>
              <td className='px-1 py-3 sm:px-3 tabular-nums break-words'>{share(point)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
