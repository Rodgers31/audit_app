'use client';

/**
 * BudgetSourceReconciliation
 *
 * Mirrors the Debt page's DebtSourceReconciliation: surfaces the data
 * provenance and known caveats about where the numbers come from so a
 * citizen can trust what they're reading or follow the chain back to the
 * primary documents.
 *
 *   Primary source: Controller of Budget (CoB) — Annual NG-BIRR
 *   Reference:      National Treasury — Appropriation Act / BPS
 *   Caveats:        Personnel Emoluments not always broken out; actuals
 *                   lag 6–9 months; CRA-formula modeling for county lines
 *                   when fresh BIRR data isn't yet available.
 */

import { motion } from 'framer-motion';
import {
  BookOpen,
  Database,
  ExternalLink,
  FileText,
  GitCompareArrows,
  Info,
  Landmark,
} from 'lucide-react';

export interface BudgetMeta {
  data_quality?: string;
  scope_detail?: string;
  quality_notes?: string[];
  source_updated_at?: string;
  covers_through?: string;
}

interface Props {
  meta?: BudgetMeta | null;
  lastUpdated?: string | null;
  fiscalPeriod?: string | null;
}

/**
 * Per-FY links to the authoritative Treasury debt-management document.
 * The "debt service as % of revenue" headline on this page is taken from the
 * corresponding row of the linked report; keeping these visible means a
 * reader can trace any headline number back to a primary PDF.
 */
const APDMR_BY_FY: Array<{ fy: string; title: string; url: string }> = [
  {
    fy: 'FY 2022/23',
    title: 'Annual Public Debt Report 2022/2023',
    url: 'https://www.treasury.go.ke/wp-content/uploads/2024/01/Annual-Public-Debt-Report-2022-2023-Sept-2023.pdf',
  },
  {
    fy: 'FY 2023/24',
    title: 'Annual Public Debt Management Report 2023/2024',
    url: 'https://www.treasury.go.ke/wp-content/uploads/2024/11/Annual-Public-Debt-Management-Report-.pdf',
  },
  {
    fy: 'FY 2024/25',
    title: 'Annual Public Debt Report 2024/2025',
    url: 'https://www.treasury.go.ke/wp-content/uploads/2025/11/Annual-Public-Debt-Report-2024-2025.pdf',
  },
  {
    fy: 'FY 2025/26',
    title: '2025 Budget Policy Statement (budgeted; APDMR due Nov 2026)',
    url: 'https://www.treasury.go.ke/wp-content/uploads/2025/02/2025-Budget-Policy-Statement...pdf',
  },
];

