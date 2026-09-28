/**
 * Custom React Query hooks for national statistics
 */
import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import {
  getAlertsAndNotifications,
  getAuditComplianceStats,
  getDashboardStats,
  getFinancialHealthIndicators,
  getNationalOverview,
  getNationalTrends,
  getPerformanceRankings,
  getRegionalAnalysis,
  getSectorPerformance,
  getTransparencyIndex,
} from '../api/statistics';
import { NationalStatsResponse } from '../api/types';

// Query keys for statistics
const QUERY_KEYS = {
  stats: ['stats'] as const,
  dashboard: ['stats', 'dashboard'] as const,
  overview: ['stats', 'overview'] as const,
  rankings: ['stats', 'rankings'] as const,
  sectorPerformance: (sector?: string) => ['stats', 'sector-performance', sector] as const,
  regionalAnalysis: ['stats', 'regional-analysis'] as const,
  trends: (years?: number) => ['stats', 'trends', years] as const,
  auditCompliance: ['stats', 'audit-compliance'] as const,
  financialHealth: ['stats', 'financial-health'] as const,
  transparencyIndex: ['stats', 'transparency-index'] as const,
  alerts: ['stats', 'alerts'] as const,
};

// Get dashboard overview statistics
export const useDashboardStats = (
  options?: Omit<UseQueryOptions<NationalStatsResponse>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.dashboard,
    queryFn: ({ signal }) => getDashboardStats(signal),
    staleTime: 5 * 60 * 1000, // 5 minutes
    ...options,
  });
};

// Get national overview statistics
export const useNationalOverview = (
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.overview,
    queryFn: ({ signal }) => getNationalOverview(signal),
    staleTime: 10 * 60 * 1000, // 10 minutes
    ...options,
  });
};

// Get performance rankings
export const usePerformanceRankings = (
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.rankings,
    queryFn: ({ signal }) => getPerformanceRankings(signal),
    staleTime: 15 * 60 * 1000, // 15 minutes
    ...options,
  });
};

// Get sector performance analysis
export const useSectorPerformance = (
  sector?: string,
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.sectorPerformance(sector),
    queryFn: ({ signal }) => getSectorPerformance(sector, signal),
    staleTime: 15 * 60 * 1000, // 15 minutes
    ...options,
  });
};

// Get regional analysis
export const useRegionalAnalysis = (
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.regionalAnalysis,
    queryFn: ({ signal }) => getRegionalAnalysis(signal),
    staleTime: 20 * 60 * 1000, // 20 minutes
    ...options,
  });
};

// Get trends over time
export const useNationalTrends = (
  years?: number,
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.trends(years),
    queryFn: ({ signal }) => getNationalTrends(years, signal),
    staleTime: 15 * 60 * 1000, // 15 minutes
    ...options,
  });
};

// Get audit compliance statistics
export const useAuditComplianceStats = (
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.auditCompliance,
    queryFn: ({ signal }) => getAuditComplianceStats(signal),
    staleTime: 10 * 60 * 1000, // 10 minutes
    ...options,
  });
};

// Get financial health indicators
export const useFinancialHealthIndicators = (
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.financialHealth,
    queryFn: ({ signal }) => getFinancialHealthIndicators(signal),
    staleTime: 15 * 60 * 1000, // 15 minutes
    ...options,
  });
};

// Get transparency index
export const useTransparencyIndex = (
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.transparencyIndex,
    queryFn: ({ signal }) => getTransparencyIndex(signal),
    staleTime: 30 * 60 * 1000, // 30 minutes
    ...options,
  });
};

// Get alerts and notifications
export const useAlertsAndNotifications = (
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) => {
  return useQuery({
    queryKey: QUERY_KEYS.alerts,
    queryFn: ({ signal }) => getAlertsAndNotifications(signal),
    staleTime: 2 * 60 * 1000, // 2 minutes for alerts
    ...options,
  });
};
