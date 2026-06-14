'use client';

import { County } from '@/types';
import { motion } from 'framer-motion';

interface CountySliderProps {
  counties: County[];
  currentCountyIndex: number;
  onCountyIndexChange: (index: number) => void;
  onCountySelect: (county: County) => void;
  className?: string;
}

const formatKES = (amount: number): string => {
  if (amount >= 1e9) return `KES ${(amount / 1e9).toFixed(1)}B`;
  if (amount >= 1e6) return `KES ${(amount / 1e6).toFixed(1)}M`;
  if (amount >= 1e3) return `KES ${(amount / 1e3).toFixed(0)}K`;
  return `KES ${amount}`;
};

const formatPop = (population: number): string => {
  if (population >= 1e6) return `${(population / 1e6).toFixed(1)}M`;
  if (population >= 1e3) return `${(population / 1e3).toFixed(0)}K`;
  return population.toString();
};

export default function CountySlider({
  counties,
  currentCountyIndex,
  onCountyIndexChange,
  onCountySelect,
  className = '',
}: CountySliderProps) {
  const handleCountyClick = (county: County, index: number) => {
    onCountySelect(county);
    onCountyIndexChange(index);
  };

  // Return early if no counties data
  if (!counties || counties.length === 0) {
    return (
      <div className={`p-4 ${className}`}>
        <div className='text-center text-gray-500 dark:text-neutral-muted/80'>Loading counties data...</div>
      </div>
    );
  }

  const getPrevIndex = () =>
    currentCountyIndex === 0 ? counties.length - 1 : currentCountyIndex - 1;

  const getNextIndex = () => (currentCountyIndex + 1) % counties.length;

  const prevCounty = counties[getPrevIndex()];
  const currentCounty = counties[currentCountyIndex];
  const nextCounty = counties[getNextIndex()];

  const renderCountyCard = (
    county: County,
    index: number,
    position: 'prev' | 'current' | 'next'
  ) => {
    const isActive = position === 'current';

    return (
      <motion.button
        type='button'
        key={`${position}-${county.id}`}
        animate={{
          opacity: isActive ? 1 : 0.6,
        }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
        className='cursor-pointer transition-all duration-300 hover:opacity-90 flex-1 text-left'
        onClick={() => handleCountyClick(county, index)}>
        <div
          className={`
          rounded-lg border shadow-sm p-3 h-full flex flex-col justify-between
          ${
            isActive
              ? 'bg-green-50 border-green-400 border-2 shadow-md'
              : 'bg-gray-50 dark:bg-surface-elevated border-gray-300 dark:border-neutral-border opacity-70'
          }
        `}>
          {/* County Name and Status */}
          <div className='flex items-start justify-between mb-2'>
            <h4 className='font-semibold text-sm text-gray-900 dark:text-neutral-text truncate pr-2'>{county.name}</h4>
            <span
              className={`
              px-1.5 py-0.5 rounded text-xs font-medium flex-shrink-0
              ${
                (county.auditStatus || 'pending') === 'clean'
                  ? 'bg-green-100 text-green-700'
                  : (county.auditStatus || 'pending') === 'qualified'
                  ? 'bg-yellow-100 text-yellow-700'
                  : (county.auditStatus || 'pending') === 'adverse'
                  ? 'bg-red-100 text-red-700'
                  : 'bg-orange-100 text-orange-700'
              }
            `}>
              {county.auditStatus || 'pending'}
            </span>
          </div>

          {/* Financial Info */}
          <div className='space-y-1 flex-1'>
            {/* Population */}
            <div className='text-xs'>
              <span className='text-gray-500 dark:text-neutral-muted/80'>Pop: </span>
              <span className='font-medium text-gray-700 dark:text-neutral-muted'>{formatPop(county.population)}</span>
            </div>

            {/* Budget */}
            <div className='text-xs'>
              <span className='text-gray-500 dark:text-neutral-muted/80'>Budget: </span>
              <span className='font-medium text-green-600'>
                {formatKES(county.budget ?? county.totalBudget ?? 0)}
              </span>
            </div>

            {/* Debt */}
            <div className='text-xs'>
              <span className='text-gray-500 dark:text-neutral-muted/80'>Debt: </span>
              <span className='font-medium text-red-600'>
                {formatKES(county.debt ?? county.totalDebt ?? 0)}
              </span>
            </div>
          </div>
        </div>
      </motion.button>
    );
  };

  return (
    <div className={`rounded-xl p-3 ${className}`}>
      <div className='flex gap-3 h-28'>
        {renderCountyCard(prevCounty, getPrevIndex(), 'prev')}
        {renderCountyCard(currentCounty, currentCountyIndex, 'current')}
        {renderCountyCard(nextCounty, getNextIndex(), 'next')}
      </div>
    </div>
  );
}
