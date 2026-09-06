'use client';

/**
 * MoneyFlowHero
 *
 * The narrative centrepiece of the Follow-the-Money page. Mirrors the
 * BudgetFlowHero / DebtFlowHero layout so the three "money" pages feel
 * like one product:
 *
 *   - Eyebrow: source + FY
 *   - Headline: "KES X allocated → KES Y reached citizens"
 *   - Callout: leak ratio (how many shillings of every 100 the auditor flagged)
 *   - 3-stage horizontal waterfall: Allocated → Spent → Flagged. There is no
 *     Released stage: exchequer disbursements are not ingested from any source
 *     (see backend/routers/money_flow.py), and the `Released` entry left in
 *     STAGE_META below is parked for if they ever are, not rendered today.
 *   - Each gap is rendered explicitly above the bar so users can *see* the leak
 *   - Footer caveat points to the authoritative CoB + OAG sources
 */

import { motion } from 'framer-motion';
import { AlertTriangle, ArrowDownRight, Info } from 'lucide-react';
import { useState } from 'react';
import type { BudgetSource, MoneyFlowData } from '@/types';

interface Props {
  data: MoneyFlowData | null | undefined;
}

/**
 * What the Allocated stage's figure was read from, in this hero's terse
 * register. Keyed on the API's `budget_source` — the same vocabulary
 * ModelledDataNote switches its note on — because the stage's provenance is
 * not fixed: since the classification-split fix its amount is the Controller
 * of Budget's own CBIRR aggregate wherever the report has landed, and only a
 * CRA equitable-share projection period is the model this used to name
 * unconditionally.
 *
 * `mixed` is a pooled national figure over a partly-ingested CBIRR: naming
 * either single source there would be wrong about the other half of the money.
 */
const ALLOCATED_TAGLINE: Record<NonNullable<BudgetSource>, string> = {
  cob_cbirr: 'Controller of Budget CBIRR county aggregates',
  cra_model: 'CRA equitable-share model — not CoB-reported',
  mixed: 'CoB CBIRR where published; CRA model elsewhere',
};

/**
 * The same claim, in the footer's prose. It read "Allocations follow the
 * Commission on Revenue Allocation formula" unconditionally, on a page whose
 * allocation figure is now the Controller of Budget's own for every county the
 * CBIRR covers. Absent provenance says nothing about allocations rather than
 * defaulting to either source.
 */
function allocationProvenanceSentence(source: BudgetSource | undefined): string {
  switch (source) {
    case 'cob_cbirr':
      return "Allocations are the Controller of Budget's own county budget aggregates.";
    case 'cra_model':
      return 'Allocations follow the Commission on Revenue Allocation formula and are modelled, not Controller of Budget figures.';
    case 'mixed':
      return "Allocations are the Controller of Budget's own where it has published the county, and modelled on the Commission on Revenue Allocation formula elsewhere.";
    default:
      return '';
  }
}

const STAGE_META: Record<
  string,
  { label: string; tagline: string; gradStart: string; gradEnd: string; accent: string }
> = {
  Allocated: {
    label: 'Allocated',
    // Overridden per response from ALLOCATED_TAGLINE — see below. This value
    // is only reached when the API reports no provenance at all, and then no
    // tagline is rendered rather than this one.
    tagline: '',
    gradStart: '#2F6343',
    gradEnd: '#1F4A30',
    accent: '#1B3A2A',
  },
  Released: {
    label: 'Released',
    tagline: 'Exchequer releases to county accounts',
    gradStart: '#4B8564',
    gradEnd: '#2F6343',
    accent: '#2F6343',
  },
  Spent: {
    label: 'Spent',
    tagline: 'Counties executed on programmes & projects',
    gradStart: '#B38628',
    gradEnd: '#7D591A',
    accent: '#A6781F',
  },
  Flagged: {
    label: 'Flagged',
    tagline: 'OAG: irregular, unsupported, or wasteful',
    gradStart: '#9E3030',
    gradEnd: '#4C1616',
    accent: '#7E2424',
  },
};

