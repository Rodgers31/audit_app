/**
 * Audits API service
 */
import { apiClient } from './axios';
import { AUDITS_ENDPOINTS, COUNTIES_ENDPOINTS, buildUrlWithParams } from './endpoints';
import {
  ApiResponse,
  AuditFilters,
  AuditReportResponse,
  CountyAuditsEnriched,
  PaginatedResponse,
} from './types';

// Get all audit reports with optional filtering
export const getAuditReports = async (filters?: AuditFilters): Promise<AuditReportResponse[]> => {
  const queryParams: Record<string, any> = {};

  if (filters?.countyId) queryParams.county_id = filters.countyId;
  if (filters?.fiscalYear) queryParams.fiscal_year = filters.fiscalYear;
  if (filters?.auditStatus?.length) queryParams.audit_status = filters.auditStatus;
  if (filters?.concernLevel?.length) queryParams.concern_level = filters.concernLevel;
  if (filters?.page) queryParams.page = filters.page;
  if (filters?.limit) queryParams.limit = filters.limit;

  const url = buildUrlWithParams(AUDITS_ENDPOINTS.LIST, queryParams);
  const response = await apiClient.get<ApiResponse<AuditReportResponse[]>>(url);
  return response.data.data;
};

// Get single audit report by ID
export const getAuditReport = async (id: string): Promise<AuditReportResponse> => {
  const response = await apiClient.get<ApiResponse<AuditReportResponse>>(
    AUDITS_ENDPOINTS.GET_BY_ID(id)
  );
  return response.data.data;
};

// Get audit reports for a specific county
export const getCountyAuditReports = async (
  countyId: string,
  fiscalYear?: string
): Promise<AuditReportResponse[]> => {
  const queryParams: Record<string, any> = {};
  if (fiscalYear) queryParams.fiscal_year = fiscalYear;

  const url = buildUrlWithParams(COUNTIES_ENDPOINTS.AUDITS(countyId), queryParams);
  const response = await apiClient.get<ApiResponse<AuditReportResponse[]>>(url);
  return response.data.data;
};

// Get latest audit report for a county
export const getLatestCountyAudit = async (countyId: string): Promise<AuditReportResponse> => {
  const response = await apiClient.get<ApiResponse<AuditReportResponse>>(
    COUNTIES_ENDPOINTS.LATEST_AUDIT(countyId)
  );
  return response.data.data;
};

// Get enriched county audits aggregation for modal/report
export const getCountyAuditsEnriched = async (countyId: string): Promise<CountyAuditsEnriched> => {
  const response = await apiClient.get<CountyAuditsEnriched>(COUNTIES_ENDPOINTS.AUDITS(countyId));
  return response.data;
};

// List county audit findings with filters/pagination and provenance
export interface CountyAuditListItem {
  id: string | number;
  description?: string;
  severity?: string;
  status?: string;
  category?: string;
  amountLabel?: string;
  fiscal_year?: string;
  source: { title?: string; url?: string; page?: number | string; table_index?: number };
}

export interface CountyAuditListResponse {
  total: number;
  page: number;
  limit: number;
  items: CountyAuditListItem[];
}

export const getCountyAuditList = async (
  countyId: string,
  params?: { page?: number; limit?: number; year?: string; status?: string; severity?: string }
): Promise<CountyAuditListResponse> => {
  const qp: Record<string, any> = {};
  if (params?.page) qp.page = params.page;
  if (params?.limit) qp.limit = params.limit;
  if (params?.year) qp.year = params.year;
  if (params?.status) qp.status = params.status;
  if (params?.severity) qp.severity = params.severity;
  const url = buildUrlWithParams(COUNTIES_ENDPOINTS.AUDITS_LIST(countyId), qp);
  const { data } = await apiClient.get<CountyAuditListResponse>(url);
  return data;
};

// Get audit reports with pagination
export const getAuditReportsPaginated = async (
  page: number = 1,
  limit: number = 20,
  filters?: Omit<AuditFilters, 'page' | 'limit'>
): Promise<PaginatedResponse<AuditReportResponse>> => {
  const queryParams: Record<string, any> = {
    page,
    limit,
  };

  if (filters?.countyId) queryParams.county_id = filters.countyId;
  if (filters?.fiscalYear) queryParams.fiscal_year = filters.fiscalYear;
  if (filters?.auditStatus?.length) queryParams.audit_status = filters.auditStatus;
  if (filters?.concernLevel?.length) queryParams.concern_level = filters.concernLevel;

  const url = buildUrlWithParams(AUDITS_ENDPOINTS.PAGINATED, queryParams);
  const response = await apiClient.get<PaginatedResponse<AuditReportResponse>>(url);
  return response.data;
};

// Get audit statistics
export const getAuditStatistics = async (): Promise<any> => {
  const response = await apiClient.get<ApiResponse<any>>(AUDITS_ENDPOINTS.STATISTICS);
  return response.data.data;
};

