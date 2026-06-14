/**
 * CountyDetails - Main component for displaying detailed county information
 * Refactored into modular components for better maintainability
 * Utility functions extracted to separate file for reusability
 */
'use client';

import { County } from '@/types';
import { motion } from 'framer-motion';
import CountyHeader from './county-details/CountyHeader';
import FinancialSummary from './county-details/FinancialSummary';
import MetricsCards from './county-details/MetricsCards';
import { calculateCountyMetrics } from './county-details/countyUtils';

interface CountyDetailsProps {
  county: County;
  className?: string;
  onHoverStart?: () => void;
  onHoverEnd?: () => void;
}

export default function CountyDetails({
  county,
  className = '',
  onHoverStart,
  onHoverEnd,
}: CountyDetailsProps) {
  // Calculate all financial metrics using utility function
  const { budgetUtilization, debtRatio, perCapitaDebt, revenue, expenditure, balance } =
    calculateCountyMetrics(county);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className={`bg-white dark:bg-surface-base rounded-2xl shadow-sm border border-gray-200 dark:border-neutral-border p-6 hover:shadow-lg transition-all duration-300 ${className}`}
      onMouseEnter={onHoverStart}
      onMouseLeave={onHoverEnd}>
      {/* County Header */}
      <CountyHeader county={county} />

      {/* Main Metrics Cards */}
      <MetricsCards county={county} budgetUtilization={budgetUtilization} debtRatio={debtRatio} />

      {/* Financial Summary */}
      <FinancialSummary
        revenue={revenue}
        expenditure={expenditure}
        balance={balance}
        perCapitaDebt={perCapitaDebt}
      />
    </motion.div>
  );
}
