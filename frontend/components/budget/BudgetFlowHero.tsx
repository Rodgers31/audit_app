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

import { motion } from 'framer-motion';
import { ArrowDownRight, Info } from 'lucide-react';
import { useMemo, useState } from 'react';

import {
  frameworkCitation,
  fiscalColumnLabel,
  frameworkOf,
  frameworkSources,
  frameworkUses,
  type FiscalFramework,
} from '@/lib/fiscal/framework';

export interface FlowHeroInput {
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
}

interface Props {
  data: FlowHeroInput | null | undefined;
}

/* ────────────────────────────── helpers ────────────────────────────── */

function fmtT(billionKES?: number | null): string {
  if (billionKES == null) return '—';
  if (billionKES >= 1000) return `${(billionKES / 1000).toFixed(2)}T`;
  return `${billionKES.toFixed(0)}B`;
}

function pct(v: number, total: number): number {
  return total > 0 ? (v / total) * 100 : 0;
}

/* ──────────────────────── segment types & colors ──────────────────────── */

interface Segment {
  key: string;
  label: string;
  valueB: number; // KES billions
  share: number; // % of parent total
  gradStart: string;
  gradEnd: string;
  accent: string; // flat color for text/icons
  note: string; // hover tooltip
}

const FLOW_BAR_HEIGHT = 44;

