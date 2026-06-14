'use client';

/**
 * MoneyFlowSourceReconciliation
 *
 * Shows, per-fiscal-year, exactly which authoritative documents back each
 * stage of the waterfall. Mirrors the Debt page reconciliation panel so
 * users can verify our numbers against the originals and understand why a
 * stage is blank when the source report hasn't been published yet.
 */

import { BookOpenCheck, ExternalLink } from 'lucide-react';

interface SourceEntry {
  publisher: string;
  title: string;
  url: string;
  covers: string; // which stage(s) it feeds
  status: 'published' | 'preliminary' | 'pending';
}

interface Props {
  fiscalYear: string;
}

/**
 * Keyed by the canonical fiscal-year label (e.g. "2024/25" or "2024/2025").
 * OAG audits lag the fiscal year by ~15–18 months, so FY24/25 audits don't
 * exist yet; CoB CBIRRs publish quarterly + annual, so the current FY has
 * only partial coverage.
 */
function buildSourcesFor(fy: string): SourceEntry[] {
  const norm = fy.replace('FY', '').trim();

  const common: SourceEntry[] = [
    {
      publisher: 'Commission on Revenue Allocation',
      title: `County Equitable Share — FY ${norm}`,
      url: 'https://www.crakenya.org/county-allocations/',
      covers: 'Allocated',
      status: 'published',
    },
  ];

  const cbirrBase =
    'https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/';
  const oagBase = 'https://oagkenya.go.ke/index.php/reports/county-audit-reports';

  // Encode the publishing status of each source, per year.
  const matrix: Record<string, Array<Omit<SourceEntry, 'url'> & { url?: string }>> = {
    '2022/23': [
      {
        publisher: 'Controller of Budget',
        title: 'County Budget Implementation Review Report FY2022/23 Annual',
        covers: 'Released, Spent',
        status: 'published',
      },
      {
        publisher: 'Office of the Auditor General',
        title: 'Consolidated County Audit Report FY2022/23',
        covers: 'Flagged',
        status: 'published',
      },
    ],
    '2023/24': [
      {
        publisher: 'Controller of Budget',
        title: 'County Budget Implementation Review Report FY2023/24 Annual',
        covers: 'Released, Spent',
        status: 'published',
      },
      {
        publisher: 'Office of the Auditor General',
        title: 'Consolidated County Audit Report FY2023/24',
        covers: 'Flagged',
        status: 'published',
      },
    ],
    '2024/25': [
      {
        publisher: 'Controller of Budget',
        title: 'County Budget Implementation Review Report FY2024/25 H1 + Q3',
        covers: 'Released, Spent',
        status: 'preliminary',
      },
      {
        publisher: 'Office of the Auditor General',
        title: 'Consolidated County Audit Report FY2024/25',
        covers: 'Flagged',
        status: 'pending',
      },
    ],
    '2025/26': [
      {
        publisher: 'National Treasury',
        title: '2025 Budget Policy Statement — County Equitable Share Projection',
        covers: 'Allocated (budgeted)',
        status: 'published',
      },
      {
        publisher: 'Controller of Budget',
        title: 'County Budget Implementation Review Report FY2025/26',
        covers: 'Released, Spent',
        status: 'pending',
      },
      {
        publisher: 'Office of the Auditor General',
        title: 'Consolidated County Audit Report FY2025/26',
        covers: 'Flagged',
        status: 'pending',
      },
    ],
  };

  const entries = matrix[norm] ?? matrix[norm.replace(/(\d{4})\/(\d{2})$/, (_, a, b) => `${a}/${b}`)] ?? [];
  const mapped = entries.map((e) => ({
    publisher: e.publisher,
    title: e.title,
    covers: e.covers,
    status: e.status,
    url:
      e.url ??
      (e.publisher.includes('Controller')
        ? cbirrBase
        : e.publisher.includes('Auditor')
          ? oagBase
          : e.publisher.includes('Treasury')
            ? 'https://www.treasury.go.ke/budget-policy-statements/'
            : 'https://www.crakenya.org/county-allocations/'),
  }));

  return [...common, ...mapped];
}

const STATUS_STYLES: Record<SourceEntry['status'], { label: string; className: string }> = {
  published: {
    label: 'Published',
    className: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  },
  preliminary: {
    label: 'Preliminary',
    className: 'bg-amber-50 text-amber-700 border-amber-200',
  },
  pending: {
    label: 'Not yet published',
    className: 'bg-neutral-100 text-neutral-500 border-neutral-200',
  },
};

export default function MoneyFlowSourceReconciliation({ fiscalYear }: Props) {
  const sources = buildSourcesFor(fiscalYear);

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
            Every stage of the waterfall above is anchored to one of these official
            documents. Open any link to verify the underlying figures yourself.
          </p>
        </div>
      </div>
      <ul className='divide-y divide-neutral-border/40 border-t border-neutral-border/30'>
        {sources.map((s, i) => {
          const st = STATUS_STYLES[s.status];
          const clickable = s.status !== 'pending';
          return (
            <li
              key={`${s.publisher}-${i}`}
              className={`px-5 sm:px-7 py-3 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 ${
                clickable ? 'hover:bg-gov-forest/[0.03]' : ''
              } transition-colors`}>
              <div className='flex-1 min-w-0'>
                <div className='flex items-center gap-2 flex-wrap'>
                  <span className='text-[11px] uppercase tracking-wider font-semibold text-gov-forest dark:text-emerald-100'>
                    {s.publisher}
                  </span>
                  <span
                    className={`text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full border ${st.className}`}>
                    {st.label}
                  </span>
                </div>
                <div className='text-[13px] text-gov-dark dark:text-white mt-0.5 leading-snug'>
                  {s.title}
                </div>
                <div className='text-[11px] text-neutral-muted mt-0.5'>
                  Feeds: {s.covers}
                </div>
              </div>
              {clickable ? (
                <a
                  href={s.url}
                  target='_blank'
                  rel='noopener noreferrer'
                  className='inline-flex items-center gap-1 text-[12px] font-medium text-gov-sage hover:text-gov-forest dark:text-emerald-100 transition-colors flex-shrink-0'>
                  View source <ExternalLink size={12} />
                </a>
              ) : (
                <span className='text-[11px] text-neutral-muted/80 italic flex-shrink-0'>
                  Awaiting publication
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
