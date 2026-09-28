/**
 * National statistics API service
 */
import { apiClient } from './axios';
import { apiGet } from './request';
import { STATISTICS_ENDPOINTS, buildUrlWithParams } from './endpoints';
import { ApiResponse, NationalStatsResponse } from './types';

// Get dashboard overview statistics
export const getDashboardStats = async (signal?: AbortSignal): Promise<NationalStatsResponse> => {
  const response = await apiGet<ApiResponse<NationalStatsResponse>>(
    apiClient,
    STATISTICS_ENDPOINTS.DASHBOARD,
    signal
  );
  return response.data.data;
};

// Get national overview statistics
export const getNationalOverview = async (signal?: AbortSignal): Promise<any> => {
  const response = await apiGet<ApiResponse<any>>(apiClient, STATISTICS_ENDPOINTS.OVERVIEW, signal);
  return response.data.data;
};

// Get performance rankings
export const getPerformanceRankings = async (signal?: AbortSignal): Promise<any> => {
  const response = await apiGet<ApiResponse<any>>(apiClient, STATISTICS_ENDPOINTS.RANKINGS, signal);
  return response.data.data;
};

// Get sector performance analysis
export const getSectorPerformance = async (sector?: string, signal?: AbortSignal): Promise<any> => {
  const queryParams: Record<string, any> = {};
  if (sector) queryParams.sector = sector;

  const url = buildUrlWithParams(STATISTICS_ENDPOINTS.SECTOR_PERFORMANCE, queryParams);
  const response = await apiGet<ApiResponse<any>>(apiClient, url, signal);
  return response.data.data;
};

// Get regional analysis
export const getRegionalAnalysis = async (signal?: AbortSignal): Promise<any> => {
  const response = await apiGet<ApiResponse<any>>(apiClient, STATISTICS_ENDPOINTS.REGIONAL_ANALYSIS, signal);
  return response.data.data;
};

// Get trends over time
export const getNationalTrends = async (years?: number, signal?: AbortSignal): Promise<any> => {
  const queryParams: Record<string, any> = {};
  if (years) queryParams.years = years;

  const url = buildUrlWithParams(STATISTICS_ENDPOINTS.TRENDS, queryParams);
  const response = await apiGet<ApiResponse<any>>(apiClient, url, signal);
  return response.data.data;
};

// Get audit compliance statistics
export const getAuditComplianceStats = async (signal?: AbortSignal): Promise<any> => {
  const response = await apiGet<ApiResponse<any>>(apiClient, STATISTICS_ENDPOINTS.AUDIT_COMPLIANCE, signal);
  return response.data.data;
};

// Get financial health indicators
export const getFinancialHealthIndicators = async (signal?: AbortSignal): Promise<any> => {
  const response = await apiGet<ApiResponse<any>>(apiClient, STATISTICS_ENDPOINTS.FINANCIAL_HEALTH, signal);
  return response.data.data;
};

// Get transparency index
export const getTransparencyIndex = async (signal?: AbortSignal): Promise<any> => {
  const response = await apiGet<ApiResponse<any>>(apiClient, STATISTICS_ENDPOINTS.TRANSPARENCY_INDEX, signal);
  return response.data.data;
};

// Get alerts and notifications
export const getAlertsAndNotifications = async (signal?: AbortSignal): Promise<any> => {
  const response = await apiGet<ApiResponse<any>>(apiClient, STATISTICS_ENDPOINTS.ALERTS, signal);
  return response.data.data;
};
