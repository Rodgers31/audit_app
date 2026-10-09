/** Frozen worker-dispatch contract. Calendar evidence cannot pass these parsers. */
import { boolean, date, integer, record } from './ingestion';

export const DISPATCH_SOURCES = ['treasury', 'cob', 'oag', 'knbs', 'opendata', 'cra'] as const;
export type DispatchSource = typeof DISPATCH_SOURCES[number];
export const COMMAND_STATUSES = ['queued', 'running', 'completed', 'failed', 'interrupted'] as const;
export type CommandStatus = typeof COMMAND_STATUSES[number];
export interface DispatchCapability {
  timestamp: string; evidence: 'worker_dispatch'; available: boolean; reason: string;
  generation: string | null;
  worker: { status: 'ready' | 'unavailable'; last_seen_at: string | null; expires_at: string | null };
  sources: Record<DispatchSource, { available: boolean; reason: string }>;
}
export interface EtlCommand {
  id: string; source: DispatchSource; dry_run: boolean; status: CommandStatus; version: number;
  created_at: string; updated_at: string; started_at: string | null; finished_at: string | null;
  job_id: number | null; outcome: 'completed' | 'failed' | 'execution_unverified' | null;
}
export interface CommandFilters { page: number; page_size: number; source: DispatchSource | ''; status: CommandStatus | '' }
export interface CommandList { entries: EtlCommand[]; page: number; page_size: number; total: number; has_more: boolean }
export interface CommandAcceptance { ok: true; accepted: true; replayed: boolean; audit_recorded: true; command: EtlCommand }
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const validCommandId = (id: unknown): id is string => typeof id === 'string' && UUID.test(id);
function invalid(): never { throw new Error('Dispatch evidence unavailable. Refresh to verify.'); }
function exact(raw: unknown, keys: string[]) {
  const value = record(raw);
  if (Object.keys(value).length !== keys.length || keys.some(key => !Object.hasOwn(value, key))) invalid();
  return value;
}
function uuid(value: unknown) { if (!validCommandId(value)) invalid(); return value; }
function timestamp(value: unknown) {
  if (typeof value !== 'string' || !/(?:Z|\+00:00)$/.test(value)) invalid();
  return date(value);
}
const optionalTimestamp = (value: unknown) => value === null ? null : timestamp(value);
/** Date.parse truncates API microseconds; preserve chronology within that millisecond. */
function compareTimestamp(left:string, right:string) {
  const remainder=(value:string)=>Number((/\.(\d{1,6})/.exec(value)?.[1] ?? '').padEnd(6,'0')) % 1000;
  return Date.parse(left)-Date.parse(right) || remainder(left)-remainder(right);
}
function reason(value: unknown) {
  if (typeof value !== 'string' || !value.trim() || value.length > 240 ||
      /[\x00-\x1f\x7f]|https?:\/\/|bearer\s|[\w.+-]+@[\w.-]+|(?:token|password|secret)\s*[:=]/i.test(value)) invalid();
  return value;
}
function source(value: unknown): DispatchSource {
  if (!DISPATCH_SOURCES.includes(value as DispatchSource)) invalid();
  return value as DispatchSource;
}
function status(value: unknown): CommandStatus {
  if (!COMMAND_STATUSES.includes(value as CommandStatus)) invalid();
  return value as CommandStatus;
}
export function parseDispatchCapability(raw: unknown, now = Date.now()): DispatchCapability {
  const v = exact(raw, ['timestamp', 'evidence', 'available', 'reason', 'generation', 'worker', 'sources']);
  const seen = timestamp(v.timestamp), available = boolean(v.available);
  const worker = exact(v.worker, ['status', 'last_seen_at', 'expires_at']);
  const last_seen_at = optionalTimestamp(worker.last_seen_at), expires_at = optionalTimestamp(worker.expires_at);
  if (!Number.isFinite(now) || v.evidence !== 'worker_dispatch' ||
      worker.status !== (available ? 'ready' : 'unavailable') ||
      (last_seen_at === null) !== (expires_at === null) ||
      (last_seen_at && expires_at && (compareTimestamp(last_seen_at,seen) > 0 || compareTimestamp(last_seen_at,expires_at) >= 0))) invalid();
  const generation = available ? uuid(v.generation) : null;
  if (!available && v.generation !== null) invalid();
  if (available && (!last_seen_at || !expires_at || compareTimestamp(seen,expires_at) >= 0 ||
      Date.parse(expires_at) <= now || Date.parse(seen) > now + 5000 || now - Date.parse(seen) > 30000)) invalid();
  const rawSources = exact(v.sources, [...DISPATCH_SOURCES]);
  const sources = {} as DispatchCapability['sources'];
  for (const name of DISPATCH_SOURCES) {
    const entry = exact(rawSources[name], ['available', 'reason']);
    const supported = boolean(entry.available);
    if (supported && !available) invalid();
    sources[name] = { available: supported, reason: reason(entry.reason) };
  }
  return {timestamp:seen, evidence:'worker_dispatch', available, reason:reason(v.reason), generation,
    worker:{status:available ? 'ready' : 'unavailable',last_seen_at,expires_at},sources};
}
export function dispatchCurrent(capability: DispatchCapability | undefined, now = Date.now()) {
  return !!capability?.available && Number.isFinite(now) && !!capability.worker.expires_at &&
    Date.parse(capability.timestamp) <= now + 5000 && now - Date.parse(capability.timestamp) <= 30000 &&
    now < Date.parse(capability.worker.expires_at);
}
export function parseCommand(raw: unknown, expectedId?: string): EtlCommand {
  const v = exact(raw, ['id','source','dry_run','status','version','created_at','updated_at','started_at','finished_at','job_id','outcome']);
  const id = uuid(v.id), commandStatus = status(v.status), created_at = timestamp(v.created_at), updated_at = timestamp(v.updated_at);
  const started_at = optionalTimestamp(v.started_at), finished_at = optionalTimestamp(v.finished_at);
  const job_id = v.job_id === null ? null : integer(v.job_id, 1, 2147483647);
  if (expectedId !== undefined && (!validCommandId(expectedId) || id !== expectedId) ||
      compareTimestamp(updated_at,created_at) < 0 || started_at && (compareTimestamp(started_at,created_at) < 0 || compareTimestamp(started_at,updated_at) > 0) ||
      finished_at && (compareTimestamp(finished_at,started_at ?? created_at) < 0 || compareTimestamp(finished_at,updated_at) > 0)) invalid();
  if (commandStatus === 'queued' && (started_at !== null || finished_at !== null || job_id !== null || v.outcome !== null) ||
      commandStatus === 'running' && (!started_at || finished_at !== null || v.outcome !== null) ||
      commandStatus === 'completed' && (!started_at || !finished_at || !job_id || v.outcome !== 'completed') ||
      commandStatus === 'failed' && (!finished_at || v.outcome !== 'failed' || job_id !== null && !started_at) ||
      commandStatus === 'interrupted' && (!started_at || !finished_at || v.outcome !== 'execution_unverified')) invalid();
  return {id,source:source(v.source),dry_run:boolean(v.dry_run),status:commandStatus,version:integer(v.version,1),
    created_at,updated_at,started_at,finished_at,job_id,outcome:v.outcome as EtlCommand['outcome']};
}
/** Receipt refreshes cannot regress or replace the original semantic intent. */
export function commandProgress(next: EtlCommand, previous?: EtlCommand) {
  if (previous && (next.id !== previous.id || next.source !== previous.source || next.dry_run !== previous.dry_run ||
      next.created_at !== previous.created_at || next.version < previous.version ||
      compareTimestamp(next.updated_at,previous.updated_at) < 0 ||
      previous.started_at !== null && next.started_at !== previous.started_at ||
      previous.finished_at !== null && next.finished_at !== previous.finished_at ||
      previous.job_id !== null && next.job_id !== previous.job_id ||
      !activeCommand(previous) && next.status !== previous.status ||
      previous.status === 'running' && next.status === 'queued' ||
      next.version === previous.version && JSON.stringify(next) !== JSON.stringify(previous))) invalid();
  return next;
}
export function parseCommandAcceptance(raw: unknown, intent: {source:DispatchSource;dry_run:boolean}, httpStatus: number): CommandAcceptance {
  const v = exact(raw, ['ok','accepted','replayed','audit_recorded','command']);
  const command = parseCommand(v.command);
  if (httpStatus !== 202 || v.ok !== true || v.accepted !== true || v.audit_recorded !== true ||
      command.source !== intent.source || command.dry_run !== intent.dry_run) invalid();
  return {ok:true,accepted:true,replayed:boolean(v.replayed),audit_recorded:true,command};
}
export function parseCommandList(raw: unknown, expected: CommandFilters): CommandList {
  integer(expected.page,1,10000); integer(expected.page_size,1,50);
  if (expected.source) source(expected.source);
  if (expected.status) status(expected.status);
  const v = exact(raw, ['entries','page','page_size','total','has_more']);
  const page = integer(v.page,1,10000), page_size = integer(v.page_size,1,50), total = integer(v.total);
  if (!Array.isArray(v.entries) || page !== expected.page || page_size !== expected.page_size) invalid();
  const entries = v.entries.map(entry => parseCommand(entry)), has_more = boolean(v.has_more);
  if (entries.length !== Math.min(page_size, Math.max(0,total - (page - 1) * page_size)) ||
      new Set(entries.map(entry=>entry.id)).size !== entries.length || has_more !== (page * page_size < total) ||
      entries.some(entry => expected.source && entry.source !== expected.source || expected.status && entry.status !== expected.status) ||
      entries.some((entry,index) => index > 0 && (compareTimestamp(entry.created_at,entries[index-1].created_at) > 0 ||
        compareTimestamp(entry.created_at,entries[index-1].created_at) === 0 && entry.id >= entries[index-1].id))) invalid();
  return {entries,page,page_size,total,has_more};
}
export function commandFilters(params: URLSearchParams): CommandFilters & {canonical: URLSearchParams} {
  const bounded = (key:string, fallback:number, max:number) => {
    const value = params.get(key);
    return value && /^\d+$/.test(value) && Number(value)>=1 && Number(value)<=max ? Number(value) : fallback;
  };
  const page=bounded('page',1,10000), page_size=bounded('page_size',20,50);
  const rawSource=params.get('source'),rawStatus=params.get('status');
  const selectedSource=DISPATCH_SOURCES.includes(rawSource as DispatchSource) ? rawSource as DispatchSource : '';
  const selectedStatus=COMMAND_STATUSES.includes(rawStatus as CommandStatus) ? rawStatus as CommandStatus : '';
  const canonical=new URLSearchParams();
  if (selectedSource) canonical.set('source',selectedSource);
  if (selectedStatus) canonical.set('status',selectedStatus);
  if (page_size!==20) canonical.set('page_size',String(page_size));
  if (page!==1) canonical.set('page',String(page));
  return {page,page_size,source:selectedSource,status:selectedStatus,canonical};
}
export const activeCommand = (command: EtlCommand) => command.status === 'queued' || command.status === 'running';
export const COMMAND_LABELS: Record<CommandStatus,string> = {
  queued:'Queued — accepted, awaiting execution.', running:'Running — execution in progress.',
  completed:'Completed — recorded ingestion observation.', failed:'Failed — execution did not complete.',
  interrupted:'Interrupted — execution unverified. Do not automatically repeat.',
};
export function dispatchHttpStatus(error: unknown) {
  if (!error || typeof error !== 'object' || !('response' in error)) return undefined;
  const response = error.response;
  return response && typeof response === 'object' && 'status' in response && typeof response.status === 'number' ? response.status : undefined;
}
