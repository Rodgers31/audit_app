'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import { Info } from 'lucide-react';

/**
 * Honest disclaimer for county FINANCIAL figures (budget sector splits,
 * debt, pending bills), which are modelled estimates — not official
 * Controller-of-Budget data (audit §2.4). Exceptions that ARE real
 * parsed CoB data: county Total/Development/Recurrent aggregates from
 * the live BIRR parse. County audit findings display only when the
 * backend marks them display-grade (real ingested OAG data) — the
 * former fixture findings were fabricated and have been purged.
 */
export default function ModelledDataNote({ className = '' }: { className?: string }) {
  const { t } = useLang();
  return (
    <div
      role='note'
      className={`flex items-start gap-2.5 rounded-lg border border-amber-300/70 bg-amber-50 px-4 py-3 text-sm dark:border-amber-700/50 dark:bg-amber-950/30 ${className}`}>
      <Info className='mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600 dark:text-amber-400' />
      <p className='leading-snug text-amber-900/90 dark:text-amber-100/90'>
        {t('counties.modelled_estimate')}
      </p>
    </div>
  );
}
