/**
 * Counties API service
 */
import {
  AccountabilityScorecard,
  BudgetSource,
  County,
  CountyComprehensive,
} from '@/types';
import type { CountyFiscalYears } from '@/lib/utils';
import { apiClient } from './axios';
import { COUNTIES_ENDPOINTS, buildUrlWithParams } from './endpoints';
import { ApiResponse, CountyFilters, CountyResponse, PaginatedResponse } from './types';

// Backend county response type — matches the real /api/v1/counties endpoint shape
interface BackendCountyResponse {
  id: string;
  name: string;
  code?: string;
  population: number;
  budget_2025: number;
  financial_health_score?: number | null;
  audit_rating: string; // severity: info/warning/critical
  audit_status: string; // clean/qualified/adverse/disclaimer/pending
  last_audit_date?: string;
  audit_findings_count?: number;
  // Budget
  coordinates?: [number, number];
  total_budget?: number;
  total_spent?: number;
  budget_utilization?: number;
  development_budget?: number;
  recurrent_budget?: number;
  /** 'cob_cbirr' | 'cra_model' | null — which rows the API summed for
   *  total_budget. null when it published no budget for this county. */
  budget_source?: BudgetSource;
  sector_breakdown?: Record<string, { allocated: number; spent: number }>;
  // Revenue / money
  money_received?: number;
  revenue_collection?: number;
  pending_bills?: number | null;
  // Debt
  debt?: number;
  total_debt?: number;
  // Economic
  gdp?: number | null;
  // Audit issues
  audit_issues?: Array<{
    id: string;
    type: string;
    severity: string;
    description: string;
    status: string;
  }>;
  // Provenance
  data_freshness?: {
    budget_source?: number | null;
    last_audit_source?: number | null;
  };
}

/**
 * First figure the API actually published, or `undefined` when it published
 * none. Never 0 — this is the whole point.
 *
 * "The API did not publish this figure" and "the figure is zero" are different
 * claims, and collapsing the first into the second here made them
 * indistinguishable to every component downstream: an absent `money_received`
 * became a funding-gap alert for the county's entire budget, an absent debt
 * became a confident "0.0% debt ratio", and an absent budget became a county
 * allocated nothing.
 *
 * A zero arriving FROM the API is treated as absence too, deliberately. Every
 * field this is used on is a SUM over rows on the backend — budget lines for
 * `total_budget`, loan rows for `total_debt` — so 0.0 is an empty aggregate,
 * not a measured zero. No county is allocated nothing (all 47 receive an
 * equitable share by constitutional formula) and none has been shown to owe
 * exactly nothing, so treating 0 as absence loses no real figure while
 * stopping the UI from stating one the source never made. Non-finite values
 * are rejected for the same reason: NaN is not a figure either.
 */
/**
 * A figure the API reported, keeping a genuine zero.
 *
 * The counterpart to `publishedAmount`: that one drops zeros because the
 * fields it guards are backend SUMs, where 0 means "nothing aggregated". This
 * one guards a field the backend now nulls explicitly when no source
 * published a figure, so 0 can be taken at face value.
 */
const reportedAmount = (v: number | null | undefined): number | undefined =>
  typeof v === 'number' && Number.isFinite(v) ? v : undefined;

const publishedAmount = (...candidates: Array<number | null | undefined>): number | undefined => {
  for (const v of candidates) {
    if (typeof v === 'number' && Number.isFinite(v) && v !== 0) return v;
  }
  return undefined;
};

