'use client';

import { BookOpenCheck, ExternalLink } from 'lucide-react';
import type { BudgetSource, MoneyFlowData } from '@/types';

interface Props {
  fiscalYear: string;
  budgetSource?: BudgetSource;
  data?: MoneyFlowData | null;
}

function sourceURL(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

const DIRECTORIES = {
  cob: 'https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/',
  oag: 'https://oagkenya.go.ke/index.php/reports/county-audit-reports',
  cra: 'https://www.crakenya.org/county-allocations/',
};

/** Source presence comes from this response, never from the age or label of a fiscal period. */
export default function MoneyFlowSourceReconciliation({ fiscalYear, budgetSource, data }: Props) {
  const source = data?.budget_source ?? budgetSource;
  const period = fiscalYear.replace(/^FY\s*/i, '').trim();
  const sources = ['Allocated', 'Spent', 'Flagged'].map((stage) => {
    const published = data?.stages.find((entry) => entry.stage === stage);
    const isCoB = stage === 'Spent' || (stage === 'Allocated' && source === 'cob_cbirr');
    const isCRA = stage === 'Allocated' && source === 'cra_model';
    const publisher =
      stage === 'Flagged'
        ? 'Office of the Auditor General'
        : isCoB
          ? 'Controller of Budget'
          : isCRA
            ? 'Commission on Revenue Allocation'
            : source === 'mixed'
              ? 'Controller of Budget / Commission on Revenue Allocation'
              : 'Allocation source unavailable';
    const documentURL =
      sourceURL(published?.source_doc) ?? (isCoB ? sourceURL(data?.source_document_url) : null);
    const directory =
      stage === 'Flagged'
        ? DIRECTORIES.oag
        : isCoB
          ? DIRECTORIES.cob
          : isCRA
            ? DIRECTORIES.cra
            : null;
    return {
      stage,
      publisher,
      documentURL,
      directory,
      title:
        documentURL &&
        isCoB &&
        documentURL === sourceURL(data?.source_document_url) &&
        data?.source_document_title
          ? data.source_document_title
          : `${stage === 'Allocated' && isCRA ? 'Modelled allocation' : stage} · FY ${period}`,
      hasAmount: published?.amount != null,
    };
  });

  return (
    <section className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface overflow-hidden'>
      <div className='px-5 sm:px-7 pt-5 pb-3 flex items-start gap-3'>
        <div className='w-9 h-9 rounded-lg bg-gov-forest/10 text-gov-forest dark:text-emerald-100 flex items-center justify-center flex-shrink-0'>
          <BookOpenCheck size={18} />
        </div>
        <div className='min-w-0'>
          <h3 className='font-display text-lg text-gov-dark dark:text-white leading-tight'>
            Source reconciliation
          </h3>
          <p className='text-[12px] text-neutral-muted mt-0.5'>
            Source links supplied with the figures for FY {period} appear below. Report-directory
            links help locate documents; they do not establish that a report has been published or
            verified for this period.
          </p>
        </div>
      </div>
      <ul className='divide-y divide-neutral-border/40 border-t border-neutral-border/30'>
        {sources.map((entry) => (
          <li
            key={entry.stage}
            className='px-5 sm:px-7 py-3 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4'>
            <div className='flex-1 min-w-0'>
              <div className='flex items-center gap-2 flex-wrap'>
                <span className='text-[11px] uppercase tracking-wider font-semibold text-gov-forest dark:text-emerald-100'>
                  {entry.publisher}
                </span>
                <span className='text-[11px] font-medium text-neutral-muted'>
                  {entry.documentURL ? 'Source link supplied' : 'Source document not linked'}
                </span>
              </div>
              <div className='text-[13px] text-gov-dark dark:text-white mt-0.5 leading-snug'>
                {entry.title}
              </div>
              <div className='text-[11px] text-neutral-muted mt-0.5'>
                Feeds: {entry.stage} · {entry.hasAmount ? 'Amount available' : 'Amount unavailable'}
              </div>
            </div>
            {(entry.documentURL || entry.directory) && (
              <a
                href={entry.documentURL ?? entry.directory!}
                target='_blank'
                rel='noopener noreferrer'
                className='inline-flex items-center gap-1 text-[12px] font-medium text-gov-sage hover:text-gov-forest dark:text-emerald-100 transition-colors flex-shrink-0'>
                {entry.documentURL ? 'View source document' : 'Browse official reports'}
                <ExternalLink size={12} />
              </a>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
