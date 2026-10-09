'use client';
import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import api from '@/lib/api/axios';
import { DISPATCH_SOURCES, dispatchCurrent, dispatchHttpStatus, parseCommandAcceptance, parseDispatchCapability, type CommandAcceptance, type DispatchSource } from '@/lib/admin/etlDispatch';
import { useEtlAccess, type EtlAccess } from './useEtlAccess';
import { CommandReceipt, etlButton } from './CommandReceipt';
import { CommandHistory } from './CommandHistory';
import { useCommandReceipt } from './useCommandReceipt';
import { clearSubmittedIntent, rememberSubmittedIntent, submittedIntent } from './submittedIntent';

interface Intent {source:DispatchSource;dry_run:boolean;key:string;lifetime:number;generation:string;ambiguous:boolean}
export default function DispatchPanel() {
  const access=useEtlAccess();
  const qc=useQueryClient();
  const capability=useQuery({
    queryKey:['admin','etl-dispatch',access.actorId,access.lifetime],
    enabled:access.enabled, gcTime:0, retry:false, refetchOnWindowFocus:false, staleTime:0,
    queryFn:({signal})=>access.read('/admin/etl/dispatch',signal,raw=>parseDispatchCapability(raw)),
  });
  const [clock,setClock]=useState(Date.now);
  const [intent,setIntent]=useState<Intent|null>(null);
  const [confirmation,setConfirmation]=useState(false);
  const [result,setResult]=useState<{lifetime:number;value:CommandAcceptance}|null>(null);
  const [error,setError]=useState<{lifetime:number;ambiguous:boolean}|null>(null);
  const [busy,setBusy]=useState(false);
  const lock=useRef(false);
  const dialog=useRef<HTMLDialogElement>(null);
  const opener=useRef<HTMLButtonElement|null>(null);
  const validIntent=intent?.lifetime===access.lifetime ? intent : null;
  const data=access.enabled && !capability.isError ? capability.data : undefined;
  const ready=dispatchCurrent(data,clock);
  useEffect(() => {
    const timer=setInterval(()=>setClock(Date.now()),1000);
    return ()=>clearInterval(timer);
  },[]);
  useEffect(() => {
    const pending=submittedIntent(access.authActorId);
    if(pending) {
      const recovery={...pending,lifetime:access.lifetime,ambiguous:true};
      setIntent(recovery);setError({lifetime:access.lifetime,ambiguous:true});
    } else {setIntent(null);setError(null);}
    setResult(null);setBusy(false);lock.current=false;setConfirmation(false);
  },[access.lifetime]);
  useEffect(() => {
    const element=dialog.current;
    if (confirmation && validIntent && access.enabled && ready) {
      element?.showModal();
    } else if (element?.open) element.close();
    return ()=> { if(element?.open) element.close(); };
  },[confirmation,validIntent,access.enabled,ready]);
  const cancel=() => {setConfirmation(false);opener.current?.focus();};
  const execute=async (selected:Intent, recovery=false) => {
    if (!access.current(selected.lifetime) || lock.current || (!recovery && (!dispatchCurrent(data) || !data?.sources[selected.source].available))) return;
    lock.current=true;setBusy(true);setResult(null);setError(null);setConfirmation(false);
    rememberSubmittedIntent(access.authActorId!,selected);
    const controller=access.controller();
    try {
      const response=await api.post('/admin/etl/trigger/'+selected.source,
        {dry_run:selected.dry_run,dispatch_generation:selected.generation},
        {signal:controller.signal,headers:{'Idempotency-Key':selected.key}});
      if (!access.current(selected.lifetime) || controller.signal.aborted) return;
      const accepted=parseCommandAcceptance(response.data,selected,response.status);
      clearSubmittedIntent(access.authActorId,selected.key);
      setResult({lifetime:selected.lifetime,value:accepted});setIntent(null);
      void qc.invalidateQueries({queryKey:['admin','etl-commands',access.actorId,access.lifetime]});
    } catch (failure) {
      if (!access.current(selected.lifetime) || controller.signal.aborted) return;
      // Retire a definite first-submission refusal before access invalidation.
      // Refusing recovery cannot prove the original ambiguous POST was absent.
      // Missing/invalid acknowledgment or server failures can follow a commit.
      const status=dispatchHttpStatus(failure);
      const ambiguous=recovery || status===undefined || status>=500;
      if(!ambiguous) clearSubmittedIntent(access.authActorId,selected.key);
      access.rejectAccess(failure);
      if (!access.current(selected.lifetime)) return;
      setIntent(ambiguous ? {...selected,ambiguous:true} : null);
      setError({lifetime:selected.lifetime,ambiguous});
      void qc.resetQueries({queryKey:['admin','etl-dispatch',access.actorId,access.lifetime]});
    } finally {
      access.release(controller);
      if(access.current(selected.lifetime)) {lock.current=false;setBusy(false);opener.current?.focus();}
    }
  };
  const begin=(source:DispatchSource,dry_run:boolean,button:HTMLButtonElement) => {
    if(!access.current() || lock.current || !dispatchCurrent(data) || !data?.sources[source].available) return;
    opener.current=button;
    const same=validIntent?.ambiguous && validIntent.source===source && validIntent.dry_run===dry_run;
    const selected:Intent=same ? validIntent : {source,dry_run,key:crypto.randomUUID(),lifetime:access.lifetime,generation:data.generation!,ambiguous:false};
    setIntent(selected);setResult(null);setError(null);
    if(dry_run) void execute(selected,!!same);
    else setConfirmation(true);
  };
  const receipt=access.enabled && !capability.isError && result?.lifetime===access.lifetime && !error ? result.value : null;
  const failure=access.enabled && error?.lifetime===access.lifetime ? error : null;
  return <div className='space-y-5'>
    <section aria-labelledby='dispatch-heading' className='rounded-2xl border border-neutral-border bg-white p-5 shadow-surface dark:bg-surface-base'>
      <div className='flex flex-wrap items-center justify-between gap-3'>
        <h2 id='dispatch-heading' className='font-display text-lg text-neutral-text'>Dedicated worker dispatch</h2>
        <button className={etlButton} disabled={!access.enabled || capability.isFetching || busy} onClick={()=>{if(access.current()) void capability.refetch();}}>Refresh worker evidence</button>
      </div>
      <p className='mt-2 text-sm text-neutral-muted'>Run Now permits publication under the dedicated runner. Dry Run performs checks with no publication. Calendar and health never enable execution.</p>
      <p role='status' className='my-3 text-sm text-neutral-text'>
        {access.denied ? 'Administrator access expired. Renew your session to verify access.' :
          !access.visible ? 'Worker checks paused while this page is hidden.' :
          capability.isError ? 'Worker evidence unavailable or malformed. Controls are disabled.' :
          !data ? 'Verifying dedicated worker capability…' :
          ready ? data.reason : data.available ? 'Worker evidence expired. Refresh to verify.' : data.reason}
      </p>
      {ready && data && <p className='mb-3 break-all text-xs text-neutral-muted'>Worker lease through {new Date(data.worker.expires_at!).toLocaleString()} · generation {data.generation}</p>}
      <ul className='divide-y divide-neutral-border'>
        {DISPATCH_SOURCES.map(source=><li key={source} className='flex flex-wrap items-center gap-3 py-3'>
          <div className='min-w-0 flex-1 basis-48'><p className='font-mono text-sm font-semibold text-neutral-text'>{source}</p><p className='text-sm text-neutral-muted'>{data?.sources[source].reason ?? 'Validated worker capability required.'}</p></div>
          <div className='flex flex-wrap gap-2'>
            <button className={etlButton} aria-label={'Dry Run · '+source} disabled={!ready || !data?.sources[source].available || busy} onClick={event=>begin(source,true,event.currentTarget)}>Dry Run</button>
            <button className={etlButton+' bg-gov-forest !text-white'} aria-label={'Run Now · '+source} disabled={!ready || !data?.sources[source].available || busy} onClick={event=>begin(source,false,event.currentTarget)}>Run Now</button>
          </div>
        </li>)}
      </ul>
      <dialog ref={dialog} aria-labelledby='run-confirm-title' onCancel={cancel} onKeyDown={event=>{
        if(event.key!=='Tab') return;
        const buttons=event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)');
        const first=buttons[0],last=buttons[buttons.length-1];
        if(event.shiftKey && document.activeElement===first) {event.preventDefault();last?.focus();}
        else if(!event.shiftKey && document.activeElement===last) {event.preventDefault();first?.focus();}
      }} className='m-auto w-[calc(100%-2rem)] max-w-lg rounded-2xl border border-neutral-border bg-white p-6 text-neutral-text backdrop:bg-black/50 dark:bg-surface-base'>
        <h3 id='run-confirm-title' className='font-display text-xl'>Confirm Run Now</h3>
        <p className='my-4 text-sm'>Run {validIntent?.source} now? This permits publication under the dedicated runner. Acceptance queues work; it does not confirm completion.</p>
        <div className='flex flex-wrap gap-3'><button autoFocus className={etlButton} onClick={cancel}>Cancel</button><button className={etlButton+' bg-gov-forest !text-white'} disabled={!ready || !access.enabled || busy} onClick={()=>{if(validIntent) void execute(validIntent,validIntent.ambiguous);}}>Confirm Run Now</button></div>
      </dialog>
      {busy && access.enabled && <p role='status' className='mt-4 text-sm'>Requesting durable acceptance…</p>}
      {failure && <div role='alert' className='mt-4 space-y-2 text-sm text-neutral-text'>
        <p>{failure.ambiguous ? 'Acceptance is uncertain. Recover the same intent to look up its original receipt. This is not an execution retry.' : 'Command was not acknowledged. Refresh worker evidence before a new intent.'}</p>
        {failure.ambiguous && validIntent && <button className={etlButton} disabled={!access.enabled || busy} onClick={()=>void execute(validIntent,true)}>Recover same intent</button>}
      </div>}
      {receipt && <div role='status' className='mt-4 space-y-3 border-t border-neutral-border pt-4'>
        <p>Command accepted. Queued acceptance is not completed work.</p>
        {receipt.replayed && <p>Original receipt recovered. No second command was accepted.</p>}
        <AcceptedReceipt key={receipt.command.id} access={access} accepted={receipt} />
        <Link className='inline-flex min-h-11 items-center underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-gov-sage' href={'/admin/etl/commands/'+receipt.command.id}>View accepted command</Link>
      </div>}
    </section>
    <CommandHistory access={access} />
  </div>;
}

function AcceptedReceipt({access,accepted}:{access:EtlAccess;accepted:CommandAcceptance}) {
  const receipt=useCommandReceipt(access,accepted.command.id,accepted.command);
  return receipt.isError ? <p role='alert'>Could not verify the latest receipt. Open command detail to retry the read.</p> :
    receipt.data && access.enabled ? <CommandReceipt command={receipt.data} /> : null;
}
