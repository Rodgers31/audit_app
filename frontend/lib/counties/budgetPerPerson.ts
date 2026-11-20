import { apiClient } from '@/lib/api/axios';
import { apiGet } from '@/lib/api/request';
import { evidenceUrl } from '@/lib/evidence/qualification';
import type { BudgetSource } from '@/types';
import { getCountyRegion, normalizeCountyName } from './regions';

export const COUNTY_CENSUS_YEAR = 2019;

const CENSUS_LIMIT = 100;
const KNBS_HOSTS = ['knbs.or.ke', 'www.knbs.or.ke', 'repository.knbs.or.ke'];
const COB_HOSTS = ['cob.go.ke', 'www.cob.go.ke'];
const COUNTY_CENSUS_TITLE =
  /^2019 Kenya Population and Housing Census(?: \(KPHC\))? Volume (?:I|1)\s*[:-]?\s*Population by County and Sub-County$/i;
const COB_BUDGET_TITLE = /\bcounty\b.*\b(?:CBIRR|BIRR|budget implementation review)\b/i;

type PublicSource = {
  id: number;
  title: string;
  publisher: string;
  url: string;
};

type CensusCount = {
  countyKey: string;
  population: number;
};

export type CountyCensus = {
  year: typeof COUNTY_CENSUS_YEAR;
  source: PublicSource;
  counts: ReadonlyMap<number, CensusCount>;
};

function record(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function positiveInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}

function publicSource(value: unknown, approvedHosts: readonly string[]): PublicSource | undefined {
  const source = record(value);
  if (
    !source ||
    !positiveInteger(source.id) ||
    typeof source.title !== 'string' ||
    typeof source.publisher !== 'string' ||
    typeof source.url !== 'string'
  ) return undefined;

  const url = evidenceUrl(source.url);
  if (!url) return undefined;
  const parsed = new URL(url);
  if (parsed.protocol !== 'https:' || parsed.port || !approvedHosts.includes(parsed.hostname)) return undefined;
  return { id: source.id, title: source.title.trim(), publisher: source.publisher.trim(), url };
}

function countyIdentityKey(name: string): string {
  const key = normalizeCountyName(name);
  return key === 'nairobicity' ? 'nairobi' : key;
}

function censusCandidates(payload: unknown) {
  if (!Array.isArray(payload) || payload.length > CENSUS_LIMIT) return [];
  const countyRows = payload.flatMap(value => {
    const row = record(value);
    if (
      !row ||
      row.year !== COUNTY_CENSUS_YEAR ||
      row.entity_type !== 'county' ||
      !positiveInteger(row.entity_id) ||
      typeof row.entity_name !== 'string' ||
      !getCountyRegion(row.entity_name)
    ) return [];

    return [{
      entityId: row.entity_id,
      countyKey: countyIdentityKey(row.entity_name),
      sourceId: row.source_document_id,
      population: row.total_population,
    }];
  });

  return countyRows.flatMap(row => {
    if (
      !positiveInteger(row.population) ||
      !positiveInteger(row.sourceId) ||
      countyRows.some(other => other !== row &&
        (other.entityId === row.entityId || other.countyKey === row.countyKey))
    ) return [];
    return [{ ...row, population: row.population, sourceId: row.sourceId }];
  });
}

/** One bounded census query and one source lookup, with the existing API retry budget. */
export async function loadCountyCensus(signal?: AbortSignal): Promise<CountyCensus | undefined> {
  signal?.throwIfAborted();
  const population = await apiGet<unknown>(
    apiClient, `/economic/population?year=${COUNTY_CENSUS_YEAR}&limit=${CENSUS_LIMIT}`, signal
  );
  signal?.throwIfAborted();

  const rows = censusCandidates(population.data);
  const sourceId = rows[0]?.sourceId;
  if (sourceId == null || rows.some(row => row.sourceId !== sourceId)) return undefined;

  const document = await apiGet<unknown>(apiClient, `/source-documents/${sourceId}`, signal);
  signal?.throwIfAborted();
  const source = publicSource(document.data, KNBS_HOSTS);
  if (
    !source ||
    source.id !== sourceId ||
    source.publisher.toLowerCase() !== 'kenya national bureau of statistics' ||
    !COUNTY_CENSUS_TITLE.test(source.title) ||
    record(record(document.data)?.meta)?.dataset_id !== 'knbs_census_2019'
  ) return undefined;

  return {
    year: COUNTY_CENSUS_YEAR,
    source,
    counts: new Map(rows.map(({ entityId, countyKey, population }) => [entityId, { countyKey, population }])),
  };
}

