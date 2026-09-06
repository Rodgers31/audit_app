'use client';

/**
 * MoneyFlowTab — wraps the FollowTheMoney visualization for a specific
 * county + fiscal year. The FollowTheMoney component itself is already
 * a standalone chunk (it pulls in d3/sankey), and by putting it inside
 * a dynamic-imported tab we avoid shipping either until the user clicks
 * "Follow the money".
 */
import FollowTheMoney, { YearSelector } from '@/components/FollowTheMoney';
import { useLang } from '@/lib/i18n/LangProvider';
import { useCountyFiscalYears } from '@/lib/react-query';
import { useCountyMoneyFlow } from '@/lib/react-query/useMoneyFlow';
import { moneyFlowDefaultYear } from '@/lib/utils';
import { CountyComprehensive } from '@/types';
import { useState } from 'react';

export default function MoneyFlowTab({ data: countyData }: { data: CountyComprehensive }) {
  const { t } = useLang();

  // The year list used to come from /audits/fiscal-years — EVERY fiscal
  // period, including ones with no county budget data — and the default was
  // picked from it with getLatestReportedFiscalYear(), a label derived from
  // `new Date()`. In September 2026 that landed on FY2025/26, the CRA
  // equitable-share projection.
  //
  // It also chose independently of the page it sits on, so this tab could show
  // FY2025/26 while Budget & Debt two clicks away showed FY2024/25, for the
  // same county, with nothing saying they differed. The page's own resolved
  // year now leads; the reader's selection still wins over it.
  const { data: fiscalYearsMeta } = useCountyFiscalYears();
  const years = fiscalYearsMeta?.years.map((y) => y.label) ?? [];
  const [pickedYear, setPickedYear] = useState<string | undefined>(undefined);
  const selectedYear = moneyFlowDefaultYear(
    pickedYear,
    countyData.budget.fiscal_year ?? undefined,
    fiscalYearsMeta
  );

  // '' keeps the query disabled (useCountyMoneyFlow gates on !!year) until the
  // year list says which period to ask for — one fetch, for the right year.
  const { data, isLoading } = useCountyMoneyFlow(countyData.id, selectedYear ?? '');

  return (
    <div className='space-y-5'>
      {/* Section header — no nested card, just typography */}
      <div className='flex flex-col sm:flex-row sm:items-end justify-between gap-3 pb-1'>
        <div>
          <div className='flex items-center gap-2 mb-1'>
            <div className='h-6 w-1 rounded-full bg-gov-forest' />
            <h3 className='text-base font-semibold text-gray-900 dark:text-neutral-text'>
              {t('county.money.header_prefix')} · {countyData.name}
            </h3>
          </div>
          <p className='text-xs text-gray-500 dark:text-neutral-muted/80 ml-3'>
            {t('county.money.subtitle')}
            {selectedYear ? ` · ${selectedYear}` : ''}
          </p>
        </div>
        {/* No selector until the API says which years exist — an empty
            dropdown is a control claiming choices it does not have. */}
        {years.length > 0 && selectedYear && (
          <YearSelector value={selectedYear} onChange={setPickedYear} years={years} />
        )}
      </div>

      {/* The visualization itself renders its own cards — no wrapper */}
      <FollowTheMoney data={data} isLoading={isLoading} />
    </div>
  );
}
