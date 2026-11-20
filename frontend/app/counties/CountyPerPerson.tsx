import { useLang } from '@/lib/i18n/LangProvider';
import type { publishedBudgetPerPerson } from '@/lib/counties/budgetPerPerson';
import styles from './CountyExperience.module.css';

type PerPersonAmount = NonNullable<ReturnType<typeof publishedBudgetPerPerson>>;

export type PerPersonMeasure = {
  amounts: ReadonlyMap<string, PerPersonAmount>;
  maximum: number;
};

const wholeShillings = new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 });

export function formatPerPerson(value: number): string {
  return `KES ${wholeShillings.format(Math.round(value))}`;
}

export function perPersonTone(value: number | undefined, maximum: number) {
  if (value == null) return 'unavailable';
  if (maximum <= 0) return 1;
  return Math.min(4, Math.floor(value / maximum * 4) + 1);
}

export function PerPersonLegend({ measure }: { measure: PerPersonMeasure }) {
  const { t } = useLang();
  return (
    <div className={styles.perPersonLegend} role='group' aria-label={t('counties.per_person.legend')}>
      {measure.amounts.size > 0 && (
        <div className={styles.perPersonScale}>
          <div className={styles.perPersonSwatches} aria-hidden='true'>
            {(measure.maximum > 0 ? [1, 2, 3, 4] : [1]).map((tone) => (
              <span key={tone} data-per-person-tone={tone} />
            ))}
          </div>
          <div className={styles.perPersonRange}>
            <span>{formatPerPerson(0)}</span>
            {measure.maximum > 0 && <span>{formatPerPerson(measure.maximum)}</span>}
          </div>
        </div>
      )}
      <p className={styles.perPersonMissing}>
        <i aria-hidden='true' data-per-person-tone='unavailable' />
        {t('counties.per_person.unavailable')}
      </p>
    </div>
  );
}

export function PerPersonSummary({ amount, fiscalYear }: {
  amount?: PerPersonAmount;
  fiscalYear?: string;
}) {
  const { t } = useLang();
  return (
    <div className={styles.perPersonSummary}>
      <dl className={styles.spendingSummary}>
        <div>
          <dt>{t('counties.per_person.measure')}{fiscalYear && ` · ${fiscalYear}`}</dt>
          <dd>{amount ? <strong>{formatPerPerson(amount.value)}</strong> : t('counties.per_person.unavailable')}</dd>
        </div>
      </dl>
      {amount && (
        <p className={styles.perPersonSources}>
          <a href={amount.budget.url}>{t('counties.per_person.budget_report')}</a>
          <span aria-hidden='true'> · </span>
          <a href={amount.censusSource.url}>
            {t('counties.per_person.census').replace('{year}', String(amount.censusYear))}
          </a>
        </p>
      )}
    </div>
  );
}
