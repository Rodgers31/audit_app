'use client';

import { evidenceUrl } from '@/lib/evidence/qualification';
import type { MoneyFlowData } from '@/types';
import { ChevronDown } from 'lucide-react';
import { useLang } from '@/lib/i18n/LangProvider';
import { nationalSpendingMessages as messages } from '@/lib/i18n/messages/transparency';
import {
  formatEfficiency,
  formatFlowKES,
  isProjectedMoneyFlow,
} from './moneyFlowPresentation';
import styles from './MoneyFlowPresentation.module.css';

function barePeriod(year: string) {
  return year.replace(/^FY\s*/i, '').trim();
}

function nationalAmount(data: MoneyFlowData | null | undefined, stageName: string) {
  const stage = data?.stages?.find((entry) => entry.stage === stageName);
  const amount = stage?.amount;
  return amount != null && Number.isFinite(amount) && !stage?.data_unavailable ? amount : null;
}

function headlineShare(share: number) {
  const rounded = Math.round(share);
  if (rounded === 0 && share > 0) return '<1%';
  if (rounded === 100 && share !== 100) return share < 100 ? '<100%' : '>100%';
  return `${formatEfficiency(rounded)}%`;
}

export default function MoneyFlowHero({
  data,
  selectedYear = data?.fiscal_year ?? '',
}: {
  data: MoneyFlowData | null | undefined;
  selectedYear?: string;
}) {
  const { lang } = useLang();
  const copy = (key: keyof typeof messages, values: Record<string, string | number> = {}) =>
    messages[key][lang].replace(/\{(\w+)\}/g, (match, name) => String(values[name] ?? match));
  const year = barePeriod(selectedYear);
  if (!year) return null;

  const samePeriod = data && barePeriod(data.fiscal_year) === year ? data : null;
  const allocated = nationalAmount(samePeriod, 'Allocated');
  const spent = nationalAmount(samePeriod, 'Spent');
  const budgetSource = samePeriod?.budget_source;
  const projected = isProjectedMoneyFlow(samePeriod);

  // The national API supplies this URL only for a single source across the county
  // totals. Each county's allocation and spending use the same reported rows.
  const reportURL =
    budgetSource === 'cob_cbirr' ? evidenceUrl(samePeriod?.source_document_url) : null;
  const share =
    reportURL && allocated != null && allocated > 0 && spent != null && spent >= 0
      ? (spent / allocated) * 100
      : null;
  const remaining = share != null && allocated != null && spent != null ? allocated - spent : null;
  const hasAmount = allocated != null || spent != null;
  const allocationLabel =
    budgetSource === 'cra_model' ? 'estimate' : budgetSource === 'mixed' ? 'mixedAllocation' : 'allocation';
  const sourceKey =
    budgetSource === 'cob_cbirr' ? 'cob' : budgetSource === 'cra_model' ? 'craModel' : budgetSource;
  const sourceNote = share != null ? 'method' : allocated != null ? sourceKey : null;
  const compactAmount = (amount: number | null) => formatFlowKES(amount).replace('KES ', 'KES\u00a0');
  const exactAmount = (amount: number) =>
    `KES ${amount.toLocaleString(lang === 'sw' ? 'sw-KE' : 'en-KE', { maximumFractionDigits: 2 })}`;
  let comparisonNote: keyof typeof messages = 'noComparison';
  if (allocated === 0) comparisonNote = 'zeroAllocation';
  else if (allocated == null) comparisonNote = 'allocationUnavailable';
  else if (spent == null) comparisonNote = 'spendingUnavailable';

  return (
    <section className={`${styles.presentation} ${styles.flow}`} aria-labelledby='money-flow-verdict'>
      <p className={styles.sourceLabel}>{copy('period', { year })}</p>
      {share != null && remaining != null ? (
        <>
          <h2 id='money-flow-verdict' className={styles.flowTitle}>
            <strong>{copy('verdict', { percent: headlineShare(share) })}</strong>{' '}
            {copy('comparison', {
              spent: compactAmount(spent),
              allocated: compactAmount(allocated),
            })}
          </h2>
          <div className={styles.spendingFlow} aria-hidden='true' data-testid='national-spending-flow'>
            <span className={styles.spentSegment} style={{ width: `${Math.min(share, 100)}%` }}>
              <span className={styles.segmentLabel}>
                {copy('spentSegment', { amount: formatFlowKES(spent).slice(4) })}
              </span>
            </span>
            {remaining > 0 && (
              <span className={styles.remainingSegment} style={{ width: `${100 - share}%` }}>
                <span className={styles.segmentLabel}>{formatFlowKES(remaining).slice(4)}</span>
              </span>
            )}
          </div>
          <p className={styles.flowDescription}>
            {copy(remaining < 0 ? 'overspend' : 'remaining', { amount: compactAmount(Math.abs(remaining)) })}
          </p>
        </>
      ) : (
        <>
          <h2 id='money-flow-verdict' className={styles.flowTitle}>
            {copy(projected ? 'projected' : hasAmount ? 'reported' : 'unavailable')}
          </h2>
          {hasAmount && (
            <dl className={styles.flowAmounts}>
              {allocated != null && (
                <div>
                  <dt>{copy(allocationLabel)}</dt>
                  <dd>{formatFlowKES(allocated)}</dd>
                </div>
              )}
              {spent != null && (
                <div>
                  <dt>{copy('spending')}</dt>
                  <dd>{formatFlowKES(spent)}</dd>
                </div>
              )}
            </dl>
          )}
          {hasAmount && <p className={styles.flowDescription}>{copy(comparisonNote)}</p>}
        </>
      )}
      {(reportURL || sourceNote) && (
        <details className={styles.flowSource} key={year}>
          <summary>
            {copy('source')}
            <ChevronDown size={16} aria-hidden='true' />
          </summary>
          {sourceNote && <p>{copy(sourceNote)}</p>}
          {share != null && allocated != null && spent != null && (
            <dl className={styles.sourceAmounts}>
              <div>
                <dt>{copy('allocation')}</dt>
                <dd>{exactAmount(allocated)}</dd>
              </div>
              <div>
                <dt>{copy('spending')}</dt>
                <dd>{exactAmount(spent)}</dd>
              </div>
            </dl>
          )}
          {reportURL && (
            <a href={reportURL} target='_blank' rel='noopener noreferrer'>
              {samePeriod?.source_document_title || copy('reportLink')}
            </a>
          )}
        </details>
      )}
    </section>
  );
}
