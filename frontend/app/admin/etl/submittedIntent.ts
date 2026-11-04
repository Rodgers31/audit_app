'use client';
import { DISPATCH_SOURCES, validCommandId, type DispatchSource } from '@/lib/admin/etlDispatch';

export interface SubmittedIntent {source:DispatchSource;dry_run:boolean;key:string;generation:string}
const prefix='auditgava.etl.submitted-intent.v1:';
export class IntentRecoveryError extends Error {
  constructor() {super('Browser command recovery is unavailable. Keep this tab open and reconcile the unconfirmed command before starting another.');}
}
function valid(intent:SubmittedIntent) {
  return !!intent && Object.keys(intent).sort().join(',')==='dry_run,generation,key,source' &&
    DISPATCH_SOURCES.includes(intent.source) && typeof intent.dry_run==='boolean' && validCommandId(intent.key) && validCommandId(intent.generation);
}
function storageKey(actorId:string) {if(!validCommandId(actorId))throw new IntentRecoveryError();return prefix+actorId;}
function read(actorId:string):SubmittedIntent[] {
  const key=storageKey(actorId);
  try {
    const raw=sessionStorage.getItem(key);if(raw===null)return [];
    if(raw.length>16384)throw new IntentRecoveryError();
    const value=JSON.parse(raw);
    if(!value || Object.keys(value).sort().join(',')!=='actorId,intents,version' || value.version!==1 || value.actorId!==actorId || !Array.isArray(value.intents) || value.intents.length>32)throw new IntentRecoveryError();
    const keys=new Set<string>(),semantics=new Set<string>();
    for(const intent of value.intents) {
      if(!valid(intent) || keys.has(intent.key) || semantics.has(intent.source+':'+intent.dry_run))throw new IntentRecoveryError();
      keys.add(intent.key);semantics.add(intent.source+':'+intent.dry_run);
    }
    return value.intents;
  }catch {throw new IntentRecoveryError();}
}
function write(actorId:string,intents:SubmittedIntent[]) {
  if(intents.length>32 || intents.some(intent=>!valid(intent)))throw new IntentRecoveryError();
  const key=storageKey(actorId),raw=JSON.stringify({version:1,actorId,intents});
  try {sessionStorage.setItem(key,raw);if(sessionStorage.getItem(key)!==raw)throw new IntentRecoveryError();}
  catch {throw new IntentRecoveryError();}
}
// Tab-scoped metadata survives reloads and auth remounts. No credentials,
// receipts or job bodies are stored. Recovery is always an explicit action.
export function rememberSubmittedIntent(actorId:string, intent:SubmittedIntent) {
  const selected={source:intent.source,dry_run:intent.dry_run,key:intent.key,generation:intent.generation};
  if(!valid(selected))throw new IntentRecoveryError();
  const intents=read(actorId),existing=intents.find(intent=>intent.key===selected.key || intent.source===selected.source && intent.dry_run===selected.dry_run);
  if(existing) {
    if(existing.key!==selected.key || existing.source!==selected.source || existing.dry_run!==selected.dry_run || existing.generation!==selected.generation)throw new IntentRecoveryError();
    // Verify writes even on an explicit recovery; storage failure must refuse
    // before another POST rather than silently rely on browser memory.
  } else intents.push(selected);
  write(actorId,intents);
}
export function submittedIntent(actorId:string|null,match?:{source:DispatchSource;dry_run:boolean}) {
  if(actorId===null)return null;
  const intents=read(actorId);
  return (match?intents.find(intent=>intent.source===match.source && intent.dry_run===match.dry_run):intents[0])??null;
}
export function clearSubmittedIntent(actorId:string|null, key:string) {
  if(actorId===null)return;
  if(!validCommandId(key))throw new IntentRecoveryError();
  const intents=read(actorId);if(!intents.some(intent=>intent.key===key))return;
  const remaining=intents.filter(intent=>intent.key!==key);
  if(remaining.length)write(actorId,remaining);
  else try {sessionStorage.removeItem(storageKey(actorId));if(sessionStorage.getItem(storageKey(actorId))!==null)throw new IntentRecoveryError();}
  catch {throw new IntentRecoveryError();}
}
