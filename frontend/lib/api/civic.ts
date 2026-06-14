/**
 * Civic figures API — live fiscal magnitudes for the Learn glossary.
 *
 * These are the numbers the glossary used to hardcode (GDP, national
 * budget, public debt, county equitable share). They now resolve from the
 * backend's one canonical DB source per metric, each carrying the period it
 * refers to and its provenance, so the glossary self-updates as new data is
 * seeded instead of going stale. See backend `/learn/civic-figures`.
 */
import { apiClient } from './axios';
import { LEARN_ENDPOINTS } from './endpoints';

export type CivicFigureKey =
  | 'nominal_gdp'
  | 'national_budget'
  | 'public_debt'
  | 'equitable_share';

export interface CivicFigure {
  /** True only when a real value AND its period were resolved from the DB. */
  available: boolean;
  /** Raw KES (e.g. 16_224_478_000_000), or null when never seeded. */
  value: number | null;
  unit: string;
  /** The period the figure refers to: a fiscal year ("FY2025/26") or year ("2024"). */
  period: string | null;
  /** Human-readable source/publisher. */
  source: string;
  /** Source-document vintage (ISO date), not the request time. */
  as_of: string | null;
  /** "official" | "estimated" | "projected". */
  data_quality: string;
}

export interface CivicFiguresResponse {
  status: string;
  data_source: string;
  figures: Partial<Record<CivicFigureKey, CivicFigure>>;
}

export const getCivicFigures = async (): Promise<CivicFiguresResponse> => {
  const response = await apiClient.get<CivicFiguresResponse>(
    LEARN_ENDPOINTS.CIVIC_FIGURES
  );
  return response.data;
};
