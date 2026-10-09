import {boolean,date,integer,record,text} from './ingestion';
export const ETL_SOURCES=['treasury','cob','oag','knbs','opendata','cra'];
export interface ScheduleSourceDecision { should_run:boolean; reason:string; next_run:string|null; next_reason:string; current_period:string }
export interface ManualTrigger { available:boolean; reason:string }
export interface ScheduleResponse {
  timestamp:string; evidence:'calendar_plan'; manual_trigger:ManualTrigger;
  summary:{sources_running_today:number; sources_skipping_today:number; total_sources:number; skip_percentage:number;
    efficiency_vs_fixed_schedule:string; sources_to_run:Array<{source:string;reason:string}>; sources_not_running:string[]};
  sources:Record<string,ScheduleSourceDecision>;
}
export interface EtlHealth {timestamp:string; scheduler_status:'unverified'; plan_status:'available'|'unavailable';
  worker_status:'unverified'; data_freshness:'unverified'; manual_trigger:ManualTrigger}
function manual(raw:unknown):ManualTrigger { const v=record(raw); return {available:boolean(v.available),reason:text(v.reason)}; }
export function parseSchedule(raw:unknown):ScheduleResponse {
  const v=record(raw), summary=record(v.summary), entries=Object.entries(record(v.sources));
  if(v.evidence!=='calendar_plan' || entries.length!==ETL_SOURCES.length || entries.some(([name])=>!ETL_SOURCES.includes(name))) throw new Error('Unsupported calendar plan');
  const sources:Record<string,ScheduleSourceDecision>={};
  for(const [name,rawDecision] of entries) {
    const d=record(rawDecision);
    const should_run=boolean(d.should_run);
    if(d.should_run_now !== undefined && d.should_run_now!==should_run) throw new Error('Conflicting plan decisions');
    sources[name]={should_run,reason:text(d.reason),next_run:d.next_run===null?null:date(d.next_run),
      next_reason:text(d.next_reason),current_period:text(d.current_period)};
  }
  const running=integer(summary.sources_running_today), skipping=integer(summary.sources_skipping_today), total=integer(summary.total_sources,1,6);
  if(total!==entries.length || running!==entries.filter(([n])=>sources[n].should_run).length || running+skipping!==total ||
      typeof summary.skip_percentage!=='number' || !Number.isFinite(summary.skip_percentage) ||
      Math.abs(summary.skip_percentage-skipping/total*100)>.11) throw new Error('Inconsistent plan summary');
  if(!Array.isArray(summary.sources_to_run) || !Array.isArray(summary.sources_not_running)) throw new Error('Invalid plan source list');
  const planned=summary.sources_to_run.map(rawItem=>{const item=record(rawItem);return {source:text(item.source),reason:text(item.reason)};});
  const skipped=summary.sources_not_running.map(text);
  if(planned.length!==running || skipped.length!==skipping || new Set([...planned.map(p=>p.source),...skipped]).size!==total ||
    planned.some(p=>!ETL_SOURCES.includes(p.source) || !sources[p.source].should_run || p.reason!==sources[p.source].reason) ||
    skipped.some(n=>!ETL_SOURCES.includes(n) || sources[n].should_run)) throw new Error('Inconsistent plan sources');
  return {timestamp:date(v.timestamp),evidence:'calendar_plan',manual_trigger:manual(v.manual_trigger),sources,
    summary:{sources_running_today:running,sources_skipping_today:skipping,total_sources:total,skip_percentage:summary.skip_percentage,
      efficiency_vs_fixed_schedule:text(summary.efficiency_vs_fixed_schedule),sources_to_run:planned,sources_not_running:skipped}};
}
export function parseEtlHealth(raw:unknown):EtlHealth {
  const v=record(raw);
  if(v.scheduler_status!=='unverified' || v.worker_status!=='unverified' || v.data_freshness!=='unverified' ||
      (v.plan_status!=='available' && v.plan_status!=='unavailable')) throw new Error('Unsupported execution evidence');
  return {timestamp:date(v.timestamp),scheduler_status:'unverified',worker_status:'unverified',data_freshness:'unverified',
    plan_status:v.plan_status as EtlHealth['plan_status'],manual_trigger:manual(v.manual_trigger)};
}
