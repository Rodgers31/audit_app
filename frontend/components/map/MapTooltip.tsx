/**
 * MapTooltip – glass-card styled hover tooltip matching dashboard aesthetic.
 * Shows county audit status, budget utilisation and financial alerts.
 */
'use client';

import { County } from '@/types';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  ArrowRight,
  Coins,
  Receipt,
  Scale,
  TrendingUp,
  X,
} from 'lucide-react';
import Link from 'next/link';

interface MapTooltipProps {
  county: County;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onCountyClick: (county: County) => void;
  /** When provided, renders an explicit close (X) button in the tooltip
   * corner. Used on touch devices where auto-dismiss-on-mouseleave would
   * close the tooltip before the user has time to read it. */
  onClose?: () => void;
  /** Cursor (or county centroid) anchor, in map-container local
   * coordinates. When set, the tooltip positions ITSELF just above/
   * beside the anchor — the user can slide the cursor up into the card
   * without losing hover. Omit to fall back to the legacy center-top
   * placement (used on touch where there is no mouse cursor). */
  anchor?: { x: number; y: number; containerWidth: number; containerHeight: number };
}

/** Tooltip intrinsic dimensions. Must stay in sync with the card's
 * `w-[min(18rem, ...)]` class below. 18rem = 288px. ~260px tall with
 * the default content; a bit of padding in the math is safe. */
const TIP_W = 288;
// Slightly taller than before to accommodate the status stripe, larger
// metric values, and button-styled CTA. Only used for anchor-placement
// math — the card itself is content-sized, so being ~10px off here just
// shifts the tooltip marginally from its ideal position.
const TIP_H = 290;
/** Gap between the cursor and the tooltip. The smaller this is, the
 * less neighboring-county territory the cursor must cross to reach the
 * tooltip — in dense central-Kenya clusters (Meru, Nairobi, Kiambu)
 * even a 12px gap was enough for SVG hit-testing to fire a neighbor's
 * onMouseEnter mid-transit. The inset-8 hit zone (32px) on the card
 * more than bridges this. */
const TIP_GAP = 6;

/** Place the tooltip relative to a cursor/centroid anchor with edge
 * collision. Prefers ABOVE the cursor (so the user can move up into
 * it without the cursor crossing the card's bottom edge on the way);
 * flips below if there is not enough room up top. Horizontally,
 * centers on the cursor but clamps inside the container. */
function placeAnchored(a: NonNullable<MapTooltipProps['anchor']>) {
  const { x, y, containerWidth: W, containerHeight: H } = a;
  // Horizontal: center on cursor, clamp 4px from either edge.
  let left = x - TIP_W / 2;
  left = Math.max(4, Math.min(left, W - TIP_W - 4));
  // Vertical: prefer above cursor; flip below if no room.
  let top = y - TIP_H - TIP_GAP;
  if (top < 4) top = Math.min(H - TIP_H - 4, y + TIP_GAP);
  top = Math.max(4, Math.min(top, H - TIP_H - 4));
  return { left, top };
}

/* ── helpers ── */