function fmtDate(iso?: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('en-KE', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

export default function BudgetSourceReconciliation({
  meta,
  lastUpdated,
  fiscalPeriod,
}: Props) {
  const qualityLabel = meta?.data_quality ?? 'estimated';
  const notes = meta?.quality_notes ?? [];

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.5 }}
      className='rounded-2xl border border-neutral-border/40 bg-white/70 dark:bg-surface-elevated backdrop-blur-sm overflow-hidden'>
      <div className='border-b border-neutral-border/40 bg-gradient-to-r from-gov-sand/40 via-white to-transparent dark:from-surface-elevated/40 dark:via-surface-base/20 dark:to-transparent px-5 sm:px-7 py-4'>
        <div className='flex items-start gap-3'>
          <div className='rounded-lg bg-gov-forest/10 text-gov-forest dark:text-emerald-100 p-2 mt-0.5'>
            <GitCompareArrows size={18} />
          </div>
          <div className='flex-1 min-w-0'>
            <h3 className='font-display text-lg sm:text-xl text-gov-dark dark:text-white leading-tight'>
              Sources &amp; Reconciliation
            </h3>
            <p className='text-xs sm:text-sm text-neutral-muted mt-0.5'>
              Who published these numbers, what they measure, and what they leave out.
            </p>
          </div>
        </div>
      </div>

      <div className='grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-neutral-border/40'>
        {/* Execution / actuals */}
        <div className='p-5 sm:p-6 relative'>
          <div className='absolute top-4 right-4 inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-gov-forest dark:text-emerald-100 bg-gov-forest/10 px-2 py-0.5 rounded-full'>
            <span className='relative flex h-1.5 w-1.5'>
              <span className='animate-ping absolute inline-flex h-full w-full rounded-full bg-gov-forest opacity-60' />
              <span className='relative inline-flex rounded-full h-1.5 w-1.5 bg-gov-forest' />
            </span>
            Actuals
          </div>
          <div className='flex items-center gap-2 mb-2'>
            <Database size={14} className='text-gov-forest dark:text-emerald-100' />
            <span className='text-xs font-semibold uppercase tracking-wider text-gov-forest dark:text-emerald-100'>
              Controller of Budget
            </span>
          </div>
          <div className='font-display text-lg text-gov-dark dark:text-white'>
            Budget Implementation Review
          </div>
          <p className='text-xs text-neutral-muted mt-2 leading-relaxed'>
            Execution rates, sector spend, and county utilisation come from the CoB&apos;s
            quarterly and annual BIRR reports to Parliament, per Article 228(6) of the
            Constitution. Published with a 3–6 month lag after quarter close.
          </p>
          <dl className='mt-4 space-y-1.5 text-[11px]'>
            <div className='flex justify-between gap-3'>
              <dt className='text-neutral-muted'>Source</dt>
              <dd className='text-gov-dark dark:text-white font-medium text-right'>CoB Annual NG-BIRR</dd>
            </div>
            <div className='flex justify-between gap-3'>
              <dt className='text-neutral-muted'>Fetch</dt>
              <dd className='text-gov-dark dark:text-white font-medium text-right'>Quarterly · PDF parsed</dd>
            </div>
            <div className='flex justify-between gap-3'>
              <dt className='text-neutral-muted'>Last updated</dt>
              <dd className='text-gov-dark dark:text-white font-medium text-right'>{fmtDate(lastUpdated)}</dd>
            </div>
          </dl>
        </div>

        {/* Plan / appropriations */}
        <div className='p-5 sm:p-6 relative'>
          <div className='absolute top-4 right-4 inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-gov-gold bg-gov-gold/15 px-2 py-0.5 rounded-full'>
            <BookOpen size={10} />
            Plan
          </div>
          <div className='flex items-center gap-2 mb-2'>
            <FileText size={14} className='text-gov-gold' />
            <span className='text-xs font-semibold uppercase tracking-wider text-gov-gold'>
              National Treasury
            </span>
          </div>
          <div className='font-display text-lg text-gov-dark dark:text-white'>
            Appropriation Act &amp; BPS
          </div>
          <p className='text-xs text-neutral-muted mt-2 leading-relaxed'>
            Headline budget ceilings, fiscal aggregates, revenue targets, and borrowing
            plans come from the Budget Policy Statement and the Appropriation Act passed
            by the National Assembly before each FY begins.
          </p>
          <dl className='mt-4 space-y-1.5 text-[11px]'>
            <div className='flex justify-between gap-3'>
              <dt className='text-neutral-muted'>Source</dt>
              <dd className='text-gov-dark dark:text-white font-medium text-right'>
                National Treasury BPS
              </dd>
            </div>
            <div className='flex justify-between gap-3'>
              <dt className='text-neutral-muted'>Fetch</dt>
              <dd className='text-gov-dark dark:text-white font-medium text-right'>Annual publication</dd>
            </div>
            <div className='flex justify-between gap-3'>
              <dt className='text-neutral-muted'>Covers</dt>
              <dd className='text-gov-dark dark:text-white font-medium text-right'>
                {fiscalPeriod ?? meta?.covers_through ?? '—'}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {/* APDMR per-FY source strip — makes the debt-service headline traceable */}
      <div className='border-t border-neutral-border/40 bg-white/60 dark:bg-surface-elevated px-5 sm:px-7 py-4'>
        <div className='flex items-start gap-3'>
          <div className='rounded-lg bg-gov-copper/10 text-gov-copper p-2 mt-0.5 flex-shrink-0'>
            <Landmark size={16} />
          </div>
          <div className='flex-1 min-w-0'>
            <div className='flex items-baseline justify-between flex-wrap gap-x-3 gap-y-0.5'>
              <span className='text-sm font-semibold text-gov-dark dark:text-white'>
                Debt-service headline: source by fiscal year
              </span>
              <span className='text-[10px] uppercase tracking-wider text-gov-copper/80 font-semibold'>
                Treasury APDMR
              </span>
            </div>
            <p className='text-[11.5px] text-neutral-muted mt-1 leading-relaxed'>
              &quot;Debt service as % of revenue&quot; on this page follows the National
              Treasury <em>Annual Public Debt Management Report</em>: interest +
              principal redemptions (domestic + external), divided by tax + non-tax
              revenue. Click an FY to open the primary source.
            </p>
            <ul className='mt-2.5 grid grid-cols-1 sm:grid-cols-2 gap-1.5'>
              {APDMR_BY_FY.map((r) => (
                <li key={r.fy}>
                  <a
                    href={r.url}
                    target='_blank'
                    rel='noopener noreferrer'
                    className='group flex items-center justify-between gap-2 rounded-md border border-neutral-border/40 bg-white dark:bg-surface-base px-2.5 py-1.5 text-[11px] hover:border-gov-copper/50 hover:bg-gov-copper/5 transition-colors'>
                    <span className='flex items-center gap-2 min-w-0'>
                      <span className='font-semibold text-gov-dark dark:text-white tabular-nums flex-shrink-0'>
                        {r.fy.replace('FY ', '')}
                      </span>
                      <span className='text-neutral-muted truncate'>{r.title}</span>
                    </span>
                    <ExternalLink
                      size={11}
                      className='text-neutral-muted group-hover:text-gov-copper flex-shrink-0'
                    />
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* Quality / caveats strip */}
      {(notes.length > 0 || meta?.scope_detail) && (
        <div className='border-t border-neutral-border/40 bg-gov-sand/30 px-5 sm:px-7 py-4'>
          <div className='flex items-start gap-3'>
            <div className='rounded-full bg-white dark:bg-surface-base border border-gov-gold/40 text-gov-gold p-1.5 mt-0.5 flex-shrink-0'>
              <Info size={14} />
            </div>
            <div className='flex-1'>
              <div className='flex flex-wrap items-baseline gap-x-2 gap-y-0.5'>
                <span className='text-sm font-semibold text-gov-dark dark:text-white'>
                  Data quality: <span className='capitalize'>{qualityLabel}</span>
                </span>
                <span className='text-xs text-neutral-muted'>
                  What these numbers don&apos;t tell you
                </span>
              </div>
              {meta?.scope_detail && (
                <p className='text-[12px] text-neutral-muted leading-relaxed mt-1'>
                  {meta.scope_detail}
                </p>
              )}
              {notes.length > 0 && (
                <ul className='mt-2 space-y-1.5 text-[11.5px] text-neutral-muted/90 leading-relaxed list-disc pl-4'>
                  {notes.slice(0, 4).map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </motion.section>
  );
}
