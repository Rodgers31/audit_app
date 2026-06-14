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
 *      — Tax, non-tax, new borrowing, other financing
 *
 *   2. Where does it actually go?       (Uses)
 *      — Debt service, recurrent non-debt, development, counties, other
 *
 * The striking number that anchors the whole page is the debt-service-to-
 * revenue ratio: "for every 100 shillings government collects, X goes to
 * debt service BEFORE anything else is funded." We surface this as a
 * large callout between the two bars.
 *
 * Hover state: lifting a segment highlights it and reveals a detail popover
 * with the underlying KES value, share, and plain-English interpretation.
 */

import { motion } from 'framer-motion';
import { ArrowDownRight, Info } from 'lucide-react';
import { useMemo, useState } from 'react';

export interface FlowHeroInput {
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
  const budget = data?.appropriated_budget ?? 0;
  const revenue = data?.total_revenue ?? 0;
  const tax = data?.tax_revenue ?? 0;
  const nonTax = data?.non_tax_revenue ?? 0;
  const borrowing = data?.total_borrowing ?? 0;
  const debtService = data?.debt_service_cost ?? 0;
  const dev = data?.development_spending ?? 0;
  const recurrent = data?.recurrent_spending ?? 0;
  const counties = data?.county_allocation ?? 0;

  // Derived
  const otherFinancing = Math.max(0, budget - tax - nonTax - borrowing);
  const recurrentNonDebt = Math.max(0, recurrent - debtService);
  const otherSpend = Math.max(0, budget - recurrent - dev - counties);

  // "shillings-per-shilling-of-revenue" metric: debt service vs total revenue
  const debtServicePct = revenue > 0 ? (debtService / revenue) * 100 : 0;
  const debtServiceCents =
    data?.debt_service_per_shilling ?? Math.round(debtServicePct);

  /* ── Sources (money in) ── */
  const sources: Segment[] = useMemo(
    () => [
      {
        key: 'tax',
        label: 'Tax revenue',
        valueB: tax,
        share: pct(tax, budget),
        gradStart: '#2F6343',
        gradEnd: '#1F4A30',
        accent: '#1B3A2A',
        note: 'PAYE, VAT, corporation tax, customs, excise — collected by KRA.',
      },
      {
        key: 'nonTax',
        label: 'Non-tax revenue',
        valueB: nonTax,
        share: pct(nonTax, budget),
        gradStart: '#4B8564',
        gradEnd: '#2F6343',
        accent: '#2F6343',
        note: 'Licence fees, interest, SOE dividends, A-in-A receipts.',
      },
      {
        key: 'borrowing',
        label: 'New borrowing',
        valueB: borrowing,
        share: pct(borrowing, budget),
        gradStart: '#B83E3E',
        gradEnd: '#7E2424',
        accent: '#9E3030',
        note: 'Eurobonds, domestic T-bonds, T-bills, loans — adds to the debt stock.',
      },
      {
        key: 'otherFin',
        label: 'Other financing',
        valueB: otherFinancing,
        share: pct(otherFinancing, budget),
        gradStart: '#B38628',
        gradEnd: '#7D591A',
        accent: '#A6781F',
        note: 'Grants, drawdowns, carryover balances, one-off receipts.',
      },
    ],
    [tax, nonTax, borrowing, otherFinancing, budget]
  );

  /* ── Uses (money out) ── */
  const uses: Segment[] = useMemo(
    () => [
      {
        key: 'debtService',
        label: 'Debt service',
        valueB: debtService,
        share: pct(debtService, budget),
        gradStart: '#9E3030',
        gradEnd: '#4C1616',
        accent: '#7E2424',
        note:
          'Interest + principal repayment on past borrowing. Paid before any program runs.',
      },
      {
        key: 'recurrentNonDebt',
        label: 'Recurrent (ex-debt)',
        valueB: recurrentNonDebt,
        share: pct(recurrentNonDebt, budget),
        gradStart: '#6B7280',
        gradEnd: '#3F4754',
        accent: '#4B5563',
        note:
          'Salaries, pensions, operations & maintenance — keeps existing services running.',
      },
      {
        key: 'development',
        label: 'Development',
        valueB: dev,
        share: pct(dev, budget),
        gradStart: '#3B7251',
        gradEnd: '#1F4A30',
        accent: '#2F6343',
        note:
          'New infrastructure and capital projects — roads, hospitals, water systems.',
      },
      {
        key: 'counties',
        label: 'Counties',
        valueB: counties,
        share: pct(counties, budget),
        gradStart: '#4B8564',
        gradEnd: '#295B3E',
        accent: '#3E7655',
        note:
          "Equitable share transferred to 47 county governments under the Constitution.",
      },
      {
        key: 'otherSpend',
        label: 'Other (CFS etc.)',
        valueB: otherSpend,
        share: pct(otherSpend, budget),
        gradStart: '#B38628',
        gradEnd: '#7D591A',
        accent: '#A6781F',
        note:
          'Consolidated Fund Services: constitutional salaries, pensions, guaranteed payments.',
      },
    ],
    [debtService, recurrentNonDebt, dev, counties, otherSpend, budget]
  );

