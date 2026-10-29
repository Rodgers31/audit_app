/** Labels describe the registered source contract, never its current eligibility. */
export const sourceLabels: Record<string, string> = {
  counties_budget: 'County budgets', national_budget: 'National budget',
  pending_bills: 'County pending bills', revenue_by_source: 'KRA revenue collections',
  audits: 'Audit reports', economic_indicators: 'Economic indicators', population: 'Population',
  county_officials: 'County officials', national_debt: 'National debt', debt_timeline: 'Debt history',
  fiscal_summary: 'Fiscal summary', learning_hub: 'Learning hub', stalled_projects: 'Stalled projects',
  national_gdp: 'National GDP', imf_weo: 'IMF economic outlook', county_borrowing: 'County borrowing',
  cra: 'Revenue allocation', opendata: 'OpenData', treasury: 'National Treasury',
  cob: 'Controller of Budget', oag: 'Auditor-General', knbs: 'Kenya National Bureau of Statistics', kra: 'Kenya Revenue Authority',
};
export function sourceLabel(domain: string) { return Object.hasOwn(sourceLabels, domain) ? sourceLabels[domain] : domain.replaceAll('_', ' '); }
