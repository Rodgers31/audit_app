'use client';

import { County } from '@/types';
import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';

interface CountyQuickSelectProps {
  counties: County[];
  selectedCounty: County | null;
  onCountySelect: (county: County) => void;
}

export default function CountyQuickSelect({
  counties,
  selectedCounty,
  onCountySelect,
}: CountyQuickSelectProps) {
  const [currentPage, setCurrentPage] = useState(0);
  const [isUserInteracting, setIsUserInteracting] = useState(false);
  const [timerKey, setTimerKey] = useState(0);

  const countiesPerPage = 12;
  const totalPages = Math.ceil((counties?.length || 0) / countiesPerPage) || 1;

  // Auto-cycle through pages (same behavior as before)
  useEffect(() => {
    if (isUserInteracting || totalPages <= 1) return;
    const id = setInterval(() => {
      setCurrentPage((p) => (p + 1) % totalPages);
    }, 6000);
    return () => clearInterval(id);
  }, [totalPages, isUserInteracting, timerKey]);

  // Resume auto-cycling after a pause
  useEffect(() => {
    if (!isUserInteracting) return;
    const t = setTimeout(() => {
      setIsUserInteracting(false);
      setTimerKey((k) => k + 1);
    }, 5000);
    return () => clearTimeout(t);
  }, [isUserInteracting]);

  const currentCounties = counties.slice(
    currentPage * countiesPerPage,
    (currentPage + 1) * countiesPerPage
  );

  return (
    <div className='mt-6'>
      <div className='flex items-center justify-between mb-4'>
        <h3 className='text-lg font-semibold text-gray-900 dark:text-neutral-text'>Quick Select County:</h3>
        <div className='flex items-center gap-2'>
          <div className='text-xs text-gray-500 dark:text-neutral-muted/80'>
            {totalPages > 1 && `Page ${currentPage + 1} of ${totalPages}`}
          </div>
          {totalPages > 1 && (
            <div className='flex gap-1'>
              {Array.from({ length: totalPages }).map((_, index) => (
                <motion.div
                  key={index}
                  className={`w-2 h-2 rounded-full cursor-pointer ${
                    currentPage === index ? 'bg-blue-600' : 'bg-gray-300'
                  }`}
                  onClick={() => {
                    setCurrentPage(index);
                    setIsUserInteracting(true);
                    setTimerKey((k) => k + 1);
                  }}
                  whileHover={{ scale: 1.2 }}
                  whileTap={{ scale: 0.9 }}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      <motion.div
        className='grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2 min-h-[120px]'
        key={currentPage}
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -20 }}
        transition={{ duration: 0.5 }}>
        {currentCounties.map((county, index) => {
          const isSelected = selectedCounty?.id === county.id;
          return (
            <motion.button
              key={county.id}
              onClick={() => {
                setIsUserInteracting(true);
                setTimerKey((k) => k + 1);
                onCountySelect(county);
              }}
              className={`
                px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200
                ${
                  isSelected
                    ? 'bg-blue-600 text-white shadow-lg scale-105'
                    : 'bg-white dark:bg-surface-base text-gray-700 dark:text-neutral-muted border border-gray-200 dark:border-neutral-border hover:border-blue-300 hover:text-blue-600'
                }
              `}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05, duration: 0.25 }}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}>
              {county.name.replace(' County', '')}
            </motion.button>
          );
        })}
      </motion.div>

      <div className='flex items-center justify-between mt-3'>
        <p className='text-sm text-gray-500 dark:text-neutral-muted/80'>
          Showing {currentCounties.length} of {counties.length} counties
          {!isUserInteracting && totalPages > 1 && (
            <span className='ml-2 text-blue-600'>• Auto-cycling</span>
          )}
        </p>
        {totalPages > 1 && (
          <div className='flex gap-2'>
            <button
              onClick={() => {
                setCurrentPage((p) => (p - 1 + totalPages) % totalPages);
                setIsUserInteracting(true);
                setTimerKey((k) => k + 1);
              }}
              className='px-2 py-1 text-xs bg-gray-100 dark:bg-surface-elevated hover:bg-gray-200 dark:bg-surface-sunken rounded transition-colors'>
              ←
            </button>
            <button
              onClick={() => {
                setCurrentPage((p) => (p + 1) % totalPages);
                setIsUserInteracting(true);
                setTimerKey((k) => k + 1);
              }}
              className='px-2 py-1 text-xs bg-gray-100 dark:bg-surface-elevated hover:bg-gray-200 dark:bg-surface-sunken rounded transition-colors'>
              →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
