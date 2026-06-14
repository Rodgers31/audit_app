'use client';

import { County } from '@/types';
import { motion } from 'framer-motion';
import { BookOpen, Hammer, Heart } from 'lucide-react';

interface CountySpendingChartProps {
  county: County;
}

export default function CountySpendingChart({ county }: CountySpendingChartProps) {
  const totalBudget = county.budget ?? county.totalBudget ?? 0;

  // Build spending categories from actual county sector data
  const rawCategories = [
    { name: 'Education', amount: county.education ?? 0, color: '#3b82f6', icon: BookOpen },
    { name: 'Health', amount: county.health ?? 0, color: '#ef4444', icon: Heart },
    { name: 'Infrastructure', amount: county.infrastructure ?? 0, color: '#f59e0b', icon: Hammer },
  ];

  // Only show sectors with actual data
  const spendingCategories = rawCategories.filter((c) => c.amount > 0);

  const maxAmount = Math.max(...spendingCategories.map((cat) => cat.amount), 1);

  const formatAmount = (amount: number) => {
    return `KES ${(amount / 1e9).toFixed(1)}B`;
  };

  const formatPercentage = (amount: number) => {
    return totalBudget > 0 ? `${((amount / totalBudget) * 100).toFixed(1)}%` : '0%';
  };

  return (
    <div className='space-y-6'>
      {/* Summary */}
      <div className='bg-gray-50 dark:bg-surface-elevated rounded-xl p-4'>
        <h4 className='text-lg font-semibold text-gray-900 dark:text-neutral-text mb-2'>Budget Breakdown</h4>
        <p className='text-sm text-gray-600 dark:text-neutral-muted'>
          Total Annual Budget: <span className='font-semibold'>{formatAmount(totalBudget)}</span>
        </p>
      </div>

      {spendingCategories.length === 0 ? (
        <p className='text-sm text-gray-500 dark:text-neutral-muted/80 text-center py-4'>
          Sector spending breakdown is not available for this county.
        </p>
      ) : (
        /* Bar Chart */
        <div className='space-y-4'>
          {spendingCategories.map((category, index) => {
            const Icon = category.icon;
            const percentage = (category.amount / maxAmount) * 100;

            return (
              <motion.div
                key={category.name}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1, duration: 0.5 }}
                className='space-y-2'>
                {/* Category Header */}
                <div className='flex items-center justify-between'>
                  <div className='flex items-center gap-3'>
                    <div
                      className='w-8 h-8 rounded-lg flex items-center justify-center'
                      style={{ backgroundColor: `${category.color}20` }}>
                      <Icon size={16} style={{ color: category.color }} />
                    </div>
                    <span className='font-medium text-gray-900 dark:text-neutral-text'>{category.name}</span>
                  </div>
                  <div className='text-right'>
                    <div className='font-semibold text-gray-900 dark:text-neutral-text'>
                      {formatAmount(category.amount)}
                    </div>
                    <div className='text-sm text-gray-500 dark:text-neutral-muted/80'>{formatPercentage(category.amount)}</div>
                  </div>
                </div>

                {/* Progress Bar */}
                <div className='relative'>
                  <div className='w-full bg-gray-200 dark:bg-surface-sunken rounded-full h-3'>
                    <motion.div
                      className='h-3 rounded-full'
                      style={{ backgroundColor: category.color }}
                      initial={{ width: 0 }}
                      animate={{ width: `${percentage}%` }}
                      transition={{ delay: index * 0.1 + 0.2, duration: 0.8, ease: 'easeOut' }}
                    />
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Additional Insights */}
      {county.budgetUtilization != null && county.budgetUtilization > 0 && (
        <div className='bg-blue-50 rounded-xl p-4 border border-blue-200'>
          <h5 className='font-semibold text-blue-900 mb-2'>Spending Insights</h5>
          <ul className='text-sm text-blue-800 space-y-1'>
            <li>• Budget utilization rate: {county.budgetUtilization}%</li>
          </ul>
        </div>
      )}
    </div>
  );
}
