'use client';
import { useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { activeCommand, COMMAND_LABELS, COMMAND_STATUSES, DISPATCH_SOURCES, commandFilters, commandProgress, parseCommandList, type EtlCommand } from '@/lib/admin/etlDispatch';
import type { EtlAccess } from './useEtlAccess';
import { etlButton } from './CommandReceipt';

export function CommandHistory({access}: {access:EtlAccess}) {
  const router=useRouter(), search=useSearchParams();
  const {canonical,...filters}=commandFilters(new URLSearchParams(search));
  const canonicalQuery=canonical.toString(), supplied=search.toString();
  const pendingQuery=useRef<string|null>(null);
  if(pendingQuery.current===canonicalQuery) pendingQuery.current=null;
  const scope=JSON.stringify([access.lifetime,filters]);
  const previous=useRef<{scope:string;entries:Map<string,EtlCommand>}>({scope,entries:new Map()});
  if(previous.current.scope!==scope) previous.current={scope,entries:new Map()};
  useEffect(()=>{
    if(canonicalQuery!==supplied) router.replace('/admin/etl'+(canonicalQuery?'?'+canonicalQuery:''));
  },[canonicalQuery,supplied,router]);
  useEffect(()=>{
    const back=()=>{pendingQuery.current=null;};
    window.addEventListener('popstate',back);
    return ()=>window.removeEventListener('popstate',back);
  },[]);
  const setQuery=(updates:Record<string,string|number>)=>{
    const next=new URLSearchParams(pendingQuery.current ?? canonicalQuery);
    for(const [key,value] of Object.entries(updates)) value==='' ? next.delete(key) : next.set(key,String(value));
    if(!('page' in updates)) next.delete('page');
    pendingQuery.current=commandFilters(next).canonical.toString();
    router.push('/admin/etl'+(pendingQuery.current?'?'+pendingQuery.current:''));
  };
  const history=useQuery({
    queryKey:['admin','etl-commands',access.actorId,access.lifetime,filters],
    enabled:access.enabled,gcTime:0,retry:false,staleTime:0,refetchOnWindowFocus:false,
    queryFn:({signal})=>access.read('/admin/etl/commands',signal,raw=>{
      const value=parseCommandList(raw,filters);
      for(const entry of value.entries) commandProgress(entry,previous.current.entries.get(entry.id));
      for(const entry of value.entries) previous.current.entries.set(entry.id,entry);
      return value;
    },{page:filters.page,page_size:filters.page_size,...(filters.source?{source:filters.source}:{}),...(filters.status?{status:filters.status}:{})}),
    refetchInterval:query=>access.enabled && !query.state.error && query.state.data?.entries.some(activeCommand) ? 5000 : false,
  });
  const data=access.enabled && !history.isError ? history.data : undefined;
  const returnTo='/admin/etl'+(canonicalQuery?'?'+canonicalQuery:'');
  return <section aria-labelledby='history-heading' className='rounded-2xl border border-neutral-border bg-white p-5 shadow-surface dark:bg-surface-base'>
    <div className='flex flex-wrap items-center justify-between gap-3'><h2 id='history-heading' className='font-display text-lg text-neutral-text'>Command history</h2>
      <button className={etlButton} disabled={!access.enabled || history.isFetching} onClick={()=>{if(access.current()) void history.refetch();}}>Refresh command history</button>
    </div>
    <p className='my-3 text-sm text-neutral-muted'>Durable acceptance and recorded execution are separate. Active receipts update every five seconds while this page is visible.</p>
    <div className='mb-4 flex flex-wrap gap-3'>
      <label className='text-sm text-neutral-text'>Command source<select aria-label='Command source' className={etlButton+' ml-2 bg-white dark:bg-surface-base'} value={filters.source} onChange={e=>setQuery({source:e.target.value})}><option value=''>All sources</option>{DISPATCH_SOURCES.map(s=><option key={s}>{s}</option>)}</select></label>
      <label className='text-sm text-neutral-text'>Command status<select aria-label='Command status' className={etlButton+' ml-2 bg-white dark:bg-surface-base'} value={filters.status} onChange={e=>setQuery({status:e.target.value})}><option value=''>All statuses</option>{COMMAND_STATUSES.map(s=><option key={s}>{s}</option>)}</select></label>
      <label className='text-sm text-neutral-text'>Commands per page<select aria-label='Commands per page' className={etlButton+' ml-2 bg-white dark:bg-surface-base'} value={filters.page_size} onChange={e=>setQuery({page_size:e.target.value})}>{Array.from(new Set([10,20,50,filters.page_size])).sort((a,b)=>a-b).map(n=><option key={n}>{n}</option>)}</select></label>
      {(filters.source || filters.status || filters.page_size!==20) && <button className={etlButton} onClick={()=>{pendingQuery.current='';router.push('/admin/etl');}}>Clear command filters</button>}
    </div>
    {!access.enabled ? <p role='status' className='text-sm'>{access.denied?'Command history hidden until access is renewed.':'Command reads paused.'}</p> :
      history.isError ? <p role='alert' className='text-sm'>Could not load command history. Refresh to retry.</p> :
      !data ? <p role='status' className='text-sm'>Loading command history…</p> :
      <><p className='mb-3 text-sm'>{data.entries.length} on this page · {data.total} commands matching</p>
        {data.entries.length===0 ? <p className='text-sm'>No commands match this page.</p> : <ul className='divide-y divide-neutral-border'>
          {data.entries.map(command=><li key={command.id} className='space-y-1 py-3 text-sm text-neutral-text'>
            <Link className='inline-flex min-h-11 max-w-full items-center break-all font-mono underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-gov-sage' href={'/admin/etl/commands/'+command.id+'?returnTo='+encodeURIComponent(returnTo)} aria-label={'View command '+command.id}>{command.source} · {command.id}</Link>
            <p>{COMMAND_LABELS[command.status]}</p><p>{command.dry_run?'Dry Run — no publication':'Run Now'} · accepted {new Date(command.created_at).toLocaleString()}</p>
          </li>)}
        </ul>}
        <nav aria-label='Command history pages' className='mt-4 flex flex-wrap items-center gap-3'>
          <button className={etlButton} disabled={filters.page<=1} onClick={()=>setQuery({page:filters.page-1})}>Previous commands</button>
          <span className='text-sm'>Page {filters.page}</span>
          <button className={etlButton} disabled={!data.has_more || filters.page>=10000} onClick={()=>setQuery({page:filters.page+1})}>Next commands</button>
        </nav>
      </>}
  </section>;
}
