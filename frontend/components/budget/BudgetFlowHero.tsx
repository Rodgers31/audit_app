'use client';

/**
 * BudgetFlowHero
 *
 * The narrative centrepiece of the Budget & Spending page.
 *
 * Two paired horizontal "flow" bars answer the two questions every citizen
 * asks about a national budget:
 *
 *   1. Where does the money come from?  (Sources)
 *      — Tax, non-tax, A-i-A, grants, net borrowing
 *
 *   2. Where does it actually go?       (Uses)
 *      — Interest on debt, recurrent (ex-interest), development, counties,
 *        contingency
 *
 * BOTH BARS ARE ONE COLUMN OF ONE TABLE (issue #237): Annex Table 2a of the
 * Budget Summary, Treasury's fiscal framework. Each bar reconciles to that
 * column's "Expenditure and Net Lending", so there is no computed residual
 * on either side. This used to draw sources and uses against
 * `appropriated_budget` — the Controller of Budget's GROSS figure, which
 * counts principal redemption and excludes county transfers — and let two
 * "residual" segments absorb the difference between the bases, while
 * subtracting interest-plus-principal from a recurrent figure that holds
 * interest only. The gross budget is still the headline; it is explained
 * beside the flow, not forced into it.
 *
 * The debt-service callout stays on its own declared basis (Treasury APDMR:
 * interest + principal over tax + non-tax revenue).
 */

import type { FiscalMeasureQualification, FiscalTaxObservation } from '@/lib/api/fiscal';
import { useLang } from '@/lib/i18n/LangProvider';
import FiscalMeasureDisclosure from './FiscalMeasureDisclosure';
import { ArrowDownRight, Info } from 'lucide-react';
import BudgetFlowChart, { formatBudgetPart, formatBudgetShare, type BudgetFlowSegment } from './BudgetFlowChart';

import {
  frameworkCitation,
  qualifiedFrameworkValue,
  fiscalColumnLabel,
  frameworkOf,
  frameworkSources,
  frameworkUses,
  type FiscalFramework,
} from '@/lib/fiscal/framework';

export interface FlowHeroInput {
  absent_reasons?: Record<string, string>;
  measure_qualifications?: Record<string, FiscalMeasureQualification>;
  tax_split_observation?: FiscalTaxObservation | null;
  /** Billions KES of the gross budget that is redemption of maturing debt. */
  debt_redemption_billion?: number | null;
  /** The enacted headline, once sourced for this year. Absent until then. */
  enacted_budget?: number | null;
  fiscal_year?: string | null;
  appropriated_budget?: number | null; // KES B
  total_revenue?: number | null;
  tax_revenue?: number | null;
  non_tax_revenue?: number | null;
  total_borrowing?: number | null;
  debt_service_cost?: number | null;
  development_spending?: number | null;
  recurrent_spending?: number | null;
  county_allocation?: number | null;
  debt_service_per_shilling?: number | null; // cents per KES of revenue
  /** The split and the total it reconciles to, KSh billion. */
  fiscal_framework?: FiscalFramework | null;
  fiscal_framework_absent_reason?: string | null;
}

interface Props {
  data: FlowHeroInput | null | undefined;
}

/* ────────────────────────────── helpers ────────────────────────────── */

function fmtT(billionKES?: number | null): string {
  return billionKES == null ? '—' : formatBudgetPart(billionKES);
}

