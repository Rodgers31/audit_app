'use client';
import Link from 'next/link';
import styles from '@/components/admin/admin.module.css';
import { sourceLabel } from '@/lib/admin/sourceLabels';
import { COMMAND_LABELS, type EtlCommand } from '@/lib/admin/etlDispatch';

export const etlButton = 'min-h-11 rounded-lg border border-neutral-border px-3 py-2 text-sm font-semibold text-neutral-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-gov-sage disabled:opacity-50';
export function CommandReceipt({command}: {command:EtlCommand}) {
  const next=command.status==='queued'?'This request is accepted and waiting. Follow its receipt; a second request is not needed.':command.status==='running'?'Execution is recorded as running. Follow this receipt for its outcome; work may already have committed.':command.status==='completed'?'Inspect the linked data update for saved counts and its separate draft outcomes.':'Completion was not confirmed. Inspect the linked data observation and dedicated runner logs before requesting new work.';
  return <div className='space-y-4 break-words text-sm text-neutral-text'>
    <p className='font-semibold'>{COMMAND_LABELS[command.status]}</p>
    <p>{sourceLabel(command.source)} · {command.dry_run ? 'Dry Run — no publication' : 'Run Now — publication permitted by the runner'}</p>
    <p className={styles.notice}>{next}</p>
    <dl className={styles.facts}>
      <div><dt className='text-neutral-muted'>Accepted</dt><dd>{new Date(command.created_at).toLocaleString()}</dd></div>
      <div><dt className='text-neutral-muted'>Last recorded change</dt><dd>{new Date(command.updated_at).toLocaleString()} · version {command.version}</dd></div>
      {command.started_at && <div><dt className='text-neutral-muted'>Started</dt><dd>{new Date(command.started_at).toLocaleString()}</dd></div>}
      {command.finished_at && <div><dt className='text-neutral-muted'>Finished</dt><dd>{new Date(command.finished_at).toLocaleString()}</dd></div>}
    </dl>
    {command.job_id !== null && <Link href={'/admin/ingestion/'+command.job_id} className='inline-flex min-h-11 items-center underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-gov-sage'>Inspect data and draft outcomes · job #{command.job_id}</Link>}
    <p className='text-neutral-muted'>A command receipt does not certify financial data freshness. History is an operational observation, not an immutable audit ledger.</p>
  </div>;
}
