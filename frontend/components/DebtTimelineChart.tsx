'use client';

import { motion } from 'framer-motion';

interface DebtTimelineDataPoint {
  year: number;
  debt: number;
}

interface DebtTimelineChartProps {
  data?: DebtTimelineDataPoint[];
}

export default function DebtTimelineChart({ data }: DebtTimelineChartProps) {
  const timelineData: DebtTimelineDataPoint[] = data && data.length > 0 ? data : [];

  if (timelineData.length === 0) {
    return (
      <div className='h-80 w-full flex items-center justify-center'>
        <p className='text-sm text-gray-500 dark:text-neutral-muted/80'>Debt timeline data unavailable.</p>
      </div>
    );
  }

  const maxDebt = Math.max(...timelineData.map((item) => item.debt));
  const minYear = timelineData[0]?.year ?? 2015;
  const latestDebt = timelineData[timelineData.length - 1]?.debt ?? 0;
  const earliestDebt = timelineData[0]?.debt ?? 1;
  const growthPct = ((latestDebt / earliestDebt - 1) * 100).toFixed(0);
  const prevDebt =
    timelineData.length > 1 ? timelineData[timelineData.length - 2].debt : latestDebt;
  const addedLast = latestDebt - prevDebt;
  const avgGrowth =
    timelineData.length > 1
      ? (
          timelineData.reduce(
            (sum, item, idx) => (idx > 0 ? sum + (item.debt - timelineData[idx - 1].debt) : sum),
            0
          ) /
          (timelineData.length - 1)
        ).toFixed(0)
      : '0';

  return (
    <div className='h-80 w-full'>
      <div className='mb-4'>
        <p className='text-gray-600 dark:text-neutral-muted text-sm'>
          Kenya's debt has grown dramatically over the past decade, increasing by over
          <span className='font-semibold text-red-600'> {growthPct}%</span> since {minYear}.
        </p>
      </div>

      {/* Custom Line Chart */}
      <div className='relative h-64 bg-gradient-to-t from-red-50 to-transparent rounded-lg p-4'>
        <svg className='w-full h-full' viewBox='0 0 400 200' preserveAspectRatio='none'>
          {/* Grid lines */}
          {[0, 1, 2, 3, 4].map((i) => (
            <line
              key={i}
              x1='0'
              y1={i * 50}
              x2='400'
              y2={i * 50}
              stroke='#e5e7eb'
              strokeWidth='1'
              strokeDasharray='5,5'
            />
          ))}

          {/* Data line */}
          <motion.polyline
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 2, ease: 'easeInOut' }}
            fill='none'
            stroke='#ef4444'
            strokeWidth='3'
            strokeLinecap='round'
            strokeLinejoin='round'
            points={timelineData
              .map((item, index) => {
                const x = (index / (timelineData.length - 1)) * 400;
                const y = 200 - (item.debt / maxDebt) * 180;
                return `${x},${y}`;
              })
              .join(' ')}
          />

          {/* Data points */}
          {timelineData.map((item, index) => {
            const x = (index / (timelineData.length - 1)) * 400;
            const y = 200 - (item.debt / maxDebt) * 180;
            return (
              <motion.circle
                key={index}
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: index * 0.1, duration: 0.3 }}
                cx={x}
                cy={y}
                r='4'
                fill='#ef4444'
                stroke='white'
                strokeWidth='2'
                className='hover:r-6 transition-all cursor-pointer'
              />
            );
          })}
        </svg>

        {/* X-axis labels */}
        <div className='flex justify-between mt-2 px-2'>
          {timelineData.map((item, index) => (
            <div key={index} className='text-xs text-gray-500 dark:text-neutral-muted/80 font-medium'>
              {item.year}
            </div>
          ))}
        </div>

        {/* Y-axis labels */}
        <div className='absolute left-0 top-0 h-full flex flex-col justify-between py-4'>
          {[maxDebt, maxDebt * 0.75, maxDebt * 0.5, maxDebt * 0.25, 0].map((value, index) => (
            <div key={index} className='text-xs text-gray-500 dark:text-neutral-muted/80 font-medium -ml-12'>
              {value.toLocaleString()}B
            </div>
          ))}
        </div>
      </div>

      {/* Statistics */}
      <div className='mt-4 grid grid-cols-3 gap-4 text-center'>
        <div className='bg-red-50 rounded-lg p-3'>
          <div className='text-lg font-bold text-red-600'>+{growthPct}%</div>
          <div className='text-xs text-gray-600 dark:text-neutral-muted'>Growth since {minYear}</div>
        </div>
        <div className='bg-orange-50 rounded-lg p-3'>
          <div className='text-lg font-bold text-orange-600'>KES {addedLast.toLocaleString()}B</div>
          <div className='text-xs text-gray-600 dark:text-neutral-muted'>
            Added in {timelineData[timelineData.length - 1]?.year}
          </div>
        </div>
        <div className='bg-blue-50 rounded-lg p-3'>
          <div className='text-lg font-bold text-blue-600'>KES {avgGrowth}B</div>
          <div className='text-xs text-gray-600 dark:text-neutral-muted'>Avg annual growth</div>
        </div>
      </div>
    </div>
  );
}