function fmtT(kes: number | null | undefined): string {
  if (kes == null) return '—';
  const abs = Math.abs(kes);
  if (abs >= 1e12) return `${(kes / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(kes / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${(kes / 1e6).toFixed(0)}M`;
  return kes.toLocaleString();
}

const BAR_HEIGHT = 52;

export default function MoneyFlowHero({ data }: Props) {
  const [hover, setHover] = useState<string | null>(null);

  if (!data || !data.stages || data.stages.length === 0) return null;

  const stageMap = Object.fromEntries(
    data.stages.map((s) => [s.stage, s])
  ) as Record<string, (typeof data.stages)[number]>;

  const allocated = stageMap.Allocated?.amount ?? null;
  const released = stageMap.Released?.amount ?? null;
  const spent = stageMap.Spent?.amount ?? null;
  const flagged = stageMap.Flagged?.amount ?? null;

  // A projected / budgeted year will have allocation but no execution yet.
  const isProjected = allocated != null && spent == null && released == null;

  // The Allocated stage's provenance is per-response, not fixed — see
  // ALLOCATED_TAGLINE. Absent means the API published no budget, and then the
  // stage carries no source claim at all.
  const allocatedTagline = data.budget_source
    ? ALLOCATED_TAGLINE[data.budget_source]
    : '';

  const fy = data.fiscal_year;
  const countyLabel = data.county_name || 'All counties';

  // If we have no allocated anchor, nothing to draw.
  if (!allocated) {
    return (
      <EmptyHero fy={fy} reason='No CRA/CoB allocations have been recorded yet for this year.' />
    );
  }

  // Width of each bar segment is proportional to its amount vs. allocated (the anchor).
  const pct = (v: number | null | undefined) =>
    v != null && allocated > 0 ? Math.min(100, (v / allocated) * 100) : 0;

  const allocatedPct = 100;
  const spentPct = pct(spent);
  const flaggedPct = pct(flagged);

  const unspent =
    spent != null && (released ?? allocated) != null
      ? Math.max(0, (released ?? allocated)! - spent)
      : null;

  // Headline metric: flagged per 100 KES allocated
  const flaggedPer100 =
    flagged != null && allocated > 0 ? (flagged / allocated) * 100 : null;

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
          <div className='min-w-0'>
            <div className='text-[11px] font-semibold uppercase tracking-[0.18em] text-gov-forest/80 dark:text-emerald-100/80'>
              {isProjected ? 'CRA Budget Estimate' : 'Controller of Budget + OAG'} · FY {fy.replace('FY', '').trim()}
            </div>
            <h2 className='font-display text-[24px] sm:text-[28px] text-gov-dark dark:text-white leading-tight mt-1'>
              {isProjected
                ? <>KES {fmtT(allocated)} budgeted for {countyLabel.toLowerCase()}</>
                : <>KES {fmtT(allocated)} allocated, KES {fmtT(spent)} reached programmes</>}
            </h2>
            <p className='text-sm text-neutral-muted mt-1 max-w-2xl'>
              {isProjected
                ? 'This fiscal year is still being executed, so spending figures will appear as the Controller of Budget publishes quarterly reports.'
                : 'The waterfall below traces every shilling from Treasury allocation through execution, and the portion the Auditor General questioned (could not confirm was properly spent).'}
            </p>
          </div>

          {/* Leak callout — mirrors Budget page's debt-service callout */}
          {flaggedPer100 != null && (
            <div className='relative flex-shrink-0'>
              <div className='rounded-xl bg-gov-copper/10 border border-gov-copper/30 px-4 py-3 flex items-center gap-3 max-w-[18rem]'>
                <div className='flex-shrink-0 w-10 h-10 rounded-full bg-gov-copper/15 border border-gov-copper/40 flex items-center justify-center'>
                  <AlertTriangle size={18} className='text-gov-copper' />
                </div>
                <div>
                  <div className='text-[11px] uppercase tracking-wider font-semibold text-gov-copper'>
                    OAG · questioned ratio
                  </div>
                  <div className='font-display text-xl text-gov-dark dark:text-white leading-tight tabular-nums'>
                    KES {flaggedPer100.toFixed(2)}
                  </div>
                  <div className='text-[11px] text-neutral-muted leading-tight'>
                    of every KES 100 allocated was questioned by the Auditor General — could not be confirmed as properly spent (not proven loss)
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Waterfall */}
      <div className='px-5 sm:px-8 pb-2 pt-2'>
        <div className='flex items-baseline justify-between gap-2 mb-3'>
          <h3 className='text-[13px] font-semibold text-gov-dark dark:text-white tracking-tight'>
            Where the money went
          </h3>
          <span className='text-[11px] text-neutral-muted'>
            Anchor: KES {fmtT(allocated)} allocated
          </span>
        </div>

        <div className='space-y-4'>
          <WaterfallStage
            stage='Allocated'
            amount={allocated}
            widthPct={allocatedPct}
            hover={hover}
            setHover={setHover}
            tagline={allocatedTagline}
          />
          <StageGap
            label='Unspent — absorption shortfall'
            amount={unspent}
            unavailable={spent == null}
            reason={isProjected ? 'County spending still pending' : 'County execution still in progress'}
          />
          <WaterfallStage
            stage='Spent'
            amount={spent}
            widthPct={spentPct}
            hover={hover}
            setHover={setHover}
          />
          <StageGap
            label='Of which the Auditor General flagged'
            amount={flagged}
            unavailable={flagged == null}
            reason='OAG audit report not yet published for this year'
            severity='critical'
          />
          <WaterfallStage
            stage='Flagged'
            amount={flagged}
            widthPct={flaggedPct}
            hover={hover}
            setHover={setHover}
            severity='critical'
          />
        </div>
      </div>

      {/* Footer note */}
      <div className='px-5 sm:px-8 pb-5 pt-5'>
        <div className='flex items-start gap-2 text-[11px] text-neutral-muted/90 leading-relaxed border-t border-neutral-border/40 pt-3'>
          <Info size={13} className='mt-0.5 flex-shrink-0 text-gov-forest/70 dark:text-emerald-100/70' />
          <span>
            {allocationProvenanceSentence(data.budget_source)} Expenditure
            comes from the Controller of Budget&apos;s{' '}
            <em>County Budget Implementation Review Report</em> (CBIRR). Flagged amounts
            are the aggregate of findings the Auditor General <em>questioned</em>{' '}
            (classified as irregular, unsupported, or wasteful) in the consolidated county
            audit for the year — expenditure that could not be confirmed as properly
            supported, which is a <strong>query, not proven loss or theft</strong>. Where a
            stage is blank the source document has not yet been published — it isn&apos;t
            missing.
          </span>
        </div>
      </div>
    </motion.section>
  );
}

