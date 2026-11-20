import type { FindingDetailItem } from '@/lib/api/audits';
import type { Lang } from '@/lib/i18n/messages';
import { AUDITS_MESSAGES, auditSectionLabel } from '@/lib/i18n/messages/audits';
import { ArrowDown, ArrowUp, ExternalLink, FileText, MoveVertical, X } from 'lucide-react';
import Link from 'next/link';
import { useId, useLayoutEffect, useRef, useState } from 'react';
import { FINDING_SEVERITY } from './auditFindingPresentation';

type AuditCopy = (key: keyof typeof AUDITS_MESSAGES) => string;
type SortColumn = 'finding' | 'year';
type Sort = { column: SortColumn; direction: 'ascending' | 'descending' };
const SORTABLE_COLUMNS = [
  { column: 'finding', label: 'audits.finding' },
  { column: 'year', label: 'audits.year' },
] as const;

function findingName(finding: FindingDetailItem) {
  return finding.finding_title || finding.finding_text;
}

function byCurrentPage(items: FindingDetailItem[], sort: Sort | null, lang: Lang) {
  if (!sort) return items;
  const direction = sort.direction === 'ascending' ? 1 : -1;
  const collator = new Intl.Collator(lang === 'sw' ? 'sw-KE' : 'en-KE');
  return [...items].sort((left, right) => {
    if (sort.column === 'finding') return direction * collator.compare(findingName(left), findingName(right));
    // Findings without a recorded year remain at the end in both directions.
    if (left.audit_year == null) return right.audit_year == null ? 0 : 1;
    if (right.audit_year == null) return -1;
    return direction * (left.audit_year - right.audit_year);
  });
}

function FindingSeverity({ severity, copy }: { severity: string; copy: AuditCopy }) {
  const presentation = FINDING_SEVERITY[severity.toLowerCase()];
  return <span className={presentation?.tone ?? 'text-neutral-text'}>
    {presentation ? copy(presentation.label) : severity || copy('audits.unavailable')}
  </span>;
}

function FindingSourceLink({ finding, copy, iconOnly }: {
  finding: FindingDetailItem; copy: AuditCopy; iconOnly?: boolean;
}) {
  if (!finding.source_document_url) return null;
  const name = [copy('audits.source_report'), finding.page_ref].filter(Boolean).join(' · ');
  return (
    <a href={finding.source_document_url} target='_blank' rel='noopener noreferrer'
      aria-label={iconOnly ? name : undefined} title={iconOnly ? name : undefined}
      className={iconOnly ? 'audit-receipt min-w-11 justify-center' : 'audit-receipt'}>
      {iconOnly ? <FileText size={16} aria-hidden='true' /> : <>
        <span className='min-w-0'>{name}</span>
        <ExternalLink size={14} className='shrink-0' aria-hidden='true' />
      </>}
    </a>
  );
}

