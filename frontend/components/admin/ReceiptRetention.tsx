import { parseReceiptRetention } from '@/lib/admin/ingestion';
import styles from './admin.module.css';

export default function ReceiptRetention({ metadata }: { metadata: Record<string, unknown> }) {
  const value = parseReceiptRetention(metadata.receipt_retention);
  return <details className={styles.disclosure}><summary>Retained source evidence · {value.state==='confirmed'?'storage readback confirmed':value.state==='missing_bytes'?'needs attention':'not established'}</summary><div><section aria-label='Source receipt retention'>
    <h2 className='font-display text-lg text-neutral-text'>Source receipt retention</h2>
    {value.state === 'unverified' ? <p role='status'>No verified retention summary is available for this job. Its retention outcome is unknown.</p> : <>
      <p role='status'>{value.state === 'missing_bytes' ? 'Source evidence needs attention. Some captured bytes were not confirmed in storage.' : value.state === 'confirmed' ? 'All observed source captures passed storage readback.' : 'No source captures were observed. Storage retention was not qualified by this job.'}</p>
      <p className='mt-2'>Observed {value.observed} · Verified {value.retained} · Unconfirmed {value.missing}</p>
      <p>Recovered after retry {value.recovered} · Additional requests {value.retry_requests}</p>
    </>}
    <p className='mt-2 text-sm text-neutral-muted'>Data update counts and retained source evidence are separate outcomes. A completed ingestion job does not prove that its source bytes were retained.</p>
  </section></div></details>;
}