/* ───────────────────────── internal components ───────────────────────── */

function WaterfallStage({
  stage,
  amount,
  widthPct,
  hover,
  setHover,
  severity,
  tagline,
}: {
  stage: keyof typeof STAGE_META;
  amount: number | null | undefined;
  widthPct: number;
  hover: string | null;
  setHover: (s: string | null) => void;
  severity?: 'critical';
  /** Overrides the stage's fixed tagline where the claim is per-response —
   *  the Allocated stage's source. Empty means render no tagline, which is
   *  what an unpublished figure's provenance is. */
  tagline?: string;
}) {
  const meta = STAGE_META[stage];
  const caption = tagline ?? meta.tagline;
  const isActive = hover === stage;
  const isDim = hover != null && hover !== stage;
  const unavailable = amount == null;

  return (
    <div
      className={`relative transition-opacity duration-300 ${
        isDim ? 'opacity-50' : 'opacity-100'
      }`}
      onMouseEnter={() => setHover(stage)}
      onMouseLeave={() => setHover(null)}>
      <div className='flex items-baseline justify-between gap-2 mb-1'>
        <div className='flex items-center gap-2 min-w-0'>
          <span
            className='w-2 h-2 rounded-full flex-shrink-0'
            style={{ backgroundColor: meta.accent }}
            aria-hidden='true'
          />
          <span
            className='text-[12.5px] font-semibold tracking-tight truncate'
            style={{ color: meta.accent }}>
            {meta.label}
          </span>
          {caption && (
            <span className='text-[11px] text-neutral-muted hidden sm:inline truncate'>
              · {caption}
            </span>
          )}
        </div>
        <span className='font-display text-[15px] text-gov-dark dark:text-white tabular-nums flex-shrink-0'>
          {unavailable ? (
            <span className='text-neutral-muted text-[12px] font-normal italic'>
              not yet published
            </span>
          ) : (
            <>KES {fmtT(amount)}</>
          )}
        </span>
      </div>
      <div
        className='relative w-full rounded-lg bg-gov-sand/50 border border-neutral-border/30 overflow-hidden'
        style={{ height: BAR_HEIGHT }}>
        {!unavailable && (
          <motion.div
            initial={{ width: 0 }}
            whileInView={{ width: `${widthPct}%` }}
            viewport={{ once: true, margin: '-60px' }}
            transition={{ duration: 0.7, ease: 'easeOut', delay: 0.1 }}
            className='h-full relative'
            style={{
              background: `linear-gradient(90deg, ${meta.gradStart} 0%, ${meta.gradEnd} 100%)`,
              boxShadow: isActive
                ? '0 0 0 2px rgba(255,255,255,0.8) inset, 0 4px 16px rgba(0,0,0,0.12)'
                : 'none',
            }}>
            {widthPct > 15 && (
              <span className='absolute inset-0 flex items-center px-3 text-white text-[11px] font-semibold tracking-wide uppercase'>
                {widthPct.toFixed(0)}%
              </span>
            )}
            {severity === 'critical' && (
              <span
                aria-hidden='true'
                className='absolute inset-0 pointer-events-none'
                style={{
                  backgroundImage:
                    'repeating-linear-gradient(45deg, rgba(255,255,255,0.08) 0 6px, transparent 6px 14px)',
                }}
              />
            )}
          </motion.div>
        )}
        {unavailable && (
          <div className='h-full w-full flex items-center justify-center text-[11px] text-neutral-muted italic'>
            data unavailable
          </div>
        )}
      </div>
    </div>
  );
}

