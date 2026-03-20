'use client';

import { MoneyFlowData, MoneyFlowStage } from '@/types';
import { motion } from 'framer-motion';
import { AlertTriangle, ArrowDown, Ban, ChevronDown, Loader2, TrendingDown } from 'lucide-react';
import React, { useMemo } from 'react';

/* ═══════════ Helpers ═══════════ */

function fmtKES(n: number | null | undefined): string {
  if (n == null || n === 0) return 'KES 0';
  const abs = Math.abs(n);
  if (abs >= 1e12) return `KES ${(n / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `KES ${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `KES ${(n / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `KES ${(n / 1e3).toFixed(0)}K`;
  return `KES ${n.toLocaleString()}`;
}

const STAGE_CONFIG: Record<
  string,
  { color: string; bgLight: string; border: string; icon: string }
> = {
  Allocated: {
    color: 'text-blue-700',
    bgLight: 'bg-blue-50',
    border: 'border-blue-200',
    icon: '💰',
  },
  Released: {
    color: 'text-emerald-700',
    bgLight: 'bg-emerald-50',
    border: 'border-emerald-200',
    icon: '🏦',
  },
  Spent: {
    color: 'text-amber-700',
    bgLight: 'bg-amber-50',
    border: 'border-amber-200',
    icon: '📊',
  },
  Flagged: {
    color: 'text-red-700',
    bgLight: 'bg-red-50',
    border: 'border-red-200',
    icon: '🚩',
  },
};

const GAP_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  'Withheld/Delayed': { bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-300' },
  'Unspent Funds': { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-300' },
  'Irregular/Unsupported Expenditure': {
    bg: 'bg-red-50',
    text: 'text-red-700',
    border: 'border-red-300',
  },
};

/* ═══════════ Stage Card ═══════════ */

function StageCard({
  stage,
  maxAmount,
  index,
}: {
  stage: MoneyFlowStage;
  maxAmount: number;
  index: number;
}) {
  const config = STAGE_CONFIG[stage.stage] || STAGE_CONFIG.Allocated;
  const barWidth =
    stage.amount && maxAmount > 0 ? Math.max((stage.amount / maxAmount) * 100, 8) : 0;

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3, delay: index * 0.1 }}
      className={`${config.bgLight} border ${config.border} rounded-xl p-4 relative`}>
      <div className='flex items-start justify-between gap-3'>
        <div className='flex-1 min-w-0'>
          <div className='flex items-center gap-2 mb-1'>
            <span className='text-lg'>{config.icon}</span>
            <span className={`text-xs font-semibold uppercase tracking-wider ${config.color}`}>
              {stage.stage}
            </span>
          </div>
          <div className='text-sm text-gray-600 mb-1'>{stage.label}</div>
          {stage.data_unavailable ? (
            <div className='flex items-center gap-1.5 text-gray-400'>
              <Ban size={14} />
              <span className='text-sm italic'>Data not available</span>
            </div>
          ) : (
            <div className={`text-xl font-bold ${config.color} tabular-nums`}>
              {fmtKES(stage.amount)}
            </div>
          )}
          {stage.source && (
            <div className='text-[11px] text-gray-400 mt-1'>Source: {stage.source}</div>
          )}
        </div>
      </div>

      {/* Proportional bar */}
      {!stage.data_unavailable && stage.amount != null && stage.amount > 0 && (
        <div className='mt-3 h-2 bg-gray-200/60 rounded-full overflow-hidden'>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${barWidth}%` }}
            transition={{ duration: 0.6, delay: index * 0.1 + 0.2, ease: 'easeOut' }}
            className={`h-full rounded-full ${
              stage.stage === 'Flagged'
                ? 'bg-red-500'
                : stage.stage === 'Spent'
                  ? 'bg-amber-500'
                  : stage.stage === 'Released'
                    ? 'bg-emerald-500'
                    : 'bg-blue-500'
            }`}
          />
        </div>
      )}
    </motion.div>
  );
}

/* ═══════════ Gap Indicator ═══════════ */

