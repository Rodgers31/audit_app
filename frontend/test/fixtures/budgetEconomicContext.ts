import type { FigureQualification } from '@/lib/evidence/qualification';

const nationalReceipt = {
  status: 'verified',
  reason: 'retained_source_and_observation_matched',
  source_kind: 'api',
  publisher: 'World Bank',
  source_document_id: 1,
  receipt_id: 2,
  digest: 'a'.repeat(64),
  locator: null,
  document_bytes_checked: true,
  value_checked: true,
} as const;

export const nominalGdpReceipt: FigureQualification = {
  ...nationalReceipt,
  identity: { measure: 'total_national_gdp', entity_id: null, geography: 'KEN', period: '2025', unit: 'KES_millions', basis: 'actual', dimensions: {} },
  source_url: 'https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN',
};

export const realGrowthReceipt: FigureQualification = {
  ...nationalReceipt,
  identity: { ...nominalGdpReceipt.identity, measure: 'gdp_growth_rate', period: '2024', unit: 'percent' },
  source_url: 'https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.KD.ZG',
};

export function headlineInflationReceipt(period: string): FigureQualification {
  return {
    ...nationalReceipt,
    identity: { measure: 'inflation_rate_12m', entity_id: null, geography: 'KEN', period, unit: 'percent', basis: 'actual', dimensions: {} },
    source_kind: 'web',
    publisher: 'Central Bank of Kenya',
    source_url: 'https://www.centralbank.go.ke/inflation-rates/',
  };
}

export const syntheticEconomicContext = {
  gdp_billion_kes: 12_345.678,
  gdp_as_of: '2025-12-31T00:00:00',
  gdp_growth_pct: -0.4,
  gdp_growth_as_of: '2024-12-31T00:00:00',
  budget_to_gdp_pct: 32.1,
  revenue_to_gdp_pct: 15.2,
  inflation_pct: 7.51,
  inflation_as_of: '2026-10-31T00:00:00',
  inflation_measure: '12-month CPI inflation',
  qualifications: {
    gdp: { total_national_gdp: nominalGdpReceipt },
    gdp_growth: { gdp_growth_rate: realGrowthReceipt },
    inflation: { inflation_rate_12m: headlineInflationReceipt('2026-10') },
  },
};
