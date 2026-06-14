'use client';

import { County } from '@/types';
import { motion } from 'framer-motion';

interface CountyDebtChartProps {
  county: County;
}

export default function CountyDebtChart({ county }: CountyDebtChartProps) {
  const totalDebt = county.debt ?? county.totalDebt ?? 0;
  const budget = county.budget ?? county.totalBudget ?? 0;

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
    ...(totalDebt > (county.pendingBills ?? 0)
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

  const formatAmount = (amount: number) => {
    return `KES ${(amount / 1e9).toFixed(1)}B`;
  };

  const formatPercentage = (amount: number) => {
    if (!totalDebt || totalDebt === 0) return '0%';
    return `${((amount / totalDebt) * 100).toFixed(1)}%`;
  };

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
              const percentage = (segment.amount / totalDebt) * 100;
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
            {budget > 0 ? ((totalDebt / budget) * 100).toFixed(1) : '0.0'}%
          </div>
        </div>
        <div className='bg-blue-50 rounded-xl p-4 border border-blue-200'>
          <h5 className='font-semibold text-blue-900 mb-1'>Per Capita Debt</h5>
          <div className='text-2xl font-bold text-blue-700'>
            KES{' '}
            {(county.population > 0
              ? Math.round(totalDebt / county.population)
              : 0
            ).toLocaleString()}
          </div>
        </div>
      </div>

      {/* Debt Analysis */}
      <div className='bg-yellow-50 rounded-xl p-4 border border-yellow-200'>
        <h5 className='font-semibold text-yellow-900 mb-2'>Debt Analysis</h5>
        <ul className='text-sm text-yellow-800 space-y-1'>
          <li>
            • Debt represents {budget > 0 ? ((totalDebt / budget) * 100).toFixed(1) : '0.0'}% of
            annual budget
          </li>
          <li>
            • Each resident owes approximately KES{' '}
            {(county.population > 0
              ? Math.round(totalDebt / county.population)
              : 0
            ).toLocaleString()}
          </li>
          <li>• Largest debt source: {debtComposition[0].type}</li>
        </ul>
      </div>
    </div>
  );
}
