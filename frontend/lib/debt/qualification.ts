/** Public debt ratios require the API's independently checked operand pair. */
type ObjectValue = Record<string, unknown>;
const object = (v: unknown): ObjectValue | null =>
  v !== null && typeof v === 'object' && !Array.isArray(v) ? v as ObjectValue : null;
const amount = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0;
const positiveId = (v: unknown): boolean => typeof v === 'number' && Number.isInteger(v) && v > 0;
const checked = (q: ObjectValue | null): q is ObjectValue => !!q && q.status === 'verified' &&
  q.value_checked === true && q.document_bytes_checked === true;
function officialUrl(value: unknown, hosts: string[]): boolean {
  if (typeof value !== 'string') return false;
  try {
    const u = new URL(value);
    return u.protocol === 'https:' && hosts.includes(u.hostname) && !u.username && !u.password &&
      (!u.port || u.port === '443') && !u.hash;
  } catch { return false; }
}
function operand(q: ObjectValue | null, measure: string, year: number, basis: string): boolean {
  if (!checked(q) || !positiveId(q.source_document_id) || !positiveId(q.receipt_id) ||
      typeof q.digest !== 'string' || !/^[a-f0-9]{64}$/.test(q.digest)) return false;
  const id = object(q.identity);
  return !!id && id.measure === measure && id.geography === 'KEN' && id.entity_id === null &&
    id.period === String(year) && id.unit === 'KES' && id.basis === basis;
}

export function publishedTimelineRatio(value: unknown): number | null {
  const row = object(value);
  if (!row || !Number.isInteger(row.year) || typeof row.year !== 'number' ||
      row.year < 1900 || row.year >= new Date().getUTCFullYear() || row.unit !== 'KES' ||
      !amount(row.total) || !amount(row.gdp) || row.gdp <= 0 || !amount(row.gdp_ratio)) return null;
  const qs = object(row.qualifications), period = object(row.period);
  const stock = object(qs?.total), gdp = object(qs?.gdp), ratio = object(qs?.gdp_ratio);
  if (!operand(stock, 'total', row.year, 'actual') || !operand(gdp, 'gdp', row.year, 'current_prices') ||
      !checked(ratio) || !officialUrl(stock?.source_url, ['centralbank.go.ke', 'www.centralbank.go.ke']) ||
      !officialUrl(gdp?.source_url, ['api.worldbank.org']) || gdp?.source_kind !== 'api') return null;
  const stockLocator = object(stock?.locator), gdpLocator = object(gdp?.locator);
  const month = typeof stockLocator?.cell === 'string'
    ? stockLocator.cell.match(/^(\d{4}-(?:0[1-9]|1[0-2])) \/ total$/)?.[1] : null;
  const ratioIdentity = object(ratio.identity);
  const stockLocationOk = !!stockLocator && typeof stockLocator.table === 'string' && !!stockLocator.table.trim() &&
    (stock?.source_kind === 'pdf' && positiveId(stockLocator.page) ||
      stock?.source_kind === 'web' && !Object.prototype.hasOwnProperty.call(stockLocator, 'page') && typeof stockLocator.edition === 'string' && !!stockLocator.edition.trim());
  if (!month || !month.startsWith(`${row.year}-`) || !period || period.stock_as_of_month !== month ||
      period.gdp_calendar_year !== row.year || !ratioIdentity || ratioIdentity.measure !== 'gdp_ratio' ||
      ratioIdentity.geography !== 'KEN' || ratioIdentity.entity_id !== null ||
      ratioIdentity.period !== String(row.year) || ratioIdentity.unit !== 'percent' || ratioIdentity.basis !== 'derived' ||
      Object.prototype.hasOwnProperty.call(gdpLocator ?? {}, 'page') || typeof gdpLocator?.json_path !== 'string' || !gdpLocator.json_path.trim() ||
      gdpLocator.indicator !== 'NY.GDP.MKTP.CN' || gdpLocator.country !== 'KEN' || gdpLocator.date !== String(row.year) ||
      !stockLocationOk) return null;
  const computed = row.total / row.gdp * 100;
  // The server verifies exact Decimal half-up rounding. Floating-point
  // arithmetic here checks the declared one-decimal interval, including ties.
  const oneDecimal = Math.round(row.gdp_ratio * 10) / 10;
  return Number.isFinite(computed) && Math.abs(oneDecimal - row.gdp_ratio) < 0.000001 &&
    Math.abs(computed - row.gdp_ratio) <= 0.050000001 ? row.gdp_ratio : null;
}

/** Name the monthly stock and annual denominator without inventing a vintage. */
export function debtRatioDisclosure(value: unknown): string | null {
  const row = object(value), period = object(row?.period);
  if (publishedTimelineRatio(row) == null || !period) return null;
  return `CBK stock at ${period.stock_as_of_month}; World Bank annual GDP ${period.gdp_calendar_year}; source vintage unconfirmed`;
}

export function publishedHeadlineRatio(value: unknown): number | null {
  const data = object(value);
  if (!data || !amount(data.debt_to_gdp_ratio) || typeof data.debt_to_gdp_year !== 'number' ||
      !Number.isInteger(data.debt_to_gdp_year) || data.debt_to_gdp_year < 1900 ||
      data.debt_to_gdp_year > new Date().getUTCFullYear()) return null;
  const qualification = object(object(data.figure_qualifications)?.derived_ratio);
  if (qualification?.status === 'qualified' &&
      qualification.reason === 'published_imf_ratio_outside_seven_table_contract' &&
      data.debt_to_gdp_source === 'IMF World Economic Outlook' &&
      typeof data.debt_to_gdp_basis === 'string' && data.debt_to_gdp_basis.includes('GGXWDG_NGDP')) {
    return data.debt_to_gdp_ratio;
  }
  const observed = object(data.debt_to_gdp_observation);
  const ratio = publishedTimelineRatio(observed);
  const observedQualification = object(object(observed?.qualifications)?.gdp_ratio);
  const declaredIdentity = object(qualification?.identity), observedIdentity = object(observedQualification?.identity);
  const period = object(observed?.period);
  const expectedBasis = `Central government debt (CBK) / nominal GDP (World Bank, ${observed?.year}); stock as of ${period?.stock_as_of_month}`;
  // A checked attached pair cannot override conflicting headline metadata.
  const sameDerivedIdentity = !!declaredIdentity && !!observedIdentity &&
    ['measure', 'entity_id', 'geography', 'period', 'unit', 'basis'].every(k => declaredIdentity[k] === observedIdentity[k]);
  return ratio !== null && ratio === data.debt_to_gdp_ratio && observed?.year === data.debt_to_gdp_year &&
    data.debt_to_gdp_source === 'CBK / World Bank' && data.debt_to_gdp_basis === expectedBasis &&
    checked(qualification) && qualification.reason === observedQualification?.reason &&
    qualification.source_document_id === observedQualification?.source_document_id && sameDerivedIdentity
      ? ratio : null;
}

export function headlineRatioDisclosure(value: unknown): string | null {
  const data = object(value);
  if (!data || publishedHeadlineRatio(data) == null) return null;
  if (data.debt_to_gdp_source !== 'IMF World Economic Outlook') return debtRatioDisclosure(data.debt_to_gdp_observation);
  const vintage = typeof data.debt_to_gdp_vintage === 'string' && data.debt_to_gdp_vintage.trim()
    ? data.debt_to_gdp_vintage : 'unconfirmed';
  return `IMF general-government debt / GDP, ${data.debt_to_gdp_year}; source vintage ${vintage}`;
}
