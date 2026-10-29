'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import { borrowingCoverageKey, borrowingSources, type BorrowingCoverage } from '@/lib/countyBorrowingCoverage';

export default function CountyBorrowingNote({ balance, absentReason, coverage, asAt }: {
  balance: number | null | undefined;
  absentReason?: string | null;
  coverage?: BorrowingCoverage;
  asAt?: string | null;
}) {
  const { t } = useLang();
  return (
    <div role='note' className='mt-2 text-xs leading-relaxed text-gray-600 dark:text-neutral-muted'>
      <p>{t(borrowingCoverageKey(balance, absentReason, coverage, asAt))}</p>
      {borrowingSources(coverage).map((source, index) => (
        <div key={`${source.url}-${index}`}>
          <a href={source.url} target='_blank' rel='noopener noreferrer'
            className='mr-3 underline underline-offset-2'>
            {t('county.borrowing.checked_source')} {index + 1} (PDF {source.pdf_pages.join(', ')})
          </a>
          {source.reporting_period_end && <span className='mr-3'>
            {t('county.borrowing.report_period_ended')}: <time dateTime={source.reporting_period_end}>{source.reporting_period_end}</time>
          </span>}
          {source.scope_reviewed_on && <span>
            {t('county.borrowing.scope_reviewed')}: <time dateTime={source.scope_reviewed_on}>{source.scope_reviewed_on}</time>
          </span>}
        </div>
      ))}
    </div>
  );
}
