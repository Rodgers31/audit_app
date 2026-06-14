'use client';

import { motion } from 'framer-motion';

interface BudgetAllocation {
  sector: string;
  amount: number;
  percentage: number;
  icon: any;
  color: string;
}

interface BudgetData {
  total: number;
  allocations: BudgetAllocation[];
}

interface BudgetAllocationChartProps {
  data: BudgetData;
  comparisonData?: BudgetData | null;
  showComparison?: boolean;
}

export default function BudgetAllocationChart({
  data,
  comparisonData,
  showComparison,
}: BudgetAllocationChartProps) {
  const maxAmount = Math.max(...data.allocations.map((item) => item.amount));

  const formatCurrency = (amount: number) => {
    return `KES ${(amount / 1e12).toFixed(2)}T`;
  };

  const getComparisonData = (sector: string) => {
    if (!showComparison || !comparisonData) return null;

    const prevItem = comparisonData.allocations.find((item) => item.sector === sector);
    if (!prevItem) return null;

    const currentItem = data.allocations.find((item) => item.sector === sector);
    if (!currentItem) return null;

    const change = ((currentItem.amount - prevItem.amount) / prevItem.amount) * 100;
    return {
      change: change,
      isIncrease: change > 0,
      prevAmount: prevItem.amount,
    };
  };

  return (
    <div className='space-y-6'>
      {/* Chart Legend */}
      {showComparison && (
        <div className='flex justify-center gap-8 mb-6'>
          <div className='flex items-center gap-2'>
            <div className='w-4 h-4 bg-blue-500 rounded'></div>
            <span className='text-sm text-gray-600 dark:text-neutral-muted'>2024 Budget</span>
          </div>
          <div className='flex items-center gap-2'>
            <div className='w-4 h-4 bg-blue-200 rounded'></div>
            <span className='text-sm text-gray-600 dark:text-neutral-muted'>2023 Budget</span>
          </div>
        </div>
      )}

      {/* Stacked Bar Chart */}
      <div className='space-y-4'>
        {data.allocations
          .sort((a, b) => b.amount - a.amount)
          .map((item, index) => {
            const Icon = item.icon;
            const percentage = (item.amount / maxAmount) * 100;
            const comparison = getComparisonData(item.sector);
            const prevPercentage = comparison ? (comparison.prevAmount / maxAmount) * 100 : 0;

            return (
              <motion.div
                key={item.sector}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1, duration: 0.6 }}
                className='space-y-3'>
                {/* Sector Header */}
                <div className='flex items-center justify-between'>
                  <div className='flex items-center gap-3'>
                    <div
                      className='w-10 h-10 rounded-xl flex items-center justify-center'
                      style={{ backgroundColor: `${item.color}20` }}>
                      <Icon size={20} style={{ color: item.color }} />
                    </div>
                    <div>
                      <h4 className='font-semibold text-gray-900 dark:text-neutral-text'>{item.sector}</h4>
                      <div className='text-sm text-gray-600 dark:text-neutral-muted'>
                        {item.percentage}% of total budget
                      </div>
                    </div>
                  </div>

                  <div className='text-right'>
                    <div className='font-bold text-gray-900 dark:text-neutral-text text-lg'>
                      {formatCurrency(item.amount)}
                    </div>
                    {comparison && (
                      <div
                        className={`text-sm ${
                          comparison.isIncrease ? 'text-green-600' : 'text-red-600'
                        }`}>
                        {comparison.isIncrease ? '+' : ''}
                        {comparison.change.toFixed(1)}% vs 2023
                      </div>
                    )}
                  </div>
                </div>

                {/* Progress Bars */}
                <div className='relative'>
                  {/* Current Year Bar */}
                  <div className='w-full bg-gray-200 dark:bg-surface-sunken rounded-full h-6'>
                    <motion.div
                      className='h-6 rounded-full flex items-center justify-end pr-3'
                      style={{ backgroundColor: item.color }}
                      initial={{ width: 0 }}
                      animate={{ width: `${percentage}%` }}
                      transition={{ delay: index * 0.1 + 0.3, duration: 1, ease: 'easeOut' }}>
                      <span className='text-white text-xs font-medium'>{item.percentage}%</span>
                    </motion.div>
                  </div>

                  {/* Comparison Bar (Previous Year) */}
                  {showComparison && comparison && (
                    <div className='w-full bg-transparent rounded-full h-2 mt-1'>
                      <motion.div
                        className='h-2 rounded-full opacity-50'
                        style={{ backgroundColor: item.color }}
                        initial={{ width: 0 }}
                        animate={{ width: `${prevPercentage}%` }}
                        transition={{ delay: index * 0.1 + 0.5, duration: 0.8, ease: 'easeOut' }}
                      />
                    </div>
                  )}
                </div>

                {/* Additional Info for Comparison */}
                {showComparison && comparison && (
                  <div className='text-xs text-gray-500 dark:text-neutral-muted/80 ml-13'>
                    2023: {formatCurrency(comparison.prevAmount)}
                    {comparison.isIncrease ? ' → ' : ' → '}
                    2024: {formatCurrency(item.amount)}
                  </div>
                )}
              </motion.div>
            );
          })}
      </div>

      {/* Chart Summary */}
      <div className='mt-8 p-6 bg-gray-50 dark:bg-surface-elevated rounded-2xl'>
        <h4 className='font-semibold text-gray-900 dark:text-neutral-text mb-4'>Budget Summary</h4>
        <div className='grid grid-cols-2 md:grid-cols-4 gap-4 text-center'>
          <div>
            <div className='text-2xl font-bold text-blue-600'>{data.allocations.length}</div>
            <div className='text-sm text-gray-600 dark:text-neutral-muted'>Major Sectors</div>
          </div>
          <div>
            <div className='text-2xl font-bold text-green-600'>{formatCurrency(data.total)}</div>
            <div className='text-sm text-gray-600 dark:text-neutral-muted'>Total Budget</div>
          </div>
          <div>
            <div className='text-2xl font-bold text-purple-600'>
              {data.allocations[0].percentage}%
            </div>
            <div className='text-sm text-gray-600 dark:text-neutral-muted'>Largest Allocation</div>
          </div>
          {showComparison && comparisonData && (
            <div>
              <div className='text-2xl font-bold text-orange-600'>
                +{(((data.total - comparisonData.total) / comparisonData.total) * 100).toFixed(1)}%
              </div>
              <div className='text-sm text-gray-600 dark:text-neutral-muted'>Growth vs 2023</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
