/**
 * Example component demonstrating usage of all API hooks
 * This shows how to integrate the hooks into your existing components
 */
'use client';

import {
  useAuditReports,
  useBudgetAllocation,
  useCounties,
  useDashboardStats,
  useLatestCountyAudit,
  useNationalDebtOverview,
  useTopPerformingCounties,
} from '@/lib/react-query';
import { County } from '@/types';
import { motion } from 'framer-motion';
import { AlertTriangle, BarChart3, DollarSign, FileText, Loader2, TrendingUp } from 'lucide-react';
import { useState } from 'react';

export default function ApiHooksExamples() {
  const [selectedCountyId, setSelectedCountyId] = useState<string>('001'); // Default to Nairobi

  // Example 1: Dashboard Statistics
  const { data: dashboardStats, isLoading: isDashboardLoading } = useDashboardStats();

  // Example 2: Counties List
  const { data: counties = [], isLoading: isCountiesLoading } = useCounties();

  // Example 3: Top Performing Counties
  const { data: topCounties = [], isLoading: isTopLoading } = useTopPerformingCounties(5);

  // Example 4: Audit Reports with Filters
  const { data: auditReports = [], isLoading: isAuditsLoading } = useAuditReports({
    auditStatus: ['clean', 'qualified'],
    limit: 10,
  });

  // Example 5: Budget Allocation for Selected County
  const { data: budgetData, isLoading: isBudgetLoading } = useBudgetAllocation(
    selectedCountyId,
    '2024' // Current fiscal year
  );

  // Example 6: Latest Audit for Selected County
  const { data: latestAudit, isLoading: isLatestAuditLoading } =
    useLatestCountyAudit(selectedCountyId);

  // Example 7: National Debt Overview
  const { data: debtOverview, isLoading: isDebtLoading } = useNationalDebtOverview();

  if (isDashboardLoading) {
    return (
      <div className='flex items-center justify-center p-8'>
        <Loader2 className='h-8 w-8 animate-spin text-blue-600' />
        <span className='ml-2 text-gray-600 dark:text-neutral-muted'>Loading dashboard...</span>
      </div>
    );
  }

  return (
    <div className='space-y-8 p-6'>
      <div className='text-center'>
        <h1 className='text-3xl font-bold text-gray-900 dark:text-neutral-text mb-2'>API Hooks Examples</h1>
        <p className='text-gray-600 dark:text-neutral-muted'>Demonstration of React Query hooks integration</p>
      </div>

      {/* Dashboard Stats */}
      {dashboardStats && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className='bg-white dark:bg-surface-base rounded-lg shadow-lg p-6'>
          <h2 className='text-xl font-semibold text-gray-900 dark:text-neutral-text mb-4 flex items-center'>
            <BarChart3 className='h-5 w-5 mr-2' />
            National Overview
          </h2>
          <div className='grid grid-cols-1 md:grid-cols-4 gap-4'>
            <div className='bg-blue-50 p-4 rounded-lg'>
              <div className='text-blue-600 text-sm font-medium'>Total Counties</div>
              <div className='text-2xl font-bold text-blue-700'>{dashboardStats.totalCounties}</div>
            </div>
            <div className='bg-green-50 p-4 rounded-lg'>
              <div className='text-green-600 text-sm font-medium'>Total Budget</div>
              <div className='text-2xl font-bold text-green-700'>
                KES {(dashboardStats.totalBudget / 1e12).toFixed(1)}T
              </div>
            </div>
            <div className='bg-red-50 p-4 rounded-lg'>
              <div className='text-red-600 text-sm font-medium'>Total Debt</div>
              <div className='text-2xl font-bold text-red-700'>
                KES {(dashboardStats.totalDebt / 1e12).toFixed(1)}T
              </div>
            </div>
            <div className='bg-purple-50 p-4 rounded-lg'>
              <div className='text-purple-600 text-sm font-medium'>Audit Score</div>
              <div className='text-2xl font-bold text-purple-700'>
                {dashboardStats.averageAuditScore}%
              </div>
            </div>
          </div>
        </motion.div>
      )}

      {/* County Selection */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className='bg-white dark:bg-surface-base rounded-lg shadow-lg p-6'>
        <h2 className='text-xl font-semibold text-gray-900 dark:text-neutral-text mb-4'>County Selection</h2>
        <div className='grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2'>
          {counties.slice(0, 12).map((county: County) => (
            <button
              key={county.id}
              onClick={() => setSelectedCountyId(county.id)}
              className={`p-2 text-sm rounded-lg border transition-colors ${
                selectedCountyId === county.id
                  ? 'border-blue-500 bg-blue-50 text-blue-700'
                  : 'border-gray-200 dark:border-neutral-border hover:border-gray-300 dark:border-neutral-border'
              }`}>
              {county.name}
            </button>
          ))}
        </div>
      </motion.div>

      {/* Selected County Details */}
      {selectedCountyId && (
        <div className='grid grid-cols-1 lg:grid-cols-2 gap-6'>
          {/* Budget Allocation */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className='bg-white dark:bg-surface-base rounded-lg shadow-lg p-6'>
            <h3 className='text-lg font-semibold text-gray-900 dark:text-neutral-text mb-4 flex items-center'>
              <DollarSign className='h-5 w-5 mr-2' />
              Budget Allocation
            </h3>
            {isBudgetLoading ? (
              <div className='flex items-center justify-center p-4'>
                <Loader2 className='h-6 w-6 animate-spin text-blue-600' />
              </div>
            ) : budgetData ? (
              <div className='space-y-3'>
                <div className='flex justify-between'>
                  <span className='text-gray-600 dark:text-neutral-muted'>Total Budget:</span>
                  <span className='font-semibold'>
                    KES {(budgetData.totalBudget / 1e9).toFixed(1)}B
                  </span>
                </div>
                <div className='flex justify-between'>
                  <span className='text-gray-600 dark:text-neutral-muted'>Total Spent:</span>
                  <span className='font-semibold'>
                    KES {(budgetData.totalSpent / 1e9).toFixed(1)}B
                  </span>
                </div>
                <div className='space-y-2'>
                  {budgetData.allocations?.slice(0, 5).map((allocation: any, index: number) => (
                    <div key={index} className='flex justify-between text-sm'>
                      <span className='text-gray-600 dark:text-neutral-muted'>{allocation.sector}:</span>
                      <span>{allocation.percentage}%</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className='text-gray-500 dark:text-neutral-muted/80'>No budget data available</p>
            )}
          </motion.div>

          {/* Latest Audit */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className='bg-white dark:bg-surface-base rounded-lg shadow-lg p-6'>
            <h3 className='text-lg font-semibold text-gray-900 dark:text-neutral-text mb-4 flex items-center'>
              <FileText className='h-5 w-5 mr-2' />
              Latest Audit
            </h3>
            {isLatestAuditLoading ? (
              <div className='flex items-center justify-center p-4'>
                <Loader2 className='h-6 w-6 animate-spin text-blue-600' />
              </div>
            ) : latestAudit ? (
              <div className='space-y-3'>
                <div className='flex justify-between'>
                  <span className='text-gray-600 dark:text-neutral-muted'>Fiscal Year:</span>
                  <span className='font-semibold'>{latestAudit.fiscalYear}</span>
                </div>
                <div className='flex justify-between'>
                  <span className='text-gray-600 dark:text-neutral-muted'>Status:</span>
                  <span
                    className={`font-semibold ${
                      latestAudit.auditStatus === 'clean'
                        ? 'text-green-600'
                        : latestAudit.auditStatus === 'qualified'
                        ? 'text-yellow-600'
                        : 'text-red-600'
                    }`}>
                    {latestAudit.auditStatus}
                  </span>
                </div>
                <div className='text-sm text-gray-600 dark:text-neutral-muted'>
                  <p className='font-medium mb-1'>Summary:</p>
                  <p>{latestAudit.summary?.headline}</p>
                </div>
                {latestAudit.findings?.length > 0 && (
                  <div className='text-sm'>
                    <p className='font-medium text-gray-700 dark:text-neutral-muted mb-1'>Key Findings:</p>
                    <ul className='space-y-1'>
                      {latestAudit.findings.slice(0, 3).map((finding: any, index: number) => (
                        <li key={index} className='text-gray-600 dark:text-neutral-muted flex items-start'>
                          <AlertTriangle className='h-3 w-3 mr-1 mt-0.5 text-yellow-500' />
                          {finding.description}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <p className='text-gray-500 dark:text-neutral-muted/80'>No audit data available</p>
            )}
          </motion.div>
        </div>
      )}

      {/* Top Performing Counties */}
      {!isTopLoading && topCounties.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className='bg-white dark:bg-surface-base rounded-lg shadow-lg p-6'>
          <h2 className='text-xl font-semibold text-gray-900 dark:text-neutral-text mb-4 flex items-center'>
            <TrendingUp className='h-5 w-5 mr-2' />
            Top Performing Counties
          </h2>
          <div className='grid grid-cols-1 md:grid-cols-5 gap-4'>
            {topCounties.map((county: County, index: number) => (
              <div key={county.id} className='text-center p-4 bg-green-50 rounded-lg'>
                <div className='text-2xl font-bold text-green-600'>#{index + 1}</div>
                <div className='font-semibold text-gray-900 dark:text-neutral-text'>{county.name}</div>
                <div className='text-sm text-gray-600 dark:text-neutral-muted'>{county.auditStatus || 'pending'}</div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Recent Audit Reports */}
      {!isAuditsLoading && auditReports.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className='bg-white dark:bg-surface-base rounded-lg shadow-lg p-6'>
          <h2 className='text-xl font-semibold text-gray-900 dark:text-neutral-text mb-4'>
            Recent Clean & Qualified Audits
          </h2>
          <div className='space-y-3'>
            {auditReports.slice(0, 5).map((report: any) => (
              <div
                key={report.id}
                className='flex items-center justify-between p-3 bg-gray-50 dark:bg-surface-elevated rounded-lg'>
                <div>
                  <div className='font-semibold'>{report.countyName}</div>
                  <div className='text-sm text-gray-600 dark:text-neutral-muted'>{report.fiscalYear}</div>
                </div>
                <div className='text-right'>
                  <div
                    className={`text-sm font-medium ${
                      report.auditStatus === 'clean' ? 'text-green-600' : 'text-yellow-600'
                    }`}>
                    {report.auditStatus}
                  </div>
                  <div className='text-xs text-gray-500 dark:text-neutral-muted/80'>{report.auditDate}</div>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}
