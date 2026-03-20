/**
 * Central exports for all React Query hooks
 * Import all hooks from a single location for convenience
 */

// Counties hooks
export {
  useCounties,
  useCountiesInfinite,
  useCountiesSearch,
  useCounty,
  useCountyAccountability,
  useCountyByCode,
  useCountyComprehensive,
  useCountyFinancialSummary,
  useFlaggedCounties,
  useTopPerformingCounties,
} from './useCounties';

// Audits hooks
export {
  useAuditDashboardSummary,
  useAuditFindings,
  useAuditReport,
  useAuditReports,
  useAuditReportsInfinite,
  useAuditStatistics,
  useAuditTrends,
  useAvailableFiscalYears,
  useCountyAuditReports,
  useCountyAuditsEnriched,
  useLatestCountyAudit,
  useRecurringFindings,
} from './useAudits';

// Budget hooks
export {
  useBudgetAllocation,
  useBudgetComparison,
  useBudgetEnhanced,
  useBudgetOverview,
  useBudgetTrends,
  useBudgetUtilizationSummary,
  useNationalBudgetSummary,
  useSectorBudgetAllocation,
} from './useBudget';

// Debt hooks
export {
  useCountyDebtData,
  useCountyPendingBills,
  useDebtBreakdown,
  useDebtComparison,
  useDebtRiskAssessment,
  useDebtSustainability,
  useDebtSustainabilityIndicators,
  useDebtTimeline,
  useNationalDebtOverview,
  usePendingBillsSummary,
  useTopLoans,
} from './useDebt';

// Statistics hooks
export {
  useAlertsAndNotifications,
  useAuditComplianceStats,
  useDashboardStats,
  useFinancialHealthIndicators,
  useNationalOverview,
  useNationalTrends,
  usePerformanceRankings,
  useRegionalAnalysis,
  useSectorPerformance,
  useTransparencyIndex,
} from './useStatistics';

// Money Flow hooks
export { useCountyMoneyFlow, useNationalMoneyFlow } from './useMoneyFlow';

// Query Provider
export { QueryProvider } from './QueryProvider';
