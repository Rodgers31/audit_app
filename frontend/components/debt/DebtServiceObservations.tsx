import type { FiscalMeasureQualification } from '@/lib/api/fiscal';
import type { DebtServicePoint } from '@/lib/debt/debtServiceSeries';
import { useLang } from '@/lib/i18n/LangProvider';

const formatMoney = (value: number) => value.toLocaleString('en-KE', { maximumFractionDigits: 20 });
type Translate = ReturnType<typeof useLang>['t'];

function share(point: DebtServicePoint, t: Translate): string {
  if (point.ratio != null) return `${point.ratio.toFixed(1)}%`;
  const reasons = [];
  if (point.service == null) reasons.push(t('debt.cost.no_service_reason'));
  if (point.revenue == null) reasons.push(t('debt.cost.no_revenue_reason'));
  else if (point.revenue <= 0) reasons.push(t('debt.cost.zero_revenue_reason'));
  if (!reasons.length) reasons.push(t('debt.cost.no_pair_reason'));
  return t('debt.cost.withheld_reason').replace('{reason}', reasons.join(' · '));
}

function MeasureSource({ proof }: { proof?: FiscalMeasureQualification }) {
  const { t } = useLang();
  if (!proof) return null;
  return <span className='mt-1 block font-normal text-neutral-muted'>
    {t('debt.cost.precision').replace('{vintage}', proof.vintage).replace('{precision}', formatMoney(proof.precision_kes))}{' '}
    <a className='inline-flex min-h-11 min-w-11 max-w-full items-center underline' href={proof.source.url} target='_blank' rel='noopener noreferrer'>
      {proof.source.title ?? t('debt.cost.source')} · {proof.source.page}
    </a>
  </span>;
}

/** Same observations as the plotted series, available without pointer hover. */
export default function DebtServiceObservations({ points }: { points: DebtServicePoint[] }) {
  const { t } = useLang();
  const money = (value: number | null) => value == null ? t('foundation.no_chart_value') : formatMoney(value);
  return (
    <details className='mt-3 min-w-0'>
      <summary className='flex min-h-11 w-fit min-w-11 cursor-pointer items-center rounded py-2 text-sm font-semibold underline underline-offset-4'>
        {t('foundation.chart_table')}
      </summary>
      <table className='w-full table-fixed break-words text-sm'>
        <caption className='py-3 text-left font-semibold'>{t('debt.cost.table')}</caption>
        <thead>
          <tr className='border-b border-neutral-border text-left align-top'>
            <th scope='col' className='w-1/5 px-1 py-2 sm:px-3'>{t('debt.cost.year_column')}</th>
            <th scope='col' className='px-1 py-2 sm:px-3'>{t('debt.cost.service_column')}</th>
            <th scope='col' className='px-1 py-2 sm:px-3'>{t('debt.cost.revenue_column')}</th>
            <th scope='col' className='px-1 py-2 sm:px-3'>{t('debt.cost.share_column')}</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point, index) => (
            <tr key={`${point.year}-${index}`} className='border-b border-neutral-border align-top'>
              <th scope='row' className='px-1 py-3 text-left font-medium sm:px-3'>
                {point.year ?? t('debt.cost.no_year')}
              </th>
              <td className='px-1 py-3 tabular-nums sm:px-3'>{money(point.service)}<MeasureSource proof={point.serviceQualification} /></td>
              <td className='px-1 py-3 tabular-nums sm:px-3'>{money(point.revenue)}<MeasureSource proof={point.revenueQualification} /></td>
              <td className='px-1 py-3 tabular-nums sm:px-3'>{share(point, t)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
