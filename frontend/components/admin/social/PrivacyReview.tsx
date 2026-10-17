'use client';
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/AuthProvider';
import { privacyApi, PrivacyPlan } from '@/lib/api/socialPrivacy';
import { SocialErrorBanner } from './SocialNotice';
import styles from './social.module.css';

export default function PrivacyReview() {
  const {user}=useAuth(); const qc=useQueryClient();
  const [page,setPage]=useState(1),[selected,setSelected]=useState(''),[policy,setPolicy]=useState('');
  const [evidence,setEvidence]=useState(''),[reason,setReason]=useState(''),[credentials,setCredentials]=useState<string[]>([]),[flows,setFlows]=useState<string[]>([]);
  const [pending,setPending]=useState(false),[error,setError]=useState<unknown>(),[confirm,setConfirm]=useState(false),[mediaIds,setMediaIds]=useState('');
  const queue=useQuery({queryKey:['admin','social','privacy',user?.id,page],queryFn:()=>privacyApi.queue(page),enabled:!!user,retry:false,refetchOnWindowFocus:false});
  const detail=useQuery({queryKey:['admin','social','privacy',user?.id,selected],queryFn:()=>privacyApi.detail(selected),enabled:!!user&&!!selected,retry:false,refetchOnWindowFocus:false});
  async function run(path:string,body:object){setPending(true);setError(undefined);try{await privacyApi.command(path,body,crypto.randomUUID());setConfirm(false);await qc.invalidateQueries({queryKey:['admin','social','privacy',user?.id]});}catch(e){setError(e);}finally{setPending(false);}}
  function choose(id:string){setSelected(id);setCredentials([]);setFlows([]);setMediaIds('');setEvidence('');setReason('');setError(undefined);setConfirm(false);}
  function toggle(value:string,items:string[],set:(v:string[])=>void){set(items.includes(value)?items.filter(i=>i!==value):[...items,value]);}
  function planActions(plan:PrivacyPlan){const execution=plan.execution;return <article className={styles.schedule} key={plan.id}>
    <h3>Approved scope review</h3><p>Plan {plan.id}</p><p>Policy: {plan.policy_key} · {plan.decision.replaceAll('_',' ')}</p><p>{plan.evidence}</p>
    <p>{plan.scope.credentials.length} credential envelopes · {plan.scope.flows.length} pending flows · {plan.scope.media_assets.length} media assets</p>
    <details><summary>Exact approved identities and hashes</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify({scope:plan.scope,plan_hash:plan.plan_hash,policy_hash:plan.policy_hash},null,2)}</pre></details>
    {plan.decision==='pending_review'&&<><label>Independent review reason<textarea value={reason} onChange={e=>setReason(e.target.value)} maxLength={2000}/></label><div className={styles.toolbar}>
      <button type='button' className={styles.button} disabled={pending||reason.trim().length<10||plan.proposed_by===user?.id} onClick={()=>run(`/plans/${plan.id}/decision`,{plan_hash:plan.plan_hash,decision:'approved',reason})}>Approve exact scope</button>
      <button type='button' className={styles.button} disabled={pending||reason.trim().length<10||plan.proposed_by===user?.id} onClick={()=>run(`/plans/${plan.id}/decision`,{plan_hash:plan.plan_hash,decision:'rejected',reason})}>Reject scope</button></div><p className={styles.muted}>An operator-configured approver other than the proposer must review this scope.</p></>}
    {execution&&<><p>Execution: {execution.state.replaceAll('_',' ')}</p>{execution.state==='completed'?<p>Approved scope completed. The overall request remains open for retained history, provider copies and backup review.</p>:<><label><input type='checkbox' checked={confirm} onChange={e=>setConfirm(e.target.checked)}/> I reviewed this exact scope and the retained-history limits.</label><button type='button' className={styles.button} disabled={pending||!confirm||!queue.data?.execution_enabled} onClick={()=>run(`/plans/${plan.id}/${execution.state==='prepared'?'execute':'reconcile'}`,{expected_version:execution.version})}>{execution.state==='prepared'?'Execute approved scope':'Reconcile existing operation'}</button></>}</>}
  </article>;}
  return <div className={styles.workspace}>
    <p>Requests identify the person asking for review. Deletion requires an approved policy, a separate human approver and verified execution. Audit, delivery and financial provenance remain retained.</p>
    {queue.data&&!queue.data.workflow_enabled&&<p role='status'>Privacy approval is disabled until an operator installs the policy and eligible approvers. Publishing and uploads remain off.</p>}
    {queue.data&&!queue.data.execution_enabled&&<p>Execution is disabled pending policy and backup custody approval.</p>}
    {!!(queue.error||detail.error||error)&&<SocialErrorBanner error={error||detail.error||queue.error} onRetry={()=>{queue.refetch();if(selected)detail.refetch();}}/>}
    <button className={styles.button} type='button' disabled={pending} onClick={()=>{queue.refetch();if(selected)detail.refetch();}}>Refresh requests</button>
    {!queue.data&&!queue.error&&<p role='status'>Loading privacy requests…</p>}
    {queue.data&&queue.data.requests.length===0&&<p>No privacy requests on this page.</p>}
    <div className={styles.fields}>{queue.data?.requests.map(r=><button type='button' key={r.id} className={styles.button} aria-pressed={selected===r.id} onClick={()=>choose(r.id)}>{r.kind.replaceAll('_',' ')} · {r.state.replaceAll('_',' ')} · {r.id}</button>)}</div>
    {queue.data&&<div className={styles.toolbar}><button type='button' className={styles.button} disabled={page===1||pending} onClick={()=>setPage(page-1)}>Previous page</button><span>Page {page} · {queue.data.total} requests</span><button type='button' className={styles.button} disabled={!queue.data.has_more||pending} onClick={()=>setPage(page+1)}>Next page</button></div>}
    {detail.data&&<section className={styles.fields}><h2>Request review</h2><p>Ownership resolution: {detail.data.resolution.replaceAll('_',' ')}</p>{detail.data.plans.map(planActions)}
      {queue.data?.workflow_enabled&&detail.data.kind==='data_deletion'&&<form className={styles.schedule} onSubmit={e=>{e.preventDefault();run('/plans',{receipt_id:selected,policy_key:policy,policy_hash:queue.data!.policies[policy],evidence,erase_credentials:credentials,erase_flows:flows,media_assets:mediaIds.split(/[\s,]+/).filter(Boolean)});}}>
        <h3>Propose a bounded scope</h3><label>Approved retention policy<select required value={policy} onChange={e=>setPolicy(e.target.value)}><option value=''>Choose an operator-approved policy</option>{Object.keys(queue.data.policies).map(key=><option key={key}>{key}</option>)}</select></label>
        <fieldset><legend>Credential envelopes to erase</legend>{detail.data.credentials.map(id=><label key={id}><input type='checkbox' checked={credentials.includes(id)} onChange={()=>toggle(id,credentials,setCredentials)}/>{id}</label>)}</fieldset>
        <fieldset><legend>Pending flows to erase</legend>{detail.data.flows.map(id=><label key={id}><input type='checkbox' checked={flows.includes(id)} onChange={()=>toggle(id,flows,setFlows)}/>{id}</label>)}</fieldset>
        <label>Media asset UUIDs, separated by commas or new lines<textarea value={mediaIds} maxLength={4000} onChange={e=>setMediaIds(e.target.value)}/></label><label>Policy and ownership evidence<textarea required minLength={10} maxLength={2000} value={evidence} onChange={e=>setEvidence(e.target.value)}/></label>
        <p>Media scopes are inspected and frozen by the separately configured media authority port before approval. Referenced originals remain protected.</p>
        <button type='submit' className={styles.button} disabled={pending||!policy||(!credentials.length&&!flows.length&&!mediaIds.trim())||evidence.trim().length<10}>Submit scope for independent review</button>
      </form>}
    </section>}
  </div>;
}
