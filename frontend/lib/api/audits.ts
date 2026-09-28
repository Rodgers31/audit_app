/**
 * Audits API service
 */
import { apiClient } from './axios';
import { apiGet } from './request';
import { AUDITS_ENDPOINTS, COUNTIES_ENDPOINTS, buildUrlWithParams } from './endpoints';
import {
  ApiResponse,
  AuditFilters,
  AuditReportResponse,
  CountyAuditsEnriched,
  PaginatedResponse,
} from './types';

// Get all audit reports with optional filtering
export const getAuditReports = async (filters?: AuditFilters, signal?: AbortSignal): Promise<AuditReportResponse[]> => {
  const queryParams: Record<string, any> = {};

  if (filters?.countyId) queryParams.county_id = filters.countyId;
  if (filters?.fiscalYear) queryParams.fiscal_year = filters.fiscalYear;
  if (filters?.auditStatus?.length) queryParams.audit_status = filters.auditStatus;
  if (filters?.concernLevel?.length) queryParams.concern_level = filters.concernLevel;
  if (filters?.page) queryParams.page = filters.page;
  if (filters?.limit) queryParams.limit = filters.limit;

  const url = buildUrlWithParams(AUDITS_ENDPOINTS.LIST, queryParams);
  const response = await apiGet<ApiResponse<AuditReportResponse[]>>(apiClient, url, signal);
  return response.data.data;
};

// Get single audit report by ID
export const getAuditReport = async (id: string, signal?: AbortSignal): Promise<AuditReportResponse> => {
  const response = await apiGet<ApiResponse<AuditReportResponse>>(
    apiClient,
    AUDITS_ENDPOINTS.GET_BY_ID(id),
    signal
  );
  return response.data.data;
};

// Get audit reports for a specific county
export const getCountyAuditReports = async (
  countyId: string,
  fiscalYear?: string,
  signal?: AbortSignal
): Promise<AuditReportResponse[]> => {
  const queryParams: Record<string, any> = {};
  if (fiscalYear) queryParams.fiscal_year = fiscalYear;

  const url = buildUrlWithParams(COUNTIES_ENDPOINTS.AUDITS(countyId), queryParams);
  const response = await apiGet<ApiResponse<AuditReportResponse[]>>(apiClient, url, signal);
  return response.data.data;
};

// Get latest audit report for a county
export const getLatestCountyAudit = async (countyId: string, signal?: AbortSignal): Promise<AuditReportResponse> => {
  const response = await apiGet<ApiResponse<AuditReportResponse>>(
    apiClient,
    COUNTIES_ENDPOINTS.LATEST_AUDIT(countyId),
    signal
  );
  return response.data.data;
};

// Get enriched county audits aggregation for modal/report
export const getCountyAuditsEnriched = async (countyId: string, signal?: AbortSignal): Promise<CountyAuditsEnriched> => {
  const response = await apiGet<CountyAuditsEnriched>(apiClient, COUNTIES_ENDPOINTS.AUDITS(countyId), signal);
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
  params?: { page?: number; limit?: number; year?: string; status?: string; severity?: string },
  signal?: AbortSignal
): Promise<CountyAuditListResponse> => {
  const qp: Record<string, any> = {};
  if (params?.page) qp.page = params.page;
  if (params?.limit) qp.limit = params.limit;
  if (params?.year) qp.year = params.year;
  if (params?.status) qp.status = params.status;
  if (params?.severity) qp.severity = params.severity;
  const url = buildUrlWithParams(COUNTIES_ENDPOINTS.AUDITS_LIST(countyId), qp);
  const { data } = await apiGet<CountyAuditListResponse>(apiClient, url, signal);
  return data;
};

// Get audit reports with pagination
export const getAuditReportsPaginated = async (
  page: number = 1,
  limit: number = 20,
  filters?: Omit<AuditFilters, 'page' | 'limit'>,
  signal?: AbortSignal
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
  const response = await apiGet<PaginatedResponse<AuditReportResponse>>(apiClient, url, signal);
  return response.data;
};