// Transform backend county data to frontend County type
export const transformCountyData = (bc: BackendCountyResponse): County => {
  // Use real coordinates from backend; undefined if not provided (do not default to Nairobi)
  const coordinates: [number, number] | undefined = bc.coordinates || undefined;
  const budget = publishedAmount(bc.total_budget, bc.budget_2025);
  const debt = publishedAmount(bc.total_debt, bc.debt);

  // Fiscal grade — from the backend's financial-health index, NOT an audit
  // opinion. Kept in its own field so the UI can never present a computed
  // number as an OAG audit rating: production currently has audit_rating="" /
  // audit_status="pending" for many counties, and this derived grade used to
  // be displayed as "Audit Rating".
  //
  // The index is no longer budget utilisation under another name — it is an
  // equal-weighted composite of absorption, own-source revenue performance,
  // pending-bill burden and audit opinion, and the API reports its components.
  //
  // `|| 0` here graded a county with no score at all a "C". The backend now
  // returns null when fewer than two components can be computed, and a county
  // nobody can score must not be given the lowest grade.
  const score = reportedAmount(bc.financial_health_score);
  const fiscalGrade =
    score == null
      ? undefined
      : score >= 85
        ? 'A'
        : score >= 70
          ? 'B+'
          : score >= 55
            ? 'B'
            : score >= 40
              ? 'B-'
              : 'C';

  // The backend already classifies audit_status – use it directly.
  const validStatuses = ['clean', 'qualified', 'adverse', 'disclaimer'];
  const auditStatus: County['auditStatus'] = validStatuses.includes(bc.audit_status)
    ? (bc.audit_status as County['auditStatus'])
    : 'pending';

  // Sector breakdown comes as { name: { allocated, spent } } — flatten to allocated amounts
  const sectors = bc.sector_breakdown || {};
  const sectorVal = (key: string) => {
    const entry = (sectors as any)[key];
    return entry?.allocated ?? entry ?? 0;
  };

  return {
    id: bc.id,
    name: bc.name,
    code: bc.code || bc.id,
    coordinates,
    budget_2025: bc.budget_2025,
    financial_health_score: score,
    // Real OAG rating only — empty until the audits pipeline provides one.
    // The backend currently mirrors audit SEVERITY ("info"/"warning"/
    // "critical") into audit_rating; that's a status, not a rating, so
    // treat it as "no rating" too instead of displaying "Rating: info".
    audit_rating: ['info', 'warning', 'critical'].includes(bc.audit_rating)
      ? ''
      : bc.audit_rating || '',
    fiscal_grade: fiscalGrade,
    budget,
    debt,
    population: bc.population,
    auditStatus,
    lastAuditDate: bc.last_audit_date || undefined,
    // The API genuinely returns gdp: null for every county — no county GDP
    // series is ingested. Rendering 0 said each county produces nothing (F2).
    gdp: bc.gdp ?? undefined,
    moneyReceived: publishedAmount(bc.money_received, bc.total_spent),
    budgetUtilization: bc.budget_utilization ?? undefined,
    revenueCollection: bc.revenue_collection ?? undefined,
    // `?? 0` here published a zero for a county with no figure. The API now
    // returns null when nobody has published one — Narok submitted no
    // pending-bills data to the Treasury for FY 2024/25, and the BROP says so
    // — and "owes nothing" is a different claim from "not reported".
    //
    // NOT publishedAmount(): that treats 0 as absence, which is right for the
    // backend's SUM-backed fields but wrong here. A publisher can report zero
    // pending bills, and that is a figure.
    pendingBills: reportedAmount(bc.pending_bills),
    developmentBudget: bc.development_budget || undefined,
    recurrentBudget: bc.recurrent_budget || undefined,
    // Passed through verbatim, including null: the provenance note treats
    // "no source reported" as a reason to make no claim, not as a default to
    // the modelled wording. `?? null` would be the same value; an older API
    // that omits the field entirely lands on undefined, which reads the same.
    budgetSource: bc.budget_source,
    auditIssues: (bc.audit_issues || []).map((a) => ({
      id: String(a.id),
      type: 'financial' as const,
      severity: (a.severity || 'medium') as 'low' | 'medium' | 'high' | 'critical',
      description: a.description || '',
      status: (a.status === 'open' ? 'open' : 'resolved') as 'open' | 'pending' | 'resolved',
    })),
    totalBudget: budget,
    totalDebt: debt,
    education: sectorVal('Education'),
    health: sectorVal('Health Services') || sectorVal('Health'),
    infrastructure: sectorVal('Roads and Public Works') || sectorVal('Infrastructure'),
  };
};

// Get all counties with optional filtering
export const getCounties = async (filters?: CountyFilters): Promise<County[]> => {
  const queryParams: Record<string, any> = {};

  if (filters?.search) queryParams.search = filters.search;
  if (filters?.auditStatus?.length) queryParams.audit_status = filters.auditStatus;
  if (filters?.debtLevel) queryParams.debt_level = filters.debtLevel;
  if (filters?.budgetRange) {
    queryParams.budget_min = filters.budgetRange[0];
    queryParams.budget_max = filters.budgetRange[1];
  }
  if (filters?.fiscalYear) queryParams.fiscal_year = filters.fiscalYear;
  if (filters?.page) queryParams.page = filters.page;
  if (filters?.limit) queryParams.limit = filters.limit;

  const url = buildUrlWithParams(COUNTIES_ENDPOINTS.LIST, queryParams);
  const response = await apiClient.get<BackendCountyResponse[]>(url);

  // Transform backend data to frontend County type
  return response.data.map(transformCountyData);
};

