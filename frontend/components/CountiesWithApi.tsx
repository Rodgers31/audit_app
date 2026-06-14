/**
 * Example component showing how to use the new API hooks
 * Replace the mock data usage in your main page with this pattern
 */
'use client';

import { useCounties, useTopPerformingCounties } from '@/lib/react-query/useCounties';
import { County } from '@/types';
import { motion } from 'framer-motion';
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react';

interface CountiesWithApiProps {
  onCountySelect: (county: County) => void;
  selectedCounty: County | null;
}

export default function CountiesWithApi({ onCountySelect, selectedCounty }: CountiesWithApiProps) {
  // Fetch all counties with React Query
  const { data: counties = [], isLoading, isError, error, refetch, isRefetching } = useCounties();

  // Fetch top performing counties
  const { data: topCounties = [], isLoading: isLoadingTop } = useTopPerformingCounties(5);

  // Loading state
  if (isLoading) {
    return (
      <div className='flex items-center justify-center p-8'>
        <Loader2 className='h-8 w-8 animate-spin text-blue-600' />
        <span className='ml-2 text-gray-600 dark:text-neutral-muted'>Loading counties...</span>
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <div className='bg-red-50 border border-red-200 rounded-lg p-6'>
        <div className='flex items-center mb-4'>
          <AlertTriangle className='h-6 w-6 text-red-600 mr-2' />
          <h3 className='text-lg font-semibold text-red-800'>Failed to load counties</h3>
        </div>
        <p className='text-red-700 mb-4'>
          {error instanceof Error ? error.message : 'An unexpected error occurred'}
        </p>
        <button
          onClick={() => refetch()}
          disabled={isRefetching}
          className='flex items-center px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50'>
          <RefreshCw className={`h-4 w-4 mr-2 ${isRefetching ? 'animate-spin' : ''}`} />
          Try Again
        </button>
      </div>
    );
  }

  return (
    <div className='space-y-6'>
      {/* Counties Grid */}
      <div>
        <div className='flex items-center justify-between mb-4'>
          <h2 className='text-2xl font-bold text-gray-900 dark:text-neutral-text'>All Counties ({counties.length})</h2>
          <button
            onClick={() => refetch()}
            disabled={isRefetching}
            className='flex items-center px-3 py-1 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50'>
            <RefreshCw className={`h-4 w-4 mr-1 ${isRefetching ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'>
          {counties.map((county) => (
            <motion.div
              key={county.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              whileHover={{ scale: 1.02 }}
              className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                selectedCounty?.id === county.id
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 dark:border-neutral-border hover:border-gray-300 dark:border-neutral-border'
              }`}
              onClick={() => onCountySelect(county)}>
              <h3 className='font-semibold text-gray-900 dark:text-neutral-text'>{county.name} County</h3>
              <p className='text-sm text-gray-600 dark:text-neutral-muted'>Code: {county.code}</p>
              <p className='text-sm text-gray-600 dark:text-neutral-muted'>
                Population: {(county.population / 1e6).toFixed(1)}M
              </p>
              <div className='mt-2'>
                <span
                  className={`inline-block px-2 py-1 text-xs rounded-full ${
                    county.auditStatus === 'clean'
                      ? 'bg-green-100 text-green-800'
                      : county.auditStatus === 'qualified'
                      ? 'bg-yellow-100 text-yellow-800'
                      : county.auditStatus === 'adverse'
                      ? 'bg-red-100 text-red-800'
                      : 'bg-gray-100 dark:bg-surface-elevated text-gray-800 dark:text-neutral-text'
                  }`}>
                  {county.auditStatus}
                </span>
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Top Performing Counties */}
      {!isLoadingTop && topCounties.length > 0 && (
        <div>
          <h3 className='text-xl font-bold text-gray-900 dark:text-neutral-text mb-4'>Top Performing Counties</h3>
          <div className='flex flex-wrap gap-2'>
            {topCounties.map((county) => (
              <motion.button
                key={county.id}
                whileHover={{ scale: 1.05 }}
                className='px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium hover:bg-green-200'
                onClick={() => onCountySelect(county)}>
                {county.name}
              </motion.button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