function StageGap({
  label,
  amount,
  unavailable,
  reason,
  severity,
}: {
  label: string;
  amount: number | null | undefined;
  unavailable: boolean;
  reason: string;
  severity?: 'critical';
}) {
  const isCritical = severity === 'critical';
  return (
    <div className='pl-4 flex items-center gap-2 text-[11.5px]'>
      <ArrowDownRight
        size={13}
        className={isCritical ? 'text-gov-copper flex-shrink-0' : 'text-neutral-muted flex-shrink-0'}
      />
      <span className={isCritical ? 'text-gov-copper font-medium' : 'text-neutral-muted'}>
        {label}
      </span>
      <span className='font-mono text-[11px] tabular-nums ml-auto'>
        {unavailable ? (
          <em className='text-neutral-muted/70 not-italic text-[11px]'>{reason}</em>
        ) : amount != null && amount > 0 ? (
          <span className={isCritical ? 'text-gov-copper font-semibold' : 'text-gov-dark/60 dark:text-white/60'}>
            − KES {fmtT(amount)}
          </span>
        ) : (
          <span className='text-emerald-600/80'>no shortfall</span>
        )}
      </span>
    </div>
  );
}

function EmptyHero({ fy, reason }: { fy: string; reason: string }) {
  return (
    <div className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-8 text-center'>
      <div className='text-[11px] font-semibold uppercase tracking-[0.18em] text-gov-forest/60 dark:text-emerald-100/60 mb-2'>
        Follow the Money · FY {fy}
      </div>
      <h2 className='font-display text-2xl text-gov-dark dark:text-white mb-2'>No data yet</h2>
      <p className='text-sm text-neutral-muted max-w-lg mx-auto'>{reason}</p>
    </div>
  );
}
