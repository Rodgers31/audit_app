/**
 * Counties API service
 */
import {
  AccountabilityScorecard,
  BudgetSource,
  County,
  CountyComprehensive,
  CountyRevenue,
} from '@/types';
import type { CountyFiscalYears } from '@/lib/utils';
import { apiClient } from './axios';
import { apiGet } from './request';
import { COUNTIES_ENDPOINTS, buildUrlWithParams } from './endpoints';
import { ApiResponse, CountyFilters, CountyResponse, PaginatedResponse } from './types';
import { financialHealthBand } from '@/lib/counties/financialHealth';

// Backend county response type — matches the real /api/v1/counties endpoint shape
interface BackendCountyResponse {
  id: string;
  name: string;
  code?: string;
  // Null where no KNBS census row exists for the county. The endpoint used to
  // send 0 there, which is a count, not an absence.
  population: number | null;
  budget_2025: number;
  financial_health_score?: number | null;
  audit_rating: string; // severity: info/warning/critical
  audit_status: string; // clean/qualified/adverse/disclaimer/pending
  last_audit_date?: string;
  audit_findings_count?: number;
  // Budget
  coordinates?: [number, number];
  total_budget?: number;
  financial_summary?: { total_allocation: number | null; accounting_basis?: string | null };
  total_spent?: number;
  budget_utilization?: number;
  development_budget?: number;
  recurrent_budget?: number;
  /** 'cob_cbirr' | 'cra_model' | null — which rows the API summed for
   *  total_budget. null when it published no budget for this county. */
  budget_source?: BudgetSource;
  sector_breakdown?: Record<string, { allocated: number; spent: number }>;
  // Revenue / money
  /** Withheld (null) by the API since #238: it was the budget under another name. */
  money_received?: number | null;
  revenue_collection?: number;
  revenue?: CountyRevenue;
  pending_bills?: number | null;
  // Debt
  debt?: number | null;
  total_debt?: number | null;
  total_debt_absent_reason?: string | null;
  debt_currency?: string | null;
  debt_accounting_basis?: string;
  debt_basis?: 'actual' | null;
  debt_as_at?: string | null;
  debt_coverage?: string;
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

/** A reported figure, including zero. The API explicitly withholds absence. */
const reportedAmount = (v: number | null | undefined): number | undefined =>
  typeof v === 'number' && Number.isFinite(v) ? v : undefined;

// Legacy budget aliases still lack the supported summary contract.
const publishedAmount = (...candidates: Array<number | null | undefined>): number | undefined => {
  for (const v of candidates) {
    if (typeof v === 'number' && Number.isFinite(v) && v !== 0) return v;
  }
  return undefined;
};

/** Required identity shared by the list, legacy detail and comprehensive detail.
 * Reject the response as a whole: inventing a name or dropping one bad row
 * would publish a plausible but incomplete county report. Keep route IDs
 * verbatim; official county-code metadata uses a separate namespace.
 */
function assertCountyIdentity(value: unknown): asserts value is { id: string; name: string } {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Invalid county response: expected a county object');
  }
  const county = value as Record<string, unknown>;
  for (const field of ['id', 'name'] as const) {
    if (typeof county[field] !== 'string' || county[field].trim().length === 0) {
      throw new Error(`Invalid county response: ${field} must be a nonblank string`);
    }
  }
}

// Financial/provenance fields retain their existing transformations. This
// boundary validates required identity, not completeness of financial coverage.
export const transformCountyData = (value: unknown): County => {
  assertCountyIdentity(value);
  const bc = value as BackendCountyResponse;
  // Use real coordinates from backend; undefined if not provided (do not default to Nairobi)
  const coordinates: [number, number] | undefined = bc.coordinates || undefined;
  const budget = bc.financial_summary
    ? reportedAmount(bc.financial_summary.total_allocation)
    : publishedAmount(bc.total_budget, bc.budget_2025);
  // A declared current total is authoritative, including zero or withheld
  // null. Only an omitted field may use the historical alias.
  const reportedDebt = reportedAmount(bc.total_debt !== undefined ? bc.total_debt : bc.debt);
  const debt = reportedDebt !== undefined && reportedDebt >= 0 ? reportedDebt : undefined;

  // Fiscal grade — from the backend's financial-health index, NOT an audit
  // opinion. Kept in its own field so the UI can never present a computed
  // number as an OAG audit rating: production currently has audit_rating="" /
  // audit_status="pending" for many counties, and this derived grade used to
  // be displayed as "Audit Rating".
  //
  // The index combines absorption, own-source revenue performance,
  // pending-bill burden and a more heavily weighted audit opinion.
  //
  // `|| 0` here graded a county with no score at all a "C". The backend now
  // returns null when fewer than two components can be computed, and a county
  // nobody can score must not be given the lowest grade.
  const score = reportedAmount(bc.financial_health_score);
  const fiscalGrade = financialHealthBand(score)?.grade;

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
    // Money received, or nothing. It used to fall back to `total_spent`,
    // publishing what a county SPENT as what it received (#238).
    moneyReceived: reportedAmount(bc.money_received),
    budgetUtilization: bc.budget_utilization ?? undefined,
    revenueCollection: bc.revenue_collection ?? undefined,
    revenue: bc.revenue,
    // `?? 0` here published a zero for a county with no figure. The API now
    // returns null when nobody has published one — Nandi reported no trade
    // payables to the Controller of Budget at 30 June 2026, and the report
    // says so — and "owes nothing" is a different claim from "not reported".
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
    totalDebtAbsentReason: bc.total_debt_absent_reason,
    debtCurrency: bc.debt_currency,
    debtAccountingBasis: bc.debt_accounting_basis,
    debtBasis: bc.debt_basis,
    debtAsAt: bc.debt_as_at,
    debtCoverage: bc.debt_coverage,
    education: sectorVal('Education'),
    health: sectorVal('Health Services') || sectorVal('Health'),
    infrastructure: sectorVal('Roads and Public Works') || sectorVal('Infrastructure'),
  };
};

