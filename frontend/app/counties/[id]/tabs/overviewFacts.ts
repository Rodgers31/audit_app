import { evidenceUrl } from '@/lib/evidence/qualification';
import type { CountyComprehensive } from '@/types';

type BudgetObservation = CountyComprehensive['budget'] & {
  accounting_basis?: string | null;
  fiscal_period?: { label?: string; start_date?: string; end_date?: string } | null;
  sources?: Array<{ publisher?: string; title?: string; url?: string }>;
};

export interface OverviewSource {
  href: string;
  title?: string;
  publisher?: string;
}

function finiteAmount(n: unknown): n is number {
  return typeof n === 'number' && Number.isFinite(n) && n >= 0;
}

function fiscalYearName(label: string | null | undefined) {
  return label?.trim().replace(/^FY\s*/i, '').replace(/\s+/g, ' ').toUpperCase();
}

function annualPeriod(period: BudgetObservation['fiscal_period']) {
  const year = fiscalYearName(period?.label);
  const match = year && /^(\d{4})\/(\d{2}|\d{4})$/.exec(year);
  if (!period || !match) return null;
  const start = Number(match[1]);
  const end = start + 1;
  const endDate = `${end}-06-30`;
  return Number(match[2]) === (match[2].length === 2 ? end % 100 : end)
    && period.start_date?.slice(0, 10) === `${start}-07-01`
    && period.end_date?.slice(0, 10) === endDate ? endDate : null;
}

export function countyOverviewFacts(data: CountyComprehensive) {
  const budget: BudgetObservation = data.budget;
  const { debt, audit, financial_summary: summary } = data;
  const { fiscal_period: period, total_allocated: allocated, total_spent: spent, utilization_rate: rate } = budget;
  const budgetSources: OverviewSource[] = (Array.isArray(budget.sources) ? budget.sources : []).flatMap(source => {
    const href = evidenceUrl(source?.url);
    return href ? [{ href, title: source.title, publisher: source.publisher }] : [];
  }).filter((source, index, sources) => sources.findIndex(item => item.href === source.href) === index);
  const periodLabel = period?.label || budget.fiscal_year || null;
  const matchedPeriod = Boolean(period?.label && period.start_date && period.end_date
    && period.start_date <= period.end_date
    && (!budget.fiscal_year || fiscalYearName(budget.fiscal_year) === fiscalYearName(period.label)));
  const annualEnd = matchedPeriod ? annualPeriod(period) : null;
  const partYear = /(?:\s[369]M|\sQ[1-4])$/i.test(periodLabel ?? '');

  // The county account publishes one period and one source document, using
  // an official total or both classification components.
  const publishedBudget = matchedPeriod && budget.sources?.length === 1 && budgetSources.length === 1
    && (budget.accounting_basis === 'reported_total' || budget.accounting_basis === 'recurrent_plus_development')
    && (budget.source == null || budget.source === 'cob_cbirr');
  const spending = publishedBudget
    && finiteAmount(allocated) && allocated > 0 && finiteAmount(spent) && finiteAmount(rate)
    && Math.abs(rate - spent / allocated * 100) <= 0.051
    ? { allocated, spent, rate, annual: annualEnd != null, partYear }
    : null;

  const pendingSource = debt.pending_bills_source;
  const pendingHref = evidenceUrl(pendingSource?.url);
  const pending = finiteAmount(debt.pending_bills) && pendingHref && debt.pending_bills_as_at
    ? {
        amount: debt.pending_bills, asAt: debt.pending_bills_as_at, table: pendingSource?.table,
        source: { href: pendingHref, title: pendingSource?.title, publisher: pendingSource?.publisher },
      }
    : null;
  const ratio = summary.pending_bills_ratio;
  // This API field is withheld until its own pending-budget period/currency
  // gate passes. A matching annual end and arithmetic ensure this payload's
  // rendered allocation is the same denominator.
  const pendingShare = pending && publishedBudget && annualEnd === pending.asAt
    && finiteAmount(allocated) && allocated > 0 && finiteAmount(ratio)
    && Math.abs(ratio - pending.amount / allocated * 100) <= 0.051
    ? { rate: ratio, allocated }
    : null;

  const total = audit.findings_count;
  const findings = audit.findings ?? [];
  const reportedSeverity = audit.by_severity;
  const grouped = findings.reduce<Record<string, number>>((counts, finding) => {
    if (finding.severity === 'info' || finding.severity === 'warning' || finding.severity === 'critical') {
      counts[finding.severity] = (counts[finding.severity] ?? 0) + 1;
    }
    return counts;
  }, {});
  const fullyCited = findings.every(finding => evidenceUrl(finding.source_url) && finding.page_ref?.trim());
  const allRows = Number.isSafeInteger(total) && total > 0 && total === findings.length
    && new Set(findings.map(finding => finding.id)).size === total;
  const reconciled = reportedSeverity && Object.values(grouped).reduce((sum, n) => sum + n, 0) === total
    && Object.values(reportedSeverity).every(n => Number.isSafeInteger(n) && n >= 0)
    && Object.values(reportedSeverity).reduce((sum, n) => sum + n, 0) === total
    && ['info', 'warning', 'critical'].every(key => (reportedSeverity[key] ?? 0) === (grouped[key] ?? 0));
  const citedFinding = findings.find(finding => finding.severity === 'critical') ?? findings[0];
  const auditHref = evidenceUrl(citedFinding?.source_url);
  const years = findings.map(finding => String(finding.audit_year ?? ''));
  const recordedYears = years.length && years.every(year => /^\d{4}$/.test(year) && Number(year) >= 1900)
    ? years.map(Number).sort((a, b) => a - b) : [];
  const auditPeriod = recordedYears.length
    ? { start: recordedYears[0], end: recordedYears[recordedYears.length - 1] } : null;
  const findingCounts = allRows && fullyCited && reconciled && auditHref
    ? { serious: grouped.critical ?? 0, total, source: { href: auditHref }, period: auditPeriod }
    : null;

  return { periodLabel, budgetSources, spending, pending, pendingShare, findingCounts };
}
