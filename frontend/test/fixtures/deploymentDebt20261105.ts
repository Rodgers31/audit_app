/** Inert reader contracts. These fixtures do not establish source authority. */
export function syntheticDebtTimeline20261105(ratio: number) {
  const year = 2025, gdp = 20_000_000_000_000;
  const total = gdp * ratio / 100;
  const identity = (measure: string, basis: string, unit = 'KES') => ({
    measure, entity_id: null, geography: 'KEN', period: String(year), unit, basis,
  });
  const proof = { status: 'verified', reason: 'retained_source_and_observation_matched',
    value_checked: true, document_bytes_checked: true, source_document_id: 1,
    receipt_id: 1, digest: 'a'.repeat(64) };
  return {
    year, unit: 'KES', external: total * .4, domestic: total * .6, total, gdp, gdp_ratio: ratio,
    qualifications: {
      total: { ...proof, identity: identity('total', 'actual'), source_kind: 'pdf',
        source_url: 'https://www.centralbank.go.ke/synthetic-fixture.pdf',
        locator: { page: 56, table: '4.1.3', cell: '2025-12 / total' } },
      gdp: { ...proof, identity: identity('gdp', 'current_prices'), source_kind: 'api',
        source_url: 'https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN',
        locator: { json_path: '$[1][0].value', indicator: 'NY.GDP.MKTP.CN', country: 'KEN', date: '2025' } },
      gdp_ratio: { status: 'verified', reason: 'independently_matched_ratio_operands',
        value_checked: true, document_bytes_checked: true, source_document_id: 1,
        identity: identity('gdp_ratio', 'derived', 'percent') },
    },
    period: { stock_as_of_month: '2025-12', gdp_calendar_year: year, year_end_stock: true,
      vintage_date: null, publication_date: null },
  };
}
