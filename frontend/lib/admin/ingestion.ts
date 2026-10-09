/** Runtime contracts for operational observations, including untrusted URLs. */
export const INGESTION_STATUSES = ['pending', 'running', 'completed', 'completed_with_errors', 'failed'] as const;
export interface IngestionJob {
  id: number; domain: string; status: string; dry_run: boolean;
  started_at: string; finished_at: string | null; duration_seconds: number | null;
  items_processed: number; items_created: number; items_updated: number;
  errors: string[]; error_count: number; metadata: Record<string, unknown>;
  diagnostics_redacted: boolean; created_at: string;
}
export interface IngestionJobList { jobs: IngestionJob[]; total: number; page: number; page_size: number; has_more: boolean }
export function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Unsupported operations response');
  return value as Record<string, unknown>;
}
export function integer(value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < min || value > max) throw new Error('Invalid operations number');
  return value;
}
export function text(value: unknown): string {
  if (typeof value !== 'string') throw new Error('Invalid operations text');
  return value;
}
export function date(value: unknown): string {
  const raw = text(value);
  const components = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(?:Z|[+-](\d{2}):(\d{2}))?$/.exec(raw);
  if (!components) throw new Error('Invalid operations date');
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, offsetHour, offsetMinute] = components;
  const year = Number(yearText), month = Number(monthText), day = Number(dayText);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  // Date.parse normalizes nonexistent dates and 24:00; reject those components
  // before accepting an instant. Match the API's second precision and offsets.
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > days[month - 1] ||
      Number(hourText) > 23 || Number(minuteText) > 59 || Number(secondText) > 59 ||
      (offsetHour !== undefined && (Number(offsetHour) > 23 || Number(offsetMinute) > 59)) ||
      !Number.isFinite(Date.parse(raw))) throw new Error('Invalid operations date');
  return raw;
}
export function boolean(value: unknown): boolean {
  if (typeof value !== 'boolean') throw new Error('Invalid operations flag');
  return value;
}
export function parseIngestionJob(raw: unknown): IngestionJob {
  const v = record(raw);
  const status = text(v.status);
  if (!INGESTION_STATUSES.includes(status as typeof INGESTION_STATUSES[number])) throw new Error('Unknown job status');
  const domain = text(v.domain);
  if (!/^[a-zA-Z0-9_-]{1,100}$/.test(domain)) throw new Error('Invalid job domain');
  if (!Array.isArray(v.errors) || v.errors.some(e => typeof e !== 'string')) throw new Error('Invalid diagnostics');
  const duration = v.duration_seconds;
  if (duration !== null && (typeof duration !== 'number' || !Number.isFinite(duration) || duration < 0)) throw new Error('Invalid duration');
  const errorCount = integer(v.error_count);
  if ((errorCount > 0) !== (v.errors.length > 0) || v.diagnostics_redacted !== true) throw new Error('Unsupported diagnostics contract');
  const meta = record(v.metadata);
  // Only display fields from the server's operational allowlist.
  const metadata: Record<string, unknown> = {};
  if (typeof meta.source_mode === 'string' && ['live', 'fixture', 'unknown', 'unavailable', 'stale', 'refused'].includes(meta.source_mode)) metadata.source_mode = meta.source_mode;
  for (const key of ['manual_trigger', 'dropped_by_global_budget', 'dry_run']) if (typeof meta[key] === 'boolean') metadata[key] = meta[key];
  if (typeof meta.since === 'string') metadata.since = date(meta.since);
  return { id: integer(v.id,1,2147483647), domain, status, dry_run:boolean(v.dry_run),
    started_at:date(v.started_at), finished_at:v.finished_at === null ? null : date(v.finished_at),
    duration_seconds:duration as number | null, items_processed:integer(v.items_processed),
    items_created:integer(v.items_created), items_updated:integer(v.items_updated),
    errors:errorCount ? ['Diagnostic withheld; inspect the dedicated runner logs.'] : [],
    error_count:errorCount, diagnostics_redacted:true, metadata, created_at:date(v.created_at) };
}
export function parseIngestionList(raw: unknown, expected: { page:number; page_size:number }): IngestionJobList {
  const v = record(raw);
  const total = integer(v.total), page = integer(v.page,1,10000), page_size = integer(v.page_size,1,100);
  if (!Array.isArray(v.jobs) || page !== expected.page || page_size !== expected.page_size) throw new Error('Mismatched job page');
  const jobs = v.jobs.map(parseIngestionJob);
  const has_more = boolean(v.has_more);
  if (jobs.length !== Math.min(page_size,Math.max(0,total-(page-1)*page_size)) ||
      new Set(jobs.map(j => j.id)).size !== jobs.length || has_more !== (page*page_size<total)) throw new Error('Inconsistent job page');
  return {jobs,total,page,page_size,has_more};
}
export function ingestionFilters(params: URLSearchParams) {
  const bounded = (key: string, fallback: number, max: number) => {
    const raw = params.get(key);
    return raw !== null && /^\d+$/.test(raw) && Number(raw)>=1 && Number(raw)<=max ? Number(raw) : fallback;
  };
  const rawDomain=params.get('domain') ?? '', rawStatus=params.get('status') ?? '';
  const domain=/^[a-zA-Z0-9_-]{0,100}$/.test(rawDomain) ? rawDomain : '';
  const status=INGESTION_STATUSES.includes(rawStatus.toLowerCase() as typeof INGESTION_STATUSES[number]) ? rawStatus.toLowerCase() : '';
  const days=bounded('days',7,365), page=bounded('page',1,10000);
  const canonical=new URLSearchParams();
  if(domain) canonical.set('domain',domain);
  if(status) canonical.set('status',status);
  if(days!==7) canonical.set('days',String(days));
  if(page!==1) canonical.set('page',String(page));
  return {domain,status,days,page,canonical};
}
export function activeJob(job: IngestionJob) { return job.status === 'pending' || job.status === 'running'; }
