'use client';
import { useSearchParams } from 'next/navigation';
import PageShell from '@/components/layout/PageShell';
import { commandFilters, validCommandId } from '@/lib/admin/etlDispatch';
import { useEtlAccess } from '../../useEtlAccess';
import { CommandReceipt, etlButton } from '../../CommandReceipt';
import { useCommandReceipt } from '../../useCommandReceipt';

export function CommandDetail({commandId}:{commandId:string}) {
  const access=useEtlAccess(), search=useSearchParams();
  const rawReturn=search.get('returnTo') ?? '/admin/etl';
  const returnQuery=rawReturn.startsWith('/admin/etl?') ? commandFilters(new URLSearchParams(rawReturn.slice('/admin/etl?'.length))).canonical.toString() : '';
  const back='/admin/etl'+(returnQuery?'?'+returnQuery:'');
  const receipt=useCommandReceipt(access,commandId);
  const data=access.enabled && !receipt.isError ? receipt.data : undefined;
  return <PageShell title='Command receipt' subtitle='Durable acceptance and recorded execution evidence.' back={{href:back,label:'Back to command history'}}>
    <section className='min-w-0 space-y-4 rounded-2xl border border-neutral-border bg-white p-5 shadow-surface dark:bg-surface-base'>
      {!validCommandId(commandId)?<p role='alert'>Invalid command identity.</p>:
        !access.isAdmin?<p>{access.isLoading?'Verifying access…':'Administrator access required.'}</p>:
        access.denied?<p role='alert'>Administrator access expired. Renew your session to verify access.</p>:
        !access.visible?<p role='status'>Receipt reads paused while this page is hidden.</p>:
        receipt.isError?<p role='alert'>Could not verify this command receipt. Refresh to retry.</p>:
        !data?<p role='status'>Loading command receipt…</p>:
        <><p className='break-all font-mono text-sm text-neutral-text'>{data.id}</p><CommandReceipt command={data} /></>}
      <button className={etlButton} disabled={!access.enabled || !validCommandId(commandId) || receipt.isFetching} onClick={()=>{if(access.current()) void receipt.refetch();}}>Refresh receipt</button>
    </section>
  </PageShell>;
}
