/**
 * API response types and interfaces
 */
import { AuditIssue, County } from '@/types';

// Base API response wrapper
export interface ApiResponse<T> {
  data: T;
  message?: string;
  success: boolean;
  timestamp: string;
}

// Paginated response wrapper
export interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    total: number;
    page: number;
    limit: number;
    totalPages: number;
  };
  success: boolean;
  message?: string;
}

// Error response
export interface ApiError {
  message: string;
  code?: string;
  details?: any;
  timestamp: string;
}

// County API responses
export interface CountyResponse extends County {
  // Additional fields that might come from API
  lastUpdated?: string;
}

export interface CountiesListResponse {
  counties: CountyResponse[];
  total: number;
}

// Audit API responses
export interface AuditReportResponse {
  id: string;
  countyId: string;
  countyName: string;
  fiscalYear: string;
  auditStatus: string;
  auditOpinion: string;
  auditDate: string;
  findings: AuditIssue[];
  summary: {
    headline: string;
    summary: string;
    keyFindings: string[];
    concern_level: string;
  };
  financialData: {
    totalBudget: number;
    budgetUtilization: number;
    revenueCollection: number;
    pendingBills: number;
  };
}

/** Actual flat county /budget account. Amounts are KES unless currency says otherwise.
 * A null figure carries an absent_reasons entry; zero is a reported figure.
 * The supported period is selected by the backend, not by the legacy query.
 */
export interface CountyAccountPeriod {
  id: number;
  label: string | null;
  start_date: string | null;
  end_date: string | null;
}

export interface CountyAccountSource {
  id: number | null;
  title: string | null;
  publisher: string | null;
  url: string | null;
  page_refs: string[];
}

export interface CountyFinancialSummary {
  total_allocation: number | null;
  total_spent: number | null;
  execution_rate: number | null;
  fiscal_period: CountyAccountPeriod | null;
  accounting_basis: 'reported_total' | 'recurrent_plus_development' | null;
  currency: string | null;
  sources: CountyAccountSource[];
  absent_reasons: Record<string, string>;
  budget_lines_count: number;
}

export interface BudgetAllocationResponse {
  county_id: string;
  county_name: string;
  total_budget: number | null;
  total_spent: number | null;
  budget_2025: number | null;
  budget_utilization: number | null;
  budget_execution_rate: number | null;
  budget_source: string | null;
  revenue_2024: number | null;
  fiscal_period: CountyAccountPeriod | null;
  sources: CountyAccountSource[];
  accounting_basis: CountyFinancialSummary['accounting_basis'];
  currency: string | null;
  absent_reasons: Record<string, string>;
  financial_summary: CountyFinancialSummary;
  /** Breakdown is deliberately unavailable; no invented allocation array. */
  expenditure_breakdown: Record<string, never>;
  budget_allocation: Record<string, never>;
}

// Budget API responses
export interface BudgetComparisonAllocationResponse {
  countyId: string;
  countyName: string;
  fiscalYear: string;
  allocations: {
    sector: string;
    budgeted: number;
    spent: number;
    percentage: number;
  }[];
  totalBudget: number;
  totalSpent: number;
}

// Debt API responses
export interface DebtDataResponse {
  countyId: string;
  countyName: string;
  totalDebt: number;
  debtToGdpRatio: number;
  debtCategories: {
    category: string;
    amount: number;
    percentage: number;
  }[];
  debtTimeline: {
    year: string;
    amount: number;
  }[];
}

// National statistics
export interface NationalStatsResponse {
  totalCounties: number;
  totalBudget: number;
  totalDebt: number;
  averageAuditScore: number;
  countiesByAuditStatus: {
    clean: number;
    qualified: number;
    adverse: number;
    disclaimer: number;
    pending: number;
  };
  topPerformingCounties: CountyResponse[];
  flaggedCounties: CountyResponse[];
}

// Query parameters
export interface CountyFilters {
  search?: string;
  auditStatus?: string[];
  debtLevel?: 'low' | 'medium' | 'high';
  budgetRange?: [number, number];
  fiscalYear?: string;
  page?: number;
  limit?: number;
}

export interface AuditFilters {
  countyId?: string;
  fiscalYear?: string;
  auditStatus?: string[];
  concernLevel?: string[];
  page?: number;
  limit?: number;
}

// Enriched audits response from backend /api/v1/counties/{id}/audits
export interface CountyAuditQuery {
  id: number;
  description: string | null;
  finding?: string | null;
  recommendation?: string | null;
  amount_involved: number | null;
  amount?: number | null;
  amount_unavailable_reason?: string | null;
  severity: string | null;
  status: string | null;
  date_raised: string | null;
  category: string | null;
  fiscal_year: string | null;
  audited_entity_name: string | null;
  source: {
    id: number | null;
    title: string | null;
    publisher: string | null;
    url: string | null;
    page: number | string | null;
    page_url: string | null;
  };
}

export interface CountyAuditsEnriched {
  county_id: string;
  county_name: string;
  country?: 'KEN';
  currency?: 'KES';
  data_source?: 'database';
  findings_reason?: string | null;
  withheld_findings?: number;
  fiscal_years_covered?: string[];
  summary: {
    queries_count: number;
    total_amount_involved: number | null;
    amount_coverage?: import("@/types").AuditAmountCoverage;
    by_severity: Record<string, number>;
    by_status: Record<string, number>;
    by_category: Record<string, number>;
  };
  top_recent: CountyAuditQuery[];
  queries: CountyAuditQuery[];
  missing_funds: {
    count: number | null;
    total_amount: number | null;
    absent_reason?: string;
    cases: Array<{
      case_id: string;
      description: string;
      amount: number;
      amount_label: string;
      period: string;
      status: string;
    }>;
  };
  cob_implementation: {
    absent_reason?: string;
    coverage?: {
      mentioned_in_report: boolean;
      context_length: number;
      analysis_depth: string;
    };
    issues?: string[];
    budget_implementation?: Record<string, any>;
  };
  kpis: {
    budget_execution_rate?: number;
    pending_bills?: number;
    financial_health_score?: number;
  };
}