// Raw county list shared by transformed readers and the comparison's SSR/client
// readers. Only identity is validated; each reader retains its financial schema.
export const getCountyList = async <T extends { id: string; name: string } = BackendCountyResponse>(
  filters?: CountyFilters,
  signal?: AbortSignal
): Promise<T[]> => {
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
  const response = await apiGet<T[]>(apiClient, url, signal);

  if (!Array.isArray(response.data)) {
    throw new Error('Invalid county response: expected a county list');
  }
  for (const county of response.data) assertCountyIdentity(county);
  return response.data;
};

// Get all counties with optional filtering and the existing financial mapping.
export const getCounties = async (filters?: CountyFilters, signal?: AbortSignal): Promise<County[]> =>
  (await getCountyList(filters, signal)).map(transformCountyData);

// Get single county by ID
export const getCounty = async (id: string, signal?: AbortSignal): Promise<County> => {
  const response = await apiGet<unknown>(apiClient, COUNTIES_ENDPOINTS.GET_BY_ID(id), signal);
  return transformCountyData(response.data);
};

// Get county by code (e.g., 'NBI' for Nairobi)
export const getCountyByCode = async (code: string, signal?: AbortSignal): Promise<CountyResponse> => {
  const response = await apiGet<ApiResponse<CountyResponse>>(
    apiClient,
    COUNTIES_ENDPOINTS.GET_BY_CODE(code),
    signal
  );
  return response.data.data;
};

// Get counties with pagination
export const getCountiesPaginated = async (
  page: number = 1,
  limit: number = 20,
  filters?: Omit<CountyFilters, 'page' | 'limit'>,
  signal?: AbortSignal
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

  const response = await apiGet<PaginatedResponse<CountyResponse>>(apiClient, url, signal);
  return response.data;
};

// Get county financial summary
export const getCountyFinancialSummary = async (id: string, signal?: AbortSignal): Promise<any> => {
  const response = await apiGet<ApiResponse<any>>(apiClient, COUNTIES_ENDPOINTS.FINANCIAL_SUMMARY(id), signal);
  return response.data.data;
};

// Search counties by name
export const searchCounties = async (query: string, signal?: AbortSignal): Promise<CountyResponse[]> => {
  const url = buildUrlWithParams(COUNTIES_ENDPOINTS.SEARCH, { q: query });
  const response = await apiGet<ApiResponse<CountyResponse[]>>(apiClient, url, signal);
  return response.data.data;
};

// Get top performing counties
export const getTopPerformingCounties = async (limit: number = 10, signal?: AbortSignal): Promise<CountyResponse[]> => {
  const url = buildUrlWithParams(COUNTIES_ENDPOINTS.TOP_PERFORMING, { limit });
  const response = await apiGet<ApiResponse<CountyResponse[]>>(apiClient, url, signal);
  return response.data.data;
};

// Get counties with issues/flags
export const getFlaggedCounties = async (signal?: AbortSignal): Promise<CountyResponse[]> => {
  const response = await apiGet<ApiResponse<CountyResponse[]>>(apiClient, COUNTIES_ENDPOINTS.FLAGGED, signal);
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
export const getCountyFiscalYears = async (signal?: AbortSignal): Promise<CountyFiscalYears> => {
  const response = await apiGet<CountyFiscalYears>(
    apiClient,
    COUNTIES_ENDPOINTS.FISCAL_YEARS,
    signal
  );
  return response.data;
};

// Get comprehensive county data (one-stop detail)
// fiscalYear (e.g. "2024/25") scopes the health/budget snapshot to that FY.
// When omitted, the backend falls back to the latest period with execution data.
export const getCountyComprehensive = async (
  id: string,
  fiscalYear?: string,
  signal?: AbortSignal
): Promise<CountyComprehensive> => {
  const base = COUNTIES_ENDPOINTS.COMPREHENSIVE(id);
  const url = fiscalYear ? buildUrlWithParams(base, { fiscal_year: fiscalYear }) : base;
  const response = await apiGet<CountyComprehensive>(apiClient, url, signal);
  assertCountyIdentity(response.data);
  return response.data;
};

// Get county accountability scorecard
export const getCountyAccountability = async (id: string, signal?: AbortSignal): Promise<AccountabilityScorecard> => {
  const response = await apiGet<AccountabilityScorecard>(
    apiClient,
    COUNTIES_ENDPOINTS.ACCOUNTABILITY(id),
    signal
  );
  return response.data;
};
