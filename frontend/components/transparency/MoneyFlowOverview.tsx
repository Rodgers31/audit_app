import { FileText, TriangleAlert } from 'lucide-react';
import {
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
}: {
  insights: MoneyFlowInsights;
  fiscalYear: string;
  projected: boolean;
}) {
  const flagged = !projected && insights.flagged != null && insights.flagged > 0;
  const AuditIcon = flagged ? TriangleAlert : FileText;
  return (
    <section
      className={`${styles.presentation} ${styles.overview}`}
      aria-labelledby='money-flow-overview'>
      <header className={styles.overviewHead}>
        <h2 id='money-flow-overview'>At a glance</h2>
        <p>FY {fiscalYear}</p>
      </header>
      <div className={styles.metrics}>
        <Metric
          label='Total allocated'
          value={formatFlowKES(insights.allocated)}
          note={`47 counties · FY ${fiscalYear}`}
          tone='allocation'
        />
        <Metric
          label={projected ? 'Spent so far' : 'Gap to spend'}
          value={projected ? 'Pending' : formatFlowKES(insights.gap)}
          note={
            projected
              ? 'Execution figures publish as the CoB releases quarterly CBIRRs'
              : insights.unspentPct != null
                ? `${insights.unspentPct.toFixed(1)}% of allocation unspent at report time`
                : 'Execution not yet published for this period'
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
          label='National efficiency'
          efficiency
          value={
            projected || insights.efficiency == null
              ? '—'
              : `${formatEfficiency(insights.efficiency)}%`
          }
          note={
            projected
              ? 'Calculated once CoB + OAG publish'
              : insights.efficiency == null
                ? 'Execution data pending'
                : insights.efficiency >= 70
                  ? 'Good — higher budget execution'
                  : insights.efficiency >= 50
                    ? 'Fair — needs improvement'
                    : 'Low — limited budget execution'
          }
          tone={efficiencyTone(projected ? null : insights.efficiency)}
        />
      </div>
      <div className={styles.auditStatus} data-tone={flagged ? 'low' : 'neutral'}>
        <AuditIcon size={23} aria-hidden='true' />
        <div>
          <h3 className={styles.auditLabel}>Questioned by Auditor General</h3>
          <p className={styles.auditValue}>
            {projected
              ? 'Not yet audited'
              : insights.flagged == null
                ? 'Not yet published'
                : formatFlowKES(insights.flagged)}
          </p>
        </div>
        <p className={styles.auditCopy}>
          {projected
            ? 'OAG audits close ~18 months after year-end'
            : insights.flagged == null
              ? 'No Auditor-General report for this year traces to a source document yet. This is not a finding that nothing was questioned.'
              : flagged
                ? "Amounts questioned in the Auditor-General's reports for this year — not proven loss or theft."
                : 'The published report questioned no amount for this period'}
        </p>
      </div>
    </section>
  );
}
