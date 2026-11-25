'use client';

import { evidenceUrl } from '@/lib/evidence/qualification';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import type { AuditFinding, UnaccountedCase } from '@/types';
import { ChevronDown, ExternalLink } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState, type Ref } from 'react';
import styles from '../../CountyExperience.module.css';
import { severityTone, SignalMark } from '../../CountySignals';
import { fmtKES, SEVERITY_STYLE } from '../shared';

const FINDINGS_PER_BATCH = 20;
const EXCERPT_LIMIT = 180;

export const CATEGORY_LABELS = new Map<string, TranslationKey>([
  ['Financial Irregularity', 'county.audit.cat.financial_irregularity'],
  ['Asset Management', 'county.audit.cat.asset_management'],
  ['Missing Funds', 'county.audit.cat.missing_funds'],
  ['Procurement Issues', 'county.audit.cat.procurement'],
  ['Payroll Issues', 'county.audit.cat.payroll'],
  ['Revenue Collection', 'county.audit.cat.revenue_collection'],
  ['other', 'county.audit.cat.other'],
]);

export const STATUS_LABELS = new Map<string, TranslationKey>([
  ['under review', 'county.audit.status.under_review'],
  ['escalated', 'county.audit.status.escalated'],
  ['resolved', 'county.audit.status.resolved'],
  ['pending', 'county.audit.status.pending'],
  ['open', 'county.audit.status.open'],
]);

function findingPreview(text: string, sourceCase: UnaccountedCase | undefined) {
  if (sourceCase) {
    return { title: sourceCase.title, excerpt: sourceCase.excerpt };
  }

  const trimmed = text.trim();
  const line = /^([^\r\n]{5,104})\r?\n\s*\S/.exec(trimmed)?.[1];
  // Some reports store the heading and paragraph on one line. Reuse a lead
  // only where title-style words end at a clear opening phrase in the prose.
  const inlineLead = /^([^\r\n]{5,104}?)(?= (?:The|As|During|According|Review) [a-z])/.exec(trimmed)?.[1];
  const isTitleCase = (value: string) => /^[A-Z\d]/.test(value) && value.split(/\s+/).every(word =>
    /^[A-Z\d]/.test(word) || /^(?:a|an|and|at|by|for|from|in|of|on|or|the|to|with)$/.test(word));
  const title = line?.trim() || (inlineLead && isTitleCase(inlineLead) ? inlineLead : null);
  return { title, excerpt: title ? trimmed.slice(title.length).trimStart() : trimmed };
}

