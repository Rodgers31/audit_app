'use client';

/**
 * Findings the Auditor-General titled "Unaccounted …" or "Loss of Funds".
 *
 * Issue #233. Rendered in the report's own words, each linked to its page.
 * No money figure: no matched finding carries an extracted amount, and where
 * the loader stores one it is the paragraph's only KES figure — often the
 * account balance under discussion, not the sum unaccounted for.
 */
import { useLang } from '@/lib/i18n/LangProvider';
import type { UnaccountedCase } from '@/types';
import { AlertTriangle, ExternalLink } from 'lucide-react';
import Link from 'next/link';

export default function UnaccountedFindings({ cases }: { cases: UnaccountedCase[] }) {
  const { t } = useLang();
  if (!cases.length) return null;
  return (
    <div className='bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/40 rounded-xl p-4'>
      <div className='flex items-center gap-2 mb-2'>
        <AlertTriangle size={16} className='text-red-600 flex-shrink-0' />
        <span className='text-sm font-semibold text-red-900 dark:text-red-200'>
          {t('county.unaccounted.heading').replace('{n}', String(cases.length))}
        </span>
      </div>
      <ul className='space-y-1'>
        {cases.map((c) => (
          <li key={c.finding_id} className='text-xs text-red-900/90 dark:text-red-100/90 flex flex-wrap items-baseline gap-x-1.5'>
            <span className='font-medium'>“{c.title}”</span>
            {c.fiscal_year && <span className='text-red-700/80 dark:text-red-200/70'>· {c.fiscal_year}</span>}
            {c.source.page_url && c.page_ref && (
              <a
                href={c.source.page_url}
                target='_blank'
                rel='noopener noreferrer'
                className='inline-flex items-center gap-0.5 text-red-800 dark:text-red-200 hover:underline'>
                {t('home.audits.source_page').replace('{page}', c.page_ref)}
                <ExternalLink className='w-2.5 h-2.5' />
              </a>
            )}
          </li>
        ))}
      </ul>
      <p className='text-[11px] text-red-700/80 dark:text-red-200/70 mt-2 leading-relaxed'>
        {t('county.unaccounted.no_total')}{' '}
        <Link href='/accountability/unaccounted-funds' className='underline hover:no-underline'>
          {t('county.unaccounted.see_all')}
        </Link>
      </p>
    </div>
  );
}