const fmtKES = (n: number | undefined): string => {
  if (!n || n === 0) return 'KES 0';
  if (n >= 1e9) return `KES ${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `KES ${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `KES ${(n / 1e3).toFixed(0)}K`;
  return `KES ${n}`;
};

const STATUS_CONFIG: Record<
  string,
  { bg: string; text: string; ring: string; dot: string; stripe: string }
> = {
  clean: {
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    ring: 'ring-emerald-200',
    dot: 'bg-emerald-500',
    stripe: 'bg-emerald-500',
  },
  qualified: {
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    ring: 'ring-amber-200',
    dot: 'bg-amber-500',
    stripe: 'bg-amber-500',
  },
  adverse: {
    bg: 'bg-red-50',
    text: 'text-red-700',
    ring: 'ring-red-200',
    dot: 'bg-red-500',
    stripe: 'bg-red-500',
  },
  disclaimer: {
    bg: 'bg-violet-50',
    text: 'text-violet-700',
    ring: 'ring-violet-200',
    dot: 'bg-violet-500',
    stripe: 'bg-violet-500',
  },
  pending: {
    bg: 'bg-gray-50 dark:bg-surface-elevated',
    text: 'text-gray-600 dark:text-neutral-muted',
    ring: 'ring-gray-200',
    dot: 'bg-gray-400',
    stripe: 'bg-gray-300',
  },
};

const fmtPopulation = (n?: number) => {
  if (!n) return null;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M residents`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K residents`;
  return `${n} residents`;
};

const utilizationClass = (u: number) =>
  u > 85 ? 'bg-emerald-500' : u > 70 ? 'bg-amber-500' : 'bg-red-500';

/* ── component ── */

export default function MapTooltip({
  county,
  onMouseEnter,
  onMouseLeave,
  onCountyClick,
  onClose,
  anchor,
}: MapTooltipProps) {
  const status = county.auditStatus || 'pending';
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending;

  const utilization = county.budgetUtilization || 0;
  const debtRatio =
    county.budget && county.budget > 0 ? ((county.debt || 0) / county.budget) * 100 : 0;
  const fundingGap = (county.budget || 0) - (county.moneyReceived || 0);
  const auditIssuesCount = county.auditIssues?.length || 0;

  // Two positioning modes:
  //   1. Anchor-driven (desktop hover): tooltip follows the cursor/centroid
  //      so the user can slide the cursor into the card without crossing
  //      another county. Framer-motion's animation composes because we set
  //      `left`/`top` via inline style and let `initial/animate` handle
  //      opacity + scale only (no X/Y transform to clobber).
  //   2. Center-top fallback (touch / no-anchor): the legacy placement.
  //      On touch there is no cursor to follow, so anchoring is pointless.
  const anchored = anchor ? placeAnchored(anchor) : null;
  const positionStyle: React.CSSProperties = anchored
    ? { left: anchored.left, top: anchored.top }
    : {};

  // When anchored we skip the -50% X shift (position is computed in
  // absolute px already); when falling back we keep the center-top
  // behaviour.
  const motionProps = anchored
    ? {
        initial: { opacity: 0, scale: 0.92, y: 14 },
        animate: { opacity: 1, scale: 1, y: 0 },
        exit: { opacity: 0, scale: 0.92, y: 14 },
      }
    : {
        initial: { opacity: 0, scale: 0.92, y: 14, x: '-50%' as const },
        animate: { opacity: 1, scale: 1, y: 0, x: '-50%' as const },
        exit: { opacity: 0, scale: 0.92, y: 14, x: '-50%' as const },
      };

  return (
    <motion.div
      {...motionProps}
      transition={{ type: 'spring', damping: 22, stiffness: 340 }}
      style={positionStyle}
      className={
        anchored
          ? 'absolute z-50'
          : 'absolute z-50 top-[18%] left-1/2'
      }>
      {/* Invisible hit-area so mouse doesn't lose hover in the gap.
          Wider than TIP_GAP by design: the card is "easy to catch"
          even if the cursor overshoots slightly while transiting from
          the county — the 32px pad + 6px TIP_GAP means the hit zone
          starts overlapping the county before the visual card does. */}
      <div
        className='absolute -inset-8 z-0'
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
      />

      <div
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        onClick={() => onCountyClick(county)}
        // Width caps at 18rem on wide screens but shrinks to leave 1rem
        // of viewport margin on either side so the tooltip never clips
        // off the right edge on mobile. Content inside uses truncate /
        // min-w-0 so labels reflow instead of overflowing the card.
        // `overflow-hidden` clips the status-stripe to the rounded-xl
        // corners so the accent doesn't square off the top edge.
        className='relative w-[min(18rem,calc(100vw-2rem))] rounded-xl bg-gradient-to-br from-white via-white to-gov-sand/30 dark:from-surface-elevated dark:via-surface-base dark:to-surface-elevated backdrop-blur-xl border border-white/60 dark:border-neutral-border shadow-[0_10px_40px_rgba(15,23,42,0.14)] overflow-hidden cursor-pointer transition-all duration-200 hover:shadow-[0_14px_48px_rgba(15,23,42,0.20)] hover:-translate-y-0.5'>
        {/* ── Status-colour stripe — visual cue for audit state before
            the reader parses the chip. Pending = gray (neutral). */}
        <div className={`h-1 w-full ${cfg.stripe}`} />

        <div className='p-4'>
          {/* ── Header ── */}
          <div className='flex items-start justify-between gap-2 mb-3'>
            <div className='min-w-0'>
              <h3 className='text-[16px] font-bold text-gov-dark dark:text-white truncate leading-tight'>
                {county.name}
              </h3>
              <p className='text-[11px] text-neutral-muted mt-0.5 truncate'>
                {[
                  fmtPopulation(county.population),
                  county.governor ? `Gov. ${county.governor.split(' ').slice(-1)[0]}` : null,
                  county.lastAuditDate
                    ? `Audited ${new Date(county.lastAuditDate).getFullYear()}`
                    : null,
                ]
                  .filter(Boolean)
                  .join(' · ') || 'County overview'}
              </p>
            </div>
            <div className='flex items-center gap-1.5 shrink-0'>
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ring-1 ${cfg.bg} ${cfg.text} ${cfg.ring}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                {status}
              </span>
              {onClose && (
                // Explicit close button — needed on touch devices where the
                // tooltip no longer auto-dismisses after a hover-leave timer.
                // Rendered as a real <button> (not a div) for screen readers
                // and to avoid the card's onClick swallowing the tap.
                <button
                  type='button'
                  aria-label={`Close ${county.name} tooltip`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onClose();
                  }}
                  className='inline-flex h-6 w-6 items-center justify-center rounded-full bg-gray-100 dark:bg-surface-elevated text-gray-500 dark:text-neutral-muted/80 hover:bg-gray-200 dark:bg-surface-sunken hover:text-gray-800 dark:text-neutral-text active:bg-gray-300 transition-colors'>
                  <X className='w-3.5 h-3.5' />
                </button>
              )}
            </div>
          </div>

          {/* ── Metrics row ── */}
          <div className='grid grid-cols-2 gap-2 mb-3'>
            {/* Budget utilisation */}
            <div className='rounded-lg border border-neutral-border/40 bg-white/70 dark:bg-surface-elevated p-2.5'>
              <div className='flex items-center gap-1 mb-1.5'>
                <Coins className='w-3 h-3 text-gov-forest/70 dark:text-emerald-100/70' />
                <span className='text-[10px] font-medium text-neutral-muted'>Utilisation</span>
              </div>
              <div className='flex items-baseline gap-1 mb-1.5'>
                <span className='text-[15px] font-bold text-gov-dark dark:text-white tabular-nums leading-none'>
                  {utilization.toFixed(0)}
                </span>
                <span className='text-[10px] font-medium text-neutral-muted'>%</span>
              </div>
              <div className='w-full h-1 rounded-full bg-gray-200/70'>
                <div
                  className={`h-1 rounded-full ${utilizationClass(utilization)} transition-all`}
                  style={{ width: `${Math.min(utilization, 100)}%` }}
                />
              </div>
            </div>

            {/* Debt ratio */}
            <div className='rounded-lg border border-neutral-border/40 bg-white/70 dark:bg-surface-elevated p-2.5'>
              <div className='flex items-center gap-1 mb-1.5'>
                <TrendingUp className='w-3 h-3 text-gov-gold/80' />
                <span className='text-[10px] font-medium text-neutral-muted'>Debt Ratio</span>
              </div>
              <div className='flex items-baseline gap-1 mb-0.5'>
                <span className='text-[15px] font-bold text-gov-dark dark:text-white tabular-nums leading-none'>
                  {debtRatio.toFixed(1)}
                </span>
                <span className='text-[10px] font-medium text-neutral-muted'>%</span>
              </div>
              <div className='text-[10px] text-neutral-muted truncate'>{fmtKES(county.debt)}</div>
            </div>
          </div>

          {/* ── Alerts (compact) ── */}
          <div className='space-y-1'>
            {fundingGap > 0 && (
              <AlertRow
                icon={<Scale className='w-3 h-3 text-amber-600' />}
                label='Funding gap'
                value={fmtKES(fundingGap)}
                tint='amber'
              />
            )}
            {auditIssuesCount > 0 && (
              <AlertRow
                icon={<AlertTriangle className='w-3 h-3 text-red-500' />}
                label='Audit issues'
                value={`${auditIssuesCount} found`}
                tint='red'
              />
            )}
            {(county.pendingBills ?? 0) > 0 && (
              <AlertRow
                icon={<Receipt className='w-3 h-3 text-violet-500' />}
                label='Pending bills'
                value={fmtKES(county.pendingBills)}
                tint='violet'
              />
            )}
          </div>

          {/* ── CTA ──
              Real Link, not just text. The card's wrapping onClick selects
              the county (drives the home-dashboard side panel), but this
              CTA is a distinct target for "take me to the full page". We
              stopPropagation so the card's onClick doesn't also fire the
              selection — the page transition makes that stale anyway.

              ?from=home-map is the signal the detail page uses to render
              "Back to map" + "All counties" shortcuts. InteractiveKenyaMap
              is only mounted on the home dashboard today, so the param is
              always accurate here; if that changes, hoist this into a
              prop. */}
          <Link
            href={`/counties/${county.id}?from=home-map`}
            onClick={(e) => e.stopPropagation()}
            className='mt-3 flex items-center justify-center gap-1.5 rounded-lg bg-gov-forest/[0.06] hover:bg-gov-forest hover:text-white px-3 py-2 text-[11px] font-semibold text-gov-forest dark:text-emerald-100 transition-colors group/cta'>
            View detailed analysis
            <ArrowRight className='w-3 h-3 transition-transform group-hover/cta:translate-x-0.5' />
          </Link>
        </div>
      </div>
    </motion.div>
  );
}

/* tiny helper row — severity-tinted background so red/amber/violet
 * alerts carry weight at a glance rather than blending into the card. */
const ALERT_TINT: Record<
  'amber' | 'red' | 'violet',
  { bg: string; border: string; value: string }
> = {
  amber: { bg: 'bg-amber-50/70', border: 'border-amber-100', value: 'text-amber-800' },
  red: { bg: 'bg-red-50/70', border: 'border-red-100', value: 'text-red-800' },
  violet: { bg: 'bg-violet-50/70', border: 'border-violet-100', value: 'text-violet-800' },
};

function AlertRow({
  icon,
  label,
  value,
  tint,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tint: 'amber' | 'red' | 'violet';
}) {
  const t = ALERT_TINT[tint];
  return (
    <div
      className={`flex items-center justify-between rounded-md px-2 py-1.5 border ${t.bg} ${t.border}`}>
      <div className='flex items-center gap-1.5'>
        {icon}
        <span className='text-[10px] font-medium text-gray-700 dark:text-neutral-muted'>{label}</span>
      </div>
      <span className={`text-[10px] font-bold tabular-nums ${t.value}`}>{value}</span>
    </div>
  );
}
