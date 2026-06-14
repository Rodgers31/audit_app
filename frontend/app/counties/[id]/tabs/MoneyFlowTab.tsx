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
import { useAvailableFiscalYears } from '@/lib/react-query';
import { useCountyMoneyFlow } from '@/lib/react-query/useMoneyFlow';
import { generateFiscalYears, getLatestReportedFiscalYear } from '@/lib/utils';
import { CountyComprehensive } from '@/types';
import { useEffect, useState } from 'react';

const DEFAULT_FISCAL_YEARS = generateFiscalYears();

/** Resolve the best default year from the available list. Backend
 * sometimes prefixes years with "FY" and sometimes not — we match
 * either form. Falls back to the first list item, or to the util
 * helper if the list is completely empty. */
function pickDefaultYear(years: string[]): string {
  const latestReported = getLatestReportedFiscalYear();
  return (
    years.find((y) => y === latestReported || y === `FY${latestReported}`) ||
    years[1] /* first completed FY in a desc-sorted list */ ||
    years[0] ||
    latestReported
  );
}

export default function MoneyFlowTab({ data: countyData }: { data: CountyComprehensive }) {
  const { t } = useLang();
  const { data: fiscalYears } = useAvailableFiscalYears();
  const years = fiscalYears && fiscalYears.length > 0 ? fiscalYears : DEFAULT_FISCAL_YEARS;

  // Default to the latest *reported* FY, not the in-progress one —
  // money-flow aggregates need actuals, which aren't published until
  // well after year-end. Previously this defaulted to `FY2025/26` in
  // April 2026 and the tab showed "No money flow data for this period".
  const [selectedYear, setSelectedYear] = useState(() => pickDefaultYear(years));

  // `useAvailableFiscalYears` often resolves AFTER the first render, so
  // the initial `selectedYear` was picked from the fallback list — which
  // can use a different format (`2024/25` vs `FY2024/25`). Reconcile
  // once the real list arrives so the visible `<select>` highlights the
  // right option and the query key matches a cached backend response.
  useEffect(() => {
    if (!fiscalYears || fiscalYears.length === 0) return;
    if (fiscalYears.includes(selectedYear)) return;
    setSelectedYear(pickDefaultYear(fiscalYears));
    // Only reconcile on list change — user selections stand.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fiscalYears]);

  const { data, isLoading } = useCountyMoneyFlow(countyData.id, selectedYear);

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
            {t('county.money.subtitle')} · {selectedYear}
          </p>
        </div>
        <YearSelector value={selectedYear} onChange={setSelectedYear} years={years} />
      </div>

      {/* The visualization itself renders its own cards — no wrapper */}
      <FollowTheMoney data={data} isLoading={isLoading} />
    </div>
  );
}
