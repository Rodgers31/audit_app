/**
 * Centralized API endpoints configuration
 * All API endpoints in one place for easy management and debugging
 */

// Base API configuration
export const API_CONFIG = {
  BASE_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  VERSION: process.env.NEXT_PUBLIC_API_VERSION || 'v1',
  TIMEOUT: 10000,
} as const;

// Get full API base URL
export const getApiBaseUrl = () => `${API_CONFIG.BASE_URL}/api/${API_CONFIG.VERSION}`;

/**
 * Counties Endpoints
 */
export const COUNTIES_ENDPOINTS = {
  // Basic CRUD operations
  LIST: '/counties',
  GET_BY_ID: (id: string) => `/counties/${id}`,
  GET_BY_CODE: (code: string) => `/counties/code/${code}`,

  // Pagination and search
  PAGINATED: '/counties/paginated',
  SEARCH: '/counties/search',

  // Specialized queries
  TOP_PERFORMING: '/counties/top-performing',
  FLAGGED: '/counties/flagged',

  // County-specific data
  COMPREHENSIVE: (id: string) => `/counties/${id}/comprehensive`,
  FINANCIAL_SUMMARY: (id: string) => `/counties/${id}/financial-summary`,
  AUDITS: (id: string) => `/counties/${id}/audits`,
  AUDITS_LIST: (id: string) => `/counties/${id}/audits/list`,
  LATEST_AUDIT: (id: string) => `/counties/${id}/audits/latest`,
  BUDGET: (id: string) => `/counties/${id}/budget`,
  BUDGET_TRENDS: (id: string) => `/counties/${id}/budget/trends`,
  DEBT: (id: string) => `/counties/${id}/debt`,
  DEBT_TIMELINE: (id: string) => `/counties/${id}/debt/timeline`,
  DEBT_SUSTAINABILITY: (id: string) => `/counties/${id}/debt/sustainability`,
  ACCOUNTABILITY: (id: string) => `/counties/${id}/accountability`,
  MONEY_FLOW: (id: string) => `/counties/${id}/money-flow`,
} as const;

/**
 * Audits Endpoints
 */
export const AUDITS_ENDPOINTS = {
  // Basic operations
  LIST: '/audits',
  GET_BY_ID: (id: string) => `/audits/${id}`,
  PAGINATED: '/audits/paginated',

  // Statistics and metadata
  STATISTICS: '/audits/statistics',
  FISCAL_YEARS: '/audits/fiscal-years',

  // Federal / national government audits
  FEDERAL: '/audits/federal',

  // National audit dashboard
  DASHBOARD_SUMMARY: '/audit/summary',
  DASHBOARD_TRENDS: '/audit/trends',
  DASHBOARD_RECURRING: '/audit/recurring',
  DASHBOARD_FINDINGS: '/audit/findings',
  MONEY_FLOW_NATIONAL: '/audit/money-flow/national',
} as const;

/**
 * Budget Endpoints
 */
export const BUDGET_ENDPOINTS = {
  // Comparison and analysis
  COMPARISON: '/budget/comparison',
  NATIONAL: '/budget/national',
  UTILIZATION: '/budget/utilization',
  OVERVIEW: '/budget/overview',
  ENHANCED: '/budget/enhanced',

  // Sector analysis
  SECTORS: (sector: string) => `/budget/sectors/${sector}`,
} as const;

/**
 * Debt Endpoints
 */
export const DEBT_ENDPOINTS = {
  // National overview
  NATIONAL: '/debt/national',
  LOANS: '/debt/loans',
  BREAKDOWN: '/debt/breakdown',
  BREAKDOWN_BY_COUNTY: (countyId: string) => `/debt/breakdown/${countyId}`,
  TIMELINE: '/debt/timeline',
  PENDING_BILLS: '/pending-bills',
  PENDING_BILLS_SUMMARY: '/pending-bills/summary',
  PENDING_BILLS_COUNTY: (countyId: string) => `/pending-bills/counties/${countyId}`,

  // Analysis and comparison
  COMPARISON: '/debt/comparison',
  TOP_LOANS: '/debt/top-loans',
  SUSTAINABILITY: '/debt/sustainability',
  DEBT_SUSTAINABILITY: '/debt/sustainability',
  RISK_ASSESSMENT: '/debt/risk-assessment',
} as const;

/**
 * Fiscal Endpoints
 */
export const FISCAL_ENDPOINTS = {
  SUMMARY: '/fiscal/summary',
} as const;

/**
 * Statistics Endpoints
 */
export const STATISTICS_ENDPOINTS = {
  // Dashboard and overview
  DASHBOARD: '/stats/dashboard',
  OVERVIEW: '/stats/overview',

  // Performance analysis
  RANKINGS: '/stats/rankings',
  SECTOR_PERFORMANCE: '/stats/sector-performance',
  REGIONAL_ANALYSIS: '/stats/regional-analysis',

  // Trends and compliance
  TRENDS: '/stats/trends',
  AUDIT_COMPLIANCE: '/stats/audit-compliance',
  FINANCIAL_HEALTH: '/stats/financial-health',

  // Transparency and alerts
  TRANSPARENCY_INDEX: '/stats/transparency-index',
  ALERTS: '/stats/alerts',
} as const;

/**
 * Helper function to build URL with query parameters
 */
export const buildUrlWithParams = (endpoint: string, params?: Record<string, any>): string => {
  if (!params || Object.keys(params).length === 0) {
    return endpoint;
  }

  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      if (Array.isArray(value)) {
        value.forEach((item) => searchParams.append(key, item.toString()));
      } else {
        searchParams.append(key, value.toString());
      }
    }
  });

  const queryString = searchParams.toString();
  return queryString ? `${endpoint}?${queryString}` : endpoint;
};

/**
 * All endpoints grouped for easy reference
 */
export const API_ENDPOINTS = {
  COUNTIES: COUNTIES_ENDPOINTS,
  AUDITS: AUDITS_ENDPOINTS,
  BUDGET: BUDGET_ENDPOINTS,
  DEBT: DEBT_ENDPOINTS,
  STATISTICS: STATISTICS_ENDPOINTS,
} as const;

/**
 * Debug helper to list all endpoints
 */
export const getAllEndpoints = () => {
  const endpoints: string[] = [];

  Object.values(API_ENDPOINTS).forEach((category) => {
    Object.values(category).forEach((endpoint) => {
      if (typeof endpoint === 'string') {
        endpoints.push(endpoint);
      } else {
        endpoints.push(`${endpoint.name} (function)`);
      }
    });
  });

  return endpoints.sort();
};

/**
 * Development helper to log all endpoints
 */
export const logAllEndpoints = () => {
  if (process.env.NODE_ENV === 'development') {
    console.group('🔗 API Endpoints Configuration');
    console.log('Base URL:', getApiBaseUrl());
    console.log('Counties:', Object.values(COUNTIES_ENDPOINTS));
    console.log('Audits:', Object.values(AUDITS_ENDPOINTS));
    console.log('Budget:', Object.values(BUDGET_ENDPOINTS));
    console.log('Debt:', Object.values(DEBT_ENDPOINTS));
    console.log('Statistics:', Object.values(STATISTICS_ENDPOINTS));
    console.groupEnd();
  }
};
