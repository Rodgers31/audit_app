'use client';

import { motion } from 'framer-motion';

interface DebtBreakdownChartProps {
  domesticDebt?: number;
  externalDebt?: number;
  data?: any;
}

export default function DebtBreakdownChart({
  domesticDebt,
  externalDebt,
  data,
}: DebtBreakdownChartProps) {
  // Use props or extract from data object — no hardcoded fallbacks
  const domestic = domesticDebt || data?.domestic_debt || data?.breakdown?.domestic_debt || 0;
  const external = externalDebt || data?.external_debt || data?.breakdown?.external_debt || 0;

  const DEBT_BREAKDOWN = [
    {
      type: 'External Debt',
      amount: external,
      color: '#ef4444',
      description: 'Borrowed from international lenders',
    },
    {
      type: 'Domestic Debt',
      amount: domestic,
      color: '#f59e0b',
      description: 'Borrowed from local institutions',
    },
  ];

  const totalDebt = DEBT_BREAKDOWN.reduce((sum, item) => sum + item.amount, 0);

  // Calculate angles for pie chart
  let currentAngle = 0;
  const segments = DEBT_BREAKDOWN.map((item) => {
    const percentage = (item.amount / totalDebt) * 100;
    const angle = (item.amount / totalDebt) * 360;
    const segment = {
      ...item,
      percentage,
      startAngle: currentAngle,
      endAngle: currentAngle + angle,
    };
    currentAngle += angle;
    return segment;
  });

  // Generate SVG path for pie segments
  const createPath = (
    centerX: number,
    centerY: number,
    radius: number,
    startAngle: number,
    endAngle: number
  ) => {
    const start = polarToCartesian(centerX, centerY, radius, endAngle);
    const end = polarToCartesian(centerX, centerY, radius, startAngle);
    const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1';

    return [
      'M',
      centerX,
      centerY,
      'L',
      start.x,
      start.y,
      'A',
      radius,
      radius,
      0,
      largeArcFlag,
      0,
      end.x,
      end.y,
      'Z',
    ].join(' ');
  };

  const polarToCartesian = (
    centerX: number,
    centerY: number,
    radius: number,
    angleInDegrees: number
  ) => {
    const angleInRadians = ((angleInDegrees - 90) * Math.PI) / 180.0;
    return {
      x: centerX + radius * Math.cos(angleInRadians),
      y: centerY + radius * Math.sin(angleInRadians),
    };
  };

  return (
    <div className='h-80 w-full'>
      <div className='mb-4'>
        <p className='text-gray-600 dark:text-neutral-muted text-sm'>
          Kenya's debt is split between{' '}
          <span className='font-semibold text-red-600'>external lenders</span> (World Bank, China,
          etc.) and <span className='font-semibold text-amber-600'>domestic sources</span> (local
          banks, pension funds).
        </p>
      </div>

      <div className='flex items-center justify-center h-64'>
        <div className='relative'>
          {/* Pie Chart */}
          <svg width='200' height='200' className='transform -rotate-90'>
            {segments.map((segment, index) => (
              <motion.path
                key={index}
                initial={{ opacity: 0, scale: 0 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: index * 0.3, duration: 0.6, ease: 'easeOut' }}
                d={createPath(100, 100, 80, segment.startAngle, segment.endAngle)}
                fill={segment.color}
                stroke='white'
                strokeWidth='3'
                className='hover:brightness-110 transition-all cursor-pointer'
              />
            ))}

            {/* Center circle for donut effect */}
            <circle cx='100' cy='100' r='40' fill='white' stroke='#e5e7eb' strokeWidth='2' />
          </svg>

          {/* Center text */}
          <div className='absolute inset-0 flex items-center justify-center'>
            <div className='text-center'>
              <div className='text-lg font-bold text-gray-800 dark:text-neutral-text'>
                KES {totalDebt.toLocaleString()}B
              </div>
              <div className='text-xs text-gray-500 dark:text-neutral-muted/80'>Total Debt</div>
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className='ml-8 space-y-4'>
          {segments.map((segment, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.2 + 0.5, duration: 0.5 }}
              className='flex items-center space-x-3'>
              <div
                className='w-4 h-4 rounded-full'
                style={{ backgroundColor: segment.color }}></div>
              <div>
                <div className='font-semibold text-gray-800 dark:text-neutral-text'>{segment.type}</div>
                <div className='text-sm text-gray-600 dark:text-neutral-muted'>
                  KES {segment.amount.toLocaleString()}B ({segment.percentage.toFixed(1)}%)
                </div>
                <div className='text-xs text-gray-500 dark:text-neutral-muted/80'>{segment.description}</div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Breakdown Stats */}
      <div className='mt-6 grid grid-cols-2 gap-4'>
        <div className='bg-red-50 rounded-lg p-4 text-center'>
          <div className='text-2xl font-bold text-red-600 mb-1'>
            {((DEBT_BREAKDOWN[0].amount / totalDebt) * 100).toFixed(1)}%
          </div>
          <div className='text-sm font-medium text-gray-700 dark:text-neutral-muted mb-1'>External Debt</div>
          <div className='text-xs text-gray-500 dark:text-neutral-muted/80'>Mainly from China, World Bank, IMF</div>
        </div>
        <div className='bg-amber-50 rounded-lg p-4 text-center'>
          <div className='text-2xl font-bold text-amber-600 mb-1'>
            {((DEBT_BREAKDOWN[1].amount / totalDebt) * 100).toFixed(1)}%
          </div>
          <div className='text-sm font-medium text-gray-700 dark:text-neutral-muted mb-1'>Domestic Debt</div>
          <div className='text-xs text-gray-500 dark:text-neutral-muted/80'>Banks, pension funds, treasury bills</div>
        </div>
      </div>
    </div>
  );
}
