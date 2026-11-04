import api from '@/lib/api/axios';
import { acknowledgedUuid, sameJson } from './socialAcknowledgement';
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
async function read<T>(url: string, decode:(v:unknown)=>T,signal?:AbortSignal): Promise<T> { try { return decode((await api.get('/admin/social/privacy'+url,{signal})).data); } catch(e) { throw toSocialError(e); } }
export const privacyApi={
  queue:(page:number,signal?:AbortSignal)=>read(`/requests?page=${page}&page_size=20`,decodePrivacyQueue,signal),
  detail:(id:string,signal?:AbortSignal)=>read(`/requests/${encodeURIComponent(id)}`,v=>{ const o=object(v), r=request(v); if(r.id!==id) invalid(); return {...r,credentials:array(o.credentials).map(string),flows:array(o.flows).map(string),plans:array(o.plans).map(decodePrivacyPlan)}; },signal),
  command:async(path:string, body:object, key:string, context?:{actor:string;plan?:PrivacyPlan}):Promise<PrivacyPlan>=>{
    try {
      const result=decodePrivacyPlan((await api.post('/admin/social/privacy'+path,body,{headers:{'Idempotency-Key':key}})).data), input=object(body);
      if(path==='/plans') {
        const ids=(value:unknown)=>array(value ?? []).map(value=>acknowledgedUuid(string(value))??invalid()).sort();
        if(result.decision!=='pending_review'||result.approved_by!==null||result.execution!==null||result.id!==acknowledgedUuid(key)||result.receipt_id!==acknowledgedUuid(string(input.receipt_id))||result.policy_key!==input.policy_key||result.policy_hash!==input.policy_hash||result.evidence!==input.evidence||context&&result.proposed_by!==context.actor||!sameJson(ids(result.scope.credentials.map(item=>item.id)),ids(input.erase_credentials))||!sameJson(ids(result.scope.flows.map(item=>item.id)),ids(input.erase_flows))||!sameJson(ids(result.scope.media_assets.map(item=>item.id)),ids(input.media_assets)))invalid();
      } else {
        const match=/^\/plans\/([^/]+)\/(decision|execute|reconcile)$/.exec(path);
        if(!match||result.id!==match[1])invalid();
        const prior=context?.plan;
        if(prior&&(result.id!==prior.id||result.receipt_id!==prior.receipt_id||result.proposed_by!==prior.proposed_by||result.policy_key!==prior.policy_key||result.policy_hash!==prior.policy_hash||result.plan_hash!==prior.plan_hash||result.evidence!==prior.evidence||!sameJson(result.scope,prior.scope)))invalid();
        if(match[2]==='decision') {
          if(result.plan_hash!==input.plan_hash||result.decision!==input.decision||!result.approved_by||context&&result.approved_by!==context.actor||result.decision==='approved'&&!result.execution||result.decision==='rejected'&&result.execution!==null)invalid();
        } else {
          // The UI already holds this exact execution. Do not infer its hash,
          // custody or operation identity from an arbitrary returned plan.
          if(!prior?.execution||!result.execution||result.decision!=='approved'||result.approved_by!==prior.approved_by||result.execution.id!==prior.execution.id||result.execution.state!=='completed'||typeof input.expected_version!=='number'||prior.execution.version!==input.expected_version||result.execution.version<(prior.execution.state==='completed'?input.expected_version:input.expected_version+1)||result.execution.result.scope_completed!==true||result.execution.result.request_completed!==false)invalid();
        }
      }
      return result;
    } catch(e){throw toSocialError(e);}
  },
};