// Get audit statistics
export const getAuditStatistics = async (signal?: AbortSignal): Promise<any> => {
  const response = await apiGet<ApiResponse<any>>(apiClient, AUDITS_ENDPOINTS.STATISTICS, signal);
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
  /** The figure this finding states, or null when the report states none —
   *  which is the ordinary case (764 of 813 in FY2024/25). It was 0 before,
   *  which made "no figure stated" indistinguishable from "nothing
   *  questioned" for anything summing or sorting this array. */
  amount_numeric: number | null;
  status: string;
  category: string;
  query_type: string;
  report_section: string;
  date_raised: string;
  date: string | null;
  /** Extraction-backed provenance (Stage 2): the report paragraph's title,
   *  the PDF page the finding was extracted from ("p.106"), and the source
   *  document URL a reader can open to check it. */
  title?: string | null;
  page_ref?: string | null;
  source_url?: string | null;
}

/** A count with the page a reader can open to check it. */
interface PageCited {
  page_ref: string | null;
  source_url: string | null;
}

export type ModifiedOpinion = 'Adverse' | 'Disclaimer' | 'Qualified';

/** backend/services/audit_derived.py::derive_federal_headline. Every count
 *  is a floor: the opinion could only be read for `entities_opinion_read` of
 *  `entities_with_findings` votes. No vote is ever reported as clean. */
export interface FederalAuditHeadline {
  basis: 'extracted_section_headings';
  source_document: { id: number; title: string | null; url: string | null };
  entities_with_findings: number;
  /** Rows of the report's "unresolved prior-year issues" tables that the
   *  extractor read as findings; excluded from every count here. */
  excluded_table_rows: number;
  entities_opinion_read: number;
  /** Only the opinions actually found — a missing category is absent, never 0. */
  modified_opinions: { opinion: ModifiedOpinion; entities: number; findings: number }[];
  entities: ({ entity: string; opinion: ModifiedOpinion; findings: number } & PageCited)[];
  recurring_prior_year: ({ entities: number; findings: number } & PageCited) | null;
  emphasis_of_matter:
    | ({
        entities: number;
        findings: number;
        most_common_title: string | null;
        most_common_findings: number | null;
      } & PageCited)
    | null;
}

export interface FederalAuditResponse {
  /** All four describe one document. Each is null when nothing resolves to
   *  a report a reader could open. */
  report_title: string | null;
  auditor_general: string | null;
  fiscal_year: string | null;
  report_date: string | null;
  total_findings: number;
  // The report's own questioned total. Nothing extracts it, so it is null
  // with `total_amount_questioned_reason: "not_extracted"` (issue #233).
  // NOT a naive sum of finding amounts.
  total_amount_questioned: number | null;
  total_amount_questioned_reason?: string | null;
  /** Findings excluded by the publication gate. */
  withheld_findings?: number;
  /** The same count, by the gate's reason slug. Sums to withheld_findings. */
  withheld_findings_by_reason?: Record<string, number>;
  // Transparency only: raw sum across all finding amounts (not "questioned").
  total_amount_in_findings?: number;
  /** How many findings the `total_amount_in_findings` sum covers. A
   *  partial sum with no denominator cannot be told apart from a total. */
  findings_with_amount: number;
  by_severity: Record<string, number>;
  /** Derived from the latest report's extracted findings; null when that
   *  report has none (`headline_reason` says so). */
  headline: FederalAuditHeadline | null;
  headline_reason?: 'no_extraction_backed_findings' | null;
  findings: FederalAuditFinding[];
  top_ministries: { ministry: string; finding_count: number }[];
  /** Why `findings` is empty, when it is: "awaiting_sourced_data" (rows
   *  exist but are withheld for lack of a traceable source) or
   *  "no_findings_recorded". Null when findings are published. */
  findings_reason?: 'awaiting_sourced_data' | 'no_findings_recorded' | null;
  /** When the next OAG publication is expected — computed by the backend
   *  from the Layer-1 source registry, never hand-written in the UI. */
  next_expected?: {
    dataset: string;
    publisher: string | null;
    cadence: string | null;
    lag: string | number | null;
    lag_unit: 'months' | 'days';
    window_start: string | null;
    window_end: string | null;
    in_window: boolean;
  } | null;
  last_updated: string | null;
}

/**
 * `topFindings` asks for only the N largest findings that state an amount;
 * every summary field still describes all of them (`total_findings` is the
 * report's count). See `select_top_stated_findings` in backend/main.py.
 */
