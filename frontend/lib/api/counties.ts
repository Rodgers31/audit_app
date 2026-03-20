/**
 * Counties API service
 */
import { AccountabilityScorecard, County, CountyComprehensive } from '@/types';
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
  financial_health_score: number;
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
  sector_breakdown?: Record<string, { allocated: number; spent: number }>;
  // Revenue / money
  money_received?: number;
  revenue_collection?: number;
  pending_bills?: number;
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

// Transform backend county data to frontend County type
const transformCountyData = (bc: BackendCountyResponse): County => {
  const coordinates: [number, number] = bc.coordinates || [36.8219, -1.2921];
  const budget = bc.total_budget || bc.budget_2025 || 0;
  const debt = bc.total_debt || bc.debt || 0;

  // Build letter-grade audit_rating from financial_health_score when
  // the backend returns severity strings ("info"/"warning"/"critical").
  const score = bc.financial_health_score || 0;
  const letterGrade =
    score >= 85 ? 'A' : score >= 70 ? 'B+' : score >= 55 ? 'B' : score >= 40 ? 'B-' : 'C';

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
    financial_health_score: bc.financial_health_score,
    audit_rating: letterGrade,
    budget,
    debt,
    population: bc.population,
    auditStatus,
    lastAuditDate: bc.last_audit_date || undefined,
    gdp: bc.gdp ?? 0,
    moneyReceived: bc.money_received || bc.total_spent || 0,
    budgetUtilization: bc.budget_utilization || 0,
    revenueCollection: bc.revenue_collection || 0,
    pendingBills: bc.pending_bills || 0,
    developmentBudget: bc.development_budget || 0,
    recurrentBudget: bc.recurrent_budget || 0,
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

// Get comprehensive county data (one-stop detail)
export const getCountyComprehensive = async (id: string): Promise<CountyComprehensive> => {
  const response = await apiClient.get<CountyComprehensive>(COUNTIES_ENDPOINTS.COMPREHENSIVE(id));
  return response.data;
};

// Get county accountability scorecard
export const getCountyAccountability = async (id: string): Promise<AccountabilityScorecard> => {
  const response = await apiClient.get<AccountabilityScorecard>(
    COUNTIES_ENDPOINTS.ACCOUNTABILITY(id)
  );
  return response.data;
};
