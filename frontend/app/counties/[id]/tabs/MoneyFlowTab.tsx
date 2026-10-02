'use client';

import styles from '../../CountyExperience.module.css';

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
import { AlertTriangle, Loader2 } from 'lucide-react';
import { useState, type ReactNode } from 'react';

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
  const fiscalYears = useCountyFiscalYears();
  const fiscalYearsMeta = fiscalYears.data;
  const years = fiscalYearsMeta?.years.map((y) => y.label) ?? [];
  const [pickedYear, setPickedYear] = useState<string | undefined>(undefined);
  const selectedYear = moneyFlowDefaultYear(
    pickedYear,
    countyData.budget.fiscal_year ?? undefined,
    fiscalYearsMeta
  );

  // '' keeps the query disabled (useCountyMoneyFlow gates on !!year) until the
  // year list says which period to ask for — one fetch, for the right year.
  const hasPeriod = !!selectedYear && years.includes(selectedYear);
  const moneyFlow = useCountyMoneyFlow(countyData.id, selectedYear ?? '', {
    enabled: fiscalYears.isSuccess && hasPeriod && !!countyData.id,
  });

  // Query pending includes the disabled state: it is not a successful empty read.
  // Keep discovery and transport failures separate from a report with no stages.
  let content: ReactNode;
  if (fiscalYears.isError) {
    content = (
      <ReadError
        message={t('county.money.years_error')}
        retrying={fiscalYears.isFetching}
        onRetry={() => { void fiscalYears.refetch({ cancelRefetch: false }); }}
      />
    );
  } else if (fiscalYears.isPending) {
    content = (
      <div role='status' className='flex items-center justify-center py-16'>
        <Loader2 aria-hidden='true' className='w-6 h-6 shrink-0 animate-spin text-gov-sage' />
        <span className='ml-3 text-sm text-gray-600 dark:text-neutral-muted'>{t('county.money.loading_years')}</span>
      </div>
    );
  } else if (!hasPeriod) {
    content = (
      <p role='status' className='py-12 text-center text-sm text-gray-600 dark:text-neutral-muted'>
        {t('county.money.years_unavailable')}
      </p>
    );
  } else if (moneyFlow.isError) {
    content = (
      <ReadError
        message={t('county.money.read_error')}
        retrying={moneyFlow.isFetching}
        onRetry={() => { void moneyFlow.refetch({ cancelRefetch: false }); }}
      />
    );
  } else {
    content = <FollowTheMoney data={moneyFlow.data} isLoading={moneyFlow.isPending} />;
  }

  return (
    <div className={styles.moneyReport}>
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
        {hasPeriod && selectedYear && (
          <YearSelector value={selectedYear} onChange={setPickedYear} years={years} />
        )}
      </div>

      {/* The visualization itself renders its own cards — no wrapper */}
      {content}
    </div>
  );
}

function ReadError({ message, retrying, onRetry }: {
  message: string;
  retrying: boolean;
  onRetry: () => void;
}) {
  const { t } = useLang();
  return (
    <div role='alert' aria-busy={retrying} className='py-12 text-center text-gray-700 dark:text-neutral-text'>
      <AlertTriangle aria-hidden='true' size={28} className='mx-auto mb-2 text-amber-600 dark:text-amber-400' />
      <p className='text-sm'>{message}</p>
      <button type='button' onClick={onRetry} disabled={retrying}
        className='mt-3 min-h-11 rounded-lg border border-gray-300 dark:border-white/20 px-4 py-2 text-sm font-medium hover:bg-gray-50 dark:hover:bg-white/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gov-forest disabled:opacity-60'>
        {t('county.money.retry')}
      </button>
    </div>
  );
}