export default function BudgetFlowHero({ data }: Props) {
  const [hover, setHover] = useState<string | null>(null);

  const fy = data?.fiscal_year ?? '—';
  const budget = data?.appropriated_budget ?? null;
  const redemptionB = data?.debt_redemption_billion ?? null;

  // The flow is all-or-nothing and comes from one object. `null` means no
  // Budget Summary column supplies this year on one basis — and a blank
  // breakdown is not a finding that these amounts are zero.
  const ff = frameworkOf(data);
  const uses = frameworkUses(ff);
  const sources = frameworkSources(ff);
  const hasFlow = uses != null && sources != null;
  const flowTotal = uses?.total ?? null;
  const citation = frameworkCitation(ff);
  const equitableShareB = ff?.county_equitable_share_billion ?? null;

  // "shillings-per-shilling-of-revenue" metric: debt service vs total revenue
  const revenue = data?.total_revenue ?? null;
  const debtService = data?.debt_service_cost ?? null;
  const debtServicePct =
    revenue != null && revenue > 0 && debtService != null
      ? (debtService / revenue) * 100
      : null;
  const debtServiceCents =
    data?.debt_service_per_shilling ??
    (debtServicePct != null ? Math.round(debtServicePct) : null);

  /* ── Sources (money in) ── */
  const sourceSegments: Segment[] = useMemo(() => {
    if (!sources || !flowTotal) return [];
    const revenueSegs: Segment[] =
      sources.tax != null && sources.nonTax != null
        ? [
            {
              key: 'tax',
              label: 'Tax revenue',
              valueB: sources.tax,
              share: pct(sources.tax, flowTotal),
              gradStart: '#2F6343',
              gradEnd: '#1F4A30',
              accent: '#1B3A2A',
              note: 'Income tax, VAT, excise and import duty — collected by KRA.',
            },
            {
              key: 'nonTax',
              label: 'Non-tax revenue',
              valueB: sources.nonTax,
              share: pct(sources.nonTax, flowTotal),
              gradStart: '#4B8564',
              gradEnd: '#2F6343',
              accent: '#2F6343',
              note: 'Investment income, fees, fines and other ordinary revenue that is not tax.',
            },
          ]
        : [
            {
              key: 'ordinary',
              label: 'Tax & non-tax revenue',
              valueB: sources.ordinaryRevenue,
              share: pct(sources.ordinaryRevenue, flowTotal),
              gradStart: '#2F6343',
              gradEnd: '#1F4A30',
              accent: '#1B3A2A',
              note: 'The Budget Summary edition for this year prints no separate tax and non-tax rows.',
            },
          ];
    const segs: Segment[] = [
      ...revenueSegs,
      {
        key: 'aia',
        label: 'A-i-A',
        valueB: sources.aia,
        share: pct(sources.aia, flowTotal),
        gradStart: '#6A9E7F',
        gradEnd: '#4B8564',
        accent: '#3E7655',
        note: 'Appropriations-in-Aid: money ministries collect and spend directly (levies, fees, project loans routed through them).',
      },
      {
        key: 'grants',
        label: 'Grants',
        valueB: sources.grants,
        share: pct(sources.grants, flowTotal),
        gradStart: '#8DB89C',
        gradEnd: '#6A9E7F',
        accent: '#4B8564',
        note: 'Donor grants — not repaid.',
      },
      {
        key: 'borrowing',
        label: 'Net borrowing',
        valueB: sources.borrowing,
        share: pct(sources.borrowing, flowTotal),
        gradStart: '#B83E3E',
        gradEnd: '#7E2424',
        accent: '#9E3030',
        note: 'The fiscal deficit, financed by net domestic and net foreign borrowing — adds to the debt stock.',
      },
    ];
    if (sources.cashAdjustment > 0.05) {
      segs.push({
        key: 'cashAdj',
        label: 'Cash-basis adjustment',
        valueB: sources.cashAdjustment,
        share: pct(sources.cashAdjustment, flowTotal),
        gradStart: '#B38628',
        gradEnd: '#7D591A',
        accent: '#A6781F',
        note: "The table's own 'Adjustment to Cash Basis' less its 'Statistical discrepancy' — printed rows, not a figure computed here.",
      });
    }
    return segs;
  }, [sources, flowTotal]);

  /* ── Uses (money out) ── */
  const useSegments: Segment[] = useMemo(() => {
    if (!uses) return [];
    const t = uses.total;
    return [
      {
        key: 'interest',
        label: 'Interest on debt',
        valueB: uses.interest,
        share: pct(uses.interest, t),
        gradStart: '#9E3030',
        gradEnd: '#4C1616',
        accent: '#7E2424',
        note:
          'Interest on domestic and foreign debt — the part of debt service that is spending. ' +
          'Principal repaid on maturing loans is financing, not spending, so it is not in this bar.',
      },
      {
        key: 'recurrentExInterest',
        label: 'Recurrent (ex-interest)',
        valueB: uses.recurrentExInterest,
        share: pct(uses.recurrentExInterest, t),
        gradStart: '#6B7280',
        gradEnd: '#3F4754',
        accent: '#4B5563',
        note: 'Salaries, pensions, operations & maintenance — keeps existing services running.',
      },
      {
        key: 'development',
        label: 'Development',
        valueB: uses.development,
        share: pct(uses.development, t),
        gradStart: '#3B7251',
        gradEnd: '#1F4A30',
        accent: '#2F6343',
        note: 'Capital projects and net lending — roads, hospitals, water systems.',
      },
      {
        key: 'counties',
        label: 'Counties',
        valueB: uses.counties,
        share: pct(uses.counties, t),
        gradStart: '#4B8564',
        gradEnd: '#295B3E',
        accent: '#3E7655',
        note:
          equitableShareB != null
            ? `Transfers to the 47 county governments: the equitable share (KES ${fmtT(equitableShareB)}) plus conditional allocations.`
            : 'Transfers to the 47 county governments: the equitable share plus conditional allocations.',
      },
      {
        key: 'contingency',
        label: 'Contingency fund',
        valueB: uses.contingency,
        share: pct(uses.contingency, t),
        gradStart: '#B38628',
        gradEnd: '#7D591A',
        accent: '#A6781F',
        note: 'Set aside for urgent and unforeseen needs.',
      },
    ];
  }, [uses, equitableShareB]);

  if (!data || !budget) {
    return null;
  }

  // Gross less redemption, plus the county equitable share: the measure
  // budget coverage usually quotes. From API values only — this sentence
  // used to assert a hard-coded "~KES 4.8T".
  const quotedScaleB =
    redemptionB != null && equitableShareB != null ? budget - redemptionB + equitableShareB : null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.55 }}
      className='rounded-2xl bg-gradient-to-br from-white via-gov-sand/30 to-white dark:from-surface-elevated dark:via-surface-base dark:to-surface-elevated border border-neutral-border/40 shadow-surface overflow-hidden'>
      {/* Header */}
      <div className='px-5 sm:px-8 pt-6 sm:pt-8 pb-4'>
        <div className='flex items-start justify-between gap-4 flex-wrap'>
          <div>
            <div className='text-[11px] font-semibold uppercase tracking-[0.18em] text-gov-forest/80 dark:text-emerald-100/80'>
              National Budget · {fy}
            </div>
            <h2 className='font-display text-[26px] sm:text-3xl text-gov-dark dark:text-white leading-tight mt-1'>
              {`KES ${fmtT(budget)} approved for ${fy}`}
            </h2>
            <p className='text-sm text-neutral-muted mt-1 max-w-2xl'>
              {hasFlow
                ? `The approved gross budget, on the Controller of Budget basis. Below, the same year on Treasury's fiscal framework: KES ${fmtT(flowTotal)} of spending and how it is paid for — sources on top, uses on the bottom.`
                : 'The approved gross budget, on the Controller of Budget basis.'}
            </p>

            <p className='text-xs text-neutral-muted mt-1'>Fiscal framework: {fiscalColumnLabel(data)} · {ff?.source?.edition ?? 'Edition unconfirmed'}</p>

            {/*
              Which budget is this? There are several real answers, and the
              commonly quoted one is not this one. Rather than pick silently,
              show the basis and reconcile to the figure a reader is more
              likely to have seen. `<details>` so it is an affordance, not a
              wall of text, and native so it needs no modal machinery.
            */}
            <details className='group mt-2 max-w-2xl'>
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
                {hasFlow && (
                  <p>
                    The flow below is Treasury&apos;s <strong>fiscal framework</strong>{' '}
                    for the same year: KES {fmtT(flowTotal)} of spending and net
                    lending, which counts interest but not principal, and counts
                    transfers to counties. It is a different total from the gross
                    figure above, so the flow is drawn against its own total rather
                    than against the gross budget.
                  </p>
                )}
                <p>
                  We publish the gross figure because every year on this page is
                  sourced on that one basis, so the years can be compared. A number
                  on a different basis is not wrong — it answers a different
                  question.
                </p>
              </div>
            </details>
          </div>
          {/* Debt-service callout */}
          <div className='relative flex-shrink-0'>
            <div className='rounded-xl bg-gov-copper/10 border border-gov-copper/30 px-4 py-3 flex items-center gap-3 max-w-xs'>
              <div className='flex-shrink-0 w-10 h-10 rounded-full bg-gov-copper/15 border border-gov-copper/40 flex items-center justify-center'>
                <ArrowDownRight size={18} className='text-gov-copper' />
              </div>
              <div>
                <div className='text-[11px] uppercase tracking-wider font-semibold text-gov-copper'>
                  Treasury APDMR · {fy}
                </div>
                <div className='font-display text-xl text-gov-dark dark:text-white leading-tight tabular-nums'>
                  {debtServiceCents == null ? '—' : `KES ${debtServiceCents.toFixed(1)}`}
                </div>
                <div className='text-[11px] text-neutral-muted leading-tight'>
                  {debtServiceCents == null
                    ? 'of every KES 100 of revenue — not yet published for this year'
                    : 'of every KES 100 of revenue services the debt (interest + principal)'}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Composition withheld — no Budget Summary column supplies this year
          on one basis. Say so rather than drawing bars of zeros. */}
      {!hasFlow && (
        <div className='px-5 sm:px-8 pb-7 pt-2'>
          <div className='rounded-xl border border-neutral-border/60 bg-surface-sunken/40 px-4 py-4'>
            <div className='flex items-start gap-2.5'>
              <Info
                size={14}
                className='mt-0.5 flex-shrink-0 text-gov-forest/70 dark:text-emerald-100/70'
              />
              <div className='text-[12px] leading-relaxed text-neutral-muted'>
                <span className='font-semibold text-gov-dark dark:text-white'>
                  How {fy} breaks down is not published yet.
                </span>{' '}
                The sources-and-uses breakdown is drawn only from Treasury&apos;s
                Budget Summary, where every part adds up to one total. No edition we
                can read supplies {fy} on that basis, so the breakdown is withheld
                rather than assembled from figures measured different ways.
                <span className='block mt-1.5 text-neutral-muted/80'>
                  A blank breakdown is not a finding that these amounts are zero.
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Sources bar */}
      {hasFlow && flowTotal != null && (
      <div className='px-5 sm:px-8 pb-1 pt-2'>
        <div className='flex items-baseline justify-between gap-2 mb-2'>
          <h3 className='text-[13px] font-semibold text-gov-dark dark:text-white tracking-tight'>
            Where the money comes from
          </h3>
          <span className='text-[11px] text-neutral-muted'>
            Total KES {fmtT(flowTotal)} · revenue KES {fmtT(sources!.ordinaryRevenue)}
          </span>
        </div>
        <FlowBar segments={sourceSegments} total={flowTotal} hover={hover} setHover={setHover} />
        <SegmentLegend segments={sourceSegments} hover={hover} setHover={setHover} />
        {sources!.cashAdjustment < -0.05 && (
          <p className='mt-1.5 text-[11px] text-neutral-muted'>
            Treasury&apos;s table records a statistical discrepancy for this year, so
            the sources shown exceed spending by KES {fmtT(-sources!.cashAdjustment)}.
          </p>
        )}
      </div>
      )}

      {/* Connector */}
      {hasFlow && (
      <div className='flex items-center justify-center py-2'>
        <div className='flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] text-neutral-muted/80 font-semibold'>
          <span className='h-px w-8 bg-neutral-border' />
          Flows into
          <span className='h-px w-8 bg-neutral-border' />
        </div>
      </div>
      )}

      {/* Uses bar */}
      {hasFlow && flowTotal != null && (
      <div className='px-5 sm:px-8 pb-7 pt-1'>
        <div className='flex items-baseline justify-between gap-2 mb-2'>
          <h3 className='text-[13px] font-semibold text-gov-dark dark:text-white tracking-tight'>
            Where it actually goes
          </h3>
          <span className='text-[11px] text-neutral-muted'>
            Spending &amp; net lending KES {fmtT(flowTotal)}
          </span>
        </div>
        <FlowBar segments={useSegments} total={flowTotal} hover={hover} setHover={setHover} />
        <SegmentLegend segments={useSegments} hover={hover} setHover={setHover} />
      </div>
      )}

      {/* Footer note */}
      <div className='px-5 sm:px-8 pb-5 pt-0'>
        <div className='flex items-start gap-2 text-[11px] text-neutral-muted/90 leading-relaxed border-t border-neutral-border/40 pt-3'>
          <Info size={13} className='mt-0.5 flex-shrink-0 text-gov-forest/70 dark:text-emerald-100/70' />
          <span>
            <strong className='text-gov-dark dark:text-white'>Basis:</strong> the
            headline is the Controller of Budget&apos;s National-Government
            <em> original gross</em> budget.
            {hasFlow && citation && (
              <>
                {' '}The flow is Treasury&apos;s fiscal framework, {citation}: every
                segment is a printed line of one column, and each bar adds up to that
                column&apos;s total.
              </>
            )}{' '}
            Debt-service callout follows the National Treasury <em>Annual Public Debt
            Management Report</em> definition — interest payments{' '}
            <strong>plus</strong> principal redemptions, domestic + external — as a share
            of tax + non-tax revenue.
          </span>
        </div>
      </div>
    </motion.section>
  );
}