export const getFederalAudits = async (params?: {
  topFindings?: number;
},
  signal?: AbortSignal
): Promise<FederalAuditResponse> => {
  const url = buildUrlWithParams(AUDITS_ENDPOINTS.FEDERAL, {
    top_findings: params?.topFindings,
  });
  const response = await apiGet<FederalAuditResponse>(apiClient, url, signal);
  return response.data;
};

// Get fiscal years with available audit data
export const getAvailableFiscalYears = async (signal?: AbortSignal): Promise<string[]> => {
  const response = await apiGet<ApiResponse<string[]>>(apiClient, AUDITS_ENDPOINTS.FISCAL_YEARS, signal);
  return response.data.data;
};

// ===== National Audit Dashboard API =====

export interface WorstCounty {
  county_id: number;
  county_name: string;
  total_amount: number;
  finding_count: number;
}

/**
 * A published figure, or absence with the reason stated.
 *
 * `value: null` means NOT PUBLISHED. It never means zero — `0` here would be a
 * claim about the world ("the Auditor-General questioned nothing"), and the
 * API deliberately spells the two differently. Render `null` as an em dash and
 * show `reason`; never coerce it with `?? 0` or `|| 0`.
 */
export interface WithheldFigure {
  value: number | null;
  reason: string | null;
}

export interface AuditDashboardSummary {
  total_irregular_expenditure: WithheldFigure;
  total_unsupported_expenditure: WithheldFigure;
  total_findings: number;
  findings_by_type: Record<string, number>;
  /** `null` when the facet is not published — see `findings_by_opinion_reason`. */
  findings_by_opinion: Record<string, number> | null;
  findings_by_opinion_reason: string | null;
  /**
   * `null` — not published. A ranking of named counties by flagged amount is
   * not supported by the data behind it; see `worst_counties_reason`. Never
   * an empty array as a stand-in for absence.
   */
  worst_counties: WorstCounty[] | null;
  worst_counties_reason: string | null;
  year_range: { min_year: number | null; max_year: number | null };
}

export interface AuditTrendsData {
  years: number[];
  findings_per_year: Record<string, number>;
  amount_per_year: Record<string, number>;
  /** `null` when the facet is not published — see `opinion_per_year_reason`. */
  opinion_per_year: Record<string, Record<string, number>> | null;
  opinion_per_year_reason: string | null;
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
  /**
   * Why the list is empty, when it is. "0 patterns" is a claim about Kenyan
   * county audits; what the backend can actually assert is narrower — that no
   * entity and section appears in two or more of the audit years published.
   * Present only when there is nothing to show.
   */
  absent_reason?: string | null;
}

export interface FindingDetailItem {
  id: number;
  entity_id: number;
  county_name: string | null;
  county_slug?: string | null;
  audited_entity_name?: string | null;
  page_ref?: string | null;
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
  source_document_url: string | null;
  confidence_score: number | null;
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

export const getAuditDashboardSummary = async (signal?: AbortSignal): Promise<AuditDashboardSummary> => {
  const response = await apiGet<AuditDashboardSummary>(apiClient, AUDITS_ENDPOINTS.DASHBOARD_SUMMARY, signal);
  return response.data;
};

export const getAuditTrends = async (params?: {
  county_id?: number;
  query_type?: string;
},
  signal?: AbortSignal
): Promise<AuditTrendsData> => {
  const qp: Record<string, any> = {};
  if (params?.county_id) qp.county_id = params.county_id;
  if (params?.query_type) qp.query_type = params.query_type;
  const url = buildUrlWithParams(AUDITS_ENDPOINTS.DASHBOARD_TRENDS, qp);
  const response = await apiGet<AuditTrendsData>(apiClient, url, signal);
  return response.data;
};

export const getRecurringFindings = async (signal?: AbortSignal): Promise<RecurringFindingsData> => {
  const response = await apiGet<RecurringFindingsData>(apiClient, AUDITS_ENDPOINTS.DASHBOARD_RECURRING, signal);
  return response.data;
};

export const getAuditFindings = async (filters?: FindingsFilters, signal?: AbortSignal): Promise<FindingsListData> => {
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
  const response = await apiGet<FindingsListData>(apiClient, url, signal);
  return response.data;
};