function GapIndicator({
  gap,
  label,
  index,
}: {
  gap: number;
  label: string;
  index: number;
}) {
  const colors = GAP_COLORS[label] || GAP_COLORS['Unspent Funds'];

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.2, delay: index * 0.1 + 0.15 }}
      className='flex items-center gap-3 px-4 py-2'>
      {/* Vertical connector line */}
      <div className='flex flex-col items-center'>
        <ArrowDown size={16} className='text-gray-300' />
      </div>

      {/* Gap pill */}
      <div
        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border border-dashed ${colors.bg} ${colors.border}`}>
        <TrendingDown size={14} className={colors.text} />
        <div>
          <span className={`text-xs font-semibold ${colors.text}`}>{label}</span>
          <span className={`text-sm font-bold ml-2 ${colors.text} tabular-nums`}>
            {fmtKES(gap)}
          </span>
        </div>
      </div>
    </motion.div>
  );
}

/* ═══════════ Efficiency Score Ring ═══════════ */

function EfficiencyRing({ score }: { score: number }) {
  const size = 96;
  const stroke = 6;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (Math.min(score, 100) / 100) * circ;
  const color = score >= 70 ? '#22c55e' : score >= 50 ? '#f59e0b' : '#ef4444';
  const label = score >= 70 ? 'Good' : score >= 50 ? 'Fair' : 'Poor';

  return (
    <div className='flex flex-col items-center'>
      <div
        className='relative inline-flex items-center justify-center'
        style={{ width: size, height: size }}>
        <svg width={size} height={size} className='-rotate-90'>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill='none'
            stroke='#f3f4f6'
            strokeWidth={stroke}
          />
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill='none'
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap='round'
            strokeDasharray={circ}
            initial={{ strokeDashoffset: circ }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 1, delay: 0.5, ease: 'easeOut' }}
          />
        </svg>
        <div className='absolute text-center'>
          <div className='text-xl font-bold text-gray-900'>{score.toFixed(0)}%</div>
        </div>
      </div>
      <div className='text-xs font-semibold mt-1' style={{ color }}>
        {label} Efficiency
      </div>
    </div>
  );
}

/* ═══════════ Main Component ═══════════ */

interface FollowTheMoneyProps {
  data: MoneyFlowData | undefined;
  isLoading?: boolean;
  compact?: boolean;
}

export default function FollowTheMoney({ data, isLoading, compact }: FollowTheMoneyProps) {
  const maxAmount = useMemo(() => {
    if (!data?.stages) return 0;
    return Math.max(...data.stages.map((s) => s.amount || 0));
  }, [data]);

  if (isLoading) {
    return (
      <div className='flex items-center justify-center py-16'>
        <Loader2 className='w-6 h-6 animate-spin text-gov-sage' />
        <span className='ml-3 text-gov-dark/60 font-medium'>Tracing the money...</span>
      </div>
    );
  }

  if (!data || !data.stages || data.stages.length === 0) {
    return (
      <div className='text-center py-12 text-gray-400'>
        <AlertTriangle size={28} className='mx-auto mb-2 text-gray-300' />
        <p className='text-sm'>No money flow data available for this period.</p>
      </div>
    );
  }

  const hasAnyData = data.stages.some((s) => !s.data_unavailable);

  return (
    <div className='space-y-1'>
      {/* Header row with efficiency score */}
      {!compact && (
        <div className='flex items-center justify-between mb-4'>
          <div>
            <h3 className='text-sm font-semibold text-gray-800'>{data.county_name}</h3>
            <p className='text-xs text-gray-500'>FY {data.fiscal_year}</p>
          </div>
          {data.efficiency_score != null && <EfficiencyRing score={data.efficiency_score} />}
        </div>
      )}

      {/* Compact efficiency display */}
      {compact && data.efficiency_score != null && (
        <div className='flex items-center justify-end mb-3'>
          <div className='flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-1.5'>
            <span className='text-xs text-gray-500'>Efficiency:</span>
            <span
              className={`text-sm font-bold ${
                data.efficiency_score >= 70
                  ? 'text-emerald-600'
                  : data.efficiency_score >= 50
                    ? 'text-amber-600'
                    : 'text-red-600'
              }`}>
              {data.efficiency_score.toFixed(1)}%
            </span>
          </div>
        </div>
      )}

      {/* Waterfall stages */}
      {data.stages.map((stage, i) => {
        // The next stage's gap_from_prev describes the leak BETWEEN stage i and i+1
        const nextStage = i < data.stages.length - 1 ? data.stages[i + 1] : null;
        const showGap =
          nextStage &&
          nextStage.gap_from_prev != null &&
          nextStage.gap_from_prev > 0;

        return (
          <React.Fragment key={stage.stage}>
            <StageCard stage={stage} maxAmount={maxAmount} index={i} />
            {showGap && (
              <GapIndicator
                gap={nextStage!.gap_from_prev!}
                label={nextStage!.gap_label || 'Gap'}
                index={i}
              />
            )}
            {/* Connector arrow when no gap to show */}
            {!showGap && i < data.stages.length - 1 && (
              <div className='flex justify-center py-1'>
                <ArrowDown size={16} className='text-gray-300' />
              </div>
            )}
          </React.Fragment>
        );
      })}

      {/* Waste summary */}
      {hasAnyData && data.total_waste_estimate != null && data.total_waste_estimate > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className='bg-red-50 border border-red-200 rounded-xl p-4 mt-3'>
          <div className='flex items-center gap-3'>
            <div className='w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0'>
              <AlertTriangle size={20} className='text-red-600' />
            </div>
            <div>
              <div className='text-sm font-semibold text-red-900'>
                {fmtKES(data.total_waste_estimate)} Flagged by Auditors
              </div>
              <div className='text-xs text-red-700'>
                Irregular or unsupported expenditure identified by the Office of the Auditor General
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}

/* ═══════════ Year Selector ═══════════ */

export function YearSelector({
  value,
  onChange,
  years,
}: {
  value: string;
  onChange: (year: string) => void;
  years: string[];
}) {
  return (
    <div className='relative inline-block'>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className='text-sm px-3 py-1.5 rounded-lg bg-white border border-gray-200 text-gray-700 focus:outline-none focus:ring-2 focus:ring-gov-sage/30 focus:border-gov-sage appearance-none pr-8 cursor-pointer'
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")`,
          backgroundRepeat: 'no-repeat',
          backgroundPosition: 'right 8px center',
        }}>
        {years.map((y) => (
          <option key={y} value={y}>
            FY {y}
          </option>
        ))}
      </select>
    </div>
  );
}