/* ───────────────────────────── flow bar ───────────────────────────── */

function FlowBar({
  segments,
  total,
  hover,
  setHover,
}: {
  segments: Segment[];
  total: number;
  hover: string | null;
  setHover: (s: string | null) => void;
}) {
  return (
    <div
      className='relative w-full rounded-full bg-gov-sand/60 border border-neutral-border/30 overflow-hidden flex'
      style={{ height: FLOW_BAR_HEIGHT }}>
      {segments.map((seg, i) => {
        const w = pct(seg.valueB, total);
        if (w < 0.1) return null;
        const isHover = hover === seg.key;
        return (
          <motion.div
            key={seg.key}
            initial={{ width: 0 }}
            animate={{ width: `${w}%` }}
            transition={{ duration: 0.9, delay: 0.08 * i, ease: [0.22, 1, 0.36, 1] }}
            onMouseEnter={() => setHover(seg.key)}
            onMouseLeave={() => setHover(null)}
            className='relative h-full cursor-default group'
            style={{
              background: `linear-gradient(135deg, ${seg.gradStart}, ${seg.gradEnd})`,
              filter: isHover ? 'brightness(1.08)' : 'brightness(1)',
              transform: isHover ? 'scaleY(1.06)' : 'scaleY(1)',
              transformOrigin: 'center',
              transition: 'filter .2s, transform .2s',
            }}>
            {w > 6 && (
              <span className='absolute inset-0 flex items-center justify-center px-2 text-[11px] font-bold text-white/95 drop-shadow-sm tabular-nums'>
                {w.toFixed(0)}%
              </span>
            )}
            {isHover && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.15 }}
                className='absolute left-1/2 -translate-x-1/2 -top-2 -translate-y-full z-10 bg-white dark:bg-surface-base border border-neutral-border/60 shadow-elevated rounded-lg px-3 py-2 w-56 pointer-events-none'>
                <div className='text-[11px] font-semibold uppercase tracking-wider' style={{ color: seg.accent }}>
                  {seg.label}
                </div>
                <div className='text-sm font-bold text-gov-dark dark:text-white tabular-nums leading-tight'>
                  KES {fmtT(seg.valueB)} · {seg.share > 0 && seg.share < 0.1 ? '<0.1' : seg.share.toFixed(1)}%
                </div>
                <div className='text-[11px] text-neutral-muted leading-snug mt-1'>
                  {seg.note}
                </div>
              </motion.div>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}

/* ───────────────────────── segment legend chips ───────────────────────── */

function SegmentLegend({
  segments,
  hover,
  setHover,
}: {
  segments: Segment[];
  hover: string | null;
  setHover: (s: string | null) => void;
}) {
  return (
    <div className='mt-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-1.5'>
      {segments.map((seg) => {
        const isHover = hover === seg.key;
        return (
          <button
            key={seg.key}
            type='button'
            onMouseEnter={() => setHover(seg.key)}
            onMouseLeave={() => setHover(null)}
            className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-left transition-all ${
              isHover
                ? 'bg-white dark:bg-surface-base border border-neutral-border/60 shadow-sm'
                : 'border border-transparent'
            }`}>
            <span
              className='w-2 h-5 rounded-sm flex-shrink-0'
              style={{ background: `linear-gradient(180deg, ${seg.gradStart}, ${seg.gradEnd})` }}
            />
            <span className='flex-1 min-w-0'>
              <span className='block text-[11px] font-semibold text-gov-dark dark:text-white truncate'>
                {seg.label}
              </span>
              <span className='block text-[11px] text-neutral-muted tabular-nums'>
                KES {fmtT(seg.valueB)} · {seg.share > 0 && seg.share < 0.1 ? '<0.1' : seg.share.toFixed(1)}%
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
