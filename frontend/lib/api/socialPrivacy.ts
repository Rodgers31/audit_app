import api from '@/lib/api/axios';
import { toSocialError, SocialApiError } from './social';
export interface PrivacyPlan {
  id: string; receipt_id: string; proposed_by: string; policy_key: string; policy_hash: string; plan_hash: string;
  evidence: string; scope: {credentials:{id:string;version:number}[];flows:{id:string;content_hash:string;identity_hash:string}[];media_assets:{id:string;scope_hash:string}[]};
  decision: 'pending_review'|'approved'|'rejected'; approved_by: string|null;
  execution: { id: string; state: 'prepared'|'executing'|'outcome_unknown'|'completed'; version: number; result: Record<string, unknown> }|null;
}
export interface PrivacyRequest { id: string; kind: string; state: string; resolution: string; affected_count: number }
export interface PrivacyRequestDetail extends PrivacyRequest { credentials: string[]; flows: string[]; plans: PrivacyPlan[] }
export interface PrivacyQueue { requests: PrivacyRequest[]; total: number; page: number; page_size: number; has_more: boolean; workflow_enabled: boolean; execution_enabled: boolean; policies: Record<string,string> }
function invalid(): never { throw new SocialApiError('INVALID_RESPONSE', 'Privacy response could not be verified. Refresh before continuing.'); }
function object(v: unknown): Record<string, unknown> { if (!v || typeof v !== 'object' || Array.isArray(v)) invalid(); return v as Record<string, unknown>; }
function string(v: unknown): string { if(typeof v !== 'string') invalid(); return v; }
function number(v: unknown): number { if(typeof v !== 'number' || !Number.isSafeInteger(v) || v<0) invalid(); return v; }
function bool(v: unknown): boolean { if(typeof v !== 'boolean') invalid(); return v; }
function array(v: unknown): unknown[] { if(!Array.isArray(v)) invalid(); return v; }
function request(v: unknown): PrivacyRequest { const o=object(v); return {id:string(o.id),kind:string(o.kind),state:string(o.state),resolution:string(o.resolution),affected_count:number(o.affected_count)}; }
export function decodePrivacyPlan(v: unknown): PrivacyPlan {
  const o=object(v), scope=object(o.scope); const decision=string(o.decision ?? 'pending_review');
  if(!['pending_review','approved','rejected'].includes(decision)) invalid();
  let execution: PrivacyPlan['execution']=null;
  if(o.execution != null) { const e=object(o.execution), state=string(e.state); if(!['prepared','executing','outcome_unknown','completed'].includes(state)||number(e.version)<1) invalid(); execution={id:string(e.id),state:state as NonNullable<PrivacyPlan['execution']>['state'],version:number(e.version),result:object(e.result)}; }
  const credentials=array(scope.credentials).map(v=>{const entry=object(v),version=number(entry.version);if(version<1)invalid();return {id:string(entry.id),version};});
  const flows=array(scope.flows).map(v=>{const entry=object(v),content_hash=string(entry.content_hash);if(!/^[a-f0-9]{64}$/.test(content_hash))invalid();const identity_hash=string(entry.identity_hash);if(!/^[a-f0-9]{64}$/.test(identity_hash))invalid();return {id:string(entry.id),content_hash,identity_hash};});
  const media_assets=array(scope.media_assets).map(v=>{const entry=object(v);const scope_hash=string(entry.scope_hash);if(!/^[a-f0-9]{64}$/.test(scope_hash))invalid();return {id:string(entry.id),scope_hash};});
  return {id:string(o.id),receipt_id:string(o.receipt_id),proposed_by:string(o.proposed_by),policy_key:string(o.policy_key),policy_hash:string(o.policy_hash),plan_hash:string(o.plan_hash),evidence:string(o.evidence),scope:{credentials,flows,media_assets},decision:decision as PrivacyPlan['decision'],approved_by:o.approved_by==null?null:string(o.approved_by),execution};
}
export function decodePrivacyQueue(v: unknown): PrivacyQueue { const o=object(v), policies=object(o.policies); for(const value of Object.values(policies)) string(value); return {requests:array(o.requests).map(request),total:number(o.total),page:number(o.page),page_size:number(o.page_size),has_more:bool(o.has_more),workflow_enabled:bool(o.workflow_enabled),execution_enabled:bool(o.execution_enabled),policies:policies as Record<string,string>}; }
async function read<T>(url: string, decode:(v:unknown)=>T): Promise<T> { try { return decode((await api.get('/admin/social/privacy'+url)).data); } catch(e) { throw toSocialError(e); } }
export const privacyApi={
  queue:(page:number)=>read(`/requests?page=${page}&page_size=20`,decodePrivacyQueue),
  detail:(id:string)=>read(`/requests/${encodeURIComponent(id)}`,v=>{ const o=object(v), r=request(v); if(r.id!==id) invalid(); return {...r,credentials:array(o.credentials).map(string),flows:array(o.flows).map(string),plans:array(o.plans).map(decodePrivacyPlan)}; }),
  command:async(path:string, body:object, key:string):Promise<PrivacyPlan>=>{ try{return decodePrivacyPlan((await api.post('/admin/social/privacy'+path,body,{headers:{'Idempotency-Key':key}})).data);}catch(e){throw toSocialError(e);} },
};
