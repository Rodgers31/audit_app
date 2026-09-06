'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import type { BudgetSource } from '@/types';
import { Info } from 'lucide-react';

/**
 * Provenance note for county FINANCIAL figures — budget, sector splits, debt,
 * pending bills, audit findings.
 *
 * The budget clause is chosen from what the API says it summed, because both
 * kinds of period live in the database at once: CBIRR-reported periods
 * carrying the Controller of Budget's Total/Development/Recurrent aggregates,
 * and CRA equitable-share PROJECTION periods carrying a modelled sector split
 * (see backend/tests/test_county_period_agreement.py).
 *
 * It used to open, for every county and every period, "County budget
 * allocations are a modelled estimate — not official Controller of Budget
 * figures". That became false once counties_budget started parsing the CBIRR:
 * all 47 counties now reconcile to the report's printed 633,303.87m total, and
 * Baringo's page printed KES 9.54B straight off that parse while this banner
 * called it a CRA model.
 *
 * Pass the provenance of whatever the page is showing — one county's, or the
 * whole list's. Absent (`undefined`/`null`, or an empty list) means no budget
 * figure was published, and the note then makes no claim about a budget source
 * rather than defaulting to one.
 */
export default function ModelledDataNote({
  className = '',
  budgetSource,
}: {
  className?: string;
  /** `budget.source` from /comprehensive, or the rows' `budgetSource` from a list. */
  budgetSource?: BudgetSource | Array<BudgetSource | undefined> | null;
}) {
  const { t } = useLang();

  const clauseKey = budgetProvenanceKey(budgetSource);
  const clauses = [clauseKey, 'counties.provenance.rest' as const].filter(
    Boolean
  ) as TranslationKey[];

  return (
    <div
      role='note'
      className={`flex items-start gap-2.5 rounded-lg border border-amber-300/70 bg-amber-50 px-4 py-3 text-sm dark:border-amber-700/50 dark:bg-amber-950/30 ${className}`}>
      <Info className='mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600 dark:text-amber-400' />
      <p className='leading-snug text-amber-900/90 dark:text-amber-100/90'>
        {clauses.map((key) => t(key)).join(' ')}
      </p>
    </div>
  );
}

/**
 * Which budget clause the note should carry, or null for "say nothing".
 *
 * Counties whose budget the API withheld contribute no provenance — they show
 * a dash, not a figure — so they neither pick a clause nor force the mixed
 * one. A page genuinely showing both kinds says so; asserting either single
 * source there would be wrong about the other half of the rows.
 *
 * Exported so the rule can be exercised directly — the mixed case is
 * otherwise only reachable through a partially-ingested CBIRR.
 */
export function budgetProvenanceKey(
  budgetSource: BudgetSource | Array<BudgetSource | undefined> | null | undefined
): TranslationKey | null {
  const present = (Array.isArray(budgetSource) ? budgetSource : [budgetSource]).filter(
    (s): s is 'cob_cbirr' | 'cra_model' => s === 'cob_cbirr' || s === 'cra_model'
  );
  if (present.length === 0) return null;

  const hasCbirr = present.includes('cob_cbirr');
  const hasModel = present.includes('cra_model');
  if (hasCbirr && hasModel) return 'counties.provenance.budget_mixed';
  return hasCbirr ? 'counties.provenance.budget_cbirr' : 'counties.provenance.budget_cra';
}