function FindingDetailPane({ finding, copy, lang, id, onClose }: {
  finding: FindingDetailItem; copy: AuditCopy; lang: Lang; id: string; onClose: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useLayoutEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, [finding.id]);

  const confidence = finding.confidence_score;
  const confidenceLabel = typeof confidence === 'number' && confidence >= 0 && confidence <= 1
    ? new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE', { style: 'percent', maximumFractionDigits: 1 }).format(confidence)
    : null;
  const extraText = [
    ['audits.finding_recommendation', finding.recommended_action],
    ['audits.finding_response', finding.management_response],
    ['audits.finding_follow_up', finding.follow_up_status],
  ] as const;
  const amount = finding.amount != null && Number.isFinite(finding.amount)
    ? `KES ${new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE', { maximumFractionDigits: 2 }).format(finding.amount)}`
    : copy('audits.not_stated');

  return (
    <aside id={id} aria-labelledby={`${id}-heading`} data-audit-finding-pane
      className='audit-panel min-w-0 max-h-[calc(100dvh-var(--public-header-height)-2rem)] overflow-y-auto px-4 pb-4 text-sm leading-relaxed [overflow-wrap:anywhere] lg:sticky lg:top-[calc(var(--public-header-height)+1rem)] lg:self-start xl:px-5 xl:pb-5'>
      <div className='sticky top-0 flex min-w-0 items-start justify-between gap-2 border-b border-neutral-border bg-surface-base py-3'>
        <h3 ref={heading} id={`${id}-heading`} tabIndex={-1}
          className='min-w-0 self-center font-display text-2xl font-semibold leading-tight text-neutral-text'>
          {finding.finding_title || copy('audits.finding_details')}
        </h3>
        <button type='button' className='audit-control min-w-11 shrink-0 !px-0'
          onClick={onClose} aria-label={copy('audits.close_finding')}>
          <X size={18} aria-hidden='true' />
        </button>
      </div>
      <div className='space-y-4 pt-3'>
        <p className='text-neutral-muted'>
          {finding.audited_entity_name || copy('audits.institution_not_identified')}
          {finding.audit_year != null && <> · <span className='font-mono'>{finding.audit_year}</span></>}
        </p>
        <p className='max-w-[70ch] whitespace-pre-line text-neutral-text'>{finding.finding_text}</p>
        <dl className='grid gap-x-4 gap-y-3 border-y border-neutral-border py-3 xl:grid-cols-2'>
          <div>
            <dt className='font-semibold'>{copy('audits.severity')}</dt>
            <dd><FindingSeverity severity={finding.severity} copy={copy} /></dd>
          </div>
          <div>
            <dt className='font-semibold'>{copy('audits.finding_amount_mentioned')}</dt>
            <dd>{amount}</dd>
          </div>
          <div>
            <dt className='font-semibold'>{copy('audits.section')}</dt>
            <dd>{finding.query_type ? auditSectionLabel(finding.query_type, lang) : copy('audits.not_stated')}</dd>
          </div>
          <div>
            <dt className='font-semibold'>{copy('audits.status')}</dt>
            <dd>{finding.status || copy('audits.not_stated')}</dd>
          </div>
          <div>
            <dt className='font-semibold'>{copy('audits.opinion')}</dt>
            <dd>{finding.audit_opinion || copy('audits.not_stated')}</dd>
          </div>
          {finding.county_name && finding.county_slug && (
            <div>
              <dt className='font-semibold'>{copy('audits.finding_county')}</dt>
              <dd><Link className='audit-receipt' href={`/counties/${encodeURIComponent(finding.county_slug)}`}>{finding.county_name}</Link></dd>
            </div>
          )}
          {confidenceLabel && (
            <div className='xl:col-span-2'>
              <dt className='font-semibold'>{copy('audits.extraction_confidence')}</dt>
              <dd>{confidenceLabel} · {copy('audits.extraction_confidence_scope')}</dd>
            </div>
          )}
        </dl>
        {extraText.map(([label, value]) => value && (
          <div key={label}>
            <h4 className='font-semibold'>{copy(label)}</h4>
            <p className='max-w-[70ch] whitespace-pre-line'>{value}</p>
          </div>
        ))}
        {finding.source_document_url
          ? <FindingSourceLink finding={finding} copy={copy} />
          : <p className='text-neutral-muted'>{copy('audits.finding_source_unavailable')}</p>}
      </div>
    </aside>
  );
}