// Get single county by ID
export const getCounty = async (id: string): Promise<County> => {
  const response = await apiClient.get<BackendCountyResponse>(COUNTIES_ENDPOINTS.GET_BY_ID(id));
  return transformCountyData(response.data);
};

// Get county by code (e.g., 'NBI' for Nairobi)
export const getCountyByCode = async (code: string): Promise<CountyResponse> => {
  const response = await apiClient.get<ApiResponse<CountyResponse>>(
    COUNTIES_ENDPOINTS.GET_BY_CODE(code)
  );
  return response.data.data;
};

// Get counties with pagination
export const getCountiesPaginated = async (
  page: number = 1,
  limit: number = 20,
  filters?: Omit<CountyFilters, 'page' | 'limit'>
): Promise<PaginatedResponse<CountyResponse>> => {
  const queryParams: Record<string, any> = {
    page,
    limit,
  };

  if (filters?.search) queryParams.search = filters.search;
  if (filters?.auditStatus?.length) queryParams.audit_status = filters.auditStatus;
  if (filters?.debtLevel) queryParams.debt_level = filters.debtLevel;
  if (filters?.budgetRange) {
    queryParams.budget_min = filters.budgetRange[0];
    queryParams.budget_max = filters.budgetRange[1];
  }

  const url = buildUrlWithParams(COUNTIES_ENDPOINTS.PAGINATED, queryParams);

  const response = await apiClient.get<PaginatedResponse<CountyResponse>>(url);
  return response.data;
};

// Get county financial summary
export const getCountyFinancialSummary = async (id: string): Promise<any> => {
  const response = await apiClient.get<ApiResponse<any>>(COUNTIES_ENDPOINTS.FINANCIAL_SUMMARY(id));
  return response.data.data;
};

// Search counties by name
export const searchCounties = async (query: string): Promise<CountyResponse[]> => {
  const url = buildUrlWithParams(COUNTIES_ENDPOINTS.SEARCH, { q: query });
  const response = await apiClient.get<ApiResponse<CountyResponse[]>>(url);
  return response.data.data;
};

// Get top performing counties
export const getTopPerformingCounties = async (limit: number = 10): Promise<CountyResponse[]> => {
  const url = buildUrlWithParams(COUNTIES_ENDPOINTS.TOP_PERFORMING, { limit });
  const response = await apiClient.get<ApiResponse<CountyResponse[]>>(url);
  return response.data.data;
};

// Get counties with issues/flags
export const getFlaggedCounties = async (): Promise<CountyResponse[]> => {
  const response = await apiClient.get<ApiResponse<CountyResponse[]>>(COUNTIES_ENDPOINTS.FLAGGED);
  return response.data.data;
};

/**
 * Which fiscal years county budget data exists for, and which one the API
 * resolves to when asked for none.
 *
 * The explorer's year picker was seeded from the calendar, which named the
 * in-progress FY — a CRA projection — while the county detail pages let the
 * API resolve the period from the rows that exist. The two published different
 * budgets for the same county. This is the one source both now use.
 */
export const getCountyFiscalYears = async (): Promise<CountyFiscalYears> => {
  const response = await apiClient.get<CountyFiscalYears>(
    COUNTIES_ENDPOINTS.FISCAL_YEARS
  );
  return response.data;
};

// Get comprehensive county data (one-stop detail)
// fiscalYear (e.g. "2024/25") scopes the health/budget snapshot to that FY.
// When omitted, the backend falls back to the latest period with execution data.
export const getCountyComprehensive = async (
  id: string,
  fiscalYear?: string
): Promise<CountyComprehensive> => {
  const base = COUNTIES_ENDPOINTS.COMPREHENSIVE(id);
  const url = fiscalYear ? buildUrlWithParams(base, { fiscal_year: fiscalYear }) : base;
  const response = await apiClient.get<CountyComprehensive>(url);
  return response.data;
};

// Get county accountability scorecard
export const getCountyAccountability = async (id: string): Promise<AccountabilityScorecard> => {
  const response = await apiClient.get<AccountabilityScorecard>(
    COUNTIES_ENDPOINTS.ACCOUNTABILITY(id)
  );
  return response.data;
};
