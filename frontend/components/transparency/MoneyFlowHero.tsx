'use client';

/**
 * MoneyFlowHero
 *
 * The narrative centrepiece of the Follow-the-Money page, using the
 * approved open layout and directly labeled proportional measures:
 *
 *   - Eyebrow: source + FY
 *   - Headline: "KES X allocated → KES Y reached citizens"
 *   - Callout: leak ratio (how many shillings of every 100 the auditor flagged)
 *   - 3-stage horizontal waterfall: Allocated → Spent → Flagged. There is no
 *     Released stage: exchequer disbursements are not ingested from any source
 *     (see backend/routers/money_flow.py).
 *   - Each gap is rendered explicitly above the bar so users can *see* the leak
 *   - Footer caveat points to the authoritative CoB + OAG sources
 */

import { AlertTriangle, ArrowDownRight, Info } from 'lucide-react';
import type { BudgetSource, MoneyFlowData } from '@/types';
import { isProjectedMoneyFlow } from './moneyFlowPresentation';
import styles from './MoneyFlowPresentation.module.css';

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

const SOURCE_LABEL: Record<NonNullable<BudgetSource>, string> = {
  cob_cbirr: 'Controller of Budget CBIRR',
  cra_model: 'CRA Budget Estimate',
  mixed: 'CoB CBIRR + CRA model',
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

const STAGE_META = {
  Allocated: { label: 'Allocated', tagline: '', tone: 'good' },
  Spent: {
    label: 'Spent',
    tagline: 'Counties executed on programmes & projects',
    tone: 'fair',
  },
  Flagged: {
    label: 'Flagged',
    tagline: 'OAG: irregular, unsupported, or wasteful',
    tone: 'low',
  },
} as const;

function fmtT(kes: number | null | undefined): string {
  if (kes == null) return '—';
  const abs = Math.abs(kes);
  if (abs >= 1e12) return `${(kes / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(kes / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${(kes / 1e6).toFixed(0)}M`;
  return kes.toLocaleString();
}

export default function MoneyFlowHero({ data }: Props) {
  if (!data || !data.stages || data.stages.length === 0) return null;

  const stageMap = Object.fromEntries(data.stages.map((s) => [s.stage, s])) as Record<
    string,
    (typeof data.stages)[number]
  >;

  const allocated = stageMap.Allocated?.amount ?? null;
  const released = stageMap.Released?.amount ?? null;
  const spent = stageMap.Spent?.amount ?? null;
  const flagged = stageMap.Flagged?.amount ?? null;

  const isProjected = isProjectedMoneyFlow(data);

  // The Allocated stage's provenance is per-response, not fixed — see
  // ALLOCATED_TAGLINE. Absent means the API published no budget, and then the
  // stage carries no source claim at all.
  const allocatedTagline = data.budget_source ? ALLOCATED_TAGLINE[data.budget_source] : '';

  const fy = data.fiscal_year;
  const countyLabel = data.county_name || 'All counties';

  // If we have no allocated anchor, nothing to draw.
  if (allocated == null || allocated === 0) {
    return (
      <EmptyHero
        fy={fy}
        title={allocated === 0 ? 'Reported allocation: KES 0' : 'Allocation unavailable'}
        reason={
          allocated === 0
            ? 'Percentage comparisons cannot be calculated against a zero allocation. Other available national figures remain in the summary below.'
            : 'A complete national allocation is unavailable for this period. Other available national figures remain in the summary below.'
        }
      />
    );
  }

  // Width of each bar segment is proportional to its amount vs. allocated (the anchor).
  const pct = (v: number | null | undefined) =>
    v != null && allocated > 0 ? Math.min(100, (v / allocated) * 100) : 0;

  const allocatedPct = allocated > 0 ? 100 : 0;
  const spentPct = pct(spent);
  const flaggedPct = pct(flagged);

  const unspent =
    spent != null && (released ?? allocated) != null
      ? Math.max(0, (released ?? allocated)! - spent)
      : null;

  // Headline metric: flagged per 100 KES allocated
  const flaggedPer100 = flagged != null && allocated > 0 ? (flagged / allocated) * 100 : null;

  return (
    <section className={`${styles.presentation} ${styles.flow}`} aria-labelledby='money-flow-title'>
      <header className={styles.flowHead}>
        <p className={styles.sourceLabel}>
          {data.budget_source ? SOURCE_LABEL[data.budget_source] : 'Allocation source unavailable'}
          {flagged != null ? ' + OAG' : ''} · FY {fy.replace('FY', '').trim()}
        </p>
        <h2 id='money-flow-title' className={styles.flowTitle}>
          {isProjected ? (
            <>
              KES {fmtT(allocated)} budgeted for {countyLabel.toLowerCase()}
            </>
          ) : spent == null ? (
            <>KES {fmtT(allocated)} allocated; spending unavailable</>
          ) : (
            <>
              KES {fmtT(allocated)} allocated, KES {fmtT(spent)} reached programmes
            </>
          )}
        </h2>
        <p className={styles.flowDescription}>
          {isProjected
            ? 'This allocation is modelled. Spending figures will appear when sourced Controller of Budget reports are available.'
            : 'The waterfall below traces every shilling from Treasury allocation through execution, and the portion the Auditor General questioned (could not confirm was properly spent).'}
        </p>
        {flaggedPer100 != null && (
          <div className={styles.questionedRatio} data-tone={flaggedPer100 > 0 ? 'low' : 'neutral'}>
            {flaggedPer100 > 0 ? (
              <AlertTriangle size={18} aria-hidden='true' />
            ) : (
              <Info size={18} aria-hidden='true' />
            )}
            <span>OAG · questioned ratio</span>
            <strong>KES {flaggedPer100.toFixed(2)}</strong>
            <p>
              of every KES 100 allocated was questioned by the Auditor General — could not be
              confirmed as properly spent (not proven loss)
            </p>
          </div>
        )}
      </header>
      <div className={styles.chartHeading}>
        <h3>Where the money went</h3>
        <span>Anchor: KES {fmtT(allocated)} allocated</span>
      </div>
      <WaterfallStage
        stage='Allocated'
        amount={allocated}
        widthPct={allocatedPct}
        tagline={allocatedTagline}
      />
      <StageGap
        label='Unspent — absorption shortfall'
        amount={unspent}
        unavailable={spent == null}
        reason='Spending data unavailable for this reporting period'
      />
      <WaterfallStage stage='Spent' amount={spent} widthPct={spentPct} />
      <StageGap
        label='Of which the Auditor General flagged'
        amount={flagged}
        unavailable={flagged == null}
        reason='OAG audit report not yet published for this year'
      />
      <WaterfallStage stage='Flagged' amount={flagged} widthPct={flaggedPct} />
      <div className={styles.flowCaveat}>
        <Info size={16} aria-hidden='true' />
        <p>
          {allocationProvenanceSentence(data.budget_source)} Expenditure comes from the Controller
          of Budget&apos;s <em>County Budget Implementation Review Report</em> (CBIRR). Flagged
          amounts are the aggregate of findings the Auditor General <em>questioned</em> (classified
          as irregular, unsupported, or wasteful) in the consolidated county audit for the year —
          expenditure that could not be confirmed as properly supported, which is a{' '}
          <strong>query, not proven loss or theft</strong>. Where a stage is blank the source
          document has not yet been published — it isn&apos;t missing.
        </p>
      </div>
    </section>
  );
}

/* ───────────────────────── internal components ───────────────────────── */

function WaterfallStage({
  stage,
  amount,
  widthPct,
  tagline,
}: {
  stage: keyof typeof STAGE_META;
  amount: number | null | undefined;
  widthPct: number;
  tagline?: string;
}) {
  const meta = STAGE_META[stage];
  const caption = tagline ?? meta.tagline;
  const unavailable = amount == null;
  return (
    <div data-tone={unavailable || amount === 0 ? 'neutral' : meta.tone}>
      <div className={styles.stageHeading}>
        <div className={styles.stageName}>
          {meta.label}
          {caption && <small>{caption}</small>}
        </div>
        <p className={styles.stageAmount}>
          {unavailable ? 'Not yet published' : `KES ${fmtT(amount)}`}
        </p>
      </div>
      {unavailable ? (
        <div className={styles.stageMissing}>
          Data unavailable — no published amount for this reporting period.
        </div>
      ) : (
        <>
          <div
            className={styles.stageTrack}
            role='img'
            aria-label={`${meta.label}: KES ${fmtT(amount)}, ${widthPct.toFixed(0)}% of allocation`}>
            <div className={styles.stageFill} style={{ width: `${widthPct}%` }} />
          </div>
          <p className={styles.stagePercentage}>{widthPct.toFixed(0)}% of the allocation</p>
        </>
      )}
    </div>
  );
}

function StageGap({
  label,
  amount,
  unavailable,
  reason,
}: {
  label: string;
  amount: number | null | undefined;
  unavailable: boolean;
  reason: string;
}) {
  return (
    <div className={styles.stageGap}>
      <ArrowDownRight size={14} aria-hidden='true' />
      <span>{label}</span>
      <span>
        {unavailable
          ? reason
          : amount != null && amount > 0
            ? `− KES ${fmtT(amount)}`
            : 'no shortfall'}
      </span>
    </div>
  );
}

function EmptyHero({ fy, title, reason }: { fy: string; title: string; reason: string }) {
  return (
    <div className='rounded-2xl bg-white dark:bg-surface-base border border-neutral-border/40 shadow-surface p-8 text-center'>
      <div className='text-[11px] font-semibold uppercase tracking-[0.18em] text-gov-forest/60 dark:text-emerald-100/60 mb-2'>
        Follow the Money · FY {fy}
      </div>
      <h2 className='font-display text-2xl text-gov-dark dark:text-white mb-2'>{title}</h2>
      <p className='text-sm text-neutral-muted max-w-lg mx-auto'>{reason}</p>
    </div>
  );
}
