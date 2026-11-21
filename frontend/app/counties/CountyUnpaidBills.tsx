import { formatUnpaidBills, type UnpaidBillsMeasure } from '@/lib/counties/explorerUnpaidBills';
import { formatAsAt, pendingBillsNoteLines } from '@/lib/counties/pendingBillsNotes';
import { useLang } from '@/lib/i18n/LangProvider';
import styles from './CountyExplorerUnpaidBills.module.css';
import layout from './CountyExperience.module.css';

export function UnpaidBillsDate({ asAt }: { asAt?: string }) {
  const { t, lang } = useLang();
  const date = formatAsAt(asAt, lang);
  return date
    ? <time dateTime={asAt}>{t('counties.unpaid_bills.date').replace('{date}', date)}</time>
    : t('counties.unpaid_bills.no_date');
}

export function UnpaidBillsLegend({ measure }: { measure: UnpaidBillsMeasure }) {
  const { t } = useLang();
  return (
    <div className={styles.legend} role='group' aria-label={t('counties.unpaid_bills.legend')}>
      {measure.amounts.size > 0 && (
        <div>
          <div className={styles.swatches} aria-hidden='true'>
            {(measure.maximum > 0 ? [1, 2, 3, 4] : [1]).map(tone => (
              <span key={tone} data-unpaid-bills-tone={tone} />
            ))}
          </div>
          <div className={styles.range}>
            <span>{formatUnpaidBills(0)}</span>
            {measure.maximum > 0 && <span>{formatUnpaidBills(measure.maximum)}</span>}
          </div>
        </div>
      )}
      <p className={styles.missing}>
        <i aria-hidden='true' data-unpaid-bills-tone='unavailable' />
        {t('counties.unpaid_bills.unavailable')}
      </p>
    </div>
  );
}

export function UnpaidBillsSource({ sourceUrl, sourceTable }: {
  sourceUrl: string;
  sourceTable?: string | null;
}) {
  const { t } = useLang();
  return (
    <a className={styles.source} href={sourceUrl}>{t('counties.unpaid_bills.source')}{sourceTable && ` · ${sourceTable}`}</a>
  );
}

export function UnpaidBillsSummary({ measure, countyId }: { measure: UnpaidBillsMeasure; countyId: string }) {
  const { t } = useLang();
  const amount = measure.amounts.get(countyId);
  const notes = pendingBillsNoteLines(amount?.notes, t, formatUnpaidBills);
  return (
    <div className={styles.summary}>
      <dl className={layout.spendingSummary}>
        <div>
          <dt>{t('counties.unpaid_bills.measure')} · <UnpaidBillsDate asAt={measure.asAt} /></dt>
          <dd>{amount ? <strong>{formatUnpaidBills(amount.value)}</strong> : t('counties.unpaid_bills.unavailable')}</dd>
        </div>
      </dl>
      {amount && <p><UnpaidBillsSource sourceUrl={amount.sourceUrl} sourceTable={amount.sourceTable} /></p>}
      {notes.map(note => <p key={note} className={styles.qualification}>{note}</p>)}
    </div>
  );
}
