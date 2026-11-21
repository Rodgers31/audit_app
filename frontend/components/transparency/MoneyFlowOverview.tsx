'use client';

import { FileText, TriangleAlert } from 'lucide-react';
import { useLang } from '@/lib/i18n/LangProvider';
import {
  auditAmountCoverageNote,
  efficiencyTone,
  formatEfficiency,
  formatFlowKES,
  type FlowTone,
  type MoneyFlowInsights,
} from './moneyFlowPresentation';
import styles from './MoneyFlowPresentation.module.css';

function Metric({
  label,
  value,
  note,
  tone,
  efficiency = false,
}: {
  label: string;
  value: string;
  note: string;
  tone: FlowTone;
  efficiency?: boolean;
}) {
  const money = value.startsWith('KES ');
  return (
    <div
      className={`${styles.metric} ${efficiency ? styles.efficiencyMetric : ''}`}
      data-tone={tone}>
      <h3 className={styles.metricLabel}>{label}</h3>
      <p className={styles.metricValue}>
        {money && <small>KES </small>}
        {money ? value.slice(4) : value}
      </p>
      <p className={styles.metricNote}>{note}</p>
    </div>
  );
}

export default function MoneyFlowOverview({
  insights,
  fiscalYear,
  projected,
  auditOnly = false,
  auditAbsenceExplained = false,
}: {
  insights: MoneyFlowInsights;
  fiscalYear: string;
  projected: boolean;
  auditOnly?: boolean;
  auditAbsenceExplained?: boolean;
}) {
  const { t, lang } = useLang();
  const flagged = !projected && insights.flagged != null && insights.flagged > 0;
  const AuditIcon = flagged ? TriangleAlert : FileText;
  const AuditHeading = auditOnly ? 'h2' : 'h3';
  const coverageNote = auditAmountCoverageNote(insights.audit_amount_coverage, lang);
  if (auditOnly && insights.flagged == null && auditAbsenceExplained) return null;
  return (
    <section
      className={auditOnly ? styles.presentation : `${styles.presentation} ${styles.overview}`}
      aria-labelledby={auditOnly ? 'national-audit-amount' : 'money-flow-overview'}>
      {!auditOnly && (
        <>
          <header className={styles.overviewHead}>
            <h2 id='money-flow-overview'>{t('transparency.overview.title')}</h2>
            <p>FY {fiscalYear}</p>
          </header>
          <div className={styles.metrics}>
            <Metric
              label={t('transparency.overview.allocated')}
              value={formatFlowKES(insights.allocated)}
              note={`${t('transparency.overview.counties')} · FY ${fiscalYear}`}
              tone='allocation'
            />
            <Metric
              label={t(projected ? 'transparency.overview.spent' : 'transparency.overview.gap')}
              value={projected ? t('transparency.overview.pending') : formatFlowKES(insights.gap)}
              note={
                projected
                  ? t('transparency.overview.execution_pending')
                  : insights.unspentPct != null
                    ? t('transparency.overview.unspent').replace(
                        '{percent}',
                        insights.unspentPct.toFixed(1)
                      )
                    : t('transparency.overview.execution_unavailable')
              }
              tone={
                projected || insights.gap == null
                  ? 'neutral'
                  : insights.gap > 0
                    ? 'fair'
                    : insights.gap === 0
                      ? 'good'
                      : 'low'
              }
            />
            <Metric
              label={t('transparency.overview.efficiency')}
              efficiency
              value={
                projected || insights.efficiency == null
                  ? t('transparency.overview.not_published')
                  : `${formatEfficiency(insights.efficiency)}%`
              }
              note={
                projected
                  ? t('transparency.overview.efficiency_pending')
                  : insights.efficiency == null
                    ? t('transparency.overview.execution_unavailable')
                    : insights.efficiency >= 70
                      ? t('transparency.overview.good')
                      : insights.efficiency >= 50
                        ? t('transparency.overview.fair')
                        : t('transparency.overview.low')
              }
              tone={efficiencyTone(projected ? null : insights.efficiency)}
            />
          </div>
        </>
      )}
      <div className={styles.auditStatus} data-tone={flagged ? 'low' : 'neutral'}>
        <AuditIcon size={23} aria-hidden='true' />
        <div>
          <AuditHeading
            id={auditOnly ? 'national-audit-amount' : undefined}
            className={styles.auditLabel}>
            {t(auditOnly ? 'transparency.overview.national_questioned' : 'transparency.overview.questioned')}
          </AuditHeading>
          <p className={styles.auditValue}>
            {projected
              ? t('transparency.overview.not_audited')
              : insights.flagged == null
                ? t('transparency.overview.not_published')
                : formatFlowKES(insights.flagged)}
          </p>
        </div>
        <div className={styles.auditCopy}>
          {coverageNote && <p>{coverageNote}</p>}
          {flagged ? (
            <p>{t('transparency.overview.audit_positive')}</p>
          ) : !coverageNote && (
            <p>{t(projected
              ? 'transparency.overview.audit_pending'
              : insights.flagged == null
                ? 'transparency.overview.audit_unavailable'
                : 'transparency.overview.audit_zero')}</p>
          )}
        </div>
      </div>
    </section>
  );
}