// Federal / national government audit findings
export interface FederalAuditFinding {
  id: number;
  entity_name: string;
  entity_type: string;
  finding: string;
  severity: string;
  recommended_action: string;
  amount_involved: string;
  amount_numeric: number;
  status: string;
  category: string;
  query_type: string;
  report_section: string;
  date_raised: string;
  date: string | null;
}

export interface FederalAuditResponse {
  report_title: string;
  auditor_general: string;
  fiscal_year: string;
  report_date: string;
  opinion_type: string;
  total_findings: number;
  total_amount_questioned: number;
  total_amount_questioned_label: string;
  by_severity: Record<string, number>;
  basis_for_qualification: string[];
  emphasis_of_matter: string[];
  key_statistics: {
    total_ministries_audited: number;
    total_findings: number;
    critical_findings: number;
    significant_findings: number;
    minor_findings: number;
    total_amount_flagged_kes: number;
    response_rate_to_previous_queries: string;
    recurring_issues_from_prior_year: number;
  };
  findings: FederalAuditFinding[];
  top_ministries: { ministry: string; finding_count: number }[];
  last_updated: string;
}

export const getFederalAudits = async (): Promise<FederalAuditResponse> => {
  const response = await apiClient.get<FederalAuditResponse>(AUDITS_ENDPOINTS.FEDERAL);
  return response.data;
};

// Get fiscal years with available audit data
export const getAvailableFiscalYears = async (): Promise<string[]> => {
  const response = await apiClient.get<ApiResponse<string[]>>(AUDITS_ENDPOINTS.FISCAL_YEARS);
  return response.data.data;
};

// ===== National Audit Dashboard API =====

export interface WorstCounty {
  county_id: number;
  county_name: string;
  total_amount: number;
  finding_count: number;
}

export interface AuditDashboardSummary {
  total_irregular_expenditure: number;
  total_unsupported_expenditure: number;
  total_findings: number;
  findings_by_type: Record<string, number>;
  findings_by_opinion: Record<string, number>;
  worst_counties: WorstCounty[];
  year_range: { min_year: number | null; max_year: number | null };
}

export interface AuditTrendsData {
  years: number[];
  findings_per_year: Record<string, number>;
  amount_per_year: Record<string, number>;
  opinion_per_year: Record<string, Record<string, number>>;
}

export interface RecurringFindingItem {
  county_name: string;
  query_type: string;
  years_appeared: number[];
  total_amount: number;
  finding_ids: number[];
}

export interface RecurringFindingsData {
  recurring_findings: RecurringFindingItem[];
  total: number;
}

export interface FindingDetailItem {
  id: number;
  entity_id: number;
  county_name: string | null;
  period_id: number;
  finding_text: string;
  severity: string;
  recommended_action: string | null;
  query_type: string | null;
  amount: number | null;
  status: string | null;
  audit_opinion: string | null;
  audit_year: number | null;
  follow_up_status: string | null;
  external_reference: string | null;
  management_response: string | null;
}

export interface FindingsListData {
  items: FindingDetailItem[];
  total: number;
  page: number;
  limit: number;
}

export interface FindingsFilters {
  county_id?: number;
  year?: number;
  query_type?: string;
  severity?: string;
  audit_opinion?: string;
  status?: string;
  page?: number;
  limit?: number;
}

export const getAuditDashboardSummary = async (): Promise<AuditDashboardSummary> => {
  const response = await apiClient.get<AuditDashboardSummary>(AUDITS_ENDPOINTS.DASHBOARD_SUMMARY);
  return response.data;
};

export const getAuditTrends = async (params?: {
  county_id?: number;
  query_type?: string;
}): Promise<AuditTrendsData> => {
  const qp: Record<string, any> = {};
  if (params?.county_id) qp.county_id = params.county_id;
  if (params?.query_type) qp.query_type = params.query_type;
  const url = buildUrlWithParams(AUDITS_ENDPOINTS.DASHBOARD_TRENDS, qp);
  const response = await apiClient.get<AuditTrendsData>(url);
  return response.data;
};

export const getRecurringFindings = async (): Promise<RecurringFindingsData> => {
  const response = await apiClient.get<RecurringFindingsData>(AUDITS_ENDPOINTS.DASHBOARD_RECURRING);
  return response.data;
};

export const getAuditFindings = async (filters?: FindingsFilters): Promise<FindingsListData> => {
  const qp: Record<string, any> = {};
  if (filters?.county_id) qp.county_id = filters.county_id;
  if (filters?.year) qp.year = filters.year;
  if (filters?.query_type) qp.query_type = filters.query_type;
  if (filters?.severity) qp.severity = filters.severity;
  if (filters?.audit_opinion) qp.audit_opinion = filters.audit_opinion;
  if (filters?.status) qp.status = filters.status;
  if (filters?.page) qp.page = filters.page;
  if (filters?.limit) qp.limit = filters.limit;
  const url = buildUrlWithParams(AUDITS_ENDPOINTS.DASHBOARD_FINDINGS, qp);
  const response = await apiClient.get<FindingsListData>(url);
  return response.data;
};