  if (!data || !budget) {
    return null;
  }

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
              KES {fmtT(budget)} in, KES {fmtT(budget)} out
            </h2>
            <p className='text-sm text-neutral-muted mt-1 max-w-2xl'>
              Every shilling the national government plans to spend this fiscal year must
              first be raised. Here&apos;s how the plumbing works — sources on top,
              uses on the bottom.
            </p>
          </div>
          {/* Debt-service callout */}
          <div className='relative flex-shrink-0'>
            <div className='rounded-xl bg-gov-copper/10 border border-gov-copper/30 px-4 py-3 flex items-center gap-3 max-w-xs'>
              <div className='flex-shrink-0 w-10 h-10 rounded-full bg-gov-copper/15 border border-gov-copper/40 flex items-center justify-center'>
                <ArrowDownRight size={18} className='text-gov-copper' />
              </div>
              <div>
                <div className='text-[10px] uppercase tracking-wider font-semibold text-gov-copper'>
                  Treasury APDMR · {fy}
                </div>
                <div className='font-display text-xl text-gov-dark dark:text-white leading-tight tabular-nums'>
                  KES {debtServiceCents.toFixed(1)}
                </div>
                <div className='text-[11px] text-neutral-muted leading-tight'>
                  of every KES 100 of revenue services the debt (interest + principal)
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Sources bar */}
      <div className='px-5 sm:px-8 pb-1 pt-2'>
        <div className='flex items-baseline justify-between gap-2 mb-2'>
          <h3 className='text-[13px] font-semibold text-gov-dark dark:text-white tracking-tight'>
            Where the money comes from
          </h3>
          <span className='text-[11px] text-neutral-muted'>
            Total budget KES {fmtT(budget)}
          </span>
        </div>
        <FlowBar segments={sources} total={budget} hover={hover} setHover={setHover} />
        <SegmentLegend segments={sources} hover={hover} setHover={setHover} />
      </div>

      {/* Connector */}
      <div className='flex items-center justify-center py-2'>
        <div className='flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-neutral-muted/80 font-semibold'>
          <span className='h-px w-8 bg-neutral-border' />
          Flows into
          <span className='h-px w-8 bg-neutral-border' />
        </div>
      </div>

      {/* Uses bar */}
      <div className='px-5 sm:px-8 pb-7 pt-1'>
        <div className='flex items-baseline justify-between gap-2 mb-2'>
          <h3 className='text-[13px] font-semibold text-gov-dark dark:text-white tracking-tight'>
            Where it actually goes
          </h3>
          <span className='text-[11px] text-neutral-muted'>
            Debt service alone: KES {fmtT(debtService)} ({debtServicePct.toFixed(0)}% of revenue)
          </span>
        </div>
        <FlowBar segments={uses} total={budget} hover={hover} setHover={setHover} />
        <SegmentLegend segments={uses} hover={hover} setHover={setHover} />
      </div>

      {/* Footer note */}
      <div className='px-5 sm:px-8 pb-5 pt-0'>
        <div className='flex items-start gap-2 text-[11px] text-neutral-muted/90 leading-relaxed border-t border-neutral-border/40 pt-3'>
          <Info size={13} className='mt-0.5 flex-shrink-0 text-gov-forest/70 dark:text-emerald-100/70' />
          <span>
            Debt-service figure follows the National Treasury <em>Annual Public Debt
            Management Report</em> definition — interest payments{' '}
            <strong>plus</strong> principal redemptions, domestic + external — as a share
            of tax + non-tax revenue. Year-end actuals arrive from the Controller of
            Budget in the National Government Budget Implementation Review Report.
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
                <div className='text-[10px] font-semibold uppercase tracking-wider' style={{ color: seg.accent }}>
                  {seg.label}
                </div>
                <div className='text-sm font-bold text-gov-dark dark:text-white tabular-nums leading-tight'>
                  KES {fmtT(seg.valueB)} · {seg.share.toFixed(1)}%
                </div>
                <div className='text-[10.5px] text-neutral-muted leading-snug mt-1'>
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
              <span className='block text-[10.5px] font-semibold text-gov-dark dark:text-white truncate'>
                {seg.label}
              </span>
              <span className='block text-[10px] text-neutral-muted tabular-nums'>
                KES {fmtT(seg.valueB)} · {seg.share.toFixed(1)}%
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