export default function AuditFindingsDesktop({ items, lang }: { items: FindingDetailItem[]; lang: Lang }) {
  const copy: AuditCopy = key => AUDITS_MESSAGES[key][lang];
  const paneId = useId();
  const rowTrigger = useRef<HTMLButtonElement>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [sort, setSort] = useState<Sort | null>(null);
  const selected = items.find(finding => finding.id === selectedId);
  const rows = byCurrentPage(items, sort, lang);

  function closeFinding() {
    setSelectedId(null);
    rowTrigger.current?.focus();
  }

  return (
    <div data-audit-desktop-findings className={`hidden min-w-0 gap-4 lg:grid ${selected ? 'lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]' : ''}`}
      onKeyDown={event => {
        if (event.key === 'Escape' && selected && !event.defaultPrevented) {
          event.preventDefault();
          closeFinding();
        }
      }}>
      <table className='w-full min-w-0 table-fixed self-start border-separate border-spacing-0 rounded border border-neutral-border bg-surface-base text-left text-sm text-neutral-text [overflow-wrap:anywhere]'>
        <caption className='sr-only'>{copy('audits.all_findings')}</caption>
        <thead className='sticky top-[var(--public-header-height)] z-10 bg-surface-base'>
          <tr>
            {SORTABLE_COLUMNS.map(({ column, label }) => {
              const activeSort = sort?.column === column ? sort.direction : undefined;
              const SortIcon = activeSort === 'ascending' ? ArrowUp : activeSort === 'descending' ? ArrowDown : MoveVertical;
              return (
                <th key={column} scope='col' aria-sort={activeSort}
                  className={`border-b border-neutral-border px-2 ${column === 'year' ? 'w-16' : ''}`}>
                  <button type='button'
                    aria-label={copy('audits.sort_findings_page').replace('{column}', copy(label))}
                    onClick={() => setSort({ column, direction: activeSort === 'ascending' ? 'descending' : 'ascending' })}
                    className='inline-flex min-h-11 min-w-11 items-center gap-1 rounded text-left font-semibold underline-offset-4 hover:underline'>
                    {copy(label)}
                    <SortIcon size={14} className='shrink-0' aria-hidden='true' />
                  </button>
                </th>
              );
            })}
            <th scope='col' className='w-28 border-b border-neutral-border px-2'>{copy('audits.severity')}</th>
            <th scope='col' className='w-14 border-b border-neutral-border px-1 text-center'>{copy('audits.finding_source_column')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(finding => {
            const isSelected = finding.id === selected?.id;
            return (
              <tr key={finding.id} className={`cursor-pointer align-top hover:bg-surface-sunken/50 ${isSelected ? 'bg-surface-sunken/50' : ''}`}
                onClick={event => {
                  if (event.target instanceof Element && event.target.closest('a, button')) return;
                  event.currentTarget.querySelector('button')?.click();
                }}>
                <th scope='row' className='border-b border-neutral-border p-2 font-normal'>
                  <button type='button' aria-expanded={isSelected} aria-controls={isSelected ? paneId : undefined}
                    onClick={event => {
                      rowTrigger.current = event.currentTarget;
                      setSelectedId(finding.id);
                    }}
                    className='flex min-h-11 w-full scroll-mt-[calc(var(--public-header-height)+3rem)] items-center rounded text-left font-semibold text-neutral-text underline decoration-neutral-border underline-offset-4 hover:decoration-current'>
                    <span className='line-clamp-2'>{findingName(finding)}</span>
                  </button>
                  <span className='block text-neutral-muted'>
                    {finding.audited_entity_name || copy('audits.institution_not_identified')}
                  </span>
                </th>
                <td className='border-b border-neutral-border px-2 py-3 font-mono'>
                  {finding.audit_year ?? <>
                    <span aria-hidden='true'>—</span>
                    <span className='sr-only'>{copy('audits.not_stated')}</span>
                  </>}
                </td>
                <td className='border-b border-neutral-border px-2 py-3'>
                  <FindingSeverity severity={finding.severity} copy={copy} />
                </td>
                <td className='border-b border-neutral-border px-1 py-1 text-center'>
                  {finding.source_document_url ? <FindingSourceLink finding={finding} copy={copy} iconOnly />
                    : <>
                      <span className='inline-block pt-2 text-neutral-muted' aria-hidden='true'>—</span>
                      <span className='sr-only'>{copy('audits.finding_source_unavailable')}</span>
                    </>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {selected && <FindingDetailPane id={paneId} finding={selected} copy={copy} lang={lang} onClose={closeFinding} />}
    </div>
  );
}