export default function BudgetFlowHero({ data }: Props) {
  const { t } = useLang();

  const fy = data?.fiscal_year ?? '—';
  const budget = data?.appropriated_budget ?? null;
  const redemptionB = data?.debt_redemption_billion ?? null;

  // Each side needs its own qualified, reconciling parts. The old duplicate
  // donut could show qualified uses even if the source rows were withheld.
  const ff = frameworkOf(data);
  const uses = frameworkUses(ff);
  const sources = frameworkSources(ff);
  const hasFlow = uses != null && sources != null;
  const hasAnyBreakdown = uses != null || sources != null;
  const issue = data?.fiscal_framework_absent_reason ?? Object.values(ff?.absent_reasons ?? {})[0];
  const withholdingReason = typeof issue === 'string' && /invalid|contradict/.test(issue)
    ? 'Some component evidence conflicts with the stored figures.'
    : typeof issue === 'string' && /reconcile|disagree/.test(issue)
      ? 'The available figures do not reconcile on the same basis.'
      : 'Compatible source evidence for every component is not yet confirmed.';
  const flowTotal = uses?.total ?? sources?.total ?? null;
  const citation = frameworkCitation(ff);
  const qualifiedShare = qualifiedFrameworkValue(ff, 'county_equitable_share_billion');
  const qualifiedTransfers = qualifiedFrameworkValue(ff, 'county_transfers_billion');
  const equitableShareB = qualifiedShare != null && qualifiedTransfers != null && qualifiedShare <= qualifiedTransfers ? qualifiedShare : null;

  const debtServiceCents = data?.debt_service_per_shilling ?? null;

  const sourceSegments: BudgetFlowSegment[] = sources ? [
    sources.tax != null
      ? { id: 'tax', amount: sources.tax }
      : { id: 'ordinary', amount: sources.ordinaryRevenue },
    { id: 'aia', amount: sources.aia },
    ...(sources.nonTax != null ? [{ id: 'nonTax' as const, amount: sources.nonTax }] : []),
    { id: 'grants', amount: sources.grants },
    { id: 'borrowing', amount: sources.borrowing },
    { id: 'cashAdjustment', amount: sources.cashAdjustment },
  ] : [];
  const useSegments: BudgetFlowSegment[] = uses ? [
    { id: 'interest', amount: uses.interest },
    { id: 'recurrent', amount: uses.recurrentExInterest },
    { id: 'development', amount: uses.development },
    { id: 'counties', amount: uses.counties },
    { id: 'contingency', amount: uses.contingency },
  ] : [];
  const sourceTakeaway = sources && sources.total > 0 ? [
    sources.tax != null
      ? t('budget.flow.tax_share').replace('{tax}', formatBudgetShare(sources.tax, sources.total))
      : t('budget.flow.ordinary_share').replace('{revenue}', formatBudgetShare(sources.ordinaryRevenue, sources.total)),
    t('budget.flow.borrowing_share').replace('{borrowing}', formatBudgetShare(sources.borrowing, sources.total)),
  ].join(' ') : '';
  const usesTakeaway = uses
    ? t(ff?.source?.column === 'Actual' ? 'budget.flow.interest_actual' : 'budget.flow.interest_plan')
        .replace('{interest}', formatBudgetShare(uses.interest, uses.total))
    : '';
  const sourcesNotes: string[] = [];
  if (sources && sources.cashAdjustment < 0) {
    sourcesNotes.push(t('budget.flow.negative_cash').replace('{amount}', `KES ${formatBudgetPart(sources.cashAdjustment)}`));
  }
  if (sources && sources.borrowing < 0) {
    sourcesNotes.push(t('budget.flow.negative_borrowing').replace('{amount}', `KES ${formatBudgetPart(sources.borrowing)}`));
  }

  if (!data) {
    return null;
  }

  // Gross less redemption, plus the county equitable share: the measure
  // budget coverage usually quotes. From API values only — this sentence
  // used to assert a hard-coded "~KES 4.8T".
  const quotedScaleB =
    budget != null && redemptionB != null && equitableShareB != null ? budget - redemptionB + equitableShareB : null;

  return (
    <section
      className='min-w-0 space-y-5'>
      {/* Header */}
      <div className='pt-2'>
        <div className='flex items-start justify-between gap-4 flex-wrap'>
          <div className='min-w-0 max-w-full [overflow-wrap:anywhere]'>
            <div className='text-xs font-semibold text-gov-forest dark:text-emerald-100'>
              National budget · {fy}
            </div>
            <h2 className='font-display text-[26px] sm:text-3xl text-gov-dark dark:text-white leading-tight mt-1'>
              {budget == null ? `Approved budget for ${fy} withheld` : `KES ${fmtT(budget)} approved for ${fy}`}
            </h2>
            <p className='text-sm text-neutral-muted mt-1 max-w-2xl'>
              The approved gross budget, on the Controller of Budget basis.
              {hasAnyBreakdown && (
                <> {hasFlow
                  ? t('budget.flow.complete').replace('{total}', fmtT(flowTotal))
                  : t('budget.flow.partial')}</>
              )}
            </p>

            <FiscalMeasureDisclosure qualifications={data?.measure_qualifications} absentReasons={data?.absent_reasons} taxObservation={data?.tax_split_observation} />
            <p className='text-xs text-neutral-muted mt-1'>Fiscal framework: {fiscalColumnLabel(data)} · {ff?.source?.edition ?? 'Edition unconfirmed'}</p>

            {/*
              Which budget is this? There are several real answers, and the
              commonly quoted one is not this one. Rather than pick silently,
              show the basis and reconcile to the figure a reader is more
              likely to have seen. `<details>` so it is an affordance, not a
              wall of text, and native so it needs no modal machinery.
            */}
            {budget != null && (<details className='group mt-2 max-w-2xl'>
              <summary className='inline-flex cursor-pointer list-none items-center gap-1.5 text-[12px] font-medium text-gov-forest hover:underline dark:text-emerald-100'>
                <Info size={13} />
                Why this figure, and why you may have seen a different one
              </summary>
              <div className='mt-2 space-y-2 rounded-xl border border-neutral-border/40 bg-gov-sand/25 px-4 py-3 text-[12.5px] leading-relaxed text-neutral-muted'>
                <p>
                  This is the <strong>gross</strong> budget: everything Parliament
                  votes for ministries, plus Consolidated Fund Services — debt
                  service, pensions and constitutional salaries, which are charged
                  directly on the Consolidated Fund rather than voted each year.
                </p>
                {/* fmtT takes BILLIONS, and every value here is in billions. */}
                {redemptionB != null && (
                  <p>
                    It <strong>includes</strong> KES {fmtT(redemptionB)} of debt{' '}
                    <em>redemption</em> — repaying maturing debt, not new spending —
                    and <strong>excludes</strong> the county equitable share, which
                    counties receive directly. Take redemption out and the national
                    figure is about KES {fmtT(budget - redemptionB)}
                    {quotedScaleB != null && (
                      <>
                        ; add the county equitable share (KES {fmtT(equitableShareB)})
                        back and it is about KES {fmtT(quotedScaleB)}, the scale of
                        the total usually quoted in budget coverage
                      </>
                    )}
                    .
                  </p>
                )}
                {hasAnyBreakdown && (
                  <p>
                    The breakdown below is Treasury&apos;s <strong>fiscal framework</strong>{' '}
                    for the same year. It reports KES {fmtT(flowTotal)} of
                    spending and net lending, including interest and county
                    transfers. Principal repayments appear in financing.
                  </p>
                )}
                <p>
                  We publish the gross figure because every year on this page is
                  sourced on that one basis, so the years can be compared. A number
                  on a different basis is not wrong — it answers a different
                  question.
                </p>
              </div>
            </details>)}
          </div>
          {/* Debt-service callout */}
          <aside
            aria-label={t('budget.flow.debt_source').replace('{year}', fy)}
            className='flex w-full min-w-0 max-w-full items-start gap-3 rounded border border-neutral-border bg-surface-base px-4 py-3 text-neutral-text sm:max-w-xs'>
            <ArrowDownRight aria-hidden='true' size={18} className='mt-0.5 shrink-0 text-signal-caution' />
            <div className='min-w-0 [overflow-wrap:anywhere]'>
              <p className='text-xs font-semibold'>{t('budget.flow.debt_source').replace('{year}', fy)}</p>
              <p className='font-display text-xl font-semibold leading-tight tabular-nums'>
                {debtServiceCents == null ? '—' : `KES ${debtServiceCents.toFixed(1)}`}
              </p>
              <p className='text-sm leading-snug text-neutral-muted'>
                {t(debtServiceCents == null ? 'budget.flow.debt_ratio_withheld' : 'budget.flow.debt_ratio')}
              </p>
            </div>
          </aside>
        </div>
      </div>

      {/* The source may exist while its component evidence is unconfirmed. */}
      {!hasAnyBreakdown && (
        <div>
          <div className='rounded-xl border border-neutral-border/60 bg-surface-sunken/40 px-4 py-4'>
            <div className='flex items-start gap-2.5'>
              <Info
                size={14}
                className='mt-0.5 flex-shrink-0 text-gov-forest/70 dark:text-emerald-100/70'
              />
              <div className='text-[12px] leading-relaxed text-neutral-muted'>
                <span className='font-semibold text-gov-dark dark:text-white'>
                  How {fy} breaks down is withheld.
                </span>{' '}
                Every part must be confirmed for this fiscal year and add up to
                one spending total. {withholdingReason}
                <span className='block mt-1.5 text-neutral-muted/80'>
                  A blank breakdown is not a finding that these amounts are zero.
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {hasAnyBreakdown && (
        <div className='grid min-w-0 gap-6 lg:grid-cols-2'>
          {sources ? (
            <BudgetFlowChart
              key={`${fy}-sources`}
              heading={t('budget.flow.sources')}
              basis={t('budget.flow.source_total')
                .replace('{total}', fmtT(sources.total))
                .replace('{revenue}', fmtT(sources.ordinaryRevenue))}
              takeaway={sourceTakeaway}
              total={sources.total}
              segments={sourceSegments}
              notes={sourcesNotes}
            />
          ) : (
            <div>
              <h3 className='font-display text-xl font-bold leading-tight'>{t('budget.flow.sources')}</h3>
              <p className='text-sm text-neutral-muted'>{t('budget.flow.missing_sources')}</p>
            </div>
          )}
          {uses ? (
            <BudgetFlowChart
              key={`${fy}-uses`}
              heading={t('budget.flow.uses')}
              basis={t('budget.flow.uses_total').replace('{total}', fmtT(uses.total))}
              takeaway={usesTakeaway}
              total={uses.total}
              segments={useSegments}
              notes={equitableShareB == null ? undefined : [
                t('budget.flow.equitable_share').replace('{amount}', `KES ${fmtT(equitableShareB)}`),
              ]}
            />
          ) : (
            <div>
              <h3 className='font-display text-xl font-bold leading-tight'>{t('budget.flow.uses')}</h3>
              <p className='text-sm text-neutral-muted'>{t('budget.flow.missing_uses')}</p>
            </div>
          )}
        </div>
      )}

      {/* Footer note */}
      <div>
        <div className='flex items-start gap-2 text-xs text-neutral-muted leading-relaxed border-t border-neutral-border/40 pt-3'>
          <Info size={13} className='mt-0.5 flex-shrink-0 text-gov-forest/70 dark:text-emerald-100/70' />
          <span>
            <strong className='text-gov-dark dark:text-white'>Basis:</strong> the
            headline is the Controller of Budget&apos;s National-Government
            <em> original gross</em> budget.
            {hasAnyBreakdown && citation && (
              <>
                {' '}The flow is Treasury&apos;s fiscal framework, {citation}: the
                figures use one column and reconcile to its total within the report&apos;s
                rounding. The source table includes the cash-basis adjustment less the
                statistical discrepancy when Treasury supplies both rows.
              </>
            )}{' '}
            Debt-service callout follows the National Treasury <em>Annual Public Debt
            Management Report</em> definition — interest payments{' '}
            <strong>plus</strong> principal redemptions, domestic + external — as a share
            of tax + non-tax revenue.
          </span>
        </div>
      </div>
    </section>
  );
}
