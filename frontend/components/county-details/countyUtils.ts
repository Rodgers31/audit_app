/**
 * County Details Utilities
 * Helper functions for formatting and calculating county metrics
 * Extracted from CountyDetails component for better maintainability
 */

import { countyDebtRatio } from '@/components/map/MapUtilities';
import { countyBudget, countyDebt } from '@/lib/countyFigures';
import { County } from '@/types';

/**
 * Format population numbers with appropriate units
 */
export const formatPopulation = (population: number | undefined): string => {
  if (!population || population === 0) return 'N/A';
  if (population >= 1e6) return `${(population / 1e6).toFixed(3)}M`;
  if (population >= 1e3) return `${(population / 1e3).toFixed(0)}K`;
  return population.toString();
};

/**
 * Format currency values in billions or millions
 */
export const formatCurrency = (amount: number | undefined): string => {
  if (!amount || amount === 0) return 'KES 0';
  if (amount >= 1e9) return `KES ${(amount / 1e9).toFixed(2)}B`;
  if (amount >= 1e6) return `KES ${(amount / 1e6).toFixed(0)}M`;
  if (amount >= 1e3) return `KES ${(amount / 1e3).toFixed(0)}K`;
  return `KES ${amount.toLocaleString()}`;
};

/**
 * Get audit status styling classes
 */
export const getAuditStatusColor = (status: string) => {
  switch (status) {
    case 'clean':
      return 'bg-green-100 text-green-700 border-green-200';
    case 'qualified':
      return 'bg-yellow-100 text-yellow-700 border-yellow-200';
    case 'adverse':
      return 'bg-red-100 text-red-700 border-red-200';
    case 'disclaimer':
      return 'bg-orange-100 text-orange-700 border-orange-200';
    default:
      return 'bg-gray-100 text-gray-700 border-gray-200';
  }
};

/**
 * Get audit status background classes for cards
 */
export const getAuditStatusBackground = (status: string) => {
  switch (status) {
    case 'clean':
      return 'bg-green-50 border-green-200';
    case 'qualified':
      return 'bg-yellow-50 border-yellow-200';
    case 'adverse':
      return 'bg-red-50 border-red-200';
    case 'disclaimer':
      return 'bg-orange-50 border-orange-200';
    default:
      return 'bg-gray-50 border-gray-200';
  }
};

/**
 * Get audit status icon background color
 */
export const getAuditStatusIconColor = (status: string) => {
  switch (status) {
    case 'clean':
      return 'bg-green-500';
    case 'qualified':
      return 'bg-yellow-500';
    case 'adverse':
      return 'bg-red-500';
    case 'disclaimer':
      return 'bg-orange-500';
    default:
      return 'bg-gray-500';
  }
};

/**
 * Get audit status text color
 */
export const getAuditStatusTextColor = (status: string) => {
  switch (status) {
    case 'clean':
      return 'text-green-600';
    case 'qualified':
      return 'text-yellow-600';
    case 'adverse':
      return 'text-red-600';
    case 'disclaimer':
      return 'text-orange-600';
    default:
      return 'text-gray-600';
  }
};

/**
 * Get audit status title text
 */
export const getAuditStatusText = (status: string) => {
  switch (status) {
    case 'clean':
      return 'Clean Opinion';
    case 'qualified':
      return 'Qualified Opinion';
    case 'adverse':
      return 'Adverse Opinion';
    case 'disclaimer':
      return 'Disclaimer Opinion';
    default:
      return 'Unknown Status';
  }
};

/**
 * Get audit status description
 */
export const getAuditDescription = (status: string) => {
  switch (status) {
    case 'clean':
      return 'No material issues found';
    case 'qualified':
      return 'Some concerns identified';
    case 'adverse':
      return 'Significant issues found';
    case 'disclaimer':
      return 'Unable to form opinion';
    default:
      return 'Status unknown';
  }
};

/**
 * Calculate county financial metrics
 */
export const calculateCountyMetrics = (county: County) => {
  const budgetUtilization = county.budgetUtilization ?? null;
  // Absent figures stay absent: a county whose budget or debt the API never
  // published must not be reported as one allocated nothing or owing nothing.
  const budget = countyBudget(county) ?? null;
  const debt = countyDebt(county) ?? null;
  const debtRatio = countyDebtRatio(county);
  const perCapitaDebt = debt != null && county.population > 0 ? debt / county.population : null;
  const revenue = county.revenueCollection ?? null;
  const expenditure =
    budgetUtilization != null && budget != null ? budget * (budgetUtilization / 100) : null;
  const balance =
    revenue != null && expenditure != null ? revenue - expenditure : null;

  return {
    budget,
    debt,
    budgetUtilization,
    debtRatio,
    perCapitaDebt,
    revenue,
    expenditure,
    balance,
  };
};

/**
 * Get balance color based on positive/negative value
 */
export const getBalanceColor = (balance: number): string => {
  return balance >= 0 ? 'text-green-600' : 'text-red-600';
};