function periodKey(value: unknown): string {
  return typeof value === 'string' ? value.trim().replace(/^FY\s*/i, '').toUpperCase() : '';
}

function isCob(publisher: unknown): boolean {
  return typeof publisher === 'string' &&
    /^(?:office of the )?controller of budget$/i.test(publisher.trim());
}

type BudgetPerPersonInput = {
  countyName: string;
  fiscalYear?: string;
  budgetSource?: BudgetSource;
  financialSummary: unknown;
  budgetLines: unknown;
  census?: CountyCensus;
};

/** The selected period's published allocation divided by the stated census count. */
export function publishedBudgetPerPerson({
  countyName, fiscalYear, budgetSource, financialSummary, budgetLines, census,
}: BudgetPerPersonInput) {
  const period = periodKey(fiscalYear);
  const countyKey = countyIdentityKey(countyName);
  const summary = record(financialSummary);
  const lines = record(budgetLines);
  const fiscalPeriod = record(summary?.fiscal_period)?.label;
  const allocation = summary?.total_allocation;
  const sources = summary?.sources;
  if (
    !census || !countyKey || !period || !lines ||
    (budgetSource != null && budgetSource !== 'cob_cbirr') ||
    typeof fiscalPeriod !== 'string' || periodKey(fiscalPeriod) !== period ||
    summary?.currency !== 'KES' || summary.accounting_basis !== 'reported_total' ||
    typeof allocation !== 'number' || !Number.isFinite(allocation) || allocation < 0 ||
    !Array.isArray(sources) || sources.length !== 1
  ) return undefined;

  const budget = publicSource(sources[0], COB_HOSTS);
  if (!budget || !isCob(budget.publisher) || !COB_BUDGET_TITLE.test(budget.title)) return undefined;

  const totals = Object.values(lines).flatMap(value => {
    const receipt = record(record(value)?.allocated_amount);
    const identity = record(receipt?.identity);
    const dimensions = record(identity?.dimensions);
    if (
      !receipt || !identity ||
      identity.measure !== 'allocated_amount' ||
      typeof identity.geography !== 'string' ||
      countyIdentityKey(identity.geography) !== countyKey ||
      periodKey(identity.period) !== period ||
      typeof dimensions?.category !== 'string' ||
      dimensions.category.trim().toLowerCase() !== 'total' ||
      (dimensions.subcategory != null && dimensions.subcategory !== '')
    ) return [];
    return [{ receipt, identity }];
  });
  if (totals.length !== 1) return undefined;

  const [{ receipt, identity }] = totals;
  const supported = (
    receipt.status === 'verified' &&
    receipt.document_bytes_checked === true &&
    receipt.value_checked === true
  ) || (receipt.status === 'qualified' && receipt.reason === 'historical_source_not_value_checked');
  if (
    !supported || identity.unit !== 'KES' || identity.basis !== 'actual' ||
    !positiveInteger(identity.entity_id) ||
    receipt.source_document_id !== budget.id || !isCob(receipt.publisher) ||
    typeof receipt.source_url !== 'string' || evidenceUrl(receipt.source_url) !== budget.url
  ) return undefined;

  const count = census.counts.get(identity.entity_id);
  if (count?.countyKey !== countyKey || !positiveInteger(count.population)) return undefined;

  return {
    value: allocation / count.population,
    allocation,
    fiscalPeriod,
    budget,
    population: count.population,
    censusYear: census.year,
    censusSource: census.source,
  };
}
