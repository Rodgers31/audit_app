/**
 * Money Flow API service — Follow the Money endpoints
 */
import { MoneyFlowData } from '@/types';
import { apiClient } from './axios';
import { AUDITS_ENDPOINTS, COUNTIES_ENDPOINTS, buildUrlWithParams } from './endpoints';

// Get money flow for a specific county and fiscal year
export const getCountyMoneyFlow = async (
  countyId: string,
  year: string
): Promise<MoneyFlowData> => {
  const url = buildUrlWithParams(COUNTIES_ENDPOINTS.MONEY_FLOW(countyId), { year });
  const response = await apiClient.get<MoneyFlowData>(url);
  return response.data;
};

// Get national aggregated money flow for a fiscal year
export const getNationalMoneyFlow = async (year: string): Promise<MoneyFlowData> => {
  const url = buildUrlWithParams(AUDITS_ENDPOINTS.MONEY_FLOW_NATIONAL, { year });
  const response = await apiClient.get<MoneyFlowData>(url);
  return response.data;
};

// Get money flow for ALL counties in a single batch call
export const getAllCountiesMoneyFlow = async (year: string): Promise<MoneyFlowData[]> => {
  const url = buildUrlWithParams('/money-flow/all-counties', { year });
  const response = await apiClient.get<MoneyFlowData[]>(url);
  return response.data;
};
