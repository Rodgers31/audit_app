'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useMutation, useQuery } from '@tanstack/react-query';
import api from '@/lib/api/axios';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useAdmin } from '@/lib/auth/admin';
import { useSocialMutation } from '@/lib/hooks/useSocial';
import { generationApi, decodeDetection } from '@/lib/api/socialGeneration';
import { parseIngestionList, parseIngestionJob, formatIngestionTime } from '@/lib/admin/ingestion';
import { sourceLabel } from '@/lib/admin/sourceLabels';
import { describeGenerationReason } from '@/lib/socialGenerationReasons';
import { SocialErrorBanner } from './SocialNotice';
import styles from './social.module.css';

type Selection = {domain:string;ingestion_id:number;record_ids:number[];reports:boolean;backfill:boolean};
export default function GenerationPreview(){
  const {user}=useAuth(),{isAdmin}=useAdmin();
  return <GenerationSourceFlow key={isAdmin&&user?.id?user.id:'no-access'}/>;
}

function GenerationSourceFlow() {
  const { user } = useAuth(), { isAdmin } = useAdmin(), params=useSearchParams();
  const root=['admin','social',user?.id,'generation'];
  const [domain,setDomain]=useState(params?.get('domain') ?? 'pending_bills');
  const initialJob=params?.get('job') ?? '';
  const [job,setJob]=useState(/^[1-9]\d{0,9}$/.test(initialJob)&&Number(initialJob)<=2147483647 ? initialJob : '');
  const [jobPage,setJobPage]=useState(1),[page,setPage]=useState(1);
  const [reports,setReports]=useState(false),[backfill,setBackfill]=useState(false),[reason,setReason]=useState('');
  const [results,setResults]=useState<ReturnType<typeof decodeDetection>>([]);
  const capabilities=useQuery({queryKey:[...root,'capabilities'],queryFn:({signal})=>generationApi.capabilities(signal),enabled:isAdmin&&!!user?.id,retry:false});
  const selected=capabilities.data?.find(c=>c.domain===domain);
  const supported=!!selected&&(reports?selected.reports:selected.financial);
  const jobs=useQuery({queryKey:[...root,'jobs',domain,jobPage],enabled:isAdmin&&supported,retry:false,queryFn:async({signal})=>parseIngestionList((await api.get('/admin/ingestion-jobs',{params:{domain,status:'completed',days:365,page:jobPage,page_size:20},signal})).data,{page:jobPage,page_size:20})});
  const committed=(j:ReturnType<typeof parseIngestionJob>)=>j.domain===domain&&j.status==='completed'&&!j.dry_run&&j.error_count===0&&j.metadata.source_mode==='live';
  const chosen=useQuery({queryKey:[...root,'selected-job',job],enabled:isAdmin&&supported&&!!job,retry:false,queryFn:async({signal})=>{const value=parseIngestionJob((await api.get(`/admin/ingestion-jobs/${Number(job)}`,{signal})).data);if(value.id!==Number(job))throw new Error('Mismatched job');return value;}});
  const jobValid=!!chosen.data&&!chosen.error&&committed(chosen.data);
  const records=useQuery({queryKey:[...root,'source-records',domain,job,reports,page],enabled:isAdmin&&supported&&jobValid,retry:false,queryFn:({signal})=>generationApi.sourceRecords({domain,ingestion_id:Number(job),reports,page},signal)});
  const selection:Selection={domain,ingestion_id:Number(job),reports,backfill,record_ids:records.data?.record_ids ?? []};
  const identity=JSON.stringify(selection);
  const preview=useMutation({mutationFn:async(body:Selection)=>({body,result:await generationApi.preview(body)})});
  const command=useSocialMutation();
  const current=preview.data&&!preview.error&&JSON.stringify(preview.data.body)===identity ? preview.data : undefined;
  const summaries:Record<string,{status:string;reason:string;count:number}>={};
  for(const item of current?.result.results??[]){const key=item.status+':'+item.reason;summaries[key]??={status:item.status,reason:item.reason,count:0};summaries[key].count++;}
  const busy=preview.isPending||command.isPending;
  const canPreview=isAdmin&&supported&&jobValid&&!chosen.isFetching&&!records.isFetching&&!records.error&&!!selection.record_ids.length;
  const reset=()=>{preview.reset();setResults([]);setReason('');};
  async function detect(){if(!current||!current.result.drafts_enabled||!reason.trim()||!canPreview)return;try{const {domain,ingestion_id,record_ids,backfill,reports:reportMode}=current.body;setResults(await command.run(reportMode?'/generation/detect-reports':'/generation/detect',{domain,ingestion_id,record_ids,backfill,reason},decodeDetection));}catch{/* The command hook retains the exact retry intent. */}}
  return <section className={`${styles.fields} ${styles.sourceCheck}`} aria-labelledby='source-preview-heading'><h2 id='source-preview-heading'>Check a source for drafts</h2>
    <p>Choose a source and completed live job. Preview reads current evidence without saving a baseline or draft. A first observation is normally silent; later meaningful changes can create a draft for human review.</p>
    {capabilities.error&&<SocialErrorBanner error={capabilities.error} onRetry={()=>capabilities.refetch()}/>}
    {capabilities.data&&!selected&&<p role='alert'>The requested source is not registered. Choose a source from the list.</p>}
    <fieldset disabled={!isAdmin||busy} className={styles.fields}><legend>1. Choose committed source evidence</legend>
      <label>Source<select value={domain} onChange={e=>{setDomain(e.target.value);setJob('');setJobPage(1);setPage(1);reset();}}>{capabilities.data?.map(c=><option key={c.domain} value={c.domain}>{sourceLabel(c.domain)}</option>)}</select></label>
      <label>Content to check<select value={reports?'report':'financial'} onChange={e=>{setReports(e.target.value==='report');setPage(1);reset();}}><option value='financial'>Financial figures</option><option value='report'>Neutral report announcement</option></select></label>
      {selected&&<p>{describeGenerationReason(selected.reason)}</p>}
      {!supported&&selected&&<p role='status'>This source does not support the selected content. Choose another source or content type.</p>}
      {supported&&<><label>Completed live job<select value={job} disabled={jobs.isFetching} onChange={e=>{setJob(e.target.value);setPage(1);reset();}}><option value=''>Choose a completed job</option>{jobValid&&!jobs.data?.jobs.some(j=>String(j.id)===job)&&<option value={job}>{sourceLabel(domain)} · {formatIngestionTime(chosen.data!.finished_at)} · job #{job}</option>}{jobs.data?.jobs.filter(committed).map(j=><option key={j.id} value={j.id}>{sourceLabel(j.domain)} · {formatIngestionTime(j.finished_at)} · job #{j.id}</option>)}</select></label>
        {jobs.error&&<SocialErrorBanner error={jobs.error} onRetry={()=>jobs.refetch()}/>}{jobs.data&&!jobs.data.jobs.filter(committed).length&&<p>No completed live jobs on this page. Inspect data updates or browse another page.</p>}
        <div className={styles.actions}><button type='button' className={styles.button} disabled={jobPage===1||jobs.isFetching} onClick={()=>setJobPage(p=>p-1)}>Newer jobs</button><button type='button' className={styles.button} disabled={!jobs.data?.has_more||jobs.isFetching} onClick={()=>setJobPage(p=>p+1)}>Older jobs</button><Link href={`/admin/ingestion?domain=${encodeURIComponent(domain)}`}>Inspect data updates</Link></div>
      </>}
      {chosen.error&&<SocialErrorBanner error={chosen.error} onRetry={()=>chosen.refetch()}/>}{chosen.data&&!chosen.error&&!jobValid&&<p role='alert'>This job is not a completed, error-free live job for this source. Choose another job.</p>}
      {records.error&&<SocialErrorBanner error={records.error} onRetry={()=>records.refetch()}/>}
      {jobValid&&records.data&&!records.error&&<><p>{records.data.total} source candidates. {records.data.record_ids.length?`Checking records ${(page-1)*25+1}–${Math.min(page*25,records.data.total)}.`:'No exact committed records were found.'} Candidate selection does not establish eligibility.</p><div className={styles.actions}><button type='button' className={styles.button} disabled={page===1||records.isFetching} onClick={()=>{setPage(p=>p-1);reset();}}>Previous source batch</button><button type='button' className={styles.button} disabled={!records.data.has_more||records.isFetching} onClick={()=>{setPage(p=>p+1);reset();}}>Next source batch</button></div></>}
      <details className={styles.details}><summary>Historic draft or evidence refresh</summary><div><label><input type='checkbox' checked={backfill} onChange={e=>{setBackfill(e.target.checked);reset();}}/> Explicitly preview a backfill or refresh</label><p>This is a manual action. It can create a historic draft when detection is later confirmed; it does not prove unattended generation.</p></div></details>
      <button type='button' className={`${styles.button} ${styles.primary}`} disabled={!canPreview} onClick={()=>{setResults([]);preview.mutate(selection);}}>2. Preview without saving</button>
    </fieldset>
    {preview.isPending&&<p role='status'>Checking the selected source evidence…</p>}{preview.error&&<SocialErrorBanner error={preview.error}/>}
    {current&&<div className={styles.fields} aria-live='polite'><h3>Preview outcome</h3><p>Draft controls: {current.result.drafts_enabled?'enabled for this source':'off for this source'}. Automatic invocation has separate release requirements.</p>{Object.entries(summaries).map(([key,r])=><article key={key} className={styles.evidence}><strong>{r.count} {r.count===1?'record':'records'} · {r.status.replaceAll('_',' ')}</strong><p>{describeGenerationReason(r.reason)}</p></article>)}<details className={styles.details}><summary>Individual record results</summary><div>{current.result.results.map(r=><p key={r.record_id}>Record #{r.record_id} · {r.status.replaceAll('_',' ')} · {describeGenerationReason(r.reason)}{r.source_document_id?` Source document #${r.source_document_id}.`:''}</p>)}</div></details>
      <details className={styles.details}><summary>3. Run explicit detection for this preview</summary><div className={styles.fields}><p>Detection rechecks the current evidence and may save a baseline or a pending-review draft. It does not publish a post.</p><label>Reason for this manual action<input value={reason} disabled={busy} onChange={e=>setReason(e.target.value)}/></label><button type='button' className={styles.button} disabled={busy||!current.result.drafts_enabled||!reason.trim()||!canPreview} onClick={detect}>Confirm manual detection</button>{!current.result.drafts_enabled&&<p>Draft generation is off. This preview does not change any control.</p>}</div></details>
    </div>}
    {command.error&&<SocialErrorBanner error={command.error}/>}{results.map((r,i)=><p key={i} role='status'>{r.status.replaceAll('_',' ')}{r.post_id&&<> · <Link href={`/admin/social/${r.post_id}`}>Review generated draft</Link></>}</p>)}
  </section>;
}