function FindingCard({ finding, sourceCase, focusHeading }: {
  finding: AuditFinding;
  sourceCase?: UnaccountedCase;
  focusHeading?: Ref<HTMLHeadingElement>;
}) {
  const { t } = useLang();
  const headingId = useId();
  const source = evidenceUrl(finding.source_url);
  const citedCase = source && source === evidenceUrl(sourceCase?.source.page_url) ? sourceCase : undefined;
  const { title, excerpt } = findingPreview(finding.finding, citedCase);
  const preview = excerpt.length <= EXCERPT_LIMIT ? excerpt
    : `${excerpt.slice(0, EXCERPT_LIMIT).replace(/\s+\S*$/, '')}…`;
  const tone = severityTone(finding.severity);
  const severity = SEVERITY_STYLE[finding.severity];
  const status = STATUS_LABELS.get(finding.status?.toLowerCase());
  const category = CATEGORY_LABELS.get(finding.category);
  const page = finding.page_ref;
  const pageLabel = page
    ? t('county.audit.source_page').replace('{page}', () => page)
    : t('county.audit.source_report');

  return (
    <article className={`${styles.signal} audit-panel space-y-2 p-3 sm:p-4`}
      aria-labelledby={headingId} data-tone={tone}>
      <div className='flex flex-wrap items-center justify-between gap-x-3 gap-y-1'>
        <p className='min-w-0 text-sm font-medium text-neutral-muted [overflow-wrap:anywhere]'>
          {finding.audited_entity_name || t('county.audit.institution_unavailable')}
        </p>
        {source && (
          <a href={source} target='_blank' rel='noopener noreferrer' aria-label={pageLabel}
            className='audit-receipt min-w-11 [overflow-wrap:anywhere]'>
            <span className={page ? 'font-mono' : undefined}>{page || pageLabel}</span>
            <ExternalLink size={14} aria-hidden='true' className='shrink-0' />
          </a>
        )}
      </div>
      <h4 id={headingId} ref={focusHeading} tabIndex={focusHeading ? -1 : undefined}
        className='scroll-mt-32 text-base font-semibold text-neutral-text [overflow-wrap:anywhere] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4'>
        {title || t('county.audit.finding_heading')}
      </h4>
      {preview && (
        <p className='line-clamp-2 whitespace-pre-line text-sm leading-relaxed text-neutral-muted [overflow-wrap:anywhere]'>
          {preview}
        </p>
      )}
      <div className='flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-neutral-muted [overflow-wrap:anywhere]'>
        {severity && (
          <span className={styles.severityCount}>
            <SignalMark tone={tone} />
            {t(finding.severity === 'critical' ? 'county.audit.serious_label' : severity.labelKey)}
          </span>
        )}
        {citedCase
          ? <span>{t('county.audit.unaccounted_label')}</span>
          : finding.category && finding.category !== 'other' && <span>{category ? t(category) : finding.category}</span>}
        {finding.status && <span>{status ? t(status) : finding.status}</span>}
        {finding.amount_involved > 0 && (
          <span className='font-semibold tabular-nums text-neutral-text'>{fmtKES(finding.amount_involved)}</span>
        )}
        {finding.audit_year && <span className='font-mono'>{t('county.audit.fy_prefix')} {finding.audit_year}</span>}
        {finding.reference && <span className='font-mono'>{t('county.audit.ref_prefix')} {finding.reference}</span>}
      </div>
      {(finding.finding.trim() || finding.recommendation) && (
        <details className='group border-t border-neutral-border'>
          <summary aria-describedby={headingId}
            className='flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 text-left text-sm font-semibold text-gov-forest focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 dark:text-neutral-text [&::-webkit-details-marker]:hidden'>
            {t('county.audit.read_words')}
            <ChevronDown size={16} aria-hidden='true' className='shrink-0 group-open:rotate-180' />
          </summary>
          <div className='space-y-3 pb-2 text-sm leading-relaxed text-neutral-text [overflow-wrap:anywhere]'>
            {finding.finding.trim() && <blockquote cite={source} className='whitespace-pre-wrap'>{finding.finding}</blockquote>}
            {finding.recommendation && (
              <div>
                <p className='font-semibold'>{t('county.audit.recommendation')}</p>
                <p className='whitespace-pre-wrap'>{finding.recommendation}</p>
              </div>
            )}
          </div>
        </details>
      )}
    </article>
  );
}

export default function CountyAuditFindingsList({ findings, sourceCases, title }: {
  findings: AuditFinding[];
  sourceCases: UnaccountedCase[];
  title: string;
}) {
  const { lang, t } = useLang();
  const headingId = useId();
  const listId = useId();
  const nextHeading = useRef<HTMLHeadingElement>(null);
  const [visibleLimit, setVisibleLimit] = useState(FINDINGS_PER_BATCH);
  const visible = findings.slice(0, visibleLimit);
  const total = findings.length;
  const shown = visible.length;
  const more = Math.min(FINDINGS_PER_BATCH, total - shown);
  const caseById = useMemo(() => new Map(sourceCases.map(item => [item.finding_id, item])), [sourceCases]);
  const format = (n: number) => n.toLocaleString(lang === 'sw' ? 'sw-KE' : 'en-KE');
  const countMessage = total === 1 ? 'county.audit.showing_one' : 'county.audit.showing_of';

  useEffect(() => {
    nextHeading.current?.focus();
  }, [visibleLimit]);

  return (
    <section aria-labelledby={headingId} className='min-w-0 space-y-3' data-county-audit-list>
      <h3 id={headingId} className='font-display text-xl text-neutral-text'>{title}</h3>
      {total === 0 ? (
        <p className='text-sm text-neutral-muted'>{t('county.audit.no_findings')}</p>
      ) : (
        <>
          <ul id={listId} className='min-w-0 space-y-3'>
            {visible.map((finding, index) => (
              <li key={finding.id}>
                <FindingCard finding={finding} sourceCase={caseById.get(finding.id)}
                  focusHeading={visibleLimit > FINDINGS_PER_BATCH && index === visibleLimit - FINDINGS_PER_BATCH
                    ? nextHeading : undefined} />
              </li>
            ))}
          </ul>
          <div className='flex flex-wrap items-center justify-between gap-x-3 gap-y-2'>
            <p role='status' className='text-sm text-neutral-muted'>
              {t(countMessage).replace('{shown}', format(shown)).replace('{total}', format(total))}
            </p>
            {more > 0 && (
              <button type='button' className='audit-control' aria-controls={listId}
                onClick={() => setVisibleLimit(limit => limit + FINDINGS_PER_BATCH)}>
                {t('county.audit.show_more').replace('{count}', format(more))}
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
