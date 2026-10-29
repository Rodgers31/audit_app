import Link from 'next/link';
import { describeGenerationReason } from '@/lib/socialGenerationReasons';
import styles from '@/components/admin/admin.module.css';

export default function GenerationOutcomes({ metadata, domain, jobId }: { metadata: Record<string, unknown>; domain?:string; jobId?:number }) {
  const selection=domain&&jobId?`?domain=${encodeURIComponent(domain)}&job=${jobId}`:'';
  return <section aria-label='Generation outcomes' className={styles.panel}>
    <div className={styles.sectionHeading}><h2>Draft outcome</h2><Link className={styles.button} href='/admin/social'>Inspect saved drafts</Link></div>
    <p>Ingestion completion and draft creation are separate. Publishing and uploads require their own authorization.</p>
    {(['post_commit_generation', 'post_commit_report_generation'] as const).map(key => {
      const value = metadata[key] as Record<string, unknown> | undefined;
      return <article key={key} className='mt-4'>
        <h3>{key === 'post_commit_generation' ? 'Financial drafts' : 'Neutral report drafts'}</h3>
        {!value ? <p>No generation receipt recorded for this job. Its outcome is unknown.</p> : <>
          <p>{describeGenerationReason(value.reason)}</p>
          {value.execution_unverified ? <p>Execution is unverified. Counters are unknown; inspect existing drafts before retrying.</p> :
            <p>Processed {String(value.processed)} · Drafts created {String(value.drafts_created)} · Baselines {String(value.baselines)} · Unchanged {String(value.unchanged)} · Refused {String(value.refused)}</p>}
          {!value.execution_unverified&&Number(value.baselines)>0&&<p>A first qualified observation records a silent baseline. It does not automatically announce historic figures.</p>}
          {!value.execution_unverified&&Number(value.unchanged)>0&&<p>Unchanged evidence does not need a duplicate draft.</p>}
          {value.confirmed && typeof value.confirmed === 'object' ? <p>Confirmed before uncertainty: {String((value.confirmed as Record<string, unknown>).processed)} processed · {String((value.confirmed as Record<string, unknown>).drafts_created)} drafts. The current record may also have committed.</p> : null}
          {value.refusal_reasons && typeof value.refusal_reasons === 'object' ? <ul aria-label={value.execution_unverified ? 'Confirmed refusals before uncertainty' : 'Evidence refusals'}>{Object.entries(value.refusal_reasons).map(([reason, count]) => <li key={reason}>{describeGenerationReason(reason)} ({String(count)})</li>)}</ul> : null}
        </>}
      </article>;
    })}
    <div className={`${styles.filters} mt-5`}><Link className={styles.button} href={`/admin/social/automation${selection}`}>Check this source without saving</Link><span className={styles.quiet}>Preview explains eligibility. An explicit manual detection is a separate action.</span></div>
  </section>;
}
