'use client';

import InfoSheet from '@/components/ui/InfoSheet';
import { borrowingCoverageKey, borrowingSources } from '@/lib/countyBorrowingCoverage';
import { formatAsAt, pendingBillsAbsenceLine, pendingBillsAsAtLine, pendingBillsNoteLines } from '@/lib/counties/pendingBillsNotes';
import { evidenceUrl } from '@/lib/evidence/qualification';
import { useLang } from '@/lib/i18n/LangProvider';
import { COUNTY_COMPARE_MESSAGES as messages } from '@/lib/i18n/messages/countyCompare';
import { fmtKES } from '@/lib/utils';
import { Info } from 'lucide-react';
import { debtAmount, reported, type CountySummary } from './ledgerData';

export default function CompareDebtInfo({ counties }: { counties: CountySummary[] }) {
  const { lang, t } = useLang();
  const title = messages.debtTitle[lang];
  return (
    <InfoSheet title={title} trigger={(props) => (
      <button {...props} type='button' aria-label={title} className='audit-control size-11 shrink-0 border-transparent px-0 text-neutral-muted motion-reduce:transition-none'
        onClick={(event) => {
          event.currentTarget.focus();
          props.onClick();
        }}>
        <Info aria-hidden='true' size={24} />
      </button>
    )}>
      <p>{messages.debtContext[lang]}</p>
      {counties.map((county) => {
        const debt = debtAmount(county);
        const date = debt === null ? null : formatAsAt(county.debt_as_at, lang);
        const pending = reported(county.pending_bills);
        const source = county.pending_bills_source;
        const pendingLine = pending === null
          ? pendingBillsAbsenceLine(county.pending_bills_absence, lang, t)
          : pendingBillsAsAtLine(county.pending_bills_as_at, source?.table, lang, t);
        const pendingUrl = pending === null ? undefined : evidenceUrl(source?.url);
        const pendingNotes = pending === null ? [] : pendingBillsNoteLines(county.pending_bills_notes, t, fmtKES);
        return (
          <section key={county.id} className='space-y-1 border-t border-neutral-border pt-3'>
            <h3 className='text-base font-semibold'>{county.name}</h3>
            <p>{t(borrowingCoverageKey(debt, county.total_debt_absent_reason, county.debt_source_coverage, county.debt_as_at))}</p>
            {date && <p>{messages.debtDate[lang].replace('{date}', date)}</p>}
            {borrowingSources(county.debt_source_coverage).map((item, index) => (
              <a key={`${item.url}-${index}`} href={item.url} target='_blank' rel='noopener noreferrer'
                className='flex min-h-11 items-center underline underline-offset-4'>
                {t('county.borrowing.checked_source')} {index + 1} (PDF {item.pdf_pages.join(', ')})
              </a>
            ))}
            <p>
              <strong>{t('compare.row.pending_bills')}</strong>{' '}
              {pending === null ? messages.missing[lang] : fmtKES(pending)}
            </p>
            {pendingLine && <p>{pendingLine}</p>}
            {pendingNotes.map((note) => <p key={note}>{note}</p>)}
            {pendingUrl && (
              <a href={pendingUrl} target='_blank' rel='noopener noreferrer' className='flex min-h-11 items-center underline underline-offset-4'>
                {source?.title || t('evidence.open_source')}
              </a>
            )}
          </section>
        );
      })}
    </InfoSheet>
  );
}
