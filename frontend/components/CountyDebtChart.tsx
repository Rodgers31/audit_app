'use client';

import { countyDebtRatio } from '@/components/map/MapUtilities';
import { countyDebt } from '@/lib/countyFigures';
import { County } from '@/types';
import { motion } from 'framer-motion';

interface CountyDebtChartProps {
  county: County;
}

export default function CountyDebtChart({ county }: CountyDebtChartProps) {
  const totalDebt = countyDebt(county);

  // Use actual pending bills data when available
  const debtComposition = [
    ...(county.pendingBills && county.pendingBills > 0
      ? [
          {
            type: 'Pending Bills',
            amount: county.pendingBills,
            color: '#10b981',
            description: 'Outstanding payments to suppliers',
          },
        ]
      : []),
    ...(totalDebt != null && totalDebt > (county.pendingBills ?? 0)
      ? [
          {
            type: 'Other Debt',
            amount: totalDebt - (county.pendingBills ?? 0),
            color: '#3b82f6',
            description: 'Loans and other obligations',
          },
        ]
      : []),
  ];

  const formatAmount = (amount: number | null | undefined) =>
    amount == null ? '—' : `KES ${(amount / 1e9).toFixed(1)}B`;

  // A share of an unpublished total is not a share of anything.
  const formatPercentage = (amount: number) =>
    totalDebt != null && totalDebt > 0 ? `${((amount / totalDebt) * 100).toFixed(1)}%` : '—';

  const debtRatio = countyDebtRatio(county);
  // A per-capita figure needs a population someone counted. Absent, it is
  // withheld — not divided by the 0 the API used to send.
  const perCapitaDebt =
    totalDebt != null && county.population != null && county.population > 0
      ? Math.round(totalDebt / county.population)
      : null;

  // Calculate pie chart segments
  const createPieSlice = (startAngle: number, endAngle: number, color: string) => {
    const centerX = 100;
    const centerY = 100;
    const radius = 80;

    const x1 = centerX + radius * Math.cos((startAngle * Math.PI) / 180);
    const y1 = centerY + radius * Math.sin((startAngle * Math.PI) / 180);
    const x2 = centerX + radius * Math.cos((endAngle * Math.PI) / 180);
    const y2 = centerY + radius * Math.sin((endAngle * Math.PI) / 180);

    const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1';

    const pathData = [
      'M',
      centerX,
      centerY,
      'L',
      x1,
      y1,
      'A',
      radius,
      radius,
      0,
      largeArcFlag,
      1,
      x2,
      y2,
      'Z',
    ].join(' ');

    return pathData;
  };

  let currentAngle = -90; // Start from top

  return (
    <div className='space-y-6'>
      {/* Pie Chart */}
      <div className='flex justify-center'>
        <div className='relative'>
          <svg width='200' height='200' className='drop-shadow-lg'>
            {debtComposition.map((segment, index) => {
              const percentage = ((segment.amount / (totalDebt as number)) * 100) || 0;
              const angle = (percentage / 100) * 360;
              const startAngle = currentAngle;
              const endAngle = currentAngle + angle;
              currentAngle += angle;

              return (
                <motion.path
                  key={segment.type}
                  d={createPieSlice(startAngle, endAngle, segment.color)}
                  fill={segment.color}
                  stroke='#ffffff'
                  strokeWidth='2'
                  initial={{ opacity: 0, scale: 0 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: index * 0.2, duration: 0.6 }}
                  className='hover:opacity-80 cursor-pointer'
                  style={{ transformOrigin: '100px 100px' }}
                />
              );
            })}
            {/* Center circle for donut effect */}
            <circle cx='100' cy='100' r='35' fill='white' stroke='#e2e8f0' strokeWidth='2' />
            <text
              x='100'
              y='95'
              textAnchor='middle'
              className='text-sm font-semibold fill-gray-900'>
              Total Debt
            </text>
            <text x='100' y='110' textAnchor='middle' className='text-xs fill-gray-600'>
              {formatAmount(totalDebt)}
            </text>
          </svg>
        </div>
      </div>

      {/* Legend */}
      <div className='space-y-3'>
        {debtComposition.map((segment, index) => (
          <motion.div
            key={segment.type}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.1 + 0.3, duration: 0.5 }}
            className='flex items-center justify-between p-3 bg-gray-50 dark:bg-surface-elevated rounded-lg'>
            <div className='flex items-center gap-3'>
              <div className='w-4 h-4 rounded-full' style={{ backgroundColor: segment.color }} />
              <div>
                <div className='font-medium text-gray-900 dark:text-neutral-text'>{segment.type}</div>
                <div className='text-sm text-gray-600 dark:text-neutral-muted'>{segment.description}</div>
              </div>
            </div>
            <div className='text-right'>
              <div className='font-semibold text-gray-900 dark:text-neutral-text'>{formatAmount(segment.amount)}</div>
              <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>{formatPercentage(segment.amount)}</div>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Debt Metrics */}
      <div className='grid grid-cols-2 gap-4'>
        <div className='bg-red-50 rounded-xl p-4 border border-red-200'>
          <h5 className='font-semibold text-red-900 mb-1'>Debt-to-Budget Ratio</h5>
          <div className='text-2xl font-bold text-red-700'>
            {debtRatio != null ? `${debtRatio.toFixed(1)}%` : '—'}
          </div>
        </div>
        <div className='bg-blue-50 rounded-xl p-4 border border-blue-200'>
          <h5 className='font-semibold text-blue-900 mb-1'>Per Capita Debt</h5>
          <div className='text-2xl font-bold text-blue-700'>
            {perCapitaDebt != null ? `KES ${perCapitaDebt.toLocaleString()}` : '—'}
          </div>
        </div>
      </div>

      {/* Debt Analysis */}
      <div className='bg-yellow-50 rounded-xl p-4 border border-yellow-200'>
        <h5 className='font-semibold text-yellow-900 mb-2'>Debt Analysis</h5>
        <ul className='text-sm text-yellow-800 space-y-1'>
          <li>
            {debtRatio != null
              ? `• Debt represents ${debtRatio.toFixed(1)}% of annual budget`
              : '• Debt as a share of budget is not reported for this county'}
          </li>
          <li>
            {perCapitaDebt != null
              ? `• Each resident owes approximately KES ${perCapitaDebt.toLocaleString()}`
              : '• Per-resident debt is not reported for this county'}
          </li>
          {debtComposition.length > 0 && (
            <li>• Largest debt source: {debtComposition[0].type}</li>
          )}
        </ul>
      </div>
    </div>
  );
}
