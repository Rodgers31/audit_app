'use client';

import { motion } from 'framer-motion';
import { BarChart3, Calendar, TrendingUp } from 'lucide-react';

interface BudgetData {
  total: number;
  allocations: any[];
}

interface BudgetComparisonFilterProps {
  selectedYear: '2023' | '2024' | 'comparison';
  onYearChange: (year: '2023' | '2024' | 'comparison') => void;
  budgetData: {
    2023: BudgetData;
    2024: BudgetData;
  };
}

export default function BudgetComparisonFilter({
  selectedYear,
  onYearChange,
  budgetData,
}: BudgetComparisonFilterProps) {
  const formatCurrency = (amount: number) => {
    return `KES ${(amount / 1e12).toFixed(2)}T`;
  };

  const options = [
    {
      id: '2024' as const,
      label: '2024 Budget',
      description: 'Current fiscal year allocation',
      icon: Calendar,
      value: budgetData['2024'].total,
      color: 'blue',
    },
    {
      id: '2023' as const,
      label: '2023 Budget',
      description: 'Previous fiscal year allocation',
      icon: BarChart3,
      value: budgetData['2023'].total,
      color: 'green',
    },
    {
      id: 'comparison' as const,
      label: 'Compare Years',
      description: 'Side-by-side comparison',
      icon: TrendingUp,
      value: budgetData['2024'].total - budgetData['2023'].total,
      color: 'purple',
    },
  ];

  const getColorClasses = (color: string, isSelected: boolean) => {
    const baseClasses = 'transition-all duration-200';

    if (isSelected) {
      switch (color) {
        case 'blue':
          return `${baseClasses} bg-blue-600 text-white border-blue-600 shadow-lg scale-105`;
        case 'green':
          return `${baseClasses} bg-green-600 text-white border-green-600 shadow-lg scale-105`;
        case 'purple':
          return `${baseClasses} bg-purple-600 text-white border-purple-600 shadow-lg scale-105`;
        default:
          return `${baseClasses} bg-gray-600 text-white border-gray-600 shadow-lg scale-105`;
      }
    } else {
      switch (color) {
        case 'blue':
          return `${baseClasses} bg-white dark:bg-surface-base text-blue-600 border-blue-200 hover:border-blue-400 hover:bg-blue-50`;
        case 'green':
          return `${baseClasses} bg-white dark:bg-surface-base text-green-600 border-green-200 hover:border-green-400 hover:bg-green-50`;
        case 'purple':
          return `${baseClasses} bg-white dark:bg-surface-base text-purple-600 border-purple-200 hover:border-purple-400 hover:bg-purple-50`;
        default:
          return `${baseClasses} bg-white dark:bg-surface-base text-gray-600 dark:text-neutral-muted border-gray-200 dark:border-neutral-border hover:border-gray-400 hover:bg-gray-50 dark:bg-surface-elevated`;
      }
    }
  };

  return (
    <div className='bg-white dark:bg-surface-base rounded-3xl p-8 shadow-xl border border-gray-200 dark:border-neutral-border'>
      <div className='text-center mb-8'>
        <h2 className='text-2xl font-bold text-gray-900 dark:text-neutral-text mb-2'>Choose Budget Period</h2>
        <p className='text-gray-600 dark:text-neutral-muted'>
          Select a fiscal year or compare budget allocations across years
        </p>
      </div>

      <div className='grid grid-cols-1 md:grid-cols-3 gap-6'>
        {options.map((option, index) => {
          const Icon = option.icon;
          const isSelected = selectedYear === option.id;

          return (
            <motion.button
              key={option.id}
              onClick={() => onYearChange(option.id)}
              className={`
                p-6 rounded-2xl border-2 text-left
                ${getColorClasses(option.color, isSelected)}
              `}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1, duration: 0.5 }}
              whileHover={{ scale: isSelected ? 1.05 : 1.02 }}
              whileTap={{ scale: 0.98 }}>
              <div className='flex items-center gap-4 mb-4'>
                <div
                  className={`
                  w-12 h-12 rounded-xl flex items-center justify-center
                  ${isSelected ? 'bg-white/20' : `bg-${option.color}-100`}
                `}>
                  <Icon
                    size={24}
                    className={isSelected ? 'text-white' : `text-${option.color}-600`}
                  />
                </div>
                <div>
                  <h3 className='text-lg font-semibold'>{option.label}</h3>
                  <p className={`text-sm ${isSelected ? 'text-white/80' : 'text-gray-600 dark:text-neutral-muted'}`}>
                    {option.description}
                  </p>
                </div>
              </div>

              <div className='space-y-2'>
                <div className='text-2xl font-bold'>
                  {option.id === 'comparison' ? '+' : ''}
                  {formatCurrency(Math.abs(option.value))}
                </div>
                <div className={`text-sm ${isSelected ? 'text-white/80' : 'text-gray-600 dark:text-neutral-muted'}`}>
                  {option.id === 'comparison'
                    ? `Increase from 2023 to 2024`
                    : `Total budget allocation`}
                </div>
              </div>

              {/* Selection Indicator */}
              {isSelected && (
                <motion.div
                  layoutId='selectedFilter'
                  className='absolute inset-0 border-2 border-white/30 rounded-2xl pointer-events-none'
                  transition={{ type: 'spring', bounce: 0.2, duration: 0.6 }}
                />
              )}
            </motion.button>
          );
        })}
      </div>

      {/* Additional Info */}
      <div className='mt-8 p-6 bg-gray-50 dark:bg-surface-elevated rounded-2xl'>
        <h4 className='font-semibold text-gray-900 dark:text-neutral-text mb-3'>Quick Facts</h4>
        <div className='grid grid-cols-1 md:grid-cols-3 gap-4 text-sm'>
          <div className='text-center'>
            <div className='text-lg font-bold text-blue-600'>
              {(
                ((budgetData['2024'].total - budgetData['2023'].total) / budgetData['2023'].total) *
                100
              ).toFixed(1)}
              %
            </div>
            <div className='text-gray-600 dark:text-neutral-muted'>Budget Growth</div>
          </div>
          <div className='text-center'>
            <div className='text-lg font-bold text-green-600'>
              {budgetData['2024'].allocations.length}
            </div>
            <div className='text-gray-600 dark:text-neutral-muted'>Major Sectors</div>
          </div>
          <div className='text-center'>
            <div className='text-lg font-bold text-purple-600'>
              {formatCurrency(budgetData['2024'].total)}
            </div>
            <div className='text-gray-600 dark:text-neutral-muted'>Current Total</div>
          </div>
        </div>
      </div>
    </div>
  );
}
